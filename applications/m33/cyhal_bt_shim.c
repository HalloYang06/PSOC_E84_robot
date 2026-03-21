#include <string.h>

#include <rtthread.h>

#include "cyabs_rtos.h"
#include "cyhal_gpio.h"
#include "cyhal_uart.h"
#include "cycfg_peripherals.h"
#include "cycfg_pins.h"
#include "cy_scb_uart.h"
#include "cy_gpio.h"
#include "mtb_hal_gpio.h"

#define BT_SHIM_LOG(...) ((void)0)

#define CYHAL_GPIO_STATE_SLOTS (16)
#define CYHAL_PORT(pin) ((uint8_t)(((uint8_t)(pin)) >> 3U))
#define CYHAL_PIN(pin)  ((uint8_t)(((uint8_t)(pin)) & 0x07U))
#define CYHAL_MAKE_PIN(port, pin) ((cyhal_gpio_t)((((uint8_t)(port)) << 3U) | (((uint8_t)(pin)) & 0x07U)))

typedef struct
{
    bool in_use;
    bool hsiom_saved;
    cyhal_gpio_t pin;
    en_hsiom_sel_t saved_hsiom;
    mtb_hal_gpio_t hal_obj;
    cyhal_gpio_callback_data_t *callback_data;
    cyhal_gpio_event_t enabled_event;
} cyhal_gpio_state_t;

static cyhal_gpio_state_t g_gpio_states[CYHAL_GPIO_STATE_SLOTS];
static cyhal_uart_t *g_bt_uart_owner = RT_NULL;
static IRQn_Type g_gpio_port10_irq = CYBSP_BT_HOST_WAKE_IRQ;
static bool g_gpio_port10_irq_installed = false;

static cyhal_gpio_state_t *cyhal_find_gpio_state(cyhal_gpio_t pin, bool create)
{
    cyhal_gpio_state_t *free_slot = RT_NULL;
    int i;

    for (i = 0; i < CYHAL_GPIO_STATE_SLOTS; ++i)
    {
        if (g_gpio_states[i].in_use && (g_gpio_states[i].pin == pin))
        {
            return &g_gpio_states[i];
        }
        if (create && (free_slot == RT_NULL) && !g_gpio_states[i].in_use)
        {
            free_slot = &g_gpio_states[i];
        }
    }

    if ((free_slot != RT_NULL) && create)
    {
        memset(free_slot, 0, sizeof(*free_slot));
        free_slot->in_use = true;
        free_slot->pin = pin;
        mtb_hal_gpio_setup(&free_slot->hal_obj, CYHAL_PORT(pin), CYHAL_PIN(pin));
    }

    return free_slot;
}

static void cyhal_bt_uart_callback_bridge(void *callback_arg, mtb_hal_uart_event_t event)
{
    cyhal_uart_t *obj = (cyhal_uart_t *)callback_arg;

    BT_SHIM_LOG("uart callback event=0x%08lx", (unsigned long)event);

    if ((obj != RT_NULL) && (obj->callback != RT_NULL))
    {
        obj->callback(obj->callback_arg, (cyhal_uart_event_t)event);
    }
}

static void cyhal_bt_uart_irq_handler(void)
{
    BT_SHIM_LOG("uart irq");
    if (g_bt_uart_owner != RT_NULL)
    {
        (void)mtb_hal_uart_process_interrupt(&g_bt_uart_owner->hal_obj);
    }
}

static void cyhal_bt_gpio_callback_bridge(void *callback_arg, mtb_hal_gpio_event_t event)
{
    cyhal_gpio_state_t *state = (cyhal_gpio_state_t *)callback_arg;

    if (state != RT_NULL)
    {
        BT_SHIM_LOG("gpio callback pin=0x%02x event=0x%08lx level=%d", state->pin, (unsigned long)event, mtb_hal_gpio_read(&state->hal_obj));
    }

    if ((state != RT_NULL) && (state->callback_data != RT_NULL) && (state->callback_data->callback != RT_NULL))
    {
        state->callback_data->callback(state->callback_data->callback_arg, (cyhal_gpio_event_t)event);
    }
}

static void cyhal_gpio_port10_irq_handler(void)
{
    int i;

    BT_SHIM_LOG("port10 irq enter");
    for (i = 0; i < CYHAL_GPIO_STATE_SLOTS; ++i)
    {
        if (g_gpio_states[i].in_use && (CYHAL_PORT(g_gpio_states[i].pin) == 10U))
        {
            BT_SHIM_LOG("port10 irq scan pin=0x%02x", g_gpio_states[i].pin);
            (void)mtb_hal_gpio_process_interrupt(&g_gpio_states[i].hal_obj);
        }
    }
}

static void cyhal_ensure_gpio_irq_for_port(uint8_t port)
{
    if ((port == 10U) && !g_gpio_port10_irq_installed)
    {
        NVIC_DisableIRQ(g_gpio_port10_irq);
        NVIC_SetVector(g_gpio_port10_irq, (uint32_t)cyhal_gpio_port10_irq_handler);
        NVIC_ClearPendingIRQ(g_gpio_port10_irq);
        NVIC_EnableIRQ(g_gpio_port10_irq);
        g_gpio_port10_irq_installed = true;
        BT_SHIM_LOG("port10 irq installed irq=%d", g_gpio_port10_irq);
    }
}

cy_rslt_t cyhal_gpio_init(cyhal_gpio_t pin, cyhal_gpio_direction_t direction,
                          cyhal_gpio_drive_mode_t drv_mode, bool init_val)
{
    cyhal_gpio_state_t *state;
    mtb_hal_gpio_direction_t hal_dir;
    mtb_hal_gpio_drive_mode_t hal_drive;

    if (pin == NC)
    {
        return CY_RSLT_SUCCESS;
    }

    state = cyhal_find_gpio_state(pin, true);
    if (state == RT_NULL)
    {
        return CY_RTOS_NO_MEMORY;
    }

    hal_dir = (direction == CYHAL_GPIO_DIR_OUTPUT) ? MTB_HAL_GPIO_DIR_OUTPUT : MTB_HAL_GPIO_DIR_INPUT;
    if (direction == CYHAL_GPIO_DIR_BIDIRECTIONAL)
    {
        hal_dir = MTB_HAL_GPIO_DIR_BIDIRECTIONAL;
    }

    switch (drv_mode)
    {
    case CYHAL_GPIO_DRIVE_PULLUP:
        hal_drive = MTB_HAL_GPIO_DRIVE_PULLUP;
        break;
    case CYHAL_GPIO_DRIVE_PULLDOWN:
        hal_drive = MTB_HAL_GPIO_DRIVE_PULLDOWN;
        break;
    case CYHAL_GPIO_DRIVE_STRONG:
        hal_drive = MTB_HAL_GPIO_DRIVE_STRONG;
        break;
    case CYHAL_GPIO_DRIVE_PULLUPDOWN:
        hal_drive = MTB_HAL_GPIO_DRIVE_PULLUPDOWN;
        break;
    default:
        hal_drive = MTB_HAL_GPIO_DRIVE_NONE;
        break;
    }

    if (!state->hsiom_saved)
    {
        state->saved_hsiom = Cy_GPIO_GetHSIOM(&GPIO->PRT[CYHAL_PORT(state->pin)], CYHAL_PIN(state->pin));
        state->hsiom_saved = true;
    }
    Cy_GPIO_SetHSIOM(&GPIO->PRT[CYHAL_PORT(state->pin)], CYHAL_PIN(state->pin), HSIOM_SEL_GPIO);
    mtb_hal_gpio_configure(&state->hal_obj, hal_dir, hal_drive);
    mtb_hal_gpio_write(&state->hal_obj, init_val);

    if ((pin == CYHAL_MAKE_PIN(CYBSP_BT_POWER_PORT_NUM, CYBSP_BT_POWER_PIN)) ||
        (pin == CYHAL_MAKE_PIN(CYBSP_BT_DEVICE_WAKE_PORT_NUM, CYBSP_BT_DEVICE_WAKE_PIN)) ||
        (pin == CYHAL_MAKE_PIN(CYBSP_BT_HOST_WAKE_PORT_NUM, CYBSP_BT_HOST_WAKE_PIN)) ||
        (pin == CYHAL_MAKE_PIN(CYBSP_BT_UART_RTS_PORT_NUM, CYBSP_BT_UART_RTS_PIN)))
    {
        BT_SHIM_LOG("gpio init pin=0x%02x init=%d dir=%d drive=%d", pin, init_val, direction, drv_mode);
    }

    return CY_RSLT_SUCCESS;
}

void cyhal_gpio_free(cyhal_gpio_t pin)
{
    cyhal_gpio_state_t *state = cyhal_find_gpio_state(pin, false);

    if (state != RT_NULL)
    {
        if (state->hsiom_saved)
        {
            Cy_GPIO_SetHSIOM(&GPIO->PRT[CYHAL_PORT(state->pin)], CYHAL_PIN(state->pin), state->saved_hsiom);
        }
        memset(state, 0, sizeof(*state));
    }
}

void cyhal_gpio_write(cyhal_gpio_t pin, bool value)
{
    cyhal_gpio_state_t *state = cyhal_find_gpio_state(pin, true);

    if (state != RT_NULL)
    {
        mtb_hal_gpio_write(&state->hal_obj, value);
        if ((pin == CYHAL_MAKE_PIN(CYBSP_BT_POWER_PORT_NUM, CYBSP_BT_POWER_PIN)) ||
            (pin == CYHAL_MAKE_PIN(CYBSP_BT_DEVICE_WAKE_PORT_NUM, CYBSP_BT_DEVICE_WAKE_PIN)) ||
            (pin == CYHAL_MAKE_PIN(CYBSP_BT_UART_RTS_PORT_NUM, CYBSP_BT_UART_RTS_PIN)))
        {
            BT_SHIM_LOG("gpio write pin=0x%02x value=%d", pin, value);
        }
    }
}

bool cyhal_gpio_read(cyhal_gpio_t pin)
{
    cyhal_gpio_state_t *state = cyhal_find_gpio_state(pin, false);

    return (state != RT_NULL) ? mtb_hal_gpio_read(&state->hal_obj) : false;
}

void cyhal_gpio_register_callback(cyhal_gpio_t pin, cyhal_gpio_callback_data_t *callback_data)
{
    cyhal_gpio_state_t *state = cyhal_find_gpio_state(pin, true);

    if (state != RT_NULL)
    {
        state->callback_data = callback_data;
        mtb_hal_gpio_register_callback(&state->hal_obj, cyhal_bt_gpio_callback_bridge, state);
    }
}

void cyhal_gpio_enable_event(cyhal_gpio_t pin, cyhal_gpio_event_t event, uint8_t intr_priority, bool enable)
{
    cyhal_gpio_state_t *state = cyhal_find_gpio_state(pin, true);
    mtb_hal_gpio_event_t hal_event = MTB_HAL_GPIO_IRQ_NONE;

    RT_UNUSED(intr_priority);

    if (state == RT_NULL)
    {
        return;
    }

    switch (event)
    {
    case CYHAL_GPIO_IRQ_RISE:
        hal_event = MTB_HAL_GPIO_IRQ_RISE;
        break;
    case CYHAL_GPIO_IRQ_FALL:
        hal_event = MTB_HAL_GPIO_IRQ_FALL;
        break;
    case CYHAL_GPIO_IRQ_BOTH:
        hal_event = MTB_HAL_GPIO_IRQ_BOTH;
        break;
    default:
        hal_event = MTB_HAL_GPIO_IRQ_NONE;
        break;
    }

    state->enabled_event = enable ? event : CYHAL_GPIO_IRQ_NONE;
    cyhal_ensure_gpio_irq_for_port(CYHAL_PORT(pin));
    mtb_hal_gpio_enable_event(&state->hal_obj, hal_event, enable);
    if (pin == CYHAL_MAKE_PIN(CYBSP_BT_HOST_WAKE_PORT_NUM, CYBSP_BT_HOST_WAKE_PIN))
    {
        BT_SHIM_LOG("host wake event=%d enable=%d level=%d", event, enable, mtb_hal_gpio_read(&state->hal_obj));
    }
}

cy_rslt_t cyhal_uart_init(cyhal_uart_t *obj, cyhal_gpio_t tx, cyhal_gpio_t rx,
                          cyhal_gpio_t cts, cyhal_gpio_t rts, void *clk,
                          const cyhal_uart_cfg_t *cfg)
{
    cy_rslt_t result;

    RT_UNUSED(tx);
    RT_UNUSED(rx);
    RT_UNUSED(cts);
    RT_UNUSED(rts);
    RT_UNUSED(clk);
    RT_UNUSED(cfg);

    if (obj == RT_NULL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    memset(obj, 0, sizeof(*obj));

    result = Cy_SCB_UART_Init(CYBSP_BT_UART_HW, &CYBSP_BT_UART_config, &obj->context);
    if (result != CY_RSLT_SUCCESS)
    {
        return result;
    }

    Cy_SCB_UART_Enable(CYBSP_BT_UART_HW);

    result = mtb_hal_uart_setup(&obj->hal_obj, &CYBSP_BT_UART_hal_config, &obj->context, &CYBSP_BT_UART_hal_clock);
    BT_SHIM_LOG("uart setup rslt=0x%08lx", (unsigned long)result);
    if (result != CY_RSLT_SUCCESS)
    {
        Cy_SCB_UART_DeInit(CYBSP_BT_UART_HW);
        return result;
    }

    mtb_hal_uart_register_callback(&obj->hal_obj, cyhal_bt_uart_callback_bridge, obj);
    g_bt_uart_owner = obj;
    NVIC_DisableIRQ(CYBSP_BT_UART_IRQ);
    NVIC_SetVector(CYBSP_BT_UART_IRQ, (uint32_t)cyhal_bt_uart_irq_handler);
    NVIC_ClearPendingIRQ(CYBSP_BT_UART_IRQ);
    NVIC_EnableIRQ(CYBSP_BT_UART_IRQ);

    obj->is_inited = true;
    BT_SHIM_LOG("uart init ok irq=%d", CYBSP_BT_UART_IRQ);
    return CY_RSLT_SUCCESS;
}

void cyhal_uart_free(cyhal_uart_t *obj)
{
    if (obj != RT_NULL)
    {
        if (g_bt_uart_owner == obj)
        {
            NVIC_DisableIRQ(CYBSP_BT_UART_IRQ);
            g_bt_uart_owner = RT_NULL;
        }
        Cy_SCB_UART_Disable(CYBSP_BT_UART_HW, &obj->context);
        Cy_SCB_UART_DeInit(CYBSP_BT_UART_HW);
        memset(obj, 0, sizeof(*obj));
    }
}

cy_rslt_t cyhal_uart_set_baud(cyhal_uart_t *obj, uint32_t baudrate, uint32_t *actualbaud)
{
    if (obj == RT_NULL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    {
        cy_rslt_t rslt = mtb_hal_uart_set_baud(&obj->hal_obj, baudrate, actualbaud);
        BT_SHIM_LOG("uart set baud req=%lu actual=%lu rslt=0x%08lx", (unsigned long)baudrate, (unsigned long)((actualbaud != RT_NULL) ? *actualbaud : 0), (unsigned long)rslt);
        return rslt;
    }
}

cy_rslt_t cyhal_uart_enable_flow_control(cyhal_uart_t *obj, bool cts, bool rts)
{
    RT_UNUSED(rts);

    if (obj == RT_NULL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    return mtb_hal_uart_enable_cts_flow_control(&obj->hal_obj, cts);
}

void cyhal_uart_register_callback(cyhal_uart_t *obj, cyhal_uart_event_callback_t callback, void *callback_arg)
{
    if (obj != RT_NULL)
    {
        obj->callback = callback;
        obj->callback_arg = callback_arg;
        if (obj->is_inited)
        {
            mtb_hal_uart_register_callback(&obj->hal_obj, cyhal_bt_uart_callback_bridge, obj);
        }
    }
}

void cyhal_uart_enable_event(cyhal_uart_t *obj, cyhal_uart_event_t event, uint8_t intr_priority, bool enable)
{
    RT_UNUSED(intr_priority);

    if (obj != RT_NULL)
    {
        BT_SHIM_LOG("uart enable event=0x%08lx enable=%d", (unsigned long)event, enable);
        mtb_hal_uart_enable_event(&obj->hal_obj, (mtb_hal_uart_event_t)event, enable);
    }
}

cy_rslt_t cyhal_uart_write(cyhal_uart_t *obj, void *tx, size_t *tx_length)
{
    if (obj == RT_NULL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    return mtb_hal_uart_write(&obj->hal_obj, tx, tx_length);
}

cy_rslt_t cyhal_uart_read(cyhal_uart_t *obj, void *rx, size_t *rx_length)
{
    if (obj == RT_NULL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    return mtb_hal_uart_read(&obj->hal_obj, rx, rx_length);
}



