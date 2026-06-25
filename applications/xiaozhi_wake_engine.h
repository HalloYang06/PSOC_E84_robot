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
int xiaozhi_wake_engine_last_error(void);
int xiaozhi_wake_engine_stage(void);
int xiaozhi_wake_engine_last_confidence_permille(void);
int xiaozhi_wake_engine_threshold_permille(void);
int xiaozhi_wake_engine_set_threshold_permille(int threshold_permille);
int xiaozhi_wake_engine_last_noise_permille(void);
int xiaozhi_wake_engine_last_feature_source(void);
int xiaozhi_wake_engine_last_feature_error(void);
int xiaozhi_wake_engine_last_alloc_source(void);
int xiaozhi_wake_engine_last_alloc_size(void);
int xiaozhi_wake_engine_last_alloc_fail_source(void);
int xiaozhi_wake_engine_last_alloc_fail_size(void);
int xiaozhi_wake_engine_alloc_diag(void);

#endif
