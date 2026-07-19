import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications"
HEADER = APP / "wake_cpu_baseline_stats.h"
SOURCE = APP / "wake_cpu_baseline_stats.c"
BACKEND = APP / "xiaozhi_edge_impulse_wake_backend.cpp"
MAIN = APP / "main.c"


HARNESS = r"""
#include <assert.h>
#include <stdint.h>
#include "wake_cpu_baseline_stats.h"

static wake_cpu_baseline_token_t token_at(wake_cpu_baseline_state_t *state,
                                           uint32_t start)
{
    return wake_cpu_baseline_begin(state, start);
}

static void finish(wake_cpu_baseline_state_t *state,
                   uint32_t start,
                   uint32_t end,
                   int success)
{
    wake_cpu_baseline_token_t token = token_at(state, start);
    uint32_t elapsed = wake_cpu_baseline_elapsed_us(token.start_units,
                                                     end,
                                                     1000000U);
    wake_cpu_baseline_finish(state, &token, elapsed, success != 0);
}

int main(void)
{
    wake_cpu_baseline_state_t state = {0};
    wake_cpu_baseline_token_t stale;
    uint32_t out[64];

    /* The first 20 completed attempts are warmup, including failures. */
    for (uint32_t i = 0; i < 19U; ++i)
        finish(&state, i, i + 10U, 1);
    finish(&state, 19U, 29U, 0);
    assert(state.completed_count == 20U);
    assert(state.warmup_count == 20U);
    assert(state.fail_count == 1U);
    assert(state.benchmark_count == 0U);
    assert(state.sample_count == 0U);

    /* Failures never enter benchmark timing statistics. */
    finish(&state, 30U, 1030U, 0);
    assert(state.fail_count == 2U);
    assert(state.benchmark_count == 0U);
    assert(state.min_us == 0U && state.max_us == 0U && state.total_us == 0U);
    finish(&state, 40U, 72U, 1);
    assert(state.benchmark_count == 1U);
    assert(state.min_us == 32U && state.max_us == 32U && state.total_us == 32U);

    /* Unsigned subtraction preserves a single 32-bit clock wrap. */
    assert(wake_cpu_baseline_elapsed_us(0xfffffff0U, 0x10U, 1000000U) == 32U);

    /* Reset invalidates an Invoke that began in the previous generation. */
    stale = token_at(&state, 100U);
    wake_cpu_baseline_reset(&state);
    wake_cpu_baseline_finish(&state, &stale, 25U, true);
    assert(state.completed_count == 0U);
    assert(state.discarded_reset_count == 1U);
    assert(!wake_cpu_baseline_run_complete(&state));

    /* Stop-at-capacity keeps the first 1000 post-warmup successful samples. */
    for (uint32_t i = 0; i < WAKE_CPU_BASELINE_WARMUP_COUNT; ++i)
        finish(&state, i, i + 1U, 1);
    for (uint32_t i = 0; i < WAKE_CPU_BASELINE_SAMPLE_CAPACITY + 5U; ++i)
        finish(&state, i, i + i + 1U, 1);
    assert(state.sample_count == WAKE_CPU_BASELINE_SAMPLE_CAPACITY);
    assert(state.sample_dropped_count == 0U);
    assert(state.benchmark_count == WAKE_CPU_BASELINE_SAMPLE_CAPACITY);
    assert(state.last_us == 1000U);
    assert(state.min_us == 1U && state.max_us == 1000U);
    assert(state.total_us == 500500U);
    assert(state.samples[0] == 1U);
    assert(state.samples[WAKE_CPU_BASELINE_SAMPLE_CAPACITY - 1U] == 1000U);
    assert(wake_cpu_baseline_read_samples(&state, state.generation, 0U, out, 64U) ==
           WAKE_CPU_BASELINE_READ_CHUNK_MAX);
    assert(wake_cpu_baseline_read_samples(&state, state.generation, 995U, out, 64U) == 5U);
    assert(out[0] == 996U && out[4] == 1000U);
    assert(wake_cpu_baseline_read_samples(&state, state.generation + 1U, 0U, out, 1U) == 0U);
    assert(wake_cpu_baseline_run_complete(&state));
    assert(!wake_cpu_baseline_run_valid(&state, true, true, 400000000U));
    state.sample_dropped_count = 0U;
    state.discarded_reset_count = 0U;
    assert(wake_cpu_baseline_run_valid(&state, true, true, 400000000U));
    assert(state.collection_complete);
    finish(&state, 2000U, 2100U, 1);
    finish(&state, 2100U, 2200U, 0);
    assert(state.completed_count == WAKE_CPU_BASELINE_WARMUP_COUNT +
                                    WAKE_CPU_BASELINE_SAMPLE_CAPACITY);
    assert(state.fail_count == 0U);
    assert(state.sample_dropped_count == 0U);
    assert(state.total_us == 500500U);
    assert(wake_cpu_baseline_run_valid(&state, true, true, 400000000U));
    assert(!wake_cpu_baseline_run_valid(&state, false, true, 400000000U));
    assert(!wake_cpu_baseline_run_valid(&state, true, false, 400000000U));
    assert(!wake_cpu_baseline_run_valid(&state, true, true, 0U));
    return 0;
}
"""


def _compiler(env_name: str, default: str) -> str:
    compiler = os.environ.get(env_name) or shutil.which(default)
    assert compiler, f"compiler not found: {default}"
    return compiler


def test_fake_clock_behavior_and_ring_boundary():
    gcc = _compiler("HOST_GCC", "gcc")
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "baseline_test.c"
        exe = Path(tmp) / "baseline_test.exe"
        harness.write_text(HARNESS, encoding="ascii")
        subprocess.run(
            [gcc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(APP),
             str(harness), str(SOURCE), "-o", str(exe)],
            check=True,
        )
        subprocess.run([str(exe)], check=True)


def test_stats_header_compiles_as_arm_cpp():
    compiler = _compiler("ARM_NONE_EABI_GXX", "arm-none-eabi-g++")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "contract.cpp"
        output = Path(tmp) / "contract.o"
        source.write_text(
            '#include "wake_cpu_baseline_stats.h"\n'
            "wake_cpu_baseline_state_t state = {};\n",
            encoding="ascii",
        )
        subprocess.run(
            [compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(APP),
             "-c", str(source), "-o", str(output)],
            check=True,
        )


def test_production_contract_is_read_only_and_marks_tick_unready():
    backend = BACKEND.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")

    assert "wake_cpu_baseline_begin" in backend
    assert "wake_cpu_baseline_finish" in backend
    assert "wake_cpu_baseline_token_t invoke_token" in backend
    assert "cpu_baseline_finish(&invoke_token" in backend
    assert "timer_ready" in main
    assert "run_complete" in main
    assert "run_valid" in main
    assert "wake_diag samples" in main
    assert '#include "wake_cpu_baseline_stats.h"' in backend
    assert "WAKE_CPU_BASELINE_SAMPLE_CAPACITY 1000U" in HEADER.read_text(encoding="utf-8")
    assert "DWT->CTRL =" not in backend
    assert "DWT->CYCCNT =" not in backend
    assert "CoreDebug->DEMCR" not in backend


def test_reset_is_scalar_only_and_public_reads_are_clamped():
    stats = SOURCE.read_text(encoding="utf-8")
    backend = BACKEND.read_text(encoding="utf-8")
    reset_start = stats.index("void wake_cpu_baseline_reset")
    reset_end = stats.index("size_t wake_cpu_baseline_read_samples", reset_start)
    reset_body = stats[reset_start:reset_end]

    assert "memset" not in reset_body
    assert "samples" not in reset_body
    assert "WAKE_CPU_BASELINE_READ_CHUNK_MAX" in backend
    assert "capacity = WAKE_CPU_BASELINE_READ_CHUNK_MAX" in backend
