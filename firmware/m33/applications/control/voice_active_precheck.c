#include "voice_active_precheck.h"

#include <finsh.h>

#include "control_layer.h"

#define CONTROL_VOICE_PRECHECK_FIRST_JOINT_ID 4U
#define CONTROL_VOICE_PRECHECK_LAST_JOINT_ID 6U
#define CONTROL_VOICE_PRECHECK_JOINT_MASK 0x38U
#define CONTROL_VOICE_PRECHECK_MAX_AGE_MS 100U
#define CONTROL_VOICE_PRECHECK_AGE_UNAVAILABLE 0xFFFFFFFFUL

static control_voice_precheck_diag_t s_voice_precheck_diag;

static rt_uint32_t voice_precheck_age_ms(rt_tick_t now, rt_tick_t then)
{
    return (rt_uint32_t)(((rt_uint64_t)(now - then) * 1000ULL) /
                         RT_TICK_PER_SECOND);
}

static void voice_precheck_record(const control_voice_precheck_result_t *result)
{
    rt_base_t level = rt_hw_interrupt_disable();
    rt_uint32_t reason = result->reason_mask;

    s_voice_precheck_diag.total++;
    if (result->passed)
    {
        s_voice_precheck_diag.pass++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_NOT_INIT) != 0U)
    {
        s_voice_precheck_diag.reject_not_init++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_NO_FEEDBACK) != 0U)
    {
        s_voice_precheck_diag.reject_no_feedback++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_STALE) != 0U)
    {
        s_voice_precheck_diag.reject_stale++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_PROTOCOL) != 0U)
    {
        s_voice_precheck_diag.reject_protocol++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_ID) != 0U)
    {
        s_voice_precheck_diag.reject_id++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_CALIBRATION) != 0U)
    {
        s_voice_precheck_diag.reject_calibration++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_FAULT) != 0U)
    {
        s_voice_precheck_diag.reject_fault++;
    }
    if ((reason & CONTROL_VOICE_PRECHECK_REJECT_MODE) != 0U)
    {
        s_voice_precheck_diag.reject_mode++;
    }
    s_voice_precheck_diag.last = *result;
    rt_hw_interrupt_enable(level);
}

static void voice_precheck_assess_joint(rt_uint8_t joint_id,
                                        control_voice_precheck_result_t *result)
{
    control_motor_feedback_t feedback;
    rt_bool_t have_feedback = RT_FALSE;

    *result = (control_voice_precheck_result_t){0};
    result->joint_id = joint_id;
    result->motor_id = joint_id;
    result->age_ms = CONTROL_VOICE_PRECHECK_AGE_UNAVAILABLE;
    result->assessment_tick = rt_tick_get();

    if ((control_get_motor_feedback(joint_id, &feedback) == RT_EOK) &&
        (feedback.timestamp != 0U))
    {
        have_feedback = RT_TRUE;
        result->motor_id = feedback.motor_id;
        result->protocol = (rt_uint8_t)feedback.protocol;
        result->mode_state = feedback.mode_state;
        result->fault_summary = feedback.fault_summary;
        result->assessment_tick = rt_tick_get();
        result->age_ms = voice_precheck_age_ms(result->assessment_tick,
                                               feedback.timestamp);
    }
    else
    {
        result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_NO_FEEDBACK;
    }

    if (!control_motor_is_joint_calibrated(joint_id))
    {
        result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_CALIBRATION;
    }

    if (have_feedback)
    {
        if (result->age_ms > CONTROL_VOICE_PRECHECK_MAX_AGE_MS)
        {
            result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_STALE;
        }
        if (feedback.protocol != CONTROL_MOTOR_PROTOCOL_TYPE_PRIVATE)
        {
            result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_PROTOCOL;
        }
        if (feedback.motor_id != joint_id)
        {
            result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_ID;
        }
        if (feedback.fault_summary != 0U)
        {
            result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_FAULT;
        }
        if (feedback.mode_state != 0U)
        {
            result->reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_MODE;
        }
    }

    result->passed = (result->reason_mask == 0U) ? RT_TRUE : RT_FALSE;
}

rt_err_t control_voice_precheck_assess(control_voice_precheck_result_t *out)
{
    control_voice_precheck_result_t result = {0};
    rt_uint8_t joint_id;

    if (out == RT_NULL)
    {
        return -RT_EINVAL;
    }

    result.age_ms = CONTROL_VOICE_PRECHECK_AGE_UNAVAILABLE;
    result.assessment_tick = rt_tick_get();
    result.joint_id = CONTROL_VOICE_PRECHECK_FIRST_JOINT_ID;
    result.motor_id = CONTROL_VOICE_PRECHECK_FIRST_JOINT_ID;

    if (!control_layer_is_initialized())
    {
        result.reason_mask |= CONTROL_VOICE_PRECHECK_REJECT_NOT_INIT;
    }
    else
    {
        for (joint_id = CONTROL_VOICE_PRECHECK_FIRST_JOINT_ID;
             joint_id <= CONTROL_VOICE_PRECHECK_LAST_JOINT_ID;
             joint_id++)
        {
            voice_precheck_assess_joint(joint_id, &result);
            if (!result.passed)
            {
                break;
            }
        }
    }

    result.passed = (result.reason_mask == 0U) ? RT_TRUE : RT_FALSE;
    voice_precheck_record(&result);
    *out = result;
    return RT_EOK;
}

void control_voice_precheck_diag_snapshot(control_voice_precheck_diag_t *out)
{
    rt_base_t level;

    if (out == RT_NULL)
    {
        return;
    }

    level = rt_hw_interrupt_disable();
    *out = s_voice_precheck_diag;
    rt_hw_interrupt_enable(level);
}

static int cmd_voice_precheck(int argc, char **argv)
{
    control_voice_precheck_result_t result;
    control_voice_precheck_diag_t diag;

    (void)argc;
    (void)argv;
    if (control_voice_precheck_assess(&result) != RT_EOK)
    {
        rt_kprintf("VOICE_PRECHECK: result=ERROR\n");
        return -1;
    }
    control_voice_precheck_diag_snapshot(&diag);

    rt_kprintf("VOICE_PRECHECK: result=%s joint=%u mask=0x%02X reason=0x%08lX age_ms=%lu fault=0x%02X mode=%u proto=%u id=%u tick=%lu\n",
               result.passed ? "PASS" : "REJECT",
               (unsigned int)result.joint_id,
               (unsigned int)CONTROL_VOICE_PRECHECK_JOINT_MASK,
               (unsigned long)result.reason_mask,
               (unsigned long)result.age_ms,
               (unsigned int)result.fault_summary,
               (unsigned int)result.mode_state,
               (unsigned int)result.protocol,
               (unsigned int)result.motor_id,
               (unsigned long)result.assessment_tick);
    rt_kprintf("VOICE_PRECHECK_CNT: total=%lu pass=%lu not_init=%lu no_feedback=%lu stale=%lu protocol=%lu id=%lu calibration=%lu fault=%lu mode=%lu\n",
               (unsigned long)diag.total,
               (unsigned long)diag.pass,
               (unsigned long)diag.reject_not_init,
               (unsigned long)diag.reject_no_feedback,
               (unsigned long)diag.reject_stale,
               (unsigned long)diag.reject_protocol,
               (unsigned long)diag.reject_id,
               (unsigned long)diag.reject_calibration,
               (unsigned long)diag.reject_fault,
               (unsigned long)diag.reject_mode);
    return result.passed ? 0 : -1;
}
MSH_CMD_EXPORT(cmd_voice_precheck, assess joint4-6 voice active pre-entry without motion);
