import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEEPCRAFT = ROOT / "applications" / "ifx_deepcraft"


def _compile_and_run(
    source: Path,
    headers: dict[str, str],
    harness: str,
    extra_link_args: tuple[str, ...] = (),
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        for name, contents in headers.items():
            (temp / name).write_text(contents, encoding="ascii")
        harness_path = temp / "harness.c"
        harness_path.write_text(harness, encoding="ascii")
        executable = temp / "harness.exe"
        subprocess.run(
            [
                "gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(temp),
                "-I",
                str(DEEPCRAFT / "source" / "va_core"),
                "-I",
                str(DEEPCRAFT / "include"),
                "-DCOMPONENT_U55",
                str(source),
                str(harness_path),
                *extra_link_args,
                "-o",
                str(executable),
            ],
            check=True,
        )
        subprocess.run([str(executable)], check=True)


def test_mtb_ml_failed_init_does_not_poison_retry_or_reference_count():
    headers = {
        "cy_pdl.h": """
#ifndef CY_PDL_H
#define CY_PDL_H
#include <stdint.h>
extern uint32_t SystemCoreClock;
#endif
""",
        "mtb_ml.h": """
#ifndef MTB_ML_H
#define MTB_ML_H
#include <stdint.h>
typedef uint32_t cy_rslt_t;
struct ethosu_driver { uint32_t unused; };
#define MTB_ML_RESULT_SUCCESS ((cy_rslt_t)0u)
#define MTB_ML_RESULT_NPU_INIT_ERROR ((cy_rslt_t)17u)
cy_rslt_t mtb_ml_init(uint32_t priority);
cy_rslt_t mtb_ml_deinit(void);
uint32_t mtb_ml_get_init_state(void);
#endif
""",
    }
    harness = """
#include <assert.h>
#include <stdint.h>
#include "mtb_ml.h"

uint32_t SystemCoreClock = 150000000u;
struct ethosu_driver ethosu_drv;
static cy_rslt_t init_result = MTB_ML_RESULT_NPU_INIT_ERROR;
static unsigned init_calls;
static unsigned deinit_calls;

cy_rslt_t mtb_ml_ethosu_init(struct ethosu_driver *drv, uint32_t priority)
{
    assert(drv == &ethosu_drv);
    assert(priority == 4u);
    init_calls++;
    return init_result;
}

cy_rslt_t mtb_ml_ethosu_deinit(void)
{
    deinit_calls++;
    return MTB_ML_RESULT_SUCCESS;
}

int main(void)
{
    assert(mtb_ml_init(4u) == MTB_ML_RESULT_NPU_INIT_ERROR);
    assert(mtb_ml_get_init_state() == 0u);
    assert(init_calls == 1u);

    init_result = MTB_ML_RESULT_SUCCESS;
    assert(mtb_ml_init(4u) == MTB_ML_RESULT_SUCCESS);
    assert(mtb_ml_get_init_state() == 1u);
    assert(init_calls == 2u);

    assert(mtb_ml_init(4u) == MTB_ML_RESULT_SUCCESS);
    assert(mtb_ml_get_init_state() == 2u);
    assert(init_calls == 2u);

    assert(mtb_ml_deinit() == MTB_ML_RESULT_SUCCESS);
    assert(mtb_ml_get_init_state() == 1u);
    assert(deinit_calls == 0u);
    assert(mtb_ml_deinit() == MTB_ML_RESULT_SUCCESS);
    assert(mtb_ml_get_init_state() == 0u);
    assert(deinit_calls == 1u);
    return 0;
}
"""
    _compile_and_run(DEEPCRAFT / "source" / "mtb_ml.c", headers, harness)


def test_va_model_unwinds_runtime_when_npu_init_fails():
    headers = {
        "mtb_ml.h": """
#ifndef MTB_ML_H
#define MTB_ML_H
#include <stdint.h>
typedef uint32_t cy_rslt_t;
#define MTB_ML_RESULT_SUCCESS ((cy_rslt_t)0u)
cy_rslt_t mtb_ml_init(uint32_t priority);
cy_rslt_t mtb_ml_deinit(void);
#endif
""",
        "mtb_ml_model_16x8.h": """
#ifndef MTB_ML_MODEL_16X8_H
#define MTB_ML_MODEL_16X8_H
#include <stdint.h>
#include "mtb_ml.h"
typedef struct { const void *model_bin; } mtb_ml_model_bin_t;
typedef struct { void *tensor_arena; } mtb_ml_model_buffer_t;
typedef struct {
    float input_scale;
    float input_zero_point;
    int input_size;
    int output_zero_point;
    float output_scale;
    int output_size;
    int16_t *output;
    uint32_t profiling;
} mtb_ml_model_16x8_t;
#define MTB_ML_PROFILE_DISABLE 0u
cy_rslt_t mtb_ml_model_16x8_init(const mtb_ml_model_bin_t *, const mtb_ml_model_buffer_t *, mtb_ml_model_16x8_t *);
cy_rslt_t mtb_ml_model_16x8_deinit(mtb_ml_model_16x8_t *);
cy_rslt_t mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_16x8_t *);
cy_rslt_t mtb_ml_model_16x8_run(mtb_ml_model_16x8_t *, int16_t *);
#endif
""",
        "ifx_pre_post_process.h": "",
        "mtb_wwd_nlu_common.h": """
#ifndef MTB_WWD_NLU_COMMON_H
#define MTB_WWD_NLU_COMMON_H
#include <stdint.h>
#define MTB_VA_RSLT_SUCCESS ((uint32_t)0u)
#define MTB_VA_RSLT_INVALID_PARAM ((uint32_t)2u)
#define MTB_VA_RSLT_ML_INIT_ERROR ((uint32_t)7u)
#define MTB_VA_RSLT_ML_INFERENCE_ERROR ((uint32_t)6u)
#define CY_RSLT_TYPE_ERROR ((uint32_t)1u)
#define CY_RSLT_SUCCESS ((uint32_t)0u)
#define NPU_PRIORITY 3u
#define __SSAT(value, bits) (value)
#endif
""",
    }
    harness = """
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "va_ml_model.h"
#include "mtb_wwd_nlu_common.h"

volatile int g_ifx_wwd_debug_stage;
volatile int g_ifx_wwd_debug_detail;
static uint32_t npu_result;
static uint32_t reset_result;
static char events[8];
static unsigned event_count;

static void record(char event) { events[event_count++] = event; }

cy_rslt_t mtb_ml_model_16x8_init(const mtb_ml_model_bin_t *bin,
                                 const mtb_ml_model_buffer_t *buffer,
                                 mtb_ml_model_16x8_t *model)
{
    assert(bin != 0 && buffer != 0 && model != 0);
    record('I');
    return MTB_ML_RESULT_SUCCESS;
}

cy_rslt_t mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_16x8_t *model)
{
    assert(model != 0);
    record('R');
    return reset_result;
}

cy_rslt_t mtb_ml_model_16x8_deinit(mtb_ml_model_16x8_t *model)
{
    assert(model != 0);
    record('D');
    return MTB_ML_RESULT_SUCCESS;
}

cy_rslt_t mtb_ml_init(uint32_t priority)
{
    assert(priority == 3u);
    record('N');
    return npu_result;
}

cy_rslt_t mtb_ml_deinit(void) { record('X'); return MTB_ML_RESULT_SUCCESS; }
cy_rslt_t mtb_ml_model_16x8_run(mtb_ml_model_16x8_t *model, int16_t *input)
{ (void)model; (void)input; return MTB_ML_RESULT_SUCCESS; }
void __real_free(void *pointer);
void __wrap_free(void *pointer) { record('F'); __real_free(pointer); }
void *__real_malloc(size_t size);
void *__wrap_malloc(size_t size)
{
    void *pointer = __real_malloc(size);
    if (pointer != 0) memset(pointer, 0xa5, size);
    return pointer;
}

int main(void)
{
    mtb_ml_model_bin_t bin = {0};
    mtb_ml_model_buffer_t buffer = {0};
    mtb_ml_model_16x8_t *model = 0;
    unsigned char *bytes;
    size_t index;

    assert(ml_create_model(&model) == MTB_VA_RSLT_SUCCESS);
    bytes = (unsigned char *)model;
    for (index = 0u; index < sizeof(*model); index++) assert(bytes[index] == 0u);
    ml_destroy_model(&model);
    assert(model == 0);

    event_count = 0u;
    model = malloc(sizeof(*model));
    assert(model != 0);

    npu_result = 17u;
    assert(ml_inference_init(&bin, &buffer, model) == MTB_VA_RSLT_ML_INIT_ERROR);
    assert(event_count == 3u);
    assert(memcmp(events, "IRN", 3u) == 0);
    assert(g_ifx_wwd_debug_detail == 17);
    ml_destroy_model(&model);
    assert(model == 0);
    assert(event_count == 6u);
    assert(memcmp(events, "IRNDFX", 6u) == 0);

    event_count = 0u;
    reset_result = 23u;
    model = malloc(sizeof(*model));
    assert(model != 0);
    assert(ml_inference_init(&bin, &buffer, model) == MTB_VA_RSLT_ML_INIT_ERROR);
    assert(event_count == 2u);
    assert(memcmp(events, "IR", 2u) == 0);
    assert(g_ifx_wwd_debug_detail == 23);
    ml_destroy_model(&model);
    assert(model == 0);
    assert(event_count == 5u);
    assert(memcmp(events, "IRDFX", 5u) == 0);

    event_count = 0u;
    reset_result = MTB_ML_RESULT_SUCCESS;
    npu_result = MTB_ML_RESULT_SUCCESS;
    model = malloc(sizeof(*model));
    assert(model != 0);
    assert(ml_inference_init(&bin, &buffer, model) == MTB_VA_RSLT_SUCCESS);
    assert(event_count == 3u);
    assert(memcmp(events, "IRN", 3u) == 0);
    ml_destroy_model(&model);
    assert(model == 0);
    assert(event_count == 6u);
    assert(memcmp(events, "IRNDFX", 6u) == 0);
    return 0;
}
"""
    _compile_and_run(
        DEEPCRAFT / "source" / "va_core" / "va_ml_model.c",
        headers,
        harness,
        ("-Wl,--wrap=free", "-Wl,--wrap=malloc"),
    )


def test_deepcraft_owners_destroy_model_after_inference_init_failure():
    for relative_path in ("source/mtb_wwd.c", "source/mtb_nlu.c"):
        text = (DEEPCRAFT / relative_path).read_text(encoding="utf-8")
        call = text.index("ml_inference_init(")
        failure = text.index("if (error_code != MTB_VA_RSLT_SUCCESS)", call)
        failure_body = text[failure : failure + 250]
        assert "ml_destroy_model(&mtb_ml_model_obj);" in failure_body
        assert failure_body.index("ml_destroy_model") < failure_body.index("return error_code")
