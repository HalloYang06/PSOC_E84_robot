#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <rtthread.h>

typedef struct
{
    float shoulder_angle;
    float elbow_angle;
    float lateral_position;
    float shoulder_torque;
    float elbow_torque;
    float emg_ch1;
    float emg_ch2;
    rt_uint16_t heart_rate;
    rt_uint16_t spo2;
    rt_int16_t accel_x;
    rt_int16_t accel_y;
    rt_int16_t accel_z;
    rt_int16_t gyro_x;
    rt_int16_t gyro_y;
    rt_int16_t gyro_z;
    rt_tick_t timestamp;
} sensor_data_t;

rt_err_t sensor_manager_init(void);
rt_err_t sensor_get_latest(sensor_data_t *data);
rt_err_t sensor_update_latest(const sensor_data_t *data);
void sensor_fill_demo_data(sensor_data_t *data, rt_tick_t tick);

#endif
