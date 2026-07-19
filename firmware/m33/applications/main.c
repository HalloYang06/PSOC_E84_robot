#include <rtthread.h>
#include <rtdevice.h>
#include <rthw.h>
#include <board.h>
#include <reent.h>
#include <finsh.h>

#include "common/m33_m55_comm.h"
#include "m33/audio_capture.h"
#include "m33/audio_playback.h"
#include "m33/app_ble_service.h"
#include "m33/can_driver.h"
#include "drv_can.h"
#include "m33/control_manager.h"
#include "m33/http_server.h"
#include "m33/input_buffer.h"
#include "m33/m55_qa_bridge.h"
#include "m33/m55_model_bridge.h"
#include "m33/m55_emg_stream_bridge.h"
#include "m33/m55_model_input_bridge.h"
#include "m33/openclaw_integration.h"
#include "m33/safety_system.h"
#include "m33/sensor_manager.h"
#include "m33/voice_rehab_ipc_bridge.h"
#include "m33/xiaozhi_pcm_probe_data.h"
#include "control/control_layer.h"

__attribute__((weak)) struct _reent _impure_data;

#define LED_PIN_B GET_PIN(16, 5)
#define FRAME_PERIOD_MS 100
#define PCM_CAPTURE_MAX_BYTES (16000U * 2U * 2U)
#define M33_TTS_IDLE_FLUSH_MS 500U
#define M33_CM55_STATUS_STALE_RESTART_MS 20000U
#define M33_CM55_RESTART_COOLDOWN_MS 60000U
#define M33_CM55_TX_STUCK_RESTART_MS 8000U
#define M33_CM55_AUTO_RESTART_ENABLE 0
#define M33_IPC_PUMP_PERIOD_MS 5U
#define M33_APP_BLE_STATUS_HEARTBEAT_MS 1000U
#define M33_IPC_PUMP_STACK_SIZE 4096U
#define M33_IPC_INIT_STACK_SIZE 4096U
#define M33_IPC_INIT_DELAY_MS 1000U
#define M33_IPC_INIT_RETRY_MS 2000U
#define M33_ENABLE_LED_HEARTBEAT 1
#define M33_XIAOZHI_MINIMAL_FRAMEWORK 0
#define M33_AUTO_START_EMG_M55_INFERENCE 1
#define M33_AUTO_EMG_SAMPLE_PERIOD_MS 20U
#define M33_AUTO_EMG_MANAGE_F103 1
#define M33_ENABLE_M55_IPC_AUTO_INIT 0
#define M33_ENABLE_NANOPI_HEARTBEAT_BRIDGE 0

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
static rt_bool_t g_tts_audio_active = RT_FALSE;
static rt_tick_t g_tts_audio_last_tick = 0U;
static rt_uint32_t g_tts_audio_chunks = 0U;
static rt_uint32_t g_tts_audio_bytes = 0U;
static rt_tick_t g_cm55_last_auto_restart_tick = 0U;
static rt_tick_t g_cm55_tx_pending_since_tick = 0U;
static rt_tick_t g_cm55_last_watchdog_log_tick = 0U;
static rt_thread_t g_ipc_pump_thread = RT_NULL;
static rt_thread_t g_ipc_init_thread = RT_NULL;
static rt_bool_t g_m55_bridge_started = RT_FALSE;
static rt_bool_t g_app_ble_status_initialized = RT_FALSE;
static rt_bool_t g_app_ble_status_connected = RT_FALSE;
static rt_bool_t g_app_ble_status_dirty = RT_TRUE;
static rt_uint32_t g_app_ble_status_link_seq = 0U;
static rt_tick_t g_app_ble_status_last_publish_tick = 0U;
static sensor_data_t g_main_sensor;
static control_status_t g_main_control;
volatile rt_uint32_t g_m33_boot_marker = 0U;

static void m33_minimal_spin_delay(void)
{
    volatile rt_uint32_t i;

    for (i = 0U; i < 20000U; i++)
    {
        __asm volatile ("nop");
    }
}

static void m33_publish_audio_capture(void);
static rt_err_t m33_publish_pcm_shared_buffer(const rt_uint8_t *pcm, rt_uint32_t len);
static void m33_handle_ipc_command(void);
static void m33_flush_tts_audio_if_idle(void);
static void m33_watchdog_cm55_voice_status(void);

static rt_err_t m33_minimal_send_can_status(rt_uint8_t seq)
{
    struct rt_can_msg msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.id = 0x322U;
    msg.ide = RT_CAN_STDID;
    msg.rtr = RT_CAN_DTR;
    msg.len = 8U;
    msg.hdr_index = -1;
    msg.data[0] = 0xA5U;
    msg.data[1] = seq;
    msg.data[2] = 7U;
    return ifx_can_direct_send(&msg);
}

static void m33_minimal_poll_can_bridge(void)
{
    struct rt_can_msg msg;
    rt_uint8_t drained = 0U;

    while ((drained < 8U) && (ifx_can_direct_recv(&msg) == (rt_ssize_t)sizeof(msg)))
    {
        drained++;
        if ((msg.ide == RT_CAN_STDID) && (msg.id == 0x321U))
        {
            (void)m33_minimal_send_can_status((msg.len > 0U) ? msg.data[0] : 0U);
        }
    }
}

static void m33_minimal_heartbeat_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
        m33_minimal_poll_can_bridge();
        rt_thread_mdelay(5);
    }
}

static void m33_minimal_start_heartbeat_bridge(void)
{
    rt_thread_t thread;

    thread = rt_thread_create("np_hb",
                              m33_minimal_heartbeat_entry,
                              RT_NULL,
                              2048,
                              8,
                              10);
    if (thread != RT_NULL)
    {
        rt_thread_startup(thread);
    }
}

static void m33_log_cm55_boot_state(const char *tag)
{
    rt_kprintf("[m33] cm55 %s boot_addr=0x%08lx register-probe=skipped\n",
               tag,
               (unsigned long)CY_CM55_APP_BOOT_ADDR);
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
    const rt_uint32_t frame_delay_ms = 100U;
    const rt_uint32_t retry_delay_ms = 150U;
    const rt_uint32_t max_retries = 4U;
    const rt_uint32_t drain_wait_ms = 3000U;
    const rt_uint32_t default_probe_len = 16000U * 2U * 12U / 10U;
    rt_uint32_t target_len = g_xiaozhi_pcm_probe_data_len;
    rt_uint32_t offset = 0U;
    rt_uint32_t part = 0U;
    rt_uint32_t retry_total = 0U;
    voice_status_msg_t voice_status;
    rt_uint32_t voice_status_seq;
    rt_tick_t voice_status_timestamp;
    rt_tick_t drain_deadline = rt_tick_get() + rt_tick_from_millisecond((rt_int32_t)drain_wait_ms);
    rt_tick_t status_deadline;

    while ((m33_m55_comm_tx_count() > 0U) &&
           ((rt_int32_t)(drain_deadline - rt_tick_get()) > 0))
    {
        rt_kprintf("[m33] xiaozhi probe wait drain tx_pending=%lu\n",
                   (unsigned long)m33_m55_comm_tx_count());
        rt_thread_mdelay(100);
    }

    if (m33_m55_comm_tx_count() > 0U)
    {
        rt_kprintf("[m33] xiaozhi probe abort: tx_pending=%lu after %lums drain wait\n",
                   (unsigned long)m33_m55_comm_tx_count(),
                   (unsigned long)drain_wait_ms);
        return;
    }

    rt_memset(&voice_status, 0, sizeof(voice_status));
    status_deadline = rt_tick_get() + rt_tick_from_millisecond(1500);
    do
    {
        rt_memset(&voice_status, 0, sizeof(voice_status));
        if (m55_model_bridge_get_voice_status(&voice_status, &voice_status_seq, &voice_status_timestamp) &&
            ((voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_LISTENING) != 0U))
        {
            break;
        }
        rt_thread_mdelay(50);
    } while ((rt_int32_t)(status_deadline - rt_tick_get()) > 0);

    if ((voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_LISTENING) == 0U)
    {
        rt_kprintf("[m33] xiaozhi probe abort: M55 not listening seq=%lu flags=0x%lx age_ticks=%lu xz_ws=%d tx_pending=%lu\n",
                   (unsigned long)voice_status_seq,
                   (unsigned long)voice_status.flags,
                   (unsigned long)(rt_tick_get() - voice_status_timestamp),
                   (voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_CONNECTED) ? 1 : 0,
                   (unsigned long)m33_m55_comm_tx_count());
        return;
    }

    if (argc >= 2 && rt_strcmp(argv[1], "full") != 0)
    {
        long ms = strtol(argv[1], RT_NULL, 10);
        if (ms > 0)
        {
            rt_uint32_t requested = (rt_uint32_t)ms * 16000U * 2U / 1000U;
            target_len = (requested < g_xiaozhi_pcm_probe_data_len) ?
                requested :
                g_xiaozhi_pcm_probe_data_len;
        }
    }
    else if ((argc < 2) || (rt_strcmp(argv[1], "full") != 0))
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
        rt_uint32_t retry = 0U;

        if (chunk_len > frame_len)
        {
            chunk_len = frame_len;
        }

        do
        {
            ret = m33_publish_pcm_shared_buffer(g_xiaozhi_pcm_probe_data + offset, chunk_len);
            if (ret == RT_EOK)
            {
                break;
            }

            if ((ret != -RT_EFULL) && (ret != -RT_ETIMEOUT) && (ret != -RT_ENOSPC))
            {
                break;
            }

            retry++;
            retry_total++;
            rt_kprintf("[m33] xiaozhi probe backoff part=%lu retry=%lu ret=%d tx_pending=%lu delay=%lums\n",
                       (unsigned long)part,
                       (unsigned long)retry,
                       ret,
                       (unsigned long)m33_m55_comm_tx_count(),
                       (unsigned long)retry_delay_ms);
            rt_thread_mdelay(retry_delay_ms);
        } while (retry < max_retries);

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
        rt_thread_mdelay(frame_delay_ms);
    }

    rt_kprintf("[m33] xiaozhi probe done parts=%lu sent=%lu/%lu retries=%lu tx_pending=%lu\n",
               (unsigned long)part,
               (unsigned long)offset,
               (unsigned long)target_len,
               (unsigned long)retry_total,
               (unsigned long)m33_m55_comm_tx_count());
}
MSH_CMD_EXPORT(m33qa_xz_probe, Publish built-in Xiaozhi PCM probe to CM55; use "full" for long sample);

static void m33_handle_ipc_command(void)
{
    m33_m55_message_t msg;

    while (m33_m55_comm_consume(&msg) == RT_EOK)
    {
        if (msg.type == MSG_TYPE_REHAB_MODE_REQUEST)
        {
            (void)voice_rehab_ipc_bridge_submit(&msg.payload.rehab_mode_request);
            continue;
        }

        if (msg.type == MSG_TYPE_TTS_AUDIO)
        {
            if ((g_tts_audio_chunks < 3U) || ((g_tts_audio_chunks % 20U) == 0U) ||
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
                           (unsigned long)g_tts_audio_chunks,
                           (unsigned long)g_tts_audio_bytes,
                           flush_ret);
                g_tts_audio_active = RT_FALSE;
                g_tts_audio_chunks = 0U;
                g_tts_audio_bytes = 0U;
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
                g_tts_audio_active = RT_TRUE;
                g_tts_audio_last_tick = rt_tick_get();
                g_tts_audio_chunks++;
                g_tts_audio_bytes += msg.payload.audio_data.chunk_len;
                if ((g_tts_audio_chunks <= 3U) || ((g_tts_audio_chunks % 20U) == 0U))
                {
                    rt_kprintf("[m33] tts audio write chunk=%lu len=%lu total=%lu\n",
                               (unsigned long)g_tts_audio_chunks,
                               (unsigned long)msg.payload.audio_data.chunk_len,
                               (unsigned long)g_tts_audio_bytes);
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

static void m33_flush_tts_audio_if_idle(void)
{
    rt_tick_t idle_ticks;
    rt_err_t flush_ret;

    if (!g_tts_audio_active)
    {
        return;
    }

    idle_ticks = rt_tick_from_millisecond(M33_TTS_IDLE_FLUSH_MS);
    if ((rt_int32_t)((g_tts_audio_last_tick + idle_ticks) - rt_tick_get()) > 0)
    {
        return;
    }

    flush_ret = audio_playback_flush();
    rt_kprintf("[m33] tts audio idle flush chunks=%lu bytes=%lu ret=%d\n",
               (unsigned long)g_tts_audio_chunks,
               (unsigned long)g_tts_audio_bytes,
               flush_ret);
    g_tts_audio_active = RT_FALSE;
    g_tts_audio_chunks = 0U;
    g_tts_audio_bytes = 0U;
}

static void m33_watchdog_cm55_voice_status(void)
{
    voice_status_msg_t voice_status;
    rt_uint32_t voice_status_seq;
    rt_tick_t voice_status_timestamp;
    rt_tick_t now;
    rt_uint32_t age_ms;
    rt_uint32_t cooldown_ms;
    rt_uint32_t tx_pending;

    if (!m55_model_bridge_get_voice_status(&voice_status,
                                           &voice_status_seq,
                                           &voice_status_timestamp))
    {
        return;
    }

    now = rt_tick_get();
    age_ms = (rt_uint32_t)((now - voice_status_timestamp) * 1000U / RT_TICK_PER_SECOND);
    cooldown_ms = (g_cm55_last_auto_restart_tick == 0U) ?
        M33_CM55_RESTART_COOLDOWN_MS :
        (rt_uint32_t)((now - g_cm55_last_auto_restart_tick) * 1000U / RT_TICK_PER_SECOND);
    tx_pending = m33_m55_comm_tx_count();

    if (tx_pending == 0U)
    {
        g_cm55_tx_pending_since_tick = 0U;
    }
    else if ((voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_CONNECTED) == 0U)
    {
        rt_uint32_t pending_ms;

        if (g_cm55_tx_pending_since_tick == 0U)
        {
            g_cm55_tx_pending_since_tick = now;
        }
        pending_ms = (rt_uint32_t)((now - g_cm55_tx_pending_since_tick) * 1000U / RT_TICK_PER_SECOND);
        if ((pending_ms >= M33_CM55_TX_STUCK_RESTART_MS) &&
            (cooldown_ms >= M33_CM55_RESTART_COOLDOWN_MS))
        {
            rt_kprintf("[m33] cm55 tx stuck pending=%lu ms=%lu flags=0x%lx stage=%ld errno=%ld auto_restart=%u\n",
                       (unsigned long)tx_pending,
                       (unsigned long)pending_ms,
                       (unsigned long)voice_status.flags,
                       (long)voice_status.xiaozhi_ws_stage,
                       (long)voice_status.xiaozhi_ws_errno,
                       (unsigned)M33_CM55_AUTO_RESTART_ENABLE);
#if M33_CM55_AUTO_RESTART_ENABLE
            Cy_SysResetCM55(MXCM55, 10);
            Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
            g_cm55_last_auto_restart_tick = now;
            g_cm55_tx_pending_since_tick = 0U;
#endif
            return;
        }
    }

    if ((age_ms < M33_CM55_STATUS_STALE_RESTART_MS) ||
        (cooldown_ms < M33_CM55_RESTART_COOLDOWN_MS))
    {
        return;
    }

    if (tx_pending == 0U)
    {
        return;
    }

    if ((g_cm55_last_watchdog_log_tick != 0U) &&
        ((rt_uint32_t)(now - g_cm55_last_watchdog_log_tick) < (RT_TICK_PER_SECOND * 5U)))
    {
        return;
    }
    g_cm55_last_watchdog_log_tick = now;

    rt_kprintf("[m33] cm55 voice status stale age=%lu seq=%lu tx_pending=%lu flags=0x%lx stage=%ld errno=%ld auto_restart=%u\n",
               (unsigned long)age_ms,
               (unsigned long)voice_status_seq,
               (unsigned long)tx_pending,
               (unsigned long)voice_status.flags,
               (long)voice_status.xiaozhi_ws_stage,
               (long)voice_status.xiaozhi_ws_errno,
               (unsigned)M33_CM55_AUTO_RESTART_ENABLE);
#if M33_CM55_AUTO_RESTART_ENABLE
    Cy_SysResetCM55(MXCM55, 10);
    Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
    g_cm55_last_auto_restart_tick = now;
#endif
}

static void m33_publish_app_ble_status(void)
{
    app_ble_runtime_t runtime;
    m33_m55_message_t msg;
    rt_tick_t now;
    rt_uint32_t elapsed_ms;

    if (app_ble_service_get_runtime_snapshot(&runtime) != RT_EOK)
    {
        return;
    }

    now = rt_tick_get();
    if (!g_app_ble_status_initialized ||
        (runtime.connected != g_app_ble_status_connected))
    {
        g_app_ble_status_initialized = RT_TRUE;
        g_app_ble_status_connected = runtime.connected;
        g_app_ble_status_link_seq++;
        g_app_ble_status_dirty = RT_TRUE;
    }

    elapsed_ms = (rt_uint32_t)((now - g_app_ble_status_last_publish_tick) *
                               1000U / RT_TICK_PER_SECOND);
    if (!g_app_ble_status_dirty &&
        (elapsed_ms < M33_APP_BLE_STATUS_HEARTBEAT_MS))
    {
        return;
    }

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_APP_BLE_STATUS;
    msg.seq = g_app_ble_status_link_seq;
    msg.payload.app_ble_status.version = APP_BLE_STATUS_PROTOCOL_VERSION;
    msg.payload.app_ble_status.connected = runtime.connected ? 1U : 0U;
    msg.payload.app_ble_status.link_seq = g_app_ble_status_link_seq;

    if (m33_m55_comm_try_publish(&msg) == RT_EOK)
    {
        g_app_ble_status_dirty = RT_FALSE;
        g_app_ble_status_last_publish_tick = now;
    }
}

static void m33_ipc_pump_entry(void *parameter)
{
    RT_UNUSED(parameter);

    rt_kprintf("[m33] ipc pump thread started period=%ums\n",
               (unsigned)M33_IPC_PUMP_PERIOD_MS);
    while (1)
    {
        if (m33_m55_comm_is_ready())
        {
            m33_handle_ipc_command();
            m33_flush_tts_audio_if_idle();
            m33_watchdog_cm55_voice_status();
            m33_publish_app_ble_status();
        }
        rt_thread_mdelay(M33_IPC_PUMP_PERIOD_MS);
    }
}

static void m33_start_ipc_pump(void)
{
    rt_err_t ret;

    if (g_ipc_pump_thread != RT_NULL)
    {
        return;
    }

    ret = voice_rehab_ipc_bridge_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("[m33] WARN: failed to start voice rehab bridge ret=%d\n", ret);
        return;
    }

    g_ipc_pump_thread = rt_thread_create("m55_ipc",
                                         m33_ipc_pump_entry,
                                         RT_NULL,
                                         M33_IPC_PUMP_STACK_SIZE,
                                         12,
                                         10);
    if (g_ipc_pump_thread == RT_NULL)
    {
        rt_kprintf("[m33] WARN: failed to start ipc pump thread\n");
        return;
    }

    rt_thread_startup(g_ipc_pump_thread);
}

static void m33_start_m55_bridges_once(void)
{
#if M33_AUTO_START_EMG_M55_INFERENCE
    rt_err_t emg_ret;
#endif

    if (g_m55_bridge_started)
    {
        return;
    }

    m55_model_bridge_init();
    m55_qa_bridge_init();
    m33_start_ipc_pump();
#if M33_AUTO_START_EMG_M55_INFERENCE
    emg_ret = m55_emg_stream_bridge_start((rt_uint16_t)M33_AUTO_EMG_SAMPLE_PERIOD_MS,
                                          M33_AUTO_EMG_MANAGE_F103 ? RT_TRUE : RT_FALSE);
    rt_kprintf("[m33] auto EMG->M55 stream ret=%d period=%u manage_f103=%u\n",
               emg_ret,
               (unsigned)M33_AUTO_EMG_SAMPLE_PERIOD_MS,
               (unsigned)M33_AUTO_EMG_MANAGE_F103);
#endif
    g_m55_bridge_started = RT_TRUE;
}

static int cmd_m55_ipc_start(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (!m33_m55_comm_is_ready())
    {
        rt_err_t ret = m33_m55_comm_init();
        if (ret != RT_EOK)
        {
            rt_kprintf("[m33] m55_ipc_start init ret=%d\n", ret);
            return ret;
        }
    }

    if (!g_m55_bridge_started)
    {
        m55_model_bridge_init();
        m55_qa_bridge_init();
        g_m55_bridge_started = RT_TRUE;
    }
    m33_start_ipc_pump();
    rt_kprintf("[m33] m55_ipc_start ready=%d\n", m33_m55_comm_is_ready() ? 1 : 0);
    return RT_EOK;
}
MSH_CMD_EXPORT(cmd_m55_ipc_start, start CM55 IPC response pump without auto EMG stream);

static void m33_ipc_init_entry(void *parameter)
{
    rt_err_t ret;

    RT_UNUSED(parameter);

    rt_thread_mdelay(M33_IPC_INIT_DELAY_MS);
    rt_kprintf("[m33] async M55 IPC init thread started\n");

    while (!m33_m55_comm_is_ready())
    {
        ret = m33_m55_comm_init();
        if (ret == RT_EOK)
        {
            rt_kprintf("[m33] async M55 IPC ready\n");
            break;
        }

        rt_kprintf("[m33] async M55 IPC init failed ret=%d; retry in %ums\n",
                   ret,
                   (unsigned)M33_IPC_INIT_RETRY_MS);
        rt_thread_mdelay(M33_IPC_INIT_RETRY_MS);
    }

    m33_start_m55_bridges_once();
}

static void m33_start_ipc_init_async(void)
{
    if (g_ipc_init_thread != RT_NULL)
    {
        return;
    }

    g_ipc_init_thread = rt_thread_create("m55_init",
                                         m33_ipc_init_entry,
                                         RT_NULL,
                                         M33_IPC_INIT_STACK_SIZE,
                                         18,
                                         10);
    if (g_ipc_init_thread == RT_NULL)
    {
        rt_kprintf("[m33] WARN: failed to start M55 IPC init thread\n");
        return;
    }

    rt_thread_startup(g_ipc_init_thread);
}

static void m33_init_framework(void)
{
    rt_err_t can_ret;

    g_m33_boot_marker = 0x33010001U;
#if M33_ENABLE_M55_IPC_AUTO_INIT
    m33_start_ipc_init_async();
#endif
    g_m33_boot_marker = 0x33010002U;
#if M33_XIAOZHI_MINIMAL_FRAMEWORK
    g_m33_boot_marker = 0x33020001U;
    can_ret = can_driver_init();
    g_m33_boot_marker = 0x33020002U;
    if (can_ret == RT_EOK)
    {
        rt_err_t sensor_ret;
        rt_err_t first_tx_ret;

        g_m33_boot_marker = 0x33030001U;
        sensor_ret = control_sensor_report_enable(RT_TRUE,
                                                  (rt_uint16_t)M33_AUTO_EMG_SAMPLE_PERIOD_MS);
        RT_UNUSED(sensor_ret);
        g_m33_boot_marker = 0x33030002U;

        first_tx_ret = m33_minimal_send_can_status(0U);
        RT_UNUSED(first_tx_ret);
        g_m33_boot_marker = 0x33030003U;
#if M33_ENABLE_NANOPI_HEARTBEAT_BRIDGE
        m33_minimal_start_heartbeat_bridge();
#endif
        g_m33_boot_marker = 0x33030004U;
    }
    RT_UNUSED(can_ret);
    g_m33_boot_marker = 0x3302FFFFU;
    return;
#endif
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
}

#ifdef __cplusplus
extern "C" {
#endif
int main(void)
{
    rt_memset(&g_runtime, 0, sizeof(g_runtime));

#if M33_ENABLE_LED_HEARTBEAT
    rt_pin_mode(LED_PIN_B, PIN_MODE_OUTPUT);
    rt_pin_write(LED_PIN_B, PIN_HIGH);
#endif
    m33_init_framework();
#if M33_XIAOZHI_MINIMAL_FRAMEWORK
    while (1)
    {
        m33_minimal_poll_can_bridge();
        g_runtime.loop_count++;
#if M33_ENABLE_LED_HEARTBEAT
        rt_pin_write(LED_PIN_B, ((g_runtime.loop_count % 10U) == 0U) ? PIN_HIGH : PIN_LOW);
#endif
        m33_minimal_spin_delay();
    }
#endif
    rt_kprintf("[m33] framework ok\n");
    rt_thread_mdelay(100);
    control_set_mode(CONTROL_MODE_ACTIVE);

    rt_kprintf("[m33] System ready. CAN control path active.\n");

    while (1)
    {
        sensor_fill_demo_data(&g_main_sensor, rt_tick_get());
        sensor_update_latest(&g_main_sensor);
        control_apply_sensor_feedback(&g_main_sensor);
        safety_monitor_update(&g_runtime.safety, &g_main_sensor);
        control_get_status(&g_main_control);
        g_runtime.loop_count++;
#if M33_ENABLE_LED_HEARTBEAT
        if ((g_runtime.loop_count % 10U) == 0U)
        {
            rt_pin_write(LED_PIN_B, PIN_HIGH);
        }
        else
        {
            rt_pin_write(LED_PIN_B, PIN_LOW);
        }
#endif
        rt_thread_mdelay(FRAME_PERIOD_MS);
    }

    return 0;
}
#ifdef __cplusplus
}
#endif
