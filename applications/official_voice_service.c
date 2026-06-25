#include "official_voice_service.h"

#include <finsh.h>
#include <rtdevice.h>
#include <stdlib.h>

#include "drv_pdm.h"
#include "model_result_publisher.h"
#include "official_voice_result_adapter.h"

#define OFFICIAL_VOICE_SAMPLE_RATE_HZ       16000U
#define OFFICIAL_VOICE_CHANNELS             1U
#define OFFICIAL_VOICE_BITS_PER_SAMPLE      16U
#define OFFICIAL_VOICE_FRAME_SAMPLES        160U
#define OFFICIAL_VOICE_DEFAULT_TEST_MS      3000U
#define OFFICIAL_VOICE_DEFAULT_PEAK         1200U
#define OFFICIAL_VOICE_DEFAULT_AVG_ABS      70U
#define OFFICIAL_VOICE_DEFAULT_STREAK       3U
#define OFFICIAL_VOICE_BEEP_MS              180U
#define OFFICIAL_VOICE_DEFAULT_GAIN         0
#define OFFICIAL_VOICE_MAX_GAIN             75
#define OFFICIAL_VOICE_MIN_GAIN             (-207)

typedef struct
{
    rt_uint32_t frames;
    rt_uint32_t active_frames;
    rt_uint32_t detections;
    rt_uint32_t last_peak;
    rt_uint32_t last_avg_abs;
    rt_err_t last_publish_ret;
    rt_err_t last_speaker_ret;
    rt_bool_t mic_ok;
    rt_bool_t speaker_ok;
} official_voice_status_t;

typedef struct
{
    rt_uint32_t peak_threshold;
    rt_uint32_t avg_abs_threshold;
    rt_uint32_t streak_threshold;
    rt_int16_t pdm_gain;
} official_voice_config_t;

static official_voice_status_t g_official_voice_status;
static rt_mutex_t g_official_voice_speaker_lock = RT_NULL;
static official_voice_config_t g_official_voice_config =
{
    OFFICIAL_VOICE_DEFAULT_PEAK,
    OFFICIAL_VOICE_DEFAULT_AVG_ABS,
    OFFICIAL_VOICE_DEFAULT_STREAK,
    OFFICIAL_VOICE_DEFAULT_GAIN,
};

static rt_uint32_t abs_i16(rt_int16_t value)
{
    if (value < 0)
    {
        return (rt_uint32_t)(-value);
    }
    return (rt_uint32_t)value;
}

static void configure_audio_input(rt_device_t mic)
{
    struct rt_audio_caps caps;

    rt_memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_INPUT;
    caps.sub_type = AUDIO_DSP_PARAM;
    caps.udata.config.samplerate = OFFICIAL_VOICE_SAMPLE_RATE_HZ;
    caps.udata.config.channels = OFFICIAL_VOICE_CHANNELS;
    caps.udata.config.samplebits = OFFICIAL_VOICE_BITS_PER_SAMPLE;
    (void)rt_device_control(mic, AUDIO_CTL_CONFIGURE, &caps);
    (void)set_pdm_pcm_gain(g_official_voice_config.pdm_gain);
}

static void configure_audio_output(rt_device_t speaker)
{
    struct rt_audio_caps caps;

    rt_memset(&caps, 0, sizeof(caps));
    caps.main_type = AUDIO_TYPE_OUTPUT;
    caps.sub_type = AUDIO_DSP_PARAM;
    caps.udata.config.samplerate = OFFICIAL_VOICE_SAMPLE_RATE_HZ;
    caps.udata.config.channels = OFFICIAL_VOICE_CHANNELS;
    caps.udata.config.samplebits = OFFICIAL_VOICE_BITS_PER_SAMPLE;
    (void)rt_device_control(speaker, AUDIO_CTL_CONFIGURE, &caps);
}

rt_err_t official_voice_speaker_take(rt_int32_t timeout)
{
    if (g_official_voice_speaker_lock == RT_NULL)
    {
        g_official_voice_speaker_lock = rt_mutex_create("ov_spk", RT_IPC_FLAG_PRIO);
        if (g_official_voice_speaker_lock == RT_NULL)
        {
            return -RT_ENOMEM;
        }
    }

    return rt_mutex_take(g_official_voice_speaker_lock, timeout);
}

void official_voice_speaker_release(void)
{
    if (g_official_voice_speaker_lock != RT_NULL)
    {
        rt_mutex_release(g_official_voice_speaker_lock);
    }
}

static rt_uint16_t confidence_from_activity(rt_uint32_t peak, rt_uint32_t avg_abs)
{
    rt_uint32_t peak_score = (peak >= 6000U) ? 600U : ((peak * 600U) / 6000U);
    rt_uint32_t avg_score = (avg_abs >= 1000U) ? 400U : ((avg_abs * 400U) / 1000U);
    rt_uint32_t score = peak_score + avg_score;

    if (score > 1000U)
    {
        score = 1000U;
    }
    return (rt_uint16_t)score;
}

rt_err_t official_voice_speaker_beep(rt_uint32_t duration_ms)
{
    rt_device_t speaker;
    rt_int16_t frame[OFFICIAL_VOICE_FRAME_SAMPLES];
    rt_uint32_t frame_count;
    rt_uint32_t frame_index;
    rt_uint32_t i;
    rt_err_t ret;

    if (duration_ms == 0U)
    {
        duration_ms = OFFICIAL_VOICE_BEEP_MS;
    }

    speaker = rt_device_find("sound0");
    if (speaker == RT_NULL)
    {
        rt_kprintf("[official_voice] sound0 not found\n");
        g_official_voice_status.speaker_ok = RT_FALSE;
        g_official_voice_status.last_speaker_ret = -RT_ERROR;
        return -RT_ERROR;
    }

    ret = rt_device_open(speaker, RT_DEVICE_OFLAG_WRONLY);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[official_voice] open sound0 failed ret=%d\n", ret);
        g_official_voice_status.speaker_ok = RT_FALSE;
        g_official_voice_status.last_speaker_ret = ret;
        return ret;
    }

    configure_audio_output(speaker);

    frame_count = duration_ms / 10U;
    if (frame_count == 0U)
    {
        frame_count = 1U;
    }

    for (frame_index = 0; frame_index < frame_count; frame_index++)
    {
        for (i = 0; i < OFFICIAL_VOICE_FRAME_SAMPLES; i++)
        {
            rt_uint32_t phase = ((frame_index * OFFICIAL_VOICE_FRAME_SAMPLES) + i) % 32U;
            frame[i] = (phase < 16U) ? 3000 : -3000;
        }
        (void)rt_device_write(speaker, 0, frame, sizeof(frame));
        rt_thread_mdelay(10);
    }

    g_official_voice_status.speaker_ok = RT_TRUE;
    g_official_voice_status.last_speaker_ret = RT_EOK;
    rt_kprintf("[official_voice] speaker beep ok duration_ms=%lu\n", (unsigned long)duration_ms);
    return RT_EOK;
}

rt_err_t official_voice_speaker_play_pcm(const rt_int16_t *pcm, rt_uint32_t sample_count)
{
    rt_device_t speaker;
    rt_uint32_t offset = 0U;
    rt_err_t ret;
    rt_err_t final_ret = RT_EOK;

    if ((pcm == RT_NULL) || (sample_count == 0U))
    {
        return -RT_EINVAL;
    }

    ret = official_voice_speaker_take(0);
    if (ret != RT_EOK)
    {
        rt_kprintf("[official_voice] pcm feedback skipped speaker busy ret=%d\n", ret);
        return ret;
    }

    speaker = rt_device_find("sound0");
    if (speaker == RT_NULL)
    {
        rt_kprintf("[official_voice] sound0 not found for pcm feedback\n");
        final_ret = -RT_ERROR;
        goto out;
    }

    ret = rt_device_open(speaker, RT_DEVICE_OFLAG_WRONLY);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[official_voice] open sound0 failed for pcm feedback ret=%d\n", ret);
        final_ret = ret;
        goto out;
    }

    configure_audio_output(speaker);
    while (offset < sample_count)
    {
        rt_uint32_t samples = sample_count - offset;
        rt_size_t written;

        if (samples > OFFICIAL_VOICE_FRAME_SAMPLES)
        {
            samples = OFFICIAL_VOICE_FRAME_SAMPLES;
        }
        written = rt_device_write(speaker, 0, pcm + offset, samples * sizeof(pcm[0]));
        if (written == 0U)
        {
            rt_kprintf("[official_voice] pcm feedback write failed offset=%lu\n",
                       (unsigned long)offset);
            final_ret = -RT_ERROR;
            goto out;
        }
        offset += samples;
        rt_thread_mdelay(10);
    }

    rt_kprintf("[official_voice] pcm feedback ok samples=%lu\n", (unsigned long)sample_count);
out:
    official_voice_speaker_release();
    return final_ret;
}

rt_err_t official_voice_pdm_self_test(rt_uint32_t duration_ms, rt_bool_t publish_on_activity)
{
    rt_device_t mic;
    rt_int16_t frame[OFFICIAL_VOICE_FRAME_SAMPLES];
    rt_uint32_t deadline;
    rt_uint32_t active_streak = 0;
    rt_uint32_t local_frames = 0;
    rt_uint32_t local_active = 0;
    rt_uint32_t local_peak_max = 0;
    rt_uint32_t local_avg_max = 0;
    rt_bool_t published = RT_FALSE;
    rt_err_t ret;

    if (duration_ms == 0U)
    {
        duration_ms = OFFICIAL_VOICE_DEFAULT_TEST_MS;
    }

    mic = rt_device_find("mic0");
    if (mic == RT_NULL)
    {
        rt_kprintf("[official_voice] mic0 not found\n");
        g_official_voice_status.mic_ok = RT_FALSE;
        return -RT_ERROR;
    }

    ret = rt_device_open(mic, RT_DEVICE_OFLAG_RDONLY);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        rt_kprintf("[official_voice] open mic0 failed ret=%d\n", ret);
        g_official_voice_status.mic_ok = RT_FALSE;
        return ret;
    }

    configure_audio_input(mic);
    deadline = rt_tick_get() + rt_tick_from_millisecond(duration_ms);
    rt_kprintf("[official_voice] PDM test start duration_ms=%lu publish=%d\n",
               (unsigned long)duration_ms,
               publish_on_activity ? 1 : 0);

    while ((rt_int32_t)(rt_tick_get() - deadline) < 0)
    {
        rt_size_t read_len = rt_device_read(mic, 0, frame, sizeof(frame));
        rt_uint32_t peak = 0;
        rt_uint32_t sum_abs = 0;
        rt_uint32_t avg_abs;
        rt_size_t i;
        rt_size_t sample_count;

        if (read_len == 0U)
        {
            rt_thread_mdelay(5);
            continue;
        }

        sample_count = read_len / sizeof(rt_int16_t);
        if (sample_count == 0U)
        {
            continue;
        }

        for (i = 0; i < sample_count; i++)
        {
            rt_uint32_t mag = abs_i16(frame[i]);
            sum_abs += mag;
            if (mag > peak)
            {
                peak = mag;
            }
        }
        avg_abs = sum_abs / sample_count;

        local_frames++;
        if (peak > local_peak_max)
        {
            local_peak_max = peak;
        }
        if (avg_abs > local_avg_max)
        {
            local_avg_max = avg_abs;
        }

        if ((peak >= g_official_voice_config.peak_threshold) &&
            (avg_abs >= g_official_voice_config.avg_abs_threshold))
        {
            active_streak++;
            local_active++;
        }
        else
        {
            active_streak = 0;
        }

        if ((local_frames % 50U) == 0U)
        {
            rt_kprintf("[official_voice] frames=%lu peak=%lu avg_abs=%lu active=%lu\n",
                       (unsigned long)local_frames,
                       (unsigned long)local_peak_max,
                       (unsigned long)local_avg_max,
                       (unsigned long)local_active);
        }

        if (publish_on_activity && !published &&
            (active_streak >= g_official_voice_config.streak_threshold))
        {
            rt_uint16_t confidence = confidence_from_activity(peak, avg_abs);
            ret = model_result_publish_wake_word(confidence, RT_TRUE, RT_TRUE, 30U);
            g_official_voice_status.last_publish_ret = ret;
            g_official_voice_status.detections++;
            published = RT_TRUE;
            rt_kprintf("[official_voice] local activity detected confidence=%u publish_ret=%d\n",
                       confidence,
                       ret);
            (void)official_voice_speaker_beep(OFFICIAL_VOICE_BEEP_MS);
        }
    }

    g_official_voice_status.frames += local_frames;
    g_official_voice_status.active_frames += local_active;
    g_official_voice_status.last_peak = local_peak_max;
    g_official_voice_status.last_avg_abs = local_avg_max;
    g_official_voice_status.mic_ok = local_frames > 0U ? RT_TRUE : RT_FALSE;

    rt_kprintf("[official_voice] PDM test done frames=%lu active=%lu peak=%lu avg_abs=%lu published=%d\n",
               (unsigned long)local_frames,
               (unsigned long)local_active,
               (unsigned long)local_peak_max,
               (unsigned long)local_avg_max,
               published ? 1 : 0);

    return (local_frames > 0U) ? RT_EOK : -RT_ETIMEOUT;
}

void official_voice_dump_status(void)
{
    rt_kprintf("[official_voice] status mic_ok=%d speaker_ok=%d frames=%lu active=%lu detections=%lu peak=%lu avg_abs=%lu pub_ret=%d spk_ret=%d cfg_peak=%lu cfg_avg=%lu cfg_streak=%lu gain=%d\n",
               g_official_voice_status.mic_ok ? 1 : 0,
               g_official_voice_status.speaker_ok ? 1 : 0,
               (unsigned long)g_official_voice_status.frames,
               (unsigned long)g_official_voice_status.active_frames,
               (unsigned long)g_official_voice_status.detections,
               (unsigned long)g_official_voice_status.last_peak,
               (unsigned long)g_official_voice_status.last_avg_abs,
               g_official_voice_status.last_publish_ret,
               g_official_voice_status.last_speaker_ret,
               (unsigned long)g_official_voice_config.peak_threshold,
               (unsigned long)g_official_voice_config.avg_abs_threshold,
               (unsigned long)g_official_voice_config.streak_threshold,
               g_official_voice_config.pdm_gain);
}

static rt_uint32_t parse_duration_ms(int argc, char **argv, rt_uint32_t default_ms)
{
    if ((argc >= 2) && (argv[1] != RT_NULL))
    {
        long seconds = atol(argv[1]);
        if (seconds > 0)
        {
            return (rt_uint32_t)seconds * 1000U;
        }
    }
    return default_ms;
}

static void pdm_mic_self_test(int argc, char **argv)
{
    rt_uint32_t duration_ms = parse_duration_ms(argc, argv, OFFICIAL_VOICE_DEFAULT_TEST_MS);
    rt_err_t ret = official_voice_pdm_self_test(duration_ms, RT_FALSE);
    rt_kprintf("pdm_mic_self_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(pdm_mic_self_test, Official local voice PDM mic self-test; arg seconds);

static void official_voice_self_test(int argc, char **argv)
{
    rt_uint32_t duration_ms = parse_duration_ms(argc, argv, OFFICIAL_VOICE_DEFAULT_TEST_MS);
    rt_err_t mic_ret = official_voice_pdm_self_test(duration_ms, RT_FALSE);
    rt_err_t speaker_ret = official_voice_speaker_beep(OFFICIAL_VOICE_BEEP_MS);
    rt_kprintf("official_voice_self_test mic_ret=%d speaker_ret=%d\n", mic_ret, speaker_ret);
}
MSH_CMD_EXPORT(official_voice_self_test, Official local voice mic plus speaker self-test; arg seconds);

static void local_voice_listen(int argc, char **argv)
{
    rt_uint32_t duration_ms = parse_duration_ms(argc, argv, OFFICIAL_VOICE_DEFAULT_TEST_MS);
    rt_err_t ret = official_voice_pdm_self_test(duration_ms, RT_TRUE);
    rt_kprintf("local_voice_listen ret=%d\n", ret);
}
MSH_CMD_EXPORT(local_voice_listen, Listen for local voice activity and publish suggestion);

static void official_voice_speaker_test(int argc, char **argv)
{
    rt_uint32_t duration_ms = parse_duration_ms(argc, argv, OFFICIAL_VOICE_BEEP_MS);
    rt_err_t ret = official_voice_speaker_beep(duration_ms);
    rt_kprintf("official_voice_speaker_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(official_voice_speaker_test, Play a local voice feedback beep; arg seconds);

static void voice_pipeline_status(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    official_voice_dump_status();
}
MSH_CMD_EXPORT(voice_pipeline_status, Dump official local voice bridge status);

static void voice_thresholds(int argc, char **argv)
{
    if (argc >= 4)
    {
        long peak = atol(argv[1]);
        long avg_abs = atol(argv[2]);
        long streak = atol(argv[3]);

        if ((peak > 0) && (avg_abs > 0) && (streak > 0))
        {
            g_official_voice_config.peak_threshold = (rt_uint32_t)peak;
            g_official_voice_config.avg_abs_threshold = (rt_uint32_t)avg_abs;
            g_official_voice_config.streak_threshold = (rt_uint32_t)streak;
        }
        else
        {
            rt_kprintf("usage: voice_thresholds <peak> <avg_abs> <streak>\n");
        }
    }

    rt_kprintf("[official_voice] thresholds peak=%lu avg_abs=%lu streak=%lu\n",
               (unsigned long)g_official_voice_config.peak_threshold,
               (unsigned long)g_official_voice_config.avg_abs_threshold,
               (unsigned long)g_official_voice_config.streak_threshold);
}
MSH_CMD_EXPORT(voice_thresholds, Get or set local voice thresholds);

static void voice_pdm_gain(int argc, char **argv)
{
    if (argc >= 2)
    {
        long gain = atol(argv[1]);

        if ((gain < OFFICIAL_VOICE_MIN_GAIN) || (gain > OFFICIAL_VOICE_MAX_GAIN))
        {
            rt_kprintf("usage: voice_pdm_gain <%d..%d>\n",
                       OFFICIAL_VOICE_MIN_GAIN,
                       OFFICIAL_VOICE_MAX_GAIN);
        }
        else
        {
            rt_err_t ret = (rt_err_t)set_pdm_pcm_gain((rt_int16_t)gain);
            if (ret == RT_EOK)
            {
                g_official_voice_config.pdm_gain = (rt_int16_t)gain;
            }
            rt_kprintf("[official_voice] set gain=%ld ret=%d\n", gain, ret);
        }
    }

    rt_kprintf("[official_voice] pdm_gain=%d\n", g_official_voice_config.pdm_gain);
}
MSH_CMD_EXPORT(voice_pdm_gain, Get or set PDM gain in 0.5 dB steps);

static void voice_calibrate(int argc, char **argv)
{
    rt_uint32_t duration_ms = parse_duration_ms(argc, argv, OFFICIAL_VOICE_DEFAULT_TEST_MS);
    rt_uint32_t old_peak = g_official_voice_config.peak_threshold;
    rt_uint32_t old_avg = g_official_voice_config.avg_abs_threshold;
    rt_err_t ret;

    g_official_voice_config.peak_threshold = 0xFFFFFFFFU;
    g_official_voice_config.avg_abs_threshold = 0xFFFFFFFFU;
    ret = official_voice_pdm_self_test(duration_ms, RT_FALSE);
    g_official_voice_config.peak_threshold = old_peak;
    g_official_voice_config.avg_abs_threshold = old_avg;

    if (ret == RT_EOK)
    {
        rt_uint32_t suggested_peak = g_official_voice_status.last_peak + (g_official_voice_status.last_peak / 2U) + 200U;
        rt_uint32_t suggested_avg = g_official_voice_status.last_avg_abs + (g_official_voice_status.last_avg_abs / 2U) + 20U;

        rt_kprintf("[official_voice] calibration ret=%d observed_peak=%lu observed_avg=%lu suggested: voice_thresholds %lu %lu %lu\n",
                   ret,
                   (unsigned long)g_official_voice_status.last_peak,
                   (unsigned long)g_official_voice_status.last_avg_abs,
                   (unsigned long)suggested_peak,
                   (unsigned long)suggested_avg,
                   (unsigned long)g_official_voice_config.streak_threshold);
    }
    else
    {
        rt_kprintf("[official_voice] calibration failed ret=%d\n", ret);
    }
}
MSH_CMD_EXPORT(voice_calibrate, Capture ambient audio and suggest thresholds);

static void publish_official_voice_map_id_from_args(int argc, char **argv, const char *command_name)
{
    rt_int32_t map_id = OFFICIAL_VOICE_MAP_OK_INFINEON;
    rt_uint16_t confidence = 900U;
    rt_err_t ret;

    if (argc >= 2)
    {
        map_id = (rt_int32_t)atol(argv[1]);
    }
    if (argc >= 3)
    {
        long parsed_confidence = atol(argv[2]);
        if (parsed_confidence >= 0)
        {
            confidence = parsed_confidence > 1000 ? 1000U : (rt_uint16_t)parsed_confidence;
        }
    }

    ret = official_voice_publish_map_id(map_id, confidence, 30U);
    rt_kprintf("%s id=%ld label=%s ret=%d\n",
               command_name,
               (long)map_id,
               official_voice_map_id_label(map_id),
               ret);
}

static void official_voice_map_id(int argc, char **argv)
{
    publish_official_voice_map_id_from_args(argc, argv, "official_voice_map_id");
}
MSH_CMD_EXPORT(official_voice_map_id, Publish official local voice map_id);

static void ov_map(int argc, char **argv)
{
    publish_official_voice_map_id_from_args(argc, argv, "ov_map");
}
MSH_CMD_EXPORT(ov_map, Short alias: publish official local voice map_id);
