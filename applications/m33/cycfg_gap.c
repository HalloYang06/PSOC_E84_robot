#include "cycfg_gap.h"

wiced_bt_device_address_t cy_bt_device_address = {0x00, 0xA0, 0x50, 0x11, 0x44, 0x77};

const uint8_t cy_bt_adv_packet_elem_0[1] = {0x06};
const uint8_t cy_bt_adv_packet_elem_1[12] = {'O', 'p', 'e', 'n', 'C', 'l', 'a', 'w', '-', 'N', 'U', 'S'};

wiced_bt_ble_advert_elem_t cy_bt_adv_packet_data[] =
{
    {
        .advert_type = BTM_BLE_ADVERT_TYPE_FLAG,
        .len = 1,
        .p_data = (uint8_t *)cy_bt_adv_packet_elem_0,
    },
    {
        .advert_type = BTM_BLE_ADVERT_TYPE_NAME_COMPLETE,
        .len = 12,
        .p_data = (uint8_t *)cy_bt_adv_packet_elem_1,
    },
};

