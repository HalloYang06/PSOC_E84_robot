#ifndef __REHAB_TRAJECTORY_BANK_H__
#define __REHAB_TRAJECTORY_BANK_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    rt_uint16_t dt_ms;
    float pos_rad;
    float vel_rad_s;
    float torque_nm;
} rehab_trajectory_sample_t;

void rehab_trajectory_bank_init(void);
rt_err_t rehab_trajectory_bank_clear(rt_uint8_t slot);
rt_err_t rehab_trajectory_bank_append(rt_uint8_t slot,
                                      const rehab_trajectory_sample_t *sample);
rt_err_t rehab_trajectory_bank_get(rt_uint8_t slot,
                                   rt_uint16_t index,
                                   rehab_trajectory_sample_t *out);
rt_uint16_t rehab_trajectory_bank_count(rt_uint8_t slot);
rt_bool_t rehab_trajectory_bank_has_data(rt_uint8_t slot);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_TRAJECTORY_BANK_H__ */
