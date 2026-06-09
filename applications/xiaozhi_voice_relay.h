#ifndef XIAOZHI_VOICE_RELAY_H
#define XIAOZHI_VOICE_RELAY_H

#include <rtthread.h>
#include <stdint.h>

#define XIAOZHI_PROJECT_ID "fd6a55ed-a63c-44b3-b123-96fb3c154966"
#define XIAOZHI_DEVICE_ID  "nanopi-m5"
#define XIAOZHI_ROBOT_ID   "rehab-arm-alpha"

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
    XIAOZHI_WAKE_SOURCE_SERVER
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
rt_bool_t xiaozhi_voice_relay_has_token(void);
rt_err_t xiaozhi_voice_relay_set_url(const char *url);
rt_err_t xiaozhi_voice_relay_set_token(const char *token);
rt_err_t xiaozhi_voice_relay_build_headers(char *out, rt_size_t out_len);
rt_err_t xiaozhi_voice_relay_build_hello(char *out, rt_size_t out_len);
rt_err_t xiaozhi_voice_relay_build_listen_detect(char *out, rt_size_t out_len,
                                                 rt_uint32_t session_id,
                                                 const char *wake_word);
rt_err_t xiaozhi_voice_relay_build_listen_start(char *out, rt_size_t out_len,
                                                rt_uint32_t session_id,
                                                xiaozhi_wake_source_t wake_source);
rt_err_t xiaozhi_voice_relay_build_listen_stop(char *out, rt_size_t out_len,
                                               rt_uint32_t session_id,
                                               rt_uint32_t total_bytes,
                                               rt_uint32_t chunks);
rt_bool_t xiaozhi_voice_relay_parse_response(const char *json,
                                             xiaozhi_response_t *response);

#endif
