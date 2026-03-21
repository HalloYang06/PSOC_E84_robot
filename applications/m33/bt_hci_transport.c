#include "bt_hci_transport.h"
#include "bt_stack_adapter.h"
#include "app_bt_event_handler.h"

#include <rtdbg.h>

#include "cycfg_connectivity_bt.h"
#include "cycfg_pins.h"
#include "cybt_platform_config.h"
#include "cycfg_bt_settings.h"

#define DBG_TAG "bt.hci"
#define DBG_LVL DBG_INFO

#define BT_HCI_CFG_BAUD_DOWNLOAD   3000000U
#define BT_HCI_CFG_BAUD_FEATURE    115200U
#define BT_HCI_CFG_MEM_POOL_BYTES  2048U
#define BT_HCI_PIN(port, pin) ((cyhal_gpio_t)((((uint32_t)(port)) << 3U) | ((uint32_t)(pin) & 0x07U)))

static bt_hci_runtime_t g_bt_hci_runtime;
static rt_bool_t g_bt_stack_started = RT_FALSE;

static const cybt_platform_config_t g_bt_platform_cfg =
{
    .hci_config =
    {
        .hci_transport = CYBT_HCI_UART,
        .hci =
        {
            .hci_uart =
            {
                .uart_tx_pin = BT_HCI_PIN(CYBSP_BT_UART_TX_PORT_NUM, CYBSP_BT_UART_TX_PIN),
                .uart_rx_pin = BT_HCI_PIN(CYBSP_BT_UART_RX_PORT_NUM, CYBSP_BT_UART_RX_PIN),
                .uart_rts_pin = BT_HCI_PIN(CYBSP_BT_UART_RTS_PORT_NUM, CYBSP_BT_UART_RTS_PIN),
                .uart_cts_pin = BT_HCI_PIN(CYBSP_BT_UART_CTS_PORT_NUM, CYBSP_BT_UART_CTS_PIN),
                .baud_rate_for_fw_download = BT_HCI_CFG_BAUD_DOWNLOAD,
                .baud_rate_for_feature = BT_HCI_CFG_BAUD_FEATURE,
                .data_bits = 8,
                .stop_bits = 1,
                .parity = CYHAL_UART_PARITY_NONE,
                .flow_control = true,
            },
        },
    },
    .controller_config =
    {
        .bt_power_pin = BT_HCI_PIN(CYBSP_BT_POWER_PORT_NUM, CYBSP_BT_POWER_PIN),
        .sleep_mode =
        {
                .sleep_mode_enabled = CYBT_SLEEP_MODE_DISABLED,
            .device_wakeup_pin = BT_HCI_PIN(CYBSP_BT_DEVICE_WAKE_PORT_NUM, CYBSP_BT_DEVICE_WAKE_PIN),
            .host_wakeup_pin = BT_HCI_PIN(CYBSP_BT_HOST_WAKE_PORT_NUM, CYBSP_BT_HOST_WAKE_PIN),
            .device_wake_polarity = CYBT_WAKE_ACTIVE_LOW,
            .host_wake_polarity = CYBT_WAKE_ACTIVE_HIGH,
        },
    },
    .task_mem_pool_size = BT_HCI_CFG_MEM_POOL_BYTES,
};

static rt_bool_t bt_hci_stack_is_integrated(void)
{
    bt_stack_probe_t probe;

    return (bt_stack_adapter_probe(&probe) == RT_EOK) &&
           (probe.status == BT_STACK_STATUS_PRESENT ||
            probe.status == BT_STACK_STATUS_PORTING_REQUIRED ||
            probe.status == BT_STACK_STATUS_PROFILE_REQUIRED);
}

rt_err_t bt_hci_transport_init(void)
{
    rt_memset(&g_bt_hci_runtime, 0, sizeof(g_bt_hci_runtime));
    g_bt_hci_runtime.hci_uart_expected = RT_TRUE;
    g_bt_hci_runtime.dual_mode_expected = RT_TRUE;
    g_bt_hci_runtime.spp_expected = RT_TRUE;

    if (!bt_hci_stack_is_integrated())
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_STACK_MISSING;
        g_bt_hci_runtime.last_error = -RT_ENOSYS;
        LOG_W("Bluetooth board config exists, but %s is missing", bt_stack_adapter_missing_piece());
        return g_bt_hci_runtime.last_error;
    }

    g_bt_hci_runtime.state = BT_HCI_STATE_READY;
    g_bt_hci_runtime.last_error = RT_EOK;
    LOG_I("Bluetooth HCI transport layer ready for stack startup");
    return RT_EOK;
}

rt_err_t bt_hci_transport_start(void)
{
    wiced_result_t result;

    if (g_bt_hci_runtime.state == BT_HCI_STATE_UNINITIALIZED)
    {
        bt_hci_transport_init();
    }

    if (!bt_hci_stack_is_integrated())
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_STACK_MISSING;
        g_bt_hci_runtime.last_error = -RT_ENOSYS;
        LOG_W("Skipping Bluetooth startup until %s is available", bt_stack_adapter_missing_piece());
        return g_bt_hci_runtime.last_error;
    }

    if (g_bt_stack_started)
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_RUNNING;
        g_bt_hci_runtime.last_error = RT_EOK;
        return RT_EOK;
    }

    LOG_I("Starting BTSTACK bring-up");
    cybt_platform_config_init(&g_bt_platform_cfg);
    result = wiced_bt_stack_init(app_bt_management_callback, &wiced_bt_cfg_settings);
    LOG_I("wiced_bt_stack_init result=0x%08lx", (unsigned long)result);

    if ((result != WICED_SUCCESS) && (result != WICED_PENDING) && (result != WICED_ALREADY_INITIALIZED))
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_ERROR;
        g_bt_hci_runtime.last_error = -RT_ERROR;
        return g_bt_hci_runtime.last_error;
    }

    g_bt_stack_started = RT_TRUE;
    g_bt_hci_runtime.state = BT_HCI_STATE_RUNNING;
    g_bt_hci_runtime.last_error = RT_EOK;
    LOG_I("Bluetooth HCI transport started");
    return RT_EOK;
}

const bt_hci_runtime_t *bt_hci_transport_get_runtime(void)
{
    return &g_bt_hci_runtime;
}

rt_bool_t bt_hci_transport_is_ready(void)
{
    return (g_bt_hci_runtime.state == BT_HCI_STATE_READY) ||
           (g_bt_hci_runtime.state == BT_HCI_STATE_RUNNING);
}
