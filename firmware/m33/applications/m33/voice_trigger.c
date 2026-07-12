#include "voice_trigger.h"

#include <rtdevice.h>

#include "audio_capture.h"
#include "wake_word_tflite.h"

#define SILENCE_FRAMES 10
#define SILENCE_ENERGY_THRESHOLD 1500000U

typedef enum
{
    STATE_IDLE,
    STATE_DETECTING,
    STATE_RECORDING
} trigger_state_t;

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t running;
    trigger_state_t state;
    voice_trigger_callback_t callback;
    uint8_t *recording_buffer;
    uint32_t recording_len;
    uint32_t silence_count;
} voice_trigger_t;

static voice_trigger_t g_trigger = {0};

static uint32_t calculate_energy(const int16_t *samples, uint32_t count)
{
    uint64_t sum = 0;

    for (uint32_t i = 0; i < count; i++)
    {
        int32_t val = samples[i];
        sum += (uint64_t)(val * val);
    }

    return (uint32_t)(sum / count);
}

static void audio_frame_callback(const uint8_t *data, uint32_t len)
{
    const int16_t *samples = (const int16_t *)data;
    uint32_t count = len / 2;
    uint32_t energy;
    static uint32_t frame_counter = 0;

    frame_counter++;
    if ((frame_counter % 20U) == 0U)
    {
        energy = calculate_energy(samples, count);
        rt_kprintf("[voice_trigger] frame len=%u samples=%u energy=%u state=%d\n",
                   len,
                   count,
                   energy,
                   (int)g_trigger.state);
    }

    switch (g_trigger.state)
    {
    case STATE_IDLE:
        if (wake_word_tflite_detect(samples, count))
        {
            rt_kprintf("[voice_trigger] *** Hey Jarvis detected! ***\n");
            g_trigger.state = STATE_RECORDING;
            g_trigger.recording_len = 0;
            g_trigger.silence_count = 0;
        }
        break;

    case STATE_RECORDING:
        if (g_trigger.recording_len + len <= MAX_RECORDING_BYTES)
        {
            rt_memcpy(g_trigger.recording_buffer + g_trigger.recording_len, data, len);
            g_trigger.recording_len += len;

            energy = calculate_energy(samples, count);
            if (energy < SILENCE_ENERGY_THRESHOLD)
            {
                g_trigger.silence_count++;
                if (g_trigger.silence_count >= SILENCE_FRAMES)
                {
                    rt_kprintf("[voice_trigger] Recording complete (%u bytes)\n",
                               g_trigger.recording_len);

                    if ((g_trigger.callback != RT_NULL) && (g_trigger.recording_len > 0))
                    {
                        g_trigger.callback(g_trigger.recording_buffer, g_trigger.recording_len);
                    }

                    g_trigger.state = STATE_IDLE;
                    g_trigger.recording_len = 0;
                }
            }
            else
            {
                g_trigger.silence_count = 0;
            }
        }
        else
        {
            rt_kprintf("[voice_trigger] Max recording reached (%u bytes)\n",
                       g_trigger.recording_len);

            if ((g_trigger.callback != RT_NULL) && (g_trigger.recording_len > 0))
            {
                g_trigger.callback(g_trigger.recording_buffer, g_trigger.recording_len);
            }

            g_trigger.state = STATE_IDLE;
            g_trigger.recording_len = 0;
        }
        break;

    default:
        break;
    }
}

rt_err_t voice_trigger_init(void)
{
    rt_size_t total, used, max_used;

    if (g_trigger.initialized)
    {
        rt_kprintf("[voice_trigger] init already done\n");
        return RT_EOK;
    }

    rt_memset(&g_trigger, 0, sizeof(g_trigger));
    rt_kprintf("[voice_trigger] init stage=reset\n");

    rt_kprintf("[voice_trigger] init stage=alloc_record_buf size=%u\n",
               (unsigned)MAX_RECORDING_BYTES);
    g_trigger.recording_buffer = (uint8_t *)rt_malloc(MAX_RECORDING_BYTES);
    if (!g_trigger.recording_buffer)
    {
        rt_memory_info(&total, &used, &max_used);
        rt_kprintf("[voice_trigger] Failed to allocate recording buffer (%d bytes)\n",
                   MAX_RECORDING_BYTES);
        rt_kprintf("[voice_trigger] Heap info - total: %d, used: %d, available: %d\n",
                   total, used, total - used);
        return -RT_ENOMEM;
    }

    g_trigger.state = STATE_IDLE;
    g_trigger.initialized = RT_TRUE;

    rt_kprintf("[voice_trigger] init stage=wake_word_tflite_init\n");
    if (wake_word_tflite_init() != RT_EOK)
    {
        rt_kprintf("[voice_trigger] Failed to init TFLite wake word\n");
        rt_free(g_trigger.recording_buffer);
        g_trigger.recording_buffer = RT_NULL;
        g_trigger.initialized = RT_FALSE;
        return -RT_ERROR;
    }
    rt_kprintf("[voice_trigger] TFLite wake word init ok\n");

    rt_kprintf("[voice_trigger] Initialized (max %d seconds, buffer: %d bytes)\n",
               MAX_RECORDING_DURATION_MS / 1000, MAX_RECORDING_BYTES);
    rt_kprintf("[voice_trigger] Wake word: Hey Jarvis\n");

    return RT_EOK;
}

rt_err_t voice_trigger_start(voice_trigger_callback_t callback)
{
    rt_err_t ret;

    if (!g_trigger.initialized)
    {
        rt_kprintf("[voice_trigger] ERROR: Not initialized\n");
        return -RT_ERROR;
    }

    if (g_trigger.running)
    {
        rt_kprintf("[voice_trigger] Already running\n");
        return -RT_EBUSY;
    }

    g_trigger.callback = callback;
    g_trigger.state = STATE_IDLE;
    g_trigger.recording_len = 0;

    rt_kprintf("[voice_trigger] start stage=audio_capture_start\n");
    ret = audio_capture_start(audio_frame_callback);
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_trigger] audio_capture_start failed ret=%d\n", ret);
        return ret;
    }

    g_trigger.running = RT_TRUE;
    rt_kprintf("[voice_trigger] Started\n");

    return RT_EOK;
}

rt_err_t voice_trigger_stop(void)
{
    if (!g_trigger.running)
    {
        return RT_EOK;
    }

    audio_capture_stop();
    g_trigger.running = RT_FALSE;
    g_trigger.state = STATE_IDLE;

    return RT_EOK;
}

rt_err_t voice_trigger_force_record(void)
{
    if (!g_trigger.initialized || !g_trigger.running)
    {
        return -RT_ERROR;
    }

    g_trigger.state = STATE_RECORDING;
    g_trigger.recording_len = 0;
    g_trigger.silence_count = 0;
    rt_kprintf("[voice_trigger] Forced recording start\n");
    return RT_EOK;
}

rt_err_t voice_trigger_force_finish(void)
{
    if (!g_trigger.initialized || !g_trigger.running)
    {
        return -RT_ERROR;
    }

    if ((g_trigger.callback != RT_NULL) && (g_trigger.recording_len > 0))
    {
        rt_kprintf("[voice_trigger] Forced recording finish (%u bytes)\n", g_trigger.recording_len);
        g_trigger.callback(g_trigger.recording_buffer, g_trigger.recording_len);
    }
    else
    {
        rt_kprintf("[voice_trigger] Forced recording finish with no data\n");
    }

    g_trigger.state = STATE_IDLE;
    g_trigger.recording_len = 0;
    g_trigger.silence_count = 0;
    return RT_EOK;
}
