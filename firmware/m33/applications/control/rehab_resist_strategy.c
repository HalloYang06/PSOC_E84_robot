#include "rehab_resist_strategy.h"

#include "control_layer_cfg.h"

void rehab_resist_strategy_reset(rehab_resist_strategy_state_t *state)
{
    if (state != RT_NULL)
    {
        state->last_current_a = 0.0f;
        rehab_adaptive_pid_reset(&state->pid_state);
        rehab_adrc_reset(&state->adrc_state);
    }
}

static float rehab_resist_strategy_slew(float target, float current, float step)
{
    if (step <= 0.0f)
    {
        return target;
    }
    if (target > (current + step))
    {
        return current + step;
    }
    if (target < (current - step))
    {
        return current - step;
    }
    return target;
}

void rehab_resist_strategy_step(rehab_resist_strategy_state_t *state,
                                const rehab_strategy_params_t *params,
                                const control_motor_feedback_t *fb,
                                rehab_strategy_output_t *out)
{
    float abs_vel;
    float current_mag;
    float pid_trim;
    float adrc_trim;
    float dt_s;
    rehab_adaptive_pid_observation_t pid_obs;
    rehab_adrc_observation_t adrc_obs;

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
    out->adrc_error = 0.0f;
    out->adrc_z1 = 0.0f;
    out->adrc_z2 = 0.0f;
    out->adrc_z3 = 0.0f;
    out->adrc_trim_current_a = 0.0f;
    out->current_saturated = RT_FALSE;
    out->engaged = RT_FALSE;

    abs_vel = rehab_strategy_absf(fb->vel_rad_s);
    if (abs_vel < CONTROL_REHAB_RESIST_VEL_DEADBAND_RAD_S)
    {
        rehab_resist_strategy_reset(state);
        return;
    }

    current_mag = abs_vel * params->resist_current_gain_a_per_rad_s;
    dt_s = ((float)CONTROL_REHAB_SERVICE_PERIOD_MS) / 1000.0f;
    if (params->resist_adaptive_pid_enabled)
    {
        pid_trim = rehab_adaptive_pid_step(&state->pid_state,
                                           params,
                                           &params->resist_pid,
                                           abs_vel - params->resist_pid.target,
                                           rehab_strategy_absf(fb->torque_nm),
                                           abs_vel,
                                           dt_s,
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
        rehab_adaptive_pid_reset(&state->pid_state);
    }

    if (params->resist_adrc_enabled)
    {
        adrc_trim = rehab_adrc_step(&state->adrc_state,
                                    &params->resist_adrc,
                                    abs_vel,
                                    dt_s,
                                    &adrc_obs);
        current_mag += adrc_trim;
        if (current_mag < 0.0f)
        {
            current_mag = 0.0f;
        }
        out->adrc_error = adrc_obs.error;
        out->adrc_z1 = adrc_obs.z1;
        out->adrc_z2 = adrc_obs.z2;
        out->adrc_z3 = adrc_obs.z3;
        out->adrc_trim_current_a = adrc_obs.trim_current_a;
    }
    else
    {
        rehab_adrc_reset(&state->adrc_state);
    }

    out->type = REHAB_STRATEGY_OUTPUT_CURRENT;
    out->effective_gain = params->resist_current_gain_a_per_rad_s;
    out->current_saturated = (current_mag >= rehab_strategy_absf(params->resist_max_current_a)) ?
                             RT_TRUE : RT_FALSE;
    out->current_a = -params->resist_direction *
                     rehab_strategy_signf(fb->vel_rad_s) *
                     rehab_strategy_clampf(current_mag, params->resist_max_current_a);
    out->current_a = rehab_resist_strategy_slew(out->current_a,
                                                state->last_current_a,
                                                CONTROL_REHAB_RESIST_SLEW_A_PER_STEP);
    out->current_a = rehab_strategy_clampf(out->current_a,
                                           params->resist_max_current_a);
    state->last_current_a = out->current_a;
    out->engaged = RT_TRUE;
}
