#include "openclaw_integration.h"

#include <rtdevice.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

#define DBG_TAG "openclaw"
#define DBG_LVL DBG_INFO
#include <rtdbg.h>

typedef enum
{
    OPENCLAW_MODE_IDLE = 0,
    OPENCLAW_MODE_ACTIVE,
    OPENCLAW_MODE_ASSIST,
    OPENCLAW_MODE_MEMORY,
    OPENCLAW_MODE_EMERGENCY,
} openclaw_mode_t;

typedef struct
{
    openclaw_mode_t mode;
    rt_bool_t emergency_stop;
    rt_uint32_t uptime_boot_ms;
    rt_uint32_t command_count;
    rt_uint32_t last_command_ms;
    char last_tool[32];
    openclaw_sensor_snapshot_t sensors;
} openclaw_runtime_t;

static openclaw_runtime_t g_openclaw;
static struct rt_mutex g_openclaw_lock;

static int json_append(char *buffer, rt_size_t size, rt_size_t *offset, const char *fmt, ...)
{
    int written;
    va_list args;

    if (*offset >= size)
    {
        return -RT_EFULL;
    }

    va_start(args, fmt);
    written = rt_vsnprintf(buffer + *offset, size - *offset, fmt, args);
    va_end(args);

    if (written < 0)
    {
        return written;
    }

    if ((rt_size_t)written >= size - *offset)
    {
        *offset = size;
        return -RT_ENOMEM;
    }

    *offset += (rt_size_t)written;
    return RT_EOK;
}

static int json_append_float(char *buffer, rt_size_t size, rt_size_t *offset, float value, int decimals)
{
    long scale = 1;
    long whole;
    long frac;
    int i;

    if (value < 0)
    {
        if (json_append(buffer, size, offset, "-") != RT_EOK)
        {
            return -RT_ENOMEM;
        }
        value = -value;
    }

    for (i = 0; i < decimals; i++)
    {
        scale *= 10;
    }

    whole = (long)value;
    frac = (long)((value - (float)whole) * (float)scale + 0.5f);
    if (frac >= scale)
    {
        whole += 1;
        frac -= scale;
    }

    if (decimals <= 0)
    {
        return json_append(buffer, size, offset, "%ld", whole);
    }

    return json_append(buffer, size, offset, "%ld.%0*ld", whole, decimals, frac);
}

static const char *mode_to_string(openclaw_mode_t mode)
{
    switch (mode)
    {
    case OPENCLAW_MODE_ACTIVE:
        return "active";
    case OPENCLAW_MODE_ASSIST:
        return "assist";
    case OPENCLAW_MODE_MEMORY:
        return "memory";
    case OPENCLAW_MODE_EMERGENCY:
        return "emergency";
    case OPENCLAW_MODE_IDLE:
    default:
        return "idle";
    }
}

static openclaw_mode_t parse_mode(const char *name)
{
    if (!name)
    {
        return OPENCLAW_MODE_IDLE;
    }
    if (rt_strcmp(name, "active") == 0)
    {
        return OPENCLAW_MODE_ACTIVE;
    }
    if (rt_strcmp(name, "assist") == 0)
    {
        return OPENCLAW_MODE_ASSIST;
    }
    if (rt_strcmp(name, "memory") == 0)
    {
        return OPENCLAW_MODE_MEMORY;
    }
    if (rt_strcmp(name, "emergency") == 0)
    {
        return OPENCLAW_MODE_EMERGENCY;
    }
    return OPENCLAW_MODE_IDLE;
}

static const char *find_json_key(const char *body, const char *key)
{
    static char pattern[48];

    rt_snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    return rt_strstr(body, pattern);
}

static rt_bool_t json_get_string(const char *body, const char *key, char *out, rt_size_t out_size)
{
    const char *cursor;
    const char *start;
    const char *end;
    rt_size_t len;

    if (!body || !key || !out || out_size == 0)
    {
        return RT_FALSE;
    }

    cursor = find_json_key(body, key);
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }
    cursor++;
    while (*cursor == ' ' || *cursor == '\t')
    {
        cursor++;
    }
    if (*cursor != '"')
    {
        return RT_FALSE;
    }

    start = ++cursor;
    end = strchr(start, '"');
    if (!end)
    {
        return RT_FALSE;
    }

    len = (rt_size_t)(end - start);
    if (len >= out_size)
    {
        len = out_size - 1;
    }

    rt_memcpy(out, start, len);
    out[len] = '\0';
    return RT_TRUE;
}

static rt_bool_t json_get_number(const char *body, const char *key, float *out)
{
    const char *cursor;
    char tmp[32];
    rt_size_t len = 0;

    if (!body || !key || !out)
    {
        return RT_FALSE;
    }

    cursor = find_json_key(body, key);
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }
    cursor++;
    while (*cursor == ' ' || *cursor == '\t')
    {
        cursor++;
    }

    while (*cursor && len < sizeof(tmp) - 1)
    {
        if (((*cursor >= '0') && (*cursor <= '9')) || *cursor == '-' || *cursor == '+' || *cursor == '.')
        {
            tmp[len++] = *cursor++;
            continue;
        }
        break;
    }

    if (len == 0)
    {
        return RT_FALSE;
    }

    tmp[len] = '\0';
    *out = (float)atof(tmp);
    return RT_TRUE;
}

static void refresh_sensor_snapshot(openclaw_sensor_snapshot_t *snapshot)
{
    rt_tick_t now = rt_tick_get();
    float phase = (float)(now % (RT_TICK_PER_SECOND * 20)) / (float)RT_TICK_PER_SECOND;

    snapshot->shoulder_angle = 35.0f + phase * 3.0f;
    snapshot->elbow_angle = 70.0f + phase * 2.0f;
    snapshot->lateral_position = 12.0f + phase * 0.5f;
    snapshot->shoulder_torque = 0.45f + phase * 0.01f;
    snapshot->elbow_torque = 0.62f + phase * 0.01f;
    snapshot->emg_ch1 = 110.0f + phase * 4.0f;
    snapshot->emg_ch2 = 95.0f + phase * 5.0f;
    snapshot->heart_rate = 74.0f + phase * 0.6f;
    snapshot->spo2 = 98.0f;
    snapshot->accel_x = 0.02f + phase * 0.01f;
    snapshot->accel_y = -0.01f + phase * 0.01f;
    snapshot->accel_z = 1.00f;
    snapshot->gyro_x = 0.10f + phase * 0.02f;
    snapshot->gyro_y = 0.05f + phase * 0.02f;
    snapshot->gyro_z = -0.03f + phase * 0.02f;
    snapshot->temperature = 33.8f;
    snapshot->voltage = 7.4f;
    snapshot->hardware_ok = RT_TRUE;
}

void openclaw_get_sensor_snapshot(openclaw_sensor_snapshot_t *snapshot)
{
    if (!snapshot)
    {
        return;
    }

    rt_mutex_take(&g_openclaw_lock, RT_WAITING_FOREVER);
    refresh_sensor_snapshot(&g_openclaw.sensors);
    *snapshot = g_openclaw.sensors;
    rt_mutex_release(&g_openclaw_lock);
}

static void stamp_command(const char *tool_name)
{
    g_openclaw.command_count++;
    g_openclaw.last_command_ms = rt_tick_get_millisecond();
    rt_strncpy(g_openclaw.last_tool, tool_name, sizeof(g_openclaw.last_tool) - 1);
    g_openclaw.last_tool[sizeof(g_openclaw.last_tool) - 1] = '\0';
}

static rt_err_t tool_move_joint(const char *body, char *response, rt_size_t response_size)
{
    char joint[24] = "shoulder";
    float angle = 0.0f;

    json_get_string(body, "joint", joint, sizeof(joint));
    json_get_number(body, "angle", &angle);

    rt_mutex_take(&g_openclaw_lock, RT_WAITING_FOREVER);
    if (rt_strcmp(joint, "shoulder") == 0)
    {
        g_openclaw.sensors.shoulder_angle = angle;
    }
    else if (rt_strcmp(joint, "elbow") == 0)
    {
        g_openclaw.sensors.elbow_angle = angle;
    }
    else if (rt_strcmp(joint, "lateral") == 0)
    {
        g_openclaw.sensors.lateral_position = angle;
    }
    stamp_command("move_joint");
    rt_mutex_release(&g_openclaw_lock);

    {
        rt_size_t offset = 0;
        json_append(response, response_size, &offset, "{\"ok\":true,\"tool\":\"move_joint\",\"joint\":\"%s\",\"target\":", joint);
        json_append_float(response, response_size, &offset, angle, 2);
        json_append(response, response_size, &offset, "}");
    }
    return RT_EOK;
}

static rt_err_t tool_set_mode(const char *body, char *response, rt_size_t response_size)
{
    char mode_name[24] = "idle";

    json_get_string(body, "mode", mode_name, sizeof(mode_name));

    rt_mutex_take(&g_openclaw_lock, RT_WAITING_FOREVER);
    g_openclaw.mode = parse_mode(mode_name);
    if (g_openclaw.mode != OPENCLAW_MODE_EMERGENCY)
    {
        g_openclaw.emergency_stop = RT_FALSE;
    }
    stamp_command("set_mode");
    rt_mutex_release(&g_openclaw_lock);

    rt_snprintf(response, response_size,
                "{\"ok\":true,\"tool\":\"set_mode\",\"mode\":\"%s\"}",
                mode_to_string(parse_mode(mode_name)));
    return RT_EOK;
}

static rt_err_t tool_emergency_stop(const char *body, char *response, rt_size_t response_size)
{
    RT_UNUSED(body);

    rt_mutex_take(&g_openclaw_lock, RT_WAITING_FOREVER);
    g_openclaw.mode = OPENCLAW_MODE_EMERGENCY;
    g_openclaw.emergency_stop = RT_TRUE;
    stamp_command("emergency_stop");
    rt_mutex_release(&g_openclaw_lock);

    rt_snprintf(response, response_size,
                "{\"ok\":true,\"tool\":\"emergency_stop\",\"state\":\"latched\"}");
    return RT_EOK;
}

static rt_err_t tool_get_sensor_data(const char *body, char *response, rt_size_t response_size)
{
    RT_UNUSED(body);
    openclaw_build_sensors_json(response, response_size);
    return RT_EOK;
}

static rt_err_t tool_get_status(const char *body, char *response, rt_size_t response_size)
{
    RT_UNUSED(body);
    openclaw_build_status_json(response, response_size);
    return RT_EOK;
}

static const openclaw_tool_t g_tools[] = {
    {"move_joint", "Move one joint to a target angle", tool_move_joint},
    {"set_mode", "Switch rehab arm working mode", tool_set_mode},
    {"emergency_stop", "Trigger emergency stop", tool_emergency_stop},
    {"get_sensor_data", "Read current sensor snapshot", tool_get_sensor_data},
    {"get_status", "Read current controller status", tool_get_status},
    {RT_NULL, RT_NULL, RT_NULL}
};

rt_size_t openclaw_build_status_json(char *buffer, rt_size_t size)
{
    rt_size_t written;

    rt_mutex_take(&g_openclaw_lock, RT_WAITING_FOREVER);
    written = (rt_size_t)rt_snprintf(buffer, size,
                                     "{\"mode\":\"%s\",\"emergency_stop\":%s,\"hardware_ok\":%s,"
                                     "\"uptime_ms\":%lu,\"command_count\":%lu,\"last_command_ms\":%lu,\"last_tool\":\"%s\"}",
                                     mode_to_string(g_openclaw.mode),
                                     g_openclaw.emergency_stop ? "true" : "false",
                                     g_openclaw.sensors.hardware_ok ? "true" : "false",
                                     (unsigned long)(rt_tick_get_millisecond() - g_openclaw.uptime_boot_ms),
                                     (unsigned long)g_openclaw.command_count,
                                     (unsigned long)g_openclaw.last_command_ms,
                                     g_openclaw.last_tool);
    rt_mutex_release(&g_openclaw_lock);

    return written;
}

rt_size_t openclaw_build_sensors_json(char *buffer, rt_size_t size)
{
    openclaw_sensor_snapshot_t snapshot;
    rt_size_t offset = 0;

    openclaw_get_sensor_snapshot(&snapshot);

    json_append(buffer, size, &offset, "{\"shoulder_angle\":");
    json_append_float(buffer, size, &offset, snapshot.shoulder_angle, 2);
    json_append(buffer, size, &offset, ",\"elbow_angle\":");
    json_append_float(buffer, size, &offset, snapshot.elbow_angle, 2);
    json_append(buffer, size, &offset, ",\"lateral_position\":");
    json_append_float(buffer, size, &offset, snapshot.lateral_position, 2);
    json_append(buffer, size, &offset, ",\"shoulder_torque\":");
    json_append_float(buffer, size, &offset, snapshot.shoulder_torque, 2);
    json_append(buffer, size, &offset, ",\"elbow_torque\":");
    json_append_float(buffer, size, &offset, snapshot.elbow_torque, 2);
    json_append(buffer, size, &offset, ",\"emg_ch1\":");
    json_append_float(buffer, size, &offset, snapshot.emg_ch1, 2);
    json_append(buffer, size, &offset, ",\"emg_ch2\":");
    json_append_float(buffer, size, &offset, snapshot.emg_ch2, 2);
    json_append(buffer, size, &offset, ",\"heart_rate\":");
    json_append_float(buffer, size, &offset, snapshot.heart_rate, 2);
    json_append(buffer, size, &offset, ",\"spo2\":");
    json_append_float(buffer, size, &offset, snapshot.spo2, 2);
    json_append(buffer, size, &offset, ",\"accel\":{\"x\":");
    json_append_float(buffer, size, &offset, snapshot.accel_x, 3);
    json_append(buffer, size, &offset, ",\"y\":");
    json_append_float(buffer, size, &offset, snapshot.accel_y, 3);
    json_append(buffer, size, &offset, ",\"z\":");
    json_append_float(buffer, size, &offset, snapshot.accel_z, 3);
    json_append(buffer, size, &offset, "},\"gyro\":{\"x\":");
    json_append_float(buffer, size, &offset, snapshot.gyro_x, 3);
    json_append(buffer, size, &offset, ",\"y\":");
    json_append_float(buffer, size, &offset, snapshot.gyro_y, 3);
    json_append(buffer, size, &offset, ",\"z\":");
    json_append_float(buffer, size, &offset, snapshot.gyro_z, 3);
    json_append(buffer, size, &offset, "},\"temperature\":");
    json_append_float(buffer, size, &offset, snapshot.temperature, 2);
    json_append(buffer, size, &offset, ",\"voltage\":");
    json_append_float(buffer, size, &offset, snapshot.voltage, 2);
    json_append(buffer, size, &offset, ",\"hardware_ok\":%s}", snapshot.hardware_ok ? "true" : "false");

    return offset;
}

rt_err_t openclaw_execute_tool(const char *tool_name, const char *body, char *response, rt_size_t response_size)
{
    int i;

    if (!tool_name || !response || response_size == 0)
    {
        return -RT_EINVAL;
    }

    for (i = 0; g_tools[i].name != RT_NULL; i++)
    {
        if (rt_strcmp(g_tools[i].name, tool_name) == 0)
        {
            return g_tools[i].handler(body ? body : "", response, response_size);
        }
    }

    rt_snprintf(response, response_size,
                "{\"ok\":false,\"error\":\"unknown_tool\",\"tool\":\"%s\"}",
                tool_name);
    return -RT_ENOSYS;
}

rt_err_t openclaw_integration_init(void)
{
    rt_err_t ret;

    ret = rt_mutex_init(&g_openclaw_lock, "oclaw", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(&g_openclaw, 0, sizeof(g_openclaw));
    g_openclaw.mode = OPENCLAW_MODE_IDLE;
    g_openclaw.uptime_boot_ms = rt_tick_get_millisecond();
    rt_strcpy(g_openclaw.last_tool, "boot");
    refresh_sensor_snapshot(&g_openclaw.sensors);

    LOG_I("OpenClaw integration initialized with %d tools", (int)(sizeof(g_tools) / sizeof(g_tools[0]) - 1));
    return RT_EOK;
}
