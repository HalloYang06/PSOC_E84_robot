#ifndef CONTROL_ROS_EMERGENCY_LATCH_H
#define CONTROL_ROS_EMERGENCY_LATCH_H

#include <rtthread.h>

typedef enum
{
    CONTROL_ROS_EMERGENCY_NONE = 0,
    CONTROL_ROS_EMERGENCY_PASSIVE,
    CONTROL_ROS_EMERGENCY_STOP,
} control_ros_emergency_kind_t;

typedef struct
{
    rt_bool_t passive_pending;
    rt_uint8_t passive_sequence;
    rt_uint32_t stop_pending_mask;
    rt_uint32_t stop_clear_fault_mask;
} control_ros_emergency_latch_t;

typedef struct
{
    control_ros_emergency_kind_t kind;
    rt_uint8_t sequence;
    rt_uint8_t joint_id;
    rt_bool_t clear_fault;
} control_ros_emergency_item_t;

void control_ros_emergency_latch_passive(control_ros_emergency_latch_t *latch,
                                         rt_uint8_t sequence);
rt_bool_t control_ros_emergency_latch_stop(control_ros_emergency_latch_t *latch,
                                           rt_uint8_t joint_id,
                                           rt_bool_t clear_fault);
rt_bool_t control_ros_emergency_take(control_ros_emergency_latch_t *latch,
                                     control_ros_emergency_item_t *item);

#endif
