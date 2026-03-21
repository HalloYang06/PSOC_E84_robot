#include <rtthread.h>
#include <stdarg.h>
#include <string.h>

#include "cyhal_uart.h"
#include "cyhal_gpio.h"
#include "cybt_platform_interface.h"
#include "cybt_platform_task.h"
#include "cybt_platform_hci.h"
#include "cybt_platform_trace.h"
#include "cybt_platform_config.h"

#define BT_HCI_LOG(fmt, ...) rt_kprintf("[bt.hci] " fmt "\n", ##__VA_ARGS__)
#define BT_HCI_VLOG(...) ((void)0)

#define BT_HCI_DUMP_MAX 8U

#ifdef COMPONENT_55500
static void cybt_enter_autobaud_mode(void);
#endif

static void bt_hci_dump_bytes(const char *tag, const uint8_t *data, uint32_t length)
{
    char line[96];
    int offset = 0;
    uint32_t i;
    uint32_t dump_len = (length < BT_HCI_DUMP_MAX) ? length : BT_HCI_DUMP_MAX;

    if (data == RT_NULL)
    {
        BT_HCI_LOG("%s data=null len=%lu", tag, (unsigned long)length);
        return;
    }

    offset = rt_snprintf(line, sizeof(line), "%s len=%lu data=", tag, (unsigned long)length);
    for (i = 0; (i < dump_len) && (offset > 0) && (offset < (int)(sizeof(line) - 4)); ++i)
    {
        offset += rt_snprintf(&line[offset], sizeof(line) - (size_t)offset, "%02X ", data[i]);
    }

    if (length > dump_len)
    {
        rt_snprintf(&line[offset], sizeof(line) - (size_t)offset, "...");
    }

    BT_HCI_LOG("%s", line);
}

static bool bt_hci_is_write_ram_packet(const uint8_t *data, uint32_t length)
{
    return (data != RT_NULL) && (length >= 3u) && (data[0] == 0x01u) && (data[1] == 0x4Cu) && (data[2] == 0xFCu);
}

static bool bt_hci_is_write_ram_ack(const uint8_t *data, uint32_t length)
{
    return (data != RT_NULL) && (length >= 4u) && (data[0] == 0x01u) && (data[1] == 0x4Cu) && (data[2] == 0xFCu);
}

extern bool cybt_platform_get_sleep_mode_status(void);
extern const cybt_platform_config_t *cybt_platform_get_config(void);

cy_queue_t cybt_task_queue[BT_TASK_NUM] = {0};
cy_thread_t cybt_task[BT_TASK_NUM] = {0};

static void *g_rx_mem = RT_NULL;
static BT_MSG_HDR *g_tx_cmd_mem = RT_NULL;
static rt_base_t g_irq_level = 0;
static rt_uint32_t g_irq_nesting = 0;
static uint32_t g_patch_write_seq = 0;
static uint32_t g_patch_ack_seq = 0;

typedef struct
{
    bool inited;
    cyhal_uart_t hal_obj;
    cy_mutex_t tx_atomic;
    cy_mutex_t rx_atomic;
#if (CYHAL_API_VERSION >= 2)
    cyhal_gpio_callback_data_t host_wake_cb_data;
#endif
} hci_uart_cb_t;

static hci_uart_cb_t g_hci_uart_cb;

extern void cybt_hci_rx_task(cy_thread_arg_t arg);
extern void cybt_hci_tx_task(cy_thread_arg_t arg);

static cybt_result_t cybt_init_queue_if_needed(cy_queue_t *queue, size_t count, size_t item_size)
{
    cy_rslt_t result;

    if (*queue != RT_NULL)
    {
        return CYBT_SUCCESS;
    }

    result = cy_rtos_init_queue(queue, count, item_size);
    return (result == CY_RSLT_SUCCESS) ? CYBT_SUCCESS : CYBT_ERR_INIT_QUEUE_FAILED;
}

static void cybt_uart_rx_not_empty(void)
{
    cyhal_uart_enable_event(&g_hci_uart_cb.hal_obj,
                            CYHAL_UART_IRQ_RX_NOT_EMPTY,
                            CYHAL_ISR_PRIORITY_DEFAULT,
                            false);
    (void)cybt_send_msg_to_hci_rx_task(BT_IND_TO_HCI_DATA_READY_UNKNOWN, true);
}

static void cybt_uart_irq_handler(void *handler_arg, cyhal_uart_event_t event)
{
    RT_UNUSED(handler_arg);

    if ((event & CYHAL_UART_IRQ_RX_NOT_EMPTY) != 0)
    {
        cybt_uart_rx_not_empty();
    }
}

void cybt_platform_assert_bt_wake(void)
{
    const cybt_platform_config_t *cfg;
    bool wake_polarity;

    if (!cybt_platform_get_sleep_mode_status())
    {
        return;
    }

    cfg = cybt_platform_get_config();
    if ((cfg == RT_NULL) || (NC == cfg->controller_config.sleep_mode.device_wakeup_pin))
    {
        return;
    }

    wake_polarity = (cfg->controller_config.sleep_mode.device_wake_polarity == CYBT_WAKE_ACTIVE_HIGH);
    cyhal_gpio_write(cfg->controller_config.sleep_mode.device_wakeup_pin, wake_polarity);
}

void cybt_platform_deassert_bt_wake(void)
{
    const cybt_platform_config_t *cfg;
    bool sleep_polarity;

    if (!cybt_platform_get_sleep_mode_status())
    {
        return;
    }

    cfg = cybt_platform_get_config();
    if ((cfg == RT_NULL) || (NC == cfg->controller_config.sleep_mode.device_wakeup_pin))
    {
        return;
    }

    sleep_polarity = (cfg->controller_config.sleep_mode.device_wake_polarity == CYBT_WAKE_ACTIVE_LOW);
    cyhal_gpio_write(cfg->controller_config.sleep_mode.device_wakeup_pin, sleep_polarity);
}

static void cybt_host_wake_irq_handler(void *callback_arg, cyhal_gpio_event_t event)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    RT_UNUSED(callback_arg);

    if (cfg == RT_NULL)
    {
        return;
    }

    switch (event)
    {
    case CYHAL_GPIO_IRQ_RISE:
        if (cfg->controller_config.sleep_mode.host_wake_polarity == CYBT_WAKE_ACTIVE_HIGH)
        {
            cybt_platform_sleep_lock();
        }
        else
        {
            cybt_platform_sleep_unlock();
        }
        break;
    case CYHAL_GPIO_IRQ_FALL:
        if (cfg->controller_config.sleep_mode.host_wake_polarity == CYBT_WAKE_ACTIVE_LOW)
        {
            cybt_platform_sleep_lock();
        }
        else
        {
            cybt_platform_sleep_unlock();
        }
        break;
    default:
        break;
    }
}

void cybt_platform_init(void)
{
    memset(&g_hci_uart_cb, 0, sizeof(g_hci_uart_cb));
}

void cybt_platform_deinit(void)
{
}

void *cybt_platform_malloc(uint32_t req_size)
{
    return rt_malloc(req_size);
}

void cybt_platform_free(void *p_mem_block)
{
    if (p_mem_block != RT_NULL)
    {
        rt_free(p_mem_block);
    }
}

void cybt_platform_disable_irq(void)
{
    if (g_irq_nesting++ == 0)
    {
        g_irq_level = rt_hw_interrupt_disable();
    }
}

void cybt_platform_enable_irq(void)
{
    if ((g_irq_nesting > 0) && (--g_irq_nesting == 0))
    {
        rt_hw_interrupt_enable(g_irq_level);
    }
}

void cybt_platform_log_print(const char *fmt_str, ...)
{
    va_list args;
    char buffer[256];

    va_start(args, fmt_str);
    rt_vsnprintf(buffer, sizeof(buffer), fmt_str, args);
    va_end(args);
    rt_kprintf("%s", buffer);
}

void cybt_platform_sleep_lock(void)
{
}

void cybt_platform_sleep_unlock(void)
{
}

uint64_t cybt_platform_get_tick_count_us(void)
{
    uint64_t ticks = (uint64_t)rt_tick_get();
    return (ticks * 1000000ULL) / RT_TICK_PER_SECOND;
}

void cybt_platform_set_next_timeout(uint64_t abs_tick_us_to_expire)
{
    RT_UNUSED(abs_tick_us_to_expire);
}

cybt_result_t cybt_platform_task_init(void *p_arg)
{
    cy_rslt_t result;

    RT_UNUSED(p_arg);

    if (CYBT_SUCCESS != cybt_init_queue_if_needed(&HCI_RX_TASK_QUEUE, HCI_RX_TASK_QUEUE_COUNT, HCI_RX_TASK_QUEUE_ITEM_SIZE))
    {
        return CYBT_ERR_INIT_QUEUE_FAILED;
    }

    if (CYBT_SUCCESS != cybt_init_queue_if_needed(&HCI_TX_TASK_QUEUE, HCI_TX_TASK_QUEUE_COUNT, HCI_TX_TASK_QUEUE_ITEM_SIZE))
    {
        return CYBT_ERR_INIT_QUEUE_FAILED;
    }

    if ((g_rx_mem == RT_NULL) && ((g_rx_mem = rt_malloc(CYBT_RX_MEM_MIN_SIZE)) == RT_NULL))
    {
        return CYBT_ERR_OUT_OF_MEMORY;
    }

    if ((g_tx_cmd_mem == RT_NULL) && ((g_tx_cmd_mem = (BT_MSG_HDR *)rt_malloc(CYBT_TX_CMD_MEM_MIN_SIZE)) == RT_NULL))
    {
        return CYBT_ERR_OUT_OF_MEMORY;
    }

    if (cybt_task[BT_TASK_ID_HCI_TX] == RT_NULL)
    {
        result = cy_rtos_create_thread(&cybt_task[BT_TASK_ID_HCI_TX],
                                       cybt_hci_tx_task,
                                       BT_TASK_NAME_HCI_TX,
                                       RT_NULL,
                                       HCI_TX_TASK_STACK_SIZE,
                                       HCI_TX_TASK_PRIORITY,
                                       (cy_thread_arg_t)0);
        if (result != CY_RSLT_SUCCESS)
        {
            return CYBT_ERR_CREATE_TASK_FAILED;
        }
    }

    if (cybt_task[BT_TASK_ID_HCI_RX] == RT_NULL)
    {
        result = cy_rtos_create_thread(&cybt_task[BT_TASK_ID_HCI_RX],
                                       cybt_hci_rx_task,
                                       BT_TASK_NAME_HCI_RX,
                                       RT_NULL,
                                       HCI_RX_TASK_STACK_SIZE,
                                       HCI_RX_TASK_PRIORITY,
                                       (cy_thread_arg_t)0);
        if (result != CY_RSLT_SUCCESS)
        {
            return CYBT_ERR_CREATE_TASK_FAILED;
        }
    }

    return CYBT_SUCCESS;
}

cybt_result_t cybt_platform_task_deinit(void)
{
    if (HCI_RX_TASK_QUEUE != RT_NULL)
    {
        cy_rtos_deinit_queue(&HCI_RX_TASK_QUEUE);
    }

    if (HCI_TX_TASK_QUEUE != RT_NULL)
    {
        cy_rtos_deinit_queue(&HCI_TX_TASK_QUEUE);
    }

    if (g_rx_mem != RT_NULL)
    {
        rt_free(g_rx_mem);
        g_rx_mem = RT_NULL;
    }

    if (g_tx_cmd_mem != RT_NULL)
    {
        rt_free(g_tx_cmd_mem);
        g_tx_cmd_mem = RT_NULL;
    }
    return CYBT_SUCCESS;
}

cybt_result_t cybt_platform_task_mempool_init(uint32_t total_size)
{
    RT_UNUSED(total_size);
    return CYBT_SUCCESS;
}

void *cybt_platform_task_tx_mempool_alloc(uint32_t req_size)
{
    return rt_malloc(req_size);
}

void *cybt_platform_task_get_tx_cmd_mem(void)
{
    return g_tx_cmd_mem;
}

void *cybt_platform_task_get_rx_mem(void)
{
    return g_rx_mem;
}

void cybt_platform_task_mempool_free(void *p_mem_block)
{
    if ((p_mem_block != RT_NULL) && (p_mem_block != g_rx_mem) && (p_mem_block != g_tx_cmd_mem))
    {
        rt_free(p_mem_block);
    }
}

void cybt_platform_task_mempool_deinit(void)
{
}

uint8_t cybt_platform_task_get_queue_utilization(uint8_t task_id)
{
    size_t used = 0;
    size_t total = 0;
    cy_queue_t *queue = RT_NULL;

    if (task_id >= BT_TASK_NUM)
    {
        return CYBT_INVALID_QUEUE_UTILIZATION;
    }

    queue = &cybt_task_queue[task_id];
    if (*queue == RT_NULL)
    {
        return 0;
    }

    if (cy_rtos_count_queue(queue, &used) != CY_RSLT_SUCCESS)
    {
        return CYBT_INVALID_QUEUE_UTILIZATION;
    }

    total = (task_id == BT_TASK_ID_HCI_RX) ? HCI_RX_TASK_QUEUE_COUNT : HCI_TX_TASK_QUEUE_COUNT;
    return (uint8_t)((used * 100u) / total);
}

uint8_t cybt_platform_task_get_tx_heap_utilization(uint16_t *p_largest_free_size)
{
    if (p_largest_free_size != RT_NULL)
    {
        *p_largest_free_size = 0;
    }

    return 0;
}

void cybt_platform_terminate_hci_tx_thread(void)
{
}

void cybt_platform_terminate_hci_rx_thread(void)
{
}

cybt_result_t cybt_platform_hci_open(void *p_arg)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();
    cyhal_uart_cfg_t bt_uart_cfg = {0};
    cy_rslt_t result;
    uint32_t actual_baud = 0;

    RT_UNUSED(p_arg);

    if (g_hci_uart_cb.inited)
    {
        return CYBT_SUCCESS;
    }

    if (cfg == RT_NULL)
    {
        return CYBT_ERR_GENERIC;
    }

    memset(&g_hci_uart_cb, 0, sizeof(g_hci_uart_cb));

    if (cy_rtos_mutex_init(&g_hci_uart_cb.tx_atomic, false) != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_HCI_GET_TX_MUTEX_FAILED;
    }

    if (cy_rtos_mutex_init(&g_hci_uart_cb.rx_atomic, false) != CY_RSLT_SUCCESS)
    {
        cy_rtos_mutex_deinit(&g_hci_uart_cb.tx_atomic);
        return CYBT_ERR_HCI_GET_RX_MUTEX_FAILED;
    }

    if ((CYBT_SLEEP_MODE_ENABLED == cfg->controller_config.sleep_mode.sleep_mode_enabled) &&
        (NC != cfg->controller_config.sleep_mode.device_wakeup_pin))
    {
        result = cyhal_gpio_init(cfg->controller_config.sleep_mode.device_wakeup_pin,
                                 CYHAL_GPIO_DIR_OUTPUT,
                                 CYHAL_GPIO_DRIVE_STRONG,
                                 false);
        if (result != CY_RSLT_SUCCESS)
        {
            return CYBT_ERR_GPIO_DEV_WAKE_INIT_FAILED;
        }
    }

    result = cyhal_gpio_init(cfg->controller_config.bt_power_pin,
                             CYHAL_GPIO_DIR_OUTPUT,
                             CYHAL_GPIO_DRIVE_PULLUP,
                             true);
    if (result != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_GPIO_POWER_INIT_FAILED;
    }

#ifdef COMPONENT_55500
    cybt_enter_autobaud_mode();
#else
    rt_thread_mdelay(30);
#endif

    bt_uart_cfg.data_bits = cfg->hci_config.hci.hci_uart.data_bits;
    bt_uart_cfg.stop_bits = cfg->hci_config.hci.hci_uart.stop_bits;
    bt_uart_cfg.parity = cfg->hci_config.hci.hci_uart.parity;
    bt_uart_cfg.rx_buffer = RT_NULL;
    bt_uart_cfg.rx_buffer_size = 0;

    result = cyhal_uart_init(&g_hci_uart_cb.hal_obj,
                             cfg->hci_config.hci.hci_uart.uart_tx_pin,
                             cfg->hci_config.hci.hci_uart.uart_rx_pin,
                             cfg->hci_config.hci.hci_uart.uart_cts_pin,
                             cfg->hci_config.hci.hci_uart.uart_rts_pin,
                             RT_NULL,
                             &bt_uart_cfg);
    if (result != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_HCI_INIT_FAILED;
    }

#ifdef COMPONENT_55500
    result = cyhal_uart_set_baud(&g_hci_uart_cb.hal_obj,
                                 cfg->hci_config.hci.hci_uart.baud_rate_for_fw_download,
                                 &actual_baud);
#else
    result = cyhal_uart_set_baud(&g_hci_uart_cb.hal_obj, HCI_UART_DEFAULT_BAUDRATE, &actual_baud);
#endif
    if (result != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_HCI_SET_BAUDRATE_FAILED;
    }

    rt_thread_mdelay(10);

    if (cfg->hci_config.hci.hci_uart.flow_control)
    {
        result = cyhal_uart_enable_flow_control(&g_hci_uart_cb.hal_obj, true, true);
        if (result != CY_RSLT_SUCCESS)
        {
            return CYBT_ERR_HCI_SET_FLOW_CTRL_FAILED;
        }
    }

#if (CYHAL_API_VERSION >= 2)
    if ((CYBT_SLEEP_MODE_ENABLED == cfg->controller_config.sleep_mode.sleep_mode_enabled) &&
        (NC != cfg->controller_config.sleep_mode.host_wakeup_pin))
    {
        g_hci_uart_cb.host_wake_cb_data.callback = cybt_host_wake_irq_handler;
        g_hci_uart_cb.host_wake_cb_data.callback_arg = RT_NULL;
        g_hci_uart_cb.host_wake_cb_data.next = RT_NULL;
        g_hci_uart_cb.host_wake_cb_data.pin = NC;
        cyhal_gpio_register_callback(cfg->controller_config.sleep_mode.host_wakeup_pin,
                                     &g_hci_uart_cb.host_wake_cb_data);
        cyhal_gpio_enable_event(cfg->controller_config.sleep_mode.host_wakeup_pin,
                                CYHAL_GPIO_IRQ_BOTH,
                                CYHAL_ISR_PRIORITY_DEFAULT,
                                true);
    }
#endif

    cyhal_uart_register_callback(&g_hci_uart_cb.hal_obj, cybt_uart_irq_handler, RT_NULL);
    cyhal_uart_enable_event(&g_hci_uart_cb.hal_obj,
                            CYHAL_UART_IRQ_RX_NOT_EMPTY,
                            CYHAL_ISR_PRIORITY_DEFAULT,
                            true);

    if (cfg->hci_config.hci.hci_uart.flow_control &&
        (cfg->hci_config.hci.hci_uart.uart_cts_pin != NC))
    {
        while (cyhal_gpio_read(cfg->hci_config.hci.hci_uart.uart_cts_pin))
        {
            rt_thread_mdelay(10);
        }
    }

    g_hci_uart_cb.inited = true;

    if ((CYBT_SLEEP_MODE_ENABLED == cfg->controller_config.sleep_mode.sleep_mode_enabled) &&
        (NC != cfg->controller_config.sleep_mode.host_wakeup_pin))
    {
        bool host_asserted = cyhal_gpio_read(cfg->controller_config.sleep_mode.host_wakeup_pin);
        bool host_active_high = (cfg->controller_config.sleep_mode.host_wake_polarity == CYBT_WAKE_ACTIVE_HIGH);
        if ((host_active_high && host_asserted) || (!host_active_high && !host_asserted))
        {
            cybt_uart_rx_not_empty();
        }
    }

    BT_HCI_LOG("open ok baud=%lu flow=%d", (unsigned long)actual_baud, cfg->hci_config.hci.hci_uart.flow_control);
    return CYBT_SUCCESS;
}

#ifdef COMPONENT_55500
static void cybt_enter_autobaud_mode(void)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    if (cfg == RT_NULL)
    {
        return;
    }


    cyhal_gpio_init(cfg->hci_config.hci.hci_uart.uart_rts_pin,
                    CYHAL_GPIO_DIR_OUTPUT,
                    CYHAL_GPIO_DRIVE_STRONG,
                    true);
    cyhal_gpio_write(cfg->hci_config.hci.hci_uart.uart_rts_pin, false);

    cyhal_gpio_write(cfg->controller_config.bt_power_pin, false);
    rt_thread_mdelay(100);
    cyhal_gpio_write(cfg->controller_config.bt_power_pin, true);
    rt_thread_mdelay(100);

    cyhal_gpio_free(cfg->hci_config.hci.hci_uart.uart_rts_pin);
}
#endif

cybt_result_t cybt_platform_hci_set_baudrate(uint32_t baudrate)
{
    uint32_t actual_baud = 0;

    if (!g_hci_uart_cb.inited)
    {
        return CYBT_ERR_HCI_NOT_INITIALIZE;
    }

    if (cyhal_uart_set_baud(&g_hci_uart_cb.hal_obj, baudrate, &actual_baud) == CY_RSLT_SUCCESS)
    {
        return CYBT_SUCCESS;
    }

    BT_HCI_LOG("set baud failed req=%lu", (unsigned long)baudrate);
    return CYBT_ERR_HCI_SET_BAUDRATE_FAILED;
}

cybt_result_t cybt_platform_hci_write(hci_packet_type_t type, uint8_t *p_data, uint32_t length)
{
    size_t chunk_len;
    size_t total_written;
    cy_rslt_t result;
    int attempt;

    RT_UNUSED(type);

    if (!g_hci_uart_cb.inited)
    {
        return CYBT_ERR_HCI_NOT_INITIALIZE;
    }

    if ((p_data == RT_NULL) || (length == 0))
    {
        return CYBT_ERR_BADARG;
    }

    if (cy_rtos_mutex_get(&g_hci_uart_cb.tx_atomic, CY_RTOS_NEVER_TIMEOUT) != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_HCI_GET_TX_MUTEX_FAILED;
    }

    cybt_platform_sleep_lock();
    cybt_platform_assert_bt_wake();

    result = CY_RSLT_SUCCESS;
    total_written = 0u;

    for (attempt = 0; (attempt < 16) && (total_written < (size_t)length); ++attempt)
    {
        chunk_len = (size_t)length - total_written;
        result = cyhal_uart_write(&g_hci_uart_cb.hal_obj, p_data + total_written, &chunk_len);
        total_written += chunk_len;

        if (!bt_hci_is_write_ram_packet(p_data, length))
        {
            BT_HCI_VLOG("write attempt=%d chunk=%lu total=%lu/%lu rslt=0x%08lx",
                        attempt + 1,
                        (unsigned long)chunk_len,
                        (unsigned long)total_written,
                        (unsigned long)length,
                        (unsigned long)result);
        }

        if (result != CY_RSLT_SUCCESS)
        {
            break;
        }

        if (total_written < (size_t)length)
        {
            rt_thread_mdelay(1);
        }
    }

    cybt_platform_deassert_bt_wake();
    cybt_platform_sleep_unlock();
    cy_rtos_mutex_set(&g_hci_uart_cb.tx_atomic);

    if ((result != CY_RSLT_SUCCESS) || (total_written != (size_t)length))
    {
        BT_HCI_LOG("write failed len=%lu tx=%lu rslt=0x%08lx",
                   (unsigned long)length,
                   (unsigned long)total_written,
                   (unsigned long)result);
        bt_hci_dump_bytes("write fail bytes", p_data, length);
        return CYBT_ERR_HCI_WRITE_FAILED;
    }

    if (bt_hci_is_write_ram_packet(p_data, length))
    {
        ++g_patch_write_seq;
        if ((g_patch_write_seq == 1u) || ((g_patch_write_seq % 32u) == 0u))
        {
            BT_HCI_VLOG("patch write seq=%lu addr=%02X%02X%02X%02X len=%lu",
                        (unsigned long)g_patch_write_seq,
                        p_data[7],
                        p_data[6],
                        p_data[5],
                        p_data[4],
                        (unsigned long)length);
        }
    }
    else
    {
    }

    return CYBT_SUCCESS;
}

cybt_result_t cybt_platform_hci_read(hci_packet_type_t type, uint8_t *p_data, uint32_t *p_length, uint32_t timeout_ms)
{
    size_t read_len;
    size_t req_len;
    cy_rslt_t result = CY_RSLT_SUCCESS;
    int attempt;

    RT_UNUSED(type);
    RT_UNUSED(timeout_ms);

    if (!g_hci_uart_cb.inited)
    {
        return CYBT_ERR_HCI_NOT_INITIALIZE;
    }

    if ((p_data == RT_NULL) || (p_length == RT_NULL) || (*p_length == 0u))
    {
        return CYBT_ERR_BADARG;
    }

    if (cy_rtos_mutex_get(&g_hci_uart_cb.rx_atomic, CY_RTOS_NEVER_TIMEOUT) != CY_RSLT_SUCCESS)
    {
        return CYBT_ERR_HCI_GET_RX_MUTEX_FAILED;
    }

    req_len = (size_t)(*p_length);
    *p_length = 0u;
    cybt_platform_sleep_lock();

    {
        size_t total_read = 0u;

        for (attempt = 0; attempt < 8; ++attempt)
        {
            read_len = req_len - total_read;
            result = cyhal_uart_read(&g_hci_uart_cb.hal_obj, p_data + total_read, &read_len);
            if (result != CY_RSLT_SUCCESS)
            {
                break;
            }

            if (read_len > 0u)
            {
                total_read += read_len;
                if (total_read >= req_len)
                {
                    *p_length = (uint32_t)total_read;
                    if (bt_hci_is_write_ram_ack(p_data, *p_length))
                    {
                        ++g_patch_ack_seq;
                        if ((g_patch_ack_seq == 1u) || ((g_patch_ack_seq % 32u) == 0u) || (p_data[3] != 0u))
                        {
                            BT_HCI_VLOG("patch ack seq=%lu status=0x%02X",
                                        (unsigned long)g_patch_ack_seq,
                                        p_data[3]);
                        }
                    }
                    cybt_platform_sleep_unlock();
                    cy_rtos_mutex_set(&g_hci_uart_cb.rx_atomic);
                    return CYBT_SUCCESS;
                }
            }

            cybt_platform_sleep_unlock();
            rt_thread_mdelay(1);
            cybt_platform_sleep_lock();
        }

        cybt_platform_sleep_unlock();
        cy_rtos_mutex_set(&g_hci_uart_cb.rx_atomic);

        if (result != CY_RSLT_SUCCESS)
        {
            BT_HCI_LOG("read failed req=%lu got=%lu rslt=0x%08lx",
                       (unsigned long)req_len,
                       (unsigned long)total_read,
                       (unsigned long)result);
        }
        else if (total_read > 0u)
        {
            BT_HCI_LOG("read short req=%lu got=%lu",
                       (unsigned long)req_len,
                       (unsigned long)total_read);
        }
    }

    cyhal_uart_enable_event(&g_hci_uart_cb.hal_obj,
                            CYHAL_UART_IRQ_RX_NOT_EMPTY,
                            CYHAL_ISR_PRIORITY_DEFAULT,
                            true);
    return CYBT_ERR_HCI_READ_FAILED;
}

cybt_result_t cybt_platform_hci_close(void)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    if (!g_hci_uart_cb.inited)
    {
        return CYBT_ERR_HCI_NOT_INITIALIZE;
    }

    cyhal_uart_enable_event(&g_hci_uart_cb.hal_obj,
                            CYHAL_UART_IRQ_RX_NOT_EMPTY,
                            CYHAL_ISR_PRIORITY_DEFAULT,
                            false);
    cyhal_uart_register_callback(&g_hci_uart_cb.hal_obj, RT_NULL, RT_NULL);
    cyhal_uart_free(&g_hci_uart_cb.hal_obj);

#if (CYHAL_API_VERSION >= 2)
    if ((cfg != RT_NULL) && (NC != cfg->controller_config.sleep_mode.host_wakeup_pin))
    {
        cyhal_gpio_register_callback(cfg->controller_config.sleep_mode.host_wakeup_pin, RT_NULL);
        cyhal_gpio_enable_event(cfg->controller_config.sleep_mode.host_wakeup_pin,
                                CYHAL_GPIO_IRQ_NONE,
                                CYHAL_ISR_PRIORITY_DEFAULT,
                                false);
    }
#endif

    if ((cfg != RT_NULL) && (NC != cfg->controller_config.sleep_mode.device_wakeup_pin))
    {
        cyhal_gpio_free(cfg->controller_config.sleep_mode.device_wakeup_pin);
    }

    if (cfg != RT_NULL)
    {
        cyhal_gpio_write(cfg->controller_config.bt_power_pin, false);
        cyhal_gpio_free(cfg->controller_config.bt_power_pin);
    }

    cy_rtos_mutex_deinit(&g_hci_uart_cb.tx_atomic);
    cy_rtos_mutex_deinit(&g_hci_uart_cb.rx_atomic);
    memset(&g_hci_uart_cb, 0, sizeof(g_hci_uart_cb));
    return CYBT_SUCCESS;
}

void cybt_platform_hci_irq_rx_data_ind(bool enable)
{
    if (!g_hci_uart_cb.inited)
    {
        return;
    }

    cyhal_uart_enable_event(&g_hci_uart_cb.hal_obj,
                            CYHAL_UART_IRQ_RX_NOT_EMPTY,
                            CYHAL_ISR_PRIORITY_DEFAULT,
                            enable);
}





