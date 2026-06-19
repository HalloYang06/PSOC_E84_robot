#include "rehab_active_follow.h"

#include "control_layer_cfg.h"

void rehab_active_follow_step(const rehab_strategy_params_t *params,
                              const control_motor_feedback_t *fb,
                              rehab_strategy_output_t *out)
{
    float abs_torque;
    float abs_vel;
    float current_sign = 0.0f;
    float current_mag;

    if ((params == RT_NULL) || (fb == RT_NULL) || (out == RT_NULL))
    {
        return;
    }

    out->type = REHAB_STRATEGY_OUTPUT_STOP;
    out->speed_rad_s = 0.0f;
    out->limit_cur_a = params->active_max_current_a;
    out->current_a = 0.0f;
    out->effective_gain = 0.0f;
    out->current_saturated = RT_FALSE;
    out->engaged = RT_FALSE;

    abs_torque = rehab_strategy_absf(fb->torque_nm);
    abs_vel = rehab_strategy_absf(fb->vel_rad_s);
    if (abs_torque >= CONTROL_REHAB_ACTIVE_TORQUE_DEADBAND_NM)
    {
        current_sign = rehab_strategy_signf(fb->torque_nm);
        current_mag = params->active_min_current_a +
                      ((abs_torque - CONTROL_REHAB_ACTIVE_TORQUE_DEADBAND_NM) *
                       params->active_current_gain_a_per_nm);
        out->effective_gain = params->active_current_gain_a_per_nm;
    }
    else if (abs_vel >= CONTROL_REHAB_ACTIVE_VEL_DEADBAND_RAD_S)
    {
        current_sign = rehab_strategy_signf(fb->vel_rad_s);
        current_mag = params->active_min_current_a;
        out->effective_gain = params->active_current_gain_a_per_nm;
    }
    else
    {
        return;
    }

    out->type = REHAB_STRATEGY_OUTPUT_CURRENT;
    out->current_saturated = (current_mag >= rehab_strategy_absf(params->active_max_current_a)) ?
                             RT_TRUE : RT_FALSE;
    out->current_a = params->follow_direction *
                     current_sign *
                     rehab_strategy_clampf(current_mag, params->active_max_current_a);
    out->engaged = RT_TRUE;
}
