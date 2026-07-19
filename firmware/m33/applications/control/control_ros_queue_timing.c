#include "control_ros_queue_timing.h"

rt_bool_t control_ros_queue_is_stale(rt_tick_t now,
                                     rt_tick_t received_tick,
                                     rt_tick_t ttl_ticks,
                                     rt_bool_t emergency_command)
{
    if (emergency_command)
    {
        return RT_FALSE;
    }

    return ((now - received_tick) > ttl_ticks) ? RT_TRUE : RT_FALSE;
}
