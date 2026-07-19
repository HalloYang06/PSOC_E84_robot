#ifndef __REHAB_SERVICE_H__
#define __REHAB_SERVICE_H__

#include <rtthread.h>

#include "rehab_fixed_action.h"
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
    REHAB_DEMO_MODE_CURL,
    REHAB_DEMO_MODE_FIXED_ACTION,
} rehab_demo_mode_t;

typedef enum
{
    REHAB_CMD_SOURCE_BENCH_MSH = 0,
    REHAB_CMD_SOURCE_CAN,
    REHAB_CMD_SOURCE_VOICE,
    REHAB_CMD_SOURCE_APP_BLE,
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
    rt_uint8_t active_joint_mask;
    rt_uint8_t detail;
    rt_uint8_t last_fault_joint;
    rt_uint8_t last_fault_stage;
    rt_uint16_t last_fault_feedback_age_ms;
    float last_fault_velocity_rad_s;
    rt_uint8_t flags;
    rt_uint8_t assist_engaged_mask;
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
    rt_uint32_t worker_cycle_count;
    rt_tick_t worker_last_tick;
    rt_uint32_t worker_max_jitter_ms;
    rt_uint32_t mode_generation;
    rt_uint8_t curl_phase;
    rt_uint32_t curl_repetitions;
    rt_uint8_t fixed_action_id;
    rt_uint8_t fixed_action_state;
    rt_uint32_t fixed_action_repetitions;
    rt_err_t fixed_action_fault;
} rehab_service_status_t;

rt_err_t rehab_service_init(void);
rt_err_t rehab_service_set_mode(rehab_demo_mode_t mode,
                                rehab_joint_id_t joint,
                                rehab_cmd_source_t source);
rt_err_t rehab_service_set_mode_mask(rehab_demo_mode_t mode,
                                     rt_uint8_t active_joint_mask,
                                     rehab_cmd_source_t source);
rt_err_t rehab_service_set_mode_mask_if_unchanged(
    rehab_demo_mode_t mode,
    rt_uint8_t active_joint_mask,
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation);
rt_err_t rehab_service_curl_start_if_unchanged(
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation);
rt_err_t rehab_service_fixed_action_start_if_unchanged(
    rehab_fixed_action_id_t action,
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation);
rt_err_t rehab_service_set_mode_on_m33(rehab_demo_mode_t mode,
                                       rehab_joint_id_t joint,
                                       rt_uint8_t m33_joint_id,
                                       rehab_cmd_source_t source);
rt_err_t rehab_service_stop(rehab_cmd_source_t source);
rt_err_t rehab_service_stop_if_owned(rehab_cmd_source_t expected_source,
                                     rt_uint32_t expected_generation,
                                     rt_uint8_t success_detail);

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
rt_err_t rehab_service_get_intensity_level(rehab_demo_mode_t mode,
                                           rt_uint8_t *level,
                                           float *current_a);
rt_err_t rehab_service_set_intensity_level(rehab_demo_mode_t mode,
                                           rt_uint8_t level,
                                           rehab_cmd_source_t source,
                                           rt_uint8_t *applied_level);
rt_err_t rehab_service_adjust_intensity_level(rehab_demo_mode_t mode,
                                              rt_int8_t delta,
                                              rehab_cmd_source_t source,
                                              rt_uint8_t *applied_level);
void rehab_service_get_status(rehab_service_status_t *out);
rt_bool_t rehab_service_accepts_ros_target(void);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_SERVICE_H__ */
