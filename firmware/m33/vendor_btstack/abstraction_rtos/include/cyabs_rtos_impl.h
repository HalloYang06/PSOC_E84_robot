#pragma once

#include <rtthread.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CY_RTOS_MIN_STACK_SIZE 256u
#define CY_RTOS_ALIGNMENT_MASK 0x00000007UL

typedef enum
{
    CY_RTOS_PRIORITY_MIN = 0,
    CY_RTOS_PRIORITY_LOW,
    CY_RTOS_PRIORITY_BELOWNORMAL,
    CY_RTOS_PRIORITY_NORMAL,
    CY_RTOS_PRIORITY_ABOVENORMAL,
    CY_RTOS_PRIORITY_HIGH,
    CY_RTOS_PRIORITY_REALTIME,
    CY_RTOS_PRIORITY_MAX
} cy_thread_priority_t;

typedef rt_thread_t cy_thread_t;
typedef void * cy_thread_arg_t;
typedef rt_mutex_t cy_mutex_t;
typedef rt_sem_t cy_semaphore_t;
typedef void * cy_event_t;
typedef void * cy_queue_t;
typedef void * cy_timer_t;
typedef void * cy_timer_callback_arg_t;
typedef uint32_t cy_time_t;
typedef rt_err_t cy_rtos_error_t;

#ifdef __cplusplus
}
#endif
