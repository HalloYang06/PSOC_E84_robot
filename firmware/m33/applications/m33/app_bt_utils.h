#ifndef APP_BT_UTILS_H
#define APP_BT_UTILS_H

#include <stdio.h>
#include "wiced_bt_dev.h"
#include "wiced_bt_gatt.h"

#define CASE_RETURN_STR(constant) case constant: return #constant;

void print_bd_address(wiced_bt_device_address_t bdadr);
void print_array(void *to_print, uint16_t len);
const char *get_btm_event_name(wiced_bt_management_evt_t event);
const char *get_bt_advert_mode_name(wiced_bt_ble_advert_mode_t mode);
const char *get_bt_gatt_disconn_reason_name(wiced_bt_gatt_disconn_reason_t reason);
const char *get_bt_gatt_status_name(wiced_bt_gatt_status_t status);
const char *get_bt_smp_status_name(wiced_bt_smp_status_t status);

#endif
