#include "safety_system.h"

static safety_monitor_t g_safety_monitor;

rt_err_t safety_system_init(void)
{
    rt_memset(&g_safety_monitor, 0, sizeof(g_safety_monitor));
    g_safety_monitor.hardware_ok = RT_TRUE;
    g_safety_monitor.voltage = 12.0f;
    g_safety_monitor.temperature = 30.0f;
    return RT_EOK;
}

rt_err_t safety_monitor_update(safety_monitor_t *monitor, const sensor_data_t *data)
{
    if (monitor == RT_NULL || data == RT_NULL)
    {
        return -RT_ERROR;
    }

    monitor->joint_angles[0] = data->shoulder_angle;
    monitor->joint_angles[1] = data->elbow_angle;
    monitor->joint_angles[2] = data->lateral_position;
    monitor->joint_torques[0] = data->shoulder_torque;
    monitor->joint_torques[1] = data->elbow_torque;
    monitor->heart_rate = data->heart_rate;
    monitor->emg_ch1 = data->emg_ch1;
    monitor->emg_ch2 = data->emg_ch2;
    monitor->spo2 = (rt_uint8_t)data->spo2;
    monitor->safety_state = safety_check_state(monitor);
    monitor->warning_count = (monitor->safety_state == SAFETY_STATE_SAFE) ? 0 : 1;
    g_safety_monitor = *monitor;
    return RT_EOK;
}

safety_state_t safety_check_state(const safety_monitor_t *monitor)
{
    if (monitor == RT_NULL)
    {
        return SAFETY_STATE_EMERGENCY;
    }

    if (monitor->heart_rate > 150 || monitor->heart_rate < 50)
    {
        return SAFETY_STATE_DANGER;
    }
    if (monitor->emg_ch1 > 4.0f || monitor->emg_ch2 > 4.0f)
    {
        return SAFETY_STATE_WARNING;
    }
    return SAFETY_STATE_SAFE;
}

const safety_monitor_t *safety_get_monitor_data(void)
{
    return &g_safety_monitor;
}
