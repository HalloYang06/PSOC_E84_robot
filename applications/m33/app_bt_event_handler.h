#ifndef APP_BT_EVENT_HANDLER_H
#define APP_BT_EVENT_HANDLER_H

#include "wiced_bt_dev.h"

typedef struct
{
    wiced_bt_device_address_t remote_addr;
    uint32_t timer_count_s;
    uint32_t timer_count_ms;
    uint16_t conn_id;
    uint16_t peer_mtu;
    uint8_t flag_indication_sent;
    uint8_t num_to_send;
} hello_sensor_state_t;

extern hello_sensor_state_t hello_sensor_state;
extern uint8_t bondindex;

wiced_result_t app_bt_management_callback(wiced_bt_management_evt_t event,
                                          wiced_bt_management_evt_data_t *p_event_data);
void app_bt_application_init(void);
void app_bt_adv_stop_handler(void);
void app_bt_alive_probe_start(void);

#endif
