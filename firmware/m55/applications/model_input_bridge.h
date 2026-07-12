#ifndef MODEL_INPUT_BRIDGE_H
#define MODEL_INPUT_BRIDGE_H

#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

void model_input_bridge_handle_message(const m33_m55_message_t *msg);

#ifdef __cplusplus
}
#endif

#endif
