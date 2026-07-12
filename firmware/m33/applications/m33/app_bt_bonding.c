#include "app_bt_bonding.h"

#include <string.h>
#include <stdio.h>

bond_info_t bond_info;
wiced_bt_local_identity_keys_t identity_keys;
uint16_t peer_cccd_data[BOND_INDEX_MAX];
wiced_bool_t pairing_mode = WICED_FALSE;
static wiced_bool_t g_bond_data_valid = WICED_FALSE;
static wiced_bool_t g_identity_keys_valid = WICED_FALSE;

void app_kv_store_init(void)
{
}

cy_rslt_t app_bt_restore_bond_data(void)
{
    return g_bond_data_valid ? CY_RSLT_SUCCESS : CY_RSLT_TYPE_ERROR;
}

cy_rslt_t app_bt_update_bond_data(void)
{
    g_bond_data_valid = WICED_TRUE;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t app_bt_delete_bond_info(void)
{
    memset(&bond_info, 0, sizeof(bond_info));
    memset(peer_cccd_data, 0, sizeof(peer_cccd_data));
    g_bond_data_valid = WICED_FALSE;
    return CY_RSLT_SUCCESS;
}

wiced_result_t app_bt_delete_device_info(uint8_t index)
{
    if (index >= BOND_INDEX_MAX)
    {
        return WICED_BT_ERROR;
    }

    (void)wiced_bt_dev_delete_bonded_device(bond_info.link_keys[index].bd_addr);
    (void)wiced_bt_dev_remove_device_from_address_resolution_db(&bond_info.link_keys[index]);
    memset(&bond_info.link_keys[index], 0, sizeof(wiced_bt_device_link_keys_t));
    bond_info.privacy_mode[index] = 0;
    peer_cccd_data[index] = 0;
    return WICED_BT_SUCCESS;
}

cy_rslt_t app_bt_update_slot_data(void)
{
    if (bond_info.slot_data[NUM_BONDED] < BOND_INDEX_MAX)
    {
        bond_info.slot_data[NUM_BONDED]++;
    }
    bond_info.slot_data[NEXT_FREE_INDEX] = (uint8_t)((bond_info.slot_data[NEXT_FREE_INDEX] + 1u) % BOND_INDEX_MAX);
    g_bond_data_valid = WICED_TRUE;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t app_bt_save_device_link_keys(wiced_bt_device_link_keys_t *link_key)
{
    uint8_t index;
    if (link_key == NULL)
    {
        return CY_RSLT_TYPE_ERROR;
    }

    index = app_bt_find_device_in_flash(link_key->bd_addr);
    if (index >= BOND_INDEX_MAX)
    {
        index = bond_info.slot_data[NEXT_FREE_INDEX];
    }

    memcpy(&bond_info.link_keys[index], link_key, sizeof(*link_key));
    g_bond_data_valid = WICED_TRUE;
    pairing_mode = WICED_TRUE;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t app_bt_save_local_identity_key(wiced_bt_local_identity_keys_t id_key)
{
    memcpy(&identity_keys, &id_key, sizeof(identity_keys));
    g_identity_keys_valid = WICED_TRUE;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t app_bt_read_local_identity_keys(void)
{
    return g_identity_keys_valid ? CY_RSLT_SUCCESS : CY_RSLT_TYPE_ERROR;
}

cy_rslt_t app_bt_update_cccd(uint16_t cccd, uint8_t index)
{
    if (index >= BOND_INDEX_MAX)
    {
        return CY_RSLT_TYPE_ERROR;
    }
    peer_cccd_data[index] = cccd;
    g_bond_data_valid = WICED_TRUE;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t app_bt_restore_cccd(void)
{
    return CY_RSLT_SUCCESS;
}

uint8_t app_bt_find_device_in_flash(uint8_t *bd_addr)
{
    uint8_t i;
    for (i = 0; i < BOND_INDEX_MAX; ++i)
    {
        if (memcmp(bond_info.link_keys[i].bd_addr, bd_addr, BD_ADDR_LEN) == 0)
        {
            return i;
        }
    }
    return BOND_INDEX_MAX;
}

void app_bt_add_devices_to_address_resolution_db(void)
{
    uint8_t i;
    for (i = 0; i < BOND_INDEX_MAX; ++i)
    {
        if (memcmp(bond_info.link_keys[i].bd_addr, "\0\0\0\0\0\0", BD_ADDR_LEN) != 0)
        {
            (void)wiced_bt_dev_add_device_to_address_resolution_db(&bond_info.link_keys[i]);
        }
    }
}

void print_bond_data(void)
{
    printf("bonded=%u next=%u\n", bond_info.slot_data[NUM_BONDED], bond_info.slot_data[NEXT_FREE_INDEX]);
}
