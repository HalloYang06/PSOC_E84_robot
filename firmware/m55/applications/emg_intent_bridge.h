#ifndef EMG_INTENT_BRIDGE_H
#define EMG_INTENT_BRIDGE_H

#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t emg_intent_bridge_init(void);
rt_err_t emg_intent_bridge_handle_stream(const sensor_stream_msg_t *stream);

#ifdef __cplusplus
}
#endif

#endif
