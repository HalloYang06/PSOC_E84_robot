#ifndef __REHAB_SCURVE_H__
#define __REHAB_SCURVE_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    float start_rad;
    float end_rad;
    float distance_rad;
    float direction;
    float max_velocity_rad_s;
    float max_accel_rad_s2;
    float max_jerk_rad_s3;
    rt_uint32_t duration_ms;
} rehab_scurve_profile_t;

typedef struct
{
    float position_rad;
    float velocity_rad_s;
    float accel_rad_s2;
} rehab_scurve_sample_t;

rt_err_t rehab_scurve_plan(rehab_scurve_profile_t *profile,
                           float start_rad,
                           float end_rad,
                           float max_velocity_rad_s,
                           float max_accel_rad_s2,
                           float max_jerk_rad_s3);
rt_err_t rehab_scurve_sample(const rehab_scurve_profile_t *profile,
                             rt_uint32_t elapsed_ms,
                             rehab_scurve_sample_t *out);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_SCURVE_H__ */
