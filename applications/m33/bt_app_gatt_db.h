#ifndef BT_APP_GATT_DB_H
#define BT_APP_GATT_DB_H

#include <stdint.h>

#define __UUID_SERVICE_GENERIC_ACCESS 0x1800
#define __UUID_CHARACTERISTIC_DEVICE_NAME 0x2A00
#define __UUID_CHARACTERISTIC_APPEARANCE 0x2A01
#define __UUID_DESCRIPTOR_CLIENT_CHARACTERISTIC_CONFIGURATION 0x2902
#define __UUID_SERVICE_NUS 0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0, 0x93, 0xF3, 0xA3, 0xB5, 0x01, 0x00, 0x40, 0x6E
#define __UUID_CHARACTERISTIC_NUS_RX 0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0, 0x93, 0xF3, 0xA3, 0xB5, 0x02, 0x00, 0x40, 0x6E
#define __UUID_CHARACTERISTIC_NUS_TX 0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0, 0x93, 0xF3, 0xA3, 0xB5, 0x03, 0x00, 0x40, 0x6E

#define BT_APP_UUID_SERVICE_GENERIC_ACCESS __UUID_SERVICE_GENERIC_ACCESS
#define BT_APP_UUID_CHARACTERISTIC_DEVICE_NAME __UUID_CHARACTERISTIC_DEVICE_NAME
#define BT_APP_UUID_CHARACTERISTIC_APPEARANCE __UUID_CHARACTERISTIC_APPEARANCE
#define BT_APP_UUID_DESCRIPTOR_CLIENT_CHARACTERISTIC_CONFIGURATION __UUID_DESCRIPTOR_CLIENT_CHARACTERISTIC_CONFIGURATION
#define BT_APP_UUID_SERVICE_NUS __UUID_SERVICE_NUS
#define BT_APP_UUID_CHARACTERISTIC_NUS_RX __UUID_CHARACTERISTIC_NUS_RX
#define BT_APP_UUID_CHARACTERISTIC_NUS_TX __UUID_CHARACTERISTIC_NUS_TX

#define HDLS_GAP 0x0001
#define HDLC_GAP_DEVICE_NAME 0x0002
#define HDLC_GAP_DEVICE_NAME_VALUE 0x0003
#define MAX_LEN_GAP_DEVICE_NAME 0x0010
#define HDLC_GAP_APPEARANCE 0x0004
#define HDLC_GAP_APPEARANCE_VALUE 0x0005
#define MAX_LEN_GAP_APPEARANCE 0x0002

#define HDLS_NUS 0x0006
#define HDLC_NUS_TX 0x0007
#define HDLC_NUS_TX_VALUE 0x0008
#define MAX_LEN_NUS_TX 0x0200
#define HDLD_NUS_TX_CLIENT_CHAR_CONFIG 0x0009
#define MAX_LEN_NUS_TX_CLIENT_CHAR_CONFIG 0x0002
#define HDLC_NUS_RX 0x000A
#define HDLC_NUS_RX_VALUE 0x000B
#define MAX_LEN_NUS_RX 0x0200

typedef struct
{
    uint16_t handle;
    uint16_t max_len;
    uint16_t cur_len;
    uint8_t *p_data;
} gatt_db_lookup_table_t;

typedef gatt_db_lookup_table_t bt_app_gatt_lookup_t;

extern const uint8_t gatt_database[];
extern const uint16_t gatt_database_len;
extern gatt_db_lookup_table_t app_gatt_db_ext_attr_tbl[];
extern const uint16_t app_gatt_db_ext_attr_tbl_size;
extern uint8_t app_gap_device_name[];
extern const uint16_t app_gap_device_name_len;
extern uint8_t app_gap_appearance[];
extern const uint16_t app_gap_appearance_len;
extern uint8_t app_nus_tx[];
extern uint16_t app_nus_tx_len;
extern uint8_t app_nus_tx_client_char_config[];
extern const uint16_t app_nus_tx_client_char_config_len;
extern uint8_t app_nus_rx[];
extern uint16_t app_nus_rx_len;

#endif
