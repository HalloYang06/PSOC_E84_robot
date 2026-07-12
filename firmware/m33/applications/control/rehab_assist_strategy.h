#ifndef __REHAB_ASSIST_STRATEGY_H__
#define __REHAB_ASSIST_STRATEGY_H__

#include "rehab_adaptive_pid.h"
#include "rehab_adrc.h"

typedef struct
{
    rt_bool_t engaged;
    float adaptive_gain;
    rehab_adaptive_pid_state_t pid_state;
    rehab_adrc_state_t adrc_state;
} rehab_assist_strategy_state_t;

void rehab_assist_strategy_reset(rehab_assist_strategy_state_t *state);
void rehab_assist_strategy_step(rehab_assist_strategy_state_t *state,
                                const rehab_strategy_params_t *params,
                                const control_motor_feedback_t *fb,
                                float torque_sign,
                                rehab_strategy_output_t *out);

#endif /* __REHAB_ASSIST_STRATEGY_H__ */
