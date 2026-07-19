#ifndef BT_APP_GATT_HANDLER_H
#define BT_APP_GATT_HANDLER_H

#include <rtthread.h>
#include "app_ble_worker.h"
#include "app_bt_event_handler.h"
#include "bt_app_gatt_db.h"
#include "wiced_bt_gatt.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*bt_app_gatt_adv_restart_t)(void);
typedef void (*pfn_free_buffer_t)(uint8_t *);

wiced_bt_gatt_status_t app_bt_gatt_callback(wiced_bt_gatt_evt_t event,
                                            wiced_bt_gatt_event_data_t *p_data);
wiced_bt_gatt_status_t app_bt_gatt_req_cb(wiced_bt_gatt_attribute_request_t *p_attr_req,
                                          uint16_t *p_error_handle);
wiced_bt_gatt_status_t app_bt_gatt_conn_status_cb(wiced_bt_gatt_connection_status_t *p_conn_status);
wiced_bt_gatt_status_t app_bt_gatt_req_read_handler(uint16_t conn_id,
                                                    wiced_bt_gatt_opcode_t opcode,
                                                    wiced_bt_gatt_read_t *p_read_req,
                                                    uint16_t len_req,
                                                    uint16_t *p_error_handle);
wiced_bt_gatt_status_t app_bt_gatt_req_write_handler(uint16_t conn_id,
                                                     wiced_bt_gatt_opcode_t opcode,
                                                     wiced_bt_gatt_write_req_t *p_write_req,
                                                     uint16_t len_req,
                                                     uint16_t *p_error_handle);
wiced_bt_gatt_status_t app_bt_gatt_req_read_by_type_handler(uint16_t conn_id,
                                                            wiced_bt_gatt_opcode_t opcode,
                                                            wiced_bt_gatt_read_by_type_t *p_read_req,
                                                            uint16_t len_requested,
                                                            uint16_t *p_error_handle);
wiced_bt_gatt_status_t app_bt_gatt_connection_up(wiced_bt_gatt_connection_status_t *p_status);
wiced_bt_gatt_status_t app_bt_gatt_connection_down(wiced_bt_gatt_connection_status_t *p_status);
gatt_db_lookup_table_t *app_bt_find_by_handle(uint16_t handle);
wiced_bt_gatt_status_t app_bt_set_value(uint16_t attr_handle,
                                        uint8_t *p_val,
                                        uint16_t len);
void app_bt_free_buffer(uint8_t *p_buf);
void *app_bt_alloc_buffer(int len);
void app_bt_send_message(const app_ble_session_token_t *token);
void app_bt_gatt_increment_notify_value(const app_ble_session_token_t *token);
rt_err_t bt_app_gatt_send(const app_ble_session_token_t *token,
                          const uint8_t *data,
                          uint16_t len);
rt_err_t bt_app_gatt_publish_telemetry(const app_ble_session_token_t *token,
                                       const uint8_t *data,
                                       uint16_t len);
rt_err_t bt_app_gatt_notify_from_worker(uint32_t generation,
                                        uint16_t conn_id,
                                        const uint8_t *data,
                                        uint16_t len);

rt_err_t bt_app_gatt_init(bt_app_gatt_adv_restart_t adv_restart_cb);
uint16_t bt_app_gatt_current_conn_id(void);
uint32_t bt_app_gatt_event_count(void);

#ifdef __cplusplus
}
#endif

#endif
