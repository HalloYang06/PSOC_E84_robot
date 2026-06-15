#include "audio_playback.h"
#include <rtdevice.h>
#include <finsh.h>
#include <stdlib.h>

#define PLAYBACK_BUFFER_SIZE (AUDIO_FRAME_BYTES * 4)

typedef struct {
    rt_bool_t initialized;
    rt_bool_t playing;
    rt_mutex_t mutex;
    rt_device_t speaker;
    char speaker_name[RT_NAME_MAX];
    uint32_t queued_mod;
    uint8_t buffer[PLAYBACK_BUFFER_SIZE];
    uint32_t write_pos;
    uint32_t read_pos;
    uint32_t data_len;
} audio_playback_t;

static audio_playback_t g_playback = {0};

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
    if (!g_playback.initialized || !data || len == 0)
    {
        return -RT_EINVAL;
    }

    if (g_playback.speaker != RT_NULL)
    {
        rt_size_t offset = 0;
        rt_size_t written;

        rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
        while (offset < len)
        {
            rt_size_t chunk = len - offset;
            if (chunk > RT_AUDIO_REPLAY_MP_BLOCK_SIZE)
            {
                chunk = RT_AUDIO_REPLAY_MP_BLOCK_SIZE;
            }
            written = rt_device_write(g_playback.speaker, 0, data + offset, chunk);
            if (written == 0)
            {
                rt_mutex_release(g_playback.mutex);
                rt_kprintf("[audio_playback] %s direct write failed offset=%lu len=%lu\n",
                           g_playback.speaker_name,
                           (unsigned long)offset,
                           (unsigned long)len);
                return -RT_ERROR;
            }
            offset += written;
            g_playback.queued_mod =
                (g_playback.queued_mod + (uint32_t)written) % RT_AUDIO_REPLAY_MP_BLOCK_SIZE;
        }
        rt_mutex_release(g_playback.mutex);
    }

    return RT_EOK;
}

rt_err_t audio_playback_flush(void)
{
    static const uint8_t silence[RT_AUDIO_REPLAY_MP_BLOCK_SIZE] = {0};
    uint32_t pad_len;

    if (!g_playback.initialized || (g_playback.speaker == RT_NULL))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
    pad_len = (g_playback.queued_mod == 0U) ? 0U :
              (RT_AUDIO_REPLAY_MP_BLOCK_SIZE - g_playback.queued_mod);
    rt_mutex_release(g_playback.mutex);

    if (pad_len == 0U)
    {
        return RT_EOK;
    }

    rt_kprintf("[audio_playback] flush tail pad=%lu\n", (unsigned long)pad_len);
    return audio_playback_write(silence, pad_len);
}

void audio_playback_clear(void)
{
    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
    g_playback.write_pos = 0;
    g_playback.read_pos = 0;
    g_playback.data_len = 0;
    g_playback.queued_mod = 0;
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
               (unsigned long)g_playback.data_len);
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
