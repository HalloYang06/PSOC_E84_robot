#include <rtthread.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

#include "tflite_learn_333519_3.h"

#include "model-parameters/model_metadata.h"
#include "edge-impulse-sdk/dsp/numpy.hpp"
#include "edge-impulse-sdk/classifier/ei_signal_with_range.h"
#include "edge-impulse-sdk/classifier/ei_run_dsp.h"

#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#define XIAOZHI_EI_SAMPLE_RATE 16000
#define XIAOZHI_EI_RAW_SAMPLES 16000
#define XIAOZHI_EI_INPUT_SIZE 650
#define XIAOZHI_EI_N_FRAMES 50
#define XIAOZHI_EI_N_CEPSTRAL 13
#define XIAOZHI_EI_N_FILTERS 32
#define XIAOZHI_EI_FRAME_LEN 320
#define XIAOZHI_EI_HOP_LEN 320
#define XIAOZHI_EI_FFT_SIZE 256
#define XIAOZHI_EI_THRESHOLD 0.80f
#define XIAOZHI_EI_ARENA_SIZE 32768

extern "C" int g_ifx_wwd_ethosu_stub_seen;
int g_ifx_wwd_ethosu_stub_seen;

static int16_t *g_audio_window;
static float *g_features;
static float *g_frame;
static float *g_spectrum;
static float *g_mel;
static uint8_t *g_tensor_arena;
static size_t g_audio_count;
static int g_stage;
static int g_last_error;
static int g_last_confidence_permille;
static int g_last_noise_permille;
static int g_last_feature_source;
static int g_last_feature_error;
static int g_last_alloc_source;
static size_t g_last_alloc_size;
static int g_last_alloc_fail_source;
static size_t g_last_alloc_fail_size;
static uint32_t g_hyperam_alloc_count;
static uint32_t g_heap_alloc_count;
static uint32_t g_alloc_fail_count;
static uint32_t g_inference_count;

static const tflite::Model *g_model;
static tflite::MicroInterpreter *g_interpreter;
static TfLiteTensor *g_input;
static TfLiteTensor *g_output;
static tflite::MicroErrorReporter g_error_reporter;

void *ei_malloc(size_t size)
{
    struct rt_memheap *hyperam = (struct rt_memheap *)rt_object_find("hyperam", RT_Object_Class_MemHeap);
    void *ptr = RT_NULL;

    g_last_alloc_size = size;
    g_last_alloc_source = 0;

    if (hyperam != RT_NULL)
    {
        ptr = rt_memheap_alloc(hyperam, (rt_size_t)size);
        if (ptr != RT_NULL)
        {
            g_last_alloc_source = 1;
            g_hyperam_alloc_count++;
            return ptr;
        }
    }

    ptr = rt_malloc((rt_size_t)size);
    if (ptr != RT_NULL)
    {
        g_last_alloc_source = 2;
        g_heap_alloc_count++;
    }
    else
    {
        g_last_alloc_source = (hyperam != RT_NULL) ? -2 : -1;
        g_last_alloc_fail_source = g_last_alloc_source;
        g_last_alloc_fail_size = size;
        g_alloc_fail_count++;
    }
    return ptr;
}

void *ei_calloc(size_t nitems, size_t size)
{
    size_t bytes = nitems * size;
    void *ptr;

    if ((size != 0U) && ((bytes / size) != nitems))
    {
        return RT_NULL;
    }

    ptr = ei_malloc(bytes);
    if (ptr != RT_NULL)
    {
        memset(ptr, 0, bytes);
    }
    return ptr;
}

void ei_free(void *ptr)
{
    if (ptr != RT_NULL)
    {
        rt_free(ptr);
    }
}

static int get_audio_signal_data(size_t offset, size_t length, float *out_ptr)
{
    if ((g_audio_window == RT_NULL) || (out_ptr == RT_NULL) ||
        ((offset + length) > XIAOZHI_EI_RAW_SAMPLES))
    {
        return -1;
    }

    for (size_t i = 0; i < length; i++)
    {
        out_ptr[i] = (float)g_audio_window[offset + i];
    }
    return 0;
}

static float hz_to_mel(float hz)
{
    return 2595.0f * log10f(1.0f + hz / 700.0f);
}

static float mel_to_hz(float mel)
{
    return 700.0f * (powf(10.0f, mel / 2595.0f) - 1.0f);
}

static void apply_hamming(float *frame)
{
    for (int i = 0; i < XIAOZHI_EI_FRAME_LEN; i++)
    {
        frame[i] *= 0.54f - 0.46f * cosf((2.0f * 3.14159265358979323846f * i) /
                                          (XIAOZHI_EI_FRAME_LEN - 1));
    }
}

static void compute_power_spectrum(const float *input, float *power_spectrum)
{
    for (int k = 0; k < (XIAOZHI_EI_FFT_SIZE / 2); k++)
    {
        float real = 0.0f;
        float imag = 0.0f;
        for (int n = 0; n < XIAOZHI_EI_FFT_SIZE; n++)
        {
            float angle = 2.0f * 3.14159265358979323846f * (float)(k * n) /
                          (float)XIAOZHI_EI_FFT_SIZE;
            real += input[n] * cosf(angle);
            imag -= input[n] * sinf(angle);
        }
        power_spectrum[k] = real * real + imag * imag;
    }
}

static void compute_mel_energies(const float *power_spectrum, float *mel_energies)
{
    int bins[XIAOZHI_EI_N_FILTERS + 2];
    const float mel_min = hz_to_mel(0.0f);
    const float mel_max = hz_to_mel((float)XIAOZHI_EI_SAMPLE_RATE / 2.0f);

    for (int i = 0; i < XIAOZHI_EI_N_FILTERS + 2; i++)
    {
        float mel = mel_min + ((mel_max - mel_min) * (float)i) /
                                  (float)(XIAOZHI_EI_N_FILTERS + 1);
        int bin = (int)floorf(((float)XIAOZHI_EI_FFT_SIZE + 1.0f) *
                              mel_to_hz(mel) / (float)XIAOZHI_EI_SAMPLE_RATE);
        if (bin < 0)
        {
            bin = 0;
        }
        else if (bin > (XIAOZHI_EI_FFT_SIZE / 2 - 1))
        {
            bin = XIAOZHI_EI_FFT_SIZE / 2 - 1;
        }
        bins[i] = bin;
    }

    for (int m = 0; m < XIAOZHI_EI_N_FILTERS; m++)
    {
        float energy = 0.0f;
        int left = bins[m];
        int center = bins[m + 1];
        int right = bins[m + 2];

        if (center <= left)
        {
            center = left + 1;
        }
        if (right <= center)
        {
            right = center + 1;
        }

        for (int k = left; k < center && k < XIAOZHI_EI_FFT_SIZE / 2; k++)
        {
            energy += power_spectrum[k] * ((float)(k - left) / (float)(center - left));
        }
        for (int k = center; k < right && k < XIAOZHI_EI_FFT_SIZE / 2; k++)
        {
            energy += power_spectrum[k] * ((float)(right - k) / (float)(right - center));
        }
        mel_energies[m] = logf(energy + 1.0e-6f);
    }
}

static int extract_features(const int16_t *pcm, float *features)
{
    static ei_dsp_config_mfcc_t mfcc_config = {
        2,
        4,
        1,
        RT_NULL,
        0,
        13,
        0.02f,
        0.02f,
        32,
        256,
        101,
        0,
        0,
        0.98f,
        1
    };
    ei::signal_t signal;
    ei::matrix_t output_matrix(1, XIAOZHI_EI_INPUT_SIZE, features);
    int ret;

    if ((pcm == RT_NULL) || (features == RT_NULL) ||
        (g_frame == RT_NULL) || (g_spectrum == RT_NULL) || (g_mel == RT_NULL))
    {
        return -RT_EINVAL;
    }

    signal.total_length = XIAOZHI_EI_RAW_SAMPLES;
    signal.get_data = &get_audio_signal_data;
    ret = extract_mfcc_features(&signal,
                                &output_matrix,
                                &mfcc_config,
                                (float)XIAOZHI_EI_SAMPLE_RATE);
    if (ret == 0)
    {
        g_last_feature_source = 1;
        g_last_feature_error = 0;
        return 0;
    }

    g_last_feature_source = 2;
    g_last_feature_error = ret;
    if ((g_inference_count <= 3U) || ((g_inference_count % 8U) == 0U))
    {
        rt_kprintf("[xiaozhi_ei_wake] feature_fallback ret=%d alloc_src=%d alloc_size=%d hyper=%lu heap=%lu fail=%lu\n",
                   ret,
                   g_last_alloc_source,
                   (int)g_last_alloc_size,
                   (unsigned long)g_hyperam_alloc_count,
                   (unsigned long)g_heap_alloc_count,
                   (unsigned long)g_alloc_fail_count);
    }

    for (int frame_idx = 0; frame_idx < XIAOZHI_EI_N_FRAMES; frame_idx++)
    {
        int start = frame_idx * XIAOZHI_EI_HOP_LEN;

        memset(g_frame, 0, sizeof(float) * XIAOZHI_EI_FRAME_LEN);
        for (int i = 0; i < XIAOZHI_EI_FRAME_LEN; i++)
        {
            int idx = start + i;
            float prev = (idx > 0) ? (float)pcm[idx - 1] : 0.0f;
            g_frame[i] = (float)pcm[idx] - 0.98f * prev;
        }

        apply_hamming(g_frame);
        compute_power_spectrum(g_frame, g_spectrum);
        compute_mel_energies(g_spectrum, g_mel);

        for (int c = 0; c < XIAOZHI_EI_N_CEPSTRAL; c++)
        {
            float sum = 0.0f;
            for (int m = 0; m < XIAOZHI_EI_N_FILTERS; m++)
            {
                sum += g_mel[m] * cosf(3.14159265358979323846f * (float)c *
                                       ((float)m + 0.5f) / (float)XIAOZHI_EI_N_FILTERS);
            }
            features[frame_idx * XIAOZHI_EI_N_CEPSTRAL + c] = sum;
        }
    }

    return 0;
}

static int run_inference(int *detected, int *confidence_permille)
{
    int8_t *input_i8;
    int8_t *output_i8;
    int ret;

    if ((g_interpreter == RT_NULL) || (g_input == RT_NULL) || (g_output == RT_NULL) ||
        (g_audio_window == RT_NULL) || (g_features == RT_NULL))
    {
        return -1;
    }

    ret = extract_features(g_audio_window, g_features);
    if (ret != 0)
    {
        return ret;
    }
    g_stage = (g_last_feature_source == 1) ? 201 : 202;

    if (g_input->type != kTfLiteInt8)
    {
        return -2;
    }

    input_i8 = g_input->data.int8;
    for (int i = 0; i < XIAOZHI_EI_INPUT_SIZE; i++)
    {
        int32_t q = (int32_t)(g_features[i] / g_input->params.scale +
                              g_input->params.zero_point);
        if (q < -128)
        {
            q = -128;
        }
        else if (q > 127)
        {
            q = 127;
        }
        input_i8[i] = (int8_t)q;
    }

    if (g_interpreter->Invoke() != kTfLiteOk)
    {
        return -3;
    }

    if (g_output->type != kTfLiteInt8)
    {
        return -4;
    }

    output_i8 = g_output->data.int8;
    {
        float confidence = ((float)output_i8[1] - (float)g_output->params.zero_point) *
                           g_output->params.scale;
        float noise = ((float)output_i8[0] - (float)g_output->params.zero_point) *
                      g_output->params.scale;
        g_last_noise_permille = (int)(noise * 1000.0f);
        g_last_confidence_permille = (int)(confidence * 1000.0f);
        g_inference_count++;
        if ((g_inference_count <= 3U) || ((g_inference_count % 8U) == 0U))
        {
            rt_kprintf("[xiaozhi_ei_wake] infer=%lu feature_src=%d feature_ret=%d noise=%d/1000 xiaorui=%d/1000 in_scale=%d in_zero=%d out_scale=%d out_zero=%d\n",
                       (unsigned long)g_inference_count,
                       g_last_feature_source,
                       g_last_feature_error,
                       g_last_noise_permille,
                       g_last_confidence_permille,
                       (int)(g_input->params.scale * 1000000.0f),
                       g_input->params.zero_point,
                       (int)(g_output->params.scale * 1000000.0f),
                       g_output->params.zero_point);
        }
        if (confidence_permille != RT_NULL)
        {
            *confidence_permille = g_last_confidence_permille;
        }
        if ((confidence >= XIAOZHI_EI_THRESHOLD) && (detected != RT_NULL))
        {
            *detected = 1;
        }
    }

    return 0;
}

extern "C" int xiaozhi_edge_impulse_wake_init(void)
{
    g_stage = 1;
    g_last_error = 0;
    g_last_confidence_permille = 0;
    g_last_noise_permille = 0;
    g_last_feature_source = 0;
    g_last_feature_error = 0;
    g_last_alloc_source = 0;
    g_last_alloc_size = 0;
    g_last_alloc_fail_source = 0;
    g_last_alloc_fail_size = 0;
    g_hyperam_alloc_count = 0;
    g_heap_alloc_count = 0;
    g_alloc_fail_count = 0;
    g_inference_count = 0;
    g_audio_count = 0;

    if (g_audio_window == RT_NULL)
    {
        g_audio_window = (int16_t *)rt_malloc_align(sizeof(int16_t) * XIAOZHI_EI_RAW_SAMPLES, 16);
    }
    if (g_features == RT_NULL)
    {
        g_features = (float *)rt_malloc_align(sizeof(float) * XIAOZHI_EI_INPUT_SIZE, 16);
    }
    if (g_frame == RT_NULL)
    {
        g_frame = (float *)rt_malloc_align(sizeof(float) * XIAOZHI_EI_FRAME_LEN, 16);
    }
    if (g_spectrum == RT_NULL)
    {
        g_spectrum = (float *)rt_malloc_align(sizeof(float) * (XIAOZHI_EI_FFT_SIZE / 2), 16);
    }
    if (g_mel == RT_NULL)
    {
        g_mel = (float *)rt_malloc_align(sizeof(float) * XIAOZHI_EI_N_FILTERS, 16);
    }
    if (g_tensor_arena == RT_NULL)
    {
        g_tensor_arena = (uint8_t *)rt_malloc_align(XIAOZHI_EI_ARENA_SIZE, 16);
    }
    if ((g_audio_window == RT_NULL) || (g_features == RT_NULL) || (g_frame == RT_NULL) ||
        (g_spectrum == RT_NULL) || (g_mel == RT_NULL) || (g_tensor_arena == RT_NULL))
    {
        g_stage = 2;
        g_last_error = -RT_ENOMEM;
        return -RT_ENOMEM;
    }
    memset(g_audio_window, 0, sizeof(int16_t) * XIAOZHI_EI_RAW_SAMPLES);

    g_model = tflite::GetModel(tflite_learn_333519_3);
    if ((g_model == RT_NULL) || (g_model->version() != TFLITE_SCHEMA_VERSION))
    {
        g_stage = 3;
        g_last_error = -1;
        return -1;
    }

    static tflite::MicroMutableOpResolver<5> resolver;
    static bool resolver_ready = false;
    if (!resolver_ready)
    {
        if ((resolver.AddConv2D() != kTfLiteOk) ||
            (resolver.AddFullyConnected() != kTfLiteOk) ||
            (resolver.AddMaxPool2D() != kTfLiteOk) ||
            (resolver.AddReshape() != kTfLiteOk) ||
            (resolver.AddSoftmax() != kTfLiteOk))
        {
            g_stage = 4;
            g_last_error = -2;
            return -2;
        }
        resolver_ready = true;
    }

    static tflite::MicroInterpreter interpreter(g_model,
                                                resolver,
                                                g_tensor_arena,
                                                XIAOZHI_EI_ARENA_SIZE,
                                                &g_error_reporter);
    g_interpreter = &interpreter;

    g_stage = 5;
    if (g_interpreter->AllocateTensors() != kTfLiteOk)
    {
        g_last_error = -3;
        return -3;
    }

    g_input = g_interpreter->input(0);
    g_output = g_interpreter->output(0);
    if ((g_input == RT_NULL) || (g_output == RT_NULL))
    {
        g_stage = 6;
        g_last_error = -4;
        return -4;
    }

    g_stage = 10;
    rt_kprintf("[xiaozhi_ei_wake] ready official_xiaozhi_tflite arena_used=%d input_type=%d output_type=%d\n",
               g_interpreter->arena_used_bytes(),
               g_input->type,
               g_output->type);
    rt_kprintf("[xiaozhi_ei_wake] tensor_params input_scale=%d/1e6 input_zero=%d output_scale=%d/1e6 output_zero=%d\n",
               (int)(g_input->params.scale * 1000000.0f),
               g_input->params.zero_point,
               (int)(g_output->params.scale * 1000000.0f),
               g_output->params.zero_point);
    return 0;
}

extern "C" int xiaozhi_edge_impulse_wake_process(const int16_t *pcm,
                                                  uint32_t sample_count,
                                                  int *detected,
                                                  int *confidence_permille)
{
    uint32_t offset = 0;

    if (detected != RT_NULL)
    {
        *detected = 0;
    }

    while (offset < sample_count)
    {
        size_t room = XIAOZHI_EI_RAW_SAMPLES - g_audio_count;
        size_t copy_count = sample_count - offset;
        if (copy_count > room)
        {
            copy_count = room;
        }

        memcpy(&g_audio_window[g_audio_count], &pcm[offset], copy_count * sizeof(int16_t));
        g_audio_count += copy_count;
        offset += (uint32_t)copy_count;

        if (g_audio_count == XIAOZHI_EI_RAW_SAMPLES)
        {
            int ret;
            g_stage = 20;
            ret = run_inference(detected, confidence_permille);
            if (ret != 0)
            {
                g_stage = 21;
                g_last_error = ret;
                return ret;
            }

            if ((detected != RT_NULL) && (*detected != 0))
            {
                rt_kprintf("[xiaozhi_ei_wake] detected confidence=%d/1000\n",
                           g_last_confidence_permille);
                g_audio_count = 0;
                return 0;
            }

            memmove(g_audio_window,
                    &g_audio_window[XIAOZHI_EI_RAW_SAMPLES / 4],
                    (XIAOZHI_EI_RAW_SAMPLES - (XIAOZHI_EI_RAW_SAMPLES / 4)) * sizeof(int16_t));
            g_audio_count = XIAOZHI_EI_RAW_SAMPLES - (XIAOZHI_EI_RAW_SAMPLES / 4);
        }
    }

    g_last_error = 0;
    return 0;
}

extern "C" int xiaozhi_edge_impulse_wake_stage(void)
{
    return g_stage;
}

extern "C" int xiaozhi_edge_impulse_wake_last_error(void)
{
    return g_last_error;
}

extern "C" int xiaozhi_edge_impulse_wake_last_confidence_permille(void)
{
    return g_last_confidence_permille;
}

extern "C" int xiaozhi_edge_impulse_wake_last_noise_permille(void)
{
    return g_last_noise_permille;
}

extern "C" int xiaozhi_edge_impulse_wake_last_feature_source(void)
{
    return g_last_feature_source;
}

extern "C" int xiaozhi_edge_impulse_wake_last_feature_error(void)
{
    return g_last_feature_error;
}

extern "C" int xiaozhi_edge_impulse_wake_last_alloc_source(void)
{
    return g_last_alloc_source;
}

extern "C" int xiaozhi_edge_impulse_wake_last_alloc_size(void)
{
    return (int)g_last_alloc_size;
}

extern "C" int xiaozhi_edge_impulse_wake_last_alloc_fail_source(void)
{
    return g_last_alloc_fail_source;
}

extern "C" int xiaozhi_edge_impulse_wake_last_alloc_fail_size(void)
{
    return (int)g_last_alloc_fail_size;
}

extern "C" int xiaozhi_edge_impulse_wake_alloc_diag(void)
{
    return (int)((g_hyperam_alloc_count & 0xffU) * 10000U +
                 (g_heap_alloc_count & 0xffU) * 100U +
                 (g_alloc_fail_count & 0xffU));
}
