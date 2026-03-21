#ifndef HTTP_SERVER_H
#define HTTP_SERVER_H

#include <rtthread.h>
#include "sensor_manager.h"
#include "control_manager.h"

rt_err_t http_server_init(void);
rt_err_t http_server_start(void);
const char *http_server_build_status_json(const sensor_data_t *sensor, const control_status_t *control);

#endif
