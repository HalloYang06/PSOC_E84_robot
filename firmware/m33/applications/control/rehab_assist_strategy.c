#include "rehab_assist_strategy.h"

#include "control_layer_cfg.h"

void rehab_assist_strategy_reset(rehab_assist_strategy_state_t *state)
{
    if (state != RT_NULL)
    {
        state->engaged = RT_FALSE;
        state->adaptive_gain = 0.0f;
        state->last_current_a = 0.0f;
        rehab_adaptive_pid_reset(&state->pid_state);
        rehab_adrc_reset(&state->adrc_state);
    }
}

static float rehab_assist_strategy_rate_limit(float target, float current, float step)
{
    if (step <= 0.0f)
    {
        return target;
    }
    if (current <= 0.0f)
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

static float rehab_assist_strategy_effective_gain(rehab_assist_strategy_state_t *state,
                                                  const rehab_strategy_params_t *params,
                                                  float abs_torque)
{
    float target_gain;

    if (!params->adaptive_assist_enabled)
    {
        state->adaptive_gain = params->assist_current_gain_a_per_nm;
        return params->assist_current_gain_a_per_nm;
    }

    target_gain = params->adaptive_assist_base_gain_a_per_nm +
                  (abs_torque * params->adaptive_assist_load_gain_a_per_nm2);
    target_gain = rehab_strategy_clampf(target_gain,
                                        params->adaptive_assist_max_gain_a_per_nm);
    if (target_gain < 0.0f)
    {
        target_gain = 0.0f;
    }

    state->adaptive_gain =
        rehab_assist_strategy_rate_limit(target_gain,
                                         state->adaptive_gain,
                                         params->adaptive_assist_gain_step_a_per_nm);
    return state->adaptive_gain;
}

static float rehab_assist_strategy_slew(float target, float current, float step)
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

void rehab_assist_strategy_step(rehab_assist_strategy_state_t *state,
                                const rehab_strategy_params_t *params,
                                const control_motor_feedback_t *fb,
                                float torque_sign,
                                rehab_strategy_output_t *out)
{
    float signed_torque;
    float abs_torque;
    float abs_vel;
    float current_mag;
    float effective_gain;
    float assist_direction;
    float trigger_sign;
    float pid_error;
    float pid_trim;
    float adrc_trim;
    float dt_s;
    rt_bool_t torque_engaged;
    rt_bool_t velocity_engaged;
    rehab_adaptive_pid_observation_t pid_obs;
    rehab_adrc_observation_t adrc_obs;

    if ((state == RT_NULL) || (params == RT_NULL) || (fb == RT_NULL) || (out == RT_NULL))
    {
        return;
    }

    if (torque_sign == 0.0f)
    {
        torque_sign = 1.0f;
    }
    assist_direction = params->assist_direction;
    if (assist_direction == 0.0f)
    {
        assist_direction = params->follow_direction;
    }

    out->type = REHAB_STRATEGY_OUTPUT_STOP;
    out->speed_rad_s = 0.0f;
    out->limit_cur_a = params->assist_max_current_a;
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

    signed_torque = fb->torque_nm * torque_sign;
    abs_torque = rehab_strategy_absf(signed_torque);
    abs_vel = rehab_strategy_absf(fb->vel_rad_s);
    torque_engaged = RT_FALSE;
    velocity_engaged = RT_FALSE;

    if (state->engaged && (abs_torque > CONTROL_REHAB_ASSIST_TORQUE_EXIT_NM))
    {
        torque_engaged = RT_TRUE;
    }
    else if (!state->engaged && (abs_torque >= CONTROL_REHAB_ASSIST_TORQUE_ENTER_NM))
    {
        torque_engaged = RT_TRUE;
    }

    if (params->assist_velocity_fallback_enabled)
    {
        if (state->engaged && (abs_vel > params->assist_velocity_exit_rad_s))
        {
            velocity_engaged = RT_TRUE;
        }
        else if (!state->engaged && (abs_vel >= params->assist_velocity_enter_rad_s))
        {
            velocity_engaged = RT_TRUE;
        }
    }

    if (!torque_engaged && !velocity_engaged)
    {
        state->engaged = RT_FALSE;
        state->adaptive_gain = 0.0f;
        state->last_current_a = 0.0f;
        rehab_adaptive_pid_reset(&state->pid_state);
        rehab_adrc_reset(&state->adrc_state);
        return;
    }

    state->engaged = RT_TRUE;

    if (torque_engaged)
    {
        effective_gain = rehab_assist_strategy_effective_gain(state, params, abs_torque);
        current_mag = abs_torque * effective_gain;
        trigger_sign = rehab_strategy_signf(signed_torque);
        pid_error = abs_torque - params->assist_pid.target;
    }
    else
    {
        rehab_adrc_reset(&state->adrc_state);
        effective_gain = params->assist_velocity_gain_a_per_rad_s;
        current_mag = params->assist_min_current_a;
        if (abs_vel > params->assist_velocity_enter_rad_s)
        {
            current_mag +=
                ((abs_vel - params->assist_velocity_enter_rad_s) *
                 params->assist_velocity_gain_a_per_rad_s);
        }
        trigger_sign = rehab_strategy_signf(fb->vel_rad_s);
        pid_error = abs_vel - params->assist_velocity_enter_rad_s;
    }

    dt_s = ((float)CONTROL_REHAB_SERVICE_PERIOD_MS) / 1000.0f;
    if (params->assist_adaptive_pid_enabled)
    {
        pid_trim = rehab_adaptive_pid_step(&state->pid_state,
                                           params,
                                           &params->assist_pid,
                                           pid_error,
                                           abs_torque,
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

    if (torque_engaged && params->assist_adrc_enabled)
    {
        adrc_trim = rehab_adrc_step(&state->adrc_state,
                                    &params->assist_adrc,
                                    abs_torque,
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
    out->effective_gain = effective_gain;
    out->current_saturated = (current_mag >= rehab_strategy_absf(params->assist_max_current_a)) ?
                             RT_TRUE : RT_FALSE;
    out->current_a = assist_direction *
                     trigger_sign *
                     rehab_strategy_clampf(current_mag, params->assist_max_current_a);
    out->current_a = rehab_assist_strategy_slew(out->current_a,
                                                state->last_current_a,
                                                params->assist_slew_current_a_per_step);
    out->current_a = rehab_strategy_clampf(out->current_a,
                                           params->assist_max_current_a);
    state->last_current_a = out->current_a;
    out->engaged = RT_TRUE;
}
