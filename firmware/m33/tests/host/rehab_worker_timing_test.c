#include <assert.h>
#include <stdio.h>

#include "rehab_worker_timing.h"

static void test_first_cycle_establishes_baseline(void)
{
    rehab_worker_timing_t timing = {0};

    rehab_worker_timing_note(&timing, 100U, 20U, 1000U);

    assert(timing.cycle_count == 1U);
    assert(timing.last_tick == 100U);
    assert(timing.max_jitter_ms == 0U);
    assert(timing.has_last_tick == RT_TRUE);
}

static void test_max_jitter_tracks_early_and_late_cycles(void)
{
    rehab_worker_timing_t timing = {0};

    rehab_worker_timing_note(&timing, 100U, 20U, 1000U);
    rehab_worker_timing_note(&timing, 120U, 20U, 1000U);
    rehab_worker_timing_note(&timing, 151U, 20U, 1000U);
    rehab_worker_timing_note(&timing, 161U, 20U, 1000U);

    assert(timing.cycle_count == 4U);
    assert(timing.last_tick == 161U);
    assert(timing.max_jitter_ms == 11U);
}

static void test_tick_wrap_uses_unsigned_elapsed_time(void)
{
    rehab_worker_timing_t timing = {0};

    rehab_worker_timing_note(&timing, UINT32_MAX - 15U, 20U, 1000U);
    rehab_worker_timing_note(&timing, 4U, 20U, 1000U);

    assert(timing.cycle_count == 2U);
    assert(timing.last_tick == 4U);
    assert(timing.max_jitter_ms == 0U);
}

int main(void)
{
    test_first_cycle_establishes_baseline();
    test_max_jitter_tracks_early_and_late_cycles();
    test_tick_wrap_uses_unsigned_elapsed_time();
    puts("rehab_worker_timing_test PASS");
    return 0;
}
