#include "audio_playback.h"
#include <rtdevice.h>
#include <finsh.h>
#include <stdlib.h>

#define PLAYBACK_MONO_FRAME_BYTES RT_AUDIO_REPLAY_MP_BLOCK_SIZE
#define PLAYBACK_MONO_FRAME_MS ((PLAYBACK_MONO_FRAME_BYTES * 1000U) / (AUDIO_SAMPLE_RATE * sizeof(int16_t)))

typedef struct {
    rt_bool_t initialized;
    rt_bool_t playing;
    rt_mutex_t mutex;
    rt_device_t speaker;
    char speaker_name[RT_NAME_MAX];
    uint8_t pending[PLAYBACK_MONO_FRAME_BYTES];
    uint32_t pending_len;
    uint32_t written_frames;
} audio_playback_t;

static audio_playback_t g_playback = {0};

static const int16_t g_sine_64_q15[64] =
{
    0, 3212, 6393, 9512, 12539, 15446, 18204, 20787,
    23170, 25330, 27245, 28898, 30273, 31356, 32137, 32609,
    32767, 32609, 32137, 31356, 30273, 28898, 27245, 25330,
    23170, 20787, 18204, 15446, 12539, 9512, 6393, 3212,
    0, -3212, -6393, -9512, -12539, -15446, -18204, -20787,
    -23170, -25330, -27245, -28898, -30273, -31356, -32137, -32609,
    -32767, -32609, -32137, -31356, -30273, -28898, -27245, -25330,
    -23170, -20787, -18204, -15446, -12539, -9512, -6393, -3212,
};

typedef struct
{
    uint16_t duration_ms;
    uint16_t f0_start_hz;
    uint16_t f0_end_hz;
    uint8_t vowel;
} audio_voice_segment_t;

static const char *const g_speaker_candidates[] =
{
    "sound0",
    "audio0",
    "codec0",
    "i2s0",
    "dac0",
    RT_NULL
};

static rt_device_t audio_playback_find_speaker(const char **name)
{
    rt_device_t dev = RT_NULL;

    for (int i = 0; g_speaker_candidates[i] != RT_NULL; i++)
    {
        dev = rt_device_find(g_speaker_candidates[i]);
        rt_kprintf("[audio_playback] probe %s -> %s\n",
                   g_speaker_candidates[i],
                   dev ? "found" : "none");
        if (dev != RT_NULL)
        {
            if (name != RT_NULL)
            {
                *name = g_speaker_candidates[i];
            }
            return dev;
        }
    }

    if (name != RT_NULL)
    {
        *name = RT_NULL;
    }
    return RT_NULL;
}

static int16_t audio_sine_u16(uint32_t phase)
{
    return g_sine_64_q15[(phase >> 10) & 0x3fU];
}

static int16_t audio_voice_sample(uint32_t phase, uint8_t vowel, uint32_t env_q15)
{
    int32_t s1 = audio_sine_u16(phase);
    int32_t s2 = audio_sine_u16(phase * 2U);
    int32_t s3 = audio_sine_u16(phase * 3U);
    int32_t s4 = audio_sine_u16(phase * 4U);
    int32_t mixed;

    if (vowel == 0U)
    {
        mixed = (s1 * 9 + s2 * 4 + s3 * 2 + s4) / 16;
    }
    else if (vowel == 1U)
    {
        mixed = (s1 * 6 + s2 * 2 + s3 * 5 + s4 * 2) / 15;
    }
    else
    {
        mixed = (s1 * 7 + s2 * 5 + s3 + s4 * 3) / 16;
    }

    mixed = (mixed * (int32_t)env_q15) >> 15;
    mixed = mixed / 3;
    if (mixed > 28000)
    {
        mixed = 28000;
    }
    else if (mixed < -28000)
    {
        mixed = -28000;
    }
    return (int16_t)mixed;
}

rt_err_t audio_playback_init(void)
{
    rt_err_t ret;
    struct rt_audio_caps caps;
    const char *speaker_name = RT_NULL;

    if (g_playback.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_playback, 0, sizeof(g_playback));

    g_playback.mutex = rt_mutex_create("audio_pb", RT_IPC_FLAG_PRIO);
    if (!g_playback.mutex)
    {
        return -RT_ERROR;
    }

    g_playback.speaker = audio_playback_find_speaker(&speaker_name);
    if (g_playback.speaker == RT_NULL)
    {
        rt_kprintf("[audio_playback] ERROR: Cannot find speaker device. Run list_device and check Sound Device name.\n");
        return -RT_ERROR;
    }
    rt_strncpy(g_playback.speaker_name, speaker_name, sizeof(g_playback.speaker_name) - 1);

    ret = rt_device_open(g_playback.speaker, RT_DEVICE_OFLAG_WRONLY);
    if (ret != RT_EOK)
    {
        rt_kprintf("[audio_playback] ERROR: Failed to open %s ret=%d\n",
                   g_playback.speaker_name,
                   ret);
        return ret;
    }

    rt_memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_OUTPUT;
    caps.sub_type = AUDIO_DSP_PARAM;
    caps.udata.config.samplerate = AUDIO_SAMPLE_RATE;
    caps.udata.config.channels = AUDIO_CHANNELS;
    caps.udata.config.samplebits = AUDIO_BITS_PER_SAMPLE;
    if (rt_device_control(g_playback.speaker, AUDIO_CTL_CONFIGURE, &caps) != RT_EOK)
    {
        rt_kprintf("[audio_playback] WARN: Failed to configure %s dsp params\n",
                   g_playback.speaker_name);
    }

    g_playback.initialized = RT_TRUE;
    rt_kprintf("[audio_playback] Initialized (using %s sr=%d ch=%d bits=%d)\n",
               g_playback.speaker_name,
               AUDIO_SAMPLE_RATE,
               AUDIO_CHANNELS,
               AUDIO_BITS_PER_SAMPLE);

    return RT_EOK;
}

rt_err_t audio_playback_start(void)
{
    if (!g_playback.initialized)
    {
        return -RT_ERROR;
    }

    if (g_playback.playing)
    {
        return RT_EOK;
    }

    g_playback.playing = RT_TRUE;
    rt_kprintf("[audio_playback] Started\n");
    return RT_EOK;
}

rt_err_t audio_playback_stop(void)
{
    if (!g_playback.playing)
    {
        return RT_EOK;
    }

    g_playback.playing = RT_FALSE;

    rt_kprintf("[audio_playback] Stopped\n");
    return RT_EOK;
}

rt_err_t audio_playback_write(const uint8_t *data, uint32_t len)
{
    uint32_t offset = 0U;

    if (!g_playback.initialized || !data || len == 0)
    {
        return -RT_EINVAL;
    }

    while (offset < len)
    {
        uint32_t space;
        uint32_t copy_len;

        rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
        space = PLAYBACK_MONO_FRAME_BYTES - g_playback.pending_len;
        copy_len = len - offset;
        if (copy_len > space)
        {
            copy_len = space;
        }
        rt_memcpy(g_playback.pending + g_playback.pending_len, data + offset, copy_len);
        g_playback.pending_len += copy_len;
        offset += copy_len;

        if (g_playback.pending_len >= PLAYBACK_MONO_FRAME_BYTES)
        {
            rt_size_t written;

            written = rt_device_write(g_playback.speaker, 0, g_playback.pending, PLAYBACK_MONO_FRAME_BYTES);
            g_playback.pending_len = 0U;
            if (written == 0)
            {
                rt_mutex_release(g_playback.mutex);
                rt_kprintf("[audio_playback] %s block write failed frames=%lu\n",
                           g_playback.speaker_name,
                           (unsigned long)g_playback.written_frames);
                return -RT_ERROR;
            }
            g_playback.written_frames++;
            rt_mutex_release(g_playback.mutex);
            rt_thread_mdelay(PLAYBACK_MONO_FRAME_MS);
        }
        else
        {
            rt_mutex_release(g_playback.mutex);
        }
    }

    return RT_EOK;
}

rt_err_t audio_playback_flush(void)
{
    rt_size_t written = 1U;

    if (!g_playback.initialized || (g_playback.speaker == RT_NULL))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
    if (g_playback.pending_len > 0U)
    {
        rt_memset(g_playback.pending + g_playback.pending_len, 0,
                  PLAYBACK_MONO_FRAME_BYTES - g_playback.pending_len);
        written = rt_device_write(g_playback.speaker, 0,
                                  g_playback.pending,
                                  PLAYBACK_MONO_FRAME_BYTES);
        g_playback.pending_len = 0U;
        if (written != 0)
        {
            g_playback.written_frames++;
        }
    }
    rt_mutex_release(g_playback.mutex);

    rt_kprintf("[audio_playback] flush written=%lu ret=%lu\n",
               (unsigned long)g_playback.written_frames,
               (unsigned long)written);
    return written == 0 ? -RT_ERROR : RT_EOK;
}

void audio_playback_clear(void)
{
    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
    g_playback.pending_len = 0;
    rt_mutex_release(g_playback.mutex);
}

static void audio_playback_probe_cmd(int argc, char **argv)
{
    const char *name = RT_NULL;
    rt_device_t dev;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    dev = audio_playback_find_speaker(&name);
    rt_kprintf("[audio_playback] selected=%s dev=%p initialized=%d playing=%d buffered=%lu\n",
               name ? name : "(none)",
               dev,
               g_playback.initialized ? 1 : 0,
               g_playback.playing ? 1 : 0,
               (unsigned long)g_playback.pending_len);
}
MSH_CMD_EXPORT(audio_playback_probe_cmd, Probe speaker playback device candidates);

static void audio_playback_tone_cmd(int argc, char **argv)
{
    uint32_t duration_ms = 800U;
    uint32_t total_bytes;
    uint32_t sent = 0U;
    int16_t frame[256];

    if (argc > 1)
    {
        long parsed = strtol(argv[1], RT_NULL, 10);
        if ((parsed > 0) && (parsed <= 5000))
        {
            duration_ms = (uint32_t)parsed;
        }
    }

    if (audio_playback_init() != RT_EOK)
    {
        rt_kprintf("[audio_playback] tone init failed\n");
        return;
    }
    (void)audio_playback_start();

    total_bytes = (AUDIO_SAMPLE_RATE * AUDIO_CHANNELS *
                   (AUDIO_BITS_PER_SAMPLE / 8U) * duration_ms) / 1000U;
    rt_kprintf("[audio_playback] tone start ms=%lu bytes=%lu\n",
               (unsigned long)duration_ms,
               (unsigned long)total_bytes);

    while (sent < total_bytes)
    {
        uint32_t samples = sizeof(frame) / sizeof(frame[0]);
        uint32_t chunk_bytes;

        for (uint32_t i = 0; i < samples; i++)
        {
            frame[i] = ((i / 16U) & 1U) ? -9000 : 9000;
        }

        chunk_bytes = sizeof(frame);
        if ((sent + chunk_bytes) > total_bytes)
        {
            chunk_bytes = total_bytes - sent;
        }

        if (audio_playback_write((const uint8_t *)frame, chunk_bytes) != RT_EOK)
        {
            rt_kprintf("[audio_playback] tone write failed at %lu\n", (unsigned long)sent);
            return;
        }
        sent += chunk_bytes;
    }

    (void)audio_playback_flush();
    rt_kprintf("[audio_playback] tone done\n");
}
MSH_CMD_EXPORT(audio_playback_tone_cmd, Play a local speaker QA tone);

static void audio_playback_voice_cmd(int argc, char **argv)
{
    static const audio_voice_segment_t segments[] =
    {
        { 520, 125, 150, 0 },
        { 180, 150, 135, 2 },
        { 520, 135, 165, 1 },
        { 160, 165, 145, 2 },
        { 620, 145, 120, 0 },
    };
    int16_t frame[240];
    uint32_t phase = 0U;
    uint32_t total_bytes = 0U;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (audio_playback_init() != RT_EOK)
    {
        rt_kprintf("[audio_playback] voice init failed\n");
        return;
    }
    (void)audio_playback_start();

    rt_kprintf("[audio_playback] voice sample start sr=%d ch=%d bits=%d\n",
               AUDIO_SAMPLE_RATE,
               AUDIO_CHANNELS,
               AUDIO_BITS_PER_SAMPLE);

    for (uint32_t seg = 0; seg < sizeof(segments) / sizeof(segments[0]); seg++)
    {
        uint32_t samples = ((uint32_t)segments[seg].duration_ms * AUDIO_SAMPLE_RATE) / 1000U;
        uint32_t sent = 0U;

        while (sent < samples)
        {
            uint32_t chunk_samples = samples - sent;
            if (chunk_samples > (sizeof(frame) / sizeof(frame[0])))
            {
                chunk_samples = sizeof(frame) / sizeof(frame[0]);
            }

            for (uint32_t i = 0; i < chunk_samples; i++)
            {
                uint32_t pos = sent + i;
                uint32_t f0_hz = segments[seg].f0_start_hz +
                    (((uint32_t)segments[seg].f0_end_hz - segments[seg].f0_start_hz) * pos) / samples;
                uint32_t env_q15 = 32767U;
                uint32_t attack = AUDIO_SAMPLE_RATE / 25U;
                uint32_t release = AUDIO_SAMPLE_RATE / 18U;

                if (pos < attack)
                {
                    env_q15 = (32767U * pos) / attack;
                }
                else if ((samples - pos) < release)
                {
                    env_q15 = (32767U * (samples - pos)) / release;
                }

                phase += (f0_hz * 65536U) / AUDIO_SAMPLE_RATE;
                frame[i] = audio_voice_sample(phase, segments[seg].vowel, env_q15);
            }

            if (audio_playback_write((const uint8_t *)frame, chunk_samples * sizeof(frame[0])) != RT_EOK)
            {
                rt_kprintf("[audio_playback] voice write failed seg=%lu offset=%lu\n",
                           (unsigned long)seg,
                           (unsigned long)sent);
                return;
            }
            total_bytes += chunk_samples * sizeof(frame[0]);
            sent += chunk_samples;
        }
    }

    (void)audio_playback_flush();
    rt_kprintf("[audio_playback] voice sample done bytes=%lu\n", (unsigned long)total_bytes);
}
MSH_CMD_EXPORT(audio_playback_voice_cmd, Play a softer voice-like local QA sample);
