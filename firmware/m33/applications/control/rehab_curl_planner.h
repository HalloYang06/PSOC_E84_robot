#ifndef __REHAB_CURL_PLANNER_H__
#define __REHAB_CURL_PLANNER_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    REHAB_CURL_PHASE_IDLE = 0,
    REHAB_CURL_PHASE_MOVE_TOP,
    REHAB_CURL_PHASE_DWELL_TOP,
    REHAB_CURL_PHASE_MOVE_BOTTOM,
    REHAB_CURL_PHASE_DWELL_BOTTOM,
    REHAB_CURL_PHASE_FAULT,
} rehab_curl_phase_t;

typedef enum
{
    REHAB_CURL_RESULT_OK = 0,
    REHAB_CURL_RESULT_INVALID_CONFIG,
    REHAB_CURL_RESULT_STALE_FEEDBACK,
    REHAB_CURL_RESULT_MOTOR_FAULT,
    REHAB_CURL_RESULT_HARD_LIMIT,
    REHAB_CURL_RESULT_OVERSPEED,
    REHAB_CURL_RESULT_SEGMENT_TIMEOUT,
} rehab_curl_result_t;

typedef enum
{
    REHAB_CURL_ACTION_NONE = 0,
    REHAB_CURL_ACTION_COMMAND_POSITION,
    REHAB_CURL_ACTION_STOP_FAULT,
} rehab_curl_action_t;

typedef struct
{
    float hard_min_pos_rad;
    float hard_max_pos_rad;
    float top_target_pos_rad;
    float bottom_target_pos_rad;
    float position_tolerance_rad;
    float max_feedback_velocity_rad_s;
    rt_uint32_t dwell_ms;
    rt_uint32_t segment_timeout_ms;
    rt_uint32_t command_refresh_ms;
    rt_uint8_t arrival_samples;
} rehab_curl_config_t;

typedef struct
{
    rehab_curl_phase_t phase;
    rehab_curl_result_t fault;
    rehab_curl_config_t config;
    rt_uint32_t phase_started_ms;
    rt_uint32_t last_command_ms;
    rt_uint32_t completed_repetitions;
    rt_uint8_t arrival_count;
    rt_bool_t command_pending;
} rehab_curl_planner_t;

typedef struct
{
    rehab_curl_action_t action;
    rehab_curl_result_t result;
    rehab_curl_phase_t phase;
    float target_pos_rad;
    rt_uint32_t completed_repetitions;
} rehab_curl_output_t;

rehab_curl_result_t rehab_curl_planner_start(rehab_curl_planner_t *planner,
                                               const rehab_curl_config_t *config,
                                               float feedback_pos_rad,
                                               float feedback_vel_rad_s,
                                               rt_uint32_t now_ms);
void rehab_curl_planner_step(rehab_curl_planner_t *planner,
                             float feedback_pos_rad,
                             float feedback_vel_rad_s,
                             rt_bool_t feedback_fresh,
                             rt_bool_t motor_fault,
                             rt_uint32_t now_ms,
                             rehab_curl_output_t *output);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_CURL_PLANNER_H__ */
