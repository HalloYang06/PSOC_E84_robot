#include "motor7_model_runner.h"

#include "model_deployment.h"
#include "model_manager.h"
#include "model_result_publisher.h"

#define MOTOR7_MODEL_SAMPLE_COUNT 16000U
#define MOTOR7_MODEL_WINDOW_MS    1000U
#define MOTOR7_FLAG_VALID         0x0001U
#define MOTOR7_FLAG_FRESH         0x0002U

static float motor7_absf(float value)
{
    return value >= 0.0f ? value : -value;
}

static float motor7_clampf(float value, float min_value, float max_value)
{
    if (value < min_value)
    {
        return min_value;
    }
    if (value > max_value)
    {
        return max_value;
    }
    return value;
}

static int16_t motor7_clamp_i16(int value)
{
    if (value > 32767)
    {
        return 32767;
    }
    if (value < -32768)
    {
        return -32768;
    }
    return (int16_t)value;
}

static void motor7_fill_pcm_from_snapshot(const sensor_snapshot_msg_t *snapshot, int16_t *samples)
{
    rt_size_t i;
    float pos = motor7_clampf(snapshot->emg_ch1, -6.28f, 6.28f);
    float vel = motor7_clampf(snapshot->emg_ch2, -20.0f, 20.0f);
    float torque = motor7_clampf(snapshot->shoulder_angle, -20.0f, 20.0f);
    float temp = motor7_clampf(snapshot->elbow_angle, 0.0f, 120.0f);
    int amplitude = 1200 + (int)(motor7_absf(pos) * 1100.0f) +
                    (int)(motor7_absf(vel) * 260.0f) +
                    (int)(motor7_absf(torque) * 160.0f) +
                    (int)(temp * 18.0f);
    int bias = (int)(pos * 450.0f) + (int)(vel * 80.0f) + (int)(torque * 60.0f);
    rt_uint32_t step = 23U + ((rt_uint32_t)(motor7_absf(vel) * 10.0f) % 37U);
    rt_uint32_t phase = ((rt_uint32_t)(motor7_absf(pos) * 1000.0f) +
                         ((rt_uint32_t)snapshot->motor_id * 97U)) %
                        256U;

    if (amplitude > 14000)
    {
        amplitude = 14000;
    }

    for (i = 0; i < MOTOR7_MODEL_SAMPLE_COUNT; i++)
    {
        int tri;
        int sample;

        phase = (phase + step) & 0xFFU;
        tri = (phase < 128U) ? (int)phase : (255 - (int)phase);
        tri = (tri * 2) - 127;
        sample = bias + ((tri * amplitude) / 127);
        samples[i] = motor7_clamp_i16(sample);
    }
}

rt_err_t motor7_model_runner_run_snapshot(const sensor_snapshot_msg_t *snapshot)
{
    int16_t *samples;
    float score = 0.0f;
    int detected = 0;
    rt_uint16_t confidence_permille;
    rt_bool_t fresh;
    rt_err_t ret;

    if (snapshot == RT_NULL)
    {
        return -RT_EINVAL;
    }

    ret = model_deployment_load_wake_word(0U, 0U);
    if (ret != RT_EOK)
    {
        rt_kprintf("[motor7_model] load tflm ret=%d\n", ret);
        return ret;
    }

    samples = (int16_t *)rt_malloc_align(sizeof(int16_t) * MOTOR7_MODEL_SAMPLE_COUNT, 16);
    if (samples == RT_NULL)
    {
        rt_kprintf("[motor7_model] alloc pcm failed\n");
        return -RT_ENOMEM;
    }

    motor7_fill_pcm_from_snapshot(snapshot, samples);
    ret = model_manager_run_pcm16(MODEL_SLOT_WAKE_WORD,
                                  samples,
                                  MOTOR7_MODEL_SAMPLE_COUNT,
                                  &score,
                                  &detected);
    rt_free_align(samples);
    if (ret != RT_EOK)
    {
        rt_kprintf("[motor7_model] inference ret=%d\n", ret);
        return ret;
    }

    score = motor7_clampf(score, 0.0f, 1.0f);
    confidence_permille = (rt_uint16_t)((score * 1000.0f) + 0.5f);
    fresh = ((snapshot->flags & MOTOR7_FLAG_VALID) != 0U) &&
            ((snapshot->flags & MOTOR7_FLAG_FRESH) != 0U) ? RT_TRUE : RT_FALSE;

    rt_kprintf("[motor7_model] motor=%u flags=0x%04x pos=%d vel=%d temp=%d score=%u detected=%d fresh=%d\n",
               snapshot->motor_id,
               snapshot->flags,
               (int)(snapshot->emg_ch1 * 1000.0f),
               (int)(snapshot->emg_ch2 * 1000.0f),
               (int)(snapshot->elbow_angle * 10.0f),
               confidence_permille,
               detected,
               fresh ? 1 : 0);

    ret = model_result_publish_wake_word(confidence_permille,
                                         detected ? RT_TRUE : RT_FALSE,
                                         fresh,
                                         MOTOR7_MODEL_WINDOW_MS);
    rt_kprintf("[motor7_model] publish ret=%d\n", ret);
    return ret;
}
