#include "voice_manager.h"

#include <rtdevice.h>

#include "../common/m33_m55_comm.h"
#include "audio_playback.h"
#include "voice_trigger.h"

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t running;
    rt_bool_t trigger_ready;
    rt_bool_t manual_recording;
    rt_thread_t thread;
    rt_thread_t bootstrap_thread;
    rt_thread_t wake_thread;
    uint8_t *manual_buffer;
    uint32_t manual_len;
} voice_manager_t;

static voice_manager_t g_manager = {0};

#define MANUAL_RECORD_LIMIT_BYTES (AUDIO_SAMPLE_RATE * 2 * 5)

static void on_voice_recorded(const uint8_t *audio_data, uint32_t len);

static void voice_manager_wake_init_entry(void *parameter)
{
    RT_UNUSED(parameter);

    rt_kprintf("[voice_manager] wake init enter tick=%u\n", (unsigned)rt_tick_get());

    if (voice_trigger_init() == RT_EOK)
    {
        g_manager.trigger_ready = RT_TRUE;
        rt_kprintf("[voice_manager] wake word ready\n");

        if (g_manager.running)
        {
            if (voice_trigger_start(on_voice_recorded) == RT_EOK)
            {
                rt_kprintf("[voice_manager] wake trigger started\n");
            }
            else
            {
                rt_kprintf("[voice_manager] wake trigger start failed, manual mode only\n");
                g_manager.trigger_ready = RT_FALSE;
            }
        }
    }
    else
    {
        rt_kprintf("[voice_manager] wake word init deferred/failed, manual mode only\n");
    }

    g_manager.wake_thread = RT_NULL;
}

static void on_voice_recorded(const uint8_t *audio_data, uint32_t len)
{
    m33_m55_message_t msg;
    uint32_t sent = 0;
    uint32_t chunk_index = 0;

    rt_kprintf("[voice_manager] Voice recorded: %u bytes, sending to M55...\n", len);
    rt_kprintf("[voice_manager] pcm begin len=%u\n", len);

    while (sent < len)
    {
        uint32_t chunk_len = (len - sent) > AUDIO_CHUNK_SIZE ? AUDIO_CHUNK_SIZE : (len - sent);

        rt_memset(&msg, 0, sizeof(msg));
        msg.type = MSG_TYPE_AUDIO_DATA;
        msg.payload.audio_data.total_len = len;
        msg.payload.audio_data.chunk_index = chunk_index;
        msg.payload.audio_data.chunk_len = chunk_len;
        rt_memcpy(msg.payload.audio_data.data, audio_data + sent, chunk_len);

        (void)m33_m55_comm_publish(&msg);
        rt_kprintf("[voice_manager] pcm chunk=%u idx=%u\n", chunk_len, chunk_index);

        sent += chunk_len;
        chunk_index++;
        rt_thread_mdelay(10);
    }

    rt_kprintf("[voice_manager] pcm end chunks=%u\n", chunk_index);
}

static void manual_capture_callback(const uint8_t *data, uint32_t len)
{
    if (!g_manager.manual_recording || (g_manager.manual_buffer == RT_NULL))
    {
        return;
    }

    if ((g_manager.manual_len + len) > MANUAL_RECORD_LIMIT_BYTES)
    {
        len = MANUAL_RECORD_LIMIT_BYTES - g_manager.manual_len;
    }

    if (len > 0)
    {
        rt_memcpy(g_manager.manual_buffer + g_manager.manual_len, data, len);
        g_manager.manual_len += len;
    }

    if (g_manager.manual_len >= MANUAL_RECORD_LIMIT_BYTES)
    {
        rt_kprintf("[voice_manager] manual capture reached limit\n");
        (void)audio_capture_stop();
        g_manager.manual_recording = RT_FALSE;
        on_voice_recorded(g_manager.manual_buffer, g_manager.manual_len);
        g_manager.manual_len = 0;
    }
}

static rt_err_t voice_manager_manual_start(void)
{
    if (g_manager.manual_recording)
    {
        return RT_EOK;
    }

    if (g_manager.manual_buffer == RT_NULL)
    {
        g_manager.manual_buffer = (uint8_t *)rt_malloc(MANUAL_RECORD_LIMIT_BYTES);
        if (g_manager.manual_buffer == RT_NULL)
        {
            rt_kprintf("[voice_manager] manual buffer alloc failed\n");
            return -RT_ENOMEM;
        }
    }

    g_manager.manual_len = 0;
    g_manager.manual_recording = RT_TRUE;
    rt_kprintf("[voice_manager] manual capture start\n");
    return audio_capture_start(manual_capture_callback);
}

static rt_err_t voice_manager_manual_stop(void)
{
    if (!g_manager.manual_recording)
    {
        return RT_EOK;
    }

    (void)audio_capture_stop();
    g_manager.manual_recording = RT_FALSE;
    rt_kprintf("[voice_manager] manual capture stop len=%u\n", g_manager.manual_len);

    if (g_manager.manual_len > 0)
    {
        on_voice_recorded(g_manager.manual_buffer, g_manager.manual_len);
        g_manager.manual_len = 0;
    }

    return RT_EOK;
}

static void voice_manager_thread_entry(void *parameter)
{
    m33_m55_message_t msg;

    RT_UNUSED(parameter);

    while (g_manager.running)
    {
        if (m33_m55_comm_consume(&msg) == RT_EOK)
        {
            if (msg.type == MSG_TYPE_TTS_AUDIO)
            {
                rt_kprintf("[voice_manager] Received TTS audio chunk from M55\n");
                if (msg.payload.audio_data.chunk_len == 0U)
                {
                    (void)audio_playback_flush();
                }
                else
                {
                    audio_playback_write(msg.payload.audio_data.data,
                                         msg.payload.audio_data.chunk_len);
                }
            }
            else if (msg.type == MSG_TYPE_VOICE_CONTROL)
            {
                switch ((voice_control_cmd_t)msg.payload.voice_control.cmd)
                {
                case VOICE_CTRL_START_CAPTURE:
                    rt_kprintf("[voice_manager] pcm begin (manual trigger)\n");
                    if (g_manager.trigger_ready)
                    {
                        (void)voice_trigger_force_record();
                    }
                    else
                    {
                        (void)voice_manager_manual_start();
                    }
                    break;
                case VOICE_CTRL_STOP_CAPTURE:
                    rt_kprintf("[voice_manager] pcm end (manual trigger)\n");
                    if (g_manager.trigger_ready)
                    {
                        (void)voice_trigger_force_finish();
                    }
                    else
                    {
                        (void)voice_manager_manual_stop();
                    }
                    break;
                default:
                    break;
                }
            }
        }

        rt_thread_mdelay(50);
    }
}

static void voice_manager_bootstrap_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (!g_manager.running)
    {
        rt_err_t ret = voice_manager_init();
        if (ret == RT_EOK)
        {
            ret = voice_manager_start();
        }

        if (ret == RT_EOK)
        {
            rt_kprintf("[voice_manager] bootstrap ok\n");
            g_manager.bootstrap_thread = RT_NULL;
            return;
        }

        rt_kprintf("[voice_manager] bootstrap retry ret=%d\n", ret);
        rt_thread_mdelay(1000);
    }

    g_manager.bootstrap_thread = RT_NULL;
}

rt_err_t voice_manager_init(void)
{
    if (g_manager.initialized)
    {
        rt_kprintf("[voice_manager] init already done\n");
        return RT_EOK;
    }

    rt_memset(&g_manager, 0, sizeof(g_manager));
    rt_kprintf("[voice_manager] init stage=reset\n");

    rt_kprintf("[voice_manager] init stage=audio_capture_init\n");
    if (audio_capture_init() != RT_EOK)
    {
        rt_kprintf("[voice_manager] Failed to init audio capture\n");
        return -RT_ERROR;
    }

    rt_kprintf("[voice_manager] init stage=audio_playback_init\n");
    if (audio_playback_init() != RT_EOK)
    {
        rt_kprintf("[voice_manager] Failed to init audio playback\n");
        return -RT_ERROR;
    }

    g_manager.initialized = RT_TRUE;
    rt_kprintf("[voice_manager] Initialized\n");
    return RT_EOK;
}

rt_err_t voice_manager_start(void)
{
    if (!g_manager.initialized)
    {
        rt_kprintf("[voice_manager] start rejected: not initialized\n");
        return -RT_ERROR;
    }

    if (g_manager.running)
    {
        rt_kprintf("[voice_manager] start already running\n");
        return RT_EOK;
    }

    rt_kprintf("[voice_manager] start stage=audio_playback_start\n");
    if (audio_playback_start() != RT_EOK)
    {
        rt_kprintf("[voice_manager] Failed to start audio playback\n");
        return -RT_ERROR;
    }

    g_manager.running = RT_TRUE;
    rt_kprintf("[voice_manager] start stage=create voice_mgr\n");
    g_manager.thread = rt_thread_create("voice_mgr",
                                        voice_manager_thread_entry,
                                        RT_NULL,
                                        8192,
                                        14,
                                        10);
    if (!g_manager.thread)
    {
        g_manager.running = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_manager.thread);

    if (g_manager.wake_thread == RT_NULL)
    {
        rt_kprintf("[voice_manager] start stage=create wake_init\n");
        g_manager.wake_thread = rt_thread_create("wake_init",
                                                 voice_manager_wake_init_entry,
                                                 RT_NULL,
                                                 8192,
                                                 24,
                                                 10);
        if (g_manager.wake_thread)
        {
            rt_thread_startup(g_manager.wake_thread);
            rt_kprintf("[voice_manager] wake init scheduled\n");
        }
        else
        {
            rt_kprintf("[voice_manager] wake init thread create failed, manual mode only\n");
        }
    }

    rt_kprintf("[voice_manager] Started\n");
    return RT_EOK;
}

rt_err_t voice_manager_start_async(void)
{
    if (g_manager.running)
    {
        rt_kprintf("[voice_manager] async start ignored: already running\n");
        return RT_EOK;
    }

    if (g_manager.bootstrap_thread != RT_NULL)
    {
        rt_kprintf("[voice_manager] async start ignored: bootstrap exists\n");
        return RT_EOK;
    }

    rt_kprintf("[voice_manager] async start stage=create bootstrap\n");
    g_manager.bootstrap_thread = rt_thread_create("voice_boot",
                                                  voice_manager_bootstrap_entry,
                                                  RT_NULL,
                                                  4096,
                                                  13,
                                                  10);
    if (!g_manager.bootstrap_thread)
    {
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_manager.bootstrap_thread);
    rt_kprintf("[voice_manager] bootstrap started\n");
    return RT_EOK;
}

rt_err_t voice_manager_stop(void)
{
    if (!g_manager.running)
    {
        return RT_EOK;
    }

    g_manager.running = RT_FALSE;
    if (g_manager.trigger_ready)
    {
        voice_trigger_stop();
    }
    if (g_manager.manual_recording)
    {
        (void)voice_manager_manual_stop();
    }
    audio_playback_stop();

    if (g_manager.thread)
    {
        rt_thread_mdelay(100);
        g_manager.thread = RT_NULL;
    }

    g_manager.bootstrap_thread = RT_NULL;
    rt_kprintf("[voice_manager] Stopped\n");
    return RT_EOK;
}
