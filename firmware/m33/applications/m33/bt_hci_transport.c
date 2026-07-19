#include "bt_hci_transport.h"
#include "bt_stack_adapter.h"
#include "app_bt_event_handler.h"

#include <rtdbg.h>

#include "cycfg_connectivity_bt.h"
#include "cycfg_pins.h"
#include "cybt_platform_config.h"
#include "cycfg_bt_settings.h"
#include "wiced_bt_stack.h"

#define DBG_TAG "bt.hci"
#define DBG_LVL DBG_INFO

#define BT_HCI_CFG_BAUD_DOWNLOAD   3000000U
#define BT_HCI_CFG_BAUD_FEATURE    115200U
#define BT_HCI_CFG_MEM_POOL_BYTES  2048U
#define BT_HCI_PIN(port, pin) ((cyhal_gpio_t)((((uint32_t)(port)) << 3U) | ((uint32_t)(pin) & 0x07U)))

static bt_hci_runtime_t g_bt_hci_runtime;

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

static void bt_hci_transport_set_runtime(bt_hci_state_t state, rt_err_t error)
{
    rt_base_t level = rt_hw_interrupt_disable();

    g_bt_hci_runtime.state = state;
    g_bt_hci_runtime.last_error = error;
    rt_hw_interrupt_enable(level);
}

rt_err_t bt_hci_transport_init(void)
{
    bt_hci_runtime_t runtime;
    rt_base_t level;

    rt_memset(&runtime, 0, sizeof(runtime));
    runtime.hci_uart_expected = RT_TRUE;
    runtime.dual_mode_expected = RT_TRUE;
    runtime.spp_expected = RT_TRUE;

    if (!bt_hci_stack_is_integrated())
    {
        runtime.state = BT_HCI_STATE_FAILED;
        runtime.last_error = -RT_ENOSYS;
        level = rt_hw_interrupt_disable();
        g_bt_hci_runtime = runtime;
        rt_hw_interrupt_enable(level);
        LOG_W("Bluetooth board config exists, but %s is missing", bt_stack_adapter_missing_piece());
        return runtime.last_error;
    }

    runtime.state = BT_HCI_STATE_OFF;
    runtime.last_error = RT_EOK;
    level = rt_hw_interrupt_disable();
    g_bt_hci_runtime = runtime;
    rt_hw_interrupt_enable(level);
    rt_kprintf("[bt.hci] transport configured\n");
    LOG_I("Bluetooth HCI transport configured for stack startup");
    return RT_EOK;
}

rt_err_t bt_hci_transport_start(void)
{
    bt_hci_runtime_t runtime;
    wiced_result_t result;

    (void)bt_hci_transport_get_runtime_snapshot(&runtime);
    if ((runtime.state == BT_HCI_STATE_STARTING) ||
        (runtime.state == BT_HCI_STATE_READY))
    {
        return RT_EOK;
    }
    if (runtime.state == BT_HCI_STATE_FAILED)
    {
        return (runtime.last_error != RT_EOK) ? runtime.last_error : -RT_ERROR;
    }

    if (!bt_hci_stack_is_integrated())
    {
        bt_hci_transport_set_runtime(BT_HCI_STATE_FAILED, -RT_ENOSYS);
        LOG_W("Skipping Bluetooth startup until %s is available", bt_stack_adapter_missing_piece());
        return -RT_ENOSYS;
    }

    rt_kprintf("[bt.hci] starting bring-up\n");
    LOG_I("Starting BTSTACK bring-up");
    cybt_platform_config_init(&g_bt_platform_cfg);
    bt_hci_transport_set_runtime(BT_HCI_STATE_STARTING, RT_EOK);
    result = wiced_bt_stack_init(app_bt_management_callback, &wiced_bt_cfg_settings);
    rt_kprintf("[bt.hci] wiced_bt_stack_init result=0x%08lx\n", (unsigned long)result);
    LOG_I("wiced_bt_stack_init result=0x%08lx", (unsigned long)result);

    if ((result != WICED_SUCCESS) && (result != WICED_PENDING) && (result != WICED_ALREADY_INITIALIZED))
    {
        bt_hci_transport_set_runtime(BT_HCI_STATE_FAILED, -RT_ERROR);
        return -RT_ERROR;
    }

    rt_kprintf("[bt.hci] stack start accepted; waiting for enabled event\n");
    LOG_I("Bluetooth stack start accepted; readiness is asynchronous");
    return RT_EOK;
}

void bt_hci_transport_report_enabled(rt_err_t status)
{
    rt_base_t level = rt_hw_interrupt_disable();

    if (status == RT_EOK)
    {
        if (g_bt_hci_runtime.state == BT_HCI_STATE_STARTING)
        {
            g_bt_hci_runtime.state = BT_HCI_STATE_READY;
            g_bt_hci_runtime.last_error = RT_EOK;
        }
    }
    else if (g_bt_hci_runtime.state == BT_HCI_STATE_STARTING)
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_FAILED;
        g_bt_hci_runtime.last_error = status;
    }
    rt_hw_interrupt_enable(level);
}

void bt_hci_transport_report_disabled(void)
{
    rt_base_t level = rt_hw_interrupt_disable();

    if ((g_bt_hci_runtime.state == BT_HCI_STATE_STARTING) ||
        (g_bt_hci_runtime.state == BT_HCI_STATE_READY))
    {
        g_bt_hci_runtime.state = BT_HCI_STATE_FAILED;
        g_bt_hci_runtime.last_error = -RT_ERROR;
    }
    rt_hw_interrupt_enable(level);
}

rt_err_t bt_hci_transport_get_runtime_snapshot(bt_hci_runtime_t *runtime)
{
    rt_base_t level;

    if (runtime == RT_NULL)
    {
        return -RT_EINVAL;
    }

    level = rt_hw_interrupt_disable();
    *runtime = g_bt_hci_runtime;
    rt_hw_interrupt_enable(level);
    return RT_EOK;
}

rt_bool_t bt_hci_transport_is_ready(void)
{
    bt_hci_runtime_t runtime;

    (void)bt_hci_transport_get_runtime_snapshot(&runtime);
    return runtime.state == BT_HCI_STATE_READY;
}
