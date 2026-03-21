#include "control_manager.h"

static control_status_t g_control_status;
static struct rt_mutex g_control_lock;

rt_err_t control_manager_init(void)
{
    rt_mutex_init(&g_control_lock, "ctrl", RT_IPC_FLAG_PRIO);
    rt_memset(&g_control_status, 0, sizeof(g_control_status));
    g_control_status.mode = CONTROL_MODE_PASSIVE;
    g_control_status.motion_enabled = RT_TRUE;
    return RT_EOK;
}

rt_err_t control_set_mode(control_mode_t mode)
{
    rt_mutex_take(&g_control_lock, RT_WAITING_FOREVER);
    g_control_status.mode = mode;
    rt_mutex_release(&g_control_lock);
    return RT_EOK;
}

rt_err_t control_move_joint(joint_id_t joint, float target)
{
    if (joint >= JOINT_MAX)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_control_lock, RT_WAITING_FOREVER);
    g_control_status.target_angles[joint] = target;
    rt_mutex_release(&g_control_lock);
    return RT_EOK;
}

rt_err_t control_get_status(control_status_t *status)
{
    if (status == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_control_lock, RT_WAITING_FOREVER);
    *status = g_control_status;
    rt_mutex_release(&g_control_lock);
    return RT_EOK;
}

rt_err_t control_apply_sensor_feedback(const sensor_data_t *data)
{
    if (data == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_control_lock, RT_WAITING_FOREVER);
    g_control_status.current_angles[JOINT_SHOULDER_VERTICAL] = data->shoulder_angle;
    g_control_status.current_angles[JOINT_ELBOW_VERTICAL] = data->elbow_angle;
    g_control_status.current_angles[JOINT_SHOULDER_LATERAL] = data->lateral_position;
    rt_mutex_release(&g_control_lock);
    return RT_EOK;
}
