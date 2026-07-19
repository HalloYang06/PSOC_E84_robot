#ifndef M33_M55_COMM_H
#define M33_M55_COMM_H

#include <rtthread.h>
#include <rthw.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    MSG_TYPE_NONE = 0,
    MSG_TYPE_SENSOR_SNAPSHOT,
    MSG_TYPE_SENSOR_STREAM,
    MSG_TYPE_AI_INFERENCE_REQ,
    MSG_TYPE_AI_INFERENCE_RESP,
    MSG_TYPE_REHAB_ANALYSIS_REQ,
    MSG_TYPE_REHAB_ANALYSIS_RESP,
    MSG_TYPE_SYSTEM_HEARTBEAT,
    MSG_TYPE_AUDIO_DATA,
    MSG_TYPE_ASR_TEXT,
    MSG_TYPE_TTS_REQUEST,
    MSG_TYPE_TTS_AUDIO,
    MSG_TYPE_VOICE_CONTROL,
    MSG_TYPE_VOICE_CONTROL_ACK,
    MSG_TYPE_VOICE_STATUS,
    MSG_TYPE_VOICE_CONFIG,
    MSG_TYPE_VOICE_LATENCY,
    MSG_TYPE_REHAB_MODE_REQUEST = 17,
    MSG_TYPE_REHAB_MODE_RESULT = 18,
    MSG_TYPE_APP_BLE_STATUS = 19
} m33_m55_msg_type_t;

typedef enum
{
    VOICE_CONFIG_NONE = 0,
    VOICE_CONFIG_XIAOZHI_URL,
    VOICE_CONFIG_XIAOZHI_TOKEN,
    VOICE_CONFIG_XIAOZHI_RECONNECT,
    VOICE_CONFIG_XIAOZHI_TOKEN_BEGIN,
    VOICE_CONFIG_XIAOZHI_TOKEN_PART,
    VOICE_CONFIG_XIAOZHI_TOKEN_COMMIT,
    VOICE_CONFIG_XIAOZHI_TOKEN_CLEAR,
    VOICE_CONFIG_WIFI_SSID,
    VOICE_CONFIG_WIFI_PASSWORD,
    VOICE_CONFIG_WIFI_CONNECT,
    VOICE_CONFIG_WIFI_DISCONNECT,
    VOICE_CONFIG_WIFI_SAVE,
    VOICE_CONFIG_WIFI_FORGET,
    VOICE_CONFIG_WIFI_AUTO_CONNECT,
    VOICE_CONFIG_XIAOZHI_QA_TEXT
} voice_config_key_t;

typedef enum
{
    VOICE_CTRL_NONE = 0,
    VOICE_CTRL_START_CAPTURE,
    VOICE_CTRL_STOP_CAPTURE,
    VOICE_CTRL_START_LISTEN,
    VOICE_CTRL_STOP_LISTEN,
    VOICE_CTRL_PUBLISH_TEST_SNAPSHOT,
    VOICE_CTRL_PUBLISH_MOTOR7_SNAPSHOT,
    VOICE_CTRL_NET_PROBE,
    VOICE_CTRL_WIFI_DIAG,
    VOICE_CTRL_WIFI_SCAN,
    VOICE_CTRL_WHD_DIAG,
    VOICE_CTRL_M33_PCM_PROBE_ENABLE,
    VOICE_CTRL_M33_PCM_PROBE_DISABLE,
    VOICE_CTRL_M55_SPEAKER_TONE,
    VOICE_CTRL_WAKE_SET_THRESHOLD
} voice_control_cmd_t;

typedef enum
{
    MODEL_INPUT_SRC_NONE = 0,
    MODEL_INPUT_SRC_AUDIO_PCM = 1,
    MODEL_INPUT_SRC_IMU = 2,
    MODEL_INPUT_SRC_EMG = 3,
    MODEL_INPUT_SRC_HEART_RATE = 4,
    MODEL_INPUT_SRC_SPO2 = 5,
    MODEL_INPUT_SRC_SENSOR_FUSION = 6,
    MODEL_INPUT_SRC_MOTOR_FEEDBACK = 7
} model_input_source_t;

typedef enum
{
    MODEL_INPUT_FMT_NONE = 0,
    MODEL_INPUT_FMT_PCM_S16 = 1,
    MODEL_INPUT_FMT_INT16 = 2,
    MODEL_INPUT_FMT_UINT16 = 3,
    MODEL_INPUT_FMT_FLOAT32 = 4,
    MODEL_INPUT_FMT_Q15 = 5
} model_input_format_t;

typedef struct
{
    rt_uint16_t source;
    rt_uint16_t flags;
    rt_uint16_t motor_id;
    rt_uint16_t reserved0;
    float emg_ch1;
    float emg_ch2;
    rt_uint16_t heart_rate;
    rt_uint16_t spo2;
    rt_int16_t imu_data[6];
    float shoulder_angle;
    float elbow_angle;
    float lateral_position;
    rt_tick_t timestamp;
} sensor_snapshot_msg_t;

typedef struct
{
    rt_uint8_t motion_class;
    rt_uint8_t model_code;
    rt_uint8_t result_code;
    rt_uint8_t result_flags;
    float confidence;
    float fatigue_score;
    float pain_risk;
} ai_inference_msg_t;

#define M33_M55_STREAM_PAYLOAD_SIZE 16
#define AUDIO_CHUNK_SIZE 128
#define M33_M55_PCM_SHARED_CAPACITY (16000U * 2U * 2U)

typedef struct
{
    rt_uint32_t total_len;
    rt_uint32_t chunk_index;
    rt_uint32_t chunk_len;
    rt_uint8_t data[AUDIO_CHUNK_SIZE];
} audio_data_msg_t;

typedef struct
{
    rt_uint16_t source;
    rt_uint16_t format;
    rt_uint16_t channels;
    rt_uint16_t reserved0;
    rt_uint32_t sample_rate;
    rt_uint32_t frame_samples;
    rt_uint32_t total_len;
    rt_uint32_t chunk_index;
    rt_uint32_t chunk_len;
    rt_uint32_t timestamp;
    rt_uint32_t reserved1;
    rt_uint8_t data[M33_M55_STREAM_PAYLOAD_SIZE];
} sensor_stream_msg_t;

typedef struct
{
    volatile rt_uint32_t seq;
    volatile rt_uint32_t total_len;
    volatile rt_uint32_t sample_rate;
    volatile rt_uint32_t channels;
    volatile rt_uint32_t bits_per_sample;
    volatile rt_uint32_t timestamp;
    volatile rt_uint32_t reserved;
    volatile rt_uint32_t crc32;
    rt_uint8_t data[M33_M55_PCM_SHARED_CAPACITY];
} m33_m55_pcm_shared_t;

#define M33_M55_PCM_SHARED_HEADER_SIZE ((rt_uint32_t)offsetof(m33_m55_pcm_shared_t, data))

static inline void m33_m55_shared_pcm_dsb(void)
{
#if defined(__GNUC__) || defined(__clang__)
    __asm volatile ("dsb 0xF" ::: "memory");
#else
    __DSB();
#endif
}

static inline void m33_m55_shared_pcm_publish_barrier(volatile m33_m55_pcm_shared_t *shared,
                                                      rt_uint32_t payload_len)
{
    rt_uint32_t flush_len;

    if (shared == RT_NULL)
    {
        return;
    }
    if (payload_len > M33_M55_PCM_SHARED_CAPACITY)
    {
        payload_len = M33_M55_PCM_SHARED_CAPACITY;
    }

    flush_len = M33_M55_PCM_SHARED_HEADER_SIZE + payload_len;
    rt_hw_cpu_dcache_ops(RT_HW_CACHE_FLUSH, (void *)(uintptr_t)shared, (int)flush_len);
    (void)flush_len;
    m33_m55_shared_pcm_dsb();
}

static inline void m33_m55_shared_pcm_invalidate_header(volatile m33_m55_pcm_shared_t *shared)
{
    if (shared == RT_NULL)
    {
        return;
    }

    rt_hw_cpu_dcache_ops(RT_HW_CACHE_INVALIDATE,
                         (void *)(uintptr_t)shared,
                         (int)M33_M55_PCM_SHARED_HEADER_SIZE);
    m33_m55_shared_pcm_dsb();
}

static inline void m33_m55_shared_pcm_invalidate_payload(volatile m33_m55_pcm_shared_t *shared,
                                                         rt_uint32_t payload_len)
{
    if ((shared == RT_NULL) || (payload_len == 0U))
    {
        return;
    }
    if (payload_len > M33_M55_PCM_SHARED_CAPACITY)
    {
        payload_len = M33_M55_PCM_SHARED_CAPACITY;
    }

    rt_hw_cpu_dcache_ops(RT_HW_CACHE_INVALIDATE,
                         (void *)(uintptr_t)&shared->data[0],
                         (int)payload_len);
    m33_m55_shared_pcm_dsb();
}

typedef struct
{
    char text[256];
} text_msg_t;

typedef struct
{
    rt_uint32_t cmd;
    rt_uint32_t arg0;
    rt_uint32_t arg1;
} voice_control_msg_t;

#define VOICE_STATUS_FLAG_WAKE_LISTENING      0x00000001U
#define VOICE_STATUS_FLAG_WAKE_READY          0x00000002U
#define VOICE_STATUS_FLAG_LAST_WAKE           0x00000004U
#define VOICE_STATUS_FLAG_XIAOZHI_LISTENING   0x00000008U
#define VOICE_STATUS_FLAG_XIAOZHI_CONNECTED   0x00000010U
#define VOICE_STATUS_FLAG_XIAOZHI_HAS_TOKEN   0x00000020U

typedef struct
{
    rt_uint32_t key;
    char value[256];
} voice_config_msg_t;

typedef struct
{
    rt_uint32_t flags;
    rt_uint32_t submitted_frames;
    rt_uint32_t processed_windows;
    rt_uint32_t detected_count;
    rt_uint32_t latest_pcm_seq;
    rt_uint32_t latest_pcm_len;
    rt_uint32_t latest_peak;
    rt_uint32_t latest_avg_abs;
    rt_uint32_t latest_active_frames;
    rt_uint32_t latest_total_frames;
    rt_uint32_t last_wake_tick;
    rt_uint32_t wake_stage;
    rt_int32_t last_error;
    rt_int32_t xiaozhi_ws_stage;
    rt_int32_t xiaozhi_ws_errno;
    rt_uint32_t heap_total;
    rt_uint32_t heap_used;
    rt_uint32_t heap_max_used;
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
    rt_uint32_t wifi_saved;
    rt_uint32_t wifi_auto_connect;
    rt_int32_t wifi_storage_result;
    rt_int32_t lcd_init_result;
    rt_int32_t lcd_gfx_status;
    rt_int32_t lcd_mipi_status;
    rt_uint32_t lcd_frame_updates;
    rt_int32_t lcd_last_frame_status;
    rt_uint32_t lvgl_flush_count;
    rt_int32_t lvgl_last_flush_status;
    rt_uint32_t xiaozhi_token_len;
    rt_uint32_t xiaozhi_token_staging_len;
    rt_uint32_t xiaozhi_listening_bytes;
    rt_uint32_t xiaozhi_listening_chunks;
    rt_uint32_t xiaozhi_last_sent_bytes;
    rt_uint32_t xiaozhi_last_sent_chunks;
    rt_uint32_t xiaozhi_send_fail_count;
    rt_uint32_t xiaozhi_rx_text_count;
    rt_uint32_t xiaozhi_rx_binary_count;
    rt_uint32_t xiaozhi_audio_frame_len;
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
    char netdev_name[RT_NAME_MAX];
} voice_status_msg_t;

/*
 * Set VALID only when publishing one complete turn. An unobserved stage must
 * be VOICE_LATENCY_MS_UNAVAILABLE; zero means a measured 0 ms. REAL_WAKE and
 * MANUAL are mutually exclusive source labels, while QA_TEXT may be combined
 * with either source label.
 */
#define VOICE_LATENCY_MS_UNAVAILABLE   (0xFFFFFFFFUL)
#define VOICE_LATENCY_FLAG_VALID       (1UL << 0)
#define VOICE_LATENCY_FLAG_REAL_WAKE   (1UL << 1)
#define VOICE_LATENCY_FLAG_MANUAL      (1UL << 2)
#define VOICE_LATENCY_FLAG_QA_TEXT     (1UL << 3)

typedef struct
{
    rt_uint32_t turn_seq;
    rt_uint32_t flags;
    rt_uint32_t wake_to_listen_ms;
    rt_uint32_t last_voice_to_stop_ms;
    rt_uint32_t stop_to_stt_ms;
    rt_uint32_t stt_to_llm_ms;
    rt_uint32_t llm_to_tts_start_ms;
    rt_uint32_t tts_start_to_first_packet_ms;
    rt_uint32_t first_packet_to_first_write_ms;
    rt_uint32_t speech_end_to_first_write_ms;
    rt_uint32_t wake_to_first_write_ms;
} voice_latency_msg_t;

#define APP_BLE_STATUS_PROTOCOL_VERSION (1UL)

typedef struct
{
    rt_uint32_t version;
    rt_uint32_t connected;
    rt_uint32_t link_seq;
} app_ble_status_msg_t;

#define REHAB_MODE_PROTOCOL_VERSION       (3UL)
#define REHAB_MODE_SOURCE_VOICE           (1UL)
#define REHAB_MODE_ACTION_SET_MODE        (0UL)
#define REHAB_MODE_ACTION_LEVEL_UP        (1UL)
#define REHAB_MODE_ACTION_LEVEL_DOWN      (2UL)
#define REHAB_MODE_REQUEST_MODE_PASSIVE   (0UL)
#define REHAB_MODE_REQUEST_MODE_ASSIST    (3UL)
#define REHAB_MODE_REQUEST_MODE_RESIST    (4UL)
#define REHAB_MODE_JOINT_MASK             (0x38UL)
#define REHAB_MODE_MAX_TTL_MS             (500UL)

#define REHAB_MODE_RESULT_NONE            (0UL)
#define REHAB_MODE_RESULT_INVALID         (1UL)
#define REHAB_MODE_RESULT_QUEUE_FULL      (2UL)
#define REHAB_MODE_RESULT_DUPLICATE       (3UL)
#define REHAB_MODE_RESULT_STALE           (4UL)
#define REHAB_MODE_RESULT_BUSY            (5UL)
#define REHAB_MODE_RESULT_PRECONDITION    (6UL)
#define REHAB_MODE_RESULT_STOP_FAILED     (7UL)
#define REHAB_MODE_RESULT_APPLIED         (8UL)

/* M33 stamps local receive time; absolute ticks are not comparable across cores. */
typedef struct
{
    rt_uint32_t version;
    rt_uint32_t boot_epoch;
    rt_uint32_t request_id;
    rt_uint32_t source;
    rt_uint32_t mode;
    rt_uint32_t joint_mask;
    rt_uint32_t ttl_ms;
    rt_uint32_t action;
} rehab_mode_request_msg_t;

typedef struct
{
    rt_uint32_t version;
    rt_uint32_t boot_epoch;
    rt_uint32_t request_id;
    rt_uint32_t status;
    rt_uint32_t detail;
    rt_uint32_t requested_mode;
    rt_uint32_t applied_mode;
    rt_uint32_t joint_mask;
    rt_uint32_t mode_generation;
} rehab_mode_result_msg_t;

typedef struct
{
    rt_uint32_t type; /* m33_m55_msg_type_t wire value; fixed-width ABI */
    rt_uint32_t seq;
    union
    {
        sensor_snapshot_msg_t sensor_snapshot;
        sensor_stream_msg_t sensor_stream;
        ai_inference_msg_t ai_inference;
        audio_data_msg_t audio_data;
        text_msg_t text;
        voice_control_msg_t voice_control;
        voice_status_msg_t voice_status;
        voice_config_msg_t voice_config;
        voice_latency_msg_t voice_latency;
        app_ble_status_msg_t app_ble_status;
        rehab_mode_request_msg_t rehab_mode_request;
        rehab_mode_result_msg_t rehab_mode_result;
    } payload;
} m33_m55_message_t;

rt_err_t m33_m55_comm_init(void);
rt_err_t m33_m55_comm_try_publish(const m33_m55_message_t *msg);
rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg);
rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg);
extern volatile m33_m55_pcm_shared_t g_m33_m55_pcm_shared;

#ifdef __cplusplus
}
#endif

#endif
