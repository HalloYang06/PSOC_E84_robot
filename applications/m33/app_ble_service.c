#include "app_ble_service.h"

#include <stdio.h>
#include <string.h>

static struct
{
    struct rt_mutex lock;
    app_ble_runtime_t runtime;
    app_ble_command_t last_command;
    rt_bool_t has_command;
    rt_bool_t initialized;
    char last_payload[256];
} g_app_ble;

static control_mode_t app_ble_parse_mode_token(const char *token)
{
    if (token == RT_NULL)
    {
        return CONTROL_MODE_PASSIVE;
    }
    if (strcmp(token, "active") == 0)
    {
        return CONTROL_MODE_ACTIVE;
    }
    if (strcmp(token, "memory") == 0)
    {
        return CONTROL_MODE_MEMORY;
    }
    if (strcmp(token, "ai") == 0 || strcmp(token, "ai_assist") == 0)
    {
        return CONTROL_MODE_AI_ASSIST;
    }
    return CONTROL_MODE_PASSIVE;
}

rt_err_t app_ble_service_init(void)
{
    if (g_app_ble.initialized)
    {
        return RT_EOK;
    }

    if (rt_mutex_init(&g_app_ble.lock, "bleapp", RT_IPC_FLAG_PRIO) != RT_EOK)
    {
        return -RT_ERROR;
    }

    rt_memset(&g_app_ble.runtime, 0, sizeof(g_app_ble.runtime));
    rt_memset(&g_app_ble.last_command, 0, sizeof(g_app_ble.last_command));
    rt_memset(g_app_ble.last_payload, 0, sizeof(g_app_ble.last_payload));
    rt_strncpy(g_app_ble.last_payload, "{}", sizeof(g_app_ble.last_payload) - 1);
    g_app_ble.initialized = RT_TRUE;
    return RT_EOK;
}

rt_err_t app_ble_service_start(void)
{
    rt_mutex_take(&g_app_ble.lock, RT_WAITING_FOREVER);
    g_app_ble.runtime.connected = RT_FALSE;
    g_app_ble.runtime.streaming_enabled = RT_FALSE;
    rt_mutex_release(&g_app_ble.lock);
    return RT_EOK;
}

rt_err_t app_ble_service_set_link_state(rt_bool_t connected, rt_bool_t streaming_enabled)
{
    rt_mutex_take(&g_app_ble.lock, RT_WAITING_FOREVER);
    rt_bool_t was_connected = g_app_ble.runtime.connected;
    g_app_ble.runtime.connected = connected;
    g_app_ble.runtime.streaming_enabled = streaming_enabled;
    rt_mutex_release(&g_app_ble.lock);

    if (connected && !was_connected)
    {
        rt_kprintf("[ble] Connected! Send 'stream:on' to start data streaming\n");
    }
    else if (!connected && was_connected)
    {
        rt_kprintf("[ble] Disconnected\n");
    }

    return RT_EOK;
}

rt_err_t app_ble_service_parse_ascii_frame(const char *frame, app_ble_command_t *cmd)
{
    char mode_token[24] = {0};
    int joint = 0;
    float target = 0.0f;

    if (frame == RT_NULL || cmd == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_memset(cmd, 0, sizeof(*cmd));
    cmd->timestamp = rt_tick_get();

    if (rt_strncmp(frame, "stop", 4) == 0)
    {
        cmd->type = APP_BLE_CMD_EMERGENCY_STOP;
        return RT_EOK;
    }
    if (rt_strncmp(frame, "stream:on", 9) == 0)
    {
        cmd->type = APP_BLE_CMD_START_STREAM;
        return RT_EOK;
    }
    if (rt_strncmp(frame, "stream:off", 10) == 0)
    {
        cmd->type = APP_BLE_CMD_STOP_STREAM;
        return RT_EOK;
    }
    if (rt_strncmp(frame, "heartbeat", 9) == 0)
    {
        cmd->type = APP_BLE_CMD_HEARTBEAT;
        return RT_EOK;
    }
    if (sscanf(frame, "mode:%23s", mode_token) == 1)
    {
        cmd->type = APP_BLE_CMD_SET_MODE;
        cmd->mode = app_ble_parse_mode_token(mode_token);
        return RT_EOK;
    }
    if (sscanf(frame, "move:%d:%f", &joint, &target) == 2)
    {
        cmd->type = APP_BLE_CMD_MOVE_JOINT;
        cmd->joint = (joint_id_t)joint;
        cmd->target = target;
        return RT_EOK;
    }

    return -RT_ERROR;
}

rt_err_t app_ble_service_submit_command(const app_ble_command_t *cmd)
{
    if (cmd == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_app_ble.lock, RT_WAITING_FOREVER);
    g_app_ble.last_command = *cmd;
    g_app_ble.has_command = RT_TRUE;
    g_app_ble.runtime.downlink_packets++;
    g_app_ble.runtime.last_command_tick = cmd->timestamp;
    if (cmd->type == APP_BLE_CMD_START_STREAM)
    {
        g_app_ble.runtime.streaming_enabled = RT_TRUE;
    }
    else if (cmd->type == APP_BLE_CMD_STOP_STREAM)
    {
        g_app_ble.runtime.streaming_enabled = RT_FALSE;
    }
    rt_mutex_release(&g_app_ble.lock);
    return RT_EOK;
}

rt_err_t app_ble_service_peek_command(app_ble_command_t *cmd)
{
    if (cmd == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_app_ble.lock, RT_WAITING_FOREVER);
    if (!g_app_ble.has_command)
    {
        rt_mutex_release(&g_app_ble.lock);
        return -RT_EEMPTY;
    }

    *cmd = g_app_ble.last_command;
    g_app_ble.has_command = RT_FALSE;
    rt_mutex_release(&g_app_ble.lock);
    return RT_EOK;
}

rt_err_t app_ble_service_update_telemetry(const sensor_data_t *sensor,
                                          const control_status_t *control,
                                          const safety_monitor_t *safety)
{
    if (sensor == RT_NULL || control == RT_NULL || safety == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_app_ble.lock, RT_WAITING_FOREVER);
    rt_snprintf(g_app_ble.last_payload, sizeof(g_app_ble.last_payload),
                "{\"s\":%d,\"m\":%d,\"sh\":%.1f,\"el\":%.1f,\"la\":%.1f,\"hr\":%u,\"sp\":%u,\"e1\":%.2f,\"e2\":%.2f,\"sf\":%d}\n",
                g_app_ble.runtime.streaming_enabled,
                control->mode,
                sensor->shoulder_angle,
                sensor->elbow_angle,
                sensor->lateral_position,
                sensor->heart_rate,
                sensor->spo2,
                sensor->emg_ch1,
                sensor->emg_ch2,
                safety->safety_state);
    g_app_ble.runtime.uplink_packets++;
    rt_mutex_release(&g_app_ble.lock);
    return RT_EOK;
}

const char *app_ble_service_get_last_payload(void)
{
    return g_app_ble.last_payload;
}

const app_ble_runtime_t *app_ble_service_get_runtime(void)
{
    return &g_app_ble.runtime;
}

