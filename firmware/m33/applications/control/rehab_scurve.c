#include "rehab_scurve.h"

#ifndef RT_ERROR
#define RT_ERROR 1
#endif

static float scurve_abs(float value)
{
    return (value < 0.0f) ? -value : value;
}

static rt_bool_t scurve_limits_valid(float max_velocity_rad_s,
                                     float max_accel_rad_s2,
                                     float max_jerk_rad_s3)
{
    return ((max_velocity_rad_s > 0.0f) &&
            (max_accel_rad_s2 > 0.0f) &&
            (max_jerk_rad_s3 > 0.0f))
               ? RT_TRUE
               : RT_FALSE;
}

static float scurve_norm_pos(float u)
{
    float u2 = u * u;
    float u3 = u2 * u;
    float u4 = u3 * u;
    float u5 = u4 * u;

    return (10.0f * u3) - (15.0f * u4) + (6.0f * u5);
}

static float scurve_norm_vel(float u)
{
    float u2 = u * u;
    float u3 = u2 * u;
    float u4 = u3 * u;

    return (30.0f * u2) - (60.0f * u3) + (30.0f * u4);
}

static float scurve_norm_accel(float u)
{
    float u2 = u * u;

    return (60.0f * u) - (180.0f * u2) + (120.0f * u2 * u);
}

rt_err_t rehab_scurve_plan(rehab_scurve_profile_t *profile,
                           float start_rad,
                           float end_rad,
                           float max_velocity_rad_s,
                           float max_accel_rad_s2,
                           float max_jerk_rad_s3)
{
    float distance;
    float duration_s;
    rt_uint32_t duration_ms;

    if ((profile == RT_NULL) ||
        !scurve_limits_valid(max_velocity_rad_s,
                             max_accel_rad_s2,
                             max_jerk_rad_s3))
    {
        return -RT_ERROR;
    }

    rt_memset(profile, 0, sizeof(*profile));
    distance = scurve_abs(end_rad - start_rad);
    profile->start_rad = start_rad;
    profile->end_rad = end_rad;
    profile->distance_rad = distance;
    profile->direction = (end_rad >= start_rad) ? 1.0f : -1.0f;
    profile->max_velocity_rad_s = max_velocity_rad_s;
    profile->max_accel_rad_s2 = max_accel_rad_s2;
    profile->max_jerk_rad_s3 = max_jerk_rad_s3;

    if (distance <= 0.000001f)
    {
        profile->duration_ms = 1U;
        return RT_EOK;
    }

    /*
     * Minimum-jerk normalized profile:
     * max normalized velocity = 1.875, max normalized accel ~= 5.774.
     * Use conservative constants so 20 ms sampled setpoints stay inside limits.
     */
    duration_s = (1.875f * distance) / max_velocity_rad_s;
    {
        float accel_duration_s = 0.0f;
        float ratio = (5.80f * distance) / max_accel_rad_s2;
        float estimate = 0.001f;

        while ((estimate * estimate) < ratio)
        {
            estimate += 0.001f;
        }
        accel_duration_s = estimate;
        if (duration_s < accel_duration_s)
        {
            duration_s = accel_duration_s;
        }
    }
    {
        float jerk_duration_s = 0.001f;
        float ratio = (60.0f * distance) / max_jerk_rad_s3;

        while ((jerk_duration_s * jerk_duration_s * jerk_duration_s) < ratio)
        {
            jerk_duration_s += 0.001f;
        }
        if (duration_s < jerk_duration_s)
        {
            duration_s = jerk_duration_s;
        }
    }

    duration_ms = (rt_uint32_t)((duration_s * 1000.0f) + 1.0f);
    if (duration_ms == 0U)
    {
        duration_ms = 1U;
    }
    profile->duration_ms = duration_ms;
    return RT_EOK;
}

rt_err_t rehab_scurve_sample(const rehab_scurve_profile_t *profile,
                             rt_uint32_t elapsed_ms,
                             rehab_scurve_sample_t *out)
{
    float duration_s;
    float elapsed_s;
    float u;

    if ((profile == RT_NULL) || (out == RT_NULL) ||
        (profile->duration_ms == 0U))
    {
        return -RT_ERROR;
    }

    rt_memset(out, 0, sizeof(*out));
    if (elapsed_ms >= profile->duration_ms)
    {
        out->position_rad = profile->end_rad;
        return RT_EOK;
    }

    duration_s = ((float)profile->duration_ms) / 1000.0f;
    elapsed_s = ((float)elapsed_ms) / 1000.0f;
    u = elapsed_s / duration_s;
    if (u < 0.0f)
    {
        u = 0.0f;
    }
    else if (u > 1.0f)
    {
        u = 1.0f;
    }

    out->position_rad =
        profile->start_rad +
        (profile->direction * profile->distance_rad * scurve_norm_pos(u));
    out->velocity_rad_s =
        profile->direction * profile->distance_rad *
        scurve_norm_vel(u) / duration_s;
    out->accel_rad_s2 =
        profile->direction * profile->distance_rad *
        scurve_norm_accel(u) / (duration_s * duration_s);
    return RT_EOK;
}
