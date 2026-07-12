#ifndef WIFI_CONFIG_SERVICE_H
#define WIFI_CONFIG_SERVICE_H

#include <rtthread.h>
#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WIFI_CONFIG_SSID_MAX_LEN      32
#define WIFI_CONFIG_PASSWORD_MAX_LEN  64
#define WIFI_CONFIG_SCAN_MAX_APS      12

typedef struct
{
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 1];
    rt_int16_t rssi;
    rt_int16_t channel;
    rt_uint32_t security;
    rt_uint8_t bssid[6];
} wifi_config_ap_t;

typedef struct
{
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 1];
    char password[WIFI_CONFIG_PASSWORD_MAX_LEN + 1];
    rt_uint32_t saved;
    rt_uint32_t auto_connect;
    rt_int32_t storage_result;
    rt_int32_t connect_result;
    rt_uint32_t connect_ready;
    rt_err_t last_result;
    rt_int32_t scan_count;
    rt_uint32_t scan_running;
    rt_err_t scan_result;
    rt_uint32_t scan_request_count;
    rt_uint32_t scan_callback_count;
    rt_uint32_t scan_done_count;
    rt_uint32_t scan_timeout_count;
    rt_int32_t whd_stage;
    rt_int32_t whd_result;
    rt_uint32_t whd_flags;
    rt_uint32_t whd_extra0;
    rt_uint32_t whd_extra1;
    rt_uint32_t mmcsd_core_init;
    rt_uint32_t mmcsd_thread_started;
    rt_uint32_t mmcsd_change_sent;
    rt_uint32_t mmcsd_change_err;
    rt_uint32_t mmcsd_recv_count;
    rt_uint32_t mmcsd_power_up_count;
    rt_uint32_t mmcsd_cmd5_before_count;
    rt_uint32_t mmcsd_cmd5_after_count;
    rt_int32_t mmcsd_cmd5_last_err;
    rt_uint32_t wlan_connected;
    rt_uint32_t wlan_ready;
    rt_int32_t wlan_rssi;
    rt_uint32_t netdev_flags;
    rt_uint32_t netdev_ip;
    rt_uint32_t netdev_gw;
    rt_uint32_t netdev_mask;
    rt_uint32_t netdev_dns0;
    char netdev_name[RT_NAME_MAX];
} wifi_config_snapshot_t;

rt_err_t wifi_config_service_init(void);
rt_err_t wifi_config_set_ssid(const char *ssid);
rt_err_t wifi_config_set_password(const char *password);
rt_err_t wifi_config_set_auto_connect(rt_bool_t enable);
rt_err_t wifi_config_load(void);
rt_err_t wifi_config_save(void);
rt_err_t wifi_config_forget(void);
rt_err_t wifi_config_start_auto_connect(rt_uint32_t delay_ms);
rt_err_t wifi_config_connect(void);
rt_err_t wifi_config_disconnect(void);
rt_err_t wifi_config_scan(void);
rt_int32_t wifi_config_get_scan_count(void);
rt_err_t wifi_config_get_scan_ap(rt_int32_t index, wifi_config_ap_t *ap);
const char *wifi_config_security_name(rt_uint32_t security);
rt_err_t wifi_config_diag(void);
rt_err_t wifi_config_whd_diag(void);
void wifi_config_get_snapshot(wifi_config_snapshot_t *snapshot);
void wifi_config_fill_voice_status(voice_status_msg_t *status);

#ifdef __cplusplus
}
#endif

#endif
