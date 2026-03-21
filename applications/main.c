#include <rtthread.h>
#include <rtdevice.h>
#include <board.h>

#include "common/m33_m55_comm.h"
#include "m33/bt_board_bridge.h"
#include "m33/app_ble_service.h"
#include "m33/bt_app_gatt_handler.h"
#include "m33/bt_hci_transport.h"
#include "m33/can_driver.h"
#include "m33/control_manager.h"
#include "m33/http_server.h"
#include "m33/input_buffer.h"
#include "m33/openclaw_integration.h"
#include "m33/safety_system.h"
#include "m33/sensor_manager.h"

#define LED_PIN_B GET_PIN(16, 5)
#define FRAME_PERIOD_MS 100

typedef struct
{
    rt_uint32_t loop_count;
    safety_monitor_t safety;
} m33_runtime_t;

static void m33_publish_sensor_snapshot(const sensor_data_t *sensor)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_SENSOR_SNAPSHOT;
    msg.payload.sensor_snapshot.emg_ch1 = sensor->emg_ch1;
    msg.payload.sensor_snapshot.emg_ch2 = sensor->emg_ch2;
    msg.payload.sensor_snapshot.heart_rate = sensor->heart_rate;
    msg.payload.sensor_snapshot.spo2 = sensor->spo2;
    msg.payload.sensor_snapshot.imu_data[0] = sensor->accel_x;
    msg.payload.sensor_snapshot.imu_data[1] = sensor->accel_y;
    msg.payload.sensor_snapshot.imu_data[2] = sensor->accel_z;
    msg.payload.sensor_snapshot.imu_data[3] = sensor->gyro_x;
    msg.payload.sensor_snapshot.imu_data[4] = sensor->gyro_y;
    msg.payload.sensor_snapshot.imu_data[5] = sensor->gyro_z;
    msg.payload.sensor_snapshot.shoulder_angle = sensor->shoulder_angle;
    msg.payload.sensor_snapshot.elbow_angle = sensor->elbow_angle;
    msg.payload.sensor_snapshot.lateral_position = sensor->lateral_position;
    msg.payload.sensor_snapshot.timestamp = sensor->timestamp;
    m33_m55_comm_publish(&msg);
}

static void m33_init_framework(void)
{
    rt_err_t bt_err;
    m33_m55_comm_init();
    bt_board_bridge_init();
    app_ble_service_init();
    app_ble_service_start();
    sensor_manager_init();
    input_buffer_init();
    control_manager_init();
    can_driver_init();
    safety_system_init();
    http_server_init();
    http_server_start();
    openclaw_integration_init();
    bt_err = bt_hci_transport_init();
    if (bt_err == RT_EOK)
    {
        bt_err = bt_hci_transport_start();
    }

    if (bt_err != RT_EOK)
    {
        rt_kprintf("[m33] bluetooth middleware not integrated yet, transport state=%d err=%d\n",
                   bt_hci_transport_get_runtime()->state,
                   bt_err);
    }
}

static void m33_handle_ble_command(void)
{
    app_ble_command_t cmd;

    if (app_ble_service_peek_command(&cmd) != RT_EOK)
    {
        return;
    }

    switch (cmd.type)
    {
    case APP_BLE_CMD_SET_MODE:
        (void)control_set_mode(cmd.mode);
        break;

    case APP_BLE_CMD_MOVE_JOINT:
        (void)control_move_joint(cmd.joint, cmd.target);
        break;

    case APP_BLE_CMD_EMERGENCY_STOP:
        (void)control_set_mode(CONTROL_MODE_PASSIVE);
        break;

    case APP_BLE_CMD_START_STREAM:
    case APP_BLE_CMD_STOP_STREAM:
    case APP_BLE_CMD_HEARTBEAT:
        break;

    default:
        break;
    }
}

static void m33_publish_ble_telemetry(const sensor_data_t *sensor,
                                      const control_status_t *control,
                                      const safety_monitor_t *safety)
{
    const app_ble_runtime_t *runtime;
    const char *payload;
    uint16_t payload_len;
    uint16_t offset;
    const uint16_t chunk_size = 20;  // MTU 23 - 3 bytes overhead

    (void)app_ble_service_update_telemetry(sensor, control, safety);
    runtime = app_ble_service_get_runtime();
    if ((runtime == RT_NULL) || !runtime->connected || !runtime->streaming_enabled)
    {
        return;
    }

    payload = app_ble_service_get_last_payload();
    if (payload == RT_NULL)
    {
        return;
    }

    payload_len = (uint16_t)rt_strlen(payload);

    // Send in chunks if needed
    for (offset = 0; offset < payload_len; offset += chunk_size)
    {
        uint16_t send_len = (payload_len - offset) > chunk_size ? chunk_size : (payload_len - offset);
        rt_err_t ret = bt_app_gatt_send((const uint8_t *)(payload + offset), send_len);
        if (ret != RT_EOK)
        {
            rt_kprintf("[ble] Send failed at offset %u\n", offset);
            break;
        }
        // Small delay between chunks to avoid buffer overflow
        if (offset + chunk_size < payload_len)
        {
            rt_thread_mdelay(5);
        }
    }
}

int main(void)
{
    m33_runtime_t runtime;
    sensor_data_t sensor;
    control_status_t control;

    rt_memset(&runtime, 0, sizeof(runtime));

    rt_kprintf("Hello RT-Thread\r\n");
    rt_kprintf("This core is cortex-m33\n");

    rt_pin_mode(LED_PIN_B, PIN_MODE_OUTPUT);
    m33_init_framework();
    control_set_mode(CONTROL_MODE_ACTIVE);

    rt_kprintf("[m33] System ready. Waiting for BLE connection...\n");
    rt_kprintf("[m33] Send 'stream:on' to start sensor data streaming\n");

    while (1)
    {
        sensor_fill_demo_data(&sensor, rt_tick_get());
        sensor_update_latest(&sensor);
        control_apply_sensor_feedback(&sensor);
        safety_monitor_update(&runtime.safety, &sensor);
        control_get_status(&control);
        m33_publish_sensor_snapshot(&sensor);
        m33_handle_ble_command();
        m33_publish_ble_telemetry(&sensor, &control, &runtime.safety);

        runtime.loop_count++;
        if ((runtime.loop_count % 10U) == 0U)
        {
            rt_pin_write(LED_PIN_B, PIN_HIGH);
        }
        else
        {
            rt_pin_write(LED_PIN_B, PIN_LOW);
        }

        rt_thread_mdelay(FRAME_PERIOD_MS);
    }

    return 0;
}


