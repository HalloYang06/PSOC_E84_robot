#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "control_ros_queue_timing.h"

static void test_command_is_fresh_at_ttl_boundary(void)
{
    assert(control_ros_queue_is_stale(600U, 100U, 500U, RT_FALSE) == RT_FALSE);
}

static void test_command_is_stale_after_ttl(void)
{
    assert(control_ros_queue_is_stale(601U, 100U, 500U, RT_FALSE) == RT_TRUE);
}

static void test_tick_wrap_uses_unsigned_elapsed_time(void)
{
    assert(control_ros_queue_is_stale(20U, UINT32_MAX - 19U, 40U, RT_FALSE) == RT_FALSE);
    assert(control_ros_queue_is_stale(21U, UINT32_MAX - 19U, 40U, RT_FALSE) == RT_TRUE);
}

static void test_emergency_command_bypasses_age_rejection(void)
{
    assert(control_ros_queue_is_stale(10000U, 1U, 500U, RT_TRUE) == RT_FALSE);
}

int main(void)
{
    test_command_is_fresh_at_ttl_boundary();
    test_command_is_stale_after_ttl();
    test_tick_wrap_uses_unsigned_elapsed_time();
    test_emergency_command_bypasses_age_rejection();
    puts("control_ros_queue_timing_test PASS");
    return 0;
}
