#include "rehab_adaptive_pid.h"

void rehab_adaptive_pid_reset(rehab_adaptive_pid_state_t *state)
{
    if (state != RT_NULL)
    {
        state->integral = 0.0f;
        state->prev_error = 0.0f;
        state->has_prev_error = RT_FALSE;
    }
}

static float rehab_adaptive_pid_level(float value, float low, float high)
{
    if (high <= low)
    {
        return (value >= high) ? 1.0f : 0.0f;
    }
    if (value <= low)
    {
        return 0.0f;
    }
    if (value >= high)
    {
        return 1.0f;
    }
    return (value - low) / (high - low);
}

static float rehab_adaptive_pid_clampf(float value, float limit)
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

float rehab_adaptive_pid_step(rehab_adaptive_pid_state_t *state,
                              const rehab_strategy_params_t *params,
                              const rehab_adaptive_pid_profile_t *profile,
                              float error,
                              float abs_load,
                              float abs_speed,
                              float dt_s,
                              rehab_adaptive_pid_observation_t *obs)
{
    float load_level;
    float speed_level;
    float kp_eff;
    float ki_eff;
    float kd_eff;
    float derivative;
    float integral;
    float raw_trim;
    float trim;

    if (obs != RT_NULL)
    {
        rt_memset(obs, 0, sizeof(*obs));
    }
    if ((state == RT_NULL) || (params == RT_NULL) || (profile == RT_NULL))
    {
        return 0.0f;
    }
    if (dt_s <= 0.0f)
    {
        dt_s = 0.001f;
    }

    load_level = rehab_adaptive_pid_level(abs_load,
                                          params->adaptive_pid_load_low_nm,
                                          params->adaptive_pid_load_high_nm);
    speed_level = rehab_adaptive_pid_level(abs_speed,
                                           params->adaptive_pid_speed_low_rad_s,
                                           params->adaptive_pid_speed_high_rad_s);

    kp_eff = profile->kp_base +
             (load_level * profile->kp_load) +
             (speed_level * profile->kp_speed);
    ki_eff = profile->ki_base +
             (load_level * profile->ki_load) -
             (speed_level * profile->ki_speed_reduce);
    kd_eff = profile->kd_base +
             (speed_level * profile->kd_speed);

    if (kp_eff < 0.0f)
    {
        kp_eff = 0.0f;
    }
    if (ki_eff < 0.0f)
    {
        ki_eff = 0.0f;
    }
    if (kd_eff < 0.0f)
    {
        kd_eff = 0.0f;
    }

    derivative = state->has_prev_error ?
                 ((error - state->prev_error) / dt_s) :
                 0.0f;
    integral = state->integral + (error * dt_s);
    integral = rehab_adaptive_pid_clampf(integral, profile->integral_limit);

    raw_trim = (kp_eff * error) +
               (ki_eff * integral) +
               (kd_eff * derivative);
    trim = rehab_adaptive_pid_clampf(raw_trim, profile->trim_limit);

    state->integral = integral;
    state->prev_error = error;
    state->has_prev_error = RT_TRUE;

    if (obs != RT_NULL)
    {
        obs->load_level = load_level;
        obs->speed_level = speed_level;
        obs->kp_eff = kp_eff;
        obs->ki_eff = ki_eff;
        obs->kd_eff = kd_eff;
        obs->error = error;
        obs->trim_current_a = trim;
    }

    return trim;
}
