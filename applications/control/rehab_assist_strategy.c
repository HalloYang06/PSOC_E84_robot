#include "rehab_assist_strategy.h"

#include "control_layer_cfg.h"

void rehab_assist_strategy_reset(rehab_assist_strategy_state_t *state)
{
    if (state != RT_NULL)
    {
        state->engaged = RT_FALSE;
        state->adaptive_gain = 0.0f;
        rehab_adaptive_pid_reset(&state->pid_state);
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
    float pid_trim;
    rehab_adaptive_pid_observation_t pid_obs;

    if ((state == RT_NULL) || (params == RT_NULL) || (fb == RT_NULL) || (out == RT_NULL))
    {
        return;
    }

    if (torque_sign == 0.0f)
    {
        torque_sign = 1.0f;
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
    out->current_saturated = RT_FALSE;
    out->engaged = RT_FALSE;

    signed_torque = fb->torque_nm * torque_sign;
    abs_torque = rehab_strategy_absf(signed_torque);
    abs_vel = rehab_strategy_absf(fb->vel_rad_s);

    if (state->engaged)
    {
        if (abs_torque <= CONTROL_REHAB_ASSIST_TORQUE_EXIT_NM)
        {
            state->engaged = RT_FALSE;
            state->adaptive_gain = 0.0f;
            rehab_adaptive_pid_reset(&state->pid_state);
            return;
        }
    }
    else if (abs_torque < CONTROL_REHAB_ASSIST_TORQUE_ENTER_NM)
    {
        return;
    }
    else
    {
        state->engaged = RT_TRUE;
    }

    effective_gain = rehab_assist_strategy_effective_gain(state, params, abs_torque);
    current_mag = abs_torque * effective_gain;
    if (params->assist_adaptive_pid_enabled)
    {
        pid_trim = rehab_adaptive_pid_step(&state->pid_state,
                                           params,
                                           &params->assist_pid,
                                           abs_torque - params->assist_pid.target,
                                           abs_torque,
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
        rehab_adaptive_pid_reset(&state->pid_state);
    }
    out->type = REHAB_STRATEGY_OUTPUT_CURRENT;
    out->effective_gain = effective_gain;
    out->current_saturated = (current_mag >= rehab_strategy_absf(params->assist_max_current_a)) ?
                             RT_TRUE : RT_FALSE;
    out->current_a = params->follow_direction *
                     rehab_strategy_signf(signed_torque) *
                     rehab_strategy_clampf(current_mag, params->assist_max_current_a);
    out->engaged = RT_TRUE;
}
