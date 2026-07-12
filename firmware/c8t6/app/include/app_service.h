#ifndef APP_SERVICE_H
#define APP_SERVICE_H

#include <stdint.h>

#include "app_types.h"

int32_t app_service_init(void);
void app_service_run_once(void);
node_state_t app_service_get_state(void);
uint16_t app_service_get_error_count(void);
void app_service_on_systick_isr(void);

#endif
