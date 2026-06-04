#ifndef M55_MODEL_BRIDGE_H
#define M55_MODEL_BRIDGE_H

#include "common/m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

void m55_model_bridge_init(void);
void m55_model_bridge_handle_message(const m33_m55_message_t *msg);

#ifdef __cplusplus
}
#endif

#endif
