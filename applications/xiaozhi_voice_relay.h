#ifndef XIAOZHI_VOICE_RELAY_H
#define XIAOZHI_VOICE_RELAY_H

#include <rtthread.h>
#include <stdint.h>

#define XIAOZHI_PROJECT_ID "e201f41c-25a6-46e1-baf8-be6dcb83284c"
#define XIAOZHI_DEVICE_ID  "nanopi-m5"
#define XIAOZHI_ROBOT_ID   "rehab-arm-alpha"
#define XIAOZHI_PROTOCOL_VERSION 1U
#ifndef XIAOZHI_USE_OFFICIAL_OPUS_AUDIO
#define XIAOZHI_USE_OFFICIAL_OPUS_AUDIO 1
#endif
#ifdef XIAOZHI_USE_OFFICIAL_OPUS_AUDIO
#define XIAOZHI_AUDIO_FORMAT "opus"
#else
#define XIAOZHI_AUDIO_FORMAT "pcm_s16le"
#endif
#define XIAOZHI_AUDIO_SAMPLE_RATE 16000U
#define XIAOZHI_AUDIO_CHANNELS 1U
#define XIAOZHI_AUDIO_BITS_PER_SAMPLE 16U
#define XIAOZHI_AUDIO_FRAME_DURATION_MS 60U
#define XIAOZHI_AUDIO_FRAME_BYTES \
    ((XIAOZHI_AUDIO_SAMPLE_RATE * XIAOZHI_AUDIO_CHANNELS * (XIAOZHI_AUDIO_BITS_PER_SAMPLE / 8U) * XIAOZHI_AUDIO_FRAME_DURATION_MS) / 1000U)

typedef enum
{
    XIAOZHI_UTTERANCE_UNKNOWN = 0,
    XIAOZHI_UTTERANCE_DAILY_CHAT,
    XIAOZHI_UTTERANCE_VLA_COMMAND
} xiaozhi_utterance_kind_t;

typedef enum
{
    XIAOZHI_WAKE_SOURCE_MANUAL = 0,
    XIAOZHI_WAKE_SOURCE_M55_LOCAL,
    XIAOZHI_WAKE_SOURCE_APP,
    XIAOZHI_WAKE_SOURCE_SERVER,
    XIAOZHI_WAKE_SOURCE_REALTIME
} xiaozhi_wake_source_t;

typedef struct
{
    xiaozhi_utterance_kind_t kind;
    char reply[256];
    char transcript[192];
    char language_context[256];
} xiaozhi_response_t;

rt_err_t xiaozhi_voice_relay_init(void);
const char *xiaozhi_voice_relay_get_url(void);
const char *xiaozhi_voice_relay_get_device_id(void);
const char *xiaozhi_voice_relay_get_client_id(void);
rt_bool_t xiaozhi_voice_relay_has_token(void);
rt_size_t xiaozhi_voice_relay_token_len(void);
rt_size_t xiaozhi_voice_relay_token_staging_len(void);
rt_err_t xiaozhi_voice_relay_set_url(const char *url);
rt_err_t xiaozhi_voice_relay_set_token(const char *token);
rt_err_t xiaozhi_voice_relay_token_update_begin(void);
rt_err_t xiaozhi_voice_relay_token_update_part(const char *chunk);
rt_err_t xiaozhi_voice_relay_token_update_commit(void);
void xiaozhi_voice_relay_token_update_clear(void);
rt_err_t xiaozhi_voice_relay_build_headers(char *out, rt_size_t out_len);
rt_err_t xiaozhi_voice_relay_build_hello(char *out, rt_size_t out_len);
rt_err_t xiaozhi_voice_relay_build_listen_detect(char *out, rt_size_t out_len,
                                                 const char *session_id,
                                                 const char *wake_word);
rt_err_t xiaozhi_voice_relay_build_listen_start(char *out, rt_size_t out_len,
                                                const char *session_id,
                                                xiaozhi_wake_source_t wake_source);
rt_err_t xiaozhi_voice_relay_build_listen_stop(char *out, rt_size_t out_len,
                                               const char *session_id,
                                               xiaozhi_wake_source_t wake_source,
                                               rt_uint32_t total_bytes,
                                               rt_uint32_t chunks);
rt_bool_t xiaozhi_voice_relay_parse_response(const char *json,
                                             xiaozhi_response_t *response);

#endif
