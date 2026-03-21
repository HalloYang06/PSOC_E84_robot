#ifndef CONTROL_MANAGER_H
#define CONTROL_MANAGER_H

#include <rtthread.h>
#include "sensor_manager.h"

typedef enum
{
    CONTROL_MODE_PASSIVE = 0,
    CONTROL_MODE_ACTIVE,
    CONTROL_MODE_MEMORY,
    CONTROL_MODE_AI_ASSIST
} control_mode_t;

typedef enum
{
    JOINT_SHOULDER_VERTICAL = 0,
    JOINT_ELBOW_VERTICAL,
    JOINT_SHOULDER_LATERAL,
    JOINT_MAX
} joint_id_t;

typedef struct
{
    float current_angles[JOINT_MAX];
    float target_angles[JOINT_MAX];
    control_mode_t mode;
    rt_bool_t motion_enabled;
} control_status_t;

rt_err_t control_manager_init(void);
rt_err_t control_set_mode(control_mode_t mode);
rt_err_t control_move_joint(joint_id_t joint, float target);
rt_err_t control_get_status(control_status_t *status);
rt_err_t control_apply_sensor_feedback(const sensor_data_t *data);

#endif
