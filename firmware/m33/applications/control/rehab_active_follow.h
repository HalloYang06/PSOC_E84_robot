#ifndef __REHAB_ACTIVE_FOLLOW_H__
#define __REHAB_ACTIVE_FOLLOW_H__

#include "rehab_strategy.h"

void rehab_active_follow_step(const rehab_strategy_params_t *params,
                              const control_motor_feedback_t *fb,
                              rehab_strategy_output_t *out);

#endif /* __REHAB_ACTIVE_FOLLOW_H__ */
