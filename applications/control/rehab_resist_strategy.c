#include "rehab_resist_strategy.h"

#include "control_layer_cfg.h"

void rehab_resist_strategy_reset(rehab_resist_strategy_state_t *state)
{
    if (state != RT_NULL)
    {
        rehab_adaptive_pid_reset(&state->pid_state);
    }
}

void rehab_resist_strategy_step(rehab_resist_strategy_state_t *state,
                                const rehab_strategy_params_t *params,
                                const control_motor_feedback_t *fb,
                                rehab_strategy_output_t *out)
{
    float abs_vel;
    float current_mag;
    float pid_trim;
    rehab_adaptive_pid_observation_t pid_obs;

    if ((state == RT_NULL) || (params == RT_NULL) || (fb == RT_NULL) || (out == RT_NULL))
    {
        return;
    }

    out->type = REHAB_STRATEGY_OUTPUT_STOP;
    out->speed_rad_s = 0.0f;
    out->limit_cur_a = params->resist_max_current_a;
    out->current_a = 0.0f;
    out->effective_gain = 0.0f;
    out->pid_kp = 0.0f;
    out->pid_ki = 0.0f;
    out->pid_kd = 0.0f;
    out->pid_load_level = 0.0f;
    out->pid_speed_level = 0.0f;
    out->pid_error = 0.0f;
    out->pid_trim_current_a = 0.0f;
    out->current_saturated = RT_FALSE;
    out->engaged = RT_FALSE;

    abs_vel = rehab_strategy_absf(fb->vel_rad_s);
    if (abs_vel < CONTROL_REHAB_RESIST_VEL_DEADBAND_RAD_S)
    {
        rehab_resist_strategy_reset(state);
        return;
    }

    current_mag = abs_vel * params->resist_current_gain_a_per_rad_s;
    if (params->resist_adaptive_pid_enabled)
    {
        pid_trim = rehab_adaptive_pid_step(&state->pid_state,
                                           params,
                                           &params->resist_pid,
                                           abs_vel - params->resist_pid.target,
                                           rehab_strategy_absf(fb->torque_nm),
                                           abs_vel,
                                           ((float)CONTROL_REHAB_SERVICE_PERIOD_MS) / 1000.0f,
                                           &pid_obs);
        current_mag += pid_trim;
        if (current_mag < 0.0f)
        {
            current_mag = 0.0f;
        }
        out->pid_kp = pid_obs.kp_eff;
        out->pid_ki = pid_obs.ki_eff;
        out->pid_kd = pid_obs.kd_eff;
        out->pid_load_level = pid_obs.load_level;
        out->pid_speed_level = pid_obs.speed_level;
        out->pid_error = pid_obs.error;
        out->pid_trim_current_a = pid_obs.trim_current_a;
    }
    else
    {
        rehab_resist_strategy_reset(state);
    }

    out->type = REHAB_STRATEGY_OUTPUT_CURRENT;
    out->effective_gain = params->resist_current_gain_a_per_rad_s;
    out->current_saturated = (current_mag >= rehab_strategy_absf(params->resist_max_current_a)) ?
                             RT_TRUE : RT_FALSE;
    out->current_a = -params->resist_direction *
                     rehab_strategy_signf(fb->vel_rad_s) *
                     rehab_strategy_clampf(current_mag, params->resist_max_current_a);
    out->engaged = RT_TRUE;
}
