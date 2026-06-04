#ifndef M55_MODEL_INPUT_BRIDGE_H
#define M55_MODEL_INPUT_BRIDGE_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t m55_model_input_bridge_publish_snapshot(float emg_ch1,
                                                 float emg_ch2,
                                                 rt_uint16_t heart_rate,
                                                 rt_uint16_t spo2,
                                                 float shoulder_angle,
                                                 float elbow_angle,
                                                 float lateral_position);

#ifdef __cplusplus
}
#endif

#endif
