#ifndef __OPENCLAW_INTEGRATION_H__
#define __OPENCLAW_INTEGRATION_H__

#include <rtthread.h>

#define OPENCLAW_JSON_SMALL 256
#define OPENCLAW_JSON_MEDIUM 512

typedef struct
{
    float shoulder_angle;
    float elbow_angle;
    float lateral_position;
    float shoulder_torque;
    float elbow_torque;
    float emg_ch1;
    float emg_ch2;
    float heart_rate;
    float spo2;
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    float temperature;
    float voltage;
    rt_bool_t hardware_ok;
} openclaw_sensor_snapshot_t;

typedef struct
{
    const char *name;
    const char *description;
    rt_err_t (*handler)(const char *body, char *response, rt_size_t response_size);
} openclaw_tool_t;

rt_err_t openclaw_integration_init(void);
rt_err_t openclaw_execute_tool(const char *tool_name, const char *body, char *response, rt_size_t response_size);
rt_size_t openclaw_build_status_json(char *buffer, rt_size_t size);
rt_size_t openclaw_build_sensors_json(char *buffer, rt_size_t size);
void openclaw_get_sensor_snapshot(openclaw_sensor_snapshot_t *snapshot);

#endif
