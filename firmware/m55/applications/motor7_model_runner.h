#ifndef MOTOR7_MODEL_RUNNER_H
#define MOTOR7_MODEL_RUNNER_H

#include "m33_m55_comm.h"

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t motor7_model_runner_run_snapshot(const sensor_snapshot_msg_t *snapshot);

#ifdef __cplusplus
}
#endif

#endif
