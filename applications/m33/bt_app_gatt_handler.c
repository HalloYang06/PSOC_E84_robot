#include "bt_app_gatt_handler.h"

#include <string.h>

#include "app_ble_service.h"
#include "app_bt_bonding.h"
#include "app_bt_utils.h"
#include "cycfg_gap.h"

static rt_bool_t g_bt_app_gatt_ready = RT_FALSE;
static bt_app_gatt_adv_restart_t g_bt_app_adv_restart_cb = RT_NULL;
static uint32_t g_bt_app_gatt_event_count = 0u;

static void app_bt_nus_notify(void)
{
    if ((hello_sensor_state.conn_id == 0u) ||
        ((app_nus_tx_client_char_config[0] & GATT_CLIENT_CONFIG_NOTIFICATION) == 0u))
    {
        return;
    }

    (void)wiced_bt_gatt_server_send_notification(hello_sensor_state.conn_id,
                                                 HDLC_NUS_TX_VALUE,
                                                 app_nus_tx_len,
                                                 app_nus_tx,
                                                 NULL);
}

rt_err_t bt_app_gatt_send(const uint8_t *data, uint16_t len)
{
    if ((data == RT_NULL) || (len == 0u))
    {
        return -RT_ERROR;
    }
    if (len > MAX_LEN_NUS_TX)
    {
        len = MAX_LEN_NUS_TX;
    }
    if (hello_sensor_state.conn_id == 0u)
    {
        return -RT_ENOSYS;
    }
    if ((app_nus_tx_client_char_config[0] & GATT_CLIENT_CONFIG_NOTIFICATION) == 0u)
    {
        return -RT_EEMPTY;
    }

    memcpy(app_nus_tx, data, len);
    app_nus_tx_len = len;
    app_bt_nus_notify();
    return RT_EOK;
}

wiced_bt_gatt_status_t app_bt_gatt_callback(wiced_bt_gatt_evt_t event,
                                            wiced_bt_gatt_event_data_t *p_event_data)
{
    wiced_bt_gatt_status_t gatt_status = WICED_BT_SUCCESS;
    uint16_t error_handle = 0u;
    wiced_bt_gatt_attribute_request_t *p_attr_req = &p_event_data->attribute_request;

    g_bt_app_gatt_event_count++;
    rt_kprintf("[bt] GATT evt=0x%02X\n", (unsigned int)event);

    switch (event)
    {
    case GATT_CONNECTION_STATUS_EVT:
        gatt_status = app_bt_gatt_conn_status_cb(&p_event_data->connection_status);
        break;

    case GATT_ATTRIBUTE_REQUEST_EVT:
        rt_kprintf("[bt] GATT req opcode=0x%02X conn_id=%u\n", p_attr_req->opcode, p_attr_req->conn_id);
        gatt_status = app_bt_gatt_req_cb(p_attr_req, &error_handle);
        rt_kprintf("[bt] GATT req status=0x%04X err_handle=0x%04X\n", gatt_status, error_handle);
        if (gatt_status != WICED_BT_GATT_SUCCESS)
        {
            wiced_bt_gatt_server_send_error_rsp(p_attr_req->conn_id,
                                                p_attr_req->opcode,
                                                error_handle,
                                                gatt_status);
        }
        break;

    case GATT_GET_RESPONSE_BUFFER_EVT:
        rt_kprintf("[bt] GATT get-rsp-buffer len=%u\n",
                   (unsigned int)p_event_data->buffer_request.len_requested);
        p_event_data->buffer_request.buffer.p_app_rsp_buffer =
            app_bt_alloc_buffer(p_event_data->buffer_request.len_requested);
        p_event_data->buffer_request.buffer.p_app_ctxt = (void *)app_bt_free_buffer;
        gatt_status = WICED_BT_GATT_SUCCESS;
        break;

    case GATT_APP_BUFFER_TRANSMITTED_EVT:
        rt_kprintf("[bt] GATT app-buffer-transmitted\n");
        if (p_event_data->buffer_xmitted.p_app_ctxt != RT_NULL)
        {
            ((pfn_free_buffer_t)p_event_data->buffer_xmitted.p_app_ctxt)(p_event_data->buffer_xmitted.p_app_data);
        }
        gatt_status = WICED_BT_GATT_SUCCESS;
        break;

    default:
        rt_kprintf("[bt] GATT unhandled evt=0x%02X\n", (unsigned int)event);
        gatt_status = WICED_BT_GATT_SUCCESS;
        break;
    }

    return gatt_status;
}

wiced_bt_gatt_status_t app_bt_gatt_req_cb(wiced_bt_gatt_attribute_request_t *p_attr_req,
                                          uint16_t *p_error_handle)
{
    wiced_bt_gatt_status_t gatt_status = WICED_BT_SUCCESS;

    switch (p_attr_req->opcode)
    {
    case GATT_REQ_READ:
    case GATT_REQ_READ_BLOB:
        gatt_status = app_bt_gatt_req_read_handler(p_attr_req->conn_id,
                                                   p_attr_req->opcode,
                                                   &p_attr_req->data.read_req,
                                                   p_attr_req->len_requested,
                                                   p_error_handle);
        break;

    case GATT_REQ_WRITE:
    case GATT_CMD_WRITE:
        rt_kprintf("[bt] Write request: handle=0x%04X len=%u opcode=0x%02X\n",
                   p_attr_req->data.write_req.handle,
                   p_attr_req->data.write_req.val_len,
                   p_attr_req->opcode);
        gatt_status = app_bt_gatt_req_write_handler(p_attr_req->conn_id,
                                                    p_attr_req->opcode,
                                                    &p_attr_req->data.write_req,
                                                    p_attr_req->len_requested,
                                                    p_error_handle);
        if ((p_attr_req->opcode == GATT_REQ_WRITE) && (gatt_status == WICED_BT_GATT_SUCCESS))
        {
            wiced_bt_gatt_server_send_write_rsp(p_attr_req->conn_id,
                                                p_attr_req->opcode,
                                                p_attr_req->data.write_req.handle);
        }
        break;

    case GATT_REQ_MTU:
        hello_sensor_state.peer_mtu = p_attr_req->data.remote_mtu;
        rt_kprintf("[bt] MTU exchange: peer=%u local=%u\n",
                   p_attr_req->data.remote_mtu, CY_BT_MTU_SIZE);
        gatt_status = wiced_bt_gatt_server_send_mtu_rsp(p_attr_req->conn_id,
                                                        p_attr_req->data.remote_mtu,
                                                        CY_BT_MTU_SIZE);
        break;

    case GATT_HANDLE_VALUE_NOTIF:
        gatt_status = WICED_BT_GATT_SUCCESS;
        break;

    case GATT_HANDLE_VALUE_CONF:
        gatt_status = WICED_BT_GATT_SUCCESS;
        break;

    case GATT_REQ_READ_BY_TYPE:
        gatt_status = app_bt_gatt_req_read_by_type_handler(p_attr_req->conn_id,
                                                           p_attr_req->opcode,
                                                           &p_attr_req->data.read_by_type,
                                                           p_attr_req->len_requested,
                                                           p_error_handle);
        break;

    default:
        rt_kprintf("[bt] GATT unsupported opcode=0x%02X\n",
                   (unsigned int)p_attr_req->opcode);
        gatt_status = WICED_BT_GATT_REQ_NOT_SUPPORTED;
        break;
    }

    return gatt_status;
}

wiced_bt_gatt_status_t app_bt_gatt_conn_status_cb(wiced_bt_gatt_connection_status_t *p_conn_status)
{
    if (p_conn_status->connected)
    {
        return app_bt_gatt_connection_up(p_conn_status);
    }
    return app_bt_gatt_connection_down(p_conn_status);
}

wiced_bt_gatt_status_t app_bt_gatt_req_read_handler(uint16_t conn_id,
                                                    wiced_bt_gatt_opcode_t opcode,
                                                    wiced_bt_gatt_read_t *p_read_req,
                                                    uint16_t len_req,
                                                    uint16_t *p_error_handle)
{
    gatt_db_lookup_table_t *p_attr;
    uint8_t *from;
    int to_send;

    *p_error_handle = p_read_req->handle;
    rt_kprintf("[bt] GATT read handle=0x%04X offset=%u len_req=%u opcode=0x%02X\n",
               p_read_req->handle,
               (unsigned int)p_read_req->offset,
               (unsigned int)len_req,
               (unsigned int)opcode);
    p_attr = app_bt_find_by_handle(p_read_req->handle);
    if (p_attr == RT_NULL)
    {
        return WICED_BT_GATT_INVALID_HANDLE;
    }
    if (p_read_req->offset > p_attr->cur_len)
    {
        return WICED_BT_GATT_INVALID_OFFSET;
    }
    if (p_read_req->offset == p_attr->cur_len)
    {
        return wiced_bt_gatt_server_send_read_handle_rsp(conn_id, opcode, 0u, p_attr->p_data + p_attr->cur_len, NULL);
    }

    to_send = MIN((int)len_req, (int)(p_attr->cur_len - p_read_req->offset));
    from = p_attr->p_data + p_read_req->offset;
    return wiced_bt_gatt_server_send_read_handle_rsp(conn_id,
                                                     opcode,
                                                     (uint16_t)to_send,
                                                     from,
                                                     NULL);
}

wiced_bt_gatt_status_t app_bt_gatt_req_write_handler(uint16_t conn_id,
                                                     wiced_bt_gatt_opcode_t opcode,
                                                     wiced_bt_gatt_write_req_t *p_write_req,
                                                     uint16_t len_req,
                                                     uint16_t *p_error_handle)
{
    RT_UNUSED(conn_id);
    RT_UNUSED(opcode);
    RT_UNUSED(len_req);

    *p_error_handle = p_write_req->handle;
    rt_kprintf("[bt] GATT write handle=0x%04X offset=%u val_len=%u req_len=%u opcode=0x%02X\n",
               p_write_req->handle,
               (unsigned int)p_write_req->offset,
               (unsigned int)p_write_req->val_len,
               (unsigned int)len_req,
               (unsigned int)opcode);
    return app_bt_set_value(p_write_req->handle, p_write_req->p_val, p_write_req->val_len);
}

wiced_bt_gatt_status_t app_bt_gatt_req_read_by_type_handler(uint16_t conn_id,
                                                            wiced_bt_gatt_opcode_t opcode,
                                                            wiced_bt_gatt_read_by_type_t *p_read_req,
                                                            uint16_t len_requested,
                                                            uint16_t *p_error_handle)
{
    gatt_db_lookup_table_t *p_attr;
    uint16_t last_handle = 0u;
    uint16_t attr_handle = p_read_req->s_handle;
    uint8_t *p_rsp;
    uint8_t pair_len = 0u;
    int used_len = 0;

    if (p_read_req->uuid.len == LEN_UUID_16)
    {
        rt_kprintf("[bt] GATT read-by-type uuid16=0x%04X range=0x%04X-0x%04X len=%u\n",
                   p_read_req->uuid.uu.uuid16,
                   p_read_req->s_handle,
                   p_read_req->e_handle,
                   (unsigned int)len_requested);
    }

    p_rsp = app_bt_alloc_buffer((int)len_requested);
    if (p_rsp == RT_NULL)
    {
        return WICED_BT_GATT_INSUF_RESOURCE;
    }

    while (WICED_TRUE)
    {
        int filled;

        *p_error_handle = attr_handle;
        last_handle = attr_handle;
        attr_handle = wiced_bt_gatt_find_handle_by_type(attr_handle,
                                                        p_read_req->e_handle,
                                                        &p_read_req->uuid);
        if (attr_handle == 0u)
        {
            break;
        }

        p_attr = app_bt_find_by_handle(attr_handle);
        if (p_attr == RT_NULL)
        {
            app_bt_free_buffer(p_rsp);
            return WICED_BT_GATT_INVALID_HANDLE;
        }

        filled = wiced_bt_gatt_put_read_by_type_rsp_in_stream(p_rsp + used_len,
                                                              (int)(len_requested - used_len),
                                                              &pair_len,
                                                              attr_handle,
                                                              p_attr->cur_len,
                                                              p_attr->p_data);
        if (filled == 0)
        {
            break;
        }

        used_len += filled;
        attr_handle = (uint16_t)(last_handle + 1u);
    }

    if (used_len == 0)
    {
        app_bt_free_buffer(p_rsp);
        return WICED_BT_GATT_INVALID_HANDLE;
    }

    return wiced_bt_gatt_server_send_read_by_type_rsp(conn_id,
                                                      opcode,
                                                      pair_len,
                                                      (uint16_t)used_len,
                                                      p_rsp,
                                                      (void *)app_bt_free_buffer);
}

wiced_bt_gatt_status_t app_bt_gatt_connection_up(wiced_bt_gatt_connection_status_t *p_status)
{
    hello_sensor_state.conn_id = p_status->conn_id;
    memcpy(hello_sensor_state.remote_addr, p_status->bd_addr, sizeof(wiced_bt_device_address_t));
    pairing_mode = WICED_FALSE;
    app_ble_service_set_link_state(RT_TRUE, app_ble_service_get_runtime()->streaming_enabled);
    rt_kprintf("[bt] BLE connected conn_id=%u\n", p_status->conn_id);
    return WICED_BT_GATT_SUCCESS;
}

wiced_bt_gatt_status_t app_bt_gatt_connection_down(wiced_bt_gatt_connection_status_t *p_status)
{
    memset(hello_sensor_state.remote_addr, 0, BD_ADDR_LEN);
    hello_sensor_state.conn_id = 0u;
    hello_sensor_state.peer_mtu = 0u;
    pairing_mode = WICED_FALSE;
    app_ble_service_set_link_state(RT_FALSE, RT_FALSE);
    rt_kprintf("[bt] BLE disconnected conn_id=%u reason=%u\n",
               p_status->conn_id,
               (unsigned int)p_status->reason);
    if (g_bt_app_adv_restart_cb != RT_NULL)
    {
        g_bt_app_adv_restart_cb();
    }
    return WICED_BT_GATT_SUCCESS;
}

gatt_db_lookup_table_t *app_bt_find_by_handle(uint16_t handle)
{
    uint16_t i;
    for (i = 0; i < app_gatt_db_ext_attr_tbl_size; ++i)
    {
        if (handle == app_gatt_db_ext_attr_tbl[i].handle)
        {
            return &app_gatt_db_ext_attr_tbl[i];
        }
    }
    return RT_NULL;
}

wiced_bt_gatt_status_t app_bt_set_value(uint16_t attr_handle,
                                        uint8_t *p_val,
                                        uint16_t len)
{
    gatt_db_lookup_table_t *p_attr = app_bt_find_by_handle(attr_handle);

    if (p_attr == RT_NULL)
    {
        return WICED_BT_GATT_INVALID_HANDLE;
    }
    if (len > p_attr->max_len)
    {
        return WICED_BT_GATT_INVALID_ATTR_LEN;
    }

    memcpy(p_attr->p_data, p_val, len);
    p_attr->cur_len = len;

    switch (attr_handle)
    {
    case HDLD_NUS_TX_CLIENT_CHAR_CONFIG:
        if (len != 2u)
        {
            return WICED_BT_GATT_INVALID_ATTR_LEN;
        }
        app_nus_tx_client_char_config[0] = p_val[0];
        app_nus_tx_client_char_config[1] = p_val[1];
        return WICED_BT_GATT_SUCCESS;

    case HDLC_NUS_RX_VALUE:
    {
        app_ble_command_t cmd;
        char frame[MAX_LEN_NUS_RX + 1u];
        char response[64];

        app_nus_rx_len = len;
        memcpy(app_nus_rx, p_val, len);
        rt_kprintf("[bt] NUS rx len=%u data='%.*s'\n", (unsigned int)len, (int)len, p_val);

        memset(frame, 0, sizeof(frame));
        memcpy(frame, p_val, len);
        if (app_ble_service_parse_ascii_frame(frame, &cmd) == RT_EOK)
        {
            (void)app_ble_service_submit_command(&cmd);
            app_ble_service_set_link_state(RT_TRUE, app_ble_service_get_runtime()->streaming_enabled);

            rt_snprintf(response, sizeof(response), "OK:%s\n", frame);
            memcpy(app_nus_tx, response, rt_strlen(response));
            app_nus_tx_len = (uint16_t)rt_strlen(response);
            rt_kprintf("[bt] Command accepted: %s\n", frame);
        }
        else
        {
            rt_snprintf(response, sizeof(response), "ERR:invalid\n");
            memcpy(app_nus_tx, response, rt_strlen(response));
            app_nus_tx_len = (uint16_t)rt_strlen(response);
            rt_kprintf("[bt] NUS cmd parse failed: %s\n", frame);
        }
        app_bt_nus_notify();
        return WICED_BT_GATT_SUCCESS;
    }

    default:
        return WICED_BT_GATT_WRITE_NOT_PERMIT;
    }
}

void app_bt_free_buffer(uint8_t *p_buf)
{
    if (p_buf != RT_NULL)
    {
        rt_free(p_buf);
    }
}

void *app_bt_alloc_buffer(int len)
{
    return rt_malloc((rt_size_t)len);
}

void app_bt_send_message(void)
{
    app_bt_nus_notify();
}

void app_bt_gatt_increment_notify_value(void)
{
    static const uint8_t ping[] = "ping\n";

    if ((hello_sensor_state.conn_id == 0u) || ((app_nus_tx_client_char_config[0] & GATT_CLIENT_CONFIG_NOTIFICATION) == 0u))
    {
        return;
    }

    memcpy(app_nus_tx, ping, sizeof(ping) - 1u);
    app_nus_tx_len = (uint16_t)(sizeof(ping) - 1u);
    app_bt_nus_notify();
}

rt_err_t bt_app_gatt_init(bt_app_gatt_adv_restart_t adv_restart_cb)
{
    wiced_bt_gatt_status_t status;

    g_bt_app_adv_restart_cb = adv_restart_cb;
    if (g_bt_app_gatt_ready)
    {
        return RT_EOK;
    }

    status = wiced_bt_gatt_register(app_bt_gatt_callback);
    rt_kprintf("[bt] GATT register status=0x%04X\n", status);
    if (status != WICED_BT_GATT_SUCCESS)
    {
        return -RT_ERROR;
    }

    status = wiced_bt_gatt_db_init(gatt_database, gatt_database_len, NULL);
    rt_kprintf("[bt] GATT db init status=0x%04X\n", status);
    if (status != WICED_BT_GATT_SUCCESS)
    {
        return -RT_ERROR;
    }

    g_bt_app_gatt_ready = RT_TRUE;
    return RT_EOK;
}

uint16_t bt_app_gatt_current_conn_id(void)
{
    return hello_sensor_state.conn_id;
}

uint32_t bt_app_gatt_event_count(void)
{
    return g_bt_app_gatt_event_count;
}
