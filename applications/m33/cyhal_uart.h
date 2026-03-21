#ifndef APPLICATIONS_M33_CYHAL_UART_H
#define APPLICATIONS_M33_CYHAL_UART_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mtb_hal_uart_impl.h"
#include "cyhal_gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CYHAL_API_VERSION (2)
#define CYHAL_ISR_PRIORITY_DEFAULT (3u)

typedef mtb_hal_uart_event_t cyhal_uart_event_t;
#define CYHAL_UART_IRQ_NONE         MTB_HAL_UART_IRQ_NONE
#define CYHAL_UART_IRQ_RX_DONE      MTB_HAL_UART_IRQ_RX_DONE
#define CYHAL_UART_IRQ_TX_DONE      MTB_HAL_UART_IRQ_TX_DONE
#define CYHAL_UART_IRQ_RX_NOT_EMPTY MTB_HAL_UART_IRQ_RX_NOT_EMPTY

typedef enum
{
    CYHAL_UART_PARITY_NONE = 0,
    CYHAL_UART_PARITY_EVEN = 1,
    CYHAL_UART_PARITY_ODD  = 2,
} cyhal_uart_parity_t;

typedef enum
{
    CYHAL_UART_STOP_BITS_1 = 1,
    CYHAL_UART_STOP_BITS_2 = 2,
} cyhal_uart_stop_bits_t;

typedef struct
{
    uint32_t data_bits;
    cyhal_uart_stop_bits_t stop_bits;
    cyhal_uart_parity_t parity;
    void *rx_buffer;
    size_t rx_buffer_size;
} cyhal_uart_cfg_t;

typedef void (*cyhal_uart_event_callback_t)(void *callback_arg, cyhal_uart_event_t event);

typedef struct
{
    mtb_hal_uart_t hal_obj;
    cy_stc_scb_uart_context_t context;
    cyhal_uart_event_callback_t callback;
    void *callback_arg;
    bool is_inited;
} cyhal_uart_t;

cy_rslt_t cyhal_uart_init(cyhal_uart_t *obj, cyhal_gpio_t tx, cyhal_gpio_t rx,
                          cyhal_gpio_t cts, cyhal_gpio_t rts, void *clk,
                          const cyhal_uart_cfg_t *cfg);
void cyhal_uart_free(cyhal_uart_t *obj);
cy_rslt_t cyhal_uart_set_baud(cyhal_uart_t *obj, uint32_t baudrate, uint32_t *actualbaud);
cy_rslt_t cyhal_uart_enable_flow_control(cyhal_uart_t *obj, bool cts, bool rts);
void cyhal_uart_register_callback(cyhal_uart_t *obj, cyhal_uart_event_callback_t callback, void *callback_arg);
void cyhal_uart_enable_event(cyhal_uart_t *obj, cyhal_uart_event_t event, uint8_t intr_priority, bool enable);
cy_rslt_t cyhal_uart_write(cyhal_uart_t *obj, void *tx, size_t *tx_length);
cy_rslt_t cyhal_uart_read(cyhal_uart_t *obj, void *rx, size_t *rx_length);

#ifdef __cplusplus
}
#endif

#endif

