#include "openclaw_integration.h"
#include "http_server.h"

rt_err_t openclaw_integration_init(void)
{
    return RT_EOK;
}

rt_err_t openclaw_handle_set_mode(control_mode_t mode)
{
    return control_set_mode(mode);
}

rt_err_t openclaw_handle_move_joint(joint_id_t joint, float target)
{
    return control_move_joint(joint, target);
}

const char *openclaw_handle_get_sensor_data(void)
{
    sensor_data_t sensor;
    control_status_t control;

    sensor_get_latest(&sensor);
    control_get_status(&control);
    return http_server_build_status_json(&sensor, &control);
}
