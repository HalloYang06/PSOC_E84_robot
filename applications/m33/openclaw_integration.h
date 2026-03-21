#ifndef OPENCLAW_INTEGRATION_H
#define OPENCLAW_INTEGRATION_H

#include <rtthread.h>
#include "sensor_manager.h"
#include "control_manager.h"

rt_err_t openclaw_integration_init(void);
rt_err_t openclaw_handle_set_mode(control_mode_t mode);
rt_err_t openclaw_handle_move_joint(joint_id_t joint, float target);
const char *openclaw_handle_get_sensor_data(void);

#endif
