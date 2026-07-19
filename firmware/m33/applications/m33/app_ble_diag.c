#include <finsh.h>
#include <rthw.h>
#include <rtthread.h>

#include "app_ble_diag.h"
#include "cybt_platform_task.h"

#define APP_BLE_DIAG_STACK_HIGH_PERCENT 75U

static app_ble_diag_snapshot_t g_app_ble_diag;

static void app_ble_diag_increment(rt_uint32_t *value)
{
    rt_base_t level = rt_hw_interrupt_disable();

    (*value)++;
    rt_hw_interrupt_enable(level);
}

static void app_ble_diag_note_peak(rt_uint32_t *peak, rt_uint32_t value)
{
    rt_base_t level = rt_hw_interrupt_disable();

    if (value > *peak)
    {
        *peak = value;
    }
    rt_hw_interrupt_enable(level);
}

void app_ble_diag_note_gatt_event(void)
{
    app_ble_diag_increment(&g_app_ble_diag.gatt_events);
}

void app_ble_diag_note_rx_drop(void)
{
    app_ble_diag_increment(&g_app_ble_diag.rx_drops);
}

void app_ble_diag_note_rx_queue_depth(rt_uint32_t depth)
{
    app_ble_diag_note_peak(&g_app_ble_diag.rx_queue_peak, depth);
}

void app_ble_diag_note_tx_queue_depth(rt_uint32_t depth)
{
    app_ble_diag_note_peak(&g_app_ble_diag.tx_queue_peak, depth);
}

void app_ble_diag_note_tx_ack_drop(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_ack_drops);
}

void app_ble_diag_note_tx_telemetry_coalesced(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_telemetry_coalesced);
}

void app_ble_diag_note_tx_stale_drop(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_stale_drops);
}

void app_ble_diag_note_tx_disconnected_drop(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_disconnected_drops);
}

void app_ble_diag_note_tx_cccd_drop(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_cccd_drops);
}

void app_ble_diag_note_tx_session_busy_reject(void)
{
    app_ble_diag_increment(&g_app_ble_diag.tx_session_busy_rejects);
}

void app_ble_diag_note_notify_failure(void)
{
    app_ble_diag_increment(&g_app_ble_diag.notify_failures);
}

void app_ble_diag_note_hci_queue_percent(rt_uint32_t task_id, rt_uint32_t percent)
{
    rt_base_t level;

    if ((percent == CYBT_INVALID_QUEUE_UTILIZATION) || (percent > 100U))
    {
        return;
    }

    level = rt_hw_interrupt_disable();
    if (task_id == BT_TASK_ID_HCI_RX)
    {
        g_app_ble_diag.hci_rx_queue_last_percent = percent;
        g_app_ble_diag.hci_rx_queue_sample_available = 1U;
        if (percent > g_app_ble_diag.hci_rx_queue_sampled_peak_percent)
        {
            g_app_ble_diag.hci_rx_queue_sampled_peak_percent = percent;
        }
    }
    else if (task_id == BT_TASK_ID_HCI_TX)
    {
        g_app_ble_diag.hci_tx_queue_last_percent = percent;
        g_app_ble_diag.hci_tx_queue_sample_available = 1U;
        if (percent > g_app_ble_diag.hci_tx_queue_sampled_peak_percent)
        {
            g_app_ble_diag.hci_tx_queue_sampled_peak_percent = percent;
        }
    }
    rt_hw_interrupt_enable(level);
}

void app_ble_diag_note_gate_state(rt_uint32_t enabled, rt_uint32_t state, rt_err_t last_error)
{
    rt_base_t level = rt_hw_interrupt_disable();

    g_app_ble_diag.gate_enabled = enabled;
    g_app_ble_diag.gate_state = state;
    g_app_ble_diag.gate_last_error = last_error;
    rt_hw_interrupt_enable(level);
}

static app_ble_diag_stack_t app_ble_diag_stack_snapshot_locked(rt_thread_t thread)
{
    app_ble_diag_stack_t result = {0};
    rt_uint8_t *base;
    rt_uint8_t *cursor;
    rt_uint8_t *end;

    if ((thread == RT_NULL) || (thread->stack_addr == RT_NULL) || (thread->stack_size == 0U))
    {
        return result;
    }

    base = (rt_uint8_t *)thread->stack_addr;
    end = base + thread->stack_size;
#ifdef ARCH_CPU_STACK_GROWS_UPWARD
    cursor = end;
    while ((cursor > base) && (cursor[-1] == '#'))
    {
        cursor--;
    }
    result.used_bytes = (rt_uint32_t)(cursor - base);
#else
    cursor = base;
    while ((cursor < end) && (*cursor == '#'))
    {
        cursor++;
    }
    result.used_bytes = thread->stack_size - (rt_uint32_t)(cursor - base);
#endif
    result.size_bytes = thread->stack_size;
    result.used_percent = (result.used_bytes * 100U) / result.size_bytes;
    result.available = 1U;
    return result;
}

static app_ble_diag_stack_t app_ble_diag_named_stack_snapshot(const char *name)
{
    app_ble_diag_stack_t result;
    rt_thread_t thread;

    rt_enter_critical();
    thread = rt_thread_find((char *)name);
    result = app_ble_diag_stack_snapshot_locked(thread);
    rt_exit_critical();
    return result;
}

static app_ble_diag_stack_t app_ble_diag_shell_stack_snapshot(void)
{
    app_ble_diag_stack_t result;

    rt_enter_critical();
    result = app_ble_diag_stack_snapshot_locked(rt_thread_self());
    rt_exit_critical();
    return result;
}

void app_ble_diag_snapshot(app_ble_diag_snapshot_t *out)
{
    rt_size_t heap_total = 0;
    rt_size_t heap_used = 0;
    rt_size_t heap_max_used = 0;
    rt_base_t level;

    if (out == RT_NULL)
    {
        return;
    }

    level = rt_hw_interrupt_disable();
    *out = g_app_ble_diag;
    rt_hw_interrupt_enable(level);

#ifdef RT_USING_HEAP
    rt_memory_info(&heap_total, &heap_used, &heap_max_used);
    out->heap_free_bytes = (rt_uint32_t)(heap_total - heap_used);
    out->heap_min_free_bytes = (rt_uint32_t)(heap_total - heap_max_used);
#endif

    out->ble_worker_stack = app_ble_diag_named_stack_snapshot("ble_work");
    out->rehab_stack = app_ble_diag_named_stack_snapshot("rehab_sv");
    out->shell_stack = app_ble_diag_shell_stack_snapshot();
}

static void app_ble_diag_print_stack(const char *name,
                                     const app_ble_diag_stack_t *stack,
                                     const char *unavailable_reason)
{
    rt_kprintf("BLE_DIAG_STACK: name=%s available=%lu used=%lu size=%lu percent=%lu reason=%s\n",
               name,
               (unsigned long)stack->available,
               (unsigned long)stack->used_bytes,
               (unsigned long)stack->size_bytes,
               (unsigned long)stack->used_percent,
               stack->available ? "ok" : unavailable_reason);
    if (stack->available && (stack->used_percent >= APP_BLE_DIAG_STACK_HIGH_PERCENT))
    {
        rt_kprintf("BLE_DIAG_STACK_HIGH: name=%s percent=%lu\n",
                   name,
                   (unsigned long)stack->used_percent);
    }
}

static int cmd_m33_ble_diag(int argc, char **argv)
{
    app_ble_diag_snapshot_t diag;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    app_ble_diag_snapshot(&diag);
    rt_kprintf("BLE_DIAG: gate=%lu/%lu err=%ld gatt=%lu rx_drop=%lu rx_peak=%lu tx_peak=%lu ack_drop=%lu tel_merge=%lu stale=%lu disconnected=%lu cccd_off=%lu busy_reject=%lu notify_fail=%lu\n",
               (unsigned long)diag.gate_enabled,
               (unsigned long)diag.gate_state,
               (long)diag.gate_last_error,
               (unsigned long)diag.gatt_events,
               (unsigned long)diag.rx_drops,
               (unsigned long)diag.rx_queue_peak,
               (unsigned long)diag.tx_queue_peak,
               (unsigned long)diag.tx_ack_drops,
               (unsigned long)diag.tx_telemetry_coalesced,
               (unsigned long)diag.tx_stale_drops,
               (unsigned long)diag.tx_disconnected_drops,
               (unsigned long)diag.tx_cccd_drops,
               (unsigned long)diag.tx_session_busy_rejects,
               (unsigned long)diag.notify_failures);
    rt_kprintf("BLE_DIAG_HCI: rx_sample=%lu rx_last_pct=%lu rx_sampled_peak_pct=%lu tx_sample=%lu tx_last_pct=%lu tx_sampled_peak_pct=%lu tx_heap_source=unsupported largest_source=unsupported\n",
               (unsigned long)diag.hci_rx_queue_sample_available,
               (unsigned long)diag.hci_rx_queue_last_percent,
               (unsigned long)diag.hci_rx_queue_sampled_peak_percent,
               (unsigned long)diag.hci_tx_queue_sample_available,
               (unsigned long)diag.hci_tx_queue_last_percent,
               (unsigned long)diag.hci_tx_queue_sampled_peak_percent);
    rt_kprintf("BLE_DIAG_HEAP: free=%lu min_free=%lu largest_free=unsupported\n",
               (unsigned long)diag.heap_free_bytes,
               (unsigned long)diag.heap_min_free_bytes);
    app_ble_diag_print_stack("hci_rx", &diag.hci_rx_stack, "unsupported");
    app_ble_diag_print_stack("hci_tx", &diag.hci_tx_stack, "unsupported");
    app_ble_diag_print_stack("ble_worker", &diag.ble_worker_stack, "not_found");
    app_ble_diag_print_stack("rehab_svc", &diag.rehab_stack, "not_found");
    app_ble_diag_print_stack("tshell", &diag.shell_stack, "not_found");
    return RT_EOK;
}
MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_diag, m33_ble_diag, show bounded M33 BLE runtime diagnostics);
