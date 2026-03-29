#include "event_queue.h"

#include "stm32f1xx.h"

static uint32_t event_queue_enter_critical(void)
{
    /* 队列在主循环与中断间共享，关键区保证 head/tail/count 一致性。 */
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    return primask;
}

static void event_queue_exit_critical(uint32_t primask)
{
    if ((primask & 0x1U) == 0U)
    {
        __enable_irq();
    }
}

void event_queue_init(event_queue_t *queue)
{
    uint16_t i;

    if (queue == 0)
    {
        return;
    }

    queue->head = 0U;
    queue->tail = 0U;
    queue->count = 0U;

    for (i = 0U; i < EVENT_QUEUE_CAPACITY; ++i)
    {
        queue->buffer[i].id = EVENT_NONE;
        queue->buffer[i].arg0 = 0U;
        queue->buffer[i].arg1 = 0U;
    }
}

bool event_queue_push(event_queue_t *queue, const event_t *event)
{
    uint32_t primask;
    bool ok = false;

    if ((queue == 0) || (event == 0))
    {
        return false;
    }

    primask = event_queue_enter_critical();
    if (queue->count < EVENT_QUEUE_CAPACITY)
    {
        queue->buffer[queue->tail] = *event;
        queue->tail = (uint16_t)((queue->tail + 1U) % EVENT_QUEUE_CAPACITY);
        queue->count++;
        ok = true;
    }
    event_queue_exit_critical(primask);

    return ok;
}

bool event_queue_push_from_isr(event_queue_t *queue, const event_t *event)
{
    if ((queue == 0) || (event == 0))
    {
        return false;
    }

    if (queue->count >= EVENT_QUEUE_CAPACITY)
    {
        return false;
    }

    queue->buffer[queue->tail] = *event;
    queue->tail = (uint16_t)((queue->tail + 1U) % EVENT_QUEUE_CAPACITY);
    queue->count++;
    return true;
}

bool event_queue_pop(event_queue_t *queue, event_t *event)
{
    uint32_t primask;
    bool ok = false;

    if ((queue == 0) || (event == 0))
    {
        return false;
    }

    primask = event_queue_enter_critical();
    if (queue->count > 0U)
    {
        *event = queue->buffer[queue->head];
        queue->head = (uint16_t)((queue->head + 1U) % EVENT_QUEUE_CAPACITY);
        queue->count--;
        ok = true;
    }
    event_queue_exit_critical(primask);

    return ok;
}

uint16_t event_queue_count(const event_queue_t *queue)
{
    if (queue == 0)
    {
        return 0U;
    }

    return queue->count;
}
