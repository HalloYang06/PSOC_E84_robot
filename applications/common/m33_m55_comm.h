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
    MSG_TYPE_AI_INFERENCE_REQ,
    MSG_TYPE_AI_INFERENCE_RESP,
    MSG_TYPE_REHAB_ANALYSIS_REQ,
    MSG_TYPE_REHAB_ANALYSIS_RESP,
    MSG_TYPE_SYSTEM_HEARTBEAT
} m33_m55_msg_type_t;

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

typedef struct
{
    m33_m55_msg_type_t type;
    rt_uint32_t seq;
    union
    {
        sensor_snapshot_msg_t sensor_snapshot;
        ai_inference_msg_t ai_inference;
    } payload;
} m33_m55_message_t;

rt_err_t m33_m55_comm_init(void);
rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg);
rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg);

#ifdef __cplusplus
}
#endif

#endif
