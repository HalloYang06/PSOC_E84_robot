#include "cycfg_bt_settings.h"
#include "cycfg_gap.h"

#include "wiced_bt_cfg.h"
#include "wiced_bt_dev.h"
#include "wiced_bt_gatt.h"

const wiced_bt_cfg_ble_scan_settings_t cy_bt_cfg_scan_settings =
{
    .scan_mode = CY_BT_SCAN_MODE,
    .high_duty_scan_interval = CY_BT_HIGH_DUTY_SCAN_INTERVAL,
    .high_duty_scan_window = CY_BT_HIGH_DUTY_SCAN_WINDOW,
    .high_duty_scan_duration = CY_BT_HIGH_DUTY_SCAN_DURATION,
    .low_duty_scan_interval = CY_BT_LOW_DUTY_SCAN_INTERVAL,
    .low_duty_scan_window = CY_BT_LOW_DUTY_SCAN_WINDOW,
    .low_duty_scan_duration = CY_BT_LOW_DUTY_SCAN_DURATION,
    .high_duty_conn_scan_interval = CY_BT_HIGH_DUTY_CONN_SCAN_INTERVAL,
    .high_duty_conn_scan_window = CY_BT_HIGH_DUTY_CONN_SCAN_WINDOW,
    .high_duty_conn_duration = CY_BT_HIGH_DUTY_CONN_SCAN_DURATION,
    .low_duty_conn_scan_interval = CY_BT_LOW_DUTY_CONN_SCAN_INTERVAL,
    .low_duty_conn_scan_window = CY_BT_LOW_DUTY_CONN_SCAN_WINDOW,
    .low_duty_conn_duration = CY_BT_LOW_DUTY_CONN_SCAN_DURATION,
    .conn_min_interval = CY_BT_CONN_MIN_INTERVAL,
    .conn_max_interval = CY_BT_CONN_MAX_INTERVAL,
    .conn_latency = CY_BT_CONN_LATENCY,
    .conn_supervision_timeout = CY_BT_CONN_SUPERVISION_TIMEOUT,
};

const wiced_bt_cfg_ble_advert_settings_t cy_bt_cfg_adv_settings =
{
    .channel_map = CY_BT_CHANNEL_MAP,
    .high_duty_min_interval = CY_BT_HIGH_DUTY_ADV_MIN_INTERVAL,
    .high_duty_max_interval = CY_BT_HIGH_DUTY_ADV_MAX_INTERVAL,
    .high_duty_duration = CY_BT_HIGH_DUTY_ADV_DURATION,
    .low_duty_min_interval = CY_BT_LOW_DUTY_ADV_MIN_INTERVAL,
    .low_duty_max_interval = CY_BT_LOW_DUTY_ADV_MAX_INTERVAL,
    .low_duty_duration = CY_BT_LOW_DUTY_ADV_DURATION,
    .high_duty_directed_min_interval = CY_BT_HIGH_DUTY_DIRECTED_ADV_MIN_INTERVAL,
    .high_duty_directed_max_interval = CY_BT_HIGH_DUTY_DIRECTED_ADV_MAX_INTERVAL,
    .low_duty_directed_min_interval = CY_BT_LOW_DUTY_DIRECTED_ADV_MIN_INTERVAL,
    .low_duty_directed_max_interval = CY_BT_LOW_DUTY_DIRECTED_ADV_MAX_INTERVAL,
    .low_duty_directed_duration = CY_BT_LOW_DUTY_DIRECTED_ADV_DURATION,
    .high_duty_nonconn_min_interval = CY_BT_HIGH_DUTY_NONCONN_ADV_MIN_INTERVAL,
    .high_duty_nonconn_max_interval = CY_BT_HIGH_DUTY_NONCONN_ADV_MAX_INTERVAL,
    .high_duty_nonconn_duration = CY_BT_HIGH_DUTY_NONCONN_ADV_DURATION,
    .low_duty_nonconn_min_interval = CY_BT_LOW_DUTY_NONCONN_ADV_MIN_INTERVAL,
    .low_duty_nonconn_max_interval = CY_BT_LOW_DUTY_NONCONN_ADV_MAX_INTERVAL,
    .low_duty_nonconn_duration = CY_BT_LOW_DUTY_NONCONN_ADV_DURATION,
};

const wiced_bt_cfg_ble_t cy_bt_cfg_ble =
{
    .ble_max_simultaneous_links = (CY_BT_CLIENT_MAX_LINKS + CY_BT_SERVER_MAX_LINKS),
    .ble_max_rx_pdu_size = CY_BT_RX_PDU_SIZE,
    .appearance = CY_BT_APPEARANCE,
    .rpa_refresh_timeout = CY_BT_RPA_TIMEOUT,
    .host_addr_resolution_db_size = CY_BT_ADDR_RESOLUTION_DB_SIZE,
    .p_ble_scan_cfg = &cy_bt_cfg_scan_settings,
    .p_ble_advert_cfg = &cy_bt_cfg_adv_settings,
    .default_ble_power_level = CY_BT_TX_POWER,
};

const wiced_bt_cfg_gatt_t cy_bt_cfg_gatt =
{
    .max_db_service_modules = CY_BT_MAX_DB_SERVICE_MODULES,
    .max_eatt_bearers = CY_BT_MAX_EATT_BEARERS,
};

const wiced_bt_cfg_l2cap_application_t cy_bt_cfg_l2cap =
{
    .max_app_l2cap_psms = CY_BT_L2CAP_MAX_LE_PSM,
    .max_app_l2cap_channels = CY_BT_L2CAP_MAX_LE_CHANNELS,
    .max_app_l2cap_le_fixed_channels = CY_BT_L2CAP_MAX_LE_FIXED_CHANNELS,
    .max_app_l2cap_br_edr_ertm_chnls = CY_BT_L2CAP_MAX_BR_ERTM_CHANNELS,
    .max_app_l2cap_br_edr_ertm_tx_win = CY_BT_L2CAP_MAX_BR_ERTM_TX_WIN,
};

const wiced_bt_cfg_settings_t wiced_bt_cfg_settings =
{
    .device_name = (uint8_t *)app_gap_device_name,
    .security_required = CY_BT_SECURITY_LEVEL,
    .p_ble_cfg = &cy_bt_cfg_ble,
    .p_gatt_cfg = &cy_bt_cfg_gatt,
    .p_l2cap_app_cfg = &cy_bt_cfg_l2cap,
};
