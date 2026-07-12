#ifndef __REHAB_ADRC_H__
#define __REHAB_ADRC_H__

#include "rehab_strategy.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    float z1;
    float z2;
    float z3;
    float last_trim;
    rt_bool_t initialized;
} rehab_adrc_state_t;

typedef struct
{
    float error;
    float z1;
    float z2;
    float z3;
    float trim_current_a;
} rehab_adrc_observation_t;

void rehab_adrc_reset(rehab_adrc_state_t *state);
float rehab_adrc_step(rehab_adrc_state_t *state,
                      const rehab_adrc_profile_t *profile,
                      float measurement,
                      float dt_s,
                      rehab_adrc_observation_t *obs);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_ADRC_H__ */
