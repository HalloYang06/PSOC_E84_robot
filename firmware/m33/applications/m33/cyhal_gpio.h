#ifndef APPLICATIONS_M33_CYHAL_GPIO_H
#define APPLICATIONS_M33_CYHAL_GPIO_H

#include <stdbool.h>
#include <stdint.h>

#include "cy_result.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef CYHAL_GPIO_T_DEFINED
#define CYHAL_GPIO_T_DEFINED
typedef uint32_t cyhal_gpio_t;
#endif

#define CYHAL_NC_PIN_VALUE ((cyhal_gpio_t)0xFFFFFFFFu)
#ifndef NC
#define NC CYHAL_NC_PIN_VALUE
#endif

typedef enum
{
    CYHAL_GPIO_IRQ_NONE = 0,
    CYHAL_GPIO_IRQ_RISE = 1,
    CYHAL_GPIO_IRQ_FALL = 2,
    CYHAL_GPIO_IRQ_BOTH = 3,
} cyhal_gpio_event_t;

typedef enum
{
    CYHAL_GPIO_DIR_INPUT = 0,
    CYHAL_GPIO_DIR_OUTPUT = 1,
    CYHAL_GPIO_DIR_BIDIRECTIONAL = 2,
} cyhal_gpio_direction_t;

typedef enum
{
    CYHAL_GPIO_DRIVE_NONE = 0,
    CYHAL_GPIO_DRIVE_PULLUP = 2,
    CYHAL_GPIO_DRIVE_PULLDOWN = 3,
    CYHAL_GPIO_DRIVE_STRONG = 6,
    CYHAL_GPIO_DRIVE_PULLUPDOWN = 7,
} cyhal_gpio_drive_mode_t;

typedef void (*cyhal_gpio_irq_handler_t)(void *callback_arg, cyhal_gpio_event_t event);

typedef struct cyhal_gpio_callback_data_s
{
    cyhal_gpio_irq_handler_t callback;
    void *callback_arg;
    struct cyhal_gpio_callback_data_s *next;
    cyhal_gpio_t pin;
} cyhal_gpio_callback_data_t;

cy_rslt_t cyhal_gpio_init(cyhal_gpio_t pin, cyhal_gpio_direction_t direction,
                          cyhal_gpio_drive_mode_t drv_mode, bool init_val);
void cyhal_gpio_free(cyhal_gpio_t pin);
void cyhal_gpio_write(cyhal_gpio_t pin, bool value);
bool cyhal_gpio_read(cyhal_gpio_t pin);
void cyhal_gpio_register_callback(cyhal_gpio_t pin, cyhal_gpio_callback_data_t *callback_data);
void cyhal_gpio_enable_event(cyhal_gpio_t pin, cyhal_gpio_event_t event, uint8_t intr_priority, bool enable);

#ifdef __cplusplus
}
#endif

#endif
