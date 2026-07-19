#include <assert.h>
#include <math.h>
#include <stdio.h>

#include "rehab_scurve.h"

static void test_profile_starts_and_ends_at_rest(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t sample;

    assert(rehab_scurve_plan(&profile, 6.226f, 8.038f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(rehab_scurve_sample(&profile, 0U, &sample) == RT_EOK);
    assert(fabsf(sample.position_rad - 6.226f) < 0.0001f);
    assert(fabsf(sample.velocity_rad_s) < 0.0001f);
    assert(fabsf(sample.accel_rad_s2) < 0.0001f);

    assert(rehab_scurve_sample(&profile, profile.duration_ms, &sample) == RT_EOK);
    assert(fabsf(sample.position_rad - 8.038f) <= 0.001f);
    assert(fabsf(sample.velocity_rad_s) < 0.0001f);
    assert(fabsf(sample.accel_rad_s2) < 0.0001f);
}

static void test_profile_respects_bounds_on_20ms_ticks(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t prev;
    rt_uint32_t t;

    assert(rehab_scurve_plan(&profile, 3.689f, 4.944f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(rehab_scurve_sample(&profile, 0U, &prev) == RT_EOK);
    for (t = 20U; t <= profile.duration_ms + 20U; t += 20U)
    {
        rehab_scurve_sample_t sample;

        assert(rehab_scurve_sample(&profile, t, &sample) == RT_EOK);
        assert(sample.position_rad >= 3.689f - 0.001f);
        assert(sample.position_rad <= 4.944f + 0.001f);
        assert(fabsf(sample.velocity_rad_s) <= 0.121f);
        assert(fabsf(sample.accel_rad_s2) <= 0.201f);
        assert(fabsf(sample.position_rad - prev.position_rad) <= 0.01f);
        prev = sample;
    }
}

static void test_reverse_profile_is_monotonic_downward(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t prev;
    rt_uint32_t t;

    assert(rehab_scurve_plan(&profile, 8.038f, 6.226f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(profile.duration_ms > 0U);
    assert(rehab_scurve_sample(&profile, 0U, &prev) == RT_EOK);
    for (t = 20U; t <= profile.duration_ms; t += 20U)
    {
        rehab_scurve_sample_t sample;

        assert(rehab_scurve_sample(&profile, t, &sample) == RT_EOK);
        assert(sample.position_rad <= prev.position_rad + 0.0001f);
        prev = sample;
    }
}

static void test_invalid_inputs_reject(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t sample;

    assert(rehab_scurve_plan(NULL, 0.0f, 1.0f, 0.12f, 0.20f, 0.50f) != RT_EOK);
    assert(rehab_scurve_plan(&profile, 0.0f, 1.0f, 0.0f, 0.20f, 0.50f) != RT_EOK);
    assert(rehab_scurve_plan(&profile, 0.0f, 1.0f, 0.12f, 0.0f, 0.50f) != RT_EOK);
    assert(rehab_scurve_plan(&profile, 0.0f, 1.0f, 0.12f, 0.20f, 0.0f) != RT_EOK);
    assert(rehab_scurve_sample(NULL, 0U, &sample) != RT_EOK);
    assert(rehab_scurve_plan(&profile, 1.0f, 1.0f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(rehab_scurve_sample(&profile, 1000U, &sample) == RT_EOK);
    assert(fabsf(sample.position_rad - 1.0f) < 0.0001f);
}

int main(void)
{
    test_profile_starts_and_ends_at_rest();
    test_profile_respects_bounds_on_20ms_ticks();
    test_reverse_profile_is_monotonic_downward();
    test_invalid_inputs_reject();
    puts("rehab_scurve_test: PASS");
    return 0;
}
