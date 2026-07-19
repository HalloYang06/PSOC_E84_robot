#include <assert.h>
#include <stdio.h>

#include "control_ros_emergency_latch.h"

static void test_multiple_joint_stops_are_preserved(void)
{
    control_ros_emergency_latch_t latch = {0};
    control_ros_emergency_item_t item;

    assert(control_ros_emergency_latch_stop(&latch, 4U, RT_FALSE) == RT_TRUE);
    assert(control_ros_emergency_latch_stop(&latch, 5U, RT_TRUE) == RT_TRUE);

    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.kind == CONTROL_ROS_EMERGENCY_STOP);
    assert(item.joint_id == 4U);
    assert(item.clear_fault == RT_FALSE);

    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.kind == CONTROL_ROS_EMERGENCY_STOP);
    assert(item.joint_id == 5U);
    assert(item.clear_fault == RT_TRUE);
    assert(control_ros_emergency_take(&latch, &item) == RT_FALSE);
}

static void test_passive_does_not_discard_pending_stops(void)
{
    control_ros_emergency_latch_t latch = {0};
    control_ros_emergency_item_t item;

    assert(control_ros_emergency_latch_stop(&latch, 4U, RT_FALSE) == RT_TRUE);
    control_ros_emergency_latch_passive(&latch, 23U);
    assert(control_ros_emergency_latch_stop(&latch, 5U, RT_FALSE) == RT_TRUE);

    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.kind == CONTROL_ROS_EMERGENCY_PASSIVE);
    assert(item.sequence == 23U);
    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.joint_id == 4U);
    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.joint_id == 5U);
}

static void test_clear_fault_request_is_not_lost(void)
{
    control_ros_emergency_latch_t latch = {0};
    control_ros_emergency_item_t item;

    assert(control_ros_emergency_latch_stop(&latch, 3U, RT_TRUE) == RT_TRUE);
    assert(control_ros_emergency_latch_stop(&latch, 3U, RT_FALSE) == RT_TRUE);
    assert(control_ros_emergency_take(&latch, &item) == RT_TRUE);
    assert(item.clear_fault == RT_TRUE);
}

static void test_out_of_range_joint_is_rejected(void)
{
    control_ros_emergency_latch_t latch = {0};

    assert(control_ros_emergency_latch_stop(&latch, 32U, RT_FALSE) == RT_FALSE);
}

int main(void)
{
    test_multiple_joint_stops_are_preserved();
    test_passive_does_not_discard_pending_stops();
    test_clear_fault_request_is_not_lost();
    test_out_of_range_joint_is_rejected();
    puts("control_ros_emergency_latch_test PASS");
    return 0;
}
