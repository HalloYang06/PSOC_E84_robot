#ifndef CONTROL_ROS_QUEUE_TIMING_H
#define CONTROL_ROS_QUEUE_TIMING_H

#include <rtthread.h>

rt_bool_t control_ros_queue_is_stale(rt_tick_t now,
                                     rt_tick_t received_tick,
                                     rt_tick_t ttl_ticks,
                                     rt_bool_t emergency_command);

#endif
