#include "rehab_assist_safety.h"

#include "control_layer_cfg.h"

rt_bool_t rehab_assist_overspeed(const control_motor_feedback_t *feedback,
                                  float max_velocity_rad_s)
{
    float velocity_rad_s;

    if ((feedback == RT_NULL) || (max_velocity_rad_s <= 0.0f))
    {
        return RT_FALSE;
    }

    velocity_rad_s = feedback->vel_rad_s;
    if (velocity_rad_s < 0.0f)
    {
        velocity_rad_s = -velocity_rad_s;
    }

    return (velocity_rad_s > max_velocity_rad_s) ? RT_TRUE : RT_FALSE;
}

rt_bool_t rehab_assist_position_safe(rt_uint8_t joint_id,
                                     const control_motor_feedback_t *feedback)
{
    if (feedback == RT_NULL)
    {
        return RT_FALSE;
    }

    if (joint_id != CONTROL_REHAB_CURL_M33_JOINT)
    {
        return RT_TRUE;
    }

    return ((feedback->pos_rad >= CONTROL_REHAB_ASSIST_JOINT5_HARD_MIN_RAW_RAD) &&
            (feedback->pos_rad <= CONTROL_REHAB_ASSIST_JOINT5_HARD_MAX_RAW_RAD))
               ? RT_TRUE
               : RT_FALSE;
}

rt_bool_t rehab_assist_current_direction_safe(rt_uint8_t joint_id,
                                               float current_a)
{
    if (joint_id != CONTROL_REHAB_CURL_M33_JOINT)
    {
        return RT_TRUE;
    }

    return (current_a >= 0.0f) ? RT_TRUE : RT_FALSE;
}
