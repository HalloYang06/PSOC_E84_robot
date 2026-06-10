#ifndef WIFI_CONFIG_SERVICE_H
#define WIFI_CONFIG_SERVICE_H

#include <rtthread.h>
#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WIFI_CONFIG_SSID_MAX_LEN      32
#define WIFI_CONFIG_PASSWORD_MAX_LEN  64

typedef struct
{
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 1];
    char password[WIFI_CONFIG_PASSWORD_MAX_LEN + 1];
    rt_uint32_t saved;
    rt_uint32_t auto_connect;
    rt_int32_t storage_result;
    rt_err_t last_result;
    rt_int32_t scan_count;
    rt_int32_t whd_stage;
    rt_int32_t whd_result;
    rt_uint32_t whd_flags;
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
rt_err_t wifi_config_diag(void);
rt_err_t wifi_config_whd_diag(void);
void wifi_config_get_snapshot(wifi_config_snapshot_t *snapshot);
void wifi_config_fill_voice_status(voice_status_msg_t *status);

#ifdef __cplusplus
}
#endif

#endif
