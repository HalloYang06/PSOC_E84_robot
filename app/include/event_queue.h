#ifndef EVENT_QUEUE_H
#define EVENT_QUEUE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
    EVENT_NONE = 0,
    EVENT_TICK_1MS,
    EVENT_EMG_SAMPLE_READY,
    EVENT_HR_INT,
    EVENT_HR_POLL,
    EVENT_CAN_RX_PENDING,
    EVENT_CAN_TX_RETRY,
    EVENT_FAULT
} event_id_t;

typedef struct
{
    event_id_t id;
    uint32_t arg0;
    uint32_t arg1;
} event_t;

#define EVENT_QUEUE_CAPACITY 64U

typedef struct
{
    event_t buffer[EVENT_QUEUE_CAPACITY];
    volatile uint16_t head;
    volatile uint16_t tail;
    volatile uint16_t count;
} event_queue_t;

void event_queue_init(event_queue_t *queue);
bool event_queue_push(event_queue_t *queue, const event_t *event);
bool event_queue_push_from_isr(event_queue_t *queue, const event_t *event);
bool event_queue_pop(event_queue_t *queue, event_t *event);
uint16_t event_queue_count(const event_queue_t *queue);

#endif
