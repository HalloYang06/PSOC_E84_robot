#include "xiaozhi_wake_engine.h"

#include <string.h>

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
extern int xiaozhi_edge_impulse_wake_init(void);
extern int xiaozhi_edge_impulse_wake_process(const int16_t *pcm,
                                             rt_uint32_t sample_count,
                                             int *detected,
                                             int *confidence_permille);
extern int xiaozhi_edge_impulse_wake_stage(void);
extern int xiaozhi_edge_impulse_wake_last_error(void);
extern int xiaozhi_edge_impulse_wake_last_confidence_permille(void);
extern int xiaozhi_edge_impulse_wake_threshold_permille(void);
extern int xiaozhi_edge_impulse_wake_set_threshold_permille(int threshold_permille);
extern int xiaozhi_edge_impulse_wake_last_noise_permille(void);
extern int xiaozhi_edge_impulse_wake_last_feature_source(void);
extern int xiaozhi_edge_impulse_wake_last_feature_error(void);
extern int xiaozhi_edge_impulse_wake_last_alloc_source(void);
extern int xiaozhi_edge_impulse_wake_last_alloc_size(void);
extern int xiaozhi_edge_impulse_wake_last_alloc_fail_source(void);
extern int xiaozhi_edge_impulse_wake_last_alloc_fail_size(void);
extern int xiaozhi_edge_impulse_wake_alloc_diag(void);
extern int xiaozhi_edge_impulse_cpu_diag_get(xiaozhi_wake_cpu_diag_t *diag);
extern int xiaozhi_edge_impulse_cpu_diag_reset(void);
extern int xiaozhi_edge_impulse_cpu_samples_snapshot(
    xiaozhi_wake_cpu_sample_snapshot_t *snapshot);
extern rt_size_t xiaozhi_edge_impulse_cpu_samples_read(
    const xiaozhi_wake_cpu_sample_snapshot_t *snapshot,
    rt_size_t offset,
    rt_uint32_t *samples,
    rt_size_t capacity);
#endif

#ifdef XIAOZHI_WAKE_USE_IFX_DEEPCRAFT
extern int ifx_deepcraft_wake_init(void);
extern int ifx_deepcraft_wake_process(int16_t *pcm, int *detected);
extern int ifx_deepcraft_wake_stage(void);
extern int ifx_deepcraft_wake_detail(void);
#endif

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t ready;
    rt_bool_t unavailable_logged;
    int last_error;
} xiaozhi_wake_engine_t;

static xiaozhi_wake_engine_t g_wake;

const char *xiaozhi_wake_engine_backend_name(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return "infineon_official_xiaozhi_edge_impulse";
#elif defined(XIAOZHI_WAKE_USE_IFX_DEEPCRAFT)
    return "infineon_deepcraft_voice_assistant";
#else
    return "not_linked";
#endif
}

rt_err_t xiaozhi_wake_engine_init(void)
{
    if (g_wake.initialized)
    {
        return g_wake.ready ? RT_EOK : -RT_ENOSYS;
    }

    rt_memset(&g_wake, 0, sizeof(g_wake));
    g_wake.initialized = RT_TRUE;

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    g_wake.last_error = xiaozhi_edge_impulse_wake_init();
    if (g_wake.last_error == 0)
    {
        g_wake.ready = RT_TRUE;
        rt_kprintf("[xiaozhi_wake] ready backend=%s\n", xiaozhi_wake_engine_backend_name());
        return RT_EOK;
    }

    rt_kprintf("[xiaozhi_wake] Edge Impulse init failed ret=%d\n", g_wake.last_error);
    return -RT_ERROR;
#elif defined(XIAOZHI_WAKE_USE_IFX_DEEPCRAFT)
    g_wake.last_error = ifx_deepcraft_wake_init();
    if (g_wake.last_error == 0)
    {
        g_wake.ready = RT_TRUE;
        rt_kprintf("[xiaozhi_wake] ready backend=%s\n", xiaozhi_wake_engine_backend_name());
        return RT_EOK;
    }

    if (ifx_deepcraft_wake_detail() != 0)
    {
        g_wake.last_error = ifx_deepcraft_wake_detail();
    }
    rt_kprintf("[xiaozhi_wake] Infineon DEEPCRAFT init failed ret=%d\n", g_wake.last_error);
    return -RT_ERROR;
#else
    g_wake.last_error = -RT_ENOSYS;
    rt_kprintf("[xiaozhi_wake] unavailable: Infineon DEEPCRAFT wake engine is not linked\n");
    return -RT_ENOSYS;
#endif
}

rt_bool_t xiaozhi_wake_engine_is_ready(void)
{
    return g_wake.ready;
}

int xiaozhi_wake_engine_last_error(void)
{
    return g_wake.last_error;
}

int xiaozhi_wake_engine_stage(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_stage();
#elif defined(XIAOZHI_WAKE_USE_IFX_DEEPCRAFT)
    return ifx_deepcraft_wake_stage();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_confidence_permille(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_confidence_permille();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_threshold_permille(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_threshold_permille();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_set_threshold_permille(int threshold_permille)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_set_threshold_permille(threshold_permille);
#else
    RT_UNUSED(threshold_permille);
    return -RT_ENOSYS;
#endif
}

int xiaozhi_wake_engine_last_noise_permille(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_noise_permille();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_feature_source(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_feature_source();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_feature_error(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_feature_error();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_alloc_source(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_alloc_source();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_alloc_size(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_alloc_size();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_alloc_diag(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_alloc_diag();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_alloc_fail_source(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_alloc_fail_source();
#else
    return 0;
#endif
}

int xiaozhi_wake_engine_last_alloc_fail_size(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_wake_last_alloc_fail_size();
#else
    return 0;
#endif
}

rt_err_t xiaozhi_wake_engine_cpu_diag_get(xiaozhi_wake_cpu_diag_t *diag)
{
    int ret;

    if (diag == RT_NULL)
    {
        return -RT_EINVAL;
    }

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    ret = xiaozhi_edge_impulse_cpu_diag_get(diag);
    if (ret != RT_EOK)
    {
        return (rt_err_t)ret;
    }
    diag->backend = "cpu_tflm";
    diag->model_id = "official_xiaozhi_ei_int8";
    return RT_EOK;
#else
    rt_memset(diag, 0, sizeof(*diag));
    diag->backend = "unavailable";
    diag->model_id = "not_active";
    diag->timer = "not_active";
    return -RT_ENOSYS;
#endif
}

rt_err_t xiaozhi_wake_engine_cpu_diag_reset(void)
{
#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return (rt_err_t)xiaozhi_edge_impulse_cpu_diag_reset();
#else
    return -RT_ENOSYS;
#endif
}

rt_err_t xiaozhi_wake_engine_cpu_samples_snapshot(
    xiaozhi_wake_cpu_sample_snapshot_t *snapshot)
{
    if (snapshot == RT_NULL)
    {
        return -RT_EINVAL;
    }

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return (rt_err_t)xiaozhi_edge_impulse_cpu_samples_snapshot(snapshot);
#else
    rt_memset(snapshot, 0, sizeof(*snapshot));
    return -RT_ENOSYS;
#endif
}

rt_size_t xiaozhi_wake_engine_cpu_samples_read(
    const xiaozhi_wake_cpu_sample_snapshot_t *snapshot,
    rt_size_t offset,
    rt_uint32_t *samples,
    rt_size_t capacity)
{
    if ((snapshot == RT_NULL) || (samples == RT_NULL) || (capacity == 0U))
    {
        return 0U;
    }

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    return xiaozhi_edge_impulse_cpu_samples_read(snapshot,
                                                  offset,
                                                  samples,
                                                  capacity);
#else
    RT_UNUSED(offset);
    return 0U;
#endif
}

rt_err_t xiaozhi_wake_engine_process_pcm16(const int16_t *pcm,
                                           rt_uint32_t sample_count,
                                           xiaozhi_wake_result_t *result)
{
    if (result == RT_NULL)
    {
        return -RT_EINVAL;
    }

    rt_memset(result, 0, sizeof(*result));

    if ((pcm == RT_NULL) || (sample_count == 0U))
    {
        return -RT_EINVAL;
    }

    if (!g_wake.initialized)
    {
        xiaozhi_wake_engine_init();
    }

    if (!g_wake.ready)
    {
        result->event = XIAOZHI_WAKE_EVENT_UNAVAILABLE;
        if (!g_wake.unavailable_logged)
        {
            g_wake.unavailable_logged = RT_TRUE;
            rt_kprintf("[xiaozhi_wake] no real wake engine linked; build with Infineon DEEPCRAFT VA to enable wake word\n");
        }
        return -RT_ENOSYS;
    }

#ifdef XIAOZHI_WAKE_USE_EDGE_IMPULSE_TFLM
    {
        int detected = 0;
        int confidence_permille = 0;
        int ret = xiaozhi_edge_impulse_wake_process(pcm,
                                                    sample_count,
                                                    &detected,
                                                    &confidence_permille);
        if (ret != 0)
        {
            result->event = XIAOZHI_WAKE_EVENT_ERROR;
            result->error_code = xiaozhi_edge_impulse_wake_last_error();
            return -RT_ERROR;
        }

        if (detected)
        {
            result->event = XIAOZHI_WAKE_EVENT_DETECTED;
            rt_strncpy(result->wake_word, "xiaorui", sizeof(result->wake_word) - 1);
            result->error_code = confidence_permille;
            return RT_EOK;
        }
    }
#elif defined(XIAOZHI_WAKE_USE_IFX_DEEPCRAFT)
    {
        int detected = 0;
        int ret;
        rt_uint32_t offset = 0;

        while (offset + 160U <= sample_count)
        {
            ret = ifx_deepcraft_wake_process((int16_t *)(pcm + offset), &detected);
            if (ret != 0)
            {
                result->event = XIAOZHI_WAKE_EVENT_ERROR;
                result->error_code = (int)ret;
                return -RT_ERROR;
            }

            if (detected)
            {
                result->event = XIAOZHI_WAKE_EVENT_DETECTED;
                rt_strncpy(result->wake_word, "xiaorui", sizeof(result->wake_word) - 1);
                return RT_EOK;
            }

            offset += 160U;
        }
    }
#endif

    result->event = XIAOZHI_WAKE_EVENT_NONE;
    return RT_EOK;
}
