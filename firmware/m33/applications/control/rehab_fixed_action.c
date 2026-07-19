#include "rehab_fixed_action.h"

static const rehab_fixed_action_profile_t s_profiles[] = {
    {
        .id = REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND,
        .enabled = RT_TRUE,
        .joint_mask = REHAB_FIXED_ACTION_JOINT5_MASK,
        .joint = {
            [5] = {
                .active = RT_TRUE,
                .hard_min_rad = 6.000f,
                .hard_max_rad = 8.264f,
                .safe_min_rad = 6.226f,
                .safe_max_rad = 8.038f,
            },
        },
        .max_velocity_rad_s = 0.12f,
        .max_accel_rad_s2 = 0.20f,
        .max_jerk_rad_s3 = 0.50f,
        .max_feedback_velocity_rad_s = 0.35f,
        .dwell_ms = 500U,
        .repetitions = 3U,
    },
    {
        .id = REHAB_FIXED_ACTION_SHOULDER_PLANAR,
        .enabled = RT_TRUE,
        .joint_mask = REHAB_FIXED_ACTION_JOINT6_MASK,
        .joint = {
            [6] = {
                .active = RT_TRUE,
                .hard_min_rad = 3.532f,
                .hard_max_rad = 5.101f,
                .safe_min_rad = 3.689f,
                .safe_max_rad = 4.944f,
            },
        },
        .max_velocity_rad_s = 0.12f,
        .max_accel_rad_s2 = 0.20f,
        .max_jerk_rad_s3 = 0.50f,
        .max_feedback_velocity_rad_s = 0.35f,
        .dwell_ms = 500U,
        .repetitions = 3U,
    },
    {
        .id = REHAB_FIXED_ACTION_COORDINATED,
        .enabled = RT_TRUE,
        .joint_mask = REHAB_FIXED_ACTION_JOINT56_MASK,
        .joint = {
            [5] = {
                .active = RT_TRUE,
                .hard_min_rad = 6.000f,
                .hard_max_rad = 8.264f,
                .safe_min_rad = 6.226f,
                .safe_max_rad = 8.038f,
            },
            [6] = {
                .active = RT_TRUE,
                .hard_min_rad = 3.532f,
                .hard_max_rad = 5.101f,
                .safe_min_rad = 3.689f,
                .safe_max_rad = 4.944f,
            },
        },
        .max_velocity_rad_s = 0.12f,
        .max_accel_rad_s2 = 0.20f,
        .max_jerk_rad_s3 = 0.50f,
        .max_feedback_velocity_rad_s = 0.35f,
        .dwell_ms = 500U,
        .repetitions = 3U,
    },
    {
        .id = REHAB_FIXED_ACTION_SHOULDER_FORE_AFT,
        .enabled = RT_FALSE,
        .joint_mask = 0x08U,
        .max_velocity_rad_s = 0.12f,
        .max_accel_rad_s2 = 0.20f,
        .max_jerk_rad_s3 = 0.50f,
        .max_feedback_velocity_rad_s = 0.35f,
        .dwell_ms = 500U,
        .repetitions = 3U,
    },
};

static rt_bool_t fixed_mask_has(rt_uint8_t mask, rt_uint8_t joint)
{
    return ((mask & (rt_uint8_t)(1U << (joint - 1U))) != 0U) ? RT_TRUE : RT_FALSE;
}

static rt_bool_t fixed_position_inside(const rehab_fixed_action_joint_profile_t *joint,
                                       float position_rad)
{
    return ((position_rad >= joint->hard_min_rad) &&
            (position_rad <= joint->hard_max_rad))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_err_t fixed_feedback_valid(const rehab_fixed_action_profile_t *profile,
                                     const rehab_fixed_action_feedback_t *feedback)
{
    rt_uint8_t joint;

    if ((profile == RT_NULL) || (feedback == RT_NULL))
    {
        return -RT_EINVAL;
    }
    for (joint = 1U; joint < REHAB_FIXED_ACTION_JOINT_SLOTS; joint++)
    {
        const rehab_fixed_action_joint_profile_t *joint_profile = &profile->joint[joint];

        if (!fixed_mask_has(profile->joint_mask, joint))
        {
            continue;
        }
        if (((feedback->fresh_mask & (rt_uint8_t)(1U << (joint - 1U))) == 0U) ||
            ((feedback->fault_mask & (rt_uint8_t)(1U << (joint - 1U))) != 0U))
        {
            return -RT_ERROR;
        }
        if (!fixed_position_inside(joint_profile, feedback->position_rad[joint]))
        {
            return -RT_ERROR;
        }
        if ((feedback->velocity_rad_s[joint] > profile->max_feedback_velocity_rad_s) ||
            (feedback->velocity_rad_s[joint] < -profile->max_feedback_velocity_rad_s))
        {
            return -RT_ERROR;
        }
    }
    return RT_EOK;
}

static rt_err_t fixed_plan_segment(rehab_fixed_action_runner_t *runner,
                                   const rehab_fixed_action_feedback_t *feedback,
                                   rt_bool_t to_safe_max,
                                   rt_uint32_t now_ms)
{
    rt_uint32_t max_duration_ms = 1U;
    rt_uint8_t joint;

    for (joint = 1U; joint < REHAB_FIXED_ACTION_JOINT_SLOTS; joint++)
    {
        const rehab_fixed_action_joint_profile_t *joint_profile;
        float target_rad;
        rt_err_t ret;

        if (!fixed_mask_has(runner->profile->joint_mask, joint))
        {
            continue;
        }

        joint_profile = &runner->profile->joint[joint];
        target_rad = to_safe_max ? joint_profile->safe_max_rad : joint_profile->safe_min_rad;
        ret = rehab_scurve_plan(&runner->segment[joint],
                                feedback->position_rad[joint],
                                target_rad,
                                runner->profile->max_velocity_rad_s,
                                runner->profile->max_accel_rad_s2,
                                runner->profile->max_jerk_rad_s3);
        if (ret != RT_EOK)
        {
            return ret;
        }
        if (runner->segment[joint].duration_ms > max_duration_ms)
        {
            max_duration_ms = runner->segment[joint].duration_ms;
        }
    }

    for (joint = 1U; joint < REHAB_FIXED_ACTION_JOINT_SLOTS; joint++)
    {
        if (fixed_mask_has(runner->profile->joint_mask, joint))
        {
            runner->segment[joint].duration_ms = max_duration_ms;
        }
    }
    runner->segment_duration_ms = max_duration_ms;
    runner->segment_started_ms = now_ms;
    return RT_EOK;
}

static void fixed_latch_fault(rehab_fixed_action_runner_t *runner, rt_err_t result)
{
    runner->state = REHAB_FIXED_ACTION_STATE_FAULT;
    runner->fault = result;
}

const rehab_fixed_action_profile_t *rehab_fixed_action_profile(rehab_fixed_action_id_t id)
{
    rt_uint32_t i;

    for (i = 0U; i < (sizeof(s_profiles) / sizeof(s_profiles[0])); i++)
    {
        if (s_profiles[i].id == id)
        {
            return &s_profiles[i];
        }
    }
    return RT_NULL;
}

rt_err_t rehab_fixed_action_start(rehab_fixed_action_runner_t *runner,
                                  rehab_fixed_action_id_t id,
                                  const rehab_fixed_action_feedback_t *feedback,
                                  rt_uint32_t now_ms)
{
    const rehab_fixed_action_profile_t *profile;
    rt_err_t ret;

    profile = rehab_fixed_action_profile(id);
    if ((runner == RT_NULL) || (profile == RT_NULL) || !profile->enabled)
    {
        return -RT_EINVAL;
    }
    ret = fixed_feedback_valid(profile, feedback);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(runner, 0, sizeof(*runner));
    runner->profile = profile;
    runner->state = REHAB_FIXED_ACTION_STATE_CSP_PREPARE;
    runner->segment_started_ms = now_ms;
    return RT_EOK;
}

void rehab_fixed_action_step(rehab_fixed_action_runner_t *runner,
                             const rehab_fixed_action_feedback_t *feedback,
                             rt_uint32_t now_ms,
                             rehab_fixed_action_output_t *out)
{
    rt_uint8_t joint;

    if (out == RT_NULL)
    {
        return;
    }
    rt_memset(out, 0, sizeof(*out));
    if ((runner == RT_NULL) || (runner->profile == RT_NULL))
    {
        out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
        out->result = -RT_EINVAL;
        out->state = REHAB_FIXED_ACTION_STATE_FAULT;
        return;
    }

    out->state = runner->state;
    out->joint_mask = runner->profile->joint_mask;
    out->completed_repetitions = runner->completed_repetitions;

    if (runner->state == REHAB_FIXED_ACTION_STATE_FAULT)
    {
        out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
        out->result = runner->fault;
        return;
    }
    if (runner->state == REHAB_FIXED_ACTION_STATE_COMPLETE)
    {
        out->result = RT_EOK;
        return;
    }

    if (fixed_feedback_valid(runner->profile, feedback) != RT_EOK)
    {
        fixed_latch_fault(runner, -RT_ERROR);
        out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
        out->result = runner->fault;
        out->state = runner->state;
        return;
    }

    if (runner->state == REHAB_FIXED_ACTION_STATE_CSP_PREPARE)
    {
        rt_err_t ret;

        ret = fixed_plan_segment(runner, feedback, RT_FALSE, now_ms);
        if (ret != RT_EOK)
        {
            fixed_latch_fault(runner, ret);
            out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
            out->result = ret;
            out->state = runner->state;
            return;
        }
        runner->state = REHAB_FIXED_ACTION_STATE_MOVE_A;
        out->action = REHAB_FIXED_ACTION_OUTPUT_PREPARE;
        out->result = RT_EOK;
        out->state = REHAB_FIXED_ACTION_STATE_CSP_PREPARE;
        return;
    }

    if ((runner->state == REHAB_FIXED_ACTION_STATE_MOVE_A) ||
        (runner->state == REHAB_FIXED_ACTION_STATE_MOVE_B))
    {
        rt_uint32_t elapsed_ms = now_ms - runner->segment_started_ms;

        for (joint = 1U; joint < REHAB_FIXED_ACTION_JOINT_SLOTS; joint++)
        {
            rehab_scurve_sample_t sample;

            if (!fixed_mask_has(runner->profile->joint_mask, joint))
            {
                continue;
            }
            (void)rehab_scurve_sample(&runner->segment[joint], elapsed_ms, &sample);
            out->target_rad[joint] = sample.position_rad;
        }
        out->action = REHAB_FIXED_ACTION_OUTPUT_SETPOINT;
        out->result = RT_EOK;
        if (elapsed_ms >= runner->segment_duration_ms)
        {
            runner->state = (runner->state == REHAB_FIXED_ACTION_STATE_MOVE_A)
                                ? REHAB_FIXED_ACTION_STATE_DWELL_A
                                : REHAB_FIXED_ACTION_STATE_DWELL_B;
            runner->dwell_started_ms = now_ms;
            out->state = runner->state;
        }
        else
        {
            out->state = runner->state;
        }
        return;
    }

    if ((runner->state == REHAB_FIXED_ACTION_STATE_DWELL_A) &&
        ((rt_uint32_t)(now_ms - runner->dwell_started_ms) >= runner->profile->dwell_ms))
    {
        rt_err_t ret = fixed_plan_segment(runner, feedback, RT_TRUE, now_ms);

        if (ret != RT_EOK)
        {
            fixed_latch_fault(runner, ret);
            out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
            out->result = ret;
            out->state = runner->state;
            return;
        }
        runner->state = REHAB_FIXED_ACTION_STATE_MOVE_B;
    }
    else if ((runner->state == REHAB_FIXED_ACTION_STATE_DWELL_B) &&
             ((rt_uint32_t)(now_ms - runner->dwell_started_ms) >= runner->profile->dwell_ms))
    {
        runner->completed_repetitions++;
        if (runner->completed_repetitions >= runner->profile->repetitions)
        {
            runner->state = REHAB_FIXED_ACTION_STATE_COMPLETE;
        }
        else
        {
            rt_err_t ret = fixed_plan_segment(runner, feedback, RT_FALSE, now_ms);

            if (ret != RT_EOK)
            {
                fixed_latch_fault(runner, ret);
                out->action = REHAB_FIXED_ACTION_OUTPUT_STOP;
                out->result = ret;
                out->state = runner->state;
                return;
            }
            runner->state = REHAB_FIXED_ACTION_STATE_MOVE_A;
        }
    }

    out->state = runner->state;
    out->completed_repetitions = runner->completed_repetitions;
    out->result = RT_EOK;
}
