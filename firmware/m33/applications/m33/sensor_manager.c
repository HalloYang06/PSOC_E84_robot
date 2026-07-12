#include "sensor_manager.h"

static struct
{
    struct rt_mutex lock;
    sensor_data_t latest;
} g_sensor_mgr;

rt_err_t sensor_manager_init(void)
{
    rt_mutex_init(&g_sensor_mgr.lock, "sensor", RT_IPC_FLAG_PRIO);
    rt_memset(&g_sensor_mgr.latest, 0, sizeof(g_sensor_mgr.latest));
    return RT_EOK;
}

rt_err_t sensor_get_latest(sensor_data_t *data)
{
    if (data == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_sensor_mgr.lock, RT_WAITING_FOREVER);
    *data = g_sensor_mgr.latest;
    rt_mutex_release(&g_sensor_mgr.lock);
    return RT_EOK;
}

rt_err_t sensor_update_latest(const sensor_data_t *data)
{
    if (data == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_sensor_mgr.lock, RT_WAITING_FOREVER);
    g_sensor_mgr.latest = *data;
    rt_mutex_release(&g_sensor_mgr.lock);
    return RT_EOK;
}

void sensor_fill_demo_data(sensor_data_t *data, rt_tick_t tick)
{
    if (data == RT_NULL)
    {
        return;
    }

    data->shoulder_angle = 35.0f + (tick % 90);
    data->elbow_angle = 60.0f + ((tick / 2) % 70);
    data->lateral_position = 120.0f + ((tick / 3) % 120);
    data->shoulder_torque = 5.2f + (tick % 5) * 0.2f;
    data->elbow_torque = 4.0f + (tick % 7) * 0.15f;
    data->emg_ch1 = 0.8f + (tick % 10) * 0.08f;
    data->emg_ch2 = 0.6f + (tick % 8) * 0.07f;
    data->heart_rate = 72 + (tick % 8);
    data->spo2 = 98;
    data->accel_x = 12 + (tick % 4);
    data->accel_y = -5 + (tick % 3);
    data->accel_z = 1010;
    data->gyro_x = 2 + (tick % 2);
    data->gyro_y = -1;
    data->gyro_z = 8 + (tick % 4);
    data->timestamp = tick;
}
