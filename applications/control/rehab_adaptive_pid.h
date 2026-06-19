#ifndef __REHAB_ADAPTIVE_PID_H__
#define __REHAB_ADAPTIVE_PID_H__

#include "rehab_strategy.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    float integral;
    float prev_error;
    rt_bool_t has_prev_error;
} rehab_adaptive_pid_state_t;

typedef struct
{
    float load_level;
    float speed_level;
    float kp_eff;
    float ki_eff;
    float kd_eff;
    float error;
    float trim_current_a;
} rehab_adaptive_pid_observation_t;

void rehab_adaptive_pid_reset(rehab_adaptive_pid_state_t *state);
float rehab_adaptive_pid_step(rehab_adaptive_pid_state_t *state,
                              const rehab_strategy_params_t *params,
                              const rehab_adaptive_pid_profile_t *profile,
                              float error,
                              float abs_load,
                              float abs_speed,
                              float dt_s,
                              rehab_adaptive_pid_observation_t *obs);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_ADAPTIVE_PID_H__ */
