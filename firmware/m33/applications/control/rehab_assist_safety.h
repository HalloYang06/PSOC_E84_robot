#ifndef __REHAB_ASSIST_SAFETY_H__
#define __REHAB_ASSIST_SAFETY_H__

#include "rehab_strategy.h"

rt_bool_t rehab_assist_overspeed(const control_motor_feedback_t *feedback,
                                  float max_velocity_rad_s);
rt_bool_t rehab_assist_position_safe(rt_uint8_t joint_id,
                                     const control_motor_feedback_t *feedback);
rt_bool_t rehab_assist_current_direction_safe(rt_uint8_t joint_id,
                                               float current_a);

#endif /* __REHAB_ASSIST_SAFETY_H__ */
