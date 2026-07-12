#include "intent_tflm_runtime.h"

#include "intent_model_int8.h"

#include <rtthread.h>

#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#include <string.h>

namespace
{
constexpr size_t kTensorArenaBytes = 64U * 1024U;

static uint8_t *g_tensor_arena = RT_NULL;
static tflite::MicroErrorReporter g_error_reporter;
static tflite::MicroMutableOpResolver<2> g_resolver;
static tflite::MicroInterpreter *g_interpreter = RT_NULL;
static TfLiteTensor *g_input = RT_NULL;
static TfLiteTensor *g_output = RT_NULL;
static bool g_resolver_ready = false;
static bool g_ready = false;

static const char *const kIntentLabels[] = {
    "elbow_extend",
    "elbow_flex",
    "rest",
    "shoulder_flex",
};

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

static rt_uint16_t output_confidence_permille(const TfLiteTensor *output, int index)
{
    float probability;

    if ((output == RT_NULL) || (index < 0) || (index >= INTENT_TFLM_CLASS_COUNT))
    {
        return 0U;
    }

    probability = ((float)output->data.int8[index] - (float)output->params.zero_point) *
                  output->params.scale;
    if (probability <= 0.0f)
    {
        return 0U;
    }
    if (probability >= 1.0f)
    {
        return 1000U;
    }
    return (rt_uint16_t)((probability * 1000.0f) + 0.5f);
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
        rt_kprintf("[intent_runtime] schema mismatch model=%p version=%d expected=%d\n",
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
            rt_kprintf("[intent_runtime] tensor arena alloc failed bytes=%u\n",
                       (unsigned int)kTensorArenaBytes);
            return -RT_ENOMEM;
        }
    }

    memset(g_tensor_arena, 0, kTensorArenaBytes);
    if (!g_resolver_ready)
    {
        if ((g_resolver.AddFullyConnected() != kTfLiteOk) ||
            (g_resolver.AddSoftmax() != kTfLiteOk))
        {
            rt_kprintf("[intent_runtime] resolver add ops failed\n");
            return -2;
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
        rt_kprintf("[intent_runtime] AllocateTensors failed arena=%u model=%u\n",
                   (unsigned int)kTensorArenaBytes,
                   g_intent_model_int8_tflite_len);
        return -3;
    }

    g_input = g_interpreter->input(0);
    g_output = g_interpreter->output(0);
    if ((g_input == RT_NULL) || (g_output == RT_NULL))
    {
        rt_kprintf("[intent_runtime] missing input/output tensor\n");
        return -4;
    }
    if ((g_input->type != kTfLiteInt8) || (g_output->type != kTfLiteInt8))
    {
        rt_kprintf("[intent_runtime] unexpected tensor types input=%d output=%d\n",
                   g_input->type,
                   g_output->type);
        return -5;
    }
    if ((g_input->bytes != INTENT_TFLM_FEATURE_COUNT) ||
        (g_output->bytes != INTENT_TFLM_CLASS_COUNT))
    {
        rt_kprintf("[intent_runtime] shape mismatch input=%u output=%u\n",
                   (unsigned int)g_input->bytes,
                   (unsigned int)g_output->bytes);
        return -6;
    }

    g_ready = true;
    rt_kprintf("[intent_runtime] ready model=%u arena=%u used=%u\n",
               g_intent_model_int8_tflite_len,
               (unsigned int)kTensorArenaBytes,
               (unsigned int)g_interpreter->arena_used_bytes());
    return 0;
}
} // namespace

extern "C" const char *intent_tflm_label(int index)
{
    if ((index < 0) || (index >= INTENT_TFLM_CLASS_COUNT))
    {
        return "?";
    }
    return kIntentLabels[index];
}

extern "C" int intent_tflm_runtime_init(void)
{
    return ensure_interpreter_ready();
}

extern "C" int intent_tflm_runtime_infer_int8(const int8_t *input,
                                               size_t input_len,
                                               intent_tflm_result_t *result)
{
    int predicted_index;

    if ((input == RT_NULL) || (result == RT_NULL))
    {
        return -RT_EINVAL;
    }

    int init_status = ensure_interpreter_ready();
    if (init_status != 0)
    {
        return init_status;
    }
    if (input_len != g_input->bytes)
    {
        rt_kprintf("[intent_runtime] input len=%u expected=%u\n",
                   (unsigned int)input_len,
                   (unsigned int)g_input->bytes);
        return -RT_EINVAL;
    }

    memcpy(g_input->data.int8, input, input_len);
    if (g_interpreter->Invoke() != kTfLiteOk)
    {
        rt_kprintf("[intent_runtime] Invoke failed\n");
        return -RT_ERROR;
    }

    predicted_index = argmax_int8(g_output->data.int8, INTENT_TFLM_CLASS_COUNT);
    memset(result, 0, sizeof(*result));
    result->predicted_index = predicted_index;
    result->confidence_permille = output_confidence_permille(g_output, predicted_index);
    result->label = intent_tflm_label(predicted_index);
    memcpy(result->output_int8, g_output->data.int8, sizeof(result->output_int8));
    return RT_EOK;
}
