#include "wake_word_detector.h"

#include "audio_processing.h"
#define WAKE_WORD_MODEL_DATA_DEFINE
#include "wake_word_model_data.h"

#include <rtthread.h>

#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#include <stdio.h>
#include <string.h>

namespace
{
constexpr int kTensorArenaSize = 1536 * 1024;
uint8_t *g_tensor_arena = nullptr;
uint8_t *g_model_data = nullptr;
float *g_mfcc_features = nullptr;

const tflite::Model *g_tflite_model = nullptr;
tflite::MicroErrorReporter g_error_reporter;
tflite::MicroInterpreter *g_interpreter = nullptr;
TfLiteTensor *g_input = nullptr;
TfLiteTensor *g_output = nullptr;
} // namespace

bool WakeWordDetector_Init(void)
{
    if (g_mfcc_features == nullptr)
    {
        g_mfcc_features = static_cast<float *>(rt_malloc_align(sizeof(float) * INPUT_SIZE, 16));
        if (g_mfcc_features == nullptr)
        {
            printf("[wake_word] alloc mfcc failed size=%u\n", (unsigned int)(sizeof(float) * INPUT_SIZE));
            return false;
        }
    }

    if (g_model_data == nullptr)
    {
        g_model_data = static_cast<uint8_t *>(rt_malloc_align(wake_word_model_len, 16));
        if (g_model_data == nullptr)
        {
            printf("[wake_word] alloc model failed size=%u\n", wake_word_model_len);
            return false;
        }

        memcpy(g_model_data, wake_word_model, wake_word_model_len);
    }

    if (g_tensor_arena == nullptr)
    {
        g_tensor_arena = static_cast<uint8_t *>(rt_malloc_align(kTensorArenaSize, 16));
        if (g_tensor_arena == nullptr)
        {
            printf("[wake_word] alloc arena failed size=%d\n", kTensorArenaSize);
            return false;
        }
    }

    g_tflite_model = tflite::GetModel(g_model_data);
    if ((g_tflite_model == nullptr) || (g_tflite_model->version() != TFLITE_SCHEMA_VERSION))
    {
        printf("[wake_word] schema mismatch\n");
        return false;
    }

    static tflite::MicroMutableOpResolver<12> resolver;
    static bool resolver_ready = false;
    if (!resolver_ready)
    {
        if (resolver.AddConv2D() != kTfLiteOk) return false;
        if (resolver.AddMaxPool2D() != kTfLiteOk) return false;
        if (resolver.AddReshape() != kTfLiteOk) return false;
        if (resolver.AddFullyConnected() != kTfLiteOk) return false;
        if (resolver.AddSoftmax() != kTfLiteOk) return false;
        if (resolver.AddMean() != kTfLiteOk) return false;
        if (resolver.AddPad() != kTfLiteOk) return false;
        if (resolver.AddRelu() != kTfLiteOk) return false;
        if (resolver.AddMul() != kTfLiteOk) return false;
        if (resolver.AddAdd() != kTfLiteOk) return false;
        if (resolver.AddQuantize() != kTfLiteOk) return false;
        if (resolver.AddDequantize() != kTfLiteOk) return false;
        resolver_ready = true;
    }

    static tflite::MicroInterpreter interpreter(
        g_tflite_model, resolver, g_tensor_arena, kTensorArenaSize, &g_error_reporter);
    g_interpreter = &interpreter;

    if (g_interpreter->AllocateTensors() != kTfLiteOk)
    {
        printf("[wake_word] allocate tensors failed\n");
        g_interpreter = nullptr;
        return false;
    }

    g_input = g_interpreter->input(0);
    g_output = g_interpreter->output(0);
    if ((g_input == nullptr) || (g_output == nullptr) || (g_input->dims->size != 4))
    {
        printf("[wake_word] tensor shape invalid\n");
        return false;
    }

    printf("[wake_word] ready model=%u arena=%d used=%d model_ptr=%p arena_ptr=%p\n",
           wake_word_model_len,
           kTensorArenaSize,
           g_interpreter->arena_used_bytes(),
           g_model_data,
           g_tensor_arena);
    printf("[wake_word] input type=%d shape=[%d,%d,%d,%d] output type=%d shape=[%d,%d]\n",
           g_input->type,
           g_input->dims->data[0],
           g_input->dims->data[1],
           g_input->dims->data[2],
           g_input->dims->data[3],
           g_output->type,
           g_output->dims->data[0],
           g_output->dims->data[1]);
    return true;
}

bool WakeWordDetector_Detect(const int16_t *audio_data, int audio_len, float *confidence)
{
    int i;
    float score0;
    float score1;
    rt_tick_t tick_start;
    rt_tick_t tick_mfcc_done;
    rt_tick_t tick_invoke_done;
    float input_scale;
    int32_t input_zero_point;
    float output_scale;
    int32_t output_zero_point;
    int8_t *input_data;
    int8_t *output_data;

    if ((g_interpreter == nullptr) || (g_input == nullptr) || (g_output == nullptr) || (g_mfcc_features == nullptr))
    {
        return false;
    }
    if ((audio_data == nullptr) || (audio_len <= 0) || (confidence == nullptr))
    {
        return false;
    }

    tick_start = rt_tick_get();
    if (!AudioProcessing_ExtractMFCC(audio_data, audio_len, g_mfcc_features, N_FRAMES, N_MFCC))
    {
        printf("[wake_word] mfcc failed\n");
        return false;
    }
    tick_mfcc_done = rt_tick_get();

    if (g_input->type == kTfLiteFloat32)
    {
        float *input_f32 = g_input->data.f;
        for (i = 0; i < INPUT_SIZE; i++)
        {
            input_f32[i] = g_mfcc_features[i];
        }
    }
    else if (g_input->type == kTfLiteInt8)
    {
        input_scale = g_input->params.scale;
        input_zero_point = g_input->params.zero_point;
        input_data = g_input->data.int8;
        for (i = 0; i < INPUT_SIZE; i++)
        {
            int32_t quantized;

            quantized = (int32_t)(g_mfcc_features[i] / input_scale + input_zero_point);
            if (quantized < -128)
            {
                quantized = -128;
            }
            else if (quantized > 127)
            {
                quantized = 127;
            }
            input_data[i] = (int8_t)quantized;
        }
    }
    else
    {
        printf("[wake_word] unsupported input type=%d\n", g_input->type);
        return false;
    }

    if (g_interpreter->Invoke() != kTfLiteOk)
    {
        printf("[wake_word] invoke failed\n");
        return false;
    }
    tick_invoke_done = rt_tick_get();

    if (g_output->type == kTfLiteFloat32)
    {
        score0 = g_output->data.f[0];
        score1 = g_output->data.f[1];
        *confidence = score1;
    }
    else if (g_output->type == kTfLiteInt8)
    {
        output_scale = g_output->params.scale;
        output_zero_point = g_output->params.zero_point;
        output_data = g_output->data.int8;
        score0 = ((float)output_data[0] - (float)output_zero_point) * output_scale;
        score1 = ((float)output_data[1] - (float)output_zero_point) * output_scale;
        *confidence = score1;
    }
    else
    {
        printf("[wake_word] unsupported output type=%d\n", g_output->type);
        return false;
    }
    if ((*confidence > WAKE_WORD_THRESHOLD) || (*confidence >= 0.300f))
    {
        printf("[wake_word] timing mfcc=%lu ms invoke=%lu ms total=%lu ms score0=%ld score1=%ld detect=%d\n",
               (unsigned long)(((tick_mfcc_done - tick_start) * 1000U) / RT_TICK_PER_SECOND),
               (unsigned long)(((tick_invoke_done - tick_mfcc_done) * 1000U) / RT_TICK_PER_SECOND),
               (unsigned long)(((tick_invoke_done - tick_start) * 1000U) / RT_TICK_PER_SECOND),
               (long)(score0 * 1000.0f),
               (long)(score1 * 1000.0f),
               (*confidence > WAKE_WORD_THRESHOLD) ? 1 : 0);
    }
    return (*confidence > WAKE_WORD_THRESHOLD);
}

void WakeWordDetector_GetInfo(void)
{
    printf("[wake_word] info sr=%d mfcc=%d frames=%d threshold=%.2f model=%u\n",
           SAMPLE_RATE,
           N_MFCC,
           N_FRAMES,
           WAKE_WORD_THRESHOLD,
           wake_word_model_len);
}

bool WakeWordDetector_DumpFeatures(const char *path)
{
    FILE *fp;
    size_t written;

    if ((path == nullptr) || (*path == '\0') || (g_mfcc_features == nullptr))
    {
        return false;
    }

    fp = fopen(path, "wb");
    if (fp == nullptr)
    {
        return false;
    }

    written = fwrite(g_mfcc_features, sizeof(float), INPUT_SIZE, fp);
    fclose(fp);

    if (written != INPUT_SIZE)
    {
        return false;
    }

    printf("[wake_word] feature dump saved path=%s count=%d\n", path, INPUT_SIZE);
    return true;
}
