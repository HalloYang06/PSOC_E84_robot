#include "wake_word_tflite.h"
#include "wake_word_model.h"

#include "hey_jarvis_model.h"
#include "tensorflow/lite/micro/micro_allocator.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_resource_variable.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "../../../_third_party/tflite-micro/tensorflow/lite/experimental/microfrontend/lib/frontend.h"
#include "../../../_third_party/tflite-micro/tensorflow/lite/experimental/microfrontend/lib/frontend_util.h"

#include <cmath>
#include <cstring>

namespace
{
constexpr int kFeatureSize = 40;
constexpr int kFeatureDurationMs = 30;
constexpr int kFeatureStepMs = 10;
constexpr int kAudioSampleRate = WAKE_WORD_AUDIO_SAMPLE_RATE;
constexpr int kStepSamples = (kFeatureStepMs * (kAudioSampleRate / 1000));
constexpr int kBufferLengthMs = 64;
constexpr int kBufferSamples = (kAudioSampleRate / 1000) * kBufferLengthMs;
constexpr int kMinSlicesBeforeDetection = 74;
constexpr int kResolverOps = 20;
constexpr int kResourceVars = 20;
constexpr int kVarArenaSize = 1024;
constexpr float kFeatureNormalizeDiv = 25.6f;

struct WakeWordState
{
    rt_bool_t initialized;
    struct FrontendConfig frontend_config;
    struct FrontendState frontend_state;

    tflite::MicroAllocator* var_allocator;
    tflite::MicroResourceVariables* resource_variables;
    tflite::MicroInterpreter* interpreter;
    TfLiteTensor* input;
    TfLiteTensor* output;

    int16_t ring_buffer[kBufferSamples];
    size_t ring_head;
    size_t ring_tail;
    size_t ring_count;
    int16_t preprocessor_audio_buffer[kStepSamples];
    uint8_t current_stride_step;
    int ignore_windows;

    uint8_t recent_probabilities[WAKE_WORD_SLIDING_WINDOW_SIZE];
    size_t recent_index;
    size_t recent_count;
    uint32_t processed_windows;
};

static WakeWordState g_state = {};
alignas(16) static uint8_t g_tensor_arena[WAKE_WORD_TENSOR_ARENA_SIZE];
alignas(16) static uint8_t g_var_arena[kVarArenaSize];

static tflite::MicroMutableOpResolver<kResolverOps> g_resolver;
static tflite::MicroInterpreter* g_interpreter_instance = RT_NULL;

static void log_init_stage(const char* stage)
{
    rt_kprintf("[wake_word] init stage=%s tick=%u\n", stage, (unsigned)rt_tick_get());
    rt_thread_mdelay(1);
}

static bool register_streaming_ops(void)
{
    return g_resolver.AddCallOnce() == kTfLiteOk &&
           g_resolver.AddVarHandle() == kTfLiteOk &&
           g_resolver.AddReshape() == kTfLiteOk &&
           g_resolver.AddReadVariable() == kTfLiteOk &&
           g_resolver.AddStridedSlice() == kTfLiteOk &&
           g_resolver.AddConcatenation() == kTfLiteOk &&
           g_resolver.AddAssignVariable() == kTfLiteOk &&
           g_resolver.AddConv2D() == kTfLiteOk &&
           g_resolver.AddMul() == kTfLiteOk &&
           g_resolver.AddAdd() == kTfLiteOk &&
           g_resolver.AddMean() == kTfLiteOk &&
           g_resolver.AddFullyConnected() == kTfLiteOk &&
           g_resolver.AddLogistic() == kTfLiteOk &&
           g_resolver.AddQuantize() == kTfLiteOk &&
           g_resolver.AddDepthwiseConv2D() == kTfLiteOk &&
           g_resolver.AddAveragePool2D() == kTfLiteOk &&
           g_resolver.AddMaxPool2D() == kTfLiteOk &&
           g_resolver.AddPad() == kTfLiteOk &&
           g_resolver.AddPack() == kTfLiteOk &&
           g_resolver.AddSplitV() == kTfLiteOk;
}

static void setup_frontend_config(void)
{
    memset(&g_state.frontend_config, 0, sizeof(g_state.frontend_config));
    g_state.frontend_config.window.size_ms = kFeatureDurationMs;
    g_state.frontend_config.window.step_size_ms = kFeatureStepMs;
    g_state.frontend_config.filterbank.num_channels = kFeatureSize;
    g_state.frontend_config.filterbank.lower_band_limit = 125.0f;
    g_state.frontend_config.filterbank.upper_band_limit = 7500.0f;
    g_state.frontend_config.noise_reduction.smoothing_bits = 10;
    g_state.frontend_config.noise_reduction.even_smoothing = 0.025f;
    g_state.frontend_config.noise_reduction.odd_smoothing = 0.06f;
    g_state.frontend_config.noise_reduction.min_signal_remaining = 0.05f;
    g_state.frontend_config.pcan_gain_control.enable_pcan = 1;
    g_state.frontend_config.pcan_gain_control.strength = 0.95f;
    g_state.frontend_config.pcan_gain_control.offset = 80.0f;
    g_state.frontend_config.pcan_gain_control.gain_bits = 21;
    g_state.frontend_config.log_scale.enable_log = 1;
    g_state.frontend_config.log_scale.scale_shift = 6;
}

static void reset_probability_state(void)
{
    memset(g_state.recent_probabilities, 0, sizeof(g_state.recent_probabilities));
    g_state.recent_index = 0;
    g_state.recent_count = 0;
}

static void reset_stream_state(void)
{
    g_state.ring_head = 0;
    g_state.ring_tail = 0;
    g_state.ring_count = 0;
    g_state.current_stride_step = 0;
    g_state.ignore_windows = -kMinSlicesBeforeDetection;
    g_state.processed_windows = 0;
    reset_probability_state();
    FrontendReset(&g_state.frontend_state);
}

static void push_audio_samples(const int16_t* audio_data, uint32_t len)
{
    for (uint32_t i = 0; i < len; ++i)
    {
        if (g_state.ring_count == kBufferSamples)
        {
            g_state.ring_tail = (g_state.ring_tail + 1U) % kBufferSamples;
            g_state.ring_count--;
        }

        g_state.ring_buffer[g_state.ring_head] = audio_data[i];
        g_state.ring_head = (g_state.ring_head + 1U) % kBufferSamples;
        g_state.ring_count++;
    }
}

static rt_bool_t has_enough_samples(void)
{
    return g_state.ring_count >= kStepSamples;
}

static rt_bool_t generate_features_for_window(int8_t features[kFeatureSize])
{
    if (!has_enough_samples())
    {
        return RT_FALSE;
    }

    for (size_t i = 0; i < kStepSamples; ++i)
    {
        g_state.preprocessor_audio_buffer[i] = g_state.ring_buffer[g_state.ring_tail];
        g_state.ring_tail = (g_state.ring_tail + 1U) % kBufferSamples;
    }
    g_state.ring_count -= kStepSamples;

    size_t num_samples_read = 0;
    const struct FrontendOutput frontend_output =
        FrontendProcessSamples(&g_state.frontend_state,
                               g_state.preprocessor_audio_buffer,
                               kStepSamples,
                               &num_samples_read);

    if (frontend_output.size == 0 || frontend_output.values == RT_NULL)
    {
        return RT_FALSE;
    }

    if (frontend_output.size != kFeatureSize)
    {
        rt_kprintf("[wake_word] frontend size mismatch=%u\n", (unsigned)frontend_output.size);
        return RT_FALSE;
    }

    if ((g_state.processed_windows % 25U) == 0U)
    {
        int32_t min_value = frontend_output.values[0];
        int32_t max_value = frontend_output.values[0];
        int64_t sum_value = 0;
        for (size_t i = 0; i < frontend_output.size; ++i)
        {
            const int32_t v = frontend_output.values[i];
            if (v < min_value)
            {
                min_value = v;
            }
            if (v > max_value)
            {
                max_value = v;
            }
            sum_value += v;
        }
        rt_kprintf("[wake_word] feat min=%d max=%d avg=%d norm=%d zp=%d sc=%d\n",
                   (int)min_value,
                   (int)max_value,
                   (int)(sum_value / (int64_t)frontend_output.size),
                   (int)(kFeatureNormalizeDiv * 1000.0f),
                   (int)g_state.input->params.zero_point,
                   (int)(g_state.input->params.scale * 1000000.0f));
    }

    for (size_t i = 0; i < frontend_output.size; ++i)
    {
        constexpr int32_t value_scale = 256;
        constexpr int32_t value_div = 666;
        int32_t value =
            ((frontend_output.values[i] * value_scale) + (value_div / 2)) /
            value_div;
        value -= 128;
        if (value < -128)
        {
            value = -128;
        }
        if (value > 127)
        {
            value = 127;
        }
        features[i] = (int8_t)value;
    }

    return RT_TRUE;
}

static rt_bool_t perform_streaming_inference(const int8_t features[kFeatureSize])
{
    const uint8_t stride = (uint8_t)g_state.input->dims->data[1];
    const size_t offset = (size_t)kFeatureSize * g_state.current_stride_step;

    if (g_state.input->type == kTfLiteInt8)
    {
        int8_t* input_data = tflite::GetTensorData<int8_t>(g_state.input);
        memcpy(input_data + offset, features, kFeatureSize);
    }
    else if (g_state.input->type == kTfLiteUInt8)
    {
        uint8_t* input_data = tflite::GetTensorData<uint8_t>(g_state.input);
        for (size_t i = 0; i < kFeatureSize; ++i)
        {
            input_data[offset + i] = (uint8_t)((int)features[i] + 128);
        }
    }
    else if (g_state.input->type == kTfLiteFloat32)
    {
        float* input_data = tflite::GetTensorData<float>(g_state.input);
        for (size_t i = 0; i < kFeatureSize; ++i)
        {
            input_data[offset + i] =
                ((float)((int)features[i] + 128) * 26.0f) / 255.0f;
        }
    }
    else
    {
        rt_kprintf("[wake_word] Unsupported input tensor type=%d\n", (int)g_state.input->type);
        return RT_FALSE;
    }
    g_state.current_stride_step++;

    if (g_state.current_stride_step < stride)
    {
        return RT_FALSE;
    }

    g_state.current_stride_step = 0;
    if (g_state.interpreter->Invoke() != kTfLiteOk)
    {
        rt_kprintf("[wake_word] Invoke failed\n");
        return RT_FALSE;
    }

    uint8_t raw_score = 0;
    float score = 0.0f;
    if (g_state.output->type == kTfLiteUInt8)
    {
        raw_score = g_state.output->data.uint8[0];
        score = (float)raw_score / 255.0f;
    }
    else if (g_state.output->type == kTfLiteInt8)
    {
        const int32_t centered = (int32_t)g_state.output->data.int8[0] + 128;
        raw_score = (uint8_t)((centered < 0) ? 0 : ((centered > 255) ? 255 : centered));
        score = (float)raw_score / 255.0f;
    }
    else if (g_state.output->type == kTfLiteFloat32)
    {
        score = g_state.output->data.f[0];
        if (score < 0.0f)
        {
            score = 0.0f;
        }
        if (score > 1.0f)
        {
            score = 1.0f;
        }
        raw_score = (uint8_t)(score * 255.0f);
    }
    else
    {
        rt_kprintf("[wake_word] Unsupported output tensor type=%d\n", (int)g_state.output->type);
        return RT_FALSE;
    }

    g_state.recent_probabilities[g_state.recent_index] = raw_score;
    g_state.recent_index = (g_state.recent_index + 1U) % WAKE_WORD_SLIDING_WINDOW_SIZE;
    if (g_state.recent_count < WAKE_WORD_SLIDING_WINDOW_SIZE)
    {
        g_state.recent_count++;
    }

    g_state.processed_windows++;
    if ((g_state.processed_windows % 25U) == 0U)
    {
        rt_kprintf("[wake_word] output raw=%u score=%d.%03d windows=%u\n",
                   (unsigned)raw_score,
                   (int)score,
                   (int)((score - (int)score) * 1000.0f),
                   (unsigned)g_state.processed_windows);
    }

    return RT_TRUE;
}

static rt_bool_t determine_detected(void)
{
    if (g_state.ignore_windows < 0)
    {
        g_state.ignore_windows++;
        return RT_FALSE;
    }

    uint32_t sum = 0;
    uint8_t peak = 0;
    for (size_t i = 0; i < g_state.recent_count; ++i)
    {
        const uint8_t prob = g_state.recent_probabilities[i];
        sum += prob;
        if (prob > peak)
        {
            peak = prob;
        }
    }

    const float average = (g_state.recent_count == 0U)
                              ? 0.0f
                              : (float)sum / (255.0f * (float)g_state.recent_count);
    const float peak_score = (float)peak / 255.0f;

    if (peak_score >= 0.20f && (g_state.processed_windows % 10U) == 0U)
    {
        rt_kprintf("[wake_word] avg=%d.%03d peak=%d.%03d count=%u\n",
                   (int)average,
                   (int)((average - (int)average) * 1000.0f),
                   (int)peak_score,
                   (int)((peak_score - (int)peak_score) * 1000.0f),
                   (unsigned)g_state.recent_count);
    }

    return average > WAKE_WORD_PROBABILITY_CUTOFF;
}

} // namespace

extern "C"
{

rt_err_t wake_word_tflite_init(void)
{
    if (g_state.initialized)
    {
        rt_kprintf("[wake_word] init already done\n");
        return RT_EOK;
    }

    memset(&g_state, 0, sizeof(g_state));
    log_init_stage("reset");
    setup_frontend_config();
    log_init_stage("frontend_config");

    log_init_stage("register_streaming_ops");
    if (!register_streaming_ops())
    {
        rt_kprintf("[wake_word] Failed to register streaming ops\n");
        return -RT_ERROR;
    }

    log_init_stage("FrontendPopulateState");
    if (!FrontendPopulateState(&g_state.frontend_config, &g_state.frontend_state, kAudioSampleRate))
    {
        rt_kprintf("[wake_word] FrontendPopulateState failed\n");
        return -RT_ERROR;
    }

    log_init_stage("GetModel");
    const tflite::Model* model = tflite::GetModel(hey_jarvis_tflite);
    if (model == RT_NULL || model->version() != TFLITE_SCHEMA_VERSION)
    {
        rt_kprintf("[wake_word] Model/schema invalid model=%p version=%d runtime=%d\n",
                   model,
                   model ? model->version() : -1,
                   TFLITE_SCHEMA_VERSION);
        return -RT_ERROR;
    }

    log_init_stage("CreateVarAllocator");
    g_state.var_allocator = tflite::MicroAllocator::Create(g_var_arena, sizeof(g_var_arena));
    if (g_state.var_allocator == RT_NULL)
    {
        rt_kprintf("[wake_word] Failed to create var allocator\n");
        return -RT_ERROR;
    }

    log_init_stage("CreateResourceVars");
    g_state.resource_variables = tflite::MicroResourceVariables::Create(g_state.var_allocator, kResourceVars);
    if (g_state.resource_variables == RT_NULL)
    {
        rt_kprintf("[wake_word] Failed to create resource vars\n");
        return -RT_ERROR;
    }

    log_init_stage("CreateInterpreter");
    static tflite::MicroInterpreter static_interpreter(
        model,
        g_resolver,
        g_tensor_arena,
        sizeof(g_tensor_arena),
        g_state.resource_variables,
        nullptr,
        false);

    g_interpreter_instance = &static_interpreter;

    log_init_stage("AllocateTensors");
    if (g_interpreter_instance->AllocateTensors() != kTfLiteOk)
    {
        rt_kprintf("[wake_word] AllocateTensors failed used=%u arena=%u\n",
                   (unsigned)g_interpreter_instance->arena_used_bytes(),
                   (unsigned)sizeof(g_tensor_arena));
        FrontendFreeStateContents(&g_state.frontend_state);
        return -RT_ERROR;
    }

    log_init_stage("get_io_tensors");
    g_state.interpreter = g_interpreter_instance;
    g_state.input = g_interpreter_instance->input(0);
    rt_kprintf("[wake_word] input ptr=%p tick=%u\n",
               g_state.input,
               (unsigned)rt_tick_get());
    rt_thread_mdelay(1);
    g_state.output = g_interpreter_instance->output(0);
    rt_kprintf("[wake_word] output ptr=%p tick=%u\n",
               g_state.output,
               (unsigned)rt_tick_get());
    rt_thread_mdelay(1);
    g_state.ignore_windows = -kMinSlicesBeforeDetection;

    if (g_state.input == RT_NULL || g_state.output == RT_NULL)
    {
        rt_kprintf("[wake_word] Missing tensors\n");
        FrontendFreeStateContents(&g_state.frontend_state);
        return -RT_ERROR;
    }

    rt_kprintf("[wake_word] tensor types in=%d out=%d tick=%u\n",
               (int)g_state.input->type,
               (int)g_state.output->type,
               (unsigned)rt_tick_get());
    rt_thread_mdelay(1);

    if (!((g_state.input->type == kTfLiteInt8) ||
          (g_state.input->type == kTfLiteUInt8) ||
          (g_state.input->type == kTfLiteFloat32)) ||
        !((g_state.output->type == kTfLiteUInt8) ||
          (g_state.output->type == kTfLiteInt8) ||
          (g_state.output->type == kTfLiteFloat32)))
    {
        rt_kprintf("[wake_word] Tensor type mismatch in=%d out=%d\n",
                   (int)g_state.input->type,
                   (int)g_state.output->type);
        FrontendFreeStateContents(&g_state.frontend_state);
        return -RT_ERROR;
    }

    rt_kprintf("[wake_word] dims ptr in=%p out=%p tick=%u\n",
               g_state.input->dims,
               g_state.output->dims,
               (unsigned)rt_tick_get());
    rt_thread_mdelay(1);

    if (g_state.input->dims == RT_NULL)
    {
        rt_kprintf("[wake_word] input dims null\n");
        FrontendFreeStateContents(&g_state.frontend_state);
        return -RT_ERROR;
    }

    rt_kprintf("[wake_word] dims size=%d tick=%u\n",
               g_state.input->dims->size,
               (unsigned)rt_tick_get());
    rt_thread_mdelay(1);

    if (g_state.input->dims->size > 0)
    {
        rt_kprintf("[wake_word] dims[0]=%d tick=%u\n",
                   g_state.input->dims->data[0],
                   (unsigned)rt_tick_get());
        rt_thread_mdelay(1);
    }

    if (g_state.input->dims->size > 1)
    {
        rt_kprintf("[wake_word] dims[1]=%d tick=%u\n",
                   g_state.input->dims->data[1],
                   (unsigned)rt_tick_get());
        rt_thread_mdelay(1);
    }

    if (g_state.input->dims->size > 2)
    {
        rt_kprintf("[wake_word] dims[2]=%d tick=%u\n",
                   g_state.input->dims->data[2],
                   (unsigned)rt_tick_get());
        rt_thread_mdelay(1);
    }

    if (g_state.input->dims->size != 3 ||
        g_state.input->dims->data[0] != 1 ||
        g_state.input->dims->data[2] != kFeatureSize)
    {
        rt_kprintf("[wake_word] Input dims mismatch size=%d [%d,%d,%d]\n",
                   g_state.input->dims->size,
                   g_state.input->dims->size > 0 ? g_state.input->dims->data[0] : -1,
                   g_state.input->dims->size > 1 ? g_state.input->dims->data[1] : -1,
                   g_state.input->dims->size > 2 ? g_state.input->dims->data[2] : -1);
        FrontendFreeStateContents(&g_state.frontend_state);
        return -RT_ERROR;
    }

    reset_stream_state();
    g_state.initialized = RT_TRUE;

    rt_kprintf("[wake_word] TFLM wake word ready (input=%d x %d, stride=%dms, used=%u/%u)\n",
               g_state.input->dims->data[1],
               g_state.input->dims->data[2],
               kFeatureStepMs,
               (unsigned)g_interpreter_instance->arena_used_bytes(),
               (unsigned)sizeof(g_tensor_arena));
    rt_kprintf("[wake_word] input type=%d output type=%d in_scale=%d out_scale=%d\n",
               (int)g_state.input->type,
               (int)g_state.output->type,
               (int)(g_state.input->params.scale * 1000000.0f),
               (int)(g_state.output->params.scale * 1000000.0f));

    return RT_EOK;
}

rt_bool_t wake_word_tflite_detect(const int16_t* audio_data, uint32_t len)
{
    if (!g_state.initialized || audio_data == RT_NULL || len == 0)
    {
        return RT_FALSE;
    }

    push_audio_samples(audio_data, len);

    while (has_enough_samples())
    {
        int8_t features[kFeatureSize];
        if (!generate_features_for_window(features))
        {
            continue;
        }

        g_state.ignore_windows = std::min(g_state.ignore_windows + 1, 0);

        if (!perform_streaming_inference(features))
        {
            continue;
        }

        if (determine_detected())
        {
            reset_stream_state();
            return RT_TRUE;
        }
    }

    return RT_FALSE;
}

}
