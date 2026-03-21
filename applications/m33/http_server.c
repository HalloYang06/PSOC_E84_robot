#include "http_server.h"

static char g_http_status_json[256];

rt_err_t http_server_init(void)
{
    rt_strncpy(g_http_status_json, "{}", sizeof(g_http_status_json) - 1);
    return RT_EOK;
}

rt_err_t http_server_start(void)
{
    return RT_EOK;
}

const char *http_server_build_status_json(const sensor_data_t *sensor, const control_status_t *control)
{
    if (sensor == RT_NULL || control == RT_NULL)
    {
        return "{}";
    }

    rt_snprintf(g_http_status_json, sizeof(g_http_status_json),
                "{\"shoulder_angle\":%.1f,\"elbow_angle\":%.1f,\"emg_ch1\":%.2f,\"emg_ch2\":%.2f,\"heart_rate\":%u,\"spo2\":%u,\"mode\":%d}",
                sensor->shoulder_angle,
                sensor->elbow_angle,
                sensor->emg_ch1,
                sensor->emg_ch2,
                sensor->heart_rate,
                sensor->spo2,
                control->mode);
    return g_http_status_json;
}
