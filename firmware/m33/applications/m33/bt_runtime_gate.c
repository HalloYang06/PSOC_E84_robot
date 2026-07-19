#include <finsh.h>
#include <rtthread.h>

#include "app_ble_diag.h"
#include "app_ble_service.h"
#include "bt_hci_transport.h"

#ifndef M33_ENABLE_APP_BLE_RUNTIME
#define M33_ENABLE_APP_BLE_RUNTIME 0
#endif

typedef enum
{
    M33_BLE_GATE_DISABLED = 0,
    M33_BLE_GATE_OFF,
    M33_BLE_GATE_STARTING,
    M33_BLE_GATE_READY,
    M33_BLE_GATE_FAILED,
} m33_ble_gate_state_t;

static struct rt_mutex g_m33_ble_gate_lock;
static rt_bool_t g_m33_ble_gate_lock_ready;
#if M33_ENABLE_APP_BLE_RUNTIME
static m33_ble_gate_state_t g_m33_ble_gate_state = M33_BLE_GATE_OFF;
static rt_err_t g_m33_ble_gate_last_error = RT_EOK;
#else
static m33_ble_gate_state_t g_m33_ble_gate_state = M33_BLE_GATE_DISABLED;
static rt_err_t g_m33_ble_gate_last_error = -RT_ENOSYS;
#endif

static int m33_ble_gate_init(void)
{
    rt_err_t ret;

    ret = rt_mutex_init(&g_m33_ble_gate_lock, "blegate", RT_IPC_FLAG_PRIO);
    if (ret == RT_EOK)
    {
        g_m33_ble_gate_lock_ready = RT_TRUE;
    }
    app_ble_diag_note_gate_state((rt_uint32_t)M33_ENABLE_APP_BLE_RUNTIME,
                                 (rt_uint32_t)g_m33_ble_gate_state,
                                 g_m33_ble_gate_last_error);
    return ret;
}
INIT_COMPONENT_EXPORT(m33_ble_gate_init);

static void m33_ble_gate_refresh_transport_state(void)
{
#if M33_ENABLE_APP_BLE_RUNTIME
    bt_hci_runtime_t hci;
    rt_bool_t changed = RT_FALSE;

    if (!g_m33_ble_gate_lock_ready)
    {
        return;
    }

    rt_mutex_take(&g_m33_ble_gate_lock, RT_WAITING_FOREVER);
    if (bt_hci_transport_get_runtime_snapshot(&hci) == RT_EOK)
    {
        if ((hci.state == BT_HCI_STATE_FAILED) &&
            ((g_m33_ble_gate_state == M33_BLE_GATE_STARTING) ||
             (g_m33_ble_gate_state == M33_BLE_GATE_READY)))
        {
            g_m33_ble_gate_state = M33_BLE_GATE_FAILED;
            g_m33_ble_gate_last_error = hci.last_error;
            changed = RT_TRUE;
        }
        else if ((hci.state == BT_HCI_STATE_READY) &&
                 (g_m33_ble_gate_state == M33_BLE_GATE_STARTING))
        {
            g_m33_ble_gate_state = M33_BLE_GATE_READY;
            g_m33_ble_gate_last_error = hci.last_error;
            changed = RT_TRUE;
        }
    }
    if (changed)
    {
        app_ble_diag_note_gate_state(1U,
                                     (rt_uint32_t)g_m33_ble_gate_state,
                                     g_m33_ble_gate_last_error);
    }
    rt_mutex_release(&g_m33_ble_gate_lock);
#endif
}

static rt_err_t m33_ble_gate_start(void)
{
#if M33_ENABLE_APP_BLE_RUNTIME
    rt_err_t ret;

    if (!g_m33_ble_gate_lock_ready)
    {
        return -RT_EBUSY;
    }

    m33_ble_gate_refresh_transport_state();
    rt_mutex_take(&g_m33_ble_gate_lock, RT_WAITING_FOREVER);
    if (g_m33_ble_gate_state == M33_BLE_GATE_READY)
    {
        rt_mutex_release(&g_m33_ble_gate_lock);
        return RT_EOK;
    }
    if (g_m33_ble_gate_state != M33_BLE_GATE_OFF)
    {
        ret = (g_m33_ble_gate_last_error != RT_EOK) ?
              g_m33_ble_gate_last_error :
              -RT_EBUSY;
        rt_mutex_release(&g_m33_ble_gate_lock);
        return ret;
    }
    g_m33_ble_gate_state = M33_BLE_GATE_STARTING;
    app_ble_diag_note_gate_state(1U,
                                 (rt_uint32_t)g_m33_ble_gate_state,
                                 g_m33_ble_gate_last_error);
    rt_mutex_release(&g_m33_ble_gate_lock);

    ret = app_ble_service_init();
    if (ret == RT_EOK)
    {
        ret = app_ble_service_start();
    }
    if (ret == RT_EOK)
    {
        ret = bt_hci_transport_init();
    }
    if (ret == RT_EOK)
    {
        ret = bt_hci_transport_start();
    }

    if (ret == RT_EOK)
    {
        m33_ble_gate_refresh_transport_state();
        rt_mutex_take(&g_m33_ble_gate_lock, RT_WAITING_FOREVER);
        if (g_m33_ble_gate_state == M33_BLE_GATE_FAILED)
        {
            ret = g_m33_ble_gate_last_error;
        }
        rt_mutex_release(&g_m33_ble_gate_lock);
    }
    else
    {
        rt_mutex_take(&g_m33_ble_gate_lock, RT_WAITING_FOREVER);
        g_m33_ble_gate_last_error = ret;
        g_m33_ble_gate_state = M33_BLE_GATE_FAILED;
        app_ble_diag_note_gate_state(1U,
                                     (rt_uint32_t)g_m33_ble_gate_state,
                                     g_m33_ble_gate_last_error);
        rt_mutex_release(&g_m33_ble_gate_lock);
    }
    return ret;
#else
    return -RT_ENOSYS;
#endif
}

static int cmd_m33_ble_start(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m33_ble_gate_start();
    rt_kprintf("BLE_GATE_START: enabled=%u state=%u ret=%d\n",
               (unsigned int)M33_ENABLE_APP_BLE_RUNTIME,
               (unsigned int)g_m33_ble_gate_state,
               ret);
    return ret;
}
MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_start, m33_ble_start, start guarded M33 BLE runtime once);

static int cmd_m33_ble_status(int argc, char **argv)
{
    m33_ble_gate_state_t gate_state;
    rt_err_t gate_error;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    m33_ble_gate_refresh_transport_state();
    if (g_m33_ble_gate_lock_ready)
    {
        rt_mutex_take(&g_m33_ble_gate_lock, RT_WAITING_FOREVER);
        gate_state = g_m33_ble_gate_state;
        gate_error = g_m33_ble_gate_last_error;
        rt_mutex_release(&g_m33_ble_gate_lock);
    }
    else
    {
        gate_state = g_m33_ble_gate_state;
        gate_error = g_m33_ble_gate_last_error;
    }

    rt_kprintf("BLE_GATE: enabled=%u lock=%u state=%u last_error=%d auto_start=0 restart=0\n",
               (unsigned int)M33_ENABLE_APP_BLE_RUNTIME,
               g_m33_ble_gate_lock_ready ? 1U : 0U,
               (unsigned int)gate_state,
               gate_error);
#if M33_ENABLE_APP_BLE_RUNTIME
    if (gate_state == M33_BLE_GATE_READY)
    {
        bt_hci_runtime_t hci;
        app_ble_runtime_t ble;

        rt_memset(&hci, 0, sizeof(hci));
        rt_memset(&ble, 0, sizeof(ble));
        (void)bt_hci_transport_get_runtime_snapshot(&hci);
        (void)app_ble_service_get_runtime_snapshot(&ble);

        rt_kprintf("BLE_GATE_RUNTIME: hci=%u hci_err=%d connected=%u streaming=%u up=%lu down=%lu\n",
                   (unsigned int)hci.state,
                   hci.last_error,
                   ble.connected ? 1U : 0U,
                   ble.streaming_enabled ? 1U : 0U,
                   (unsigned long)ble.uplink_packets,
                   (unsigned long)ble.downlink_packets);
    }
#endif
    return RT_EOK;
}
MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_status, m33_ble_status, show guarded M33 BLE runtime status);
