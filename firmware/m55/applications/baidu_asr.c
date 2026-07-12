#include "baidu_asr.h"

#include <rtdevice.h>
#include <string.h>

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t ready;
    char api_key[64];
    char secret_key[64];
} baidu_asr_t;

static baidu_asr_t g_asr;

static rt_bool_t baidu_key_is_placeholder(const char *value)
{
    if ((value == RT_NULL) || (*value == '\0'))
    {
        return RT_TRUE;
    }

    return (rt_strcmp(value, "YOUR_BAIDU_API_KEY") == 0) ||
           (rt_strcmp(value, "YOUR_BAIDU_SECRET_KEY") == 0);
}

rt_err_t baidu_asr_init(const char *api_key, const char *secret_key)
{
    if (g_asr.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_asr, 0, sizeof(g_asr));
    if (api_key)
    {
        rt_strncpy(g_asr.api_key, api_key, sizeof(g_asr.api_key) - 1);
    }
    if (secret_key)
    {
        rt_strncpy(g_asr.secret_key, secret_key, sizeof(g_asr.secret_key) - 1);
    }

    g_asr.initialized = RT_TRUE;
    g_asr.ready = !baidu_key_is_placeholder(api_key) && !baidu_key_is_placeholder(secret_key);

    if (g_asr.ready)
    {
        rt_kprintf("[baidu_asr] backend armed, HTTP flow still pending real credentials test\n");
    }
    else
    {
        rt_kprintf("[baidu_asr] disabled: missing credentials\n");
    }

    return RT_EOK;
}

rt_bool_t baidu_asr_is_ready(void)
{
    return g_asr.ready;
}

rt_err_t baidu_asr_recognize(const uint8_t *audio_data, uint32_t len, baidu_asr_callback_t callback)
{
    RT_UNUSED(audio_data);
    RT_UNUSED(len);

    if (callback == RT_NULL)
    {
        return -RT_EINVAL;
    }

    if (!g_asr.ready)
    {
        callback(RT_NULL, -RT_ENOSYS);
        return -RT_ENOSYS;
    }

    rt_kprintf("[baidu_asr] credentials configured, but cloud HTTP ASR is not implemented yet\n");
    callback(RT_NULL, -RT_ENOSYS);
    return -RT_ENOSYS;
}
