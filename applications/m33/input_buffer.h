#ifndef INPUT_BUFFER_H
#define INPUT_BUFFER_H

#include <rtthread.h>

typedef enum
{
    EV_NONE = 0,
    EV_EMG,
    EV_HEART_RATE,
    EV_IMU_ACCEL,
    EV_IMU_GYRO,
    EV_MOTOR_FEEDBACK,
    EV_AI_RESULT
} input_event_type_t;

typedef struct
{
    input_event_type_t type;
    rt_tick_t timestamp;
    rt_uint32_t value_count;
    float values[8];
} input_event_t;

rt_err_t input_buffer_init(void);
rt_err_t input_buffer_push(const input_event_t *event);
rt_err_t input_buffer_pop(input_event_t *event);

#endif
