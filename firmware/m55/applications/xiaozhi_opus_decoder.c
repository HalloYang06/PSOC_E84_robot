#include "xiaozhi_opus_decoder.h"
#include "xiaozhi_voice_relay.h"

#if XIAOZHI_USE_OFFICIAL_OPUS_AUDIO || XIAOZHI_ENABLE_OPUS_CODEC

#include <opus.h>
#include <rtdevice.h>
#include <string.h>

#define XIAOZHI_OPUS_ENCODER_SAMPLE_RATE 16000
#define XIAOZHI_OPUS_DECODER_SAMPLE_RATE 24000
#define XIAOZHI_OPUS_CHANNELS     1
#define XIAOZHI_OPUS_MAX_MS       60
#define XIAOZHI_OPUS_MAX_SAMPLE_RATE 48000
#define XIAOZHI_OPUS_ENCODER_SAMPLES ((XIAOZHI_OPUS_ENCODER_SAMPLE_RATE * XIAOZHI_OPUS_MAX_MS) / 1000)
#define XIAOZHI_OPUS_MAX_SAMPLES  ((XIAOZHI_OPUS_MAX_SAMPLE_RATE * XIAOZHI_OPUS_MAX_MS) / 1000)

typedef struct
{
    rt_bool_t ready;
    void *state;
    int state_size;
    int sample_rate;
    int channels;
} xiaozhi_opus_decoder_t;

static xiaozhi_opus_decoder_t g_opus_decoder;
static xiaozhi_opus_decoder_t g_opus_encoder;

rt_err_t xiaozhi_opus_decoder_init(void)
{
    int sample_rate = g_opus_decoder.sample_rate ? g_opus_decoder.sample_rate : XIAOZHI_OPUS_DECODER_SAMPLE_RATE;
    int channels = g_opus_decoder.channels ? g_opus_decoder.channels : XIAOZHI_OPUS_CHANNELS;

    if (g_opus_decoder.ready)
    {
        return RT_EOK;
    }

    if ((channels != 1) && (channels != 2))
    {
        rt_kprintf("[xiaozhi_opus] decoder channels unsupported: %d\n", channels);
        return -RT_EINVAL;
    }

    g_opus_decoder.state_size = opus_decoder_get_size(channels);
    if (g_opus_decoder.state_size <= 0)
    {
        rt_kprintf("[xiaozhi_opus] decoder size invalid: %d\n", g_opus_decoder.state_size);
        return -RT_ERROR;
    }

    g_opus_decoder.state = rt_malloc((rt_size_t)g_opus_decoder.state_size);
    if (g_opus_decoder.state == RT_NULL)
    {
        rt_kprintf("[xiaozhi_opus] alloc decoder state failed size=%d\n", g_opus_decoder.state_size);
        return -RT_ENOMEM;
    }

    if (opus_decoder_init((OpusDecoder *)g_opus_decoder.state,
                          sample_rate,
                          channels) != OPUS_OK)
    {
        rt_kprintf("[xiaozhi_opus] decoder init failed\n");
        rt_free(g_opus_decoder.state);
        g_opus_decoder.state = RT_NULL;
        return -RT_ERROR;
    }

    g_opus_decoder.ready = RT_TRUE;
    g_opus_decoder.sample_rate = sample_rate;
    g_opus_decoder.channels = channels;
    rt_kprintf("[xiaozhi_opus] ready sr=%d ch=%d size=%d\n",
               g_opus_decoder.sample_rate,
               g_opus_decoder.channels,
               g_opus_decoder.state_size);
    return RT_EOK;
}

rt_err_t xiaozhi_opus_decoder_configure(int sample_rate, int channels)
{
    if ((sample_rate != 8000) && (sample_rate != 12000) &&
        (sample_rate != 16000) && (sample_rate != 24000) &&
        (sample_rate != 48000))
    {
        rt_kprintf("[xiaozhi_opus] decoder sample rate unsupported: %d\n", sample_rate);
        return -RT_EINVAL;
    }

    if ((channels != 1) && (channels != 2))
    {
        rt_kprintf("[xiaozhi_opus] decoder channels unsupported: %d\n", channels);
        return -RT_EINVAL;
    }

    if ((g_opus_decoder.sample_rate == sample_rate) &&
        (g_opus_decoder.channels == channels) &&
        g_opus_decoder.ready)
    {
        return RT_EOK;
    }

    xiaozhi_opus_decoder_deinit();
    g_opus_decoder.sample_rate = sample_rate;
    g_opus_decoder.channels = channels;
    return xiaozhi_opus_decoder_init();
}

rt_err_t xiaozhi_opus_decoder_reset(void)
{
    if (!g_opus_decoder.ready)
    {
        return xiaozhi_opus_decoder_init();
    }

    if (opus_decoder_ctl((OpusDecoder *)g_opus_decoder.state, OPUS_RESET_STATE) != OPUS_OK)
    {
        rt_kprintf("[xiaozhi_opus] decoder reset failed\n");
        return -RT_ERROR;
    }

    return RT_EOK;
}

int xiaozhi_opus_decoder_sample_rate(void)
{
    return g_opus_decoder.sample_rate ? g_opus_decoder.sample_rate : XIAOZHI_OPUS_DECODER_SAMPLE_RATE;
}

rt_err_t xiaozhi_opus_decoder_decode(const uint8_t *packet,
                                     rt_size_t packet_len,
                                     int16_t *pcm_out,
                                     rt_size_t pcm_out_cap_samples,
                                     rt_size_t *pcm_out_samples)
{
    int frame_samples;
    int decoded;

    if (pcm_out_samples != RT_NULL)
    {
        *pcm_out_samples = 0U;
    }

    if ((packet == RT_NULL) || (packet_len == 0U) || (pcm_out == RT_NULL) || (pcm_out_cap_samples == 0U))
    {
        return -RT_EINVAL;
    }

    if (!g_opus_decoder.ready)
    {
        rt_err_t ret = xiaozhi_opus_decoder_init();
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    frame_samples = opus_packet_get_nb_samples(packet,
                                               (opus_int32)packet_len,
                                               xiaozhi_opus_decoder_sample_rate());
    if ((frame_samples <= 0) || (frame_samples > (int)pcm_out_cap_samples) || (frame_samples > XIAOZHI_OPUS_MAX_SAMPLES))
    {
        rt_kprintf("[xiaozhi_opus] invalid packet len=%lu frame=%d cap=%lu\n",
                   (unsigned long)packet_len,
                   frame_samples,
                   (unsigned long)pcm_out_cap_samples);
        return -RT_EINVAL;
    }

    decoded = opus_decode((OpusDecoder *)g_opus_decoder.state,
                          packet,
                          (opus_int32)packet_len,
                          pcm_out,
                          frame_samples,
                          0);
    if (decoded < 0)
    {
        rt_kprintf("[xiaozhi_opus] decode failed len=%lu err=%d head=%02x %02x %02x %02x\n",
                   (unsigned long)packet_len,
                   decoded,
                   packet_len > 0U ? packet[0] : 0U,
                   packet_len > 1U ? packet[1] : 0U,
                   packet_len > 2U ? packet[2] : 0U,
                   packet_len > 3U ? packet[3] : 0U);
        return -RT_ERROR;
    }

    if (pcm_out_samples != RT_NULL)
    {
        *pcm_out_samples = (rt_size_t)decoded;
    }

    return RT_EOK;
}

void xiaozhi_opus_decoder_deinit(void)
{
    if (g_opus_decoder.state != RT_NULL)
    {
        rt_free(g_opus_decoder.state);
        g_opus_decoder.state = RT_NULL;
    }
    g_opus_decoder.ready = RT_FALSE;
    g_opus_decoder.state_size = 0;
}

rt_err_t xiaozhi_opus_encoder_init(void)
{
    if (g_opus_encoder.ready)
    {
        return RT_EOK;
    }

    g_opus_encoder.state_size = opus_encoder_get_size(XIAOZHI_OPUS_CHANNELS);
    if (g_opus_encoder.state_size <= 0)
    {
        rt_kprintf("[xiaozhi_opus] encoder size invalid: %d\n", g_opus_encoder.state_size);
        return -RT_ERROR;
    }

    g_opus_encoder.state = rt_malloc((rt_size_t)g_opus_encoder.state_size);
    if (g_opus_encoder.state == RT_NULL)
    {
        rt_kprintf("[xiaozhi_opus] alloc encoder state failed size=%d\n", g_opus_encoder.state_size);
        return -RT_ENOMEM;
    }

    if (opus_encoder_init((OpusEncoder *)g_opus_encoder.state,
                          XIAOZHI_OPUS_ENCODER_SAMPLE_RATE,
                          XIAOZHI_OPUS_CHANNELS,
                          OPUS_APPLICATION_VOIP) != OPUS_OK)
    {
        rt_kprintf("[xiaozhi_opus] encoder init failed\n");
        rt_free(g_opus_encoder.state);
        g_opus_encoder.state = RT_NULL;
        return -RT_ERROR;
    }

    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_EXPERT_FRAME_DURATION(OPUS_FRAMESIZE_60_MS));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_BITRATE(16000));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_COMPLEXITY(0));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_VBR(1));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_VBR_CONSTRAINT(1));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_LSB_DEPTH(16));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_DTX(0));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_INBAND_FEC(0));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_PACKET_LOSS_PERC(0));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_PREDICTION_DISABLED(0));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_MAX_BANDWIDTH(OPUS_BANDWIDTH_WIDEBAND));
    (void)opus_encoder_ctl((OpusEncoder *)g_opus_encoder.state, OPUS_SET_BANDWIDTH(OPUS_AUTO));
    g_opus_encoder.ready = RT_TRUE;
    rt_kprintf("[xiaozhi_opus] encoder ready sr=%d ch=%d size=%d\n",
               XIAOZHI_OPUS_ENCODER_SAMPLE_RATE,
               XIAOZHI_OPUS_CHANNELS,
               g_opus_encoder.state_size);
    return RT_EOK;
}

rt_err_t xiaozhi_opus_encoder_encode(const int16_t *pcm,
                                     rt_size_t pcm_samples,
                                     uint8_t *packet_out,
                                     rt_size_t packet_out_cap,
                                     rt_size_t *packet_out_len)
{
    opus_int32 encoded;

    if (packet_out_len != RT_NULL)
    {
        *packet_out_len = 0U;
    }

    if ((pcm == RT_NULL) || (packet_out == RT_NULL) || (packet_out_cap == 0U))
    {
        return -RT_EINVAL;
    }

    if (pcm_samples != XIAOZHI_OPUS_ENCODER_SAMPLES)
    {
        rt_kprintf("[xiaozhi_opus] encoder needs %u samples, got %lu\n",
                   (unsigned)XIAOZHI_OPUS_ENCODER_SAMPLES,
                   (unsigned long)pcm_samples);
        return -RT_EINVAL;
    }

    if (!g_opus_encoder.ready)
    {
        rt_err_t ret = xiaozhi_opus_encoder_init();
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    encoded = opus_encode((OpusEncoder *)g_opus_encoder.state,
                          (const opus_int16 *)pcm,
                          (int)pcm_samples,
                          packet_out,
                          (opus_int32)packet_out_cap);
    if (encoded < 0)
    {
        rt_kprintf("[xiaozhi_opus] encode failed samples=%lu err=%d\n",
                   (unsigned long)pcm_samples,
                   (int)encoded);
        return -RT_ERROR;
    }

    if (packet_out_len != RT_NULL)
    {
        *packet_out_len = (rt_size_t)encoded;
    }

    return RT_EOK;
}

void xiaozhi_opus_encoder_deinit(void)
{
    if (g_opus_encoder.state != RT_NULL)
    {
        rt_free(g_opus_encoder.state);
        g_opus_encoder.state = RT_NULL;
    }
    g_opus_encoder.ready = RT_FALSE;
    g_opus_encoder.state_size = 0;
}
#else
rt_err_t xiaozhi_opus_decoder_init(void) { return -RT_ENOSYS; }
rt_err_t xiaozhi_opus_decoder_configure(int sample_rate, int channels) { RT_UNUSED(sample_rate); RT_UNUSED(channels); return -RT_ENOSYS; }
rt_err_t xiaozhi_opus_decoder_reset(void) { return -RT_ENOSYS; }
int xiaozhi_opus_decoder_sample_rate(void) { return 16000; }
rt_err_t xiaozhi_opus_decoder_decode(const uint8_t *packet, rt_size_t packet_len, int16_t *pcm_out, rt_size_t pcm_out_cap_samples, rt_size_t *pcm_out_samples) { RT_UNUSED(packet); RT_UNUSED(packet_len); RT_UNUSED(pcm_out); RT_UNUSED(pcm_out_cap_samples); if (pcm_out_samples) *pcm_out_samples = 0; return -RT_ENOSYS; }
rt_err_t xiaozhi_opus_encoder_init(void) { return -RT_ENOSYS; }
rt_err_t xiaozhi_opus_encoder_encode(const int16_t *pcm, rt_size_t pcm_samples, uint8_t *packet_out, rt_size_t packet_out_cap, rt_size_t *packet_out_len) { RT_UNUSED(pcm); RT_UNUSED(pcm_samples); RT_UNUSED(packet_out); RT_UNUSED(packet_out_cap); if (packet_out_len) *packet_out_len = 0; return -RT_ENOSYS; }
void xiaozhi_opus_decoder_deinit(void) {}
void xiaozhi_opus_encoder_deinit(void) {}
#endif
