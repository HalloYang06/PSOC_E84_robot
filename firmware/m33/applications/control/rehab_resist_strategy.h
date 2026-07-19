#ifndef __REHAB_RESIST_STRATEGY_H__
#define __REHAB_RESIST_STRATEGY_H__

#include "rehab_adaptive_pid.h"
#include "rehab_adrc.h"

typedef struct
{
    float last_current_a;
    rehab_adaptive_pid_state_t pid_state;
    rehab_adrc_state_t adrc_state;
} rehab_resist_strategy_state_t;

void rehab_resist_strategy_reset(rehab_resist_strategy_state_t *state);
void rehab_resist_strategy_step(rehab_resist_strategy_state_t *state,
                                const rehab_strategy_params_t *params,
                                const control_motor_feedback_t *fb,
                                rehab_strategy_output_t *out);

#endif /* __REHAB_RESIST_STRATEGY_H__ */
