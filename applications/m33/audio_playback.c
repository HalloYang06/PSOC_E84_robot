#include "audio_playback.h"
#include <rtdevice.h>
#include <board.h>
#include "../../libraries/Common/board/ports/audio/drv_es8388.h"
#include "../../libraries/HAL_Drivers/drv_i2s.h"

// 声明I2S初始化函数
extern void ifx_i2s_init(void);

#define PLAYBACK_BUFFER_SIZE (AUDIO_FRAME_BYTES * 4)

typedef struct {
    rt_bool_t initialized;
    rt_bool_t playing;
    rt_thread_t thread;
    rt_mutex_t mutex;
    uint8_t buffer[PLAYBACK_BUFFER_SIZE];
    uint32_t write_pos;
    uint32_t read_pos;
    uint32_t data_len;
} audio_playback_t;

static audio_playback_t g_playback = {0};

static void audio_playback_thread_entry(void *parameter)
{
    uint8_t frame[AUDIO_FRAME_BYTES];
    uint32_t to_read;

    RT_UNUSED(parameter);

    while (g_playback.playing)
    {
        rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);

        if (g_playback.data_len >= AUDIO_FRAME_BYTES)
        {
            to_read = AUDIO_FRAME_BYTES;
            for (uint32_t i = 0; i < to_read; i++)
            {
                frame[i] = g_playback.buffer[g_playback.read_pos];
                g_playback.read_pos = (g_playback.read_pos + 1) % PLAYBACK_BUFFER_SIZE;
            }
            g_playback.data_len -= to_read;

            rt_mutex_release(g_playback.mutex);

            // TODO: 实际通过I2S DMA发送音频数据到ES8388 DAC
        }
        else
        {
            rt_mutex_release(g_playback.mutex);
        }

        rt_thread_mdelay(AUDIO_FRAME_MS);
    }
}

rt_err_t audio_playback_init(void)
{
    rt_err_t ret;

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

    // 初始化ES8388为DAC模式
    ret = es8388_init("i2c0", GET_PIN(16, 2));
    if (ret != RT_EOK)
    {
        rt_kprintf("[audio_playback] ES8388 init failed: %d\n", ret);
        return ret;
    }

    // 设置ES8388为DAC模式，I2S格式
    ret = es8388_fmt_set(ES_MODE_DAC, ES_FMT_NORMAL);
    if (ret != RT_EOK)
    {
        rt_kprintf("[audio_playback] ES8388 format set failed: %d\n", ret);
        return ret;
    }

    // 启动ES8388 DAC
    ret = es8388_start(ES_MODE_DAC);
    if (ret != RT_EOK)
    {
        rt_kprintf("[audio_playback] ES8388 start failed: %d\n", ret);
        return ret;
    }

    // 使能扬声器功放
    es8388_pa_power(RT_TRUE);

    // 设置音量
    es8388_volume_set(80);  // 音量0-100

    // 初始化I2S接口
    ifx_i2s_init();

    g_playback.initialized = RT_TRUE;
    rt_kprintf("[audio_playback] Initialized\n");

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

    g_playback.thread = rt_thread_create("audio_pb",
                                         audio_playback_thread_entry,
                                         RT_NULL,
                                         2048,
                                         16,
                                         10);
    if (g_playback.thread)
    {
        rt_thread_startup(g_playback.thread);
        rt_kprintf("[audio_playback] Started\n");
        return RT_EOK;
    }

    g_playback.playing = RT_FALSE;
    return -RT_ERROR;
}

rt_err_t audio_playback_stop(void)
{
    if (!g_playback.playing)
    {
        return RT_EOK;
    }

    g_playback.playing = RT_FALSE;

    if (g_playback.thread)
    {
        rt_thread_mdelay(AUDIO_FRAME_MS + 50);
        g_playback.thread = RT_NULL;
    }

    rt_kprintf("[audio_playback] Stopped\n");
    return RT_EOK;
}

rt_err_t audio_playback_write(const uint8_t *data, uint32_t len)
{
    uint32_t free_space;

    if (!g_playback.initialized || !data || len == 0)
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);

    free_space = PLAYBACK_BUFFER_SIZE - g_playback.data_len;
    if (len > free_space)
    {
        rt_mutex_release(g_playback.mutex);
        return -RT_EFULL;
    }

    for (uint32_t i = 0; i < len; i++)
    {
        g_playback.buffer[g_playback.write_pos] = data[i];
        g_playback.write_pos = (g_playback.write_pos + 1) % PLAYBACK_BUFFER_SIZE;
    }
    g_playback.data_len += len;

    rt_mutex_release(g_playback.mutex);

    return RT_EOK;
}

void audio_playback_clear(void)
{
    rt_mutex_take(g_playback.mutex, RT_WAITING_FOREVER);
    g_playback.write_pos = 0;
    g_playback.read_pos = 0;
    g_playback.data_len = 0;
    rt_mutex_release(g_playback.mutex);
}
