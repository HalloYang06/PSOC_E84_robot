#ifndef WAKE_CPU_BASELINE_STATS_H
#define WAKE_CPU_BASELINE_STATS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define WAKE_CPU_BASELINE_WARMUP_COUNT 20U
#define WAKE_CPU_BASELINE_SAMPLE_CAPACITY 1000U
#define WAKE_CPU_BASELINE_READ_CHUNK_MAX 16U

typedef struct
{
    uint32_t start_units;
    uint32_t generation;
    bool collect;
} wake_cpu_baseline_token_t;

typedef struct
{
    uint32_t generation;
    uint32_t completed_count;
    uint32_t fail_count;
    uint32_t warmup_count;
    uint32_t benchmark_count;
    uint32_t discarded_reset_count;
    uint32_t sample_count;
    uint32_t sample_dropped_count;
    uint32_t last_us;
    uint32_t min_us;
    uint32_t max_us;
    uint64_t total_us;
    bool collection_complete;
    uint32_t samples[WAKE_CPU_BASELINE_SAMPLE_CAPACITY];
} wake_cpu_baseline_state_t;

wake_cpu_baseline_token_t wake_cpu_baseline_begin(
    const wake_cpu_baseline_state_t *state, uint32_t start_units);
uint32_t wake_cpu_baseline_elapsed_us(uint32_t start_units,
                                      uint32_t end_units,
                                      uint32_t units_per_second);
void wake_cpu_baseline_finish(wake_cpu_baseline_state_t *state,
                              const wake_cpu_baseline_token_t *token,
                              uint32_t elapsed_us,
                              bool success);
void wake_cpu_baseline_reset(wake_cpu_baseline_state_t *state);
bool wake_cpu_baseline_run_complete(const wake_cpu_baseline_state_t *state);
bool wake_cpu_baseline_run_valid(const wake_cpu_baseline_state_t *state,
                                 bool timer_ready,
                                 bool timer_progressed,
                                 uint32_t core_hz);
size_t wake_cpu_baseline_read_samples(const wake_cpu_baseline_state_t *state,
                                      uint32_t generation,
                                      size_t offset,
                                      uint32_t *samples,
                                      size_t capacity);

#ifdef __cplusplus
}
#endif

#endif
