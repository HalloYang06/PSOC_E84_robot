#ifndef __REHAB_STRATEGY_H__
#define __REHAB_STRATEGY_H__

#include <rtthread.h>

#include "control_layer.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    REHAB_STRATEGY_OUTPUT_STOP = 0,
    REHAB_STRATEGY_OUTPUT_SPEED,
    REHAB_STRATEGY_OUTPUT_CURRENT,
} rehab_strategy_output_type_t;

typedef struct
{
    float target;
    float kp_base;
    float kp_load;
    float kp_speed;
    float ki_base;
    float ki_load;
    float ki_speed_reduce;
    float kd_base;
    float kd_speed;
    float integral_limit;
    float trim_limit;
} rehab_adaptive_pid_profile_t;

typedef struct
{
    float target;
    float b0;
    float beta1;
    float beta2;
    float beta3;
    float kp;
    float kd;
    float disturbance_gain;
    float trim_limit;
} rehab_adrc_profile_t;

typedef struct
{
    float follow_direction;
    float assist_direction;
    float resist_direction;
    float active_min_current_a;
    float active_max_current_a;
    float active_current_gain_a_per_nm;
    float assist_max_current_a;
    float assist_current_gain_a_per_nm;
    rt_bool_t assist_velocity_fallback_enabled;
    float assist_velocity_enter_rad_s;
    float assist_velocity_exit_rad_s;
    float assist_min_current_a;
    float assist_velocity_gain_a_per_rad_s;
    float assist_slew_current_a_per_step;
    rt_bool_t adaptive_assist_enabled;
    float adaptive_assist_base_gain_a_per_nm;
    float adaptive_assist_load_gain_a_per_nm2;
    float adaptive_assist_max_gain_a_per_nm;
    float adaptive_assist_gain_step_a_per_nm;
    rt_bool_t assist_adaptive_pid_enabled;
    rt_bool_t resist_adaptive_pid_enabled;
    rt_bool_t assist_adrc_enabled;
    rt_bool_t resist_adrc_enabled;
    float adaptive_pid_load_low_nm;
    float adaptive_pid_load_high_nm;
    float adaptive_pid_speed_low_rad_s;
    float adaptive_pid_speed_high_rad_s;
    rehab_adaptive_pid_profile_t assist_pid;
    rehab_adaptive_pid_profile_t resist_pid;
    rehab_adrc_profile_t assist_adrc;
    rehab_adrc_profile_t resist_adrc;
    float resist_max_current_a;
    float resist_current_gain_a_per_rad_s;
} rehab_strategy_params_t;

typedef struct
{
    rehab_strategy_output_type_t type;
    float speed_rad_s;
    float limit_cur_a;
    float current_a;
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
    rt_bool_t current_saturated;
    rt_bool_t engaged;
} rehab_strategy_output_t;

static inline float rehab_strategy_absf(float value)
{
    return (value >= 0.0f) ? value : -value;
}

static inline float rehab_strategy_signf(float value)
{
    return (value >= 0.0f) ? 1.0f : -1.0f;
}

static inline float rehab_strategy_clampf(float value, float limit)
{
    if (limit < 0.0f)
    {
        limit = -limit;
    }
    if (value > limit)
    {
        return limit;
    }
    if (value < -limit)
    {
        return -limit;
    }
    return value;
}

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_STRATEGY_H__ */
