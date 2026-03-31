#include "voice_service.h"

#include "baidu_asr.h"
#include "baidu_tts.h"
#include "m33_m55_comm.h"
#include "websocket_client.h"

#include <rtdevice.h>
#include <stdlib.h>
#include <string.h>

#define WS_SERVER_URL                "ws://10.100.191.235:8080"
#define VOICE_PCM_BUFFER_SIZE        (320000U)
#define VOICE_JSON_BUFFER_SIZE       (768U)
#define VOICE_SERVER_AUDIO_CHUNK     (4096U)

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t running;
    rt_bool_t asr_ready;
    rt_bool_t tts_ready;
    rt_uint32_t reconnect_tick;
    rt_thread_t thread;
    struct rt_mutex lock;
    rt_uint8_t *audio_buffer;
    rt_uint32_t audio_expected;
    rt_uint32_t audio_received;
} voice_service_t;

typedef struct
{
    rt_bool_t speech;
    rt_uint32_t peak;
    rt_uint32_t avg_abs;
    rt_uint32_t active_frames;
    rt_uint32_t total_frames;
    rt_uint32_t zcr_permille;
} voice_model_result_t;

static voice_service_t g_service;

static voice_model_result_t voice_service_model_entry(const uint8_t *audio_data, uint32_t len)
{
    const int16_t *samples = (const int16_t *)audio_data;
    voice_model_result_t result;
    uint32_t sample_count;
    const uint32_t frame_samples = 320U;
    uint32_t i;
    uint64_t energy = 0;
    uint32_t crossings = 0;

    rt_memset(&result, 0, sizeof(result));

    if ((audio_data == RT_NULL) || (len < 2U))
    {
        return result;
    }

    sample_count = len / sizeof(int16_t);
    for (i = 0; i < sample_count; i++)
    {
        int32_t s = samples[i];
        uint32_t mag = (s < 0) ? (uint32_t)(-s) : (uint32_t)s;
        if (mag > result.peak)
        {
            result.peak = mag;
        }
        energy += (uint64_t)mag;
        if ((i > 0U) &&
            (((samples[i - 1] < 0) && (samples[i] >= 0)) ||
             ((samples[i - 1] >= 0) && (samples[i] < 0))))
        {
            crossings++;
        }
    }

    result.avg_abs = sample_count ? (rt_uint32_t)(energy / sample_count) : 0U;
    result.total_frames = (sample_count + frame_samples - 1U) / frame_samples;
    result.zcr_permille = sample_count ? (crossings * 1000U) / sample_count : 0U;

    for (i = 0; i < sample_count; i += frame_samples)
    {
        uint32_t j;
        uint32_t end = i + frame_samples;
        uint64_t frame_energy = 0;

        if (end > sample_count)
        {
            end = sample_count;
        }

        for (j = i; j < end; j++)
        {
            int32_t s = samples[j];
            frame_energy += (uint32_t)((s < 0) ? (-s) : s);
        }

        if ((end > i) && ((frame_energy / (end - i)) > 700U))
        {
            result.active_frames++;
        }
    }

    result.speech = (result.peak > 2500U) &&
                    (result.avg_abs > 180U) &&
                    (result.active_frames >= 8U) &&
                    (result.zcr_permille > 5U);

    rt_kprintf("[voice_service] model entry pcm=%lu samples=%lu peak=%lu avg=%lu active=%lu/%lu zcr=%lu speech=%d\n",
               (unsigned long)len,
               (unsigned long)sample_count,
               (unsigned long)result.peak,
               (unsigned long)result.avg_abs,
               (unsigned long)result.active_frames,
               (unsigned long)result.total_frames,
               (unsigned long)result.zcr_permille,
               result.speech ? 1 : 0);

    return result;
}

static rt_bool_t json_get_string(const char *body, const char *key, char *out, rt_size_t out_size)
{
    char pattern[32];
    const char *cursor;
    const char *start;
    const char *end;
    rt_size_t len;

    if (!body || !key || !out || out_size == 0)
    {
        return RT_FALSE;
    }

    rt_snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    cursor = rt_strstr(body, pattern);
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor++;
    while ((*cursor == ' ') || (*cursor == '\t'))
    {
        cursor++;
    }

    if (*cursor != '"')
    {
        return RT_FALSE;
    }

    start = ++cursor;
    end = strchr(start, '"');
    if (!end)
    {
        return RT_FALSE;
    }

    len = (rt_size_t)(end - start);
    if (len >= out_size)
    {
        len = out_size - 1;
    }

    rt_memcpy(out, start, len);
    out[len] = '\0';
    return RT_TRUE;
}

static void json_escape_text(const char *src, char *dst, rt_size_t dst_size)
{
    rt_size_t used = 0;

    if (!dst || dst_size == 0)
    {
        return;
    }

    while (src && *src && (used + 2) < dst_size)
    {
        if ((*src == '\\') || (*src == '"'))
        {
            if ((used + 2) >= dst_size)
            {
                break;
            }
            dst[used++] = '\\';
        }
        else if (*src == '\r' || *src == '\n')
        {
            dst[used++] = ' ';
            src++;
            continue;
        }

        dst[used++] = *src++;
    }

    dst[used] = '\0';
}

static void voice_service_publish_text_to_m33(m33_m55_msg_type_t type, const char *text)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = type;
    if (text)
    {
        rt_strncpy(msg.payload.text.text, text, sizeof(msg.payload.text.text) - 1);
        msg.payload.text.text[sizeof(msg.payload.text.text) - 1] = '\0';
    }

    if (m33_m55_comm_publish(&msg) != RT_EOK)
    {
        rt_kprintf("[voice_service] publish text to M33 failed\n");
    }
}

static void voice_service_stream_audio_to_m33(const uint8_t *audio_data, uint32_t len)
{
    m33_m55_message_t msg;
    uint32_t sent = 0;
    uint32_t chunk_index = 0;
    uint32_t payload_offset = 0;

    if (!audio_data || len == 0)
    {
        return;
    }

    if ((len > 44) && (rt_memcmp(audio_data, "RIFF", 4) == 0))
    {
        payload_offset = 44;
    }

    while ((payload_offset + sent) < len)
    {
        uint32_t remaining = len - payload_offset - sent;
        uint32_t chunk_len = remaining > AUDIO_CHUNK_SIZE ? AUDIO_CHUNK_SIZE : remaining;

        rt_memset(&msg, 0, sizeof(msg));
        msg.type = MSG_TYPE_TTS_AUDIO;
        msg.payload.audio_data.total_len = len - payload_offset;
        msg.payload.audio_data.chunk_index = chunk_index++;
        msg.payload.audio_data.chunk_len = chunk_len;
        rt_memcpy(msg.payload.audio_data.data, audio_data + payload_offset + sent, chunk_len);

        if (m33_m55_comm_publish(&msg) != RT_EOK)
        {
            rt_kprintf("[voice_service] publish TTS chunk failed at %lu\n", (unsigned long)msg.payload.audio_data.chunk_index);
            return;
        }

        sent += chunk_len;
        rt_thread_mdelay(5);
    }
}

static void voice_service_send_text_to_server(const char *type, const char *text)
{
    char escaped[384];
    char json[VOICE_JSON_BUFFER_SIZE];

    if (!websocket_client_is_connected())
    {
        return;
    }

    json_escape_text(text ? text : "", escaped, sizeof(escaped));
    rt_snprintf(json, sizeof(json),
                "{\"type\":\"%s\",\"text\":\"%s\",\"source\":\"m55\",\"tick_ms\":%lu}",
                type, escaped, (unsigned long)rt_tick_get_millisecond());
    websocket_client_send_text(json);
}

static void voice_service_send_audio_to_server(const uint8_t *audio_data, uint32_t len)
{
    char json[VOICE_JSON_BUFFER_SIZE];
    uint32_t sent = 0;
    uint32_t chunk_index = 0;

    if ((audio_data == RT_NULL) || (len == 0) || !websocket_client_is_connected())
    {
        return;
    }

    rt_snprintf(json, sizeof(json),
                "{\"type\":\"voice_capture_begin\",\"encoding\":\"pcm_s16le\","
                "\"sample_rate\":16000,\"channels\":1,\"bits_per_sample\":16,"
                "\"total_bytes\":%lu}",
                (unsigned long)len);
    websocket_client_send_text(json);

    while (sent < len)
    {
        uint32_t chunk_len = len - sent;
        if (chunk_len > VOICE_SERVER_AUDIO_CHUNK)
        {
            chunk_len = VOICE_SERVER_AUDIO_CHUNK;
        }

        if (websocket_client_send_binary(audio_data + sent, chunk_len) != RT_EOK)
        {
            rt_kprintf("[voice_service] websocket binary send failed at chunk %lu\n",
                       (unsigned long)chunk_index);
            break;
        }

        sent += chunk_len;
        chunk_index++;
        rt_thread_mdelay(2);
    }

    rt_snprintf(json, sizeof(json),
                "{\"type\":\"voice_capture_end\",\"total_bytes\":%lu,\"sent_bytes\":%lu,"
                "\"chunks\":%lu}",
                (unsigned long)len, (unsigned long)sent, (unsigned long)chunk_index);
    websocket_client_send_text(json);
}

static void on_asr_result(const char *text, rt_err_t error)
{
    if ((error != RT_EOK) || (text == RT_NULL) || (*text == '\0'))
    {
        rt_kprintf("[voice_service] ASR failed: %d\n", error);
        return;
    }

    rt_kprintf("[voice_service] ASR: %s\n", text);
    voice_service_publish_text_to_m33(MSG_TYPE_ASR_TEXT, text);
    voice_service_send_text_to_server("asr_text", text);
}

static void on_tts_result(const uint8_t *audio_data, uint32_t len, rt_err_t error)
{
    if ((error != RT_EOK) || (audio_data == RT_NULL) || (len == 0))
    {
        rt_kprintf("[voice_service] TTS failed: %d\n", error);
        return;
    }

    rt_kprintf("[voice_service] TTS audio %lu bytes\n", (unsigned long)len);
    voice_service_stream_audio_to_m33(audio_data, len);
}

static void voice_service_handle_server_text(const char *message)
{
    char type[32];
    char text[256];
    char content[256];
    char broadcast[256];
    char speak[256];
    const char *fallback_text = RT_NULL;

    type[0] = '\0';
    text[0] = '\0';
    content[0] = '\0';
    broadcast[0] = '\0';
    speak[0] = '\0';
    json_get_string(message, "type", type, sizeof(type));
    json_get_string(message, "text", text, sizeof(text));
    json_get_string(message, "content", content, sizeof(content));
    json_get_string(message, "message", content, sizeof(content));
    json_get_string(message, "broadcast", broadcast, sizeof(broadcast));
    json_get_string(message, "tts", speak, sizeof(speak));
    json_get_string(message, "speak", speak, sizeof(speak));

    if (text[0] != '\0')
    {
        fallback_text = text;
    }
    else if (content[0] != '\0')
    {
        fallback_text = content;
    }
    else if (broadcast[0] != '\0')
    {
        fallback_text = broadcast;
    }
    else if (speak[0] != '\0')
    {
        fallback_text = speak;
    }
    else if ((type[0] == '\0') && message && *message)
    {
        fallback_text = message;
    }

    if (!fallback_text || !*fallback_text)
    {
        rt_kprintf("[voice_service] server text ignored: %s\n", message);
        return;
    }

    rt_kprintf("[voice_service] server reply: %s\n", fallback_text);
    voice_service_publish_text_to_m33(MSG_TYPE_TTS_REQUEST, fallback_text);

    if (g_service.tts_ready)
    {
        baidu_tts_synthesize(fallback_text, on_tts_result);
    }
    else
    {
        rt_kprintf("[voice_service] TTS backend unavailable, waiting for binary audio or credentials\n");
    }
}

static void on_websocket_message(websocket_message_type_t type, const uint8_t *payload, rt_size_t payload_len)
{
    if (!payload || payload_len == 0)
    {
        return;
    }

    if (type == WEBSOCKET_MESSAGE_BINARY)
    {
        rt_kprintf("[voice_service] server binary audio %lu bytes\n", (unsigned long)payload_len);
        voice_service_stream_audio_to_m33(payload, (uint32_t)payload_len);
        return;
    }

    {
        char text[384];
        rt_size_t copy_len = payload_len >= sizeof(text) ? sizeof(text) - 1 : payload_len;
        rt_memcpy(text, payload, copy_len);
        text[copy_len] = '\0';
        voice_service_handle_server_text(text);
    }
}

static void voice_service_reset_audio(void)
{
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.audio_expected = 0;
    g_service.audio_received = 0;
    rt_mutex_release(&g_service.lock);
}

static void voice_service_process_audio_buffer(void)
{
    rt_uint32_t len;
    voice_model_result_t model_result;
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    len = g_service.audio_received;
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] utterance ready: %lu bytes\n", (unsigned long)len);
    model_result = voice_service_model_entry(g_service.audio_buffer, len);

    if (!model_result.speech)
    {
        rt_kprintf("[voice_service] utterance dropped: non-speech peak=%lu avg=%lu active=%lu/%lu\n",
                   (unsigned long)model_result.peak,
                   (unsigned long)model_result.avg_abs,
                   (unsigned long)model_result.active_frames,
                   (unsigned long)model_result.total_frames);
        return;
    }

    if (websocket_client_is_connected())
    {
        voice_service_send_audio_to_server(g_service.audio_buffer, len);
    }

    if (g_service.asr_ready)
    {
        baidu_asr_recognize(g_service.audio_buffer, len, on_asr_result);
    }
    else
    {
        char notice[128];
        rt_snprintf(notice, sizeof(notice),
                    "{\"type\":\"voice_capture\",\"bytes\":%lu,\"sample_rate\":16000,\"channels\":1,\"bits\":16}",
                    (unsigned long)len);
        rt_kprintf("[voice_service] ASR backend unavailable, only notifying server\n");
        if (websocket_client_is_connected())
        {
            websocket_client_send_text(notice);
        }
    }
}

static void voice_service_accept_shared_pcm(const sensor_stream_msg_t *stream)
{
    rt_uint32_t len;

    if (stream == RT_NULL)
    {
        return;
    }

    if ((stream->source != MODEL_INPUT_SRC_AUDIO_PCM) ||
        (stream->format != MODEL_INPUT_FMT_PCM_S16))
    {
        return;
    }

    if (stream->chunk_index != g_m33_m55_pcm_shared.seq)
    {
        rt_kprintf("[voice_service] shared pcm seq mismatch msg=%lu shared=%lu\n",
                   (unsigned long)stream->chunk_index,
                   (unsigned long)g_m33_m55_pcm_shared.seq);
        return;
    }

    len = stream->total_len;
    if (len > M33_M55_PCM_SHARED_CAPACITY)
    {
        len = M33_M55_PCM_SHARED_CAPACITY;
    }
    if (len > VOICE_PCM_BUFFER_SIZE)
    {
        len = VOICE_PCM_BUFFER_SIZE;
    }

    rt_hw_cpu_dcache_ops(RT_HW_CACHE_INVALIDATE, (void *)g_m33_m55_pcm_shared.data, len);
    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    g_service.audio_expected = len;
    g_service.audio_received = len;
    rt_memcpy(g_service.audio_buffer, (const void *)g_m33_m55_pcm_shared.data, len);
    rt_mutex_release(&g_service.lock);

    rt_kprintf("[voice_service] shared pcm seq=%lu len=%lu sr=%lu ch=%u\n",
               (unsigned long)stream->chunk_index,
               (unsigned long)len,
               (unsigned long)stream->sample_rate,
               (unsigned int)stream->channels);

    voice_service_process_audio_buffer();
    voice_service_reset_audio();
}

static void voice_service_accept_audio_chunk(const audio_data_msg_t *chunk)
{
    if (!chunk)
    {
        return;
    }

    if (chunk->chunk_index == 0)
    {
        voice_service_reset_audio();
        rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
        g_service.audio_expected = chunk->total_len > VOICE_PCM_BUFFER_SIZE ? VOICE_PCM_BUFFER_SIZE : chunk->total_len;
        rt_mutex_release(&g_service.lock);
    }

    rt_mutex_take(&g_service.lock, RT_WAITING_FOREVER);
    if ((g_service.audio_buffer != RT_NULL) &&
        ((g_service.audio_received + chunk->chunk_len) <= VOICE_PCM_BUFFER_SIZE))
    {
        rt_memcpy(g_service.audio_buffer + g_service.audio_received, chunk->data, chunk->chunk_len);
        g_service.audio_received += chunk->chunk_len;
    }
    rt_mutex_release(&g_service.lock);

    if ((chunk->chunk_index % 16U) == 0U)
    {
        rt_kprintf("[voice_service] pcm chunk idx=%lu len=%lu recv=%lu/%lu\n",
                   (unsigned long)chunk->chunk_index,
                   (unsigned long)chunk->chunk_len,
                   (unsigned long)g_service.audio_received,
                   (unsigned long)g_service.audio_expected);
    }

    if ((g_service.audio_expected != 0) && (g_service.audio_received >= g_service.audio_expected))
    {
        voice_service_process_audio_buffer();
        voice_service_reset_audio();
    }
}

static rt_err_t voice_service_send_control(voice_control_cmd_t cmd)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = (rt_uint32_t)cmd;
    return m33_m55_comm_publish(&msg);
}

static void voice_service_thread_entry(void *parameter)
{
    m33_m55_message_t msg;

    RT_UNUSED(parameter);

    while (g_service.running)
    {
        if (!websocket_client_is_connected())
        {
            rt_tick_t now = rt_tick_get();
            if ((g_service.reconnect_tick == 0) || (now - g_service.reconnect_tick > RT_TICK_PER_SECOND * 2))
            {
                g_service.reconnect_tick = now;
                if (websocket_client_connect() == RT_EOK)
                {
                    rt_kprintf("[voice_service] websocket reconnected\n");
                }
            }
        }

        while (m33_m55_comm_consume(&msg) == RT_EOK)
        {
            switch (msg.type)
            {
            case MSG_TYPE_SENSOR_STREAM:
                voice_service_accept_shared_pcm(&msg.payload.sensor_stream);
                break;
            case MSG_TYPE_AUDIO_DATA:
                voice_service_accept_audio_chunk(&msg.payload.audio_data);
                break;
            case MSG_TYPE_TTS_REQUEST:
                voice_service_handle_server_text(msg.payload.text.text);
                break;
            default:
                break;
            }
        }

        rt_thread_mdelay(50);
    }
}

rt_err_t voice_service_init(const char *baidu_api_key, const char *baidu_secret_key)
{
    rt_err_t ret;

    if (g_service.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_service, 0, sizeof(g_service));
    rt_mutex_init(&g_service.lock, "voice", RT_IPC_FLAG_PRIO);
    g_service.audio_buffer = (rt_uint8_t *)rt_malloc(VOICE_PCM_BUFFER_SIZE);
    if (g_service.audio_buffer == RT_NULL)
    {
        rt_kprintf("[voice_service] alloc audio buffer failed: %u\n", VOICE_PCM_BUFFER_SIZE);
        return -RT_ENOMEM;
    }

    ret = m33_m55_comm_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] IPC init failed: %d\n", ret);
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    ret = baidu_asr_init(baidu_api_key, baidu_secret_key);
    if (ret != RT_EOK)
    {
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }
    ret = baidu_tts_init(baidu_api_key, baidu_secret_key);
    if (ret != RT_EOK)
    {
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    g_service.asr_ready = baidu_asr_is_ready();
    g_service.tts_ready = baidu_tts_is_ready();

    ret = websocket_client_init(WS_SERVER_URL);
    if (ret != RT_EOK)
    {
        rt_kprintf("[voice_service] websocket init failed: %d\n", ret);
        rt_free(g_service.audio_buffer);
        g_service.audio_buffer = RT_NULL;
        return ret;
    }

    websocket_client_set_callback(on_websocket_message);
    websocket_client_connect();

    g_service.initialized = RT_TRUE;
    rt_kprintf("[voice_service] initialized (ASR=%d TTS=%d)\n", g_service.asr_ready, g_service.tts_ready);
    return RT_EOK;
}

rt_err_t voice_service_start(void)
{
    if (!g_service.initialized)
    {
        return -RT_ERROR;
    }

    if (g_service.running)
    {
        return RT_EOK;
    }

    g_service.running = RT_TRUE;
    g_service.thread = rt_thread_create("voice_svc", voice_service_thread_entry, RT_NULL, 8192, 8, 5);
    if (!g_service.thread)
    {
        g_service.running = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_service.thread);
    rt_kprintf("[voice_service] started\n");
    return RT_EOK;
}

rt_err_t voice_service_stop(void)
{
    if (!g_service.running)
    {
        return RT_EOK;
    }

    g_service.running = RT_FALSE;
    websocket_client_disconnect();
    return RT_EOK;
}

rt_err_t voice_service_request_capture_start(void)
{
    rt_kprintf("[voice_service] request capture start\n");
    return voice_service_send_control(VOICE_CTRL_START_CAPTURE);
}

rt_err_t voice_service_request_capture_stop(void)
{
    rt_kprintf("[voice_service] request capture stop\n");
    return voice_service_send_control(VOICE_CTRL_STOP_CAPTURE);
}

rt_err_t voice_service_request_listen_start(void)
{
    rt_kprintf("[voice_service] request listen start\n");
    return voice_service_send_control(VOICE_CTRL_START_LISTEN);
}

rt_err_t voice_service_request_listen_stop(void)
{
    rt_kprintf("[voice_service] request listen stop\n");
    return voice_service_send_control(VOICE_CTRL_STOP_LISTEN);
}
