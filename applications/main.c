#include <rtthread.h>
#include <rtdevice.h>
#include <board.h>
#include <reent.h>
#include <finsh.h>

#include "common/m33_m55_comm.h"
#include "m33/audio_capture.h"
#include "m33/audio_playback.h"
#include "m33/bt_board_bridge.h"
#include "m33/app_ble_service.h"
#include "m33/bt_app_gatt_handler.h"
#include "m33/bt_hci_transport.h"
#include "m33/can_driver.h"
#include "m33/control_manager.h"
#include "m33/http_server.h"
#include "m33/input_buffer.h"
#include "m33/m55_qa_bridge.h"
#include "m33/m55_model_bridge.h"
#include "m33/m55_model_input_bridge.h"
#include "m33/openclaw_integration.h"
#include "m33/safety_system.h"
#include "m33/sensor_manager.h"
#include "m33/xiaozhi_pcm_probe_data.h"

__attribute__((weak)) struct _reent _impure_data;

#define LED_PIN_B GET_PIN(16, 5)
#define FRAME_PERIOD_MS 100
#define PCM_CAPTURE_MAX_BYTES (16000U * 2U * 2U)

#ifndef M33_ENABLE_BT_HCI
#define M33_ENABLE_BT_HCI 0
#endif

typedef enum
{
    PCM_MODE_IDLE = 0,
    PCM_MODE_MANUAL,
    PCM_MODE_LISTEN
} m33_pcm_mode_t;

typedef struct
{
    rt_uint32_t loop_count;
    safety_monitor_t safety;
    rt_bool_t pcm_capture_active;
    m33_pcm_mode_t pcm_mode;
    rt_uint8_t *pcm_buffer;
    rt_uint32_t pcm_capacity;
    rt_uint32_t pcm_length;
} m33_runtime_t;

static m33_runtime_t g_runtime;

static void m33_publish_audio_capture(void);
static rt_err_t m33_publish_pcm_shared_buffer(const rt_uint8_t *pcm, rt_uint32_t len);

static void m33_log_cm55_boot_state(const char *tag)
{
    rt_kprintf("[m33] cm55 %s boot_addr=0x%08lx status=%lu ns_vtor=0x%08lx ctl=0x%08lx cmd=0x%08lx\n",
               tag,
               (unsigned long)CY_CM55_APP_BOOT_ADDR,
               (unsigned long)Cy_SysGetCM55Status(MXCM55),
               (unsigned long)MXCM55->CM55_NS_VECTOR_TABLE_BASE,
               (unsigned long)MXCM55->CM55_CTL,
               (unsigned long)MXCM55->CM55_CMD);
}

static void m33_cm55_restart(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    m33_log_cm55_boot_state("before-restart");
    Cy_SysResetCM55(MXCM55, 10);
    Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
    rt_thread_mdelay(100);
    m33_log_cm55_boot_state("after-restart");
}
MSH_CMD_EXPORT(m33_cm55_restart, Reset and enable CM55 from M33 shell);

static void m33_pcm_capture_callback(const uint8_t *data, uint32_t len)
{
    uint32_t writable;

    if (!g_runtime.pcm_capture_active || (g_runtime.pcm_buffer == RT_NULL) || (data == RT_NULL) || (len == 0))
    {
        return;
    }

    if (g_runtime.pcm_length >= g_runtime.pcm_capacity)
    {
        if (g_runtime.pcm_mode == PCM_MODE_LISTEN)
        {
            if (len >= g_runtime.pcm_capacity)
            {
                rt_memcpy(g_runtime.pcm_buffer, data + (len - g_runtime.pcm_capacity), g_runtime.pcm_capacity);
                g_runtime.pcm_length = g_runtime.pcm_capacity;
                return;
            }

            rt_memmove(g_runtime.pcm_buffer,
                       g_runtime.pcm_buffer + len,
                       g_runtime.pcm_capacity - len);
            g_runtime.pcm_length = g_runtime.pcm_capacity - len;
        }
        else
        {
            return;
        }
    }

    writable = g_runtime.pcm_capacity - g_runtime.pcm_length;
    if (len > writable)
    {
        len = writable;
    }

    rt_memcpy(g_runtime.pcm_buffer + g_runtime.pcm_length, data, len);
    g_runtime.pcm_length += len;

    if (g_runtime.pcm_mode == PCM_MODE_LISTEN)
    {
        m33_publish_audio_capture();
        g_runtime.pcm_length = 0;
    }
}

static void m33_publish_audio_capture(void)
{
    rt_err_t ret;

    if ((g_runtime.pcm_buffer == RT_NULL) || (g_runtime.pcm_length == 0))
    {
        rt_kprintf("[m33] pcm publish skipped len=0\n");
        return;
    }

    ret = m33_publish_pcm_shared_buffer(g_runtime.pcm_buffer, g_runtime.pcm_length);
    if (ret != RT_EOK)
    {
        rt_kprintf("[m33] pcm publish failed ret=%d len=%lu\n",
                   ret,
                   (unsigned long)g_runtime.pcm_length);
    }
}

static rt_err_t m33_publish_pcm_shared_buffer(const rt_uint8_t *pcm, rt_uint32_t len)
{
    m33_m55_message_t msg;
    rt_uint32_t seq;
    rt_err_t ret;

    if ((pcm == RT_NULL) || (len == 0))
    {
        rt_kprintf("[m33] pcm publish skipped len=0\n");
        return -RT_EINVAL;
    }

    if (len > M33_M55_PCM_SHARED_CAPACITY)
    {
        rt_kprintf("[m33] pcm publish too large len=%lu cap=%lu\n",
                   (unsigned long)len,
                   (unsigned long)M33_M55_PCM_SHARED_CAPACITY);
        return -RT_EINVAL;
    }

    seq = g_m33_m55_pcm_shared.seq + 1U;
    g_m33_m55_pcm_shared.seq = seq;
    g_m33_m55_pcm_shared.total_len = len;
    g_m33_m55_pcm_shared.sample_rate = 16000U;
    g_m33_m55_pcm_shared.channels = 1U;
    g_m33_m55_pcm_shared.bits_per_sample = 16U;
    g_m33_m55_pcm_shared.timestamp = rt_tick_get_millisecond();
    g_m33_m55_pcm_shared.reserved = 0U;
    g_m33_m55_pcm_shared.crc32 = 0U;
    rt_memcpy((void *)g_m33_m55_pcm_shared.data, pcm, len);
    rt_hw_cpu_dcache_ops(RT_HW_CACHE_FLUSH, (void *)g_m33_m55_pcm_shared.data, len);

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_SENSOR_STREAM;
    msg.payload.sensor_stream.source = MODEL_INPUT_SRC_AUDIO_PCM;
    msg.payload.sensor_stream.format = MODEL_INPUT_FMT_PCM_S16;
    msg.payload.sensor_stream.channels = 1U;
    msg.payload.sensor_stream.sample_rate = 16000U;
    msg.payload.sensor_stream.frame_samples = len / 2U;
    msg.payload.sensor_stream.total_len = len;
    msg.payload.sensor_stream.chunk_index = seq;
    msg.payload.sensor_stream.chunk_len = len;
    msg.payload.sensor_stream.timestamp = g_m33_m55_pcm_shared.timestamp;

    ret = m33_m55_comm_publish(&msg);
    if (ret != RT_EOK)
    {
        rt_kprintf("[m33] pcm notify publish failed ret=%d seq=%lu len=%lu\n",
                   ret,
                   (unsigned long)seq,
                   (unsigned long)len);
        return ret;
    }

    rt_kprintf("[m33] pcm shared notify seq=%lu len=%lu\n",
               (unsigned long)seq,
               (unsigned long)len);
    return RT_EOK;
}

static void m33_start_pcm_capture(void)
{
    rt_err_t ret;

    if (g_runtime.pcm_capture_active)
    {
        rt_kprintf("[m33] pcm capture already active\n");
        return;
    }

    if (g_runtime.pcm_buffer == RT_NULL)
    {
        g_runtime.pcm_capacity = PCM_CAPTURE_MAX_BYTES;
        g_runtime.pcm_buffer = (rt_uint8_t *)rt_malloc(g_runtime.pcm_capacity);
        if (g_runtime.pcm_buffer == RT_NULL)
        {
            rt_kprintf("[m33] pcm buffer alloc failed size=%lu\n", (unsigned long)g_runtime.pcm_capacity);
            return;
        }
    }

    if (audio_capture_init() != RT_EOK)
    {
        rt_kprintf("[m33] pcm capture init failed\n");
        return;
    }

    g_runtime.pcm_length = 0;
    g_runtime.pcm_capture_active = RT_TRUE;
    ret = audio_capture_start(m33_pcm_capture_callback);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        g_runtime.pcm_capture_active = RT_FALSE;
        rt_kprintf("[m33] pcm capture start failed ret=%d\n", ret);
        return;
    }

    rt_kprintf("[m33] pcm capture started ret=%d running=%d\n",
               ret,
               audio_capture_is_running() ? 1 : 0);
}

static void m33_start_pcm_listen(void)
{
    rt_err_t ret;

    if ((g_runtime.pcm_mode == PCM_MODE_LISTEN) && g_runtime.pcm_capture_active)
    {
        rt_kprintf("[m33] pcm listen already active\n");
        return;
    }

    if (g_runtime.pcm_buffer == RT_NULL)
    {
        g_runtime.pcm_capacity = PCM_CAPTURE_MAX_BYTES;
        g_runtime.pcm_buffer = (rt_uint8_t *)rt_malloc(g_runtime.pcm_capacity);
        if (g_runtime.pcm_buffer == RT_NULL)
        {
            rt_kprintf("[m33] pcm buffer alloc failed size=%lu\n", (unsigned long)g_runtime.pcm_capacity);
            return;
        }
    }

    g_runtime.pcm_mode = PCM_MODE_LISTEN;
    g_runtime.pcm_length = 0;
    if (!audio_capture_is_running())
    {
        if (audio_capture_init() != RT_EOK)
        {
            rt_kprintf("[m33] pcm listen init failed\n");
            g_runtime.pcm_mode = PCM_MODE_IDLE;
            return;
        }

        g_runtime.pcm_capture_active = RT_TRUE;
        ret = audio_capture_start(m33_pcm_capture_callback);
        if ((ret != RT_EOK) && (ret != -RT_EBUSY))
        {
            g_runtime.pcm_capture_active = RT_FALSE;
            g_runtime.pcm_mode = PCM_MODE_IDLE;
            rt_kprintf("[m33] pcm listen start failed ret=%d\n", ret);
            return;
        }

        rt_kprintf("[m33] pcm listen started ret=%d running=%d\n",
                   ret,
                   audio_capture_is_running() ? 1 : 0);
    }
    else
    {
        g_runtime.pcm_capture_active = RT_TRUE;
        rt_kprintf("[m33] pcm listen armed\n");
    }
}

static void m33_stop_pcm_capture(void)
{
    rt_uint32_t captured_len;

    if (!g_runtime.pcm_capture_active && (g_runtime.pcm_length == 0))
    {
        rt_kprintf("[m33] pcm capture not active\n");
        return;
    }

    captured_len = g_runtime.pcm_length;
    g_runtime.pcm_mode = PCM_MODE_IDLE;
    g_runtime.pcm_capture_active = RT_FALSE;
    if (captured_len == 0)
    {
        rt_kprintf("[m33] pcm publish skipped frozen_len=0\n");
        return;
    }

    m33_publish_audio_capture();
    g_runtime.pcm_length = 0;
}

static void m33_stop_pcm_listen(void)
{
    g_runtime.pcm_mode = PCM_MODE_IDLE;
    g_runtime.pcm_capture_active = RT_FALSE;
    g_runtime.pcm_length = 0;
    rt_kprintf("[m33] pcm listen disarmed\n");
}

static void m33qa_pcm_capture_on(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    g_runtime.pcm_mode = PCM_MODE_MANUAL;
    m33_start_pcm_capture();
}
MSH_CMD_EXPORT(m33qa_pcm_capture_on, Record M33 mic PCM for CM55 Xiaozhi QA);

static void m33qa_pcm_capture_off(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    m33_stop_pcm_capture();
}
MSH_CMD_EXPORT(m33qa_pcm_capture_off, Publish recorded M33 mic PCM to CM55);

static void m33qa_pcm_listen_on(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    m33_start_pcm_listen();
}
MSH_CMD_EXPORT(m33qa_pcm_listen_on, Legacy QA: stream M33 mic PCM to CM55);

static void m33qa_pcm_listen_off(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    m33_stop_pcm_listen();
}
MSH_CMD_EXPORT(m33qa_pcm_listen_off, Stop legacy M33 mic PCM stream);

static void m33qa_xz_probe(int argc, char **argv)
{
    const rt_uint32_t frame_len = 1920U;
    const rt_uint32_t default_probe_len = 16000U * 2U * 3U;
    rt_uint32_t target_len = g_xiaozhi_pcm_probe_data_len;
    rt_uint32_t offset = 0U;
    rt_uint32_t part = 0U;

    if ((argc < 2) || (rt_strcmp(argv[1], "full") != 0))
    {
        target_len = (g_xiaozhi_pcm_probe_data_len > default_probe_len) ?
            default_probe_len :
            g_xiaozhi_pcm_probe_data_len;
    }

    rt_kprintf("[m33] xiaozhi probe start len=%lu/%lu mode=%s\n",
               (unsigned long)target_len,
               (unsigned long)g_xiaozhi_pcm_probe_data_len,
               (target_len == g_xiaozhi_pcm_probe_data_len) ? "full" : "short");
    while (offset < target_len)
    {
        rt_uint32_t chunk_len = target_len - offset;
        rt_err_t ret;

        if (chunk_len > frame_len)
        {
            chunk_len = frame_len;
        }

        ret = m33_publish_pcm_shared_buffer(g_xiaozhi_pcm_probe_data + offset, chunk_len);
        rt_kprintf("[m33] xiaozhi probe part=%lu off=%lu len=%lu ret=%d\n",
                   (unsigned long)part,
                   (unsigned long)offset,
                   (unsigned long)chunk_len,
                   ret);
        if (ret != RT_EOK)
        {
            break;
        }

        offset += chunk_len;
        part++;
        rt_thread_mdelay(80);
    }
}
MSH_CMD_EXPORT(m33qa_xz_probe, Publish built-in Xiaozhi PCM probe to CM55; use "full" for long sample);

static void m33_handle_ble_command(void)
{
    app_ble_command_t cmd;

    if (app_ble_service_peek_command(&cmd) != RT_EOK)
    {
        return;
    }

    switch (cmd.type)
    {
    case APP_BLE_CMD_SET_MODE:
        (void)control_set_mode(cmd.mode);
        break;

    case APP_BLE_CMD_MOVE_JOINT:
        (void)control_move_joint(cmd.joint, cmd.target);
        break;

    case APP_BLE_CMD_EMERGENCY_STOP:
        (void)control_set_mode(CONTROL_MODE_PASSIVE);
        break;

    case APP_BLE_CMD_START_STREAM:
    case APP_BLE_CMD_STOP_STREAM:
    case APP_BLE_CMD_HEARTBEAT:
    default:
        break;
    }
}

static void m33_handle_ipc_command(void)
{
    m33_m55_message_t msg;

    while (m33_m55_comm_consume(&msg) == RT_EOK)
    {
        if (msg.type == MSG_TYPE_TTS_AUDIO)
        {
            static rt_uint32_t tts_audio_chunks = 0U;
            static rt_uint32_t tts_audio_bytes = 0U;

            if ((tts_audio_chunks < 3U) || ((tts_audio_chunks % 20U) == 0U) ||
                (msg.payload.audio_data.chunk_len == 0U))
            {
                rt_kprintf("[m33] tts audio rx total=%lu idx=%lu len=%lu\n",
                           (unsigned long)msg.payload.audio_data.total_len,
                           (unsigned long)msg.payload.audio_data.chunk_index,
                           (unsigned long)msg.payload.audio_data.chunk_len);
            }

            if (audio_playback_init() == RT_EOK)
            {
                (void)audio_playback_start();
            }
            if (msg.payload.audio_data.chunk_len == 0U)
            {
                rt_err_t flush_ret = audio_playback_flush();
                rt_kprintf("[m33] tts audio flush chunks=%lu bytes=%lu ret=%d\n",
                           (unsigned long)tts_audio_chunks,
                           (unsigned long)tts_audio_bytes,
                           flush_ret);
                tts_audio_chunks = 0U;
                tts_audio_bytes = 0U;
                if (flush_ret != RT_EOK)
                {
                    rt_kprintf("[m33] tts audio playback flush failed ret=%d\n", flush_ret);
                }
                continue;
            }
            rt_err_t ret = audio_playback_write(msg.payload.audio_data.data,
                                                msg.payload.audio_data.chunk_len);
            if (ret != RT_EOK)
            {
                rt_kprintf("[m33] tts audio playback write failed ret=%d len=%lu\n",
                           ret,
                           (unsigned long)msg.payload.audio_data.chunk_len);
            }
            else
            {
                tts_audio_chunks++;
                tts_audio_bytes += msg.payload.audio_data.chunk_len;
                if ((tts_audio_chunks <= 3U) || ((tts_audio_chunks % 20U) == 0U))
                {
                    rt_kprintf("[m33] tts audio write chunk=%lu len=%lu total=%lu\n",
                               (unsigned long)tts_audio_chunks,
                               (unsigned long)msg.payload.audio_data.chunk_len,
                               (unsigned long)tts_audio_bytes);
                }
            }
            continue;
        }

        if (msg.type != MSG_TYPE_VOICE_CONTROL)
        {
            m55_model_bridge_handle_message(&msg);
            continue;
        }

        switch ((voice_control_cmd_t)msg.payload.voice_control.cmd)
        {
        case VOICE_CTRL_START_CAPTURE:
            rt_kprintf("[m33] ipc start capture ignored: Xiaozhi uplink audio is captured on CM55 mic0\n");
            break;
        case VOICE_CTRL_STOP_CAPTURE:
            rt_kprintf("[m33] ipc stop capture ignored: CM55 owns Xiaozhi uplink audio\n");
            break;
        case VOICE_CTRL_START_LISTEN:
            rt_kprintf("[m33] ipc start listen ignored: CM55 owns wake-word mic0 capture\n");
            break;
        case VOICE_CTRL_STOP_LISTEN:
            rt_kprintf("[m33] ipc stop listen ignored: CM55 owns wake-word mic0 capture\n");
            break;
        case VOICE_CTRL_PUBLISH_TEST_SNAPSHOT:
            rt_kprintf("[m33] ipc publish test snapshot\n");
            (void)m55_model_input_bridge_publish_snapshot(0.42f,
                                                          0.08f,
                                                          76U,
                                                          98U,
                                                          0.0f,
                                                          0.0f,
                                                          0.0f);
            break;
        case VOICE_CTRL_PUBLISH_MOTOR7_SNAPSHOT:
            rt_kprintf("[m33] ipc publish motor7 snapshot\n");
            (void)m55_model_input_bridge_publish_motor7_snapshot();
            break;
        default:
            break;
        }
    }
}

static void m33_publish_ble_telemetry(const sensor_data_t *sensor,
                                      const control_status_t *control,
                                      const safety_monitor_t *safety)
{
    const app_ble_runtime_t *runtime;
    const char *payload;
    uint16_t payload_len;
    uint16_t offset;
    const uint16_t chunk_size = 20;

    (void)app_ble_service_update_telemetry(sensor, control, safety);
    runtime = app_ble_service_get_runtime();
    if ((runtime == RT_NULL) || !runtime->connected || !runtime->streaming_enabled)
    {
        return;
    }

    payload = app_ble_service_get_last_payload();
    if (payload == RT_NULL)
    {
        return;
    }

    payload_len = (uint16_t)rt_strlen(payload);

    for (offset = 0; offset < payload_len; offset += chunk_size)
    {
        uint16_t send_len = (payload_len - offset) > chunk_size ? chunk_size : (payload_len - offset);
        rt_err_t ret = bt_app_gatt_send((const uint8_t *)(payload + offset), send_len);
        if (ret != RT_EOK)
        {
            rt_kprintf("[ble] Send failed at offset %u\n", offset);
            break;
        }

        if (offset + chunk_size < payload_len)
        {
            rt_thread_mdelay(5);
        }
    }
}

static void m33_init_framework(void)
{
    rt_err_t bt_err;

    rt_kprintf("[m33] init step1 m33_m55_comm\n");
    m33_m55_comm_init();
    m55_model_bridge_init();
    m55_qa_bridge_init();
    rt_kprintf("[m33] init step2 bt_board_bridge\n");
    bt_board_bridge_init();
    rt_kprintf("[m33] init step3 app_ble_service_init\n");
    app_ble_service_init();
    rt_kprintf("[m33] init step4 app_ble_service_start\n");
    app_ble_service_start();
    rt_kprintf("[m33] init step5 sensor_manager_init\n");
    sensor_manager_init();
    rt_kprintf("[m33] init step6 input_buffer_init\n");
    input_buffer_init();
    rt_kprintf("[m33] init step7 control_manager_init\n");
    control_manager_init();
    rt_kprintf("[m33] init step8 can_driver_init\n");
    can_driver_init();
    rt_kprintf("[m33] init step9 safety_system_init\n");
    safety_system_init();
    rt_kprintf("[m33] init step10 http_server_init\n");
    http_server_init();
    rt_kprintf("[m33] init step11 http_server_start\n");
    http_server_start();
    rt_kprintf("[m33] init step12 openclaw_integration_init\n");
    openclaw_integration_init();
#if M33_ENABLE_BT_HCI
    rt_kprintf("[m33] init step13 bt_hci_transport_init\n");
    bt_err = bt_hci_transport_init();
    rt_kprintf("[m33] bt_hci_transport_init ret=%d state=%d\n",
               bt_err,
               bt_hci_transport_get_runtime()->state);
    if (bt_err == RT_EOK)
    {
        bt_err = bt_hci_transport_start();
        rt_kprintf("[m33] bt_hci_transport_start ret=%d state=%d\n",
                   bt_err,
                   bt_hci_transport_get_runtime()->state);
    }

    if (bt_err != RT_EOK)
    {
        rt_kprintf("[m33] bluetooth middleware not integrated yet, transport state=%d err=%d\n",
                   bt_hci_transport_get_runtime()->state,
                   bt_err);
    }
#else
    rt_kprintf("[m33] init step13 bt_hci_transport skipped for M55 WiFi bring-up\n");
#endif
}

#ifdef __cplusplus
extern "C" {
#endif
int main(void)
{
    sensor_data_t sensor;
    control_status_t control;

    rt_memset(&g_runtime, 0, sizeof(g_runtime));

    rt_kprintf("Hello RT-Thread\r\n");
    rt_kprintf("This core is cortex-m33\n");
    m33_log_cm55_boot_state("after-board-init");

    rt_pin_mode(LED_PIN_B, PIN_MODE_OUTPUT);
    m33_init_framework();
    rt_thread_mdelay(100);
    m33_log_cm55_boot_state("after-framework-init");
    control_set_mode(CONTROL_MODE_ACTIVE);

    rt_kprintf("[m33] System ready. Waiting for BLE connection...\n");
    rt_kprintf("[m33] Send 'stream:on' to start sensor data streaming\n");

    while (1)
    {
        sensor_fill_demo_data(&sensor, rt_tick_get());
        sensor_update_latest(&sensor);
        control_apply_sensor_feedback(&sensor);
        safety_monitor_update(&g_runtime.safety, &sensor);
        control_get_status(&control);
        m33_handle_ble_command();
        m33_handle_ipc_command();
        m33_publish_ble_telemetry(&sensor, &control, &g_runtime.safety);

        g_runtime.loop_count++;
        if ((g_runtime.loop_count % 10U) == 0U)
        {
            rt_pin_write(LED_PIN_B, PIN_HIGH);
        }
        else
        {
            rt_pin_write(LED_PIN_B, PIN_LOW);
        }
        rt_thread_mdelay(FRAME_PERIOD_MS);
    }

    return 0;
}
#ifdef __cplusplus
}
#endif
