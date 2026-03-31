#include "baidu_tts.h"

#include <rtdevice.h>
#include <string.h>

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t ready;
    char api_key[64];
    char secret_key[64];
} baidu_tts_t;

static baidu_tts_t g_tts;

static rt_bool_t baidu_key_is_placeholder(const char *value)
{
    if ((value == RT_NULL) || (*value == '\0'))
    {
        return RT_TRUE;
    }

    return (rt_strcmp(value, "YOUR_BAIDU_API_KEY") == 0) ||
           (rt_strcmp(value, "YOUR_BAIDU_SECRET_KEY") == 0);
}

rt_err_t baidu_tts_init(const char *api_key, const char *secret_key)
{
    if (g_tts.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_tts, 0, sizeof(g_tts));
    if (api_key)
    {
        rt_strncpy(g_tts.api_key, api_key, sizeof(g_tts.api_key) - 1);
    }
    if (secret_key)
    {
        rt_strncpy(g_tts.secret_key, secret_key, sizeof(g_tts.secret_key) - 1);
    }

    g_tts.initialized = RT_TRUE;
    g_tts.ready = !baidu_key_is_placeholder(api_key) && !baidu_key_is_placeholder(secret_key);

    if (g_tts.ready)
    {
        rt_kprintf("[baidu_tts] backend armed, HTTP flow still pending real credentials test\n");
    }
    else
    {
        rt_kprintf("[baidu_tts] disabled: missing credentials\n");
    }

    return RT_EOK;
}

rt_bool_t baidu_tts_is_ready(void)
{
    return g_tts.ready;
}

rt_err_t baidu_tts_synthesize(const char *text, baidu_tts_callback_t callback)
{
    RT_UNUSED(text);

    if (callback == RT_NULL)
    {
        return -RT_EINVAL;
    }

    if (!g_tts.ready)
    {
        callback(RT_NULL, 0, -RT_ENOSYS);
        return -RT_ENOSYS;
    }

    rt_kprintf("[baidu_tts] credentials configured, but cloud HTTP TTS is not implemented yet\n");
    callback(RT_NULL, 0, -RT_ENOSYS);
    return -RT_ENOSYS;
}
