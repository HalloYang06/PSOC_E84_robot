#ifndef M55_MODEL_BRIDGE_H
#define M55_MODEL_BRIDGE_H

#include "common/m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    voice_latency_msg_t latency;
    rt_uint32_t ipc_seq;
    rt_tick_t received_tick;
    rt_uint32_t received_count;
    rt_uint32_t accepted_count;
    rt_uint32_t invalid_count;
    rt_uint32_t stale_count;
    rt_uint32_t dropped_count;
} m55_voice_latency_snapshot_t;

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
rt_bool_t m55_model_bridge_get_voice_status(voice_status_msg_t *status,
                                            rt_uint32_t *seq,
                                            rt_tick_t *timestamp);
rt_bool_t m55_model_bridge_get_voice_latency(m55_voice_latency_snapshot_t *snapshot);

#ifdef __cplusplus
}
#endif

#endif
