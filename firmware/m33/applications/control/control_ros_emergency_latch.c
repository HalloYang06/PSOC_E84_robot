#include "control_ros_emergency_latch.h"

void control_ros_emergency_latch_passive(control_ros_emergency_latch_t *latch,
                                         rt_uint8_t sequence)
{
    if (latch == RT_NULL)
    {
        return;
    }

    latch->passive_sequence = sequence;
    latch->passive_pending = RT_TRUE;
}

rt_bool_t control_ros_emergency_latch_stop(control_ros_emergency_latch_t *latch,
                                           rt_uint8_t joint_id,
                                           rt_bool_t clear_fault)
{
    rt_uint32_t joint_bit;

    if ((latch == RT_NULL) || (joint_id >= 32U))
    {
        return RT_FALSE;
    }

    joint_bit = 1UL << joint_id;
    latch->stop_pending_mask |= joint_bit;
    if (clear_fault)
    {
        latch->stop_clear_fault_mask |= joint_bit;
    }
    return RT_TRUE;
}

rt_bool_t control_ros_emergency_take(control_ros_emergency_latch_t *latch,
                                     control_ros_emergency_item_t *item)
{
    rt_uint8_t joint_id;
    rt_uint32_t joint_bit;

    if ((latch == RT_NULL) || (item == RT_NULL))
    {
        return RT_FALSE;
    }

    if (latch->passive_pending)
    {
        item->kind = CONTROL_ROS_EMERGENCY_PASSIVE;
        item->sequence = latch->passive_sequence;
        item->joint_id = 0U;
        item->clear_fault = RT_FALSE;
        latch->passive_pending = RT_FALSE;
        return RT_TRUE;
    }

    for (joint_id = 0U; joint_id < 32U; joint_id++)
    {
        joint_bit = 1UL << joint_id;
        if ((latch->stop_pending_mask & joint_bit) != 0U)
        {
            item->kind = CONTROL_ROS_EMERGENCY_STOP;
            item->sequence = 0U;
            item->joint_id = joint_id;
            item->clear_fault = ((latch->stop_clear_fault_mask & joint_bit) != 0U) ?
                                RT_TRUE : RT_FALSE;
            latch->stop_pending_mask &= ~joint_bit;
            latch->stop_clear_fault_mask &= ~joint_bit;
            return RT_TRUE;
        }
    }

    item->kind = CONTROL_ROS_EMERGENCY_NONE;
    return RT_FALSE;
}
