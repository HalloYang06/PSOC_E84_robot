#ifndef SAFETY_SYSTEM_H
#define SAFETY_SYSTEM_H

#include <rtthread.h>
#include "sensor_manager.h"

typedef enum
{
    SAFETY_STATE_SAFE = 0,
    SAFETY_STATE_WARNING,
    SAFETY_STATE_DANGER,
    SAFETY_STATE_EMERGENCY
} safety_state_t;

typedef struct
{
    float joint_angles[3];
    float joint_torques[3];
    rt_uint16_t heart_rate;
    float emg_ch1;
    float emg_ch2;
    rt_uint8_t spo2;
    safety_state_t safety_state;
    rt_uint8_t warning_count;
    float temperature;
    float voltage;
    rt_bool_t hardware_ok;
} safety_monitor_t;

rt_err_t safety_system_init(void);
rt_err_t safety_monitor_update(safety_monitor_t *monitor, const sensor_data_t *data);
safety_state_t safety_check_state(const safety_monitor_t *monitor);
const safety_monitor_t *safety_get_monitor_data(void);

#endif
