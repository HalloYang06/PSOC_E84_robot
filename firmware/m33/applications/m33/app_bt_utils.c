#include "app_bt_utils.h"

void print_bd_address(wiced_bt_device_address_t bdadr)
{
    printf("%02X:%02X:%02X:%02X:%02X:%02X\n", bdadr[0], bdadr[1], bdadr[2], bdadr[3], bdadr[4], bdadr[5]);
}

void print_array(void *to_print, uint16_t len)
{
    uint16_t i;
    for (i = 0; i < len; ++i)
    {
        if ((i % 16u) == 0u)
        {
            printf("\n");
        }
        printf("%02X ", ((uint8_t *)to_print)[i]);
    }
    printf("\n");
}

const char *get_btm_event_name(wiced_bt_management_evt_t event)
{
    switch ((int)event)
    {
        CASE_RETURN_STR(BTM_ENABLED_EVT)
        CASE_RETURN_STR(BTM_DISABLED_EVT)
        CASE_RETURN_STR(BTM_PAIRING_IO_CAPABILITIES_BLE_REQUEST_EVT)
        CASE_RETURN_STR(BTM_PAIRING_COMPLETE_EVT)
        CASE_RETURN_STR(BTM_ENCRYPTION_STATUS_EVT)
        CASE_RETURN_STR(BTM_SECURITY_REQUEST_EVT)
        CASE_RETURN_STR(BTM_SECURITY_FAILED_EVT)
        CASE_RETURN_STR(BTM_PAIRED_DEVICE_LINK_KEYS_UPDATE_EVT)
        CASE_RETURN_STR(BTM_PAIRED_DEVICE_LINK_KEYS_REQUEST_EVT)
        CASE_RETURN_STR(BTM_LOCAL_IDENTITY_KEYS_UPDATE_EVT)
        CASE_RETURN_STR(BTM_LOCAL_IDENTITY_KEYS_REQUEST_EVT)
        CASE_RETURN_STR(BTM_BLE_ADVERT_STATE_CHANGED_EVT)
        default:
            return "UNKNOWN_EVENT";
    }
}

const char *get_bt_advert_mode_name(wiced_bt_ble_advert_mode_t mode)
{
    switch ((int)mode)
    {
        CASE_RETURN_STR(BTM_BLE_ADVERT_OFF)
        CASE_RETURN_STR(BTM_BLE_ADVERT_UNDIRECTED_HIGH)
        CASE_RETURN_STR(BTM_BLE_ADVERT_UNDIRECTED_LOW)
        CASE_RETURN_STR(BTM_BLE_ADVERT_NONCONN_HIGH)
        CASE_RETURN_STR(BTM_BLE_ADVERT_NONCONN_LOW)
        default:
            return "UNKNOWN_MODE";
    }
}

const char *get_bt_gatt_disconn_reason_name(wiced_bt_gatt_disconn_reason_t reason)
{
    switch ((int)reason)
    {
        CASE_RETURN_STR(GATT_CONN_UNKNOWN)
        CASE_RETURN_STR(GATT_CONN_L2C_FAILURE)
        CASE_RETURN_STR(GATT_CONN_TIMEOUT)
        CASE_RETURN_STR(GATT_CONN_TERMINATE_PEER_USER)
        CASE_RETURN_STR(GATT_CONN_TERMINATE_LOCAL_HOST)
        CASE_RETURN_STR(GATT_CONN_FAIL_ESTABLISH)
        CASE_RETURN_STR(GATT_CONN_LMP_TIMEOUT)
        CASE_RETURN_STR(GATT_CONN_CANCEL)
        default:
            return "UNKNOWN_REASON";
    }
}

const char *get_bt_gatt_status_name(wiced_bt_gatt_status_t status)
{
    switch ((int)status)
    {
        CASE_RETURN_STR(WICED_BT_GATT_SUCCESS)
        CASE_RETURN_STR(WICED_BT_GATT_INVALID_HANDLE)
        CASE_RETURN_STR(WICED_BT_GATT_READ_NOT_PERMIT)
        CASE_RETURN_STR(WICED_BT_GATT_WRITE_NOT_PERMIT)
        CASE_RETURN_STR(WICED_BT_GATT_REQ_NOT_SUPPORTED)
        CASE_RETURN_STR(WICED_BT_GATT_INVALID_OFFSET)
        CASE_RETURN_STR(WICED_BT_GATT_ATTRIBUTE_NOT_FOUND)
        CASE_RETURN_STR(WICED_BT_GATT_INVALID_ATTR_LEN)
        CASE_RETURN_STR(WICED_BT_GATT_ERROR)
        default:
            return "UNKNOWN_GATT_STATUS";
    }
}

const char *get_bt_smp_status_name(wiced_bt_smp_status_t status)
{
    switch ((int)status)
    {
        CASE_RETURN_STR(SMP_SUCCESS)
        CASE_RETURN_STR(SMP_PASSKEY_ENTRY_FAIL)
        CASE_RETURN_STR(SMP_OOB_FAIL)
        CASE_RETURN_STR(SMP_PAIR_AUTH_FAIL)
        CASE_RETURN_STR(SMP_CONFIRM_VALUE_ERR)
        CASE_RETURN_STR(SMP_PAIR_NOT_SUPPORT)
        CASE_RETURN_STR(SMP_ENC_KEY_SIZE)
        CASE_RETURN_STR(SMP_INVALID_CMD)
        CASE_RETURN_STR(SMP_PAIR_FAIL_UNKNOWN)
        CASE_RETURN_STR(SMP_REPEATED_ATTEMPTS)
        CASE_RETURN_STR(SMP_INVALID_PARAMETERS)
        CASE_RETURN_STR(SMP_DHKEY_CHK_FAIL)
        CASE_RETURN_STR(SMP_NUMERIC_COMPAR_FAIL)
        CASE_RETURN_STR(SMP_BR_PAIRING_IN_PROGR)
        CASE_RETURN_STR(SMP_XTRANS_DERIVE_NOT_ALLOW)
        CASE_RETURN_STR(SMP_PAIR_INTERNAL_ERR)
        CASE_RETURN_STR(SMP_UNKNOWN_IO_CAP)
        CASE_RETURN_STR(SMP_INIT_FAIL)
        CASE_RETURN_STR(SMP_CONFIRM_FAIL)
        CASE_RETURN_STR(SMP_BUSY)
        CASE_RETURN_STR(SMP_ENC_FAIL)
        CASE_RETURN_STR(SMP_STARTED)
        CASE_RETURN_STR(SMP_RSP_TIMEOUT)
        CASE_RETURN_STR(SMP_FAIL)
        CASE_RETURN_STR(SMP_CONN_TOUT)
        default:
            return "UNKNOWN_SMP_STATUS";
    }
}
