#include <rtthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

#include "cyabs_rtos.h"

typedef struct
{
    rt_mq_t mq;
    rt_uint16_t max_msgs;
    rt_uint16_t item_size;
    char name[RT_NAME_MAX];
} cy_rtos_queue_wrapper_t;

static cy_rtos_error_t g_last_error = RT_EOK;
static rt_uint32_t g_queue_seq = 0;
static rt_uint32_t g_mutex_seq = 0;
static rt_uint32_t g_sem_seq = 0;
static rt_uint32_t g_thread_seq = 0;

static rt_int32_t cyabs_timeout_to_tick(cy_time_t timeout_ms)
{
    if (timeout_ms == 0)
    {
        return RT_WAITING_NO;
    }

    if (timeout_ms == CY_RTOS_NEVER_TIMEOUT)
    {
        return RT_WAITING_FOREVER;
    }

    return (rt_int32_t)rt_tick_from_millisecond(timeout_ms);
}

static cy_rslt_t cyabs_map_status(rt_err_t status)
{
    g_last_error = status;

    if (status == RT_EOK)
    {
        return CY_RSLT_SUCCESS;
    }

    if (status == -RT_ETIMEOUT)
    {
        return CY_RTOS_TIMEOUT;
    }

    if (status == -RT_ENOMEM)
    {
        return CY_RTOS_NO_MEMORY;
    }

    if (status == -RT_EINVAL)
    {
        return CY_RTOS_BAD_PARAM;
    }

    return CY_RTOS_GENERAL_ERROR;
}

static cy_rslt_t cyabs_map_mq_status(rt_err_t status, bool is_put)
{
    if (status == -RT_EFULL)
    {
        g_last_error = status;
        return is_put ? CY_RTOS_QUEUE_FULL : CY_RTOS_GENERAL_ERROR;
    }

    if (status == -RT_EEMPTY)
    {
        g_last_error = status;
        return is_put ? CY_RTOS_GENERAL_ERROR : CY_RTOS_QUEUE_EMPTY;
    }

    return cyabs_map_status(status);
}

static rt_uint8_t cyabs_map_priority(cy_thread_priority_t priority)
{
    rt_uint8_t rt_priority;

    if (priority >= CY_RTOS_PRIORITY_MAX)
    {
        priority = CY_RTOS_PRIORITY_NORMAL;
    }

    rt_priority = (rt_uint8_t)(8 + ((CY_RTOS_PRIORITY_MAX - 1u - (rt_uint32_t)priority) * 4u));
    if (rt_priority >= RT_THREAD_PRIORITY_MAX)
    {
        rt_priority = (rt_uint8_t)(RT_THREAD_PRIORITY_MAX - 1u);
    }
    return rt_priority;
}

cy_rtos_error_t cy_rtos_last_error(void)
{
    return g_last_error;
}

cy_rslt_t cy_rtos_delay_milliseconds(cy_time_t num_ms)
{
    g_last_error = RT_EOK;
    rt_thread_mdelay((rt_int32_t)num_ms);
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_get_time(cy_time_t *tval)
{
    if (tval == RT_NULL)
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    *tval = rt_tick_get_millisecond();
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_thread_create(cy_thread_t* thread, cy_thread_entry_fn_t entry_function,
                                const char* name, void* stack, uint32_t stack_size,
                                cy_thread_priority_t priority, cy_thread_arg_t arg)
{
    rt_thread_t handle;
    char auto_name[RT_NAME_MAX];

    RT_UNUSED(stack);

    if ((thread == RT_NULL) || (entry_function == RT_NULL) || (stack_size < CY_RTOS_MIN_STACK_SIZE))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    if (name == RT_NULL)
    {
        rt_snprintf(auto_name, sizeof(auto_name), "cyt%lu", (unsigned long)g_thread_seq++);
        name = auto_name;
    }

    handle = rt_thread_create(name, (void (*)(void *))entry_function, arg, stack_size,
                              cyabs_map_priority(priority), 10);
    if (handle == RT_NULL)
    {
        g_last_error = -RT_ENOMEM;
        return CY_RTOS_NO_MEMORY;
    }

    if (rt_thread_startup(handle) != RT_EOK)
    {
        rt_thread_delete(handle);
        g_last_error = -RT_ERROR;
        return CY_RTOS_GENERAL_ERROR;
    }

    *thread = handle;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_thread_get_handle(cy_thread_t* thread)
{
    if (thread == RT_NULL)
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    *thread = rt_thread_self();
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_thread_exit(void)
{
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_mutex_init(cy_mutex_t* mutex, bool recursive)
{
    rt_mutex_t handle;
    char name[RT_NAME_MAX];

    RT_UNUSED(recursive);

    if (mutex == RT_NULL)
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    rt_snprintf(name, sizeof(name), "cym%lu", (unsigned long)g_mutex_seq++);
    handle = rt_mutex_create(name, RT_IPC_FLAG_PRIO);
    if (handle == RT_NULL)
    {
        g_last_error = -RT_ENOMEM;
        return CY_RTOS_NO_MEMORY;
    }

    *mutex = handle;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_mutex_get(cy_mutex_t* mutex, cy_time_t timeout_ms)
{
    if ((mutex == RT_NULL) || (*mutex == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    return cyabs_map_status(rt_mutex_take(*mutex, cyabs_timeout_to_tick(timeout_ms)));
}

cy_rslt_t cy_rtos_mutex_set(cy_mutex_t* mutex)
{
    if ((mutex == RT_NULL) || (*mutex == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    return cyabs_map_status(rt_mutex_release(*mutex));
}

cy_rslt_t cy_rtos_mutex_deinit(cy_mutex_t* mutex)
{
    rt_err_t status;

    if ((mutex == RT_NULL) || (*mutex == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    status = rt_mutex_delete(*mutex);
    *mutex = RT_NULL;
    return cyabs_map_status(status);
}

cy_rslt_t cy_rtos_semaphore_init(cy_semaphore_t* semaphore, uint32_t maxcount, uint32_t initcount)
{
    rt_sem_t handle;
    char name[RT_NAME_MAX];

    RT_UNUSED(maxcount);

    if (semaphore == RT_NULL)
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    rt_snprintf(name, sizeof(name), "cys%lu", (unsigned long)g_sem_seq++);
    handle = rt_sem_create(name, initcount, RT_IPC_FLAG_PRIO);
    if (handle == RT_NULL)
    {
        g_last_error = -RT_ENOMEM;
        return CY_RTOS_NO_MEMORY;
    }

    *semaphore = handle;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_semaphore_get(cy_semaphore_t* semaphore, cy_time_t timeout_ms)
{
    if ((semaphore == RT_NULL) || (*semaphore == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    return cyabs_map_status(rt_sem_take(*semaphore, cyabs_timeout_to_tick(timeout_ms)));
}

cy_rslt_t cy_rtos_semaphore_set(cy_semaphore_t* semaphore)
{
    if ((semaphore == RT_NULL) || (*semaphore == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    return cyabs_map_status(rt_sem_release(*semaphore));
}

cy_rslt_t cy_rtos_semaphore_get_count(cy_semaphore_t* semaphore, size_t* count)
{
    if ((semaphore == RT_NULL) || (*semaphore == RT_NULL) || (count == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    *count = (size_t)(*semaphore)->value;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_semaphore_deinit(cy_semaphore_t* semaphore)
{
    rt_err_t status;

    if ((semaphore == RT_NULL) || (*semaphore == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    status = rt_sem_delete(*semaphore);
    *semaphore = RT_NULL;
    return cyabs_map_status(status);
}

cy_rslt_t cy_rtos_queue_init(cy_queue_t* queue, size_t length, size_t itemsize)
{
    cy_rtos_queue_wrapper_t *wrapper;

    if ((queue == RT_NULL) || (length == 0u) || (itemsize == 0u))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)rt_calloc(1, sizeof(*wrapper));
    if (wrapper == RT_NULL)
    {
        g_last_error = -RT_ENOMEM;
        return CY_RTOS_NO_MEMORY;
    }

    rt_snprintf(wrapper->name, sizeof(wrapper->name), "cyq%lu", (unsigned long)g_queue_seq++);
    wrapper->mq = rt_mq_create(wrapper->name, (rt_size_t)itemsize, (rt_size_t)length, RT_IPC_FLAG_FIFO);
    if (wrapper->mq == RT_NULL)
    {
        rt_free(wrapper);
        g_last_error = -RT_ENOMEM;
        return CY_RTOS_NO_MEMORY;
    }

    wrapper->max_msgs = (rt_uint16_t)length;
    wrapper->item_size = (rt_uint16_t)itemsize;
    *queue = (cy_queue_t)wrapper;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_queue_put(cy_queue_t* queue, const void* item_ptr, cy_time_t timeout_ms)
{
    cy_rtos_queue_wrapper_t *wrapper;
    rt_err_t status;

    if ((queue == RT_NULL) || (*queue == RT_NULL) || (item_ptr == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    status = rt_mq_send_wait(wrapper->mq, item_ptr, (rt_size_t)wrapper->item_size, cyabs_timeout_to_tick(timeout_ms));
    return cyabs_map_mq_status(status, true);
}

cy_rslt_t cy_rtos_queue_get(cy_queue_t* queue, void* item_ptr, cy_time_t timeout_ms)
{
    cy_rtos_queue_wrapper_t *wrapper;
    rt_ssize_t size;

    if ((queue == RT_NULL) || (*queue == RT_NULL) || (item_ptr == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    size = rt_mq_recv(wrapper->mq, item_ptr, (rt_size_t)wrapper->item_size, cyabs_timeout_to_tick(timeout_ms));
    if (size == (rt_ssize_t)wrapper->item_size)
    {
        g_last_error = RT_EOK;
        return CY_RSLT_SUCCESS;
    }

    return cyabs_map_mq_status((rt_err_t)size, false);
}

cy_rslt_t cy_rtos_queue_count(cy_queue_t* queue, size_t* num_waiting)
{
    cy_rtos_queue_wrapper_t *wrapper;

    if ((queue == RT_NULL) || (*queue == RT_NULL) || (num_waiting == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    *num_waiting = (size_t)wrapper->mq->entry;
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_queue_space(cy_queue_t* queue, size_t* num_spaces)
{
    cy_rtos_queue_wrapper_t *wrapper;

    if ((queue == RT_NULL) || (*queue == RT_NULL) || (num_spaces == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    *num_spaces = (size_t)(wrapper->max_msgs - wrapper->mq->entry);
    g_last_error = RT_EOK;
    return CY_RSLT_SUCCESS;
}

cy_rslt_t cy_rtos_queue_reset(cy_queue_t* queue)
{
    cy_rtos_queue_wrapper_t *wrapper;

    if ((queue == RT_NULL) || (*queue == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    return cyabs_map_mq_status(rt_mq_control(wrapper->mq, RT_IPC_CMD_RESET, RT_NULL), false);
}

cy_rslt_t cy_rtos_queue_deinit(cy_queue_t* queue)
{
    cy_rtos_queue_wrapper_t *wrapper;
    rt_err_t status;

    if ((queue == RT_NULL) || (*queue == RT_NULL))
    {
        g_last_error = -RT_EINVAL;
        return CY_RTOS_BAD_PARAM;
    }

    wrapper = (cy_rtos_queue_wrapper_t *)(*queue);
    status = rt_mq_delete(wrapper->mq);
    rt_free(wrapper);
    *queue = RT_NULL;
    return cyabs_map_mq_status(status, false);
}
