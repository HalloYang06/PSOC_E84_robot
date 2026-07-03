#ifndef M55_EMG_STREAM_BRIDGE_H
#define M55_EMG_STREAM_BRIDGE_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t m55_emg_stream_bridge_start(rt_uint16_t sample_period_ms,
                                     rt_bool_t start_f103_stream);
rt_err_t m55_emg_stream_bridge_stop(rt_bool_t stop_f103_stream);
rt_err_t m55_emg_stream_bridge_publish_once(void);

#ifdef __cplusplus
}
#endif

#endif
