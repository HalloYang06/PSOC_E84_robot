#include "audio_capture.h"
#include <rtdevice.h>
#include <board.h>

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t running;
    audio_capture_callback_t callback;
    rt_device_t mic_dev;
    rt_thread_t thread;
    uint8_t buffer[AUDIO_FRAME_BYTES];
} audio_capture_t;

static audio_capture_t g_capture = {0};

static void audio_capture_thread_entry(void *parameter)
{
    rt_size_t read_len;

    RT_UNUSED(parameter);

    while (g_capture.running)
    {
        read_len = rt_device_read(g_capture.mic_dev, 0, g_capture.buffer, AUDIO_FRAME_BYTES);

        if (read_len > 0)
        {
            if (g_capture.callback)
            {
                g_capture.callback(g_capture.buffer, read_len);
            }
        }
        else
        {
            rt_thread_mdelay(10);
        }
    }
}

rt_err_t audio_capture_init(void)
{
    struct rt_audio_caps caps;

    if (g_capture.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_capture, 0, sizeof(g_capture));

    g_capture.mic_dev = rt_device_find("mic0");
    if (g_capture.mic_dev == RT_NULL)
    {
        rt_kprintf("[audio_capture] ERROR: Cannot find mic0 device\n");
        return -RT_ERROR;
    }

    if (rt_device_open(g_capture.mic_dev, RT_DEVICE_OFLAG_RDONLY) != RT_EOK)
    {
        rt_kprintf("[audio_capture] ERROR: Failed to open mic0 device\n");
        return -RT_ERROR;
    }

    rt_memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_INPUT;
    caps.sub_type = AUDIO_DSP_PARAM;
    caps.udata.config.samplerate = AUDIO_SAMPLE_RATE;
    caps.udata.config.channels = AUDIO_CHANNELS;
    caps.udata.config.samplebits = AUDIO_BITS_PER_SAMPLE;
    if (rt_device_control(g_capture.mic_dev, AUDIO_CTL_CONFIGURE, &caps) != RT_EOK)
    {
        rt_kprintf("[audio_capture] WARN: Failed to configure mic0 dsp params\n");
    }
    else
    {
        rt_kprintf("[audio_capture] Configured mic0 sr=%d ch=%d bits=%d\n",
                   AUDIO_SAMPLE_RATE,
                   AUDIO_CHANNELS,
                   AUDIO_BITS_PER_SAMPLE);
    }

    g_capture.initialized = RT_TRUE;
    rt_kprintf("[audio_capture] Initialized (using mic0 device)\n");

    return RT_EOK;
}

rt_err_t audio_capture_start(audio_capture_callback_t callback)
{
    if (!g_capture.initialized)
    {
        rt_kprintf("[audio_capture] ERROR: Not initialized\n");
        return -RT_ERROR;
    }

    if (g_capture.running)
    {
        rt_kprintf("[audio_capture] Already running\n");
        return -RT_EBUSY;
    }

    g_capture.callback = callback;
    g_capture.running = RT_TRUE;

    g_capture.thread = rt_thread_create("audio_cap",
                                        audio_capture_thread_entry,
                                        RT_NULL,
                                        8192,
                                        20,
                                        10);
    if (g_capture.thread)
    {
        rt_thread_startup(g_capture.thread);
        rt_kprintf("[audio_capture] Started\n");
        return RT_EOK;
    }

    g_capture.running = RT_FALSE;
    return -RT_ERROR;
}

rt_err_t audio_capture_stop(void)
{
    if (!g_capture.running)
    {
        return RT_EOK;
    }

    g_capture.running = RT_FALSE;

    if (g_capture.thread)
    {
        rt_thread_mdelay(AUDIO_FRAME_MS + 50);
        g_capture.thread = RT_NULL;
    }

    return RT_EOK;
}

rt_bool_t audio_capture_is_running(void)
{
    return g_capture.running;
}
