#include "emg_intent_bridge.h"

#include "intent_tflm_runtime.h"
#include "model_result_publisher.h"

#include <math.h>
#include <rthw.h>
#include <string.h>

#define EMG_INTENT_PHYSICAL_CHANNELS 4U
#define EMG_INTENT_MODEL_CHANNELS 3U
#define EMG_INTENT_BYTES_PER_SAMPLE 2U
#define EMG_INTENT_REST_INDEX 1
#define EMG_INTENT_DETECTED_CONFIDENCE 400U
#define EMG_INTENT_INPUT_SCALE 0.05868540704250336f
#define EMG_INTENT_INPUT_ZERO_POINT -47

typedef struct
{
    float mean;
    float std;
    float min;
    float max;
    float mav;
    float rms;
} emg_channel_features_t;

static const float kFeatureMeans[INTENT_TFLM_FEATURE_COUNT] = {
    14.824007703006313f,
    66.07682380117653f,
    20.284824699792935f,
    36.619129132341925f,
    105.17267572483149f,
    66.07682380117653f,
    70.48601249420804f,
    3.378661093195168f,
    3.495710555813804f,
    0.2908954744837916f,
    11.771691451802717f,
    3.378661093195168f,
    5.063158951460208f,
    51.0093492123582f,
    17.206955290189292f,
    26.3894297635605f,
    84.20284583288756f,
    51.0093492123582f,
    55.015025679892005f,
    14.824007703006313f,
    323.47073927463356f,
};

static const float kFeatureStds[INTENT_TFLM_FEATURE_COUNT] = {
    0.5970123425713738f,
    117.031946284698f,
    29.185581407396917f,
    80.8248029689966f,
    164.0962701851204f,
    117.031946284698f,
    119.82327575513715f,
    16.669337205936774f,
    12.76114023471683f,
    4.954700705219328f,
    42.877063558387256f,
    16.669337205936774f,
    20.945483223842892f,
    76.95630161575073f,
    20.919422397549834f,
    52.482338932488624f,
    109.77286498810477f,
    76.95630161575073f,
    78.93842257537969f,
    0.5970123425713738f,
    206.08876507283696f,
};

static rt_uint32_t g_emg_intent_window_count;
static rt_uint32_t g_emg_intent_last_seq;
static rt_uint32_t g_emg_intent_error_count;
static rt_err_t g_emg_intent_init_ret = -1;

static rt_uint16_t emg_u16_le(const rt_uint8_t *data)
{
    return (rt_uint16_t)((rt_uint16_t)data[0] | ((rt_uint16_t)data[1] << 8));
}

static int emg_round_i32(float value)
{
    return (value >= 0.0f) ? (int)(value + 0.5f) : (int)(value - 0.5f);
}

static int8_t emg_quantize_feature(float value, int feature_index)
{
    float std = kFeatureStds[feature_index];
    float scaled;
    int quantized;

    if (std == 0.0f)
    {
        std = 1.0f;
    }
    scaled = (value - kFeatureMeans[feature_index]) / std;
    quantized = emg_round_i32((scaled / EMG_INTENT_INPUT_SCALE) +
                              (float)EMG_INTENT_INPUT_ZERO_POINT);
    if (quantized < -128)
    {
        quantized = -128;
    }
    if (quantized > 127)
    {
        quantized = 127;
    }
    return (int8_t)quantized;
}

extern "C" rt_err_t emg_intent_bridge_init(void)
{
    g_emg_intent_init_ret = (rt_err_t)intent_tflm_runtime_init();
    rt_kprintf("[emg_intent] runtime init ret=%d physical_ch=%u model_ch=%u\n",
               g_emg_intent_init_ret,
               (unsigned)EMG_INTENT_PHYSICAL_CHANNELS,
               (unsigned)EMG_INTENT_MODEL_CHANNELS);
    return g_emg_intent_init_ret;
}

static void emg_compute_channel_features(const rt_uint8_t *raw,
                                         rt_uint32_t frame_samples,
                                         rt_uint32_t stride_channels,
                                         rt_uint32_t channel,
                                         emg_channel_features_t *features)
{
    float sum = 0.0f;
    float abs_sum = 0.0f;
    float square_sum = 0.0f;
    float min_value = 65535.0f;
    float max_value = 0.0f;

    for (rt_uint32_t i = 0U; i < frame_samples; i++)
    {
        rt_uint32_t sample_offset = (i * stride_channels + channel) *
                                    EMG_INTENT_BYTES_PER_SAMPLE;
        float value = (float)emg_u16_le(&raw[sample_offset]);

        sum += value;
        abs_sum += (value >= 0.0f) ? value : -value;
        square_sum += value * value;
        if (value < min_value)
        {
            min_value = value;
        }
        if (value > max_value)
        {
            max_value = value;
        }
    }

    features->mean = sum / (float)frame_samples;
    features->mav = abs_sum / (float)frame_samples;
    features->rms = sqrtf(square_sum / (float)frame_samples);
    {
        float variance = (square_sum / (float)frame_samples) -
                         (features->mean * features->mean);
        features->std = (variance > 0.0f) ? sqrtf(variance) : 0.0f;
    }
    features->min = min_value;
    features->max = max_value;
}

static void emg_build_quantized_input(const rt_uint8_t *raw,
                                      rt_uint32_t frame_samples,
                                      rt_uint32_t stride_channels,
                                      rt_uint32_t stale_count,
                                      int8_t *input)
{
    emg_channel_features_t channels[EMG_INTENT_MODEL_CHANNELS];
    float features[INTENT_TFLM_FEATURE_COUNT];
    int cursor = 0;

    memset(channels, 0, sizeof(channels));
    for (rt_uint32_t channel = 0U; channel < EMG_INTENT_MODEL_CHANNELS; channel++)
    {
        emg_compute_channel_features(raw, frame_samples, stride_channels, channel, &channels[channel]);
    }

    features[cursor++] = (float)frame_samples;
    for (rt_uint32_t channel = 0U; channel < EMG_INTENT_MODEL_CHANNELS; channel++)
    {
        features[cursor++] = channels[channel].mean;
        features[cursor++] = channels[channel].std;
        features[cursor++] = channels[channel].min;
        features[cursor++] = channels[channel].max;
        features[cursor++] = channels[channel].mav;
        features[cursor++] = channels[channel].rms;
    }
    features[cursor++] = (float)stale_count;
    if (cursor < INTENT_TFLM_FEATURE_COUNT)
    {
        int placeholder_index = cursor;
        features[cursor++] = kFeatureMeans[placeholder_index];
    }

    for (int i = 0; i < INTENT_TFLM_FEATURE_COUNT; i++)
    {
        input[i] = emg_quantize_feature(features[i], i);
    }
}

static rt_uint32_t emg_stream_model_channels(const sensor_stream_msg_t *stream)
{
    if ((stream != RT_NULL) && (stream->reserved0 != 0U))
    {
        return stream->reserved0;
    }
    return EMG_INTENT_MODEL_CHANNELS;
}

static rt_bool_t emg_stream_is_valid(const sensor_stream_msg_t *stream)
{
    rt_uint32_t expected_len;
    rt_uint32_t model_channels;

    if (stream == RT_NULL)
    {
        return RT_FALSE;
    }
    if ((stream->source != MODEL_INPUT_SRC_EMG) ||
        (stream->format != MODEL_INPUT_FMT_UINT16) ||
        (stream->channels < EMG_INTENT_MODEL_CHANNELS) ||
        (stream->channels > EMG_INTENT_PHYSICAL_CHANNELS) ||
        (stream->frame_samples == 0U))
    {
        return RT_FALSE;
    }
    model_channels = emg_stream_model_channels(stream);
    if (model_channels != EMG_INTENT_MODEL_CHANNELS)
    {
        return RT_FALSE;
    }

    expected_len = stream->frame_samples *
                   stream->channels *
                   EMG_INTENT_BYTES_PER_SAMPLE;
    if ((stream->total_len < expected_len) ||
        (stream->chunk_len < expected_len) ||
        (expected_len > M33_M55_PCM_SHARED_CAPACITY))
    {
        return RT_FALSE;
    }

    return RT_TRUE;
}

extern "C" rt_err_t emg_intent_bridge_handle_stream(const sensor_stream_msg_t *stream)
{
    intent_tflm_result_t result;
    int8_t input[INTENT_TFLM_FEATURE_COUNT];
    rt_uint32_t expected_len;
    rt_uint32_t stale_count;
    rt_uint16_t window_ms;
    rt_bool_t detected;
    rt_err_t ret;
    const rt_uint8_t *raw;

    if (stream == RT_NULL)
    {
        g_emg_intent_error_count++;
        return -RT_EINVAL;
    }

    if (!emg_stream_is_valid(stream))
    {
        g_emg_intent_error_count++;
        rt_kprintf("[emg_intent] reject stream src=%u fmt=%u ch=%u samples=%lu len=%lu\n",
                   stream ? stream->source : 0U,
                   stream ? stream->format : 0U,
                   stream ? stream->channels : 0U,
                   stream ? (unsigned long)stream->frame_samples : 0UL,
                   stream ? (unsigned long)stream->total_len : 0UL);
        return -RT_EINVAL;
    }

    m33_m55_shared_pcm_invalidate_header(&g_m33_m55_pcm_shared);
    if (stream->chunk_index != g_m33_m55_pcm_shared.seq)
    {
        g_emg_intent_error_count++;
        rt_kprintf("[emg_intent] shared seq mismatch msg=%lu shared=%lu\n",
                   (unsigned long)stream->chunk_index,
                   (unsigned long)g_m33_m55_pcm_shared.seq);
        return -RT_EBUSY;
    }

    expected_len = stream->frame_samples *
                   stream->channels *
                   EMG_INTENT_BYTES_PER_SAMPLE;
    if (expected_len == 0U)
    {
        return -RT_EINVAL;
    }
    stale_count = stream->reserved1;
    if (stale_count > stream->frame_samples)
    {
        stale_count = stream->frame_samples;
    }

    raw = (const rt_uint8_t *)(const void *)g_m33_m55_pcm_shared.data;
    m33_m55_shared_pcm_invalidate_payload(&g_m33_m55_pcm_shared, expected_len);
    emg_build_quantized_input(raw, stream->frame_samples, stream->channels, stale_count, input);

    ret = (rt_err_t)intent_tflm_runtime_infer_int8(input, sizeof(input), &result);
    if (ret != RT_EOK)
    {
        g_emg_intent_error_count++;
        rt_kprintf("[emg_intent] infer failed ret=%d seq=%lu\n",
                   ret,
                   (unsigned long)stream->chunk_index);
        return ret;
    }

    window_ms = (stream->sample_rate == 0U) ? 0U :
        (rt_uint16_t)((stream->frame_samples * 1000U + (stream->sample_rate / 2U)) /
                      stream->sample_rate);
    detected = ((result.predicted_index != EMG_INTENT_REST_INDEX) &&
                (result.confidence_permille >= EMG_INTENT_DETECTED_CONFIDENCE)) ?
        RT_TRUE : RT_FALSE;

    ret = model_result_publish(MODEL_CODE_EMG_INTENT,
                               (rt_uint8_t)result.predicted_index,
                               result.confidence_permille,
                               detected,
                               RT_TRUE,
                               window_ms);
    g_emg_intent_window_count++;
    g_emg_intent_last_seq = stream->chunk_index;
    rt_kprintf("[emg_intent] seq=%lu label=%s idx=%d conf=%u detected=%d win=%u ret=%d out=[%d,%d,%d]\n",
               (unsigned long)stream->chunk_index,
               result.label,
               result.predicted_index,
               result.confidence_permille,
               detected ? 1 : 0,
               window_ms,
               ret,
               result.output_int8[0],
               result.output_int8[1],
               result.output_int8[2]);
    return ret;
}

static void emg_intent_status_cmd(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("[emg_intent] init_ret=%d windows=%lu last_seq=%lu errors=%lu\n",
               g_emg_intent_init_ret,
               (unsigned long)g_emg_intent_window_count,
               (unsigned long)g_emg_intent_last_seq,
               (unsigned long)g_emg_intent_error_count);
}
MSH_CMD_EXPORT_ALIAS(emg_intent_status_cmd, emg_intent, Show CM55 EMG intent bridge status);
