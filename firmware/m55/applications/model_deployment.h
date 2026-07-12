#ifndef MODEL_DEPLOYMENT_H
#define MODEL_DEPLOYMENT_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t model_deployment_load_wake_word(rt_uint32_t arena_kb,
                                         rt_uint16_t threshold_permille);
rt_err_t model_deployment_run_silence(rt_bool_t publish_result);

#ifdef __cplusplus
}
#endif

#endif
