#include <assert.h>
#include <math.h>
#include <stdio.h>

#include "rehab_fixed_action.h"

static rehab_fixed_action_feedback_t zero_feedback(void)
{
    rehab_fixed_action_feedback_t feedback;

    rt_memset(&feedback, 0, sizeof(feedback));
    feedback.fresh_mask = 0x30U;
    feedback.position_rad[5] = 7.000f;
    feedback.position_rad[6] = 4.200f;
    return feedback;
}

static void test_profiles_expose_safe_internal_masks(void)
{
    const rehab_fixed_action_profile_t *elbow;
    const rehab_fixed_action_profile_t *shoulder;
    const rehab_fixed_action_profile_t *coordinated;
    const rehab_fixed_action_profile_t *placeholder;

    elbow = rehab_fixed_action_profile(REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND);
    shoulder = rehab_fixed_action_profile(REHAB_FIXED_ACTION_SHOULDER_PLANAR);
    coordinated = rehab_fixed_action_profile(REHAB_FIXED_ACTION_COORDINATED);
    placeholder = rehab_fixed_action_profile(REHAB_FIXED_ACTION_SHOULDER_FORE_AFT);

    assert(elbow != RT_NULL);
    assert(elbow->joint_mask == 0x10U);
    assert(fabsf(elbow->joint[5].safe_min_rad - 6.226f) < 0.0001f);
    assert(fabsf(elbow->joint[5].safe_max_rad - 8.038f) < 0.0001f);
    assert(shoulder != RT_NULL);
    assert(shoulder->joint_mask == 0x20U);
    assert(coordinated != RT_NULL);
    assert(coordinated->joint_mask == 0x30U);
    assert(placeholder != RT_NULL);
    assert(placeholder->enabled == RT_FALSE);
}

static void test_disabled_or_unsafe_start_rejects_without_motion(void)
{
    rehab_fixed_action_runner_t runner;
    rehab_fixed_action_feedback_t feedback = zero_feedback();

    assert(rehab_fixed_action_start(&runner,
                                    REHAB_FIXED_ACTION_SHOULDER_FORE_AFT,
                                    &feedback,
                                    0U) == -RT_EINVAL);

    feedback.position_rad[5] = 9.000f;
    assert(rehab_fixed_action_start(&runner,
                                    REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND,
                                    &feedback,
                                    0U) == -RT_ERROR);
}

static void test_single_joint_outputs_prepare_then_smooth_setpoints(void)
{
    rehab_fixed_action_runner_t runner;
    rehab_fixed_action_feedback_t feedback = zero_feedback();
    rehab_fixed_action_output_t output;
    rt_uint32_t t;
    float previous = feedback.position_rad[5];

    assert(rehab_fixed_action_start(&runner,
                                    REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND,
                                    &feedback,
                                    100U) == RT_EOK);
    rehab_fixed_action_step(&runner, &feedback, 100U, &output);
    assert(output.action == REHAB_FIXED_ACTION_OUTPUT_PREPARE);
    assert(output.joint_mask == 0x10U);

    for (t = 120U; t < 20000U; t += 20U)
    {
        rehab_fixed_action_step(&runner, &feedback, t, &output);
        if (output.action == REHAB_FIXED_ACTION_OUTPUT_SETPOINT)
        {
            assert(output.joint_mask == 0x10U);
            assert(output.target_rad[5] <= previous + 0.001f);
            assert(output.target_rad[5] >= 6.226f - 0.001f);
            assert(output.target_rad[5] <= 8.038f + 0.001f);
            previous = output.target_rad[5];
            feedback.position_rad[5] = output.target_rad[5];
        }
        if (output.state == REHAB_FIXED_ACTION_STATE_DWELL_A)
        {
            return;
        }
    }
    assert(0 && "elbow action did not reach dwell A");
}

static void test_coordinated_action_outputs_both_joint_setpoints(void)
{
    rehab_fixed_action_runner_t runner;
    rehab_fixed_action_feedback_t feedback = zero_feedback();
    rehab_fixed_action_output_t output;

    assert(rehab_fixed_action_start(&runner,
                                    REHAB_FIXED_ACTION_COORDINATED,
                                    &feedback,
                                    200U) == RT_EOK);
    rehab_fixed_action_step(&runner, &feedback, 200U, &output);
    assert(output.action == REHAB_FIXED_ACTION_OUTPUT_PREPARE);
    rehab_fixed_action_step(&runner, &feedback, 220U, &output);
    assert(output.action == REHAB_FIXED_ACTION_OUTPUT_SETPOINT);
    assert(output.joint_mask == 0x30U);
    assert(output.target_rad[5] >= 6.226f - 0.001f);
    assert(output.target_rad[5] <= 8.038f + 0.001f);
    assert(output.target_rad[6] >= 3.689f - 0.001f);
    assert(output.target_rad[6] <= 4.944f + 0.001f);
}

static void test_runner_completes_three_round_trips(void)
{
    rehab_fixed_action_runner_t runner;
    rehab_fixed_action_feedback_t feedback = zero_feedback();
    rehab_fixed_action_output_t output;
    rt_uint32_t t;

    assert(rehab_fixed_action_start(&runner,
                                    REHAB_FIXED_ACTION_SHOULDER_PLANAR,
                                    &feedback,
                                    0U) == RT_EOK);
    for (t = 0U; t < 180000U; t += 20U)
    {
        rehab_fixed_action_step(&runner, &feedback, t, &output);
        if (output.action == REHAB_FIXED_ACTION_OUTPUT_SETPOINT)
        {
            feedback.position_rad[6] = output.target_rad[6];
        }
        if (output.state == REHAB_FIXED_ACTION_STATE_COMPLETE)
        {
            assert(output.completed_repetitions == 3U);
            return;
        }
    }
    assert(0 && "fixed action did not complete three repetitions");
}

int main(void)
{
    test_profiles_expose_safe_internal_masks();
    test_disabled_or_unsafe_start_rejects_without_motion();
    test_single_joint_outputs_prepare_then_smooth_setpoints();
    test_coordinated_action_outputs_both_joint_setpoints();
    test_runner_completes_three_round_trips();
    puts("rehab_fixed_action_test: PASS");
    return 0;
}
