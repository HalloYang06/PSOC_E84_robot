#ifndef __REHAB_WORKER_TIMING_H__
#define __REHAB_WORKER_TIMING_H__

#include <rtthread.h>

typedef struct
{
    rt_uint32_t cycle_count;
    rt_tick_t last_tick;
    rt_uint32_t max_jitter_ms;
    rt_bool_t has_last_tick;
} rehab_worker_timing_t;

void rehab_worker_timing_note(rehab_worker_timing_t *timing,
                              rt_tick_t now,
                              rt_tick_t expected_period_ticks,
                              rt_uint32_t ticks_per_second);

#endif /* __REHAB_WORKER_TIMING_H__ */
