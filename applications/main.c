#include <rtthread.h>
#include <rtdevice.h>
#include <board.h>
#include <fal.h>
#include <finsh.h>
#include <reent.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/time.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include "cy_retarget_io.h"
#include "whd.h"
#include "whd_resource_api.h"
#include "http_server.h"
#include "m33_m55_comm.h"
#include "model_result_publisher.h"
#include "openclaw_integration.h"
#include "voice_service.h"
#include "websocket_client.h"
#include "wifi_config_service.h"
#include "xiaozhi_wake_engine.h"
#include "xiaozhi_voice_relay.h"
#include "drv_pdm.h"

#ifdef BSP_USING_LVGL
extern int lvgl_thread_init(void);
#endif

#define LED_PIN_G GET_PIN(16, 6)
#define M55_AUDIO_SAMPLE_RATE 16000
#define M55_AUDIO_BITS_PER_SAMPLE 16
#define M55_AUDIO_FRAME_BYTES 2048
#define M55_MIC_THREAD_STACK 16384
#define M55_VOICE_BOOT_THREAD_STACK 12288
#define M55_XIAOZHI_AUTO_THREAD_STACK 8192
#define M55_VOICE_BOOT_DELAY_MS 5000
#define M55_BOOT_SELF_TEST_RETRY_COUNT 10
#define M55_XIAOZHI_CLOUD_IP "106.55.62.122"
#define M55_XIAOZHI_CLOUD_PORT 8011
#ifndef M55_WIFI_SCAN_QA_ONLY
#define M55_WIFI_SCAN_QA_ONLY 0
#endif
#ifndef M55_WIFI_LVGL_ONLY
#define M55_WIFI_LVGL_ONLY 1
#endif
#ifndef M55_XIAOZHI_AUTO_ENABLE
#define M55_XIAOZHI_AUTO_ENABLE 1
#endif
#ifndef M55_WIFI_AUTO_CONNECT_ON_BOOT
#define M55_WIFI_AUTO_CONNECT_ON_BOOT 1
#endif
#ifndef M55_ENABLE_LOCAL_HTTP_SERVER
#define M55_ENABLE_LOCAL_HTTP_SERVER 0
#endif
#ifndef M55_XIAOZHI_PDM_GAIN
#define M55_XIAOZHI_PDM_GAIN 32
#endif
#ifndef M55_XIAOZHI_AUTO_RETRY_DELAY_LOOPS
#define M55_XIAOZHI_AUTO_RETRY_DELAY_LOOPS 5U
#endif
#define M55_ENABLE_LED_HEARTBEAT 1
#ifndef M55_DETACH_CONSOLE_FOR_M33_QA
#define M55_DETACH_CONSOLE_FOR_M33_QA 0
#endif
#ifdef ENABLE_STEREO_INPUT_FEED
#define M55_AUDIO_CHANNELS 2
#define M55_AUDIO_MONO_FRAME_BYTES (M55_AUDIO_FRAME_BYTES / 2)
#else
#define M55_AUDIO_CHANNELS 1
#define M55_AUDIO_MONO_FRAME_BYTES M55_AUDIO_FRAME_BYTES
#endif

__attribute__((weak)) struct _reent _impure_data;

static struct
{
    rt_device_t dev;
    rt_thread_t thread;
    rt_bool_t running;
    volatile rt_uint32_t frame_count;
    volatile rt_tick_t last_frame_tick;
    rt_uint8_t buffer[M55_AUDIO_FRAME_BYTES];
    rt_uint8_t mono_buffer[M55_AUDIO_MONO_FRAME_BYTES];
} g_m55_mic = {0};
static rt_thread_t g_voice_boot_thread = RT_NULL;
static rt_thread_t g_boot_self_test_thread = RT_NULL;
static rt_thread_t g_xiaozhi_auto_thread = RT_NULL;
static rt_thread_t g_xiaozhi_bridge_thread = RT_NULL;
static rt_thread_t g_wifi_status_thread = RT_NULL;
static rt_bool_t g_xiaozhi_voice_started = RT_FALSE;
static volatile rt_bool_t g_xiaozhi_capture_start_pending;

typedef struct
{
    rt_uint32_t magic;
    rt_uint32_t phase;
    rt_int32_t init_ret;
    rt_int32_t whd_diag_ret_before;
    rt_int32_t scan_start_ret;
    rt_int32_t whd_diag_ret_after;
    rt_uint32_t wait_loops;
    wifi_config_snapshot_t snapshot;
    wifi_config_ap_t aps[WIFI_CONFIG_SCAN_MAX_APS];
} m55_wifi_scan_qa_t;

volatile m55_wifi_scan_qa_t g_m55_wifi_scan_qa;

extern whd_resource_source_t resource_ops;
int lwip_socket(int domain, int type, int protocol);
int lwip_connect(int s, const struct sockaddr *name, socklen_t namelen);
int lwip_close(int s);
int closesocket(int s);
static rt_err_t m55_voice_start_for_xiaozhi(void);
static rt_err_t m55_wake_listen_start_for_xiaozhi(void);
static rt_err_t m55_wake_listen_stop_for_xiaozhi(void);
rt_err_t m55_xiaozhi_talk_start_from_ui(void);
rt_err_t m55_xiaozhi_talk_stop_from_ui(void);
static void m55_dump_thread_stack(const char *tag, const char *name);
static void m55_dump_thread_stacks(const char *tag);
static void xiaozhi_bridge_publish_status(void);
static void wifi_status_publish_kick(void);

static volatile rt_uint32_t g_xz_bridge_loops;
static volatile rt_uint32_t g_xz_bridge_consumed;
static volatile rt_int32_t g_xz_bridge_last_consume_ret;
static volatile rt_uint32_t g_xz_bridge_last_msg_type;
static volatile rt_int32_t g_xz_bridge_phase;
static rt_thread_t g_xz_reconnect_thread = RT_NULL;
static volatile rt_uint32_t g_xz_reconnect_step;
static volatile rt_int32_t g_xz_reconnect_result;
static volatile rt_int32_t g_tcp_probe_stage;
static volatile rt_int32_t g_tcp_probe_errno;
static volatile rt_int32_t g_tcp_probe_result;
static volatile rt_int32_t g_tcp_probe_so_error;
static volatile rt_int32_t g_tcp_probe_select_ret;
static volatile rt_int32_t g_tcp_probe_fcntl_ret;

static void m55_dump_thread_stack(const char *tag, const char *name)
{
    rt_thread_t thread = rt_thread_find((char *)name);

    if (thread == RT_NULL)
    {
        rt_kprintf("[m55_stack] %s %s missing\n", tag, name);
        return;
    }

    rt_kprintf("[m55_stack] %s %s sp=%p stack=%p size=%lu err=%d stat=%u\n",
               tag,
               name,
               thread->sp,
               thread->stack_addr,
               (unsigned long)thread->stack_size,
               (int)thread->error,
               (unsigned)thread->stat);
}

static void m55_dump_thread_stacks(const char *tag)
{
    m55_dump_thread_stack(tag, "LVGL");
    m55_dump_thread_stack(tag, "voice_bt");
    m55_dump_thread_stack(tag, "xz_auto");
    m55_dump_thread_stack(tag, "xz_bridge");
    m55_dump_thread_stack(tag, "voice_svc");
    m55_dump_thread_stack(tag, "voice_det");
    m55_dump_thread_stack(tag, "voice_tts");
    m55_dump_thread_stack(tag, "xz_ui");
    m55_dump_thread_stack(tag, "m55_mic");
}

static void m55_wifi_scan_qa_capture(void)
{
    rt_int32_t i;
    wifi_config_snapshot_t snapshot;

    wifi_config_get_snapshot(&snapshot);
    g_m55_wifi_scan_qa.snapshot = snapshot;

    for (i = 0; i < WIFI_CONFIG_SCAN_MAX_APS; i++)
    {
        wifi_config_ap_t ap;

        rt_memset(&ap, 0, sizeof(ap));
        if ((i < snapshot.scan_count) && (wifi_config_get_scan_ap(i, &ap) == RT_EOK))
        {
            g_m55_wifi_scan_qa.aps[i] = ap;
        }
        else
        {
            rt_memset((void *)&g_m55_wifi_scan_qa.aps[i], 0, sizeof(g_m55_wifi_scan_qa.aps[i]));
        }
    }
}

static void m55_wifi_scan_qa_thread_entry(void *parameter)
{
    rt_uint32_t i;
    wifi_config_snapshot_t snapshot;

    RT_UNUSED(parameter);

    rt_memset((void *)&g_m55_wifi_scan_qa, 0, sizeof(g_m55_wifi_scan_qa));
    g_m55_wifi_scan_qa.magic = 0x57465141U; /* WFQA */
    g_m55_wifi_scan_qa.phase = 1U;

    g_m55_wifi_scan_qa.init_ret = wifi_config_service_init();
    g_m55_wifi_scan_qa.phase = 2U;
    for (i = 0; i < 45U; i++)
    {
        rt_thread_mdelay(1000);
        g_m55_wifi_scan_qa.whd_diag_ret_before = wifi_config_whd_diag();
        m55_wifi_scan_qa_capture();
        wifi_config_get_snapshot(&snapshot);
        if ((snapshot.whd_stage >= 19) && (snapshot.netdev_name[0] != '\0'))
        {
            break;
        }
    }
    g_m55_wifi_scan_qa.phase = 3U;

    g_m55_wifi_scan_qa.scan_start_ret = wifi_config_scan();
    for (i = 0; i < 30U; i++)
    {
        rt_thread_mdelay(1000);
        g_m55_wifi_scan_qa.wait_loops = i + 1U;
        m55_wifi_scan_qa_capture();
        if (g_m55_wifi_scan_qa.snapshot.scan_running == 0U &&
            g_m55_wifi_scan_qa.snapshot.scan_request_count > 0U)
        {
            break;
        }
    }

    g_m55_wifi_scan_qa.whd_diag_ret_after = wifi_config_whd_diag();
    m55_wifi_scan_qa_capture();
    g_m55_wifi_scan_qa.phase = 4U;

    rt_kprintf("[wifi_qa] done init=%ld whd_before=%ld scan_start=%ld scan_result=%ld count=%ld cb=%lu done=%lu timeout=%lu whd_after=%ld\n",
               (long)g_m55_wifi_scan_qa.init_ret,
               (long)g_m55_wifi_scan_qa.whd_diag_ret_before,
               (long)g_m55_wifi_scan_qa.scan_start_ret,
               (long)g_m55_wifi_scan_qa.snapshot.scan_result,
               (long)g_m55_wifi_scan_qa.snapshot.scan_count,
               (unsigned long)g_m55_wifi_scan_qa.snapshot.scan_callback_count,
               (unsigned long)g_m55_wifi_scan_qa.snapshot.scan_done_count,
               (unsigned long)g_m55_wifi_scan_qa.snapshot.scan_timeout_count,
               (long)g_m55_wifi_scan_qa.whd_diag_ret_after);
}

static void m55_console_detach(void)
{
    rt_console_set_device("");
}

static void dump_hex(const char *title, const rt_uint8_t *raw, rt_size_t size)
{
    rt_size_t i;

    rt_kprintf("%s\n", title);
    for (i = 0; i < size; i++)
    {
        rt_kprintf("%02x ", raw[i]);
        if ((i % 16) == 15)
        {
            rt_kprintf("\n");
        }
    }
    if ((size % 16) != 0)
    {
        rt_kprintf("\n");
    }
}

static void whd_dump_head(int argc, char **argv)
{
    const struct fal_partition *part;
    rt_uint8_t raw[32] = {0};

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    part = fal_partition_find("whd_firmware");
    if (!part)
    {
        rt_kprintf("whd_firmware partition not found\n");
        return;
    }

    if (fal_partition_read(part, 0, raw, sizeof(raw)) < 0)
    {
        rt_kprintf("read whd_firmware failed\n");
        return;
    }

    dump_hex("whd_firmware head:", raw, sizeof(raw));
}
MSH_CMD_EXPORT(whd_dump_head, Dump first 32 bytes of whd_firmware partition);

static void whd_dump_block0(int argc, char **argv)
{
    const rt_uint8_t *data = RT_NULL;
    rt_uint8_t copy[32] = {0};
    uint32_t size_out = 0;
    uint32_t result;
    uint32_t fw_size = 0;
    rt_size_t dump_size;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    result = resource_ops.whd_resource_size(RT_NULL, WHD_RESOURCE_WLAN_FIRMWARE, &fw_size);
    rt_kprintf("whd_resource_size result=%u size=%u\n", result, fw_size);
    if (result != 0)
    {
        return;
    }

    result = resource_ops.whd_get_resource_block(RT_NULL, WHD_RESOURCE_WLAN_FIRMWARE, 0, &data, &size_out);
    rt_kprintf("whd_get_resource_block result=%u block0_size=%u data=%p\n", result, size_out, data);
    if (result != 0 || data == RT_NULL)
    {
        return;
    }

    dump_size = size_out < sizeof(copy) ? size_out : sizeof(copy);
    rt_memcpy(copy, data, dump_size);
    dump_hex("whd firmware block0:", copy, dump_size);
}
MSH_CMD_EXPORT(whd_dump_block0, Dump first 32 bytes of WHD firmware block0);

static void openclaw_dump_status(int argc, char **argv)
{
    char json[OPENCLAW_JSON_MEDIUM];

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    openclaw_build_status_json(json, sizeof(json));
    rt_kprintf("%s\n", json);
}
MSH_CMD_EXPORT(openclaw_dump_status, Dump OpenClaw bridge status as JSON);

static void m55_mic_thread_entry(void *parameter)
{
    rt_size_t read_len;
    rt_uint32_t frame_count = 0;
    rt_uint32_t peak = 0;

    RT_UNUSED(parameter);

    while (g_m55_mic.running)
    {
        read_len = rt_device_read(g_m55_mic.dev, 0, g_m55_mic.buffer, sizeof(g_m55_mic.buffer));
        if (read_len > 0)
        {
            rt_size_t i;
            rt_uint32_t local_peak = 0;
            rt_int16_t *samples = (rt_int16_t *)g_m55_mic.buffer;
            rt_size_t sample_count = read_len / sizeof(rt_int16_t);

            for (i = 0; i < sample_count; i++)
            {
                rt_uint32_t mag = (samples[i] < 0) ? (rt_uint32_t)(-samples[i]) : (rt_uint32_t)samples[i];
                if (mag > local_peak)
                {
                    local_peak = mag;
                }
            }

            if (local_peak > peak)
            {
                peak = local_peak;
            }

            frame_count++;
            g_m55_mic.frame_count++;
            g_m55_mic.last_frame_tick = rt_tick_get();
            if ((frame_count % 10U) == 0U)
            {
                rt_kprintf("[m55_mic] read ok len=%u peak=%u frames=%u\n",
                           (unsigned)read_len,
                           (unsigned)peak,
                           (unsigned)frame_count);
                peak = 0;
            }

#ifdef ENABLE_STEREO_INPUT_FEED
            {
                rt_int16_t *mono_samples = (rt_int16_t *)g_m55_mic.mono_buffer;
                rt_size_t mono_count = sample_count / 2U;

                for (i = 0; i < mono_count; i++)
                {
                    rt_int32_t left = samples[i * 2U];
                    rt_int32_t right = samples[(i * 2U) + 1U];

                    mono_samples[i] = (rt_int16_t)((left + right) / 2);
                }
                (void)voice_service_submit_local_pcm(g_m55_mic.mono_buffer,
                                                     (rt_uint32_t)(mono_count * sizeof(rt_int16_t)));
            }
#else
            (void)voice_service_submit_local_pcm(g_m55_mic.buffer, (rt_uint32_t)read_len);
#endif
        }
        else
        {
            rt_thread_mdelay(10);
        }
    }
}

static rt_err_t m55_mic_start_internal(void)
{
    struct rt_audio_caps caps;

    if (g_m55_mic.running)
    {
        rt_tick_t last_frame_tick = g_m55_mic.last_frame_tick;
        rt_tick_t stale_ticks = rt_tick_from_millisecond(2000);

        if ((last_frame_tick == 0U) ||
            ((rt_int32_t)(rt_tick_get() - last_frame_tick) <= (rt_int32_t)stale_ticks))
        {
            return -RT_EBUSY;
        }

        rt_kprintf("[m55_mic] stale running state, restart frames=%lu age_ticks=%lu\n",
                   (unsigned long)g_m55_mic.frame_count,
                   (unsigned long)(rt_tick_get() - last_frame_tick));
        g_m55_mic.running = RT_FALSE;
        rt_thread_mdelay(80);
        g_m55_mic.thread = RT_NULL;
    }

    if (g_m55_mic.dev == RT_NULL)
    {
        g_m55_mic.dev = rt_device_find("mic0");
        if (g_m55_mic.dev == RT_NULL)
        {
            rt_kprintf("[m55_mic] mic0 not found\n");
            return -RT_ERROR;
        }

        if (rt_device_open(g_m55_mic.dev, RT_DEVICE_OFLAG_RDONLY) != RT_EOK)
        {
            rt_kprintf("[m55_mic] open mic0 failed\n");
            g_m55_mic.dev = RT_NULL;
            return -RT_ERROR;
        }

        rt_memset(&caps, 0, sizeof(caps));
        caps.main_type = AUDIO_TYPE_INPUT;
        caps.sub_type = AUDIO_DSP_PARAM;
        caps.udata.config.samplerate = M55_AUDIO_SAMPLE_RATE;
        caps.udata.config.channels = M55_AUDIO_CHANNELS;
        caps.udata.config.samplebits = M55_AUDIO_BITS_PER_SAMPLE;
        if (rt_device_control(g_m55_mic.dev, AUDIO_CTL_CONFIGURE, &caps) == RT_EOK)
        {
            cy_rslt_t gain_ret = set_pdm_pcm_gain((rt_int16_t)M55_XIAOZHI_PDM_GAIN);

            rt_kprintf("[m55_mic] configured mic0 sr=%d ch=%d bits=%d\n",
                       M55_AUDIO_SAMPLE_RATE,
                       M55_AUDIO_CHANNELS,
                       M55_AUDIO_BITS_PER_SAMPLE);
            rt_kprintf("[m55_mic] pdm_gain=%d ret=%ld\n",
                       M55_XIAOZHI_PDM_GAIN,
                       (long)gain_ret);
        }
        else
        {
            rt_kprintf("[m55_mic] configure mic0 failed\n");
        }
    }

    g_m55_mic.running = RT_TRUE;
    g_m55_mic.last_frame_tick = 0U;
    g_m55_mic.thread = rt_thread_create("m55_mic",
                                        m55_mic_thread_entry,
                                        RT_NULL,
                                        M55_MIC_THREAD_STACK,
                                        18,
                                        10);
    if (g_m55_mic.thread == RT_NULL)
    {
        g_m55_mic.running = RT_FALSE;
        rt_kprintf("[m55_mic] create thread failed\n");
        return -RT_ERROR;
    }

    rt_thread_startup(g_m55_mic.thread);
    rt_kprintf("[m55_mic] started\n");
    (void)voice_service_publish_status_now();
    return RT_EOK;
}

static rt_err_t m55_mic_stop_internal(void)
{
    if (!g_m55_mic.running)
    {
        return RT_EOK;
    }

    g_m55_mic.running = RT_FALSE;
    rt_thread_mdelay(50);
    g_m55_mic.thread = RT_NULL;
    rt_kprintf("[m55_mic] stopped\n");
    (void)voice_service_publish_status_now();
    return RT_EOK;
}

static void m55_mic_test(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_mic_start_internal();
    rt_kprintf("m55_mic_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_mic_test, Start local CM55 mic0 capture test);

static void m55_mic_stop(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_mic_stop_internal();
    rt_kprintf("m55_mic_stop ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_mic_stop, Stop local CM55 mic0 capture test);

rt_err_t m55_speaker_tone_internal(rt_uint32_t duration_ms)
{
    rt_device_t speaker;
    struct rt_audio_caps caps;
    rt_int16_t frame[160];
    rt_uint32_t frame_count;
    rt_uint32_t frame_index;
    rt_uint32_t i;
    rt_err_t ret;
    rt_size_t written_total = 0U;

    speaker = rt_device_find("sound0");
    if (speaker == RT_NULL)
    {
        rt_kprintf("[m55qa] sound0 not found\n");
        return -101;
    }
    rt_kprintf("[m55qa] sound0 dev=%p flag=0x%lx open=0x%lx ref=%u\n",
               speaker,
               (unsigned long)speaker->flag,
               (unsigned long)speaker->open_flag,
               (unsigned)speaker->ref_count);

    rt_memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_OUTPUT;
    caps.sub_type = AUDIO_DSP_PARAM;
    caps.udata.config.samplerate = M55_AUDIO_SAMPLE_RATE;
    caps.udata.config.channels = 1;
    caps.udata.config.samplebits = M55_AUDIO_BITS_PER_SAMPLE;
    ret = rt_device_control(speaker, AUDIO_CTL_CONFIGURE, &caps);
    rt_kprintf("[m55qa] speaker tone configure ret=%d ms=%lu\n",
               ret,
               (unsigned long)duration_ms);
    if ((ret != RT_EOK) && (ret != -RT_ENOSYS))
    {
        return ret;
    }

    ret = rt_device_open(speaker, RT_DEVICE_OFLAG_WRONLY);
    rt_kprintf("[m55qa] open sound0 ret=%d flag=0x%lx open=0x%lx ref=%u\n",
               ret,
               (unsigned long)speaker->flag,
               (unsigned long)speaker->open_flag,
               (unsigned)speaker->ref_count);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[m55qa] open sound0 failed ret=%d\n", ret);
        return ret;
    }

    frame_count = duration_ms / 10U;
    if (frame_count == 0U)
    {
        frame_count = 1U;
    }

    for (frame_index = 0; frame_index < frame_count; frame_index++)
    {
        for (i = 0; i < (sizeof(frame) / sizeof(frame[0])); i++)
        {
            rt_uint32_t phase = ((frame_index * (sizeof(frame) / sizeof(frame[0]))) + i) % 32U;
            frame[i] = (phase < 16U) ? 6000 : -6000;
        }
        written_total += rt_device_write(speaker, 0, frame, sizeof(frame));
        rt_thread_mdelay(10);
    }

    rt_kprintf("[m55qa] speaker tone done written=%lu\n", (unsigned long)written_total);
    return (written_total > 0U) ? RT_EOK : -102;
}

static void m55qa_speaker_tone(int argc, char **argv)
{
    rt_uint32_t duration_ms = 1000U;
    rt_err_t ret;

    if (argc >= 2)
    {
        duration_ms = (rt_uint32_t)atoi(argv[1]);
        if (duration_ms == 0U)
        {
            duration_ms = 1000U;
        }
    }

    ret = m55_speaker_tone_internal(duration_ms);
    rt_kprintf("[m55qa] speaker_tone ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_speaker_tone, Play a local CM55 sound0 QA tone; arg ms);

static void voice_test(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_xiaozhi_talk_start_from_ui();
    rt_kprintf("voice_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(voice_test, Start Xiaozhi listening from CM55 mic0);

static void voice_stop(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_xiaozhi_talk_stop_from_ui();
    rt_kprintf("voice_stop ret=%d\n", ret);
}
MSH_CMD_EXPORT(voice_stop, Stop Xiaozhi listening from CM55 mic0);

static void wake_on(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_wake_listen_start_for_xiaozhi();
    rt_kprintf("wake_on ret=%d\n", ret);
}
MSH_CMD_EXPORT(wake_on, Start wake listening from CM55 mic0);

static void wake_off(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_wake_listen_stop_for_xiaozhi();
    rt_kprintf("wake_off ret=%d\n", ret);
}
MSH_CMD_EXPORT(wake_off, Stop wake listening from CM55 mic0);

static void wake_diag(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("wake_diag backend=%s ready=%d stage=%d err=%d threshold=%d/1000 noise=%d/1000 xiaorui=%d/1000 feature_src=%d feature_ret=%d alloc_src=%d alloc_size=%d alloc_fail_src=%d alloc_fail_size=%d alloc_diag=%d\n",
               xiaozhi_wake_engine_backend_name(),
               xiaozhi_wake_engine_is_ready() ? 1 : 0,
               xiaozhi_wake_engine_stage(),
               xiaozhi_wake_engine_last_error(),
               xiaozhi_wake_engine_threshold_permille(),
               xiaozhi_wake_engine_last_noise_permille(),
               xiaozhi_wake_engine_last_confidence_permille(),
               xiaozhi_wake_engine_last_feature_source(),
               xiaozhi_wake_engine_last_feature_error(),
               xiaozhi_wake_engine_last_alloc_source(),
               xiaozhi_wake_engine_last_alloc_size(),
               xiaozhi_wake_engine_last_alloc_fail_source(),
               xiaozhi_wake_engine_last_alloc_fail_size(),
               xiaozhi_wake_engine_alloc_diag());
}
MSH_CMD_EXPORT(wake_diag, Show XiaoZhi local wake model diagnostics);

static void wake_threshold(int argc, char **argv)
{
    int threshold;

    if (argc < 2)
    {
        rt_kprintf("wake_threshold current=%d/1000\n",
                   xiaozhi_wake_engine_threshold_permille());
        return;
    }

    threshold = atoi(argv[1]);
    threshold = xiaozhi_wake_engine_set_threshold_permille(threshold);
    rt_kprintf("wake_threshold now=%d/1000\n", threshold);
}
MSH_CMD_EXPORT(wake_threshold, Get or set XiaoZhi wake threshold in permille);

static void wake_dump_pcm(int argc, char **argv)
{
    const char *path = "/latest_wake.pcm";
    rt_err_t ret;

    if ((argc >= 2) && (argv[1] != RT_NULL) && (argv[1][0] != '\0'))
    {
        path = argv[1];
    }

    ret = voice_service_dump_latest_pcm(path);
    rt_kprintf("wake_dump_pcm ret=%d path=%s\n", ret, path);
}
MSH_CMD_EXPORT(wake_dump_pcm, Save latest CM55 wake PCM to a raw pcm file);

static void xz_url(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("xz_url current=%s\n", xiaozhi_voice_relay_get_url());
        return;
    }

    ret = xiaozhi_voice_relay_set_url(argv[1]);
    rt_kprintf("xz_url ret=%d url=%s\n", ret, xiaozhi_voice_relay_get_url());
}
MSH_CMD_EXPORT(xz_url, Get or set Xiaozhi websocket URL);

static void xz_token(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("xz_token configured=%d\n", xiaozhi_voice_relay_has_token() ? 1 : 0);
        return;
    }

    ret = xiaozhi_voice_relay_set_token(argv[1]);
    rt_kprintf("xz_token ret=%d configured=%d\n", ret, xiaozhi_voice_relay_has_token() ? 1 : 0);
}
MSH_CMD_EXPORT(xz_token, Set Xiaozhi platform relay token);

static void xz_token_begin(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = xiaozhi_voice_relay_token_update_begin();
    rt_kprintf("xz_token_begin ret=%d\n", ret);
}
MSH_CMD_EXPORT(xz_token_begin, Begin chunked Xiaozhi platform token update);

static void xz_token_part(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: xz_token_part <token_chunk_48_to_60_chars>\n");
        return;
    }

    ret = xiaozhi_voice_relay_token_update_part(argv[1]);
    rt_kprintf("xz_token_part ret=%d len=%lu\n",
               ret,
               (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(xz_token_part, Append one chunk to Xiaozhi platform token);

static void xz_token_commit(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = xiaozhi_voice_relay_token_update_commit();
    rt_kprintf("xz_token_commit ret=%d configured=%d\n",
               ret,
               xiaozhi_voice_relay_has_token() ? 1 : 0);
}
MSH_CMD_EXPORT(xz_token_commit, Commit chunked Xiaozhi platform token);

static void xz_token_clear(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    xiaozhi_voice_relay_token_update_clear();
    rt_kprintf("xz_token_clear configured=%d\n", xiaozhi_voice_relay_has_token() ? 1 : 0);
}
MSH_CMD_EXPORT(xz_token_clear, Clear Xiaozhi platform token);

static void xz_reconnect(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_reconnect_xiaozhi();
    rt_kprintf("xz_reconnect ret=%d\n", ret);
}
MSH_CMD_EXPORT(xz_reconnect, Reconnect Xiaozhi websocket after URL or token change);

static void xz_status(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("xz_status url=%s\n", xiaozhi_voice_relay_get_url());
    rt_kprintf("xz_status token=%d connected=%d ws_stage=%d ws_errno=%d\n",
               xiaozhi_voice_relay_has_token() ? 1 : 0,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
}
MSH_CMD_EXPORT(xz_status, Show Xiaozhi websocket status without printing token);

static void xz_tcp_probe(int argc, char **argv)
{
    const char *ip = M55_XIAOZHI_CLOUD_IP;
    int port = M55_XIAOZHI_CLOUD_PORT;
    int fd;
    int ret;
    int native_errno;
    struct sockaddr_in cloud_addr;

    if (argc >= 2)
    {
        ip = argv[1];
    }
    if (argc >= 3)
    {
        port = atoi(argv[2]);
    }

    rt_memset(&cloud_addr, 0, sizeof(cloud_addr));
    cloud_addr.sin_family = AF_INET;
    cloud_addr.sin_port = htons((uint16_t)port);
    cloud_addr.sin_addr.s_addr = inet_addr(ip);

    errno = 0;
    fd = lwip_socket(AF_INET, SOCK_STREAM, 0);
    native_errno = errno;
    if (fd < 0)
    {
        rt_kprintf("xz_tcp_probe socket fd=%d errno=%d\n", fd, native_errno);
        return;
    }

    errno = 0;
    ret = lwip_connect(fd, (struct sockaddr *)&cloud_addr, sizeof(cloud_addr));
    native_errno = errno;
    lwip_close(fd);
    rt_kprintf("xz_tcp_probe ip=%s port=%d ret=%d errno=%d\n", ip, port, ret, native_errno);
}
MSH_CMD_EXPORT(xz_tcp_probe, Probe Xiaozhi cloud TCP port);

static rt_err_t m55_voice_start_for_xiaozhi(void)
{
    rt_err_t ret;

    ret = voice_service_init("YOUR_BAIDU_API_KEY", "YOUR_BAIDU_SECRET_KEY");
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[m55] voice init ret=%d\n", ret);
        return ret;
    }

    ret = voice_service_start();
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[m55] voice start ret=%d\n", ret);
        return ret;
    }

    return RT_EOK;
}

static rt_err_t m55_wake_listen_start_for_xiaozhi(void)
{
    rt_err_t ret;

    ret = m55_voice_start_for_xiaozhi();
    if (ret != RT_EOK)
    {
        return ret;
    }

    ret = voice_service_set_wake_listening_direct(RT_TRUE);
    if (ret != RT_EOK)
    {
        return ret;
    }

    ret = m55_mic_start_internal();
    if ((ret == RT_EOK) || (ret == -RT_EBUSY))
    {
        return RT_EOK;
    }

    (void)voice_service_set_wake_listening_direct(RT_FALSE);
    return ret;
}

static rt_err_t m55_wake_listen_stop_for_xiaozhi(void)
{
    rt_err_t ret;

    ret = voice_service_set_wake_listening_direct(RT_FALSE);
    (void)m55_mic_stop_internal();
    return ret;
}

rt_err_t m55_xiaozhi_talk_start_from_ui(void)
{
    rt_err_t ret;

    ret = m55_voice_start_for_xiaozhi();
    if ((ret == RT_EOK) || (ret == -RT_EBUSY))
    {
        ret = voice_service_start_xiaozhi_talk();
    }
    if ((ret == RT_EOK) || (ret == -RT_EBUSY))
    {
        ret = m55_mic_start_internal();
    }

    rt_kprintf("[m55] ui xiaozhi talk start ret=%d token=%d connected=%d ws_stage=%d ws_errno=%d\n",
               ret,
               xiaozhi_voice_relay_has_token() ? 1 : 0,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
    m55_dump_thread_stacks("ui_start");
    (void)voice_service_publish_status_now();
    return ret;
}

rt_err_t m55_xiaozhi_talk_stop_from_ui(void)
{
    rt_err_t ret;

    ret = voice_service_stop_xiaozhi_talk();
    (void)voice_service_set_wake_listening_direct(RT_TRUE);
    (void)m55_mic_start_internal();
    rt_kprintf("[m55] ui xiaozhi talk stop ret=%d connected=%d ws_stage=%d ws_errno=%d\n",
               ret,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
    m55_dump_thread_stacks("ui_stop");
    (void)voice_service_publish_status_now();
    return ret;
}

static void xiaozhi_auto_connect_thread_entry(void *parameter)
{
    rt_err_t ret;
    rt_bool_t voice_ready = RT_FALSE;
    rt_uint32_t wifi_ready_streak = 0U;
    rt_uint32_t retry_delay = 0U;
    rt_uint32_t diag_count = 0U;

    RT_UNUSED(parameter);

    (void)xiaozhi_voice_relay_init();
    rt_kprintf("[m55_xz_auto] token=%d len=%lu url=%s\n",
               xiaozhi_voice_relay_has_token() ? 1 : 0,
               (unsigned long)xiaozhi_voice_relay_token_len(),
               xiaozhi_voice_relay_get_url());

    while (1)
    {
        wifi_config_snapshot_t snapshot;
        rt_bool_t connected;

        rt_thread_mdelay(2000);

        if (!xiaozhi_voice_relay_has_token())
        {
            if ((diag_count++ % 15U) == 0U)
            {
                rt_kprintf("[m55_xz_auto] waiting for Xiaozhi token len=%lu\n",
                           (unsigned long)xiaozhi_voice_relay_token_len());
                xiaozhi_bridge_publish_status();
            }
            continue;
        }

        (void)wifi_config_diag();
        wifi_config_get_snapshot(&snapshot);
        if ((snapshot.wlan_ready == 0U) || (snapshot.netdev_ip == 0U))
        {
            wifi_ready_streak = 0U;
            if ((diag_count++ % 10U) == 0U)
            {
                rt_kprintf("[m55_xz_auto] waiting wifi ready wlan=%lu ready=%lu ip=0x%08lx saved=%lu auto=%lu\n",
                           (unsigned long)snapshot.wlan_connected,
                           (unsigned long)snapshot.wlan_ready,
                           (unsigned long)snapshot.netdev_ip,
                           (unsigned long)snapshot.saved,
                           (unsigned long)snapshot.auto_connect);
                xiaozhi_bridge_publish_status();
            }
            continue;
        }
        if (++wifi_ready_streak < 3U)
        {
            continue;
        }
        if (retry_delay > 0U)
        {
            retry_delay--;
            continue;
        }

        if (!voice_ready)
        {
            ret = m55_voice_start_for_xiaozhi();
            if ((ret == RT_EOK) || (ret == -RT_EBUSY))
            {
                voice_ready = RT_TRUE;
                rt_kprintf("[m55_xz_auto] voice service started after wifi ready\n");
                m55_dump_thread_stacks("xz_auto_voice_ready");
            }
            else
            {
                rt_kprintf("[m55_xz_auto] voice service deferred ret=%d\n", ret);
                retry_delay = M55_XIAOZHI_AUTO_RETRY_DELAY_LOOPS;
                xiaozhi_bridge_publish_status();
                continue;
            }
        }

        connected = websocket_client_is_connected();
        if (connected)
        {
            if (!g_xiaozhi_voice_started)
            {
                ret = m55_wake_listen_start_for_xiaozhi();
                if (ret == RT_EOK)
                {
                    g_xiaozhi_voice_started = RT_TRUE;
                    rt_kprintf("[m55_xz_auto] wake listening armed while Xiaozhi already connected\n");
                }
                else
                {
                    rt_kprintf("[m55_xz_auto] wake listen deferred while connected ret=%d\n", ret);
                }
                xiaozhi_bridge_publish_status();
            }
            continue;
        }

        rt_kprintf("[m55_xz_auto] wifi ready ip=0x%08lx, reconnect Xiaozhi\n",
                   (unsigned long)snapshot.netdev_ip);
        ret = voice_service_reconnect_xiaozhi();
        rt_kprintf("[m55_xz_auto] reconnect ret=%d connected=%d stage=%d errno=%d\n",
                   ret,
                   websocket_client_is_connected() ? 1 : 0,
                   websocket_client_last_stage(),
                   websocket_client_last_errno());
        m55_dump_thread_stacks("xz_auto_reconnect");
        xiaozhi_bridge_publish_status();
        if (ret == RT_EOK)
        {
            ret = m55_wake_listen_start_for_xiaozhi();
            if (ret == RT_EOK)
            {
                g_xiaozhi_voice_started = RT_TRUE;
                rt_kprintf("[m55_xz_auto] wake listening armed after Xiaozhi connected\n");
            }
            else
            {
                rt_kprintf("[m55_xz_auto] wake listen deferred after connect ret=%d\n", ret);
            }
            continue;
        }
        retry_delay = M55_XIAOZHI_AUTO_RETRY_DELAY_LOOPS;
    }

    g_xiaozhi_auto_thread = RT_NULL;
}

static void xz_talk_on(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_voice_start_for_xiaozhi();
    if ((ret == RT_EOK) || (ret == -RT_EBUSY))
    {
        ret = voice_service_start_xiaozhi_talk();
    }
    if ((ret == RT_EOK) || (ret == -RT_EBUSY))
    {
        ret = m55_mic_start_internal();
    }

    rt_kprintf("xz_talk_on ret=%d token=%d connected=%d ws_stage=%d ws_errno=%d\n",
               ret,
               xiaozhi_voice_relay_has_token() ? 1 : 0,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
}
MSH_CMD_EXPORT(xz_talk_on, Start manual Xiaozhi cloud listening from CM55 mic);

static void xz_talk_off(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_stop_xiaozhi_talk();
    (void)voice_service_set_wake_listening_direct(RT_TRUE);
    (void)m55_mic_start_internal();
    rt_kprintf("xz_talk_off ret=%d connected=%d ws_stage=%d ws_errno=%d\n",
               ret,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
}
MSH_CMD_EXPORT(xz_talk_off, Stop manual Xiaozhi cloud listening);

static void xz_qa_text(int argc, char **argv)
{
    const char *text = (argc >= 2) ? argv[1] : RT_NULL;
    rt_err_t ret = voice_service_qa_xiaozhi_text_turn(text);

    rt_kprintf("xz_qa_text ret=%d connected=%d ws_stage=%d ws_errno=%d\n",
               ret,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
}
MSH_CMD_EXPORT(xz_qa_text, Send a XiaoZhi QA text turn through platform TTS);

static void xiaozhi_bridge_publish_ack(rt_uint32_t cmd, rt_err_t ret)
{
    m33_m55_message_t ack;

    rt_memset(&ack, 0, sizeof(ack));
    ack.type = MSG_TYPE_VOICE_CONTROL_ACK;
    ack.payload.voice_control.cmd = cmd;
    ack.payload.voice_control.arg0 = (rt_uint32_t)ret;
    ack.payload.voice_control.arg1 = (rt_uint32_t)rt_tick_get();
    (void)m33_m55_comm_publish(&ack);
}

static void xiaozhi_capture_start_worker_entry(void *parameter)
{
    rt_err_t ret;

    RT_UNUSED(parameter);

    ret = voice_service_start_xiaozhi_talk();
    rt_kprintf("[m55_xz_bridge] async start_capture talk_start ret=%d connected=%d stage=%d errno=%d\n",
               ret,
               websocket_client_is_connected() ? 1 : 0,
               websocket_client_last_stage(),
               websocket_client_last_errno());
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        voice_service_note_error(-41002);
        g_xiaozhi_capture_start_pending = RT_FALSE;
        (void)voice_service_publish_status_now();
        return;
    }

    ret = m55_mic_start_internal();
    rt_kprintf("[m55_xz_bridge] async start_capture mic_start ret=%d\n", ret);
    if (ret == -RT_EBUSY)
    {
        ret = RT_EOK;
    }
    if (ret != RT_EOK)
    {
        voice_service_note_error(-41003);
    }

    g_xiaozhi_capture_start_pending = RT_FALSE;
    (void)voice_service_publish_status_now();
}

static rt_err_t xiaozhi_bridge_start_capture_async(void)
{
    rt_thread_t thread;

    if (g_xiaozhi_capture_start_pending)
    {
        return -RT_EBUSY;
    }

    g_xiaozhi_capture_start_pending = RT_TRUE;
    thread = rt_thread_create("xz_cap_on",
                              xiaozhi_capture_start_worker_entry,
                              RT_NULL,
                              4096,
                              22,
                              10);
    if (thread == RT_NULL)
    {
        g_xiaozhi_capture_start_pending = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(thread);
    return RT_EOK;
}

static rt_err_t m55_bridge_run_tcp_probe(void)
{
    int fd;
    int ret;
    int opt_error = 0;
    socklen_t opt_len = sizeof(opt_error);
    fd_set writefds;
    struct timeval timeout;
    struct sockaddr_in addr;

    g_tcp_probe_stage = 0;
    g_tcp_probe_errno = 0;
    g_tcp_probe_result = -RT_ERROR;
    g_tcp_probe_so_error = 0;
    g_tcp_probe_select_ret = 0;
    g_tcp_probe_fcntl_ret = 0;
    xiaozhi_bridge_publish_status();

    rt_memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(M55_XIAOZHI_CLOUD_PORT);
    addr.sin_addr.s_addr = inet_addr(M55_XIAOZHI_CLOUD_IP);

    errno = 0;
    g_tcp_probe_stage = 10;
    xiaozhi_bridge_publish_status();
    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
    {
        g_tcp_probe_errno = errno;
        g_tcp_probe_result = -RT_ERROR;
        rt_kprintf("[m55_tcp_probe] socket failed fd=%d errno=%d\n", fd, errno);
        xiaozhi_bridge_publish_status();
        return -RT_ERROR;
    }

    errno = 0;
    g_tcp_probe_stage = 20;
    xiaozhi_bridge_publish_status();
    ret = fcntl(fd, F_SETFL, O_NONBLOCK);
    g_tcp_probe_fcntl_ret = ret;
    if (ret < 0)
    {
        g_tcp_probe_errno = errno;
        g_tcp_probe_result = -RT_ERROR;
        rt_kprintf("[m55_tcp_probe] fcntl nonblock failed fd=%d ret=%d errno=%d\n", fd, ret, errno);
        closesocket(fd);
        xiaozhi_bridge_publish_status();
        return -RT_ERROR;
    }

    errno = 0;
    g_tcp_probe_stage = 30;
    xiaozhi_bridge_publish_status();
    ret = connect(fd, (struct sockaddr *)&addr, sizeof(addr));
    g_tcp_probe_result = ret;
    g_tcp_probe_errno = errno;
    if (ret == 0)
    {
        g_tcp_probe_stage = 60;
        g_tcp_probe_so_error = 0;
        rt_kprintf("[m55_tcp_probe] connect immediate ok %s:%d fd=%d\n",
                   M55_XIAOZHI_CLOUD_IP,
                   M55_XIAOZHI_CLOUD_PORT,
                   fd);
        closesocket(fd);
        xiaozhi_bridge_publish_status();
        return RT_EOK;
    }

    if ((errno != EINPROGRESS) && (errno != EWOULDBLOCK) && (errno != EALREADY))
    {
        rt_kprintf("[m55_tcp_probe] connect immediate failed ret=%d errno=%d\n", ret, errno);
        closesocket(fd);
        xiaozhi_bridge_publish_status();
        return -RT_ERROR;
    }

    FD_ZERO(&writefds);
    FD_SET(fd, &writefds);
    timeout.tv_sec = 5;
    timeout.tv_usec = 0;

    errno = 0;
    g_tcp_probe_stage = 40;
    xiaozhi_bridge_publish_status();
    ret = select(fd + 1, RT_NULL, &writefds, RT_NULL, &timeout);
    g_tcp_probe_select_ret = ret;
    g_tcp_probe_errno = errno;
    if (ret <= 0)
    {
        g_tcp_probe_result = (ret == 0) ? -RT_ETIMEOUT : -RT_ERROR;
        rt_kprintf("[m55_tcp_probe] select failed ret=%d errno=%d\n", ret, errno);
        closesocket(fd);
        xiaozhi_bridge_publish_status();
        return (ret == 0) ? -RT_ETIMEOUT : -RT_ERROR;
    }

    errno = 0;
    g_tcp_probe_stage = 50;
    xiaozhi_bridge_publish_status();
    ret = getsockopt(fd, SOL_SOCKET, SO_ERROR, &opt_error, &opt_len);
    g_tcp_probe_errno = errno;
    g_tcp_probe_so_error = opt_error;
    if ((ret < 0) || (opt_error != 0))
    {
        g_tcp_probe_result = (ret < 0) ? -RT_ERROR : -opt_error;
        rt_kprintf("[m55_tcp_probe] so_error ret=%d errno=%d so_error=%d\n", ret, errno, opt_error);
        closesocket(fd);
        xiaozhi_bridge_publish_status();
        return -RT_ERROR;
    }

    g_tcp_probe_stage = 60;
    g_tcp_probe_result = 0;
    g_tcp_probe_errno = 0;
    rt_kprintf("[m55_tcp_probe] connect ok %s:%d fd=%d select=%d\n",
               M55_XIAOZHI_CLOUD_IP,
               M55_XIAOZHI_CLOUD_PORT,
               fd,
               g_tcp_probe_select_ret);
    closesocket(fd);
    xiaozhi_bridge_publish_status();
    return RT_EOK;
}

static void xiaozhi_bridge_publish_status(void)
{
    m33_m55_message_t status;

    if (voice_service_publish_status_now() == RT_EOK)
    {
        return;
    }

    rt_memset(&status, 0, sizeof(status));
    status.type = MSG_TYPE_VOICE_STATUS;
    status.payload.voice_status.flags =
        (xiaozhi_voice_relay_has_token() ? VOICE_STATUS_FLAG_XIAOZHI_HAS_TOKEN : 0U) |
        (websocket_client_is_connected() ? VOICE_STATUS_FLAG_XIAOZHI_CONNECTED : 0U);
    wifi_config_fill_voice_status(&status.payload.voice_status);
    if (xiaozhi_voice_relay_has_token())
    {
        status.payload.voice_status.flags |= VOICE_STATUS_FLAG_XIAOZHI_HAS_TOKEN;
    }
    if (websocket_client_is_connected())
    {
        status.payload.voice_status.flags |= VOICE_STATUS_FLAG_XIAOZHI_CONNECTED;
    }
    status.payload.voice_status.xiaozhi_ws_stage = websocket_client_last_stage();
    status.payload.voice_status.xiaozhi_ws_errno = websocket_client_last_errno();
    status.payload.voice_status.xiaozhi_token_len = (rt_uint32_t)xiaozhi_voice_relay_token_len();
    status.payload.voice_status.xiaozhi_token_staging_len = (rt_uint32_t)xiaozhi_voice_relay_token_staging_len();
    status.payload.voice_status.net_probe_posix_tcp = (rt_int32_t)g_xz_bridge_loops;
    status.payload.voice_status.net_probe_posix_errno = (rt_int32_t)g_xz_bridge_consumed;
    status.payload.voice_status.net_probe_sal_tcp = g_xz_bridge_last_consume_ret;
    status.payload.voice_status.net_probe_sal_errno = (rt_int32_t)g_xz_bridge_last_msg_type;
    status.payload.voice_status.net_probe_lwip_tcp = (rt_int32_t)g_xz_reconnect_step;
    status.payload.voice_status.net_probe_lwip_errno = g_xz_reconnect_result;
    status.payload.voice_status.cloud_tcp_result = g_tcp_probe_select_ret;
    status.payload.voice_status.cloud_tcp_errno = g_tcp_probe_fcntl_ret;
    (void)m33_m55_comm_publish(&status);
}

rt_uint32_t voice_service_bridge_diag_loops(void)
{
    return g_xz_bridge_loops;
}

rt_uint32_t voice_service_bridge_diag_consumed(void)
{
    return g_xz_bridge_consumed;
}

rt_int32_t voice_service_bridge_diag_last_ret(void)
{
    return g_xz_bridge_last_consume_ret;
}

rt_int32_t voice_service_bridge_diag_phase(void)
{
    return g_xz_bridge_phase;
}

static void xiaozhi_reconnect_thread_entry(void *parameter)
{
    rt_err_t ret;
    rt_bool_t service_ready;

    RT_UNUSED(parameter);

    g_xz_reconnect_step = 10U;
    g_xz_reconnect_result = 0;

    ret = voice_service_init("YOUR_BAIDU_API_KEY", "YOUR_BAIDU_SECRET_KEY");
    g_xz_reconnect_result = ret;
    g_xz_reconnect_step = 11U;
    service_ready = ((ret == RT_EOK) || (ret == -RT_EBUSY)) ? RT_TRUE : RT_FALSE;
    if (service_ready)
    {
        g_xiaozhi_voice_started = RT_TRUE;
        g_xz_reconnect_step = 20U;
        g_xz_reconnect_result = RT_EOK;
        if (!websocket_client_is_connected())
        {
            g_xz_reconnect_step = 30U;
            ret = websocket_client_connect();
            g_xz_reconnect_result = ret;
            g_xz_reconnect_step = 31U;
        }
        else
        {
            ret = RT_EOK;
        }
        if (ret == RT_EOK)
        {
            char hello[768];

            g_xz_reconnect_step = 40U;
            ret = xiaozhi_voice_relay_build_hello(hello, sizeof(hello));
            if (ret == RT_EOK)
            {
                ret = websocket_client_send_text(hello);
            }
            g_xz_reconnect_result = ret;
            g_xz_reconnect_step = 41U;
        }
    }

    g_xz_reconnect_thread = RT_NULL;
}

static rt_err_t xiaozhi_bridge_start_reconnect_async(void)
{
    if (g_xz_reconnect_thread != RT_NULL)
    {
        return -RT_EBUSY;
    }

    wifi_status_publish_kick();
    g_xz_reconnect_thread = rt_thread_create("xz_reconn",
                                             xiaozhi_reconnect_thread_entry,
                                             RT_NULL,
                                             12288,
                                             17,
                                             10);
    if (g_xz_reconnect_thread == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_xz_reconnect_thread);
    return RT_EOK;
}

static void wifi_status_publish_thread_entry(void *parameter)
{
    RT_UNUSED(parameter);

    for (rt_uint32_t i = 0; i < 45U; i++)
    {
        (void)wifi_config_diag();
        (void)wifi_config_whd_diag();
        xiaozhi_bridge_publish_status();
        rt_thread_mdelay(1000);
    }

    g_wifi_status_thread = RT_NULL;
}

static void wifi_status_publish_kick(void)
{
    if (g_wifi_status_thread != RT_NULL)
    {
        return;
    }

    g_wifi_status_thread = rt_thread_create("wifi_stat",
                                            wifi_status_publish_thread_entry,
                                            RT_NULL,
                                            4096,
                                            19,
                                            10);
    if (g_wifi_status_thread != RT_NULL)
    {
        rt_thread_startup(g_wifi_status_thread);
    }
}

static rt_err_t xiaozhi_bridge_handle_config(const voice_config_msg_t *config)
{
    rt_err_t ret = RT_EOK;

    if (config == RT_NULL)
    {
        return -RT_EINVAL;
    }

    switch ((voice_config_key_t)config->key)
    {
    case VOICE_CONFIG_XIAOZHI_URL:
        ret = xiaozhi_voice_relay_set_url(config->value);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN:
        ret = xiaozhi_voice_relay_set_token(config->value);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_BEGIN:
        ret = xiaozhi_voice_relay_token_update_begin();
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_PART:
        ret = xiaozhi_voice_relay_token_update_part(config->value);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_COMMIT:
        ret = xiaozhi_voice_relay_token_update_commit();
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_CLEAR:
        xiaozhi_voice_relay_token_update_clear();
        ret = RT_EOK;
        break;
    case VOICE_CONFIG_XIAOZHI_RECONNECT:
        ret = xiaozhi_bridge_start_reconnect_async();
        break;
    case VOICE_CONFIG_XIAOZHI_QA_TEXT:
        ret = voice_service_qa_xiaozhi_text_turn(config->value);
        break;
    case VOICE_CONFIG_WIFI_SSID:
        ret = wifi_config_set_ssid(config->value);
        break;
    case VOICE_CONFIG_WIFI_PASSWORD:
        ret = wifi_config_set_password(config->value);
        break;
    case VOICE_CONFIG_WIFI_CONNECT:
        ret = wifi_config_connect();
        wifi_status_publish_kick();
        break;
    case VOICE_CONFIG_WIFI_DISCONNECT:
        ret = wifi_config_disconnect();
        wifi_status_publish_kick();
        break;
    case VOICE_CONFIG_WIFI_SAVE:
        ret = wifi_config_save();
        break;
    case VOICE_CONFIG_WIFI_FORGET:
        ret = wifi_config_forget();
        wifi_status_publish_kick();
        break;
    case VOICE_CONFIG_WIFI_AUTO_CONNECT:
        ret = wifi_config_set_auto_connect((config->value[0] == '0') ? RT_FALSE : RT_TRUE);
        if (ret == RT_EOK)
        {
            ret = wifi_config_save();
        }
        break;
    default:
        ret = -RT_EINVAL;
        break;
    }

    rt_kprintf("[m55_xz_bridge] config key=%lu ret=%d token=%d\n",
               (unsigned long)config->key,
               ret,
               xiaozhi_voice_relay_has_token() ? 1 : 0);
    return ret;
}

static rt_err_t xiaozhi_bridge_handle_control(const voice_control_msg_t *control)
{
    rt_err_t ret = RT_EOK;

    if (control == RT_NULL)
    {
        return -RT_EINVAL;
    }

    switch ((voice_control_cmd_t)control->cmd)
    {
    case VOICE_CTRL_START_CAPTURE:
        ret = m55_voice_start_for_xiaozhi();
        rt_kprintf("[m55_xz_bridge] start_capture voice_start ret=%d\n", ret);
        if ((ret != RT_EOK) && (ret != -RT_EBUSY))
        {
            voice_service_note_error(-41001);
            break;
        }
        if ((ret == RT_EOK) || (ret == -RT_EBUSY))
        {
            g_xiaozhi_voice_started = RT_TRUE;
            ret = xiaozhi_bridge_start_capture_async();
            rt_kprintf("[m55_xz_bridge] start_capture queued ret=%d connected=%d stage=%d errno=%d\n",
                       ret,
                       websocket_client_is_connected() ? 1 : 0,
                       websocket_client_last_stage(),
                       websocket_client_last_errno());
        }
        break;
    case VOICE_CTRL_STOP_CAPTURE:
        if (voice_service_xiaozhi_is_listening())
        {
            ret = voice_service_abort_xiaozhi_talk_local();
            rt_kprintf("[m55_xz_bridge] stop_capture local_abort ret=%d connected=%d stage=%d errno=%d\n",
                       ret,
                       websocket_client_is_connected() ? 1 : 0,
                       websocket_client_last_stage(),
                       websocket_client_last_errno());
        }
        else
        {
            ret = RT_EOK;
            rt_kprintf("[m55_xz_bridge] stop_capture already idle connected=%d stage=%d errno=%d\n",
                       websocket_client_is_connected() ? 1 : 0,
                       websocket_client_last_stage(),
                       websocket_client_last_errno());
        }
        (void)voice_service_set_wake_listening_direct(RT_TRUE);
        if (ret == RT_EOK)
        {
            rt_err_t mic_ret = m55_mic_start_internal();
            rt_kprintf("[m55_xz_bridge] stop_capture mic_keepalive ret=%d\n", mic_ret);
            if ((mic_ret != RT_EOK) && (mic_ret != -RT_EBUSY))
            {
                ret = mic_ret;
                voice_service_note_error(-41004);
            }
        }
        break;
    case VOICE_CTRL_START_LISTEN:
        ret = m55_wake_listen_start_for_xiaozhi();
        if (ret == RT_EOK)
        {
            g_xiaozhi_voice_started = RT_TRUE;
        }
        break;
    case VOICE_CTRL_STOP_LISTEN:
        ret = m55_wake_listen_stop_for_xiaozhi();
        break;
    case VOICE_CTRL_NET_PROBE:
        ret = m55_bridge_run_tcp_probe();
        break;
    case VOICE_CTRL_WIFI_DIAG:
        ret = wifi_config_diag();
        break;
    case VOICE_CTRL_WIFI_SCAN:
        ret = wifi_config_scan();
        wifi_status_publish_kick();
        break;
    case VOICE_CTRL_WHD_DIAG:
        ret = wifi_config_whd_diag();
        break;
    case VOICE_CTRL_WAKE_SET_THRESHOLD:
        ret = xiaozhi_wake_engine_set_threshold_permille((int)control->arg0);
        if (ret >= 0)
        {
            (void)voice_service_publish_status_now();
            ret = RT_EOK;
        }
        break;
    case VOICE_CTRL_M33_PCM_PROBE_ENABLE:
    case VOICE_CTRL_M33_PCM_PROBE_DISABLE:
    case VOICE_CTRL_M55_SPEAKER_TONE:
    {
        m33_m55_message_t local_msg;

        rt_memset(&local_msg, 0, sizeof(local_msg));
        local_msg.type = MSG_TYPE_VOICE_CONTROL;
        local_msg.payload.voice_control = *control;
        voice_service_handle_ipc_message(&local_msg);
        ret = RT_EOK;
        break;
    }
    default:
        ret = -RT_EINVAL;
        break;
    }

    rt_kprintf("[m55_xz_bridge] control cmd=%lu ret=%d\n",
               (unsigned long)control->cmd,
               ret);
    return ret;
}

static void xiaozhi_bridge_thread_entry(void *parameter)
{
    m33_m55_message_t msg;

    RT_UNUSED(parameter);

    (void)m33_m55_comm_init();
    (void)xiaozhi_voice_relay_init();
    rt_kprintf("[m55_xz_bridge] ready token=%d url=%s\n",
               xiaozhi_voice_relay_has_token() ? 1 : 0,
               xiaozhi_voice_relay_get_url());

    while (1)
    {
        rt_err_t consume_ret;

        g_xz_bridge_loops++;
        if ((g_xz_bridge_loops % 500U) == 0U)
        {
            rt_kprintf("[m55_xz_bridge] hb loops=%lu consumed=%lu ret=%ld type=%lu phase=%ld\n",
                       (unsigned long)g_xz_bridge_loops,
                       (unsigned long)g_xz_bridge_consumed,
                       (long)g_xz_bridge_last_consume_ret,
                       (unsigned long)g_xz_bridge_last_msg_type,
                       (long)g_xz_bridge_phase);
        }
        g_xz_bridge_phase = 1;
        while ((consume_ret = m33_m55_comm_consume(&msg)) == RT_EOK)
        {
            rt_err_t ret = -RT_EINVAL;

            g_xz_bridge_phase = 2;
            g_xz_bridge_consumed++;
            g_xz_bridge_last_msg_type = msg.type;
            if ((g_xz_bridge_consumed % 100U) == 0U)
            {
                rt_kprintf("[m55_xz_bridge] consumed=%lu type=%lu\n",
                           (unsigned long)g_xz_bridge_consumed,
                           (unsigned long)msg.type);
            }
            if (msg.type == MSG_TYPE_VOICE_CONFIG)
            {
                g_xz_bridge_phase = 10;
                ret = xiaozhi_bridge_handle_config(&msg.payload.voice_config);
                g_xz_bridge_phase = 11;
                xiaozhi_bridge_publish_ack(1000U + msg.payload.voice_config.key, ret);
                xiaozhi_bridge_publish_status();
            }
            else if (msg.type == MSG_TYPE_VOICE_CONTROL)
            {
                g_xz_bridge_phase = 20;
                ret = xiaozhi_bridge_handle_control(&msg.payload.voice_control);
                g_xz_bridge_phase = 21;
                xiaozhi_bridge_publish_ack(msg.payload.voice_control.cmd, ret);
                xiaozhi_bridge_publish_status();
            }
            else
            {
                g_xz_bridge_phase = 30 + (rt_int32_t)msg.type;
                voice_service_handle_ipc_message(&msg);
            }
        }
        g_xz_bridge_last_consume_ret = consume_ret;
        g_xz_bridge_phase = 3;
        rt_thread_mdelay(50);
    }
}

static void xiaozhi_bridge_thread_start(void)
{
    if (g_xiaozhi_bridge_thread != RT_NULL)
    {
        return;
    }

    g_xiaozhi_bridge_thread = rt_thread_create("xz_bridge",
                                               xiaozhi_bridge_thread_entry,
                                               RT_NULL,
                                               32768,
                                               17,
                                               10);
    if (g_xiaozhi_bridge_thread != RT_NULL)
    {
        rt_thread_startup(g_xiaozhi_bridge_thread);
    }
    else
    {
        rt_kprintf("[m55_xz_bridge] create thread failed\n");
    }
}

static void m55_wifi_ssid(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: m55_wifi_ssid <ssid>\n");
        return;
    }

    ret = wifi_config_set_ssid(argv[1]);
    rt_kprintf("m55_wifi_ssid ret=%d len=%lu\n", ret, (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(m55_wifi_ssid, Set CM55 WiFi SSID in RAM);

static void m55_wifi_password(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: m55_wifi_password <password>\n");
        return;
    }

    ret = wifi_config_set_password(argv[1]);
    rt_kprintf("m55_wifi_password ret=%d len=%lu\n", ret, (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(m55_wifi_password, Set CM55 WiFi password in RAM);

static void m55_wifi_connect(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    rt_kprintf("m55_wifi_connect ret=%d\n", wifi_config_connect());
}
MSH_CMD_EXPORT(m55_wifi_connect, Connect CM55 WiFi using staged SSID/password);

static void m55_wifi_save(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    rt_kprintf("m55_wifi_save ret=%d\n", wifi_config_save());
}
MSH_CMD_EXPORT(m55_wifi_save, Save CM55 WiFi SSID/password to local flash);

static void m55_wifi_forget(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    rt_kprintf("m55_wifi_forget ret=%d\n", wifi_config_forget());
}
MSH_CMD_EXPORT(m55_wifi_forget, Remove saved CM55 WiFi credentials);

static void m55_wifi_auto(int argc, char **argv)
{
    rt_bool_t enable;

    if (argc < 2)
    {
        wifi_config_snapshot_t snapshot;
        wifi_config_get_snapshot(&snapshot);
        rt_kprintf("usage: m55_wifi_auto <0|1>, current=%lu\n",
                   (unsigned long)snapshot.auto_connect);
        return;
    }

    enable = (argv[1][0] != '0') ? RT_TRUE : RT_FALSE;
    rt_kprintf("m55_wifi_auto ret=%d\n", wifi_config_set_auto_connect(enable));
    rt_kprintf("m55_wifi_save ret=%d\n", wifi_config_save());
}
MSH_CMD_EXPORT(m55_wifi_auto, Enable or disable saved WiFi auto-connect);

static void m55_wifi_status(int argc, char **argv)
{
    wifi_config_snapshot_t snapshot;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    wifi_config_get_snapshot(&snapshot);
    rt_kprintf("[wifi_config] ssid=%s saved=%lu auto=%lu storage=%ld connected=%lu ready=%lu rssi=%ld netdev=%s flags=0x%lx last=%ld whd=%ld/%ld\n",
               snapshot.ssid[0] ? snapshot.ssid : "(empty)",
               (unsigned long)snapshot.saved,
               (unsigned long)snapshot.auto_connect,
               (long)snapshot.storage_result,
               (unsigned long)snapshot.wlan_connected,
               (unsigned long)snapshot.wlan_ready,
               (long)snapshot.wlan_rssi,
               snapshot.netdev_name[0] ? snapshot.netdev_name : "(none)",
               (unsigned long)snapshot.netdev_flags,
               (long)snapshot.last_result,
               (long)snapshot.whd_stage,
               (long)snapshot.whd_result);
}
MSH_CMD_EXPORT(m55_wifi_status, Print saved CM55 WiFi config and live status);

static void m55_wifi_print_aps(void)
{
    rt_int32_t i;
    rt_int32_t count = wifi_config_get_scan_count();

    rt_kprintf("[wifi_config] cached_ap_count=%ld\n", (long)count);
    if (count <= 0)
    {
        rt_kprintf("[wifi_config] no cached APs; run m55_wifi_scan and wait a few seconds\n");
        return;
    }

    for (i = 0; (i < count) && (i < WIFI_CONFIG_SCAN_MAX_APS); i++)
    {
        wifi_config_ap_t ap;

        if (wifi_config_get_scan_ap(i, &ap) != RT_EOK)
        {
            continue;
        }

        rt_kprintf("[wifi_config] ap[%ld] ssid=\"%s\" rssi=%ld security=%s channel=%ld bssid=%02x:%02x:%02x:%02x:%02x:%02x\n",
                   (long)i,
                   ap.ssid[0] ? ap.ssid : "(hidden)",
                   (long)ap.rssi,
                   wifi_config_security_name(ap.security),
                   (long)ap.channel,
                   ap.bssid[0],
                   ap.bssid[1],
                   ap.bssid[2],
                   ap.bssid[3],
                   ap.bssid[4],
                   ap.bssid[5]);
    }
}

static void m55_wifi_aps(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    m55_wifi_print_aps();
}
MSH_CMD_EXPORT(m55_wifi_aps, Print cached CM55 WiFi scan results);

static void m55_wifi_disconnect(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    rt_kprintf("m55_wifi_disconnect ret=%d\n", wifi_config_disconnect());
}
MSH_CMD_EXPORT(m55_wifi_disconnect, Disconnect CM55 WiFi);

static void m55_wifi_diag(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    (void)wifi_config_diag();
    (void)wifi_config_whd_diag();
}
MSH_CMD_EXPORT(m55_wifi_diag, Print CM55 WiFi and WHD diagnostics);

static void m55_wifi_scan(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    rt_kprintf("m55_wifi_scan ret=%d\n", wifi_config_scan());
    rt_kprintf("wait 3-5 seconds, then run m55_wifi_aps or refresh LVGL with Diag\n");
    m55_wifi_print_aps();
}
MSH_CMD_EXPORT(m55_wifi_scan, Start CM55 WiFi scan);

static void voice_boot_thread_entry(void *parameter)
{
    rt_err_t ret;
    const char *api_key = "YOUR_BAIDU_API_KEY";
    const char *secret_key = "YOUR_BAIDU_SECRET_KEY";

    RT_UNUSED(parameter);

    rt_thread_mdelay(M55_VOICE_BOOT_DELAY_MS);
    rt_kprintf("[m55] starting voice service\n");

    ret = voice_service_init(api_key, secret_key);
    if (ret != RT_EOK)
    {
        rt_kprintf("Voice service init failed: %d\n", ret);
        g_voice_boot_thread = RT_NULL;
        return;
    }

    m55_dump_thread_stacks("voice_boot_after_init");
    rt_kprintf("[m55] voice service initialized\n");
    xiaozhi_bridge_thread_start();
    ret = voice_service_start();
    if (ret != RT_EOK)
    {
        rt_kprintf("Voice service start failed: %d\n", ret);
    }
    else
    {
        ret = m55_mic_start_internal();
        rt_kprintf("[m55] local mic autostart ret=%d\n", ret);
    }

    g_voice_boot_thread = RT_NULL;
}

static void boot_self_test_thread_entry(void *parameter)
{
    int i;

    RT_UNUSED(parameter);

    for (i = 0; i < M55_BOOT_SELF_TEST_RETRY_COUNT; i++)
    {
        rt_err_t ret = model_result_publish_boot_self_test();
        rt_kprintf("[m55] boot self-test publish ret=%d try=%d\n", ret, i + 1);
        rt_thread_mdelay(1000);
    }

    g_boot_self_test_thread = RT_NULL;
}

int main(void)
{
    rt_err_t ret;
#if M55_WIFI_SCAN_QA_ONLY
    rt_thread_t wifi_qa_thread;
#endif

    rt_kprintf("Hello RT-Thread\r\n");
    rt_kprintf("This core is cortex-m55\n");
#if M55_DETACH_CONSOLE_FOR_M33_QA
    m55_console_detach();
#endif

#if M55_ENABLE_LED_HEARTBEAT
    rt_pin_mode(LED_PIN_G, PIN_MODE_OUTPUT);
#endif

#if M55_WIFI_SCAN_QA_ONLY
    rt_kprintf("[m55] WiFi scan QA-only mode; LVGL/voice/OpenClaw/HTTP/autoconnect disabled\n");
    wifi_qa_thread = rt_thread_create("wifi_qa",
                                      m55_wifi_scan_qa_thread_entry,
                                      RT_NULL,
                                      4096,
                                      28,
                                      10);
    if (wifi_qa_thread)
    {
        rt_thread_startup(wifi_qa_thread);
    }

    while (1)
    {
        #if M55_ENABLE_LED_HEARTBEAT
        rt_pin_write(LED_PIN_G, PIN_LOW);
        #endif
        rt_thread_mdelay(200);
        #if M55_ENABLE_LED_HEARTBEAT
        rt_pin_write(LED_PIN_G, PIN_HIGH);
        #endif
        rt_thread_mdelay(800);
    }
#else
    (void)wifi_config_service_init();

#ifdef BSP_USING_LVGL
    rt_kprintf("[m55] starting LVGL thread\n");
    ret = lvgl_thread_init();
    rt_kprintf("[m55] LVGL thread init ret=%d\n", ret);
#endif
    wifi_status_publish_kick();

#if !M55_WIFI_LVGL_ONLY
#if M55_WIFI_AUTO_CONNECT_ON_BOOT
    (void)wifi_config_start_auto_connect(3500U);
    wifi_status_publish_kick();
#else
    rt_kprintf("[m55] WiFi auto-connect on boot disabled for XiaoZhi QA; use LVGL connect or m55qa_wifi_connect\n");
#endif

    g_boot_self_test_thread = rt_thread_create("m55_self",
                                               boot_self_test_thread_entry,
                                               RT_NULL,
                                               2048,
                                               15,
                                               10);
    if (g_boot_self_test_thread)
    {
        rt_thread_startup(g_boot_self_test_thread);
    }

    ret = openclaw_integration_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("OpenClaw integration init failed: %d\n", ret);
    }

#if M55_ENABLE_LOCAL_HTTP_SERVER
    ret = http_server_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("HTTP server init failed: %d\n", ret);
    }
#else
    rt_kprintf("M55 local HTTP server disabled; XiaoZhi voice relay uses outbound WebSocket\n");
#endif

    g_voice_boot_thread = rt_thread_create("voice_bt",
                                           voice_boot_thread_entry,
                                           RT_NULL,
                                           M55_VOICE_BOOT_THREAD_STACK,
                                           16,
                                           10);
    if (g_voice_boot_thread)
    {
        rt_thread_startup(g_voice_boot_thread);
    }
#else
    rt_kprintf("[m55] WiFi+LVGL-only mode; voice/OpenClaw/HTTP/autoconnect disabled\n");
#if M55_WIFI_AUTO_CONNECT_ON_BOOT
    (void)wifi_config_start_auto_connect(3500U);
    wifi_status_publish_kick();
#else
    rt_kprintf("[m55] WiFi auto-connect on boot disabled for XiaoZhi QA; use LVGL connect or m55qa_wifi_connect\n");
#endif
    g_voice_boot_thread = rt_thread_create("voice_bt",
                                           voice_boot_thread_entry,
                                           RT_NULL,
                                           M55_VOICE_BOOT_THREAD_STACK,
                                           16,
                                           10);
    if (g_voice_boot_thread)
    {
        rt_thread_startup(g_voice_boot_thread);
    }
#if M55_XIAOZHI_AUTO_ENABLE
    g_xiaozhi_auto_thread = rt_thread_create("xz_auto",
                                             xiaozhi_auto_connect_thread_entry,
                                             RT_NULL,
                                             M55_XIAOZHI_AUTO_THREAD_STACK,
                                             17,
                                             10);
    if (g_xiaozhi_auto_thread)
    {
        rt_thread_startup(g_xiaozhi_auto_thread);
    }
#endif
#endif

    while (1)
    {
        #if M55_ENABLE_LED_HEARTBEAT
        rt_pin_write(LED_PIN_G, PIN_LOW);
        #endif
        rt_thread_mdelay(500);
        #if M55_ENABLE_LED_HEARTBEAT
        rt_pin_write(LED_PIN_G, PIN_HIGH);
        #endif
        rt_thread_mdelay(500);
    }

    return 0;
#endif
}
