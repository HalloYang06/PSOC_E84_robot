#include "voice_service.h"

#include "baidu_asr.h"
#include "baidu_tts.h"
#include "m33_m55_comm.h"
#include "model_result_publisher.h"
#include "official_voice_service.h"
#include "websocket_client.h"
#include "wifi_config_service.h"
#include "xiaozhi_opus_decoder.h"
#include "xiaozhi_ui_state.h"
#include "xiaozhi_voice_relay.h"
#include "xiaozhi_wake_engine.h"

#include <rtdevice.h>
#include <netdev_ipaddr.h>
#include <netdev.h>
#include <wlan_mgnt.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define VOICE_PCM_BUFFER_SIZE        (320000U)
#define VOICE_TTS_PENDING_SLOT_SIZE   (4096U)
#define VOICE_TTS_PENDING_SLOT_COUNT  (64U)
#define VOICE_TTS_PENDING_BUFFER_SIZE (VOICE_TTS_PENDING_SLOT_SIZE * VOICE_TTS_PENDING_SLOT_COUNT)
#define VOICE_TTS_CHUNK_GAP_MS        12U
#define VOICE_TTS_PUBLISH_RETRY_COUNT 5U
#define VOICE_TTS_PUBLISH_RETRY_MS    20U
#define VOICE_JSON_BUFFER_SIZE       (768U)
#define VOICE_SERVER_AUDIO_CHUNK     (4096U)
#define WAKE_SKIP_WINDOWS_AFTER_TRIGGER (3U)
#define WAKE_GATE_MIN_PEAK           (5500U)
#define WAKE_GATE_MIN_AVG_ABS        (750U)
#define WAKE_GATE_MIN_ACTIVE_FRAMES  (28U)
#define VOICE_STATUS_PUBLISH_EVERY_FRAMES 20U
#define XIAOZHI_EOU_MIN_RECORD_MS    900U
#define XIAOZHI_EOU_MANUAL_MIN_RECORD_MS 3500U
#define XIAOZHI_EOU_SILENCE_MS       1400U
#define XIAOZHI_EOU_MAX_RECORD_MS    12000U
#define XIAOZHI_EOU_SILENCE_PEAK     700U
#define XIAOZHI_EOU_SILENCE_AVG      120U
#define XIAOZHI_EOU_VOICE_FRAMES     3U
#define XIAOZHI_THINKING_TIMEOUT_MS  12000U
#define XIAOZHI_TALK_HELLO_WAIT_MS   8000U
#define VOICE_IPC_DRAIN_MAX_PER_LOOP 8U
#define XIAOZHI_PCM_60MS_BYTES       XIAOZHI_AUDIO_FRAME_BYTES
#define XIAOZHI_PCM_60MS_SAMPLES     (XIAOZHI_PCM_60MS_BYTES / sizeof(int16_t))
#define XIAOZHI_OPUS_DECODE_MAX_SAMPLES ((48000U * XIAOZHI_AUDIO_FRAME_DURATION_MS) / 1000U)
#ifndef VOICE_SERVICE_CONNECT_DURING_INIT
#define VOICE_SERVICE_CONNECT_DURING_INIT 0
#endif
#ifndef VOICE_SERVICE_AUTO_RECONNECT_IN_THREAD
#define VOICE_SERVICE_AUTO_RECONNECT_IN_THREAD 1
#endif
#ifndef VOICE_SERVICE_ACCEPT_M33_PCM_PROBE
#define VOICE_SERVICE_ACCEPT_M33_PCM_PROBE 0
#endif
#define VOICE_STOP_NOTIFY_THREAD_STACK 8192

#ifdef BSP_USING_LCD
extern rt_int32_t drv_lcd_get_init_result(void);
extern rt_int32_t drv_lcd_get_gfx_status(void);
extern rt_int32_t drv_lcd_get_mipi_status(void);
extern rt_uint32_t drv_lcd_get_frame_updates(void);
extern rt_int32_t drv_lcd_get_last_frame_status(void);
#endif
#ifdef BSP_USING_LVGL
extern rt_uint32_t lv_port_disp_get_flush_count(void);
extern rt_int32_t lv_port_disp_get_last_flush_status(void);
#endif
#define VOICE_SERVICE_THREAD_STACK   24576
#define VOICE_DETECT_THREAD_STACK    65536

int sal_socket(int domain, int type, int protocol);
int sal_closesocket(int socket);
int lwip_socket(int domain, int type, int protocol);
int lwip_connect(int s, const struct sockaddr *name, socklen_t namelen);
int lwip_close(int s);
void whd_wlan_get_diag(int *stage, int *result, rt_uint32_t *flags);

#define XIAOZHI_CLOUD_PROBE_IP        "106.55.62.122"
#define XIAOZHI_CLOUD_PROBE_PORT      8011
#define VOICE_WIFI_SSID_MAX_LEN       32
#define VOICE_WIFI_PASSWORD_MAX_LEN   64
#define XIAOZHI_SESSION_ID_MAX_LEN    64
#define XIAOZHI_LOCAL_SESSION_ID      "m55"
#define XIAOZHI_BINARY_V3_HEADER_LEN  4U
#define XIAOZHI_AUDIO_FORMAT_IS_PCM \
    (rt_strcmp(XIAOZHI_AUDIO_FORMAT, "pcm_s16le") == 0)
#define XIAOZHI_PROTOCOL_USES_V3_BINARY \
    (XIAOZHI_PROTOCOL_VERSION == 3U)

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t running;
    rt_bool_t wake_listening;
    rt_bool_t asr_ready;
    rt_bool_t tts_ready;
    rt_uint32_t reconnect_tick;
    rt_thread_t thread;
    rt_thread_t detect_thread;
    struct rt_mutex lock;
    struct rt_semaphore detect_sem;
    rt_uint8_t *audio_buffer;
    rt_uint8_t *detect_buffer;
    rt_uint8_t *tts_pending_buffer;
    volatile rt_uint32_t tts_pending_len[VOICE_TTS_PENDING_SLOT_COUNT];
    volatile rt_bool_t tts_pending_is_binary[VOICE_TTS_PENDING_SLOT_COUNT];
    volatile rt_uint32_t tts_pending_read_index;
    volatile rt_uint32_t tts_pending_write_index;
    volatile rt_uint32_t tts_pending_count;
    rt_uint32_t audio_expected;
    rt_uint32_t audio_received;
    rt_bool_t m33_pcm_probe_enabled;
    rt_uint32_t m33_pcm_probe_accepted_count;
    rt_uint32_t m33_pcm_probe_ignored_count;
    rt_bool_t xiaozhi_listening_active;
    xiaozhi_wake_source_t xiaozhi_listening_source;
    rt_uint32_t xiaozhi_listening_bytes;
    rt_uint32_t xiaozhi_listening_chunks;
    rt_tick_t xiaozhi_listening_start_tick;
    rt_tick_t xiaozhi_last_voice_tick;
    rt_bool_t xiaozhi_voice_seen;
    rt_uint32_t xiaozhi_voice_seen_frames;
    rt_uint32_t xiaozhi_last_sent_bytes;
    rt_uint32_t xiaozhi_last_sent_chunks;
    rt_uint32_t xiaozhi_send_fail_count;
    rt_uint32_t xiaozhi_rx_text_count;
    rt_uint32_t xiaozhi_rx_binary_count;
    rt_uint32_t xiaozhi_tts_forward_chunks;
    rt_uint32_t xiaozhi_tts_forward_bytes;
    rt_uint32_t xiaozhi_tts_forward_fail_count;
    rt_uint32_t xiaozhi_tts_pcm_reject_count;
    rt_uint32_t xiaozhi_server_hello_count;
    rt_uint32_t xiaozhi_server_stt_count;
    rt_uint32_t xiaozhi_server_tts_start_count;
    rt_uint32_t xiaozhi_server_tts_stop_count;
    rt_uint32_t xiaozhi_server_tts_sentence_count;
    rt_uint32_t xiaozhi_server_last_type_code;
    rt_uint32_t xiaozhi_server_last_state_code;
    rt_uint32_t xiaozhi_server_last_text_lens;
    rt_uint32_t xiaozhi_server_last_error_code;
    rt_uint32_t xiaozhi_server_last_reason_code;
    rt_uint32_t xiaozhi_listen_start_count;
    rt_uint32_t xiaozhi_listen_stop_count;
    rt_int32_t xiaozhi_listen_start_result;
    rt_int32_t xiaozhi_listen_stop_result;
    rt_uint32_t service_loop_count;
    rt_uint32_t service_drain_count;
    rt_int32_t service_last_consume_ret;
    rt_uint32_t service_diag_phase;
    rt_tick_t xiaozhi_thinking_since_tick;
    rt_bool_t xiaozhi_server_hello_seen;
    char xiaozhi_listening_session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    rt_uint8_t xiaozhi_audio_frame[XIAOZHI_AUDIO_FRAME_BYTES];
    rt_uint32_t xiaozhi_audio_frame_len;
    rt_uint32_t latest_pcm_len;
    rt_uint32_t latest_pcm_seq;
    rt_bool_t latest_pcm_pending;
    rt_uint32_t wake_hit_streak;
    rt_uint32_t wake_skip_windows;
    rt_tick_t wake_last_trigger_tick;
    rt_uint32_t submitted_frames;
    rt_uint32_t processed_windows;
    rt_uint32_t detected_count;
    rt_uint32_t latest_peak;
    rt_uint32_t latest_avg_abs;
    rt_uint32_t latest_active_frames;
    rt_uint32_t latest_total_frames;
    rt_int32_t last_error;
    char xiaozhi_session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    rt_int32_t net_probe_posix_tcp;
    rt_int32_t net_probe_posix_errno;
    rt_int32_t net_probe_sal_tcp;
    rt_int32_t net_probe_sal_errno;
    rt_int32_t net_probe_lwip_tcp;
    rt_int32_t net_probe_lwip_errno;
    rt_uint32_t netdev_flags;
    rt_uint32_t netdev_ip;
    rt_uint32_t netdev_gw;
    rt_uint32_t netdev_mask;
    rt_uint32_t netdev_dns0;
    rt_int32_t cloud_tcp_result;
    rt_int32_t cloud_tcp_errno;
    rt_uint32_t wlan_connected;
    rt_uint32_t wlan_ready;
    rt_int32_t wlan_rssi;
    rt_int32_t wifi_diag_result;
    rt_int32_t wifi_scan_count;
    rt_int32_t whd_stage;
    rt_int32_t whd_result;
    rt_uint32_t whd_flags;
    char netdev_name[RT_NAME_MAX];
    char wifi_ssid[VOICE_WIFI_SSID_MAX_LEN + 1];
    char wifi_password[VOICE_WIFI_PASSWORD_MAX_LEN + 1];
} voice_service_t;

typedef struct
{
    rt_bool_t speech;
    rt_uint32_t peak;
    rt_uint32_t avg_abs;
    rt_uint32_t active_frames;
    rt_uint32_t total_frames;
    rt_uint32_t zcr_permille;
} voice_model_result_t;

static void voice_service_stop_xiaozhi_listening(rt_bool_t notify_server);
static rt_err_t voice_service_stop_xiaozhi_listening_async(void);
static rt_bool_t voice_service_take_xiaozhi_listening(char *session_id,
                                                      rt_size_t session_id_len,
                                                      xiaozhi_wake_source_t *wake_source,
                                                      rt_uint32_t *bytes,
                                                      rt_uint32_t *chunks);
static rt_err_t voice_service_send_xiaozhi_listen_stop(const char *session_id,
                                                       xiaozhi_wake_source_t wake_source,
                                                       rt_uint32_t bytes,
                                                       rt_uint32_t chunks);
static rt_err_t voice_service_publish_status(void);
static void voice_service_drain_ipc_messages(void);
static void xiaozhi_feedback_beep(rt_uint32_t duration_ms);
static const char *voice_service_public_wake_word(const char *wake_word);
static rt_err_t voice_service_send_control(voice_control_cmd_t cmd);
static rt_bool_t voice_service_wait_xiaozhi_hello(rt_uint32_t timeout_ms);
static void voice_service_flush_xiaozhi_tail_frame(void);

static voice_service_t g_service;

static rt_uint32_t voice_service_text_code4(const char *text)
{
    rt_uint32_t code = 0U;
    rt_size_t i;

    if (text == RT_NULL)
    {
        return 0U;
    }

    for (i = 0; (i < 4U) && (text[i] != '\0'); i++)
    {
        code |= ((rt_uint32_t)(rt_uint8_t)text[i]) << (i * 8U);
    }

    return code;
}

static rt_uint32_t voice_service_server_hint_code4(const char *message,
                                                   const char *type,
                                                   const char *state,
                                                   const char *error,
                                                   const char *content,
                                                   const char *speak)
{
    if ((error != RT_NULL) && (error[0] != '\0'))
    {
        return voice_service_text_code4("err");
    }
    if ((type != RT_NULL) && (type[0] != '\0'))
    {
        return voice_service_text_code4(type);
    }
    if ((state != RT_NULL) && (state[0] != '\0'))
    {
        return voice_service_text_code4(state);
    }
    if ((speak != RT_NULL) && (speak[0] != '\0'))
    {
        return voice_service_text_code4("spk");
    }
    if ((content != RT_NULL) && (content[0] != '\0'))
    {
        return voice_service_text_code4("msg");
    }
    if (message != RT_NULL)
    {
        if (rt_strstr(message, "\"stt\"") != RT_NULL)
        {
            return voice_service_text_code4("stt");
        }
        if (rt_strstr(message, "\"tts\"") != RT_NULL)
        {
            return voice_service_text_code4("tts");
        }
        if (rt_strstr(message, "\"listen\"") != RT_NULL)
        {
            return voice_service_text_code4("list");
        }
        if (rt_strstr(message, "\"goodbye\"") != RT_NULL)
        {
            return voice_service_text_code4("bye");
        }
        if (rt_strstr(message, "\"abort\"") != RT_NULL)
        {
            return voice_service_text_code4("abor");
        }
    }

    return 0U;
}

static const char *voice_service_public_wake_word(const char *wake_word)
{
    if ((wake_word == RT_NULL) || (wake_word[0] == '\0') ||
        (rt_strcmp(wake_word, "xiaorui") == 0) ||
        (rt_strcmp(wake_word, "Okay Infineon") == 0) ||
        (rt_strcmp(wake_word, "OK Infineon") == 0))
    {
        return "小瑞";
    }

    return wake_word;
}

static rt_bool_t voice_service_wait_xiaozhi_hello(rt_uint32_t timeout_ms)
{
    rt_tick_t deadline = rt_tick_get() + rt_tick_from_millisecond(timeout_ms);

    while ((rt_int32_t)(deadline - rt_tick_get()) > 0)
    {
        rt_bool_t hello_seen;

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        hello_seen = g_service.xiaozhi_server_hello_seen;
        rt_mutex_release(&g_service.lock);
        if (hello_seen)
        {
            return RT_TRUE;
        }
        rt_thread_mdelay(50);
    }

    return RT_FALSE;
}

static void voice_service_mark_xiaozhi_thinking(const char *detail)
{
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_thinking_since_tick = rt_tick_get();
    rt_mutex_release(&g_service.lock);
    xiaozhi_ui_state_set(XIAOZHI_UI_THINKING,
                         (detail && detail[0]) ? detail : "正在思考",
                         RT_EOK);
}

static void voice_service_clear_xiaozhi_thinking(void)
{
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_thinking_since_tick = 0U;
    rt_mutex_release(&g_service.lock);
}

static void voice_service_check_xiaozhi_thinking_timeout(void)
{
    rt_tick_t thinking_since;
    rt_tick_t now;

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    thinking_since = g_service.xiaozhi_thinking_since_tick;
    rt_mutex_release(&g_service.lock);

    if (thinking_since == 0U)
    {
        return;
    }

    now = rt_tick_get();
    if ((rt_uint32_t)((now - thinking_since) * 1000U / RT_TICK_PER_SECOND) <= XIAOZHI_THINKING_TIMEOUT_MS)
    {
        return;
    }

    rt_kprintf("[voice_service] Xiaozhi thinking timeout stage=%d errno=%d ws=%d last=0x%08lx/0x%08lx rx=%lu/%lu tts=%lu/%lu/%lu fwd=%lu/%lu fail=%lu\n",
               websocket_client_last_stage(),
               websocket_client_last_errno(),
               websocket_client_is_connected() ? 1 : 0,
               (unsigned long)g_service.xiaozhi_server_last_type_code,
               (unsigned long)g_service.xiaozhi_server_last_state_code,
               (unsigned long)g_service.xiaozhi_rx_text_count,
               (unsigned long)g_service.xiaozhi_rx_binary_count,
               (unsigned long)g_service.xiaozhi_server_tts_start_count,
               (unsigned long)g_service.xiaozhi_server_tts_stop_count,
               (unsigned long)g_service.xiaozhi_server_tts_sentence_count,
               (unsigned long)g_service.xiaozhi_tts_forward_chunks,
               (unsigned long)g_service.xiaozhi_tts_forward_bytes,
               (unsigned long)g_service.xiaozhi_tts_forward_fail_count);

    voice_service_clear_xiaozhi_thinking();
    xiaozhi_ui_state_set(XIAOZHI_UI_READY, "平台无回复，请重试", -RT_ETIMEOUT);
    (void)voice_service_publish_status();
}

static void xiaozhi_feedback_beep(rt_uint32_t duration_ms)
{
    (void)official_voice_speaker_beep(duration_ms);
}

static void voice_service_refresh_netdev_snapshot_locked(void)
{
    struct netdev *netdev = netdev_default;

    g_service.wlan_connected = rt_wlan_is_connected() ? 1U : 0U;
    g_service.wlan_ready = rt_wlan_is_ready() ? 1U : 0U;
    g_service.wlan_rssi = rt_wlan_get_rssi();

    if (netdev == RT_NULL)
    {
        netdev = netdev_get_first_by_flags(NETDEV_FLAG_UP);
    }
    if (netdev == RT_NULL)
    {
        netdev = netdev_get_first_by_flags(NETDEV_FLAG_LINK_UP);
    }

    if (netdev == RT_NULL)
    {
        g_service.netdev_flags = 0;
        g_service.netdev_ip = 0;
        g_service.netdev_gw = 0;
        g_service.netdev_mask = 0;
        g_service.netdev_dns0 = 0;
        g_service.netdev_name[0] = '\0';
        return;
    }

    rt_memset(g_service.netdev_name, 0, sizeof(g_service.netdev_name));
    rt_strncpy(g_service.netdev_name, netdev->name, sizeof(g_service.netdev_name) - 1);
    g_service.netdev_flags = netdev->flags;
    g_service.netdev_ip = ip4_addr_get_u32(&netdev->ip_addr);
    g_service.netdev_gw = ip4_addr_get_u32(&netdev->gw);
    g_service.netdev_mask = ip4_addr_get_u32(&netdev->netmask);
    g_service.netdev_dns0 = ip4_addr_get_u32(&netdev->dns_servers[0]);
}

static rt_err_t voice_service_publish_status(void)
{
    m33_m55_message_t msg;
    rt_size_t heap_total = 0;
    rt_size_t heap_used = 0;
    rt_size_t heap_max_used = 0;

    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_STATUS;

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    msg.payload.voice_status.flags =
        (g_service.wake_listening ? VOICE_STATUS_FLAG_WAKE_LISTENING : 0U) |
        (xiaozhi_wake_engine_is_ready() ? VOICE_STATUS_FLAG_WAKE_READY : 0U) |
        (g_service.wake_last_trigger_tick != 0U ? VOICE_STATUS_FLAG_LAST_WAKE : 0U) |
        (g_service.xiaozhi_listening_active ? VOICE_STATUS_FLAG_XIAOZHI_LISTENING : 0U) |
        (websocket_client_is_connected() ? VOICE_STATUS_FLAG_XIAOZHI_CONNECTED : 0U) |
        (xiaozhi_voice_relay_has_token() ? VOICE_STATUS_FLAG_XIAOZHI_HAS_TOKEN : 0U);
    msg.payload.voice_status.submitted_frames = g_service.submitted_frames;
    msg.payload.voice_status.processed_windows = g_service.processed_windows;
    msg.payload.voice_status.detected_count = g_service.detected_count;
    msg.payload.voice_status.latest_pcm_seq = g_service.latest_pcm_seq;
    msg.payload.voice_status.latest_pcm_len = g_service.latest_pcm_len;
    msg.payload.voice_status.latest_peak = g_service.latest_peak;
    msg.payload.voice_status.latest_avg_abs = g_service.latest_avg_abs;
    msg.payload.voice_status.latest_active_frames = g_service.latest_active_frames;
    msg.payload.voice_status.latest_total_frames = g_service.latest_total_frames;
    msg.payload.voice_status.last_wake_tick = (rt_uint32_t)g_service.wake_last_trigger_tick;
    msg.payload.voice_status.wake_stage = (rt_uint32_t)xiaozhi_wake_engine_stage();
    msg.payload.voice_status.last_error = (g_service.last_error < 0) ?
        g_service.last_error :
        ((xiaozhi_wake_engine_last_feature_source() == 2) ?
            -(300000 +
              ((xiaozhi_wake_engine_last_alloc_fail_source() + 20) * 10000) +
              ((xiaozhi_wake_engine_last_alloc_fail_size() / 16) % 10000)) :
            (xiaozhi_wake_engine_last_feature_source() * 1000000 +
             xiaozhi_wake_engine_last_noise_permille() * 1000 +
             xiaozhi_wake_engine_last_confidence_permille()));
    msg.payload.voice_status.xiaozhi_ws_stage = websocket_client_last_stage();
    msg.payload.voice_status.xiaozhi_ws_errno = websocket_client_last_errno();
    msg.payload.voice_status.xiaozhi_token_len = (rt_uint32_t)xiaozhi_voice_relay_token_len();
    msg.payload.voice_status.xiaozhi_token_staging_len = (rt_uint32_t)xiaozhi_voice_relay_token_staging_len();
    msg.payload.voice_status.xiaozhi_listening_bytes = g_service.xiaozhi_listening_bytes;
    msg.payload.voice_status.xiaozhi_listening_chunks = g_service.xiaozhi_listening_chunks;
    msg.payload.voice_status.xiaozhi_last_sent_bytes = g_service.xiaozhi_last_sent_bytes;
    msg.payload.voice_status.xiaozhi_last_sent_chunks = g_service.xiaozhi_last_sent_chunks;
    msg.payload.voice_status.xiaozhi_send_fail_count = g_service.xiaozhi_send_fail_count;
    msg.payload.voice_status.xiaozhi_rx_text_count = g_service.xiaozhi_rx_text_count;
    msg.payload.voice_status.xiaozhi_rx_binary_count = g_service.xiaozhi_rx_binary_count;
    msg.payload.voice_status.xiaozhi_audio_frame_len = g_service.xiaozhi_audio_frame_len;
    msg.payload.voice_status.xiaozhi_tts_forward_chunks = g_service.xiaozhi_tts_forward_chunks;
    msg.payload.voice_status.xiaozhi_tts_forward_bytes = g_service.xiaozhi_tts_forward_bytes;
    msg.payload.voice_status.xiaozhi_tts_forward_fail_count = g_service.xiaozhi_tts_forward_fail_count;
    msg.payload.voice_status.xiaozhi_tts_pcm_reject_count = g_service.xiaozhi_tts_pcm_reject_count;
    msg.payload.voice_status.xiaozhi_server_hello_count = g_service.xiaozhi_server_hello_count;
    msg.payload.voice_status.xiaozhi_server_stt_count = g_service.xiaozhi_server_stt_count;
    msg.payload.voice_status.xiaozhi_server_tts_start_count = g_service.xiaozhi_server_tts_start_count;
    msg.payload.voice_status.xiaozhi_server_tts_stop_count = g_service.xiaozhi_server_tts_stop_count;
    msg.payload.voice_status.xiaozhi_server_tts_sentence_count = g_service.xiaozhi_server_tts_sentence_count;
    msg.payload.voice_status.xiaozhi_server_last_type_code = g_service.xiaozhi_server_last_type_code;
    msg.payload.voice_status.xiaozhi_server_last_state_code = g_service.xiaozhi_server_last_state_code;
    msg.payload.voice_status.xiaozhi_server_last_text_lens = g_service.xiaozhi_server_last_text_lens;
    msg.payload.voice_status.xiaozhi_server_last_error_code = g_service.xiaozhi_server_last_error_code;
    msg.payload.voice_status.xiaozhi_server_last_reason_code = g_service.xiaozhi_server_last_reason_code;
    if ((g_service.xiaozhi_server_stt_count == 0U) &&
        (g_service.xiaozhi_server_tts_start_count == 0U) &&
        (g_service.xiaozhi_server_tts_stop_count == 0U))
    {
        msg.payload.voice_status.xiaozhi_server_last_text_lens =
            ((g_service.xiaozhi_listen_start_count & 0x3ffU) |
             ((g_service.xiaozhi_listen_stop_count & 0x3ffU) << 10U) |
             (((rt_uint32_t)g_service.xiaozhi_listen_start_result & 0x3ffU) << 20U));
        msg.payload.voice_status.xiaozhi_server_last_error_code =
            (((rt_uint32_t)g_service.xiaozhi_listen_stop_result & 0xffffU) |
             (msg.payload.voice_status.xiaozhi_server_last_error_code & 0xffff0000U));
    }
    rt_memory_info(&heap_total, &heap_used, &heap_max_used);
    msg.payload.voice_status.heap_total = (rt_uint32_t)heap_total;
    msg.payload.voice_status.heap_used = (rt_uint32_t)heap_used;
    msg.payload.voice_status.heap_max_used = (rt_uint32_t)heap_max_used;
    msg.payload.voice_status.net_probe_posix_tcp = (rt_int32_t)g_service.service_loop_count;
    msg.payload.voice_status.net_probe_posix_errno = (rt_int32_t)g_service.service_drain_count;
    msg.payload.voice_status.net_probe_sal_tcp = g_service.service_last_consume_ret;
    msg.payload.voice_status.net_probe_sal_errno = (rt_int32_t)g_service.service_diag_phase;
    msg.payload.voice_status.net_probe_lwip_tcp = (rt_int32_t)g_service.m33_pcm_probe_accepted_count;
    msg.payload.voice_status.net_probe_lwip_errno = (rt_int32_t)g_service.m33_pcm_probe_ignored_count;
    msg.payload.voice_status.netdev_flags = g_service.netdev_flags;
    msg.payload.voice_status.netdev_ip = g_service.netdev_ip;
    msg.payload.voice_status.netdev_gw = g_service.netdev_gw;
    msg.payload.voice_status.netdev_mask = g_service.netdev_mask;
    msg.payload.voice_status.netdev_dns0 = g_service.netdev_dns0;
    msg.payload.voice_status.cloud_tcp_result = g_service.cloud_tcp_result;
    msg.payload.voice_status.cloud_tcp_errno = g_service.cloud_tcp_errno;
    msg.payload.voice_status.wlan_connected = g_service.wlan_connected;
    msg.payload.voice_status.wlan_ready = g_service.wlan_ready;
    msg.payload.voice_status.wlan_rssi = g_service.wlan_rssi;
    msg.payload.voice_status.wifi_diag_result = g_service.wifi_diag_result;
    msg.payload.voice_status.wifi_scan_count = g_service.wifi_scan_count;
    msg.payload.voice_status.whd_stage = g_service.whd_stage;
    msg.payload.voice_status.whd_result = g_service.whd_result;
    msg.payload.voice_status.whd_flags = g_service.whd_flags;
#ifdef BSP_USING_LCD
    msg.payload.voice_status.lcd_init_result = drv_lcd_get_init_result();
    msg.payload.voice_status.lcd_gfx_status = drv_lcd_get_gfx_status();
    msg.payload.voice_status.lcd_mipi_status = drv_lcd_get_mipi_status();
    msg.payload.voice_status.lcd_frame_updates = drv_lcd_get_frame_updates();
    msg.payload.voice_status.lcd_last_frame_status = drv_lcd_get_last_frame_status();
#else
    msg.payload.voice_status.lcd_init_result = -RT_ENOSYS;
    msg.payload.voice_status.lcd_gfx_status = -RT_ENOSYS;
    msg.payload.voice_status.lcd_mipi_status = -RT_ENOSYS;
    msg.payload.voice_status.lcd_frame_updates = 0U;
    msg.payload.voice_status.lcd_last_frame_status = -RT_ENOSYS;
#endif
#ifdef BSP_USING_LVGL
    msg.payload.voice_status.lvgl_flush_count = lv_port_disp_get_flush_count();
    msg.payload.voice_status.lvgl_last_flush_status = lv_port_disp_get_last_flush_status();
#else
    msg.payload.voice_status.lvgl_flush_count = 0U;
    msg.payload.voice_status.lvgl_last_flush_status = -RT_ENOSYS;
#endif
    wifi_config_fill_voice_status(&msg.payload.voice_status);
    rt_mutex_release(&g_service.lock);

    return m33_m55_comm_publish(&msg);
}

rt_err_t voice_service_publish_status_now(void)
{
    return voice_service_publish_status();
}

void voice_service_note_error(rt_err_t error)
{
    if (!g_service.initialized)
    {
        return;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.last_error = error;
    rt_mutex_release(&g_service.lock);
    (void)voice_service_publish_status();
}

static rt_err_t voice_service_set_wake_listening(rt_bool_t enable)
{
    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.wake_listening = enable;
    if (!enable)
    {
        g_service.latest_pcm_pending = RT_FALSE;
        g_service.wake_hit_streak = 0;
        g_service.wake_skip_windows = 0;
    }
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] wake listening=%d backend=%s ready=%d\n",
               enable ? 1 : 0,
               xiaozhi_wake_engine_backend_name(),
               xiaozhi_wake_engine_is_ready() ? 1 : 0);
    return RT_EOK;
}

rt_err_t voice_service_set_wake_listening_direct(rt_bool_t enable)
{
    return voice_service_set_wake_listening(enable);
}

static voice_model_result_t voice_service_model_entry(const uint8_t *audio_data, uint32_t len)
{
    const int16_t *samples = (const int16_t *)audio_data;
    voice_model_result_t result;
    uint32_t sample_count;
    const uint32_t frame_samples = 320U;
    uint32_t i;
    uint64_t energy = 0;
    uint32_t crossings = 0;

    rt_memset(&result, 0, sizeof(result));

    if ((audio_data == RT_NULL) || (len < 2U))
    {
        return result;
    }

    sample_count = len / sizeof(int16_t);
    for (i = 0; i < sample_count; i++)
    {
        int32_t s = samples[i];
        uint32_t mag = (s < 0) ? (uint32_t)(-s) : (uint32_t)s;
        if (mag > result.peak)
        {
            result.peak = mag;
        }
        energy += (uint64_t)mag;
        if ((i > 0U) &&
            (((samples[i - 1] < 0) && (samples[i] >= 0)) ||
             ((samples[i - 1] >= 0) && (samples[i] < 0))))
        {
            crossings++;
        }
    }

    result.avg_abs = sample_count ? (rt_uint32_t)(energy / sample_count) : 0U;
    result.total_frames = (sample_count + frame_samples - 1U) / frame_samples;
    result.zcr_permille = sample_count ? (crossings * 1000U) / sample_count : 0U;

    for (i = 0; i < sample_count; i += frame_samples)
    {
        uint32_t j;
        uint32_t end = i + frame_samples;
        uint64_t frame_energy = 0;

        if (end > sample_count)
        {
            end = sample_count;
        }

        for (j = i; j < end; j++)
        {
            int32_t s = samples[j];
            frame_energy += (uint32_t)((s < 0) ? (-s) : s);
        }

        if ((end > i) && ((frame_energy / (end - i)) > 700U))
        {
            result.active_frames++;
        }
    }

    result.speech = (result.peak > 2500U) &&
                    (result.avg_abs > 180U) &&
                    (result.active_frames >= 8U) &&
                    (result.zcr_permille > 5U);

    return result;
}

static rt_bool_t json_get_string(const char *body, const char *key, char *out, rt_size_t out_size)
{
    char pattern[32];
    const char *cursor;
    const char *start;
    const char *end;
    rt_size_t len;

    if (!body || !key || !out || out_size == 0)
    {
        return RT_FALSE;
    }

    rt_snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    cursor = rt_strstr(body, pattern);
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor++;
    while ((*cursor == ' ') || (*cursor == '\t'))
    {
        cursor++;
    }

    if (*cursor != '"')
    {
        return RT_FALSE;
    }

    start = ++cursor;
    end = strchr(start, '"');
    if (!end)
    {
        return RT_FALSE;
    }

    len = (rt_size_t)(end - start);
    if (len >= out_size)
    {
        len = out_size - 1;
    }

    rt_memcpy(out, start, len);
    out[len] = '\0';
    return RT_TRUE;
}

static void json_escape_text(const char *src, char *dst, rt_size_t dst_size)
{
    rt_size_t used = 0;

    if (!dst || dst_size == 0)
    {
        return;
    }

    while (src && *src && (used + 2) < dst_size)
    {
        if ((*src == '\\') || (*src == '"'))
        {
            if ((used + 2) >= dst_size)
            {
                break;
            }
            dst[used++] = '\\';
        }
        else if (*src == '\r' || *src == '\n')
        {
            dst[used++] = ' ';
            src++;
            continue;
        }

        dst[used++] = *src++;
    }

    dst[used] = '\0';
}

static rt_bool_t json_get_uint(const char *body, const char *key, rt_uint32_t *out)
{
    char pattern[32];
    const char *cursor;
    rt_uint32_t value = 0U;
    rt_bool_t found_digit = RT_FALSE;

    if (!body || !key || !out)
    {
        return RT_FALSE;
    }

    rt_snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    cursor = rt_strstr(body, pattern);
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }
    cursor++;

    while ((*cursor == ' ') || (*cursor == '\t'))
    {
        cursor++;
    }

    while ((*cursor >= '0') && (*cursor <= '9'))
    {
        found_digit = RT_TRUE;
        value = (value * 10U) + (rt_uint32_t)(*cursor - '0');
        cursor++;
    }

    if (!found_digit)
    {
        return RT_FALSE;
    }

    *out = value;
    return RT_TRUE;
}

static void voice_service_publish_text_to_m33(m33_m55_msg_type_t type, const char *text)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = type;
    if (text)
    {
        rt_strncpy(msg.payload.text.text, text, sizeof(msg.payload.text.text) - 1);
        msg.payload.text.text[sizeof(msg.payload.text.text) - 1] = '\0';
    }

    if (m33_m55_comm_publish(&msg) != RT_EOK)
    {
        rt_kprintf("[voice_service] publish text to M33 failed\n");
    }
}

static void voice_service_log_payload_head(const char *prefix,
                                           const uint8_t *payload,
                                           rt_size_t payload_len)
{
    rt_size_t inspect_len;

    if ((prefix == RT_NULL) || (payload == RT_NULL))
    {
        return;
    }

    inspect_len = payload_len > 16U ? 16U : payload_len;
    rt_kprintf("%s len=%lu head=", prefix, (unsigned long)payload_len);
    for (rt_size_t i = 0; i < inspect_len; i++)
    {
        rt_kprintf("%02x", payload[i]);
        if ((i + 1U) < inspect_len)
        {
            rt_kprintf(" ");
        }
    }
    rt_kprintf("\n");
}

static rt_bool_t voice_service_audio_looks_like_pcm16(const uint8_t *audio_data, uint32_t len)
{
    const int16_t *samples = (const int16_t *)audio_data;
    uint32_t sample_count;
    uint32_t inspect_samples;
    uint32_t peak = 0U;
    uint64_t sum = 0U;

    if ((audio_data == RT_NULL) || (len < 320U) || ((len & 1U) != 0U))
    {
        return RT_FALSE;
    }

    /*
     * Xiaozhi official websocket audio is Opus. Only pass through binary
     * packets that are plausibly raw PCM, otherwise the speaker emits noise.
     */
    if ((len != XIAOZHI_PCM_60MS_BYTES) &&
        ((len % XIAOZHI_PCM_60MS_BYTES) != 0U) &&
        (len < 1024U))
    {
        return RT_FALSE;
    }

    sample_count = len / sizeof(int16_t);
    inspect_samples = sample_count > 960U ? 960U : sample_count;
    for (uint32_t i = 0; i < inspect_samples; i++)
    {
        int32_t s = samples[i];
        uint32_t mag = (s < 0) ? (uint32_t)(-s) : (uint32_t)s;
        if (mag > peak)
        {
            peak = mag;
        }
        sum += mag;
    }

    /*
     * Cloud XiaoZhi TTS frames are sent as fixed 60 ms PCM chunks today and
     * the first chunk can be near-silent. Accept exact frame-sized silence so
     * the reply stream is not dropped before the audible samples arrive.
     */
    if ((len == XIAOZHI_PCM_60MS_BYTES) || ((len % XIAOZHI_PCM_60MS_BYTES) == 0U))
    {
        return ((sum / inspect_samples) < 18000U) ? RT_TRUE : RT_FALSE;
    }

    return (peak > 8U) && ((sum / inspect_samples) < 18000U);
}

static void voice_service_strip_v3_audio_header(const uint8_t **audio_data, rt_size_t *len)
{
    const uint8_t *payload;
    rt_size_t payload_len;
    rt_size_t framed_len;

    if ((audio_data == RT_NULL) || (len == RT_NULL) || (*audio_data == RT_NULL))
    {
        return;
    }

    payload = *audio_data;
    payload_len = *len;
    if (payload_len < XIAOZHI_BINARY_V3_HEADER_LEN)
    {
        return;
    }

    framed_len = ((rt_size_t)payload[2] << 8) | payload[3];
    if ((payload[0] == 0U) &&
        (payload[1] == 0U) &&
        (framed_len > 0U) &&
        ((framed_len + XIAOZHI_BINARY_V3_HEADER_LEN) <= payload_len))
    {
        *audio_data = payload + XIAOZHI_BINARY_V3_HEADER_LEN;
        *len = framed_len;
    }
}

static rt_bool_t voice_service_payload_has_v3_audio_header(const uint8_t *payload, rt_size_t len)
{
    rt_size_t framed_len;

    if ((payload == RT_NULL) || (len < XIAOZHI_BINARY_V3_HEADER_LEN))
    {
        return RT_FALSE;
    }

    framed_len = ((rt_size_t)payload[2] << 8) | payload[3];
    return ((payload[0] == 0U) &&
            (payload[1] == 0U) &&
            (framed_len > 0U) &&
            ((framed_len + XIAOZHI_BINARY_V3_HEADER_LEN) <= len)) ? RT_TRUE : RT_FALSE;
}

static rt_bool_t voice_service_stream_pcm_to_m33(const uint8_t *audio_data,
                                                uint32_t len,
                                                rt_bool_t validate_raw_packet)
{
    m33_m55_message_t msg;
    uint32_t sent = 0;
    uint32_t chunk_index = 0;
    uint32_t payload_offset = 0;

    if (!audio_data || len == 0)
    {
        return RT_FALSE;
    }

    if ((len > 44) && (rt_memcmp(audio_data, "RIFF", 4) == 0))
    {
        payload_offset = 44;
    }

    if (validate_raw_packet &&
        !voice_service_audio_looks_like_pcm16(audio_data + payload_offset, len - payload_offset))
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_tts_pcm_reject_count++;
        rt_mutex_release(&g_service.lock);
        rt_kprintf("[voice_service] binary audio is not raw pcm16; skip speaker len=%lu head=%02x %02x %02x %02x\n",
                   (unsigned long)len,
                   len > 0U ? audio_data[0] : 0U,
                   len > 1U ? audio_data[1] : 0U,
                   len > 2U ? audio_data[2] : 0U,
                   len > 3U ? audio_data[3] : 0U);
        return RT_FALSE;
    }

    while ((payload_offset + sent) < len)
    {
        uint32_t remaining = len - payload_offset - sent;
        uint32_t chunk_len = remaining > AUDIO_CHUNK_SIZE ? AUDIO_CHUNK_SIZE : remaining;

        g_service.service_diag_phase = 40U;
        voice_service_drain_ipc_messages();

        rt_memset(&msg, 0, sizeof(msg));
        msg.type = MSG_TYPE_TTS_AUDIO;
        msg.payload.audio_data.total_len = len - payload_offset;
        msg.payload.audio_data.chunk_index = chunk_index++;
        msg.payload.audio_data.chunk_len = chunk_len;
        rt_memcpy(msg.payload.audio_data.data, audio_data + payload_offset + sent, chunk_len);

        if ((msg.payload.audio_data.chunk_index < 3U) || ((msg.payload.audio_data.chunk_index % 20U) == 0U))
        {
            rt_kprintf("[voice_service] tts->m33 chunk=%lu len=%lu total=%lu head=%02x %02x %02x %02x\n",
                       (unsigned long)msg.payload.audio_data.chunk_index,
                       (unsigned long)chunk_len,
                       (unsigned long)msg.payload.audio_data.total_len,
                       chunk_len > 0U ? msg.payload.audio_data.data[0] : 0U,
                       chunk_len > 1U ? msg.payload.audio_data.data[1] : 0U,
                       chunk_len > 2U ? msg.payload.audio_data.data[2] : 0U,
                       chunk_len > 3U ? msg.payload.audio_data.data[3] : 0U);
        }

        rt_err_t publish_ret = -RT_ERROR;
        for (uint32_t retry = 0U; retry <= VOICE_TTS_PUBLISH_RETRY_COUNT; retry++)
        {
            publish_ret = m33_m55_comm_publish(&msg);
            if (publish_ret == RT_EOK)
            {
                break;
            }
            rt_thread_mdelay(VOICE_TTS_PUBLISH_RETRY_MS);
            voice_service_drain_ipc_messages();
        }

        if (publish_ret != RT_EOK)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_tts_forward_fail_count++;
            rt_mutex_release(&g_service.lock);
            rt_kprintf("[voice_service] publish TTS chunk failed at %lu ret=%d\n",
                       (unsigned long)msg.payload.audio_data.chunk_index,
                       publish_ret);
            g_service.service_diag_phase = 43U;
            voice_service_drain_ipc_messages();
            return RT_FALSE;
        }

        g_service.service_diag_phase = 41U;
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_tts_forward_chunks++;
        g_service.xiaozhi_tts_forward_bytes += chunk_len;
        rt_mutex_release(&g_service.lock);
        sent += chunk_len;
        rt_thread_mdelay(VOICE_TTS_CHUNK_GAP_MS);
        g_service.service_diag_phase = 42U;
        voice_service_drain_ipc_messages();
    }

    return ((payload_offset + sent) >= len) ? RT_TRUE : RT_FALSE;
}

static rt_bool_t voice_service_decode_opus_to_m33(const uint8_t *opus_data, uint32_t len)
{
    int16_t pcm[XIAOZHI_OPUS_DECODE_MAX_SAMPLES];
    int16_t pcm16[XIAOZHI_PCM_60MS_SAMPLES];
    rt_size_t pcm_samples = 0U;
    rt_err_t ret;
    int decoder_rate;
    rt_size_t out_samples;
    rt_size_t i;

    ret = xiaozhi_opus_decoder_decode(opus_data,
                                      len,
                                      pcm,
                                      sizeof(pcm) / sizeof(pcm[0]),
                                      &pcm_samples);
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] opus decode failed ret=%d len=%lu head=%02x %02x %02x %02x\n",
                   ret,
                   (unsigned long)len,
                   len > 0U ? opus_data[0] : 0U,
                   len > 1U ? opus_data[1] : 0U,
                   len > 2U ? opus_data[2] : 0U,
                   len > 3U ? opus_data[3] : 0U);
        return RT_FALSE;
    }

    decoder_rate = xiaozhi_opus_decoder_sample_rate();
    if (decoder_rate == (int)XIAOZHI_AUDIO_SAMPLE_RATE)
    {
        return voice_service_stream_pcm_to_m33((const uint8_t *)pcm,
                                               (uint32_t)(pcm_samples * sizeof(pcm[0])),
                                               RT_FALSE);
    }

    out_samples = ((rt_size_t)pcm_samples * XIAOZHI_AUDIO_SAMPLE_RATE) / (rt_size_t)decoder_rate;
    if (out_samples > (sizeof(pcm16) / sizeof(pcm16[0])))
    {
        out_samples = sizeof(pcm16) / sizeof(pcm16[0]);
    }

    for (i = 0; i < out_samples; i++)
    {
        rt_size_t src_index = (i * (rt_size_t)decoder_rate) / XIAOZHI_AUDIO_SAMPLE_RATE;
        if (src_index >= pcm_samples)
        {
            src_index = pcm_samples - 1U;
        }
        pcm16[i] = pcm[src_index];
    }

    rt_kprintf("[voice_service] opus downsample sr=%d samples=%lu->%lu\n",
               decoder_rate,
               (unsigned long)pcm_samples,
               (unsigned long)out_samples);
    return voice_service_stream_pcm_to_m33((const uint8_t *)pcm16,
                                           (uint32_t)(out_samples * sizeof(pcm16[0])),
                                           RT_FALSE);
}

static rt_bool_t voice_service_decode_v3_opus_frames_to_m33(const uint8_t *payload, uint32_t len)
{
    uint32_t offset = 0U;
    uint32_t frames = 0U;
    rt_bool_t streamed_any = RT_FALSE;

    while ((offset + XIAOZHI_BINARY_V3_HEADER_LEN) <= len)
    {
        uint32_t frame_len;
        const uint8_t *frame = payload + offset;

        if (!voice_service_payload_has_v3_audio_header(frame, (rt_size_t)(len - offset)))
        {
            break;
        }

        frame_len = (((uint32_t)frame[2] << 8) | frame[3]);
        if ((frames < 3U) || ((frames % 20U) == 0U))
        {
            rt_kprintf("[voice_service] v3 opus frame=%lu len=%lu head=%02x %02x %02x %02x\n",
                       (unsigned long)frames,
                       (unsigned long)frame_len,
                       frame_len > 0U ? frame[4] : 0U,
                       frame_len > 1U ? frame[5] : 0U,
                       frame_len > 2U ? frame[6] : 0U,
                       frame_len > 3U ? frame[7] : 0U);
        }

        if (voice_service_decode_opus_to_m33(frame + XIAOZHI_BINARY_V3_HEADER_LEN, frame_len))
        {
            streamed_any = RT_TRUE;
        }
        else
        {
            rt_kprintf("[voice_service] v3 opus frame decode failed frame=%lu len=%lu\n",
                       (unsigned long)frames,
                       (unsigned long)frame_len);
        }

        offset += XIAOZHI_BINARY_V3_HEADER_LEN + frame_len;
        frames++;
        voice_service_drain_ipc_messages();
    }

    if (frames > 0U)
    {
        rt_kprintf("[voice_service] v3 opus frames done frames=%lu consumed=%lu/%lu streamed=%d\n",
                   (unsigned long)frames,
                   (unsigned long)offset,
                   (unsigned long)len,
                   streamed_any ? 1 : 0);
    }

    return streamed_any;
}

static void voice_service_flush_audio_to_m33(void)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_TTS_AUDIO;
    msg.payload.audio_data.total_len = 0U;
    msg.payload.audio_data.chunk_index = 0xffffffffU;
    msg.payload.audio_data.chunk_len = 0U;

    if (m33_m55_comm_publish(&msg) != RT_EOK)
    {
        rt_kprintf("[voice_service] publish TTS flush failed\n");
    }
    else
    {
        rt_kprintf("[voice_service] tts->m33 flush\n");
    }
}

static void voice_service_enqueue_tts_payload(const uint8_t *payload,
                                              rt_size_t payload_len,
                                              rt_bool_t binary)
{
    rt_size_t offset = 0U;

    if ((payload == RT_NULL) || (payload_len == 0U) || (g_service.tts_pending_buffer == RT_NULL))
    {
        return;
    }

    while (offset < payload_len)
    {
        rt_uint32_t slot;
        rt_size_t chunk_len = payload_len - offset;

        if (chunk_len > VOICE_TTS_PENDING_SLOT_SIZE)
        {
            chunk_len = VOICE_TTS_PENDING_SLOT_SIZE;
        }

        if (g_service.tts_pending_count >= VOICE_TTS_PENDING_SLOT_COUNT)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_tts_forward_fail_count++;
            rt_mutex_release(&g_service.lock);
            rt_kprintf("[voice_service] TTS pending queue full drop remain=%lu total=%lu\n",
                       (unsigned long)(payload_len - offset),
                       (unsigned long)payload_len);
            return;
        }

        slot = g_service.tts_pending_write_index;
        rt_memcpy(g_service.tts_pending_buffer + (slot * VOICE_TTS_PENDING_SLOT_SIZE),
                  payload + offset,
                  chunk_len);
        g_service.tts_pending_len[slot] = (rt_uint32_t)chunk_len;
        g_service.tts_pending_is_binary[slot] = binary;
        g_service.tts_pending_write_index = (slot + 1U) % VOICE_TTS_PENDING_SLOT_COUNT;
        g_service.tts_pending_count++;
        offset += chunk_len;
    }
}

static rt_bool_t voice_service_process_pending_tts(void)
{
    rt_uint32_t len;
    rt_uint32_t slot;
    uint8_t *payload;
    rt_bool_t binary;
    rt_bool_t streamed = RT_FALSE;

    if ((g_service.tts_pending_count == 0U) || (g_service.tts_pending_buffer == RT_NULL))
    {
        return RT_FALSE;
    }

    slot = g_service.tts_pending_read_index;
    len = g_service.tts_pending_len[slot];
    binary = g_service.tts_pending_is_binary[slot];
    payload = g_service.tts_pending_buffer + (slot * VOICE_TTS_PENDING_SLOT_SIZE);

    if (binary)
    {
        if (XIAOZHI_AUDIO_FORMAT_IS_PCM)
        {
            const uint8_t *pcm_payload = payload;
            rt_size_t pcm_len = len;

            if (XIAOZHI_PROTOCOL_USES_V3_BINARY)
            {
                voice_service_strip_v3_audio_header(&pcm_payload, &pcm_len);
            }
            if ((pcm_len >= 320U) && ((pcm_len & 1U) == 0U))
            {
                streamed = voice_service_stream_pcm_to_m33(pcm_payload,
                                                           (uint32_t)pcm_len,
                                                           RT_FALSE);
            }
            else
            {
                rt_kprintf("[voice_service] short PCM binary ignored len=%lu\n",
                           (unsigned long)pcm_len);
            }
        }
        if (!streamed && XIAOZHI_PROTOCOL_USES_V3_BINARY &&
            voice_service_payload_has_v3_audio_header(payload, len))
        {
            streamed = voice_service_decode_v3_opus_frames_to_m33(payload, len);
            if (!streamed)
            {
                const uint8_t *pcm_payload = payload;
                rt_size_t pcm_len = len;

                voice_service_strip_v3_audio_header(&pcm_payload, &pcm_len);
                if ((pcm_payload != payload) &&
                    voice_service_audio_looks_like_pcm16(pcm_payload, (uint32_t)pcm_len))
                {
                    rt_kprintf("[voice_service] v3 payload fallback to pcm16 len=%lu\n",
                               (unsigned long)pcm_len);
                    streamed = voice_service_stream_pcm_to_m33(pcm_payload,
                                                               (uint32_t)pcm_len,
                                                               RT_TRUE);
                }
            }
        }
        if (!streamed && !XIAOZHI_AUDIO_FORMAT_IS_PCM)
        {
            streamed = voice_service_decode_opus_to_m33(payload, len);
        }
        if (!streamed && voice_service_audio_looks_like_pcm16(payload, len))
        {
            streamed = voice_service_stream_pcm_to_m33(payload, len, RT_TRUE);
        }
        if (!streamed)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_tts_forward_fail_count++;
            rt_mutex_release(&g_service.lock);
            rt_kprintf("[voice_service] pending binary audio stream/decode failed len=%lu\n",
                       (unsigned long)len);
        }
        else
        {
            rt_kprintf("[voice_service] pending binary audio forwarded len=%lu\n",
                       (unsigned long)len);
        }
        (void)voice_service_publish_status();
    }
    else if (voice_service_audio_looks_like_pcm16(payload, len))
    {
        streamed = voice_service_stream_pcm_to_m33(payload, len, RT_TRUE);
        if (!streamed)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_tts_forward_fail_count++;
            rt_mutex_release(&g_service.lock);
            rt_kprintf("[voice_service] pending raw pcm audio failed len=%lu\n",
                       (unsigned long)len);
        }
        else
        {
            rt_kprintf("[voice_service] pending raw pcm audio forwarded len=%lu\n",
                       (unsigned long)len);
        }
        (void)voice_service_publish_status();
    }
    else
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_tts_forward_fail_count++;
        rt_mutex_release(&g_service.lock);
        rt_kprintf("[voice_service] pending audio ignored len=%lu head=%02x %02x %02x %02x\n",
                   (unsigned long)len,
                   len > 0U ? payload[0] : 0U,
                   len > 1U ? payload[1] : 0U,
                   len > 2U ? payload[2] : 0U,
                   len > 3U ? payload[3] : 0U);
        (void)voice_service_publish_status();
    }

    g_service.tts_pending_len[slot] = 0U;
    g_service.tts_pending_is_binary[slot] = RT_FALSE;
    g_service.tts_pending_read_index = (slot + 1U) % VOICE_TTS_PENDING_SLOT_COUNT;
    if (g_service.tts_pending_count > 0U)
    {
        g_service.tts_pending_count--;
    }
    return RT_TRUE;
}

static void voice_service_send_text_to_server(const char *type, const char *text)
{
    char escaped[384];
    char json[VOICE_JSON_BUFFER_SIZE];

    if (!websocket_client_is_connected())
    {
        return;
    }

    json_escape_text(text ? text : "", escaped, sizeof(escaped));
    rt_snprintf(json, sizeof(json),
                "{\"type\":\"%s\",\"text\":\"%s\",\"source\":\"m55\",\"tick_ms\":%lu}",
                type, escaped, (unsigned long)rt_tick_get_millisecond());
    websocket_client_send_text(json);
}

static rt_err_t voice_service_configure_xiaozhi_socket(void)
{
    char headers[1024];
    rt_err_t ret;

    ret = xiaozhi_voice_relay_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    ret = xiaozhi_voice_relay_build_headers(headers, sizeof(headers));
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] xiaozhi header build failed: %d\n", ret);
        return ret;
    }

    return websocket_client_configure(xiaozhi_voice_relay_get_url(), headers);
}

static void voice_service_reset_xiaozhi_session_state(void)
{
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_server_hello_seen = RT_FALSE;
    g_service.xiaozhi_listening_active = RT_FALSE;
    g_service.xiaozhi_listening_source = XIAOZHI_WAKE_SOURCE_MANUAL;
    g_service.xiaozhi_audio_frame_len = 0;
    rt_memset(g_service.xiaozhi_session_id, 0, sizeof(g_service.xiaozhi_session_id));
    rt_memset(g_service.xiaozhi_listening_session_id, 0, sizeof(g_service.xiaozhi_listening_session_id));
    rt_mutex_release(&g_service.lock);
}

static void voice_service_send_xiaozhi_hello(void)
{
    char json[VOICE_JSON_BUFFER_SIZE];
    rt_err_t ret;

    if (!websocket_client_is_connected())
    {
        return;
    }

    if (xiaozhi_voice_relay_build_hello(json, sizeof(json)) == RT_EOK)
    {
        ret = websocket_client_send_text(json);
        if (ret == RT_EOK)
        {
            rt_kprintf("[voice_service] Xiaozhi hello sent format=%s v=%u\n",
                       XIAOZHI_AUDIO_FORMAT,
                       (unsigned)XIAOZHI_PROTOCOL_VERSION);
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智确认", RT_EOK);
        }
        else
        {
            g_service.last_error = ret;
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "小智握手发送失败", ret);
            rt_kprintf("[voice_service] Xiaozhi hello send failed ret=%d\n", ret);
        }
    }
}

static void voice_service_start_xiaozhi_listening(const char *wake_word)
{
    char json[VOICE_JSON_BUFFER_SIZE];
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    const char *public_wake_word = voice_service_public_wake_word(wake_word);

    if (!websocket_client_is_connected())
    {
        rt_kprintf("[voice_service] Xiaozhi listening deferred: websocket disconnected\n");
        xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "网络已连，等待小智", websocket_client_last_errno());
        return;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    rt_memset(session_id, 0, sizeof(session_id));
    rt_strncpy(session_id, g_service.xiaozhi_session_id, sizeof(session_id) - 1);
    rt_mutex_release(&g_service.lock);

    if (session_id[0] == '\0')
    {
        rt_bool_t hello_seen;

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        hello_seen = g_service.xiaozhi_server_hello_seen;
        rt_mutex_release(&g_service.lock);
        if (!hello_seen)
        {
            rt_kprintf("[voice_service] Xiaozhi listening deferred: no server hello yet\n");
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智会话", -RT_EEMPTY);
            return;
        }
        rt_strncpy(session_id, XIAOZHI_LOCAL_SESSION_ID, sizeof(session_id) - 1);
    }

    if (xiaozhi_voice_relay_build_listen_start(json,
                                               sizeof(json),
                                               session_id,
                                               XIAOZHI_WAKE_SOURCE_REALTIME) == RT_EOK)
    {
        rt_err_t ret = websocket_client_send_text(json);
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_listen_start_result = ret;
        if (ret == RT_EOK)
        {
            g_service.xiaozhi_listen_start_count++;
        }
        rt_mutex_release(&g_service.lock);
        if (ret != RT_EOK)
        {
            g_service.last_error = ret;
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "开始录音失败", ret);
            rt_kprintf("[voice_service] Xiaozhi listen start send failed session=%s ret=%d\n",
                       session_id,
                       ret);
            return;
        }
        rt_kprintf("[voice_service] Xiaozhi listen start sent session=%s source=wake\n", session_id);
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_listening_active = RT_TRUE;
    g_service.xiaozhi_listening_source = XIAOZHI_WAKE_SOURCE_REALTIME;
    g_service.xiaozhi_listening_bytes = 0;
    g_service.xiaozhi_listening_chunks = 0;
    g_service.xiaozhi_listening_start_tick = rt_tick_get();
    g_service.xiaozhi_last_voice_tick = g_service.xiaozhi_listening_start_tick;
    g_service.xiaozhi_voice_seen = RT_FALSE;
    g_service.xiaozhi_voice_seen_frames = 0U;
    rt_memset(g_service.xiaozhi_listening_session_id, 0, sizeof(g_service.xiaozhi_listening_session_id));
    rt_strncpy(g_service.xiaozhi_listening_session_id,
               session_id,
               sizeof(g_service.xiaozhi_listening_session_id) - 1);
    g_service.xiaozhi_audio_frame_len = 0;
    rt_mutex_release(&g_service.lock);

    xiaozhi_ui_state_mark_wake(public_wake_word);
    rt_kprintf("[voice_service] Xiaozhi listening started session=%s word=%s\n",
               session_id,
               public_wake_word);
}

static rt_err_t voice_service_start_xiaozhi_manual_listening(void)
{
    char json[VOICE_JSON_BUFFER_SIZE];
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    rt_err_t ret;

    if (!websocket_client_is_connected())
    {
        rt_kprintf("[voice_service] Xiaozhi manual listening reconnect: websocket disconnected stage=%d errno=%d\n",
                   websocket_client_last_stage(),
                   websocket_client_last_errno());
        ret = voice_service_reconnect_xiaozhi();
        if (ret != RT_EOK)
        {
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "网络已连，等待小智", ret);
            return ret;
        }
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    rt_memset(session_id, 0, sizeof(session_id));
    rt_strncpy(session_id, g_service.xiaozhi_session_id, sizeof(session_id) - 1);
    rt_mutex_release(&g_service.lock);

    if (session_id[0] == '\0')
    {
        rt_bool_t hello_seen;

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        hello_seen = g_service.xiaozhi_server_hello_seen;
        rt_mutex_release(&g_service.lock);
        if (!hello_seen)
        {
            rt_kprintf("[voice_service] Xiaozhi manual listening deferred: no server hello yet\n");
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智会话", -RT_EEMPTY);
            return -RT_EEMPTY;
        }
        rt_strncpy(session_id, XIAOZHI_LOCAL_SESSION_ID, sizeof(session_id) - 1);
    }

    ret = xiaozhi_voice_relay_build_listen_start(json,
                                                 sizeof(json),
                                                 session_id,
                                                 XIAOZHI_WAKE_SOURCE_MANUAL);
    if (ret == RT_EOK)
    {
        ret = websocket_client_send_text(json);
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_listen_start_result = ret;
        if (ret == RT_EOK)
        {
            g_service.xiaozhi_listen_start_count++;
        }
        rt_mutex_release(&g_service.lock);
        if (ret != RT_EOK)
        {
            g_service.last_error = ret;
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "开始录音失败", ret);
            rt_kprintf("[voice_service] Xiaozhi manual listen start send failed session=%s ret=%d\n",
                       session_id,
                       ret);
            return ret;
        }
        rt_kprintf("[voice_service] Xiaozhi listen start sent session=%s source=manual\n", session_id);
    }
    else
    {
        g_service.last_error = ret;
        rt_kprintf("[voice_service] Xiaozhi manual listen start build failed ret=%d\n", ret);
        return ret;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.wake_listening = RT_FALSE;
    g_service.xiaozhi_listening_active = RT_TRUE;
    g_service.xiaozhi_listening_source = XIAOZHI_WAKE_SOURCE_MANUAL;
    g_service.xiaozhi_listening_bytes = 0;
    g_service.xiaozhi_listening_chunks = 0;
    g_service.xiaozhi_listening_start_tick = rt_tick_get();
    g_service.xiaozhi_last_voice_tick = g_service.xiaozhi_listening_start_tick;
    g_service.xiaozhi_voice_seen = RT_FALSE;
    g_service.xiaozhi_voice_seen_frames = 0U;
    rt_memset(g_service.xiaozhi_listening_session_id, 0, sizeof(g_service.xiaozhi_listening_session_id));
    rt_strncpy(g_service.xiaozhi_listening_session_id,
               session_id,
               sizeof(g_service.xiaozhi_listening_session_id) - 1);
    g_service.xiaozhi_audio_frame_len = 0;
    rt_mutex_release(&g_service.lock);

    voice_service_clear_xiaozhi_thinking();
    xiaozhi_ui_state_set(XIAOZHI_UI_LISTENING, "手动录音中", RT_EOK);
    rt_kprintf("[voice_service] Xiaozhi manual listening started session=%s\n", session_id);
    return RT_EOK;
}

rt_err_t voice_service_start_xiaozhi_talk(void)
{
    rt_err_t ret;
    rt_bool_t hello_seen;

    if (!g_service.initialized || !g_service.running)
    {
        return -RT_ERROR;
    }

    if (!websocket_client_is_connected())
    {
        ret = voice_service_reconnect_xiaozhi();
        if (ret != RT_EOK)
        {
            xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "小智连接中", ret);
            return ret;
        }
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    hello_seen = g_service.xiaozhi_server_hello_seen;
    if (!hello_seen &&
        (g_service.xiaozhi_server_hello_count > 0U) &&
        websocket_client_is_connected())
    {
        g_service.xiaozhi_server_hello_seen = RT_TRUE;
        hello_seen = RT_TRUE;
        rt_kprintf("[voice_service] Xiaozhi talk using existing hello count=%lu stage=%d errno=%d\n",
                   (unsigned long)g_service.xiaozhi_server_hello_count,
                   websocket_client_last_stage(),
                   websocket_client_last_errno());
    }
    rt_mutex_release(&g_service.lock);
    if (!hello_seen)
    {
        voice_service_send_xiaozhi_hello();
        if (!voice_service_wait_xiaozhi_hello(XIAOZHI_TALK_HELLO_WAIT_MS))
        {
            rt_uint32_t hello_count;

            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            hello_seen = g_service.xiaozhi_server_hello_seen;
            hello_count = g_service.xiaozhi_server_hello_count;
            if (!hello_seen && (hello_count > 0U))
            {
                g_service.xiaozhi_server_hello_seen = RT_TRUE;
                hello_seen = RT_TRUE;
            }
            rt_mutex_release(&g_service.lock);

            if (hello_seen)
            {
                rt_kprintf("[voice_service] Xiaozhi talk continuing with prior hello evidence count=%lu stage=%d errno=%d\n",
                           (unsigned long)hello_count,
                           websocket_client_last_stage(),
                           websocket_client_last_errno());
            }
            else
            {
                rt_kprintf("[voice_service] Xiaozhi talk deferred: hello timeout stage=%d errno=%d connected=%d\n",
                           websocket_client_last_stage(),
                           websocket_client_last_errno(),
                           websocket_client_is_connected() ? 1 : 0);
                xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智会话", -RT_ETIMEOUT);
                return -RT_ETIMEOUT;
            }
        }
    }
    if (!hello_seen)
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        hello_seen = g_service.xiaozhi_server_hello_seen;
        rt_mutex_release(&g_service.lock);
    }

    return voice_service_start_xiaozhi_manual_listening();
}

rt_err_t voice_service_stop_xiaozhi_talk(void)
{
    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    /*
     * Manual/LVGL stop must not wait on lwIP's blocking send path.  A partial
     * tail frame is less important than keeping the product UI responsive; the
     * async stop thread sends listen_stop after the UI/control caller returns.
     */
    return voice_service_stop_xiaozhi_listening_async();
}

typedef struct
{
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    xiaozhi_wake_source_t wake_source;
    rt_uint32_t bytes;
    rt_uint32_t chunks;
} voice_stop_notify_ctx_t;

static void voice_service_stop_notify_thread_entry(void *parameter)
{
    voice_stop_notify_ctx_t *ctx = (voice_stop_notify_ctx_t *)parameter;

    if (ctx != RT_NULL)
    {
        (void)voice_service_send_xiaozhi_listen_stop(ctx->session_id,
                                                     ctx->wake_source,
                                                     ctx->bytes,
                                                     ctx->chunks);
        rt_free(ctx);
    }
}

rt_err_t voice_service_abort_xiaozhi_talk_local(void)
{
    return voice_service_stop_xiaozhi_listening_async();
}

rt_bool_t voice_service_xiaozhi_is_listening(void)
{
    rt_bool_t active;

    if (!g_service.initialized)
    {
        return RT_FALSE;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    active = g_service.xiaozhi_listening_active;
    rt_mutex_release(&g_service.lock);
    return active;
}

static rt_err_t voice_service_send_xiaozhi_frame_locked_copy(const char *session_id,
                                                            const rt_uint8_t *frame)
{
    rt_err_t send_ret;
    rt_uint32_t sent_len = 0U;

    if ((frame == RT_NULL) || !websocket_client_is_connected())
    {
        return -RT_ERROR;
    }

    if (XIAOZHI_AUDIO_FORMAT_IS_PCM)
    {
        rt_size_t pcm_len = XIAOZHI_AUDIO_FRAME_BYTES;

#if XIAOZHI_PROTOCOL_VERSION == 3U
        rt_uint8_t ws_packet[XIAOZHI_AUDIO_FRAME_BYTES + XIAOZHI_BINARY_V3_HEADER_LEN];

        ws_packet[0] = 0U;
        ws_packet[1] = 0U;
        ws_packet[2] = (rt_uint8_t)((pcm_len >> 8) & 0xffU);
        ws_packet[3] = (rt_uint8_t)(pcm_len & 0xffU);
        rt_memcpy(ws_packet + XIAOZHI_BINARY_V3_HEADER_LEN, frame, pcm_len);
        send_ret = websocket_client_send_binary(ws_packet, pcm_len + XIAOZHI_BINARY_V3_HEADER_LEN);
#else
        send_ret = websocket_client_send_binary(frame, pcm_len);
#endif
        sent_len = (rt_uint32_t)pcm_len;
    }
    else
    {
        rt_uint8_t opus_packet[512];
        rt_size_t opus_len = 0U;

        send_ret = xiaozhi_opus_encoder_encode((const int16_t *)frame,
                                               XIAOZHI_PCM_60MS_SAMPLES,
                                               opus_packet,
                                               sizeof(opus_packet),
                                               &opus_len);
        if (send_ret == RT_EOK)
        {
#if XIAOZHI_PROTOCOL_VERSION == 3U
            rt_uint8_t ws_packet[512 + XIAOZHI_BINARY_V3_HEADER_LEN];

            ws_packet[0] = 0U;
            ws_packet[1] = 0U;
            ws_packet[2] = (rt_uint8_t)((opus_len >> 8) & 0xffU);
            ws_packet[3] = (rt_uint8_t)(opus_len & 0xffU);
            rt_memcpy(ws_packet + XIAOZHI_BINARY_V3_HEADER_LEN, opus_packet, opus_len);
            send_ret = websocket_client_send_binary(ws_packet, opus_len + XIAOZHI_BINARY_V3_HEADER_LEN);
#else
            send_ret = websocket_client_send_binary(opus_packet, opus_len);
#endif
        }
        sent_len = (rt_uint32_t)opus_len;
    }

    if (send_ret == RT_EOK)
    {
        rt_uint32_t chunks;
        rt_uint32_t bytes;

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_listening_bytes += sent_len;
        g_service.xiaozhi_listening_chunks++;
        chunks = g_service.xiaozhi_listening_chunks;
        bytes = g_service.xiaozhi_listening_bytes;
        rt_mutex_release(&g_service.lock);
        if ((chunks <= 3U) || ((chunks % 20U) == 0U))
        {
            rt_kprintf("[voice_service] Xiaozhi %s sent session=%s len=%lu total=%lu chunks=%lu\n",
                       XIAOZHI_AUDIO_FORMAT,
                       (session_id && session_id[0]) ? session_id : "(none)",
                       (unsigned long)sent_len,
                       (unsigned long)bytes,
                       (unsigned long)chunks);
        }
    }
    else
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_send_fail_count++;
        g_service.last_error = send_ret;
        rt_mutex_release(&g_service.lock);
        rt_kprintf("[voice_service] Xiaozhi audio send failed session=%s format=%s len=%lu fail=%lu ret=%d\n",
                   (session_id && session_id[0]) ? session_id : "(none)",
                   XIAOZHI_AUDIO_FORMAT,
                   (unsigned long)XIAOZHI_AUDIO_FRAME_BYTES,
                   (unsigned long)g_service.xiaozhi_send_fail_count,
                   send_ret);
    }

    return send_ret;
}

static void voice_service_flush_xiaozhi_tail_frame(void)
{
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    rt_uint8_t frame[XIAOZHI_AUDIO_FRAME_BYTES];
    rt_uint32_t tail_len;

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if (!g_service.xiaozhi_listening_active || (g_service.xiaozhi_audio_frame_len == 0U))
    {
        rt_mutex_release(&g_service.lock);
        return;
    }

    rt_memset(session_id, 0, sizeof(session_id));
    rt_strncpy(session_id, g_service.xiaozhi_listening_session_id, sizeof(session_id) - 1);
    tail_len = g_service.xiaozhi_audio_frame_len;
    rt_memcpy(frame, g_service.xiaozhi_audio_frame, tail_len);
    rt_memset(frame + tail_len, 0, sizeof(frame) - tail_len);
    g_service.xiaozhi_audio_frame_len = 0U;
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] Xiaozhi tail frame flush session=%s tail=%lu padded=%lu\n",
               session_id[0] ? session_id : "(none)",
               (unsigned long)tail_len,
               (unsigned long)sizeof(frame));
    (void)voice_service_send_xiaozhi_frame_locked_copy(session_id, frame);
}

static rt_err_t voice_service_stop_xiaozhi_listening_async(void)
{
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    xiaozhi_wake_source_t wake_source = XIAOZHI_WAKE_SOURCE_MANUAL;
    rt_uint32_t bytes = 0U;
    rt_uint32_t chunks = 0U;

    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    rt_memset(session_id, 0, sizeof(session_id));
    if (voice_service_take_xiaozhi_listening(session_id, sizeof(session_id), &wake_source, &bytes, &chunks))
    {
        voice_stop_notify_ctx_t *ctx = (voice_stop_notify_ctx_t *)rt_malloc(sizeof(*ctx));
        if (ctx != RT_NULL)
        {
            rt_thread_t thread;

            rt_memset(ctx, 0, sizeof(*ctx));
            rt_strncpy(ctx->session_id, session_id, sizeof(ctx->session_id) - 1);
            ctx->wake_source = wake_source;
            ctx->bytes = bytes;
            ctx->chunks = chunks;
            thread = rt_thread_create("xz_stop",
                                      voice_service_stop_notify_thread_entry,
                                      ctx,
                                      VOICE_STOP_NOTIFY_THREAD_STACK,
                                      22,
                                      10);
            if (thread != RT_NULL)
            {
                rt_thread_startup(thread);
            }
            else
            {
                rt_free(ctx);
                rt_kprintf("[voice_service] Xiaozhi async stop thread create failed session=%s\n",
                           session_id);
            }
        }
        voice_service_mark_xiaozhi_thinking("正在思考");
    }
    else
    {
        xiaozhi_ui_state_set(XIAOZHI_UI_READY, "在线，等待唤醒词", RT_EOK);
    }

    (void)voice_service_publish_status();
    return RT_EOK;
}

static rt_bool_t voice_service_feed_xiaozhi_listening(const uint8_t *audio_data, uint32_t len)
{
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    rt_uint32_t offset = 0;

    if ((audio_data == RT_NULL) || (len == 0))
    {
        return RT_FALSE;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if (!g_service.xiaozhi_listening_active)
    {
        rt_mutex_release(&g_service.lock);
        return RT_FALSE;
    }
    rt_memset(session_id, 0, sizeof(session_id));
    rt_strncpy(session_id, g_service.xiaozhi_listening_session_id, sizeof(session_id) - 1);
    rt_mutex_release(&g_service.lock);

    if (!websocket_client_is_connected())
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_listening_active = RT_FALSE;
        g_service.xiaozhi_audio_frame_len = 0;
        rt_mutex_release(&g_service.lock);
        xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "小智连接断开", websocket_client_last_errno());
        rt_kprintf("[voice_service] Xiaozhi listening stopped: websocket disconnected session=%s\n",
                   session_id);
        return RT_TRUE;
    }

    while (offset < len)
    {
        rt_uint32_t copy_len;
        rt_uint8_t frame[XIAOZHI_AUDIO_FRAME_BYTES];
        rt_bool_t frame_ready = RT_FALSE;

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        copy_len = XIAOZHI_AUDIO_FRAME_BYTES - g_service.xiaozhi_audio_frame_len;
        if (copy_len > (len - offset))
        {
            copy_len = len - offset;
        }
        rt_memcpy(g_service.xiaozhi_audio_frame + g_service.xiaozhi_audio_frame_len,
                  audio_data + offset,
                  copy_len);
        g_service.xiaozhi_audio_frame_len += copy_len;
        offset += copy_len;
        if (g_service.xiaozhi_audio_frame_len >= XIAOZHI_AUDIO_FRAME_BYTES)
        {
            rt_memcpy(frame, g_service.xiaozhi_audio_frame, XIAOZHI_AUDIO_FRAME_BYTES);
            g_service.xiaozhi_audio_frame_len = 0;
            frame_ready = RT_TRUE;
        }
        rt_mutex_release(&g_service.lock);

        if (frame_ready)
        {
            rt_err_t send_ret;

            send_ret = voice_service_send_xiaozhi_frame_locked_copy(session_id, frame);
            if (send_ret != RT_EOK)
            {
                return RT_TRUE;
            }
        }
    }

    return RT_TRUE;
}

static rt_bool_t voice_service_update_xiaozhi_eou(const voice_model_result_t *model_result)
{
    rt_tick_t now;
    rt_tick_t started;
    rt_tick_t last_voice;
    rt_uint32_t elapsed_ms;
    rt_uint32_t silence_ms;
    rt_uint32_t min_record_ms;
    rt_bool_t active;
    rt_bool_t voice_seen;
    rt_bool_t session_voice_seen;
    xiaozhi_wake_source_t wake_source;

    if (model_result == RT_NULL)
    {
        return RT_FALSE;
    }

    now = rt_tick_get();
    voice_seen = ((model_result->peak >= XIAOZHI_EOU_SILENCE_PEAK) ||
                  (model_result->avg_abs >= XIAOZHI_EOU_SILENCE_AVG)) ? RT_TRUE : RT_FALSE;

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    active = g_service.xiaozhi_listening_active;
    if (g_service.m33_pcm_probe_enabled)
    {
        if (active && voice_seen)
        {
            g_service.xiaozhi_last_voice_tick = now;
        }
        rt_mutex_release(&g_service.lock);
        return RT_FALSE;
    }
    if (!active)
    {
        rt_mutex_release(&g_service.lock);
        return RT_FALSE;
    }

    if (voice_seen)
    {
        g_service.xiaozhi_last_voice_tick = now;
        if (g_service.xiaozhi_voice_seen_frames < XIAOZHI_EOU_VOICE_FRAMES)
        {
            g_service.xiaozhi_voice_seen_frames++;
        }
        if (g_service.xiaozhi_voice_seen_frames >= XIAOZHI_EOU_VOICE_FRAMES)
        {
            g_service.xiaozhi_voice_seen = RT_TRUE;
        }
    }
    started = g_service.xiaozhi_listening_start_tick;
    last_voice = g_service.xiaozhi_last_voice_tick;
    session_voice_seen = g_service.xiaozhi_voice_seen;
    wake_source = g_service.xiaozhi_listening_source;
    rt_mutex_release(&g_service.lock);

    elapsed_ms = (rt_uint32_t)((now - started) * 1000U / RT_TICK_PER_SECOND);
    silence_ms = (rt_uint32_t)((now - last_voice) * 1000U / RT_TICK_PER_SECOND);
    min_record_ms = (wake_source == XIAOZHI_WAKE_SOURCE_MANUAL) ?
        XIAOZHI_EOU_MANUAL_MIN_RECORD_MS :
        XIAOZHI_EOU_MIN_RECORD_MS;

    if ((elapsed_ms >= XIAOZHI_EOU_MAX_RECORD_MS) ||
        (session_voice_seen &&
         (elapsed_ms >= min_record_ms) &&
         (silence_ms >= XIAOZHI_EOU_SILENCE_MS)))
    {
        voice_service_flush_xiaozhi_tail_frame();
        rt_kprintf("[voice_service] Xiaozhi auto EOU elapsed=%lu silence=%lu peak=%lu avg=%lu source=%d\n",
                   (unsigned long)elapsed_ms,
                   (unsigned long)silence_ms,
                   (unsigned long)model_result->peak,
                   (unsigned long)model_result->avg_abs,
                   (int)wake_source);
        (void)voice_service_stop_xiaozhi_listening_async();
        (void)voice_service_publish_status();
        return RT_TRUE;
    }

    return RT_FALSE;
}

static void voice_service_stop_xiaozhi_listening(rt_bool_t notify_server)
{
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    xiaozhi_wake_source_t wake_source = XIAOZHI_WAKE_SOURCE_MANUAL;
    rt_uint32_t bytes = 0U;
    rt_uint32_t chunks = 0U;

    rt_memset(session_id, 0, sizeof(session_id));
    if (!voice_service_take_xiaozhi_listening(session_id, sizeof(session_id), &wake_source, &bytes, &chunks))
    {
        return;
    }

    if (notify_server)
    {
        (void)voice_service_send_xiaozhi_listen_stop(session_id, wake_source, bytes, chunks);
    }

    if (notify_server && websocket_client_is_connected())
    {
        voice_service_mark_xiaozhi_thinking("正在思考");
        xiaozhi_feedback_beep(60U);
    }

    rt_kprintf("[voice_service] Xiaozhi listening stopped session=%s source=%d bytes=%lu chunks=%lu notify=%d\n",
               session_id,
               (int)wake_source,
               (unsigned long)bytes,
               (unsigned long)chunks,
               notify_server ? 1 : 0);
}

static rt_bool_t voice_service_take_xiaozhi_listening(char *session_id,
                                                      rt_size_t session_id_len,
                                                      xiaozhi_wake_source_t *wake_source,
                                                      rt_uint32_t *bytes,
                                                      rt_uint32_t *chunks)
{
    if ((session_id == RT_NULL) || (session_id_len == 0U) ||
        (wake_source == RT_NULL) || (bytes == RT_NULL) || (chunks == RT_NULL))
    {
        return RT_FALSE;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if (!g_service.xiaozhi_listening_active)
    {
        rt_mutex_release(&g_service.lock);
        return RT_FALSE;
    }

    rt_memset(session_id, 0, session_id_len);
    rt_strncpy(session_id, g_service.xiaozhi_listening_session_id, session_id_len - 1);
    *wake_source = g_service.xiaozhi_listening_source;
    *bytes = g_service.xiaozhi_listening_bytes;
    *chunks = g_service.xiaozhi_listening_chunks;
    g_service.xiaozhi_listening_active = RT_FALSE;
    g_service.xiaozhi_listening_source = XIAOZHI_WAKE_SOURCE_MANUAL;
    g_service.xiaozhi_listening_bytes = 0;
    g_service.xiaozhi_listening_chunks = 0;
    rt_memset(g_service.xiaozhi_listening_session_id, 0, sizeof(g_service.xiaozhi_listening_session_id));
    g_service.xiaozhi_audio_frame_len = 0;
    g_service.xiaozhi_last_sent_bytes = *bytes;
    g_service.xiaozhi_last_sent_chunks = *chunks;
    rt_mutex_release(&g_service.lock);

    return RT_TRUE;
}

static rt_err_t voice_service_send_xiaozhi_listen_stop(const char *session_id,
                                                       xiaozhi_wake_source_t wake_source,
                                                       rt_uint32_t bytes,
                                                       rt_uint32_t chunks)
{
    char json[VOICE_JSON_BUFFER_SIZE];
    rt_err_t ret;

    if (!websocket_client_is_connected())
    {
        return -RT_ERROR;
    }

    ret = xiaozhi_voice_relay_build_listen_stop(json,
                                                sizeof(json),
                                                session_id,
                                                wake_source,
                                                bytes,
                                                chunks);
    if (ret != RT_EOK)
    {
        return ret;
    }

    ret = websocket_client_send_text(json);
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_listen_stop_result = ret;
    if (ret == RT_EOK)
    {
        g_service.xiaozhi_listen_stop_count++;
    }
    rt_mutex_release(&g_service.lock);
    if (ret != RT_EOK)
    {
        g_service.last_error = ret;
        rt_kprintf("[voice_service] Xiaozhi listen stop send failed session=%s ret=%d\n",
                   session_id,
                   ret);
        return ret;
    }

    rt_kprintf("[voice_service] Xiaozhi listen stop sent session=%s source=%d bytes=%lu chunks=%lu\n",
               session_id,
               (int)wake_source,
               (unsigned long)bytes,
               (unsigned long)chunks);
    return RT_EOK;
}

static void __attribute__((unused)) on_asr_result(const char *text, rt_err_t error)
{
    if ((error != RT_EOK) || (text == RT_NULL) || (*text == '\0'))
    {
        rt_kprintf("[voice_service] ASR failed: %d\n", error);
        return;
    }

    rt_kprintf("[voice_service] ASR: %s\n", text);
    voice_service_publish_text_to_m33(MSG_TYPE_ASR_TEXT, text);
    voice_service_send_text_to_server("asr_text", text);
}

static void on_tts_result(const uint8_t *audio_data, uint32_t len, rt_err_t error)
{
    if ((error != RT_EOK) || (audio_data == RT_NULL) || (len == 0))
    {
        rt_kprintf("[voice_service] TTS failed: %d\n", error);
        return;
    }

    rt_kprintf("[voice_service] TTS audio %lu bytes\n", (unsigned long)len);
    voice_service_stream_pcm_to_m33(audio_data, len, RT_TRUE);
    voice_service_flush_audio_to_m33();
}

static void voice_service_handle_server_text(const char *message)
{
    xiaozhi_response_t xiaozhi_response;
    char type[32];
    char text[256];
    char content[256];
    char broadcast[256];
    char speak[256];
    char state[32];
    char error[96];
    char reason[160];
    char code[48];
    char session_id[XIAOZHI_SESSION_ID_MAX_LEN];
    const char *fallback_text = RT_NULL;
    rt_uint32_t raw_len;
    rt_uint32_t reason_code;
    rt_uint32_t hint_code;

    type[0] = '\0';
    text[0] = '\0';
    content[0] = '\0';
    broadcast[0] = '\0';
    speak[0] = '\0';
    state[0] = '\0';
    error[0] = '\0';
    reason[0] = '\0';
    code[0] = '\0';
    session_id[0] = '\0';
    json_get_string(message, "type", type, sizeof(type));
    json_get_string(message, "state", state, sizeof(state));
    json_get_string(message, "error", error, sizeof(error));
    json_get_string(message, "reason", reason, sizeof(reason));
    json_get_string(message, "code", code, sizeof(code));
    json_get_string(message, "session_id", session_id, sizeof(session_id));
    json_get_string(message, "text", text, sizeof(text));
    json_get_string(message, "content", content, sizeof(content));
    json_get_string(message, "message", content, sizeof(content));
    json_get_string(message, "broadcast", broadcast, sizeof(broadcast));
    json_get_string(message, "tts", speak, sizeof(speak));
    json_get_string(message, "speak", speak, sizeof(speak));
    raw_len = (rt_uint32_t)rt_strlen(message);
    reason_code = voice_service_text_code4(reason);
    hint_code = voice_service_server_hint_code4(message, type, state, error, content, speak);

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.xiaozhi_server_last_type_code = voice_service_text_code4(type);
    g_service.xiaozhi_server_last_state_code = voice_service_text_code4(state);
    g_service.xiaozhi_server_last_text_lens =
        (((rt_uint32_t)rt_strlen(text) & 0x3ffU) |
         (((rt_uint32_t)rt_strlen(content) & 0x3ffU) << 10U) |
         (((rt_uint32_t)rt_strlen(speak) & 0x3ffU) << 20U));
    g_service.xiaozhi_server_last_error_code =
        ((voice_service_text_code4(error) & 0xffffU) | ((hint_code & 0xffffU) << 16U));
    g_service.xiaozhi_server_last_reason_code =
        ((reason_code & 0xffffU) | ((raw_len & 0xffffU) << 16U));
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] server event type=%s state=%s session=%s text=%u content=%u speak=%u raw=%lu hint=0x%08lx err=%s reason=%s code=%s\n",
               type[0] ? type : "(none)",
               state[0] ? state : "(none)",
               session_id[0] ? session_id : "(none)",
               (unsigned)rt_strlen(text),
               (unsigned)rt_strlen(content),
               (unsigned)rt_strlen(speak),
               (unsigned long)raw_len,
               (unsigned long)hint_code,
               error[0] ? error : "(none)",
               reason[0] ? reason : "(none)",
               code[0] ? code : "(none)");

    if (rt_strcmp(type, "hello") == 0)
    {
        rt_uint32_t server_sample_rate = 0U;
        rt_uint32_t server_channels = 0U;
        rt_uint32_t server_frame_duration = 0U;

        (void)json_get_uint(message, "sample_rate", &server_sample_rate);
        (void)json_get_uint(message, "channels", &server_channels);
        (void)json_get_uint(message, "frame_duration", &server_frame_duration);
        if (server_sample_rate == 0U)
        {
            server_sample_rate = XIAOZHI_AUDIO_SAMPLE_RATE;
        }
        if (server_channels == 0U)
        {
            server_channels = XIAOZHI_AUDIO_CHANNELS;
        }
        (void)xiaozhi_opus_decoder_configure((int)server_sample_rate, (int)server_channels);

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_server_hello_seen = RT_TRUE;
        g_service.xiaozhi_server_hello_count++;
        if (session_id[0] != '\0')
        {
            rt_memset(g_service.xiaozhi_session_id, 0, sizeof(g_service.xiaozhi_session_id));
            rt_strncpy(g_service.xiaozhi_session_id,
                       session_id,
                       sizeof(g_service.xiaozhi_session_id) - 1);
        }
        rt_mutex_release(&g_service.lock);
        rt_kprintf("[voice_service] Xiaozhi server hello session=%s audio=%luHz/%luch/%lums\n",
                   session_id[0] ? session_id : "(none)",
                   (unsigned long)server_sample_rate,
                   (unsigned long)server_channels,
                   (unsigned long)server_frame_duration);
        voice_service_clear_xiaozhi_thinking();
        xiaozhi_ui_state_set(XIAOZHI_UI_READY, "在线，等待唤醒词", RT_EOK);
        return;
    }

    if ((rt_strcmp(type, "error") == 0) ||
        (error[0] != '\0') ||
        (reason[0] != '\0'))
    {
        voice_service_clear_xiaozhi_thinking();
        rt_kprintf("[voice_service] Xiaozhi server error type=%s state=%s error=%s reason=%s code=%s raw=%s\n",
                   type[0] ? type : "(none)",
                   state[0] ? state : "(none)",
                   error[0] ? error : "(none)",
                   reason[0] ? reason : "(none)",
                   code[0] ? code : "(none)",
                   message);
        xiaozhi_ui_state_set(XIAOZHI_UI_ERROR,
                             reason[0] ? reason : (error[0] ? error : "平台返回错误"),
                             -RT_ERROR);
        return;
    }

    if ((rt_strcmp(type, "listen") == 0) && (rt_strcmp(state, "stop") == 0))
    {
        voice_service_stop_xiaozhi_listening(RT_FALSE);
        voice_service_mark_xiaozhi_thinking("已发送，等待平台模型");
        return;
    }

    if ((rt_strcmp(type, "stt") == 0) && (text[0] != '\0'))
    {
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.xiaozhi_server_stt_count++;
        rt_mutex_release(&g_service.lock);
        rt_kprintf("[voice_service] stt text: %s\n", text);
        voice_service_mark_xiaozhi_thinking("已识别，等待回答");
        voice_service_publish_text_to_m33(MSG_TYPE_ASR_TEXT, text);
        return;
    }

    if (rt_strcmp(type, "tts") == 0)
    {
        if (rt_strcmp(state, "start") == 0)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_server_tts_start_count++;
            rt_mutex_release(&g_service.lock);
            voice_service_clear_xiaozhi_thinking();
            xiaozhi_ui_state_set(XIAOZHI_UI_SPEAKING, "准备语音回复", RT_EOK);
            xiaozhi_feedback_beep(90U);
            return;
        }
        if (rt_strcmp(state, "stop") == 0)
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_server_tts_stop_count++;
            rt_mutex_release(&g_service.lock);
            voice_service_flush_audio_to_m33();
            voice_service_clear_xiaozhi_thinking();
            xiaozhi_ui_state_set(XIAOZHI_UI_READY, "在线，等待唤醒词", RT_EOK);
            return;
        }
        if ((rt_strcmp(state, "sentence_start") == 0) &&
            ((text[0] != '\0') || (content[0] != '\0') || (speak[0] != '\0')))
        {
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.xiaozhi_server_tts_sentence_count++;
            rt_mutex_release(&g_service.lock);
            fallback_text = text[0] ? text : (content[0] ? content : speak);
            voice_service_clear_xiaozhi_thinking();
            xiaozhi_ui_state_set_reply(fallback_text);
            voice_service_publish_text_to_m33(MSG_TYPE_TTS_REQUEST, fallback_text);
            return;
        }
        rt_kprintf("[voice_service] tts event not handled state=%s raw=%s\n",
                   state[0] ? state : "(none)",
                   message);
    }

    if (xiaozhi_voice_relay_parse_response(message, &xiaozhi_response))
    {
        if (xiaozhi_response.kind == XIAOZHI_UTTERANCE_VLA_COMMAND)
        {
            const char *intent = xiaozhi_response.language_context[0] ?
                                 xiaozhi_response.language_context :
                                 xiaozhi_response.transcript;
            rt_kprintf("[voice_service] vla language intent: %s\n", intent && intent[0] ? intent : "(empty)");
            if (intent && intent[0])
            {
                voice_service_publish_text_to_m33(MSG_TYPE_ASR_TEXT, intent);
            }
        }
        else if (xiaozhi_response.kind == XIAOZHI_UTTERANCE_DAILY_CHAT)
        {
            rt_kprintf("[voice_service] daily chat reply\n");
        }

        if (xiaozhi_response.reply[0] != '\0')
        {
            fallback_text = xiaozhi_response.reply;
        }
    }

    if (fallback_text)
    {
        /* Prefer the normalized Xiaozhi reply parsed above. */
    }
    else if (text[0] != '\0')
    {
        fallback_text = text;
    }
    else if (content[0] != '\0')
    {
        fallback_text = content;
    }
    else if (broadcast[0] != '\0')
    {
        fallback_text = broadcast;
    }
    else if (speak[0] != '\0')
    {
        fallback_text = speak;
    }
    else if ((type[0] == '\0') && message && *message)
    {
        fallback_text = message;
    }

    if (!fallback_text || !*fallback_text)
    {
        rt_kprintf("[voice_service] server text ignored: %s\n", message);
        return;
    }

    rt_kprintf("[voice_service] server reply: %s\n", fallback_text);
    voice_service_clear_xiaozhi_thinking();
    xiaozhi_ui_state_set_reply(fallback_text);
    voice_service_publish_text_to_m33(MSG_TYPE_TTS_REQUEST, fallback_text);

    if (g_service.tts_ready)
    {
        baidu_tts_synthesize(fallback_text, on_tts_result);
    }
    else
    {
        rt_kprintf("[voice_service] TTS backend unavailable, waiting for binary audio or credentials\n");
    }
}

static void on_websocket_message(websocket_message_type_t type, const uint8_t *payload, rt_size_t payload_len)
{
    if (!payload || payload_len == 0)
    {
        return;
    }

    if (type == WEBSOCKET_MESSAGE_BINARY)
    {
        g_service.xiaozhi_rx_binary_count++;
        voice_service_log_payload_head("[voice_service] server binary audio", payload, payload_len);
        voice_service_clear_xiaozhi_thinking();
        xiaozhi_ui_state_set(XIAOZHI_UI_SPEAKING, "收到语音回复", RT_EOK);
        voice_service_enqueue_tts_payload(payload, payload_len, RT_TRUE);
        return;
    }

    {
        char text[384];
        rt_size_t copy_len = payload_len >= sizeof(text) ? sizeof(text) - 1 : payload_len;
        const uint8_t *audio_payload = payload;
        rt_size_t audio_len = payload_len;

        if (XIAOZHI_PROTOCOL_USES_V3_BINARY)
        {
            voice_service_strip_v3_audio_header(&audio_payload, &audio_len);
        }
        if ((payload[0] != '{') &&
            voice_service_audio_looks_like_pcm16(audio_payload, (uint32_t)audio_len))
        {
            g_service.xiaozhi_rx_binary_count++;
            voice_service_clear_xiaozhi_thinking();
            xiaozhi_ui_state_set(XIAOZHI_UI_SPEAKING, "收到语音回复", RT_EOK);
            voice_service_enqueue_tts_payload(audio_payload, audio_len, RT_FALSE);
            return;
        }

        if (payload[0] != '{')
        {
            voice_service_log_payload_head("[voice_service] non-json text ignored", payload, payload_len);
            return;
        }

        rt_memcpy(text, payload, copy_len);
        text[copy_len] = '\0';
        g_service.xiaozhi_rx_text_count++;
        voice_service_log_payload_head("[voice_service] server text head", payload, payload_len);
        rt_kprintf("[voice_service] server text: %s\n", text);
        voice_service_handle_server_text(text);
    }
}

static void voice_service_reset_audio(void)
{
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.audio_expected = 0;
    g_service.audio_received = 0;
    rt_mutex_release(&g_service.lock);
}

static void voice_service_process_audio_buffer(void)
{
    rt_uint32_t len;
    voice_model_result_t model_result;
    xiaozhi_wake_result_t wake_result;
    rt_bool_t wake_triggered = RT_FALSE;

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    len = g_service.audio_received;
    rt_mutex_release(&g_service.lock);
    model_result = voice_service_model_entry(g_service.audio_buffer, len);

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.processed_windows++;
    g_service.latest_peak = model_result.peak;
    g_service.latest_avg_abs = model_result.avg_abs;
    g_service.latest_active_frames = model_result.active_frames;
    g_service.latest_total_frames = model_result.total_frames;
    rt_mutex_release(&g_service.lock);

    if (voice_service_feed_xiaozhi_listening(g_service.audio_buffer, len))
    {
        (void)voice_service_update_xiaozhi_eou(&model_result);
        return;
    }

    if (g_service.wake_skip_windows > 0U)
    {
        g_service.wake_skip_windows--;
        return;
    }

    /*
     * Local CM55 mic input arrives as short 20 ms PCM frames. The wake backend
     * owns the 1 second rolling model window, so it must receive every frame;
     * per-frame speech gates cannot require a full-window active-frame count.
     */
    rt_memset(&wake_result, 0, sizeof(wake_result));
    if (xiaozhi_wake_engine_process_pcm16((const int16_t *)g_service.audio_buffer,
                                          len / sizeof(int16_t),
                                          &wake_result) != RT_EOK)
    {
        if (wake_result.event == XIAOZHI_WAKE_EVENT_UNAVAILABLE)
        {
            g_service.last_error = -RT_ENOSYS;
            return;
        }
        rt_kprintf("[voice_service] wake engine error=%d\n", wake_result.error_code);
        g_service.last_error = wake_result.error_code;
        return;
    }

    if (wake_result.event == XIAOZHI_WAKE_EVENT_DETECTED)
    {
        wake_triggered = RT_TRUE;
    }
    else
    {
        if (!model_result.speech)
        {
            g_service.wake_hit_streak = 0;
        }
        return;
    }

    if (wake_triggered)
    {
        g_service.wake_skip_windows = WAKE_SKIP_WINDOWS_AFTER_TRIGGER;
        g_service.wake_last_trigger_tick = rt_tick_get();
        g_service.detected_count++;
        g_service.last_error = RT_EOK;
        rt_kprintf("[voice_service] wake triggered word=%s peak=%lu avg=%lu active=%lu/%lu\n",
                   wake_result.wake_word[0] ? wake_result.wake_word : "unknown",
                   (unsigned long)model_result.peak,
                   (unsigned long)model_result.avg_abs,
                   (unsigned long)model_result.active_frames,
                   (unsigned long)model_result.total_frames);
        rt_err_t publish_ret = model_result_publish_wake_word(
            1000U,
            RT_TRUE,
            RT_TRUE,
            (rt_uint16_t)((len / sizeof(int16_t)) / 16U));
        if (publish_ret != RT_EOK)
        {
            rt_kprintf("[voice_service] model result publish failed %d\n", publish_ret);
            g_service.last_error = publish_ret;
        }
        (void)voice_service_publish_status();
        voice_service_start_xiaozhi_listening(wake_result.wake_word);
        (void)voice_service_feed_xiaozhi_listening(g_service.audio_buffer, len);
    }
}

static void voice_service_accept_shared_pcm(const sensor_stream_msg_t *stream)
{
    rt_uint32_t len;

    if (stream == RT_NULL)
    {
        return;
    }

    if ((stream->source != MODEL_INPUT_SRC_AUDIO_PCM) ||
        (stream->format != MODEL_INPUT_FMT_PCM_S16))
    {
        return;
    }

    if (!g_service.wake_listening && !g_service.xiaozhi_listening_active)
    {
        return;
    }

    if (stream->chunk_index != g_m33_m55_pcm_shared.seq)
    {
        rt_kprintf("[voice_service] shared pcm seq mismatch msg=%lu shared=%lu\n",
                   (unsigned long)stream->chunk_index,
                   (unsigned long)g_m33_m55_pcm_shared.seq);
        return;
    }

    len = stream->total_len;
    if (len > M33_M55_PCM_SHARED_CAPACITY)
    {
        len = M33_M55_PCM_SHARED_CAPACITY;
    }
    if (len > VOICE_PCM_BUFFER_SIZE)
    {
        len = VOICE_PCM_BUFFER_SIZE;
    }

    rt_hw_cpu_dcache_ops(RT_HW_CACHE_INVALIDATE, (void *)g_m33_m55_pcm_shared.data, len);
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.audio_expected = len;
    g_service.audio_received = len;
    g_service.latest_pcm_len = len;
    g_service.latest_pcm_seq = stream->chunk_index;
    g_service.latest_pcm_pending = RT_TRUE;
    rt_memcpy(g_service.audio_buffer, (const void *)g_m33_m55_pcm_shared.data, len);
    rt_mutex_release(&g_service.lock);

    (void)voice_service_feed_xiaozhi_listening(g_service.audio_buffer, len);
    rt_sem_release(&g_service.detect_sem);
}

static void voice_service_accept_audio_chunk(const audio_data_msg_t *chunk)
{
    if (!chunk)
    {
        return;
    }

    if (!g_service.wake_listening)
    {
        return;
    }

    if (chunk->chunk_index == 0)
    {
        voice_service_reset_audio();
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.audio_expected = chunk->total_len > VOICE_PCM_BUFFER_SIZE ? VOICE_PCM_BUFFER_SIZE : chunk->total_len;
        rt_mutex_release(&g_service.lock);
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if ((g_service.audio_buffer != RT_NULL) &&
        ((g_service.audio_received + chunk->chunk_len) <= VOICE_PCM_BUFFER_SIZE))
    {
        rt_memcpy(g_service.audio_buffer + g_service.audio_received, chunk->data, chunk->chunk_len);
        g_service.audio_received += chunk->chunk_len;
    }
    rt_mutex_release(&g_service.lock);

    if ((chunk->chunk_index % 16U) == 0U)
    {
        rt_kprintf("[voice_service] pcm chunk idx=%lu len=%lu recv=%lu/%lu\n",
                   (unsigned long)chunk->chunk_index,
                   (unsigned long)chunk->chunk_len,
                   (unsigned long)g_service.audio_received,
                   (unsigned long)g_service.audio_expected);
    }

    if ((g_service.audio_expected != 0) && (g_service.audio_received >= g_service.audio_expected))
    {
        voice_service_process_audio_buffer();
        voice_service_reset_audio();
    }
}

static rt_err_t voice_service_send_control(voice_control_cmd_t cmd)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = (rt_uint32_t)cmd;
    return m33_m55_comm_publish(&msg);
}

static rt_err_t voice_service_run_net_probe(void)
{
    int fd;
    struct sockaddr_in cloud_addr;
    rt_int32_t posix_tcp;
    rt_int32_t posix_errno;
    rt_int32_t sal_tcp;
    rt_int32_t sal_errno;
    rt_int32_t lwip_tcp;
    rt_int32_t lwip_errno;
    rt_int32_t cloud_tcp_result = -RT_ERROR;
    rt_int32_t cloud_tcp_errno = 0;

    errno = 0;
    fd = socket(AF_INET, SOCK_STREAM, 0);
    posix_tcp = fd;
    posix_errno = errno;
    if (fd >= 0)
    {
        closesocket(fd);
    }

    errno = 0;
    fd = sal_socket(AF_INET, SOCK_STREAM, 0);
    sal_tcp = fd;
    sal_errno = errno;
    if (fd >= 0)
    {
        sal_closesocket(fd);
    }

    errno = 0;
    fd = lwip_socket(AF_INET, SOCK_STREAM, 0);
    lwip_tcp = fd;
    lwip_errno = errno;
    if (fd >= 0)
    {
        lwip_close(fd);
    }

    rt_memset(&cloud_addr, 0, sizeof(cloud_addr));
    cloud_addr.sin_family = AF_INET;
    cloud_addr.sin_port = htons(XIAOZHI_CLOUD_PROBE_PORT);
    cloud_addr.sin_addr.s_addr = inet_addr(XIAOZHI_CLOUD_PROBE_IP);

    errno = 0;
    fd = lwip_socket(AF_INET, SOCK_STREAM, 0);
    if (fd >= 0)
    {
        cloud_tcp_result = lwip_connect(fd, (struct sockaddr *)&cloud_addr, sizeof(cloud_addr));
        cloud_tcp_errno = errno;
        lwip_close(fd);
    }
    else
    {
        cloud_tcp_result = fd;
        cloud_tcp_errno = errno;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.net_probe_posix_tcp = posix_tcp;
    g_service.net_probe_posix_errno = posix_errno;
    g_service.net_probe_sal_tcp = sal_tcp;
    g_service.net_probe_sal_errno = sal_errno;
    g_service.net_probe_lwip_tcp = lwip_tcp;
    g_service.net_probe_lwip_errno = lwip_errno;
    g_service.cloud_tcp_result = cloud_tcp_result;
    g_service.cloud_tcp_errno = cloud_tcp_errno;
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] net_probe posix=%ld errno=%ld sal=%ld errno=%ld lwip=%ld errno=%ld cloud_tcp=%ld errno=%ld net_flags=0x%lx\n",
               (long)posix_tcp,
               (long)posix_errno,
               (long)sal_tcp,
               (long)sal_errno,
               (long)lwip_tcp,
               (long)lwip_errno,
               (long)cloud_tcp_result,
               (long)cloud_tcp_errno,
               (unsigned long)g_service.netdev_flags);

    return (cloud_tcp_result == 0) ? RT_EOK :
           ((posix_tcp >= 0 || sal_tcp >= 0 || lwip_tcp >= 0) ? -RT_ETIMEOUT : -RT_ERROR);
}

static rt_err_t voice_service_wifi_set_ssid(const char *ssid)
{
    return wifi_config_set_ssid(ssid);
}

static rt_err_t voice_service_wifi_set_password(const char *password)
{
    return wifi_config_set_password(password);
}

static rt_err_t voice_service_wifi_connect(void)
{
    return wifi_config_start_auto_connect(10U);
}

static rt_err_t voice_service_wifi_disconnect(void)
{
    return wifi_config_disconnect();
}

static rt_err_t voice_service_wifi_save(void)
{
    return wifi_config_save();
}

static rt_err_t voice_service_wifi_forget(void)
{
    return wifi_config_forget();
}

static rt_err_t voice_service_wifi_auto(const char *value)
{
    rt_bool_t enable = RT_TRUE;

    if ((value != RT_NULL) && (value[0] == '0'))
    {
        enable = RT_FALSE;
    }

    (void)wifi_config_set_auto_connect(enable);
    return wifi_config_save();
}

static rt_err_t voice_service_wifi_diag(void)
{
    return wifi_config_diag();
}

static rt_err_t voice_service_wifi_scan(void)
{
    return wifi_config_scan();
}

static rt_err_t voice_service_whd_diag(void)
{
    return wifi_config_whd_diag();
}

static void voice_service_handle_control(const voice_control_msg_t *control)
{
    rt_err_t ret = RT_EOK;

    if (control == RT_NULL)
    {
        return;
    }

    switch ((voice_control_cmd_t)control->cmd)
    {
    case VOICE_CTRL_START_LISTEN:
        ret = voice_service_set_wake_listening(RT_TRUE);
        break;
    case VOICE_CTRL_STOP_LISTEN:
        ret = voice_service_set_wake_listening(RT_FALSE);
        break;
    case VOICE_CTRL_START_CAPTURE:
        ret = voice_service_start_xiaozhi_talk();
        rt_kprintf("[voice_service] xiaozhi talk start ret=%d\n", ret);
        break;
    case VOICE_CTRL_STOP_CAPTURE:
        ret = voice_service_stop_xiaozhi_talk();
        rt_kprintf("[voice_service] xiaozhi talk stop ret=%d\n", ret);
        break;
    case VOICE_CTRL_NET_PROBE:
        ret = voice_service_run_net_probe();
        break;
    case VOICE_CTRL_WIFI_DIAG:
        ret = voice_service_wifi_diag();
        break;
    case VOICE_CTRL_WIFI_SCAN:
        ret = voice_service_wifi_scan();
        break;
    case VOICE_CTRL_WHD_DIAG:
        ret = voice_service_whd_diag();
        break;
    case VOICE_CTRL_M33_PCM_PROBE_ENABLE:
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.m33_pcm_probe_enabled = RT_TRUE;
        g_service.m33_pcm_probe_accepted_count = 0U;
        g_service.m33_pcm_probe_ignored_count = 0U;
        rt_mutex_release(&g_service.lock);
        ret = RT_EOK;
        rt_kprintf("[voice_service] M33 PCM probe enabled for QA\n");
        break;
    case VOICE_CTRL_M33_PCM_PROBE_DISABLE:
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.m33_pcm_probe_enabled = RT_FALSE;
        rt_mutex_release(&g_service.lock);
        ret = RT_EOK;
        rt_kprintf("[voice_service] M33 PCM probe disabled; CM55 mic0 remains product uplink\n");
        break;
    default:
        rt_kprintf("[voice_service] unknown voice control cmd=%lu\n", (unsigned long)control->cmd);
        ret = -RT_EINVAL;
        break;
    }

    {
        m33_m55_message_t ack;

        (void)voice_service_publish_status();
        rt_memset(&ack, 0, sizeof(ack));
        ack.type = MSG_TYPE_VOICE_CONTROL_ACK;
        ack.payload.voice_control.cmd = control->cmd;
        ack.payload.voice_control.arg0 = (rt_uint32_t)ret;
        ack.payload.voice_control.arg1 = (rt_uint32_t)rt_tick_get();
        (void)m33_m55_comm_publish(&ack);
    }
}

static void voice_service_handle_config(const voice_config_msg_t *config)
{
    rt_err_t ret = RT_EOK;

    if (config == RT_NULL)
    {
        return;
    }

    switch ((voice_config_key_t)config->key)
    {
    case VOICE_CONFIG_XIAOZHI_URL:
        ret = xiaozhi_voice_relay_set_url(config->value);
        if (ret == RT_EOK)
        {
            ret = voice_service_reconnect_xiaozhi();
        }
        rt_kprintf("[voice_service] config xiaozhi url ret=%d\n", ret);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN:
        ret = xiaozhi_voice_relay_set_token(config->value);
        if (ret == RT_EOK)
        {
            ret = voice_service_reconnect_xiaozhi();
        }
        rt_kprintf("[voice_service] config xiaozhi token ret=%d configured=%d\n",
                   ret,
                   xiaozhi_voice_relay_has_token() ? 1 : 0);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_BEGIN:
        ret = xiaozhi_voice_relay_token_update_begin();
        rt_kprintf("[voice_service] config xiaozhi token_begin ret=%d\n", ret);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_PART:
        ret = xiaozhi_voice_relay_token_update_part(config->value);
        rt_kprintf("[voice_service] config xiaozhi token_part ret=%d len=%lu\n",
                   ret,
                   (unsigned long)rt_strlen(config->value));
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_COMMIT:
        ret = xiaozhi_voice_relay_token_update_commit();
        if (ret == RT_EOK)
        {
            ret = voice_service_reconnect_xiaozhi();
        }
        rt_kprintf("[voice_service] config xiaozhi token_commit ret=%d configured=%d\n",
                   ret,
                   xiaozhi_voice_relay_has_token() ? 1 : 0);
        break;
    case VOICE_CONFIG_XIAOZHI_TOKEN_CLEAR:
        xiaozhi_voice_relay_token_update_clear();
        ret = voice_service_reconnect_xiaozhi();
        rt_kprintf("[voice_service] config xiaozhi token_clear ret=%d configured=%d\n",
                   ret,
                   xiaozhi_voice_relay_has_token() ? 1 : 0);
        break;
    case VOICE_CONFIG_XIAOZHI_RECONNECT:
        ret = voice_service_reconnect_xiaozhi();
        rt_kprintf("[voice_service] config xiaozhi reconnect ret=%d\n", ret);
        break;
    case VOICE_CONFIG_WIFI_SSID:
        ret = voice_service_wifi_set_ssid(config->value);
        rt_kprintf("[voice_service] config wifi ssid ret=%d len=%lu\n",
                   ret,
                   (unsigned long)rt_strlen(config->value));
        break;
    case VOICE_CONFIG_WIFI_PASSWORD:
        ret = voice_service_wifi_set_password(config->value);
        rt_kprintf("[voice_service] config wifi password ret=%d len=%lu\n",
                   ret,
                   (unsigned long)rt_strlen(config->value));
        break;
    case VOICE_CONFIG_WIFI_CONNECT:
        ret = voice_service_wifi_connect();
        rt_kprintf("[voice_service] config wifi connect ret=%d\n", ret);
        break;
    case VOICE_CONFIG_WIFI_DISCONNECT:
        ret = voice_service_wifi_disconnect();
        rt_kprintf("[voice_service] config wifi disconnect ret=%d\n", ret);
        break;
    case VOICE_CONFIG_WIFI_SAVE:
        ret = voice_service_wifi_save();
        rt_kprintf("[voice_service] config wifi save ret=%d\n", ret);
        break;
    case VOICE_CONFIG_WIFI_FORGET:
        ret = voice_service_wifi_forget();
        rt_kprintf("[voice_service] config wifi forget ret=%d\n", ret);
        break;
    case VOICE_CONFIG_WIFI_AUTO_CONNECT:
        ret = voice_service_wifi_auto(config->value);
        rt_kprintf("[voice_service] config wifi auto ret=%d value=%s\n",
                   ret,
                   config->value);
        break;
    default:
        rt_kprintf("[voice_service] unknown voice config key=%lu\n",
                   (unsigned long)config->key);
        ret = -RT_EINVAL;
        break;
    }

    {
        m33_m55_message_t ack;

        rt_memset(&ack, 0, sizeof(ack));
        ack.type = MSG_TYPE_VOICE_CONTROL_ACK;
        ack.payload.voice_control.cmd = 1000U + config->key;
        ack.payload.voice_control.arg0 = (rt_uint32_t)ret;
        ack.payload.voice_control.arg1 = (rt_uint32_t)rt_tick_get();
        (void)m33_m55_comm_publish(&ack);
        (void)voice_service_publish_status();
    }
}

void voice_service_handle_ipc_message(const m33_m55_message_t *msg)
{
    m33_m55_message_t ack;
    rt_err_t ret;

    if (msg == RT_NULL)
    {
        return;
    }

    switch (msg->type)
    {
    case MSG_TYPE_SENSOR_SNAPSHOT:
        break;
    case MSG_TYPE_SENSOR_STREAM:
        if (msg->payload.sensor_stream.source == MODEL_INPUT_SRC_AUDIO_PCM)
        {
            rt_bool_t accept_probe_pcm;

            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            accept_probe_pcm = g_service.m33_pcm_probe_enabled &&
                               g_service.xiaozhi_listening_active;
            rt_mutex_release(&g_service.lock);
            if (!accept_probe_pcm)
            {
                rt_uint32_t ignored_count;

                rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
                g_service.m33_pcm_probe_ignored_count++;
                ignored_count = g_service.m33_pcm_probe_ignored_count;
                rt_mutex_release(&g_service.lock);
                if ((ignored_count == 1U) || ((ignored_count % 25U) == 0U))
                {
                    rt_kprintf("[voice_service] ignore M33 PCM probe count=%lu; official product uplink uses CM55 mic0\n",
                               (unsigned long)ignored_count);
                }
                break;
            }
            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            g_service.m33_pcm_probe_accepted_count++;
            {
                rt_uint32_t accepted_count = g_service.m33_pcm_probe_accepted_count;

                rt_mutex_release(&g_service.lock);
                if ((accepted_count <= 3U) || ((accepted_count % 20U) == 0U))
                {
                    rt_kprintf("[voice_service] accept M33 PCM probe count=%lu len=%lu seq=%lu\n",
                               (unsigned long)accepted_count,
                               (unsigned long)msg->payload.sensor_stream.chunk_len,
                               (unsigned long)msg->payload.sensor_stream.chunk_index);
                }
            }
        }
        voice_service_accept_shared_pcm(&msg->payload.sensor_stream);
        break;
    case MSG_TYPE_AUDIO_DATA:
        voice_service_accept_audio_chunk(&msg->payload.audio_data);
        break;
    case MSG_TYPE_TTS_REQUEST:
        voice_service_handle_server_text(msg->payload.text.text);
        break;
    case MSG_TYPE_VOICE_CONTROL:
        voice_service_handle_control(&msg->payload.voice_control);
        break;
    case MSG_TYPE_VOICE_CONFIG:
        voice_service_handle_config(&msg->payload.voice_config);
        break;
    case MSG_TYPE_AI_INFERENCE_REQ:
    case MSG_TYPE_REHAB_ANALYSIS_REQ:
        ret = -RT_ENOSYS;
        rt_memset(&ack, 0, sizeof(ack));
        ack.type = MSG_TYPE_VOICE_CONTROL_ACK;
        ack.payload.voice_control.cmd = (rt_uint32_t)msg->type;
        ack.payload.voice_control.arg0 = (rt_uint32_t)ret;
        ack.payload.voice_control.arg1 = (rt_uint32_t)rt_tick_get();
        (void)m33_m55_comm_publish(&ack);
        break;
    default:
        break;
    }
}

static void voice_service_drain_ipc_messages(void)
{
    /*
     * M55 has one owner for the M33->M55 RX queue: xz_bridge_thread_entry()
     * in main.c. Keeping this helper non-consuming prevents control/status
     * races where voice_service and the bridge both pull from the same queue.
     */
    g_service.service_last_consume_ret = -RT_EBUSY;
}

static void voice_service_thread_entry(void *parameter)
{
    RT_UNUSED(parameter);
    rt_kprintf("[voice_service] thread enter stack=%u\n", (unsigned)VOICE_SERVICE_THREAD_STACK);

    while (g_service.running)
    {
        g_service.service_loop_count++;
        g_service.service_diag_phase = 1U;
        voice_service_drain_ipc_messages();

#if VOICE_SERVICE_AUTO_RECONNECT_IN_THREAD
        if (!websocket_client_is_connected() && xiaozhi_voice_relay_has_token())
        {
            rt_bool_t listening_active;
            rt_tick_t now = rt_tick_get();

            rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
            listening_active = g_service.xiaozhi_listening_active;
            rt_mutex_release(&g_service.lock);
            if (listening_active)
            {
                rt_thread_mdelay(50);
                continue;
            }

            if ((g_service.reconnect_tick == 0) || (now - g_service.reconnect_tick > RT_TICK_PER_SECOND * 2))
            {
                rt_err_t ret;

                g_service.reconnect_tick = now;
                ret = voice_service_reconnect_xiaozhi();
                if (ret == RT_EOK)
                {
                    rt_kprintf("[voice_service] websocket auto reconnected stage=%d errno=%d\n",
                               websocket_client_last_stage(),
                               websocket_client_last_errno());
                    (void)voice_service_publish_status();
                }
                else
                {
                    rt_kprintf("[voice_service] websocket auto reconnect failed ret=%d stage=%d errno=%d\n",
                               ret,
                               websocket_client_last_stage(),
                               websocket_client_last_errno());
                    xiaozhi_ui_state_set(XIAOZHI_UI_READY, "小智离线，按说话重试", ret);
                    (void)voice_service_publish_status();
                }
            }
        }
#endif

        if (voice_service_process_pending_tts())
        {
            rt_thread_mdelay(20);
        }

        voice_service_check_xiaozhi_thinking_timeout();

        rt_thread_mdelay(50);
    }
}

static void voice_service_detect_thread_entry(void *parameter)
{
    rt_uint32_t local_len;

    RT_UNUSED(parameter);

    while (g_service.running)
    {
        if (rt_sem_take(&g_service.detect_sem, RT_TICK_PER_SECOND) != RT_EOK)
        {
            continue;
        }

        while (rt_sem_take(&g_service.detect_sem, 0) == RT_EOK)
        {
            /* Drain stale wakeups and keep only the newest PCM window. */
        }

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        if (!g_service.latest_pcm_pending || (g_service.latest_pcm_len == 0) || (g_service.detect_buffer == RT_NULL))
        {
            rt_mutex_release(&g_service.lock);
            continue;
        }

        local_len = g_service.latest_pcm_len;
        rt_memcpy(g_service.detect_buffer, g_service.audio_buffer, local_len);
        g_service.latest_pcm_pending = RT_FALSE;
        rt_mutex_release(&g_service.lock);

        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.audio_expected = local_len;
        g_service.audio_received = local_len;
        rt_memcpy(g_service.audio_buffer, g_service.detect_buffer, local_len);
        rt_mutex_release(&g_service.lock);

        voice_service_process_audio_buffer();
        voice_service_reset_audio();
    }
}

rt_err_t voice_service_init(const char *baidu_api_key, const char *baidu_secret_key)
{
    rt_err_t ret;
    if (g_service.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_service, 0, sizeof(g_service));
    rt_mutex_init(&g_service.lock, "voice", RT_IPC_FLAG_PRIO);
    rt_sem_init(&g_service.detect_sem, "vdet", 0, RT_IPC_FLAG_PRIO);
    g_service.audio_buffer = (rt_uint8_t *)rt_malloc(VOICE_PCM_BUFFER_SIZE);
    if (g_service.audio_buffer == RT_NULL)
    {
        rt_kprintf("[voice_service] alloc audio buffer failed: %u\n", VOICE_PCM_BUFFER_SIZE);
        return -RT_ENOMEM;
    }
    g_service.detect_buffer = (rt_uint8_t *)rt_malloc(VOICE_PCM_BUFFER_SIZE);
    if (g_service.detect_buffer == RT_NULL)
    {
        rt_kprintf("[voice_service] alloc detect buffer failed: %u\n", VOICE_PCM_BUFFER_SIZE);
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return -RT_ENOMEM;
    }
    g_service.tts_pending_buffer = (rt_uint8_t *)rt_malloc(VOICE_TTS_PENDING_BUFFER_SIZE);
    if (g_service.tts_pending_buffer == RT_NULL)
    {
        rt_kprintf("[voice_service] TTS pending buffer allocation failed\n");
        rt_free(g_service.detect_buffer);
        g_service.detect_buffer = RT_NULL;
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return -RT_ENOMEM;
    }
    ret = m33_m55_comm_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] IPC init failed: %d\n", ret);
        rt_free(g_service.detect_buffer);
        g_service.detect_buffer = RT_NULL;
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    ret = baidu_asr_init(baidu_api_key, baidu_secret_key);
    if (ret != RT_EOK)
    {
        rt_free(g_service.detect_buffer);
        g_service.detect_buffer = RT_NULL;
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }
    ret = baidu_tts_init(baidu_api_key, baidu_secret_key);
    if (ret != RT_EOK)
    {
        rt_free(g_service.detect_buffer);
        g_service.detect_buffer = RT_NULL;
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    g_service.asr_ready = baidu_asr_is_ready();
    g_service.tts_ready = baidu_tts_is_ready();

    ret = voice_service_configure_xiaozhi_socket();
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] websocket init failed: %d\n", ret);
        rt_free(g_service.detect_buffer);
        g_service.detect_buffer = RT_NULL;
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    websocket_client_set_callback(on_websocket_message);
#if VOICE_SERVICE_CONNECT_DURING_INIT
    ret = websocket_client_connect();
    g_service.last_error = ret;
    if (ret == RT_EOK)
    {
        voice_service_send_xiaozhi_hello();
    }
    else
    {
        xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智连接", ret);
        rt_kprintf("[voice_service] initial xiaozhi connect deferred: %d\n", ret);
    }
#else
    g_service.last_error = -ENOTCONN;
    xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "等待小智连接", g_service.last_error);
    rt_kprintf("[voice_service] initial xiaozhi connect deferred by init policy\n");
#endif

    g_service.wake_hit_streak = 0;
    g_service.wake_skip_windows = 0;
    g_service.wake_last_trigger_tick = 0;
    ret = xiaozhi_wake_engine_init();
    if (ret != RT_EOK)
    {
        g_service.last_error = xiaozhi_wake_engine_last_error();
    }
    rt_kprintf("[voice_service] xiaozhi wake backend=%s ready=%d ret=%d\n",
               xiaozhi_wake_engine_backend_name(),
               xiaozhi_wake_engine_is_ready() ? 1 : 0,
               ret);

    g_service.initialized = RT_TRUE;
    rt_kprintf("[voice_service] initialized (ASR=%d TTS=%d)\n", g_service.asr_ready, g_service.tts_ready);
    return RT_EOK;
}

rt_err_t voice_service_start(void)
{
    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    if (g_service.running)
    {
        return RT_EOK;
    }

    g_service.running = RT_TRUE;
    g_service.thread = rt_thread_create("voice_svc",
                                        voice_service_thread_entry,
                                        RT_NULL,
                                        VOICE_SERVICE_THREAD_STACK,
                                        8,
                                        5);
    if (!g_service.thread)
    {
        g_service.running = RT_FALSE;
        return -RT_ENOMEM;
    }
    g_service.detect_thread = rt_thread_create("voice_det",
                                               voice_service_detect_thread_entry,
                                               RT_NULL,
                                               VOICE_DETECT_THREAD_STACK,
                                               20,
                                               10);
    if (!g_service.detect_thread)
    {
        g_service.running = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_service.thread);
    rt_thread_startup(g_service.detect_thread);
    rt_kprintf("[voice_service] started\n");
    return RT_EOK;
}

rt_bool_t voice_service_is_running(void)
{
    return g_service.running ? RT_TRUE : RT_FALSE;
}

rt_err_t voice_service_prepare_xiaozhi_socket(void)
{
    return voice_service_configure_xiaozhi_socket();
}

rt_err_t voice_service_stop(void)
{
    if (!g_service.running)
    {
        return RT_EOK;
    }

    g_service.running = RT_FALSE;
    websocket_client_disconnect();
    return RT_EOK;
}

rt_err_t voice_service_reconnect_xiaozhi(void)
{
    rt_err_t ret;

    if (websocket_client_is_connected())
    {
        g_service.last_error = RT_EOK;
        return RT_EOK;
    }

    (void)websocket_client_disconnect();
    ret = voice_service_configure_xiaozhi_socket();
    if (ret != RT_EOK)
    {
        return ret;
    }
    voice_service_reset_xiaozhi_session_state();

    ret = websocket_client_connect();
    g_service.last_error = ret;
    if (ret == RT_EOK)
    {
        voice_service_send_xiaozhi_hello();
    }
    else
    {
        xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "小智连接中", ret);
    }
    return ret;
}

rt_err_t voice_service_submit_local_pcm(const rt_uint8_t *pcm, rt_uint32_t len)
{
    rt_uint32_t submitted_frames;

    if ((pcm == RT_NULL) || (len == 0U))
    {
        return -RT_EINVAL;
    }
    if (!g_service.initialized || !g_service.running)
    {
        return -RT_ERROR;
    }
    if (!g_service.wake_listening && !g_service.xiaozhi_listening_active)
    {
        return -RT_EBUSY;
    }
    if (len > VOICE_PCM_BUFFER_SIZE)
    {
        len = VOICE_PCM_BUFFER_SIZE;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if ((g_service.audio_buffer == RT_NULL) || (g_service.detect_buffer == RT_NULL))
    {
        rt_mutex_release(&g_service.lock);
        return -RT_ENOMEM;
    }
    g_service.audio_expected = len;
    g_service.audio_received = len;
    g_service.latest_pcm_len = len;
    g_service.latest_pcm_seq++;
    g_service.submitted_frames++;
    submitted_frames = g_service.submitted_frames;
    g_service.latest_pcm_pending = RT_TRUE;
    rt_memcpy(g_service.audio_buffer, pcm, len);
    rt_mutex_release(&g_service.lock);

    rt_sem_release(&g_service.detect_sem);
    if ((submitted_frames % VOICE_STATUS_PUBLISH_EVERY_FRAMES) == 0U)
    {
        (void)voice_service_publish_status();
    }
    return RT_EOK;
}

rt_err_t voice_service_request_capture_start(void)
{
    rt_kprintf("[voice_service] request capture start\n");
    return voice_service_send_control(VOICE_CTRL_START_CAPTURE);
}

rt_err_t voice_service_request_capture_stop(void)
{
    rt_kprintf("[voice_service] request capture stop\n");
    return voice_service_send_control(VOICE_CTRL_STOP_CAPTURE);
}

rt_err_t voice_service_request_listen_start(void)
{
    rt_kprintf("[voice_service] request listen start\n");
    return voice_service_send_control(VOICE_CTRL_START_LISTEN);
}

rt_err_t voice_service_request_listen_stop(void)
{
    rt_kprintf("[voice_service] request listen stop\n");
    return voice_service_send_control(VOICE_CTRL_STOP_LISTEN);
}

rt_err_t voice_service_dump_latest_pcm(const char *path)
{
    FILE *fp;
    rt_uint32_t len;
    rt_uint8_t *snapshot;
    size_t written;

    if ((path == RT_NULL) || (*path == '\0'))
    {
        return -RT_EINVAL;
    }

    if (g_service.audio_buffer == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    len = g_service.latest_pcm_len ? g_service.latest_pcm_len : g_service.audio_received;
    if ((len == 0U) || (len > VOICE_PCM_BUFFER_SIZE))
    {
        rt_mutex_release(&g_service.lock);
        return -RT_ERROR;
    }

    snapshot = (rt_uint8_t *)rt_malloc(len);
    if (snapshot == RT_NULL)
    {
        rt_mutex_release(&g_service.lock);
        return -RT_ENOMEM;
    }

    rt_memcpy(snapshot, g_service.audio_buffer, len);
    rt_mutex_release(&g_service.lock);

    fp = fopen(path, "wb");
    if (fp == RT_NULL)
    {
        rt_free(snapshot);
        return -RT_ERROR;
    }

    written = fwrite(snapshot, 1, len, fp);
    fclose(fp);
    rt_free(snapshot);

    if (written != len)
    {
        return -RT_ERROR;
    }

    rt_kprintf("[voice_service] latest pcm saved path=%s bytes=%lu sr=16000 ch=1 bits=16\n",
               path,
               (unsigned long)len);
    return RT_EOK;
}
