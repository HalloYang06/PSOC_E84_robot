#ifndef __REHAB_SERVICE_H__
#define __REHAB_SERVICE_H__

#include <rtthread.h>

#include "rehab_joint_map.h"
#include "rehab_strategy.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    REHAB_DEMO_MODE_PASSIVE = 0,
    REHAB_DEMO_MODE_ACTIVE_FOLLOW,
    REHAB_DEMO_MODE_ASSIST,
    REHAB_DEMO_MODE_RESIST,
    REHAB_DEMO_MODE_MEMORY_RECORD,
    REHAB_DEMO_MODE_MEMORY_PLAYBACK,
} rehab_demo_mode_t;

typedef enum
{
    REHAB_CMD_SOURCE_BENCH_MSH = 0,
    REHAB_CMD_SOURCE_CAN,
} rehab_cmd_source_t;

typedef enum
{
    REHAB_SERVICE_STATUS_FLAG_FRESH = 0x01U,
    REHAB_SERVICE_STATUS_FLAG_ASSIST_ENGAGED = 0x02U,
    REHAB_SERVICE_STATUS_FLAG_RECORDING = 0x04U,
    REHAB_SERVICE_STATUS_FLAG_PLAYING = 0x08U,
    REHAB_SERVICE_STATUS_FLAG_FAULT = 0x10U,
} rehab_service_status_flag_t;

typedef struct
{
    rehab_demo_mode_t mode;
    rehab_cmd_source_t source;
    rehab_joint_id_t joint;
    rt_uint8_t m33_joint_id;
    rt_uint8_t detail;
    rt_uint8_t flags;
    rt_bool_t feedback_fresh;
    rt_bool_t assist_engaged;
    float feedback_torque_nm;
    float feedback_vel_rad_s;
    float output_current_a;
    float output_limit_current_a;
    float effective_gain;
    float pid_kp;
    float pid_ki;
    float pid_kd;
    float pid_load_level;
    float pid_speed_level;
    float pid_error;
    float pid_trim_current_a;
    float adrc_error;
    float adrc_z1;
    float adrc_z2;
    float adrc_z3;
    float adrc_trim_current_a;
    rt_bool_t output_saturated;
    rt_uint8_t sequence;
    rt_uint8_t active_slot;
    rt_uint16_t record_count;
    rt_uint16_t playback_index;
    rt_err_t last_result;
    rt_tick_t timestamp;
} rehab_service_status_t;

rt_err_t rehab_service_init(void);
rt_err_t rehab_service_set_mode(rehab_demo_mode_t mode,
                                rehab_joint_id_t joint,
                                rehab_cmd_source_t source);
rt_err_t rehab_service_set_mode_on_m33(rehab_demo_mode_t mode,
                                       rehab_joint_id_t joint,
                                       rt_uint8_t m33_joint_id,
                                       rehab_cmd_source_t source);
rt_err_t rehab_service_stop(rehab_cmd_source_t source);

rt_err_t rehab_service_record_start(rt_uint8_t slot,
                                    rehab_joint_id_t joint,
                                    rehab_cmd_source_t source);
rt_err_t rehab_service_record_start_on_m33(rt_uint8_t slot,
                                           rehab_joint_id_t joint,
                                           rt_uint8_t m33_joint_id,
                                           rehab_cmd_source_t source);
rt_err_t rehab_service_record_stop(rehab_cmd_source_t source);
rt_err_t rehab_service_play_start(rt_uint8_t slot,
                                  rehab_joint_id_t joint,
                                  rehab_cmd_source_t source);
rt_err_t rehab_service_play_start_on_m33(rt_uint8_t slot,
                                         rehab_joint_id_t joint,
                                         rt_uint8_t m33_joint_id,
                                         rehab_cmd_source_t source);
rt_err_t rehab_service_play_stop(rehab_cmd_source_t source);

rt_err_t rehab_service_get_params(rehab_strategy_params_t *out);
rt_err_t rehab_service_set_params(const rehab_strategy_params_t *params);
void rehab_service_get_status(rehab_service_status_t *out);
rt_bool_t rehab_service_accepts_ros_target(void);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_SERVICE_H__ */
