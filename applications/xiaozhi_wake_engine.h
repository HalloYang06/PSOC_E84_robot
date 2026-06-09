#ifndef XIAOZHI_WAKE_ENGINE_H
#define XIAOZHI_WAKE_ENGINE_H

#include <rtthread.h>
#include <stdint.h>

typedef enum
{
    XIAOZHI_WAKE_EVENT_NONE = 0,
    XIAOZHI_WAKE_EVENT_DETECTED,
    XIAOZHI_WAKE_EVENT_ERROR,
    XIAOZHI_WAKE_EVENT_UNAVAILABLE
} xiaozhi_wake_event_t;

typedef struct
{
    xiaozhi_wake_event_t event;
    char wake_word[48];
    int error_code;
} xiaozhi_wake_result_t;

rt_err_t xiaozhi_wake_engine_init(void);
rt_bool_t xiaozhi_wake_engine_is_ready(void);
rt_err_t xiaozhi_wake_engine_process_pcm16(const int16_t *pcm,
                                           rt_uint32_t sample_count,
                                           xiaozhi_wake_result_t *result);
const char *xiaozhi_wake_engine_backend_name(void);

#endif
