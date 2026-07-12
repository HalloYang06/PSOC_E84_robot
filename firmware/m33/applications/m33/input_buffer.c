#include "input_buffer.h"

#define INPUT_BUFFER_CAPACITY 32

static struct
{
    struct rt_mutex lock;
    input_event_t items[INPUT_BUFFER_CAPACITY];
    rt_uint16_t head;
    rt_uint16_t tail;
    rt_uint16_t count;
} g_input_buffer;

rt_err_t input_buffer_init(void)
{
    rt_mutex_init(&g_input_buffer.lock, "inputq", RT_IPC_FLAG_PRIO);
    g_input_buffer.head = 0;
    g_input_buffer.tail = 0;
    g_input_buffer.count = 0;
    return RT_EOK;
}

rt_err_t input_buffer_push(const input_event_t *event)
{
    if (event == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_input_buffer.lock, RT_WAITING_FOREVER);
    if (g_input_buffer.count >= INPUT_BUFFER_CAPACITY)
    {
        rt_mutex_release(&g_input_buffer.lock);
        return -RT_EFULL;
    }

    g_input_buffer.items[g_input_buffer.tail] = *event;
    g_input_buffer.tail = (g_input_buffer.tail + 1) % INPUT_BUFFER_CAPACITY;
    g_input_buffer.count++;
    rt_mutex_release(&g_input_buffer.lock);
    return RT_EOK;
}

rt_err_t input_buffer_pop(input_event_t *event)
{
    if (event == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_input_buffer.lock, RT_WAITING_FOREVER);
    if (g_input_buffer.count == 0)
    {
        rt_mutex_release(&g_input_buffer.lock);
        return -RT_EEMPTY;
    }

    *event = g_input_buffer.items[g_input_buffer.head];
    g_input_buffer.head = (g_input_buffer.head + 1) % INPUT_BUFFER_CAPACITY;
    g_input_buffer.count--;
    rt_mutex_release(&g_input_buffer.lock);
    return RT_EOK;
}
