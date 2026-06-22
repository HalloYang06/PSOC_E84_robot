#include "xiaozhi_voice_relay.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#if defined(RT_USING_FAL)
#include <fal.h>
#endif

#include <netdev_ipaddr.h>
#include <netdev.h>

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
#define XIAOZHI_TOKEN_FAL_PART "xiaozhi_cfg"
#define XIAOZHI_TOKEN_FAL_MAGIC 0x585A544BU
#define XIAOZHI_TOKEN_FAL_VERSION 1U
#define XIAOZHI_TOKEN_FAL_RECORD_MAGIC_EMPTY 0xFFFFFFFFU

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t token_update_active;
    char ws_url[XIAOZHI_URL_MAX];
    char device_id[32];
    char client_id[40];
    char token[XIAOZHI_TOKEN_MAX];
    char token_staging[XIAOZHI_TOKEN_MAX];
} xiaozhi_voice_relay_t;

static xiaozhi_voice_relay_t g_xiaozhi;

typedef struct
{
    rt_uint32_t magic;
    rt_uint32_t version;
    char token[XIAOZHI_TOKEN_MAX];
    rt_uint32_t checksum;
} xiaozhi_token_record_t;

static rt_uint32_t xiaozhi_token_checksum(const void *data, rt_size_t size)
{
    const rt_uint8_t *p = (const rt_uint8_t *)data;
    rt_uint32_t hash = 2166136261UL;

    while (size-- > 0U)
    {
        hash ^= *p++;
        hash *= 16777619UL;
    }

    return hash;
}

static rt_uint32_t xiaozhi_token_record_checksum(const xiaozhi_token_record_t *record)
{
    return xiaozhi_token_checksum(record,
                                  (rt_size_t)((const rt_uint8_t *)&record->checksum -
                                              (const rt_uint8_t *)record));
}

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

static rt_bool_t xiaozhi_token_record_is_valid(xiaozhi_token_record_t *record)
{
    if (record == RT_NULL)
    {
        return RT_FALSE;
    }

    record->token[sizeof(record->token) - 1] = '\0';
    return ((record->magic == XIAOZHI_TOKEN_FAL_MAGIC) &&
            (record->version == XIAOZHI_TOKEN_FAL_VERSION) &&
            (record->checksum == xiaozhi_token_record_checksum(record)) &&
            (record->token[0] != '\0') &&
            (rt_strnlen(record->token, sizeof(record->token)) < sizeof(record->token))) ?
           RT_TRUE :
           RT_FALSE;
}

static void xiaozhi_format_device_id(const struct netdev *netdev, char *out, rt_size_t out_len)
{
    rt_size_t i;
    rt_size_t used = 0;

    if ((out == RT_NULL) || (out_len == 0U))
    {
        return;
    }

    out[0] = '\0';
    if ((netdev == RT_NULL) || (netdev->hwaddr_len == 0U))
    {
        rt_strncpy(out, XIAOZHI_DEVICE_ID, out_len - 1);
        out[out_len - 1] = '\0';
        return;
    }

    for (i = 0; (i < netdev->hwaddr_len) && ((used + 3U) < out_len); i++)
    {
        int n = rt_snprintf(out + used, out_len - used, "%02X", netdev->hwaddr[i]);
        if (n < 0)
        {
            break;
        }
        used += (rt_size_t)n;
        if ((i + 1U) < netdev->hwaddr_len)
        {
            if ((used + 1U) >= out_len)
            {
                break;
            }
            out[used++] = ':';
            out[used] = '\0';
        }
    }
}

static rt_bool_t xiaozhi_load_or_create_client_id(char *out, rt_size_t out_len)
{
    FILE *fp;
    char buf[48];
    size_t read_len;
    rt_bool_t valid = RT_FALSE;
    struct rt_device *random_dev = rt_device_find("urandom");

    if ((out == RT_NULL) || (out_len == 0U))
    {
        return RT_FALSE;
    }

    out[0] = '\0';

    fp = fopen("/flash/rehab_xiaozhi_client_id.cfg", "rb");
    if (fp != RT_NULL)
    {
        rt_memset(buf, 0, sizeof(buf));
        read_len = fread(buf, 1, sizeof(buf) - 1, fp);
        fclose(fp);
        if ((read_len > 0U) && (rt_strlen(buf) >= 8U))
        {
            rt_strncpy(out, buf, out_len - 1);
            out[out_len - 1] = '\0';
            return RT_TRUE;
        }
    }

    if (random_dev != RT_NULL)
    {
        rt_uint8_t rnd[16];
        rt_ssize_t got = rt_device_read(random_dev, 0, rnd, sizeof(rnd));
        if (got == (rt_ssize_t)sizeof(rnd))
        {
            rt_snprintf(buf, sizeof(buf),
                        "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
                        rnd[0], rnd[1], rnd[2], rnd[3],
                        rnd[4], rnd[5],
                        (rnd[6] & 0x0fU) | 0x40U, rnd[7],
                        (rnd[8] & 0x3fU) | 0x80U, rnd[9],
                        rnd[10], rnd[11], rnd[12], rnd[13], rnd[14], rnd[15]);
            rt_snprintf(out, out_len, "%s", buf);
            valid = RT_TRUE;
        }
    }

    if (!valid)
    {
        rt_snprintf(out, out_len, "00000000-0000-4000-8000-%08lu%08lu",
                    (unsigned long)rt_tick_get(),
                    (unsigned long)rt_strlen(XIAOZHI_ROBOT_ID));
        valid = RT_TRUE;
    }

    fp = fopen("/flash/rehab_xiaozhi_client_id.cfg", "wb");
    if (fp != RT_NULL)
    {
        (void)fwrite(out, 1, rt_strlen(out), fp);
        fclose(fp);
    }

    return valid;
}

#if defined(RT_USING_FAL)
static rt_err_t xiaozhi_voice_relay_load_token_fal(char *token, rt_size_t token_len)
{
    const struct fal_partition *part;
    xiaozhi_token_record_t record;
    rt_bool_t found = RT_FALSE;
    rt_uint32_t offset;

    if ((token == RT_NULL) || (token_len == 0U))
    {
        return -RT_EINVAL;
    }

    token[0] = '\0';
    (void)fal_init();
    part = fal_partition_find(XIAOZHI_TOKEN_FAL_PART);
    if (part == RT_NULL)
    {
        return -RT_ERROR;
    }

    for (offset = 0U; offset + sizeof(record) <= part->len; offset += sizeof(record))
    {
        if (fal_partition_read(part, offset, (rt_uint8_t *)&record, sizeof(record)) != sizeof(record))
        {
            return -RT_ERROR;
        }
        if (record.magic == XIAOZHI_TOKEN_FAL_RECORD_MAGIC_EMPTY)
        {
            break;
        }
        if (xiaozhi_token_record_is_valid(&record))
        {
            rt_strncpy(token, record.token, token_len - 1);
            token[token_len - 1] = '\0';
            found = RT_TRUE;
        }
    }

    return found ? RT_EOK : -RT_ERROR;
}

static rt_err_t xiaozhi_voice_relay_save_token_fal(const char *token)
{
    const struct fal_partition *part;
    xiaozhi_token_record_t record;
    xiaozhi_token_record_t existing;
    rt_uint32_t offset;
    rt_uint32_t write_offset = 0xFFFFFFFFU;

    if ((token == RT_NULL) || (token[0] == '\0') || (rt_strlen(token) >= sizeof(record.token)))
    {
        return -RT_EINVAL;
    }

    (void)fal_init();
    part = fal_partition_find(XIAOZHI_TOKEN_FAL_PART);
    if (part == RT_NULL)
    {
        rt_kprintf("[xiaozhi] token fal part not found: %s\n", XIAOZHI_TOKEN_FAL_PART);
        return -RT_ERROR;
    }

    for (offset = 0U; offset + sizeof(existing) <= part->len; offset += sizeof(existing))
    {
        if (fal_partition_read(part, offset, (rt_uint8_t *)&existing, sizeof(existing)) != sizeof(existing))
        {
            return -RT_ERROR;
        }
        if (existing.magic == XIAOZHI_TOKEN_FAL_RECORD_MAGIC_EMPTY)
        {
            write_offset = offset;
            break;
        }
    }

    if (write_offset == 0xFFFFFFFFU)
    {
        if (fal_partition_erase(part, 0, part->len) < 0)
        {
            return -RT_ERROR;
        }
        write_offset = 0U;
    }

    rt_memset(&record, 0, sizeof(record));
    record.magic = XIAOZHI_TOKEN_FAL_MAGIC;
    record.version = XIAOZHI_TOKEN_FAL_VERSION;
    rt_strncpy(record.token, token, sizeof(record.token) - 1);
    record.checksum = xiaozhi_token_record_checksum(&record);

    if (fal_partition_write(part, write_offset, (const rt_uint8_t *)&record, sizeof(record)) != sizeof(record))
    {
        return -RT_ERROR;
    }

    rt_kprintf("[xiaozhi] token fal saved offset=%lu size=%lu\n",
               (unsigned long)write_offset,
               (unsigned long)sizeof(record));
    return RT_EOK;
}

static rt_err_t xiaozhi_voice_relay_clear_token_fal(void)
{
    const struct fal_partition *part;

    (void)fal_init();
    part = fal_partition_find(XIAOZHI_TOKEN_FAL_PART);
    if (part == RT_NULL)
    {
        return -RT_ERROR;
    }
    return (fal_partition_erase(part, 0, part->len) < 0) ? -RT_ERROR : RT_EOK;
}
#endif

typedef struct
{
    char magic[32];
    char token[XIAOZHI_TOKEN_MAX];
} xiaozhi_token_file_t;

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
#if defined(RT_USING_FAL)
    (void)xiaozhi_voice_relay_clear_token_fal();
#endif
    (void)remove(XIAOZHI_TOKEN_FILE_PATH);
}

rt_err_t xiaozhi_voice_relay_init(void)
{
    rt_err_t ret;
    struct netdev *netdev;

    if (g_xiaozhi.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_xiaozhi, 0, sizeof(g_xiaozhi));
    rt_strncpy(g_xiaozhi.ws_url, XIAOZHI_DEFAULT_WS_URL, sizeof(g_xiaozhi.ws_url) - 1);
    netdev = netdev_default;
    if (netdev == RT_NULL)
    {
        netdev = netdev_get_first_by_flags(NETDEV_FLAG_UP);
    }
    xiaozhi_format_device_id(netdev, g_xiaozhi.device_id, sizeof(g_xiaozhi.device_id));
    (void)xiaozhi_load_or_create_client_id(g_xiaozhi.client_id, sizeof(g_xiaozhi.client_id));
    ret = -RT_ERROR;
#if defined(RT_USING_FAL)
    ret = xiaozhi_voice_relay_load_token_fal(g_xiaozhi.token, sizeof(g_xiaozhi.token));
#endif
    if (ret != RT_EOK)
    {
        ret = xiaozhi_voice_relay_load_token_file(g_xiaozhi.token, sizeof(g_xiaozhi.token));
    }
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

const char *xiaozhi_voice_relay_get_device_id(void)
{
    xiaozhi_voice_relay_init();
    return g_xiaozhi.device_id[0] ? g_xiaozhi.device_id : XIAOZHI_DEVICE_ID;
}

const char *xiaozhi_voice_relay_get_client_id(void)
{
    xiaozhi_voice_relay_init();
    return g_xiaozhi.client_id[0] ? g_xiaozhi.client_id : XIAOZHI_ROBOT_ID;
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
    ret = -RT_ERROR;
#if defined(RT_USING_FAL)
    ret = xiaozhi_voice_relay_save_token_fal(g_xiaozhi.token);
#endif
    if (ret != RT_EOK)
    {
        ret = xiaozhi_voice_relay_save_token_file(g_xiaozhi.token);
    }
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
                    xiaozhi_voice_relay_get_device_id(),
                    xiaozhi_voice_relay_get_client_id());
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
                    "\"features\":{\"mcp\":true,\"aec\":true},"
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
    else if (wake_source == XIAOZHI_WAKE_SOURCE_REALTIME)
    {
        mode = "realtime";
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
                                               xiaozhi_wake_source_t wake_source,
                                               rt_uint32_t total_bytes,
                                               rt_uint32_t chunks)
{
    int n;
    const char *mode = "auto";

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }

    if (wake_source == XIAOZHI_WAKE_SOURCE_MANUAL)
    {
        mode = "manual";
    }
    else if (wake_source == XIAOZHI_WAKE_SOURCE_REALTIME)
    {
        mode = "realtime";
    }

    n = rt_snprintf(out, out_len,
                    "{\"session_id\":\"%s\",\"type\":\"listen\",\"state\":\"stop\","
                    "\"mode\":\"%s\",\"audio_bytes\":%lu,\"audio_chunks\":%lu}",
                    (session_id && session_id[0]) ? session_id : "",
                    mode,
                    (unsigned long)total_bytes,
                    (unsigned long)chunks);
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
