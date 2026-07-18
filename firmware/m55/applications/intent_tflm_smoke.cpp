#include "intent_golden_samples.h"
#include "intent_model_int8.h"

#include <rtthread.h>

#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace
{
constexpr size_t kTensorArenaBytes = 64U * 1024U;
constexpr int32_t kOutputTolerance = 2;

static uint8_t *g_tensor_arena = RT_NULL;
static tflite::MicroErrorReporter g_error_reporter;
static tflite::MicroMutableOpResolver<2> g_resolver;
static tflite::MicroInterpreter *g_interpreter = RT_NULL;
static TfLiteTensor *g_input = RT_NULL;
static TfLiteTensor *g_output = RT_NULL;
static bool g_resolver_ready = false;
static bool g_ready = false;

static const char *const kIntentLabels[] = {
    "elbow_curl",
    "rest",
    "shoulder_flex",
};

static int32_t abs_i32(int32_t value)
{
    return (value < 0) ? -value : value;
}

static int argmax_int8(const int8_t *values, int count)
{
    int best_index = 0;
    int8_t best_value = values[0];

    for (int i = 1; i < count; i++)
    {
        if (values[i] > best_value)
        {
            best_value = values[i];
            best_index = i;
        }
    }

    return best_index;
}

static const char *label_for(int index)
{
    if ((index < 0) || (index >= (int)(sizeof(kIntentLabels) / sizeof(kIntentLabels[0]))))
    {
        return "?";
    }
    return kIntentLabels[index];
}

static int ensure_interpreter_ready(void)
{
    if (g_ready)
    {
        return 0;
    }

    const tflite::Model *model = tflite::GetModel(g_intent_model_int8_tflite);
    if ((model == RT_NULL) || (model->version() != TFLITE_SCHEMA_VERSION))
    {
        rt_kprintf("[intent_tflm] schema mismatch model=%p version=%d expected=%d\n",
                   model,
                   model ? model->version() : -1,
                   TFLITE_SCHEMA_VERSION);
        return -1;
    }

    if (g_tensor_arena == RT_NULL)
    {
        g_tensor_arena = static_cast<uint8_t *>(rt_malloc_align(kTensorArenaBytes, 16));
        if (g_tensor_arena == RT_NULL)
        {
            rt_kprintf("[intent_tflm] tensor arena alloc failed bytes=%u\n",
                       (unsigned int)kTensorArenaBytes);
            return -8;
        }
    }

    memset(g_tensor_arena, 0, kTensorArenaBytes);
    if (!g_resolver_ready)
    {
        if ((g_resolver.AddFullyConnected() != kTfLiteOk) ||
            (g_resolver.AddSoftmax() != kTfLiteOk))
        {
            rt_kprintf("[intent_tflm] resolver add ops failed\n");
            return -9;
        }
        g_resolver_ready = true;
    }

    static tflite::MicroInterpreter interpreter(model,
                                                g_resolver,
                                                g_tensor_arena,
                                                kTensorArenaBytes,
                                                &g_error_reporter);
    g_interpreter = &interpreter;

    if (g_interpreter->AllocateTensors() != kTfLiteOk)
    {
        rt_kprintf("[intent_tflm] AllocateTensors failed arena=%u model=%u\n",
                   (unsigned int)kTensorArenaBytes,
                   g_intent_model_int8_tflite_len);
        return -2;
    }

    g_input = g_interpreter->input(0);
    g_output = g_interpreter->output(0);
    if ((g_input == RT_NULL) || (g_output == RT_NULL))
    {
        rt_kprintf("[intent_tflm] missing input/output tensor\n");
        return -3;
    }

    if (g_input->type != kTfLiteInt8)
    {
        rt_kprintf("[intent_tflm] unexpected input type=%d, expected int8\n", g_input->type);
        return -4;
    }

    if (g_output->type != kTfLiteInt8)
    {
        rt_kprintf("[intent_tflm] unexpected output type=%d, expected int8\n", g_output->type);
        return -5;
    }

    if (g_input->bytes != (size_t)g_intent_golden_feature_count)
    {
        rt_kprintf("[intent_tflm] input bytes=%u expected=%d\n",
                   (unsigned int)g_input->bytes,
                   g_intent_golden_feature_count);
        return -6;
    }

    if (g_output->bytes != (size_t)g_intent_golden_class_count)
    {
        rt_kprintf("[intent_tflm] output bytes=%u expected=%d\n",
                   (unsigned int)g_output->bytes,
                   g_intent_golden_class_count);
        return -7;
    }

    g_ready = true;
    rt_kprintf("[intent_tflm] ready model=%u arena=%u used=%u input_scale=%d/1e6 input_zero=%d output_scale=%d/1e6 output_zero=%d\n",
               g_intent_model_int8_tflite_len,
               (unsigned int)kTensorArenaBytes,
               (unsigned int)g_interpreter->arena_used_bytes(),
               (int)(g_input->params.scale * 1000000.0f),
               g_input->params.zero_point,
               (int)(g_output->params.scale * 1000000.0f),
               g_output->params.zero_point);
    return 0;
}

static int run_one_sample(int sample_index, bool verbose)
{
    const int input_offset = sample_index * g_intent_golden_feature_count;
    const int output_offset = sample_index * g_intent_golden_class_count;

    memcpy(g_input->data.int8,
           &g_intent_golden_input[input_offset],
           (size_t)g_intent_golden_feature_count);

    if (g_interpreter->Invoke() != kTfLiteOk)
    {
        rt_kprintf("[intent_tflm] sample=%d Invoke failed\n", sample_index);
        return -1;
    }

    const int predicted_index = argmax_int8(g_output->data.int8, g_intent_golden_class_count);
    const int expected_index = (int)g_intent_golden_expected_indices[sample_index];
    int mismatches = 0;

    for (int class_index = 0; class_index < g_intent_golden_class_count; class_index++)
    {
        const int32_t actual_score = g_output->data.int8[class_index];
        const int32_t expected_score = g_intent_golden_expected_output[output_offset + class_index];
        if (abs_i32(actual_score - expected_score) > kOutputTolerance)
        {
            mismatches++;
        }
    }

    if ((predicted_index != expected_index) || (mismatches != 0) || verbose)
    {
        rt_kprintf("[intent_tflm] sample=%d pred=%d/%s expected=%d/%s score=[%d,%d,%d] mismatch=%d\n",
                   sample_index,
                   predicted_index,
                   label_for(predicted_index),
                   expected_index,
                   label_for(expected_index),
                   g_output->data.int8[0],
                   g_output->data.int8[1],
                   g_output->data.int8[2],
                   mismatches);
    }

    return ((predicted_index == expected_index) && (mismatches == 0)) ? 0 : -1;
}
} // namespace

extern "C" int intent_tflm_smoke(int argc, char **argv)
{
    bool verbose = false;
    int passed = 0;

    if ((argc > 1) && (argv != RT_NULL) && (argv[1] != RT_NULL))
    {
        verbose = (strcmp(argv[1], "-v") == 0) || (strcmp(argv[1], "verbose") == 0);
    }

    const int init_status = ensure_interpreter_ready();
    if (init_status != 0)
    {
        rt_kprintf("[intent_tflm] init failed status=%d\n", init_status);
        return init_status;
    }

    for (int i = 0; i < g_intent_golden_sample_count; i++)
    {
        if (run_one_sample(i, verbose) == 0)
        {
            passed++;
        }
    }

    rt_kprintf("[intent_tflm] golden pass %d/%d tolerance=%d\n",
               passed,
               g_intent_golden_sample_count,
               kOutputTolerance);
    return (passed == g_intent_golden_sample_count) ? 0 : -1;
}

MSH_CMD_EXPORT(intent_tflm_smoke, Run int8 intent TFLM golden-sample smoke test);
