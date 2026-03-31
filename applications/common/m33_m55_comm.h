#ifndef M33_M55_COMM_H
#define M33_M55_COMM_H

#include <rtthread.h>

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
    MSG_TYPE_VOICE_CONTROL
} m33_m55_msg_type_t;

typedef enum
{
    VOICE_CTRL_NONE = 0,
    VOICE_CTRL_START_CAPTURE,
    VOICE_CTRL_STOP_CAPTURE,
    VOICE_CTRL_START_LISTEN,
    VOICE_CTRL_STOP_LISTEN
} voice_control_cmd_t;

typedef enum
{
    MODEL_INPUT_SRC_NONE = 0,
    MODEL_INPUT_SRC_AUDIO_PCM = 1,
    MODEL_INPUT_SRC_IMU = 2,
    MODEL_INPUT_SRC_EMG = 3,
    MODEL_INPUT_SRC_HEART_RATE = 4,
    MODEL_INPUT_SRC_SPO2 = 5,
    MODEL_INPUT_SRC_SENSOR_FUSION = 6
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

typedef struct
{
    m33_m55_msg_type_t type;
    rt_uint32_t seq;
    union
    {
        sensor_snapshot_msg_t sensor_snapshot;
        sensor_stream_msg_t sensor_stream;
        ai_inference_msg_t ai_inference;
        audio_data_msg_t audio_data;
        text_msg_t text;
        voice_control_msg_t voice_control;
    } payload;
} m33_m55_message_t;

rt_err_t m33_m55_comm_init(void);
rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg);
rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg);
extern volatile m33_m55_pcm_shared_t g_m33_m55_pcm_shared;

#ifdef __cplusplus
}
#endif

#endif
