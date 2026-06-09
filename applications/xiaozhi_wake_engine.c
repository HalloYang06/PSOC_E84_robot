#include "xiaozhi_wake_engine.h"

#include <string.h>

#ifdef XIAOZHI_WAKE_USE_IFX_DEEPCRAFT
#include "voice_assistant.h"
#endif

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t ready;
    rt_bool_t unavailable_logged;
} xiaozhi_wake_engine_t;

static xiaozhi_wake_engine_t g_wake;

const char *xiaozhi_wake_engine_backend_name(void)
{
#ifdef XIAOZHI_WAKE_USE_IFX_DEEPCRAFT
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

#ifdef XIAOZHI_WAKE_USE_IFX_DEEPCRAFT
    if (voice_assistant_init(VA_MODE_WW_ONLY) == VA_RSLT_SUCCESS)
    {
        g_wake.ready = RT_TRUE;
        rt_kprintf("[xiaozhi_wake] ready backend=%s\n", xiaozhi_wake_engine_backend_name());
        return RT_EOK;
    }

    rt_kprintf("[xiaozhi_wake] Infineon DEEPCRAFT init failed\n");
    return -RT_ERROR;
#else
    rt_kprintf("[xiaozhi_wake] unavailable: Infineon DEEPCRAFT wake engine is not linked\n");
    return -RT_ENOSYS;
#endif
}

rt_bool_t xiaozhi_wake_engine_is_ready(void)
{
    return g_wake.ready;
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

#ifdef XIAOZHI_WAKE_USE_IFX_DEEPCRAFT
    {
        va_event_t event = VA_NO_EVENT;
        va_data_t data;
        va_rslt_t ret;
        rt_uint32_t offset = 0;

        rt_memset(&data, 0, sizeof(data));
        while (offset + 160U <= sample_count)
        {
            ret = voice_assistant_process((int16_t *)(pcm + offset), &event, &data);
            if (ret != VA_RSLT_SUCCESS)
            {
                result->event = XIAOZHI_WAKE_EVENT_ERROR;
                result->error_code = (int)ret;
                return -RT_ERROR;
            }

            if (event == VA_EVENT_WW_DETECTED)
            {
                result->event = XIAOZHI_WAKE_EVENT_DETECTED;
                rt_strncpy(result->wake_word, "Okay Infineon", sizeof(result->wake_word) - 1);
                return RT_EOK;
            }

            offset += 160U;
        }
    }
#endif

    result->event = XIAOZHI_WAKE_EVENT_NONE;
    return RT_EOK;
}
