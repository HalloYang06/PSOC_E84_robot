#ifndef APP_BLE_SERVICE_H
#define APP_BLE_SERVICE_H

#include <rtthread.h>
#include "sensor_manager.h"
#include "control_manager.h"
#include "safety_system.h"

#ifdef __cplusplus
extern "C" {
#endif

#define APP_BLE_COMMAND_QUEUE_DEPTH 8U

typedef enum
{
    APP_BLE_CMD_NONE = 0,
    APP_BLE_CMD_SET_MODE,
    APP_BLE_CMD_MOVE_JOINT,
    APP_BLE_CMD_EMERGENCY_STOP,
    APP_BLE_CMD_START_STREAM,
    APP_BLE_CMD_STOP_STREAM,
    APP_BLE_CMD_HEARTBEAT
} app_ble_cmd_type_t;

typedef struct
{
    app_ble_cmd_type_t type;
    control_mode_t mode;
    joint_id_t joint;
    float target;
    rt_tick_t timestamp;
} app_ble_command_t;

typedef struct
{
    rt_bool_t streaming_enabled;
    rt_bool_t connected;
    rt_uint32_t uplink_packets;
    rt_uint32_t downlink_packets;
    rt_uint32_t dropped_commands;
    rt_tick_t last_command_tick;
    rt_uint8_t queued_commands;
} app_ble_runtime_t;

rt_err_t app_ble_service_init(void);
rt_err_t app_ble_service_start(void);
rt_err_t app_ble_service_set_link_state(rt_bool_t connected, rt_bool_t streaming_enabled);
rt_err_t app_ble_service_parse_ascii_frame(const char *frame, app_ble_command_t *cmd);
rt_err_t app_ble_service_submit_command(const app_ble_command_t *cmd);
rt_err_t app_ble_service_peek_command(app_ble_command_t *cmd);
rt_err_t app_ble_service_update_telemetry(const sensor_data_t *sensor,
                                          const control_status_t *control,
                                          const safety_monitor_t *safety);
const char *app_ble_service_get_last_payload(void);
const app_ble_runtime_t *app_ble_service_get_runtime(void);

#ifdef __cplusplus
}
#endif

#endif

