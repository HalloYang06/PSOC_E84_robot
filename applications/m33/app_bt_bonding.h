#ifndef APP_BT_BONDING_H
#define APP_BT_BONDING_H

#include <stdint.h>
#include "cy_result.h"
#include "wiced_bt_stack.h"
#include "wiced_bt_ble.h"

typedef enum
{
    NUM_BONDED,
    NEXT_FREE_INDEX
} bond_info_e;

#define BOND_INDEX_MAX 4

typedef struct
{
    uint8_t slot_data[2];
    wiced_bt_device_link_keys_t link_keys[BOND_INDEX_MAX];
    wiced_bt_ble_privacy_mode_t privacy_mode[BOND_INDEX_MAX];
} bond_info_t;

extern bond_info_t bond_info;
extern wiced_bt_local_identity_keys_t identity_keys;
extern uint16_t peer_cccd_data[BOND_INDEX_MAX];
extern wiced_bool_t pairing_mode;

void app_kv_store_init(void);
cy_rslt_t app_bt_restore_bond_data(void);
cy_rslt_t app_bt_update_bond_data(void);
cy_rslt_t app_bt_delete_bond_info(void);
wiced_result_t app_bt_delete_device_info(uint8_t index);
cy_rslt_t app_bt_update_slot_data(void);
cy_rslt_t app_bt_save_device_link_keys(wiced_bt_device_link_keys_t *link_key);
cy_rslt_t app_bt_save_local_identity_key(wiced_bt_local_identity_keys_t id_key);
cy_rslt_t app_bt_read_local_identity_keys(void);
cy_rslt_t app_bt_update_cccd(uint16_t cccd, uint8_t index);
cy_rslt_t app_bt_restore_cccd(void);
uint8_t app_bt_find_device_in_flash(uint8_t *bd_addr);
void app_bt_add_devices_to_address_resolution_db(void);
void print_bond_data(void);

#endif

