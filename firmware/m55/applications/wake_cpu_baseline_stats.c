#include "wake_cpu_baseline_stats.h"

#include <string.h>

wake_cpu_baseline_token_t wake_cpu_baseline_begin(
    const wake_cpu_baseline_state_t *state, uint32_t start_units)
{
    wake_cpu_baseline_token_t token;

    token.start_units = start_units;
    token.generation = state->generation;
    token.collect = !state->collection_complete;
    return token;
}

uint32_t wake_cpu_baseline_elapsed_us(uint32_t start_units,
                                      uint32_t end_units,
                                      uint32_t units_per_second)
{
    uint32_t elapsed_units = end_units - start_units;

    if (units_per_second == 0U)
    {
        return 0U;
    }
    return (uint32_t)(((uint64_t)elapsed_units * 1000000ULL) /
                      units_per_second);
}

void wake_cpu_baseline_finish(wake_cpu_baseline_state_t *state,
                              const wake_cpu_baseline_token_t *token,
                              uint32_t elapsed_us,
                              bool success)
{
    if (!token->collect || state->collection_complete)
    {
        return;
    }
    if (token->generation != state->generation)
    {
        state->discarded_reset_count++;
        return;
    }

    state->completed_count++;
    if (!success)
    {
        state->fail_count++;
    }

    if (state->warmup_count < WAKE_CPU_BASELINE_WARMUP_COUNT)
    {
        state->warmup_count++;
        return;
    }
    if (!success)
    {
        return;
    }
    if (state->sample_count >= WAKE_CPU_BASELINE_SAMPLE_CAPACITY)
    {
        state->collection_complete = true;
        return;
    }

    state->benchmark_count++;
    state->last_us = elapsed_us;
    if ((state->benchmark_count == 1U) || (elapsed_us < state->min_us))
    {
        state->min_us = elapsed_us;
    }
    if (elapsed_us > state->max_us)
    {
        state->max_us = elapsed_us;
    }
    state->total_us += elapsed_us;

    state->samples[state->sample_count++] = elapsed_us;
    if (state->sample_count == WAKE_CPU_BASELINE_SAMPLE_CAPACITY)
    {
        state->collection_complete = true;
    }
}

void wake_cpu_baseline_reset(wake_cpu_baseline_state_t *state)
{
    uint32_t next_generation = state->generation + 1U;

    state->generation = next_generation;
    state->completed_count = 0U;
    state->fail_count = 0U;
    state->warmup_count = 0U;
    state->benchmark_count = 0U;
    state->discarded_reset_count = 0U;
    state->sample_count = 0U;
    state->sample_dropped_count = 0U;
    state->last_us = 0U;
    state->min_us = 0U;
    state->max_us = 0U;
    state->total_us = 0U;
    state->collection_complete = false;
}

bool wake_cpu_baseline_run_complete(const wake_cpu_baseline_state_t *state)
{
    return state->collection_complete &&
           (state->warmup_count == WAKE_CPU_BASELINE_WARMUP_COUNT) &&
           (state->sample_count == WAKE_CPU_BASELINE_SAMPLE_CAPACITY) &&
           (state->benchmark_count == WAKE_CPU_BASELINE_SAMPLE_CAPACITY);
}

bool wake_cpu_baseline_run_valid(const wake_cpu_baseline_state_t *state,
                                 bool timer_ready,
                                 bool timer_progressed,
                                 uint32_t core_hz)
{
    return wake_cpu_baseline_run_complete(state) && timer_ready &&
           timer_progressed && (core_hz != 0U) &&
           (state->fail_count == 0U) &&
           (state->discarded_reset_count == 0U) &&
           (state->sample_dropped_count == 0U);
}

size_t wake_cpu_baseline_read_samples(const wake_cpu_baseline_state_t *state,
                                      uint32_t generation,
                                      size_t offset,
                                      uint32_t *samples,
                                      size_t capacity)
{
    size_t available;

    if ((state->generation != generation) || (samples == NULL) ||
        (offset >= state->sample_count) || (capacity == 0U))
    {
        return 0U;
    }

    available = state->sample_count - offset;
    if (available > capacity)
    {
        available = capacity;
    }
    if (available > WAKE_CPU_BASELINE_READ_CHUNK_MAX)
    {
        available = WAKE_CPU_BASELINE_READ_CHUNK_MAX;
    }
    memcpy(samples, &state->samples[offset], available * sizeof(samples[0]));
    return available;
}
