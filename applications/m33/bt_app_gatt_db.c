#include "bt_app_gatt_db.h"

#include "wiced_bt_gatt.h"

const uint8_t gatt_database[] =
{
    PRIMARY_SERVICE_UUID16(HDLS_GAP, __UUID_SERVICE_GENERIC_ACCESS),
        CHARACTERISTIC_UUID16(HDLC_GAP_DEVICE_NAME, HDLC_GAP_DEVICE_NAME_VALUE,
                              __UUID_CHARACTERISTIC_DEVICE_NAME,
                              GATTDB_CHAR_PROP_READ, GATTDB_PERM_READABLE),
        CHARACTERISTIC_UUID16(HDLC_GAP_APPEARANCE, HDLC_GAP_APPEARANCE_VALUE,
                              __UUID_CHARACTERISTIC_APPEARANCE,
                              GATTDB_CHAR_PROP_READ, GATTDB_PERM_READABLE),

    PRIMARY_SERVICE_UUID128(HDLS_NUS, __UUID_SERVICE_NUS),
        CHARACTERISTIC_UUID128(HDLC_NUS_TX, HDLC_NUS_TX_VALUE,
                               __UUID_CHARACTERISTIC_NUS_TX,
                               GATTDB_CHAR_PROP_READ | GATTDB_CHAR_PROP_NOTIFY,
                               GATTDB_PERM_READABLE),
            CHAR_DESCRIPTOR_UUID16_WRITABLE(HDLD_NUS_TX_CLIENT_CHAR_CONFIG,
                                            __UUID_DESCRIPTOR_CLIENT_CHARACTERISTIC_CONFIGURATION,
                                            GATTDB_PERM_READABLE | GATTDB_PERM_WRITE_REQ),
        CHARACTERISTIC_UUID128_WRITABLE(HDLC_NUS_RX, HDLC_NUS_RX_VALUE,
                                        __UUID_CHARACTERISTIC_NUS_RX,
                                        GATTDB_CHAR_PROP_WRITE | GATTDB_CHAR_PROP_WRITE_NO_RESPONSE,
                                        GATTDB_PERM_WRITE_REQ | GATTDB_PERM_WRITE_CMD),
};

const uint16_t gatt_database_len = sizeof(gatt_database);

uint8_t app_gap_device_name[] = {'O', 'p', 'e', 'n', 'C', 'l', 'a', 'w', '-', 'N', 'U', 'S', '\0'};
uint8_t app_gap_appearance[] = {0x00, 0x00};
uint8_t app_nus_tx[MAX_LEN_NUS_TX] = {'r', 'e', 'a', 'd', 'y', '\n'};
uint16_t app_nus_tx_len = 6u;
uint8_t app_nus_tx_client_char_config[] = {0x00, 0x00};
uint8_t app_nus_rx[MAX_LEN_NUS_RX] = {0};
uint16_t app_nus_rx_len = 0u;

gatt_db_lookup_table_t app_gatt_db_ext_attr_tbl[] =
{
    {HDLC_GAP_DEVICE_NAME_VALUE, MAX_LEN_GAP_DEVICE_NAME, 12, app_gap_device_name},
    {HDLC_GAP_APPEARANCE_VALUE, MAX_LEN_GAP_APPEARANCE, 2, app_gap_appearance},
    {HDLC_NUS_TX_VALUE, MAX_LEN_NUS_TX, 6, app_nus_tx},
    {HDLD_NUS_TX_CLIENT_CHAR_CONFIG, MAX_LEN_NUS_TX_CLIENT_CHAR_CONFIG, 2, app_nus_tx_client_char_config},
    {HDLC_NUS_RX_VALUE, MAX_LEN_NUS_RX, 0, app_nus_rx},
};

const uint16_t app_gatt_db_ext_attr_tbl_size =
    (uint16_t)(sizeof(app_gatt_db_ext_attr_tbl) / sizeof(gatt_db_lookup_table_t));

const uint16_t app_gap_device_name_len = sizeof(app_gap_device_name);
const uint16_t app_gap_appearance_len = sizeof(app_gap_appearance);
const uint16_t app_nus_tx_client_char_config_len = sizeof(app_nus_tx_client_char_config);

