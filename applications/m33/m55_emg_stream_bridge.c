#include "m55_emg_stream_bridge.h"

#include "common/m33_m55_comm.h"
#include "control/control_layer.h"

#include <rthw.h>
#include <stdlib.h>
#include <string.h>

#define M55_EMG_PHYSICAL_CHANNELS 4U
#define M55_EMG_MODEL_CHANNELS 3U
#define M55_EMG_WINDOW_SAMPLES 15U
#define M55_EMG_DEFAULT_PERIOD_MS 20U
#define M55_EMG_DEFAULT_STEP_MS 100U
#define M55_EMG_STALE_AFTER_MS 250U
#define M55_EMG_SAMPLE_RATE_HZ 50U
#define M55_EMG_THREAD_STACK_SIZE 3072
#define M55_EMG_THREAD_PRIORITY 16

typedef struct
{
    rt_uint16_t ch[M55_EMG_PHYSICAL_CHANNELS];
    rt_uint8_t stale;
} m55_emg_sample_t;

typedef struct
{
    rt_bool_t running;
    rt_thread_t thread;
    rt_uint16_t sample_period_ms;
    rt_uint32_t step_ms;
    rt_uint32_t sample_count;
    rt_uint32_t write_index;
    rt_uint8_t last_emg_seq;
    rt_bool_t have_last_emg_seq;
    rt_uint32_t published_windows;
    rt_uint32_t publish_errors;
    rt_uint32_t skipped_duplicates;
    m55_emg_sample_t window[M55_EMG_WINDOW_SAMPLES];
} m55_emg_stream_runtime_t;

static m55_emg_stream_runtime_t g_m55_emg_stream;

static rt_uint16_t m55_emg_clamp_period(rt_uint16_t sample_period_ms)
{
    if (sample_period_ms == 0U)
    {
        return M55_EMG_DEFAULT_PERIOD_MS;
    }
    if (sample_period_ms < 10U)
    {
        return 10U;
    }
    if (sample_period_ms > 1000U)
    {
        return 1000U;
    }
    return sample_period_ms;
}

static void m55_emg_u16_to_le(rt_uint16_t value, rt_uint8_t *out)
{
    out[0] = (rt_uint8_t)(value & 0xFFU);
    out[1] = (rt_uint8_t)((value >> 8) & 0xFFU);
}

static void m55_emg_append_sample(const control_sensor_node_sample_t *node, rt_bool_t stale)
{
    m55_emg_sample_t *sample;

    sample = &g_m55_emg_stream.window[g_m55_emg_stream.write_index];
    sample->ch[0] = node->adc_raw[0];
    sample->ch[1] = node->adc_raw[1];
    sample->ch[2] = node->adc_raw[2];
    sample->ch[3] = node->adc_raw[3];
    /* sensor.c keeps node->emg3_raw[0], node->emg3_raw[1], and node->emg3_raw[2] as legacy aliases. */
    sample->stale = stale ? 1U : 0U;

    g_m55_emg_stream.write_index =
        (g_m55_emg_stream.write_index + 1U) % M55_EMG_WINDOW_SAMPLES;
    if (g_m55_emg_stream.sample_count < M55_EMG_WINDOW_SAMPLES)
    {
        g_m55_emg_stream.sample_count++;
    }
}

static rt_uint32_t m55_emg_ordered_index(rt_uint32_t logical_index)
{
    rt_uint32_t start;

    if (g_m55_emg_stream.sample_count < M55_EMG_WINDOW_SAMPLES)
    {
        return logical_index;
    }

    start = g_m55_emg_stream.write_index;
    return (start + logical_index) % M55_EMG_WINDOW_SAMPLES;
}

rt_err_t m55_emg_stream_bridge_publish_once(void)
{
    m33_m55_message_t msg;
    rt_uint8_t *dst;
    rt_uint32_t seq;
    rt_uint32_t len;
    rt_uint32_t stale_count = 0U;
    rt_err_t ret;

    if (g_m55_emg_stream.sample_count == 0U)
    {
        return -RT_EEMPTY;
    }

    len = g_m55_emg_stream.sample_count * M55_EMG_PHYSICAL_CHANNELS * sizeof(rt_uint16_t);
    if (len > M33_M55_PCM_SHARED_CAPACITY)
    {
        return -RT_EINVAL;
    }

    dst = (rt_uint8_t *)(void *)g_m33_m55_pcm_shared.data;
    for (rt_uint32_t i = 0U; i < g_m55_emg_stream.sample_count; i++)
    {
        rt_uint32_t index = m55_emg_ordered_index(i);
        const m55_emg_sample_t *sample = &g_m55_emg_stream.window[index];

        if (sample->stale != 0U)
        {
            stale_count++;
        }
        for (rt_uint32_t ch = 0U; ch < M55_EMG_PHYSICAL_CHANNELS; ch++)
        {
            rt_uint32_t offset = (i * M55_EMG_PHYSICAL_CHANNELS + ch) * sizeof(rt_uint16_t);
            m55_emg_u16_to_le(sample->ch[ch], &dst[offset]);
        }
    }

    seq = g_m33_m55_pcm_shared.seq + 1U;
    g_m33_m55_pcm_shared.seq = seq;
    g_m33_m55_pcm_shared.total_len = len;
    g_m33_m55_pcm_shared.sample_rate = M55_EMG_SAMPLE_RATE_HZ;
    g_m33_m55_pcm_shared.channels = M55_EMG_PHYSICAL_CHANNELS;
    g_m33_m55_pcm_shared.bits_per_sample = 16U;
    g_m33_m55_pcm_shared.timestamp = rt_tick_get_millisecond();
    g_m33_m55_pcm_shared.reserved = stale_count;
    g_m33_m55_pcm_shared.crc32 = 0U;
    rt_hw_cpu_dcache_ops(RT_HW_CACHE_FLUSH, dst, (int)len);

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_SENSOR_STREAM;
    msg.payload.sensor_stream.source = MODEL_INPUT_SRC_EMG;
    msg.payload.sensor_stream.format = MODEL_INPUT_FMT_UINT16;
    msg.payload.sensor_stream.channels = M55_EMG_PHYSICAL_CHANNELS;
    msg.payload.sensor_stream.reserved0 = M55_EMG_MODEL_CHANNELS;
    msg.payload.sensor_stream.sample_rate = M55_EMG_SAMPLE_RATE_HZ;
    msg.payload.sensor_stream.frame_samples = g_m55_emg_stream.sample_count;
    msg.payload.sensor_stream.total_len = len;
    msg.payload.sensor_stream.chunk_index = seq;
    msg.payload.sensor_stream.chunk_len = len;
    msg.payload.sensor_stream.timestamp = g_m33_m55_pcm_shared.timestamp;
    msg.payload.sensor_stream.reserved1 = stale_count;

    ret = m33_m55_comm_publish(&msg);
    if (ret == RT_EOK)
    {
        g_m55_emg_stream.published_windows++;
        rt_kprintf("[m55_emg] publish seq=%lu samples=%lu stale=%lu len=%lu\n",
                   (unsigned long)seq,
                   (unsigned long)g_m55_emg_stream.sample_count,
                   (unsigned long)stale_count,
                   (unsigned long)len);
    }
    else
    {
        g_m55_emg_stream.publish_errors++;
        rt_kprintf("[m55_emg] publish failed ret=%d seq=%lu len=%lu\n",
                   ret,
                   (unsigned long)seq,
                   (unsigned long)len);
    }
    return ret;
}

static void m55_emg_stream_entry(void *parameter)
{
    rt_tick_t next_publish_tick = 0U;
    rt_tick_t step_ticks = rt_tick_from_millisecond((rt_int32_t)M55_EMG_DEFAULT_STEP_MS);
    rt_tick_t stale_ticks = rt_tick_from_millisecond((rt_int32_t)M55_EMG_STALE_AFTER_MS);

    RT_UNUSED(parameter);
    rt_kprintf("[m55_emg] stream thread started period=%ums window=%u samples\n",
               (unsigned)g_m55_emg_stream.sample_period_ms,
               (unsigned)M55_EMG_WINDOW_SAMPLES);

    while (g_m55_emg_stream.running)
    {
        control_sensor_node_sample_t node;
        rt_tick_t now = rt_tick_get();
        rt_err_t ret = control_get_sensor_node_sample(&node);

        if ((ret == RT_EOK) && (node.sensor_timestamp != 0U))
        {
            rt_bool_t stale = ((rt_int32_t)(now - node.sensor_timestamp) >
                               (rt_int32_t)stale_ticks) ? RT_TRUE : RT_FALSE;

            if (!g_m55_emg_stream.have_last_emg_seq ||
                (node.emg3_seq != g_m55_emg_stream.last_emg_seq))
            {
                m55_emg_append_sample(&node, stale);
                g_m55_emg_stream.last_emg_seq = node.emg3_seq;
                g_m55_emg_stream.have_last_emg_seq = RT_TRUE;
            }
            else
            {
                g_m55_emg_stream.skipped_duplicates++;
            }
        }

        if ((g_m55_emg_stream.sample_count >= M55_EMG_WINDOW_SAMPLES) &&
            ((next_publish_tick == 0U) ||
             ((rt_int32_t)(now - next_publish_tick) >= 0)))
        {
            (void)m55_emg_stream_bridge_publish_once();
            next_publish_tick = now + step_ticks;
        }

        rt_thread_mdelay(g_m55_emg_stream.sample_period_ms);
    }

    rt_kprintf("[m55_emg] stream thread stopped windows=%lu errors=%lu\n",
               (unsigned long)g_m55_emg_stream.published_windows,
               (unsigned long)g_m55_emg_stream.publish_errors);
    g_m55_emg_stream.thread = RT_NULL;
}

rt_err_t m55_emg_stream_bridge_start(rt_uint16_t sample_period_ms,
                                     rt_bool_t start_f103_stream)
{
    rt_err_t ret;

    if (g_m55_emg_stream.running)
    {
        return RT_EOK;
    }

    ret = m33_m55_comm_is_ready() ? RT_EOK : m33_m55_comm_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("[m55_emg] m33_m55_comm_init ret=%d\n", ret);
        return ret;
    }

    ret = control_layer_init(RT_NULL);
    if (ret != RT_EOK)
    {
        rt_kprintf("[m55_emg] control_layer_init ret=%d\n", ret);
        return ret;
    }

    sample_period_ms = m55_emg_clamp_period(sample_period_ms);
    if (start_f103_stream)
    {
        ret = control_sensor_report_enable(RT_TRUE, sample_period_ms);
        if (ret != RT_EOK)
        {
            rt_kprintf("[m55_emg] control_sensor_report_enable ret=%d\n", ret);
            return ret;
        }
    }

    rt_memset(&g_m55_emg_stream, 0, sizeof(g_m55_emg_stream));
    g_m55_emg_stream.sample_period_ms = sample_period_ms;
    g_m55_emg_stream.step_ms = M55_EMG_DEFAULT_STEP_MS;
    g_m55_emg_stream.running = RT_TRUE;
    g_m55_emg_stream.thread = rt_thread_create("m55_emg",
                                               m55_emg_stream_entry,
                                               RT_NULL,
                                               M55_EMG_THREAD_STACK_SIZE,
                                               M55_EMG_THREAD_PRIORITY,
                                               10);
    if (g_m55_emg_stream.thread == RT_NULL)
    {
        g_m55_emg_stream.running = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_m55_emg_stream.thread);
    return RT_EOK;
}

rt_err_t m55_emg_stream_bridge_stop(rt_bool_t stop_f103_stream)
{
    rt_err_t ret = RT_EOK;

    if (stop_f103_stream)
    {
        ret = control_sensor_report_enable(RT_FALSE, g_m55_emg_stream.sample_period_ms);
    }
    g_m55_emg_stream.running = RT_FALSE;
    return ret;
}

#ifdef RT_USING_FINSH
#include <finsh.h>

static int cmd_m55_emg_stream(int argc, char **argv)
{
    int enable;
    rt_uint16_t period_ms = M55_EMG_DEFAULT_PERIOD_MS;
    rt_bool_t manage_f103 = RT_TRUE;
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: m55_emg_stream <0|1> [period_ms] [manage_f103 0|1]\n");
        return -1;
    }

    enable = atoi(argv[1]);
    if (argc >= 3)
    {
        period_ms = (rt_uint16_t)atoi(argv[2]);
    }
    if (argc >= 4)
    {
        manage_f103 = (atoi(argv[3]) != 0) ? RT_TRUE : RT_FALSE;
    }

    if (enable)
    {
        ret = m55_emg_stream_bridge_start(period_ms, manage_f103);
    }
    else
    {
        ret = m55_emg_stream_bridge_stop(manage_f103);
    }

    rt_kprintf("m55_emg_stream ret=%d running=%d\n",
               ret,
               g_m55_emg_stream.running ? 1 : 0);
    return ret;
}
MSH_CMD_EXPORT(cmd_m55_emg_stream, stream F103 EMG windows to CM55: m55_emg_stream <0|1> [period_ms]);

static int cmd_m55_emg_once(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_emg_stream_bridge_publish_once();
    rt_kprintf("m55_emg_once ret=%d\n", ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_m55_emg_once, publish current EMG window to CM55 once);

static int cmd_m55_emg_status(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("[m55_emg] running=%d samples=%lu write=%lu last_seq=%u have_seq=%u windows=%lu errors=%lu dup=%lu period=%u step=%lu\n",
               g_m55_emg_stream.running ? 1 : 0,
               (unsigned long)g_m55_emg_stream.sample_count,
               (unsigned long)g_m55_emg_stream.write_index,
               g_m55_emg_stream.last_emg_seq,
               g_m55_emg_stream.have_last_emg_seq ? 1U : 0U,
               (unsigned long)g_m55_emg_stream.published_windows,
               (unsigned long)g_m55_emg_stream.publish_errors,
               (unsigned long)g_m55_emg_stream.skipped_duplicates,
               (unsigned)g_m55_emg_stream.sample_period_ms,
               (unsigned long)g_m55_emg_stream.step_ms);
    return 0;
}
MSH_CMD_EXPORT(cmd_m55_emg_status, show M33 to CM55 EMG stream status);
#endif
