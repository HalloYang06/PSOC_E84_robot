#ifndef MODEL_RESULT_PUBLISHER_H
#define MODEL_RESULT_PUBLISHER_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    MODEL_RESULT_CODE_NONE = 0,
    MODEL_RESULT_CODE_WAKE_START_REQUEST = 1,
} model_result_code_t;

rt_err_t model_result_publish_wake_word(rt_uint16_t confidence_permille,
                                         rt_bool_t detected,
                                         rt_bool_t fresh,
                                         rt_uint16_t window_ms);

#ifdef __cplusplus
}
#endif

#endif
