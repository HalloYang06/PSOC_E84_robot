#ifndef TEST_HOST_REHAB_HOST_PREINCLUDE_H
#define TEST_HOST_REHAB_HOST_PREINCLUDE_H

#include "rtthread.h"

#ifndef __CONTROL_LAYER_H__
#define __CONTROL_LAYER_H__

typedef enum
{
    CONTROL_MOTOR_PROTOCOL_TYPE_PRIVATE = 0,
    CONTROL_MOTOR_PROTOCOL_TYPE_CANSIMPLE = 1,
} control_motor_protocol_type_t;

typedef struct
{
    rt_uint8_t motor_id;
    control_motor_protocol_type_t protocol;
    rt_uint8_t mode_state;
    rt_uint8_t fault_summary;
    float pos_rad;
    float vel_rad_s;
    float torque_nm;
    float temp_c;
    rt_tick_t timestamp;
} control_motor_feedback_t;

#endif /* __CONTROL_LAYER_H__ */

#endif /* TEST_HOST_REHAB_HOST_PREINCLUDE_H */
