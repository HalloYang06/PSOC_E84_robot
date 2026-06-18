#include "xiaozhi_voice_relay.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#if defined(__has_include)
#if __has_include("xiaozhi_local_token.h")
#include "xiaozhi_local_token.h"
#endif
#endif

#define XIAOZHI_DEFAULT_WS_URL "ws://106.55.62.122:8011/api/rehab-arm/v1/projects/" XIAOZHI_PROJECT_ID "/devices/" XIAOZHI_DEVICE_ID "/xiaozhi/ws?robot_id=" XIAOZHI_ROBOT_ID
#define XIAOZHI_TOKEN_MAX      768
#define XIAOZHI_URL_MAX        192
#define XIAOZHI_TOKEN_FILE_PATH "/flash/rehab_xiaozhi_token.cfg"
#define XIAOZHI_TOKEN_FILE_MAGIC "rehab_xiaozhi_token_v1"

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t token_update_active;
    char ws_url[XIAOZHI_URL_MAX];
    char token[XIAOZHI_TOKEN_MAX];
    char token_staging[XIAOZHI_TOKEN_MAX];
} xiaozhi_voice_relay_t;

static xiaozhi_voice_relay_t g_xiaozhi;

typedef struct
{
    char magic[32];
    char token[XIAOZHI_TOKEN_MAX];
} xiaozhi_token_file_t;

static void json_get_string(const char *json, const char *key, char *out, rt_size_t out_len)
{
    char pattern[48];
    const char *p;
    const char *start;
    rt_size_t i = 0;

    if (!json || !key || !out || out_len == 0)
    {
        return;
    }

    out[0] = '\0';
    rt_snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    p = strstr(json, pattern);
    if (!p)
    {
        return;
    }

    p = strchr(p + strlen(pattern), ':');
    if (!p)
    {
        return;
    }

    p++;
    while ((*p == ' ') || (*p == '\t'))
    {
        p++;
    }

    if (*p != '"')
    {
        return;
    }

    start = ++p;
    while (*p && *p != '"' && i < out_len - 1)
    {
        if ((*p == '\\') && (*(p + 1) != '\0'))
        {
            p++;
        }
        out[i++] = *p++;
    }
    out[i] = '\0';
    RT_UNUSED(start);
}

static rt_bool_t xiaozhi_token_file_is_valid(xiaozhi_token_file_t *record)
{
    if (record == RT_NULL)
    {
        return RT_FALSE;
    }

    record->magic[sizeof(record->magic) - 1] = '\0';
    record->token[sizeof(record->token) - 1] = '\0';
    if (rt_strcmp(record->magic, XIAOZHI_TOKEN_FILE_MAGIC) != 0)
    {
        return RT_FALSE;
    }
    if ((record->token[0] == '\0') || (rt_strlen(record->token) >= sizeof(record->token)))
    {
        return RT_FALSE;
    }
    return RT_TRUE;
}

static rt_err_t xiaozhi_voice_relay_load_token_file(char *token, rt_size_t token_len)
{
    FILE *fp;
    xiaozhi_token_file_t record;
    size_t read_len;

    if ((token == RT_NULL) || (token_len == 0U))
    {
        return -RT_EINVAL;
    }

    token[0] = '\0';
    fp = fopen(XIAOZHI_TOKEN_FILE_PATH, "rb");
    if (fp == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_memset(&record, 0, sizeof(record));
    read_len = fread(&record, 1, sizeof(record), fp);
    fclose(fp);
    if (read_len != sizeof(record))
    {
        return -RT_ERROR;
    }

    if (!xiaozhi_token_file_is_valid(&record))
    {
        return -RT_ERROR;
    }

    rt_strncpy(token, record.token, token_len - 1);
    token[token_len - 1] = '\0';
    return RT_EOK;
}

static rt_err_t xiaozhi_voice_relay_save_token_file(const char *token)
{
    FILE *fp;
    xiaozhi_token_file_t record;

    if ((token == RT_NULL) || (token[0] == '\0'))
    {
        return -RT_EINVAL;
    }
    if (rt_strlen(token) >= sizeof(record.token))
    {
        return -RT_EINVAL;
    }

    rt_memset(&record, 0, sizeof(record));
    rt_strncpy(record.magic, XIAOZHI_TOKEN_FILE_MAGIC, sizeof(record.magic) - 1);
    rt_strncpy(record.token, token, sizeof(record.token) - 1);

    fp = fopen(XIAOZHI_TOKEN_FILE_PATH, "wb");
    if (fp == RT_NULL)
    {
        return -RT_ERROR;
    }

    if (fwrite(&record, 1, sizeof(record), fp) != sizeof(record))
    {
        fclose(fp);
        return -RT_ERROR;
    }

    fclose(fp);
    return RT_EOK;
}

static void xiaozhi_voice_relay_clear_token_file(void)
{
    (void)remove(XIAOZHI_TOKEN_FILE_PATH);
}

rt_err_t xiaozhi_voice_relay_init(void)
{
    rt_err_t ret;

    if (g_xiaozhi.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_xiaozhi, 0, sizeof(g_xiaozhi));
    rt_strncpy(g_xiaozhi.ws_url, XIAOZHI_DEFAULT_WS_URL, sizeof(g_xiaozhi.ws_url) - 1);
    ret = xiaozhi_voice_relay_load_token_file(g_xiaozhi.token, sizeof(g_xiaozhi.token));
    if (ret != RT_EOK)
    {
#ifdef XIAOZHI_LOCAL_TOKEN
        if ((rt_strlen(XIAOZHI_LOCAL_TOKEN) > 0U) &&
            (rt_strlen(XIAOZHI_LOCAL_TOKEN) < sizeof(g_xiaozhi.token)))
        {
            rt_strncpy(g_xiaozhi.token, XIAOZHI_LOCAL_TOKEN, sizeof(g_xiaozhi.token) - 1);
        }
#endif
    }
    g_xiaozhi.initialized = RT_TRUE;
    return RT_EOK;
}

const char *xiaozhi_voice_relay_get_url(void)
{
    xiaozhi_voice_relay_init();
    return g_xiaozhi.ws_url;
}

rt_bool_t xiaozhi_voice_relay_has_token(void)
{
    xiaozhi_voice_relay_init();
    return g_xiaozhi.token[0] != '\0' ? RT_TRUE : RT_FALSE;
}

rt_size_t xiaozhi_voice_relay_token_len(void)
{
    xiaozhi_voice_relay_init();
    return rt_strlen(g_xiaozhi.token);
}

rt_size_t xiaozhi_voice_relay_token_staging_len(void)
{
    xiaozhi_voice_relay_init();
    return rt_strlen(g_xiaozhi.token_staging);
}

rt_err_t xiaozhi_voice_relay_set_url(const char *url)
{
    if ((url == RT_NULL) || (rt_strncmp(url, "ws://", 5) != 0) || (rt_strlen(url) >= sizeof(g_xiaozhi.ws_url)))
    {
        return -RT_EINVAL;
    }

    xiaozhi_voice_relay_init();
    rt_memset(g_xiaozhi.ws_url, 0, sizeof(g_xiaozhi.ws_url));
    rt_strncpy(g_xiaozhi.ws_url, url, sizeof(g_xiaozhi.ws_url) - 1);
    return RT_EOK;
}

rt_err_t xiaozhi_voice_relay_set_token(const char *token)
{
    rt_err_t ret;

    xiaozhi_voice_relay_init();

    if ((token == RT_NULL) || (token[0] == '\0'))
    {
        g_xiaozhi.token[0] = '\0';
        xiaozhi_voice_relay_clear_token_file();
        return RT_EOK;
    }

    if (rt_strlen(token) >= sizeof(g_xiaozhi.token))
    {
        return -RT_EINVAL;
    }

    rt_memset(g_xiaozhi.token, 0, sizeof(g_xiaozhi.token));
    rt_memcpy(g_xiaozhi.token, token, rt_strlen(token));
    ret = xiaozhi_voice_relay_save_token_file(g_xiaozhi.token);
    if (ret != RT_EOK)
    {
        rt_kprintf("[xiaozhi] token save failed ret=%d path=%s\n", ret, XIAOZHI_TOKEN_FILE_PATH);
    }
    return ret;
}

rt_err_t xiaozhi_voice_relay_token_update_begin(void)
{
    xiaozhi_voice_relay_init();
    rt_memset(g_xiaozhi.token_staging, 0, sizeof(g_xiaozhi.token_staging));
    g_xiaozhi.token_update_active = RT_TRUE;
    return RT_EOK;
}

rt_err_t xiaozhi_voice_relay_token_update_part(const char *chunk)
{
    rt_size_t used;
    rt_size_t add;

    xiaozhi_voice_relay_init();
    if (!g_xiaozhi.token_update_active)
    {
        return -RT_ERROR;
    }

    if ((chunk == RT_NULL) || (chunk[0] == '\0'))
    {
        return -RT_EINVAL;
    }

    used = rt_strlen(g_xiaozhi.token_staging);
    add = rt_strlen(chunk);
    if ((used + add) >= sizeof(g_xiaozhi.token_staging))
    {
        return -RT_EFULL;
    }

    rt_strncpy(g_xiaozhi.token_staging + used,
               chunk,
               sizeof(g_xiaozhi.token_staging) - used - 1);
    return RT_EOK;
}

rt_err_t xiaozhi_voice_relay_token_update_commit(void)
{
    rt_err_t ret;

    xiaozhi_voice_relay_init();
    if (!g_xiaozhi.token_update_active)
    {
        return -RT_ERROR;
    }

    ret = xiaozhi_voice_relay_set_token(g_xiaozhi.token_staging);
    rt_memset(g_xiaozhi.token_staging, 0, sizeof(g_xiaozhi.token_staging));
    g_xiaozhi.token_update_active = RT_FALSE;
    return ret;
}

void xiaozhi_voice_relay_token_update_clear(void)
{
    xiaozhi_voice_relay_init();
    rt_memset(g_xiaozhi.token, 0, sizeof(g_xiaozhi.token));
    rt_memset(g_xiaozhi.token_staging, 0, sizeof(g_xiaozhi.token_staging));
    g_xiaozhi.token_update_active = RT_FALSE;
    xiaozhi_voice_relay_clear_token_file();
}

rt_err_t xiaozhi_voice_relay_build_headers(char *out, rt_size_t out_len)
{
    int n;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    xiaozhi_voice_relay_init();
    if (g_xiaozhi.token[0] == '\0')
    {
        out[0] = '\0';
        return RT_EOK;
    }

    n = rt_snprintf(out, out_len,
                    "Authorization: Bearer %s\r\n"
                    "Protocol-Version: %u\r\n"
                    "Device-Id: %s\r\n"
                    "Client-Id: %s\r\n",
                    g_xiaozhi.token,
                    (unsigned)XIAOZHI_PROTOCOL_VERSION,
                    XIAOZHI_DEVICE_ID,
                    XIAOZHI_ROBOT_ID);
    return ((n < 0) || ((rt_size_t)n >= out_len)) ? -RT_EFULL : RT_EOK;
}

rt_err_t xiaozhi_voice_relay_build_hello(char *out, rt_size_t out_len)
{
    int n;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    n = rt_snprintf(out, out_len,
                    "{\"type\":\"hello\",\"version\":%u,"
                    "\"features\":{\"mcp\":true},"
                    "\"transport\":\"websocket\","
                    "\"audio_params\":{\"format\":\"%s\",\"sample_rate\":%u,\"channels\":%u,\"frame_duration\":%u}}",
                    (unsigned)XIAOZHI_PROTOCOL_VERSION,
                    XIAOZHI_AUDIO_FORMAT,
                    (unsigned)XIAOZHI_AUDIO_SAMPLE_RATE,
                    (unsigned)XIAOZHI_AUDIO_CHANNELS,
                    (unsigned)XIAOZHI_AUDIO_FRAME_DURATION_MS);
    return ((n < 0) || ((rt_size_t)n >= out_len)) ? -RT_EFULL : RT_EOK;
}

rt_err_t xiaozhi_voice_relay_build_listen_detect(char *out, rt_size_t out_len,
                                                 const char *session_id,
                                                 const char *wake_word)
{
    int n;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    n = rt_snprintf(out, out_len,
                    "{\"session_id\":\"%s\",\"type\":\"listen\",\"state\":\"detect\","
                    "\"text\":\"%s\",\"source\":\"m55_wake_word\","
                    "\"control_boundary\":\"xiaozhi_wake_detect_only_not_motion_permission\"}",
                    (session_id && session_id[0]) ? session_id : "",
                    (wake_word && wake_word[0]) ? wake_word : "wake_word");
    return ((n < 0) || ((rt_size_t)n >= out_len)) ? -RT_EFULL : RT_EOK;
}

rt_err_t xiaozhi_voice_relay_build_listen_start(char *out, rt_size_t out_len,
                                                const char *session_id,
                                                xiaozhi_wake_source_t wake_source)
{
    int n;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    const char *mode = "auto";

    if (wake_source == XIAOZHI_WAKE_SOURCE_MANUAL)
    {
        mode = "manual";
    }

    n = rt_snprintf(out, out_len,
                    "{\"session_id\":\"%s\",\"type\":\"listen\",\"state\":\"start\","
                    "\"mode\":\"%s\"}",
                    (session_id && session_id[0]) ? session_id : "",
                    mode);
    return ((n < 0) || ((rt_size_t)n >= out_len)) ? -RT_EFULL : RT_EOK;
}

rt_err_t xiaozhi_voice_relay_build_listen_stop(char *out, rt_size_t out_len,
                                               const char *session_id,
                                               rt_uint32_t total_bytes,
                                               rt_uint32_t chunks)
{
    int n;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    RT_UNUSED(total_bytes);
    RT_UNUSED(chunks);
    n = rt_snprintf(out, out_len,
                    "{\"session_id\":\"%s\",\"type\":\"listen\",\"state\":\"stop\"}",
                    (session_id && session_id[0]) ? session_id : "");
    return ((n < 0) || ((rt_size_t)n >= out_len)) ? -RT_EFULL : RT_EOK;
}

rt_bool_t xiaozhi_voice_relay_parse_response(const char *json,
                                             xiaozhi_response_t *response)
{
    char kind[48];
    char tmp[256];

    if ((json == RT_NULL) || (response == RT_NULL))
    {
        return RT_FALSE;
    }

    rt_memset(response, 0, sizeof(*response));
    response->kind = XIAOZHI_UTTERANCE_UNKNOWN;

    kind[0] = '\0';
    json_get_string(json, "kind", kind, sizeof(kind));
    if (kind[0] == '\0')
    {
        json_get_string(json, "utterance_kind", kind, sizeof(kind));
    }
    if (kind[0] == '\0')
    {
        json_get_string(json, "classification", kind, sizeof(kind));
    }

    if ((rt_strstr(kind, "vla_command") != RT_NULL) || (rt_strstr(kind, "command") != RT_NULL))
    {
        response->kind = XIAOZHI_UTTERANCE_VLA_COMMAND;
    }
    else if ((rt_strstr(kind, "daily_chat") != RT_NULL) || (rt_strstr(kind, "chat") != RT_NULL))
    {
        response->kind = XIAOZHI_UTTERANCE_DAILY_CHAT;
    }

    json_get_string(json, "reply", response->reply, sizeof(response->reply));
    if (response->reply[0] == '\0')
    {
        json_get_string(json, "text", response->reply, sizeof(response->reply));
    }
    if (response->reply[0] == '\0')
    {
        json_get_string(json, "tts", response->reply, sizeof(response->reply));
    }
    if (response->reply[0] == '\0')
    {
        json_get_string(json, "speak", response->reply, sizeof(response->reply));
    }

    json_get_string(json, "transcript", response->transcript, sizeof(response->transcript));
    json_get_string(json, "language_context", response->language_context, sizeof(response->language_context));
    if (response->language_context[0] == '\0')
    {
        json_get_string(json, "voice_intent", response->language_context, sizeof(response->language_context));
    }

    tmp[0] = '\0';
    json_get_string(json, "type", tmp, sizeof(tmp));
    return (response->reply[0] != '\0') ||
           (response->transcript[0] != '\0') ||
           (response->language_context[0] != '\0') ||
           (tmp[0] != '\0') ||
           (response->kind != XIAOZHI_UTTERANCE_UNKNOWN);
}
