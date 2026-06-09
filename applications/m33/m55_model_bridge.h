#ifndef M55_MODEL_BRIDGE_H
#define M55_MODEL_BRIDGE_H

#include "common/m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

void m55_model_bridge_init(void);
void m55_model_bridge_handle_message(const m33_m55_message_t *msg);
rt_bool_t m55_model_bridge_get_snapshot(rt_uint32_t *seq,
                                        rt_uint8_t *model_code,
                                        rt_uint8_t *result_code,
                                        rt_uint16_t *confidence_permille,
                                        rt_uint8_t *flags,
                                        rt_uint16_t *window_ms,
                                        rt_tick_t *timestamp);
rt_bool_t m55_model_bridge_get_voice_ack(rt_uint32_t *seq,
                                         rt_uint32_t *cmd,
                                         rt_int32_t *result,
                                         rt_uint32_t *m55_tick,
                                         rt_tick_t *timestamp);

#ifdef __cplusplus
}
#endif

#endif
