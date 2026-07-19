#include "rehab_worker_timing.h"

void rehab_worker_timing_note(rehab_worker_timing_t *timing,
                              rt_tick_t now,
                              rt_tick_t expected_period_ticks,
                              rt_uint32_t ticks_per_second)
{
    rt_tick_t elapsed_ticks;
    rt_tick_t jitter_ticks;
    rt_uint32_t jitter_ms;

    if ((timing == RT_NULL) || (ticks_per_second == 0U))
    {
        return;
    }

    timing->cycle_count++;
    if (!timing->has_last_tick)
    {
        timing->last_tick = now;
        timing->has_last_tick = RT_TRUE;
        return;
    }

    elapsed_ticks = now - timing->last_tick;
    timing->last_tick = now;
    jitter_ticks = (elapsed_ticks >= expected_period_ticks)
                       ? (elapsed_ticks - expected_period_ticks)
                       : (expected_period_ticks - elapsed_ticks);
    jitter_ms = (rt_uint32_t)(((rt_uint64_t)jitter_ticks * 1000U) / ticks_per_second);
    if (jitter_ms > timing->max_jitter_ms)
    {
        timing->max_jitter_ms = jitter_ms;
    }
}
