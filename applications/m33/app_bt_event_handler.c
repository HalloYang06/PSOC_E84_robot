#include "app_bt_event_handler.h"

#include <string.h>
#include <rtthread.h>

#include "app_bt_bonding.h"
#include "app_bt_utils.h"
#include "bt_app_gatt_handler.h"
#include "cycfg_gap.h"

hello_sensor_state_t hello_sensor_state;
uint8_t bondindex = 0u;
static wiced_bt_device_address_t g_local_bda = {0x00, 0xA0, 0x50, 0x11, 0x44, 0x77};
static rt_bool_t g_bt_app_initialized = RT_FALSE;
static rt_timer_t g_bt_alive_timer = RT_NULL;

static void app_bt_alive_timer_cb(void *parameter)
{
    RT_UNUSED(parameter);
    // Heartbeat disabled to reduce log spam
    // Uncomment below if needed for debugging
    /*
    rt_kprintf("[bt] alive conn_id=%u mtu=%u gatt_evt_count=%lu pairing=%u\n",
               (unsigned int)hello_sensor_state.conn_id,
               (unsigned int)hello_sensor_state.peer_mtu,
               (unsigned long)bt_app_gatt_event_count(),
               (unsigned int)pairing_mode);
    */
}

void app_bt_alive_probe_start(void)
{
    if (g_bt_alive_timer != RT_NULL)
    {
        return;
    }

    g_bt_alive_timer = rt_timer_create("btalive",
                                       app_bt_alive_timer_cb,
                                       RT_NULL,
                                       rt_tick_from_millisecond(2000),
                                       RT_TIMER_FLAG_PERIODIC | RT_TIMER_FLAG_SOFT_TIMER);
    if (g_bt_alive_timer != RT_NULL)
    {
        rt_timer_start(g_bt_alive_timer);
    }
}

void app_bt_application_init(void)
{
    wiced_result_t result;

    if (g_bt_app_initialized)
    {
        return;
    }
    g_bt_app_initialized = RT_TRUE;

    memset(&hello_sensor_state, 0, sizeof(hello_sensor_state));

    wiced_bt_set_pairable_mode(WICED_TRUE, FALSE);

    result = wiced_bt_ble_set_raw_advertisement_data(CY_BT_ADV_PACKET_DATA_SIZE,
                                                     cy_bt_adv_packet_data);
    rt_kprintf("[bt] Set adv data result=0x%08lx\n", (unsigned long)result);
    if (result != WICED_BT_SUCCESS)
    {
        return;
    }

    if (bt_app_gatt_init(app_bt_adv_stop_handler) != RT_EOK)
    {
        rt_kprintf("[bt] app gatt init failed\n");
        return;
    }

    result = wiced_bt_start_advertisements(BTM_BLE_ADVERT_UNDIRECTED_HIGH, 0, NULL);
    rt_kprintf("[bt] Start adv result=0x%08lx\n", (unsigned long)result);
}

void app_bt_adv_stop_handler(void)
{
    wiced_result_t result;

    if ((hello_sensor_state.conn_id == 0u) && (!pairing_mode))
    {
        result = wiced_bt_start_advertisements(BTM_BLE_ADVERT_UNDIRECTED_HIGH, 0, NULL);
        rt_kprintf("[bt] Restart adv result=0x%08lx\n", (unsigned long)result);
    }
}

wiced_result_t app_bt_management_callback(wiced_bt_management_evt_t event,
                                          wiced_bt_management_evt_data_t *p_event_data)
{
    wiced_result_t result = WICED_BT_SUCCESS;

    switch (event)
    {
    case BTM_ENABLED_EVT:
        if ((p_event_data != RT_NULL) && (p_event_data->enabled.status == WICED_BT_SUCCESS))
        {
            memcpy(cy_bt_device_address, g_local_bda, sizeof(g_local_bda));
            wiced_bt_set_local_bdaddr(g_local_bda, BLE_ADDR_PUBLIC);
            wiced_bt_dev_read_local_addr(cy_bt_device_address);
            rt_kprintf("[bt] Bluetooth stack ready\n");
            rt_kprintf("[bt] Local addr %02X:%02X:%02X:%02X:%02X:%02X\n",
                       cy_bt_device_address[0], cy_bt_device_address[1], cy_bt_device_address[2],
                       cy_bt_device_address[3], cy_bt_device_address[4], cy_bt_device_address[5]);
            app_bt_alive_probe_start();
            app_bt_application_init();
        }
        else
        {
            rt_kprintf("[bt] BTSTACK enable failed status=0x%02X\n",
                       (p_event_data != RT_NULL) ? p_event_data->enabled.status : 0xFFu);
        }
        break;

    case BTM_DISABLED_EVT:
        rt_kprintf("[bt] BTSTACK disabled\n");
        break;

    case BTM_PAIRING_IO_CAPABILITIES_BLE_REQUEST_EVT:
        if (p_event_data != RT_NULL)
        {
            p_event_data->pairing_io_capabilities_ble_request.local_io_cap = BTM_IO_CAPABILITIES_NONE;
            p_event_data->pairing_io_capabilities_ble_request.oob_data = BTM_OOB_NONE;
            p_event_data->pairing_io_capabilities_ble_request.auth_req = BTM_LE_AUTH_REQ_SC_BOND;
            p_event_data->pairing_io_capabilities_ble_request.max_key_size = 0x10;
            p_event_data->pairing_io_capabilities_ble_request.init_keys =
                BTM_LE_KEY_PENC | BTM_LE_KEY_PID | BTM_LE_KEY_PCSRK | BTM_LE_KEY_LENC;
            p_event_data->pairing_io_capabilities_ble_request.resp_keys =
                BTM_LE_KEY_PENC | BTM_LE_KEY_PID | BTM_LE_KEY_PCSRK | BTM_LE_KEY_LENC;
        }
        break;

    case BTM_PAIRING_COMPLETE_EVT:
        if ((p_event_data != RT_NULL) && (p_event_data->pairing_complete.transport == BT_TRANSPORT_LE))
        {
            rt_kprintf("[bt] BLE pairing complete reason=0x%02X sec_level=%u\n",
                       p_event_data->pairing_complete.pairing_complete_info.ble.reason,
                       (unsigned int)p_event_data->pairing_complete.pairing_complete_info.ble.sec_level);
        }
        break;

    case BTM_BLE_ADVERT_STATE_CHANGED_EVT:
        if ((p_event_data != RT_NULL) &&
            (p_event_data->ble_advert_state_changed == BTM_BLE_ADVERT_OFF))
        {
            app_bt_adv_stop_handler();
        }
        break;

    case BTM_PAIRED_DEVICE_LINK_KEYS_UPDATE_EVT:
        result = WICED_BT_SUCCESS;
        break;

    case BTM_PAIRED_DEVICE_LINK_KEYS_REQUEST_EVT:
        result = WICED_BT_ERROR;
        break;

    case BTM_LOCAL_IDENTITY_KEYS_UPDATE_EVT:
        result = WICED_BT_SUCCESS;
        break;

    case BTM_LOCAL_IDENTITY_KEYS_REQUEST_EVT:
        result = WICED_BT_ERROR;
        break;

    case BTM_ENCRYPTION_STATUS_EVT:
        if ((p_event_data != RT_NULL) && (p_event_data->encryption_status.transport == BT_TRANSPORT_LE))
        {
            rt_kprintf("[bt] BLE encryption result=0x%08lx\n",
                       (unsigned long)p_event_data->encryption_status.result);
        }
        break;

    case BTM_SECURITY_REQUEST_EVT:
        if (p_event_data != RT_NULL)
        {
            wiced_bt_ble_security_grant(p_event_data->security_request.bd_addr, WICED_BT_SUCCESS);
            rt_kprintf("[bt] BLE security request granted\n");
        }
        break;

    case BTM_SECURITY_FAILED_EVT:
        if (p_event_data != RT_NULL)
        {
            rt_kprintf("[bt] BLE security failed status=0x%08lx hci=0x%02X\n",
                       (unsigned long)p_event_data->security_failed.status,
                       p_event_data->security_failed.hci_status);
        }
        break;

    default:
        break;
    }

    return result;
}

