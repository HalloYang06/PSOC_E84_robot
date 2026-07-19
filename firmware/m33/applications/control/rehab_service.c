#include "rehab_service.h"

#include "control_layer.h"
#include "control_layer_cfg.h"
#include "rehab_active_follow.h"
#include "rehab_assist_safety.h"
#include "rehab_assist_strategy.h"
#include "rehab_curl_planner.h"
#include "rehab_fixed_action.h"
#include "rehab_intensity_level.h"
#include "rehab_resist_strategy.h"
#include "rehab_trajectory_bank.h"
#include "rehab_worker_timing.h"

typedef struct
{
    struct rt_mutex actuation_lock;
    struct rt_mutex lock;
    rt_thread_t thread;
    rehab_service_status_t status;
    rehab_strategy_params_t params;
    rehab_assist_strategy_state_t assist_state[CONTROL_MOTOR_JOINT_COUNT];
    rehab_resist_strategy_state_t resist_state[CONTROL_MOTOR_JOINT_COUNT];
    rehab_worker_timing_t worker_timing;
    rehab_curl_planner_t curl_planner;
    rehab_fixed_action_runner_t fixed_action_runner;
    rt_tick_t last_record_tick;
    rt_bool_t initialized;
    rt_bool_t stopped_for_fault;
    rt_bool_t stop_pending;
} rehab_service_runtime_t;

static rehab_service_runtime_t s_rehab;

static rt_uint32_t rehab_ticks_to_ms_u32(rt_tick_t ticks)
{
    return (rt_uint32_t)(((rt_uint64_t)ticks * 1000ULL) / RT_TICK_PER_SECOND);
}

static rehab_curl_config_t rehab_service_curl_config(void)
{
    rehab_curl_config_t config = {
        .hard_min_pos_rad = CONTROL_REHAB_CURL_HARD_MIN_RAW_RAD,
        .hard_max_pos_rad = CONTROL_REHAB_CURL_HARD_MAX_RAW_RAD,
        .top_target_pos_rad = CONTROL_REHAB_CURL_TOP_TARGET_RAW_RAD,
        .bottom_target_pos_rad = CONTROL_REHAB_CURL_BOTTOM_TARGET_RAW_RAD,
        .position_tolerance_rad = CONTROL_REHAB_CURL_POSITION_TOLERANCE_RAD,
        .max_feedback_velocity_rad_s = CONTROL_REHAB_CURL_MAX_FEEDBACK_SPEED_RAD_S,
        .dwell_ms = CONTROL_REHAB_CURL_DWELL_MS,
        .segment_timeout_ms = CONTROL_REHAB_CURL_SEGMENT_TIMEOUT_MS,
        .command_refresh_ms = CONTROL_REHAB_CURL_COMMAND_REFRESH_MS,
        .arrival_samples = CONTROL_REHAB_CURL_ARRIVAL_SAMPLES,
    };
    return config;
}

static float rehab_service_curl_raw_to_joint_position(float raw_pos_rad)
{
    return ((raw_pos_rad - CONTROL_MOTOR_JOINT5_ZERO_OFFSET_RAD) /
            CONTROL_MOTOR_JOINT5_GEAR_RATIO) *
           CONTROL_MOTOR_JOINT5_DIRECTION;
}

static rt_uint16_t rehab_ticks_to_ms_u16(rt_tick_t ticks)
{
    rt_uint32_t ms;

    ms = (rt_uint32_t)(((rt_uint64_t)ticks * 1000ULL) / RT_TICK_PER_SECOND);
    if (ms > 0xFFFFU)
    {
        return 0xFFFFU;
    }
    return (rt_uint16_t)ms;
}

static rt_bool_t rehab_feedback_is_fresh(const control_motor_feedback_t *fb, rt_tick_t now)
{
    if ((fb == RT_NULL) || (fb->timestamp == 0U))
    {
        return RT_FALSE;
    }

    return ((now - fb->timestamp) <= rt_tick_from_millisecond(CONTROL_REHAB_FEEDBACK_FRESH_MS))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_err_t rehab_feedback_active_check(const control_motor_feedback_t *fb, rt_tick_t now)
{
    if (!rehab_feedback_is_fresh(fb, now))
    {
        return -RT_ETIMEOUT;
    }
    if (fb->fault_summary != 0U)
    {
        return -RT_ERROR;
    }
    return RT_EOK;
}

static rt_err_t rehab_service_prepare_feedback(rt_uint8_t m33_joint_id)
{
    control_motor_feedback_t fb;
    rt_tick_t start;
    rt_tick_t timeout;
    rt_err_t ret;

    ret = control_motor_set_active_report(m33_joint_id, RT_TRUE);
    if (ret != RT_EOK)
    {
        return ret;
    }

    start = rt_tick_get();
    timeout = rt_tick_from_millisecond(CONTROL_REHAB_FEEDBACK_PREPARE_TIMEOUT_MS);
    do
    {
        if (control_get_motor_feedback(m33_joint_id, &fb) == RT_EOK)
        {
            ret = rehab_feedback_active_check(&fb, rt_tick_get());
            if (ret == RT_EOK)
            {
                return RT_EOK;
            }
            if (ret == -RT_ERROR)
            {
                return ret;
            }
        }
        rt_thread_mdelay(10U);
    } while ((rt_tick_get() - start) < timeout);

    return -RT_ETIMEOUT;
}

static float rehab_service_positive_or_default(float value, float fallback)
{
    return (value > 0.0f) ? value : fallback;
}

static float rehab_service_nonnegative_or_default(float value, float fallback)
{
    return (value >= 0.0f) ? value : fallback;
}

static float rehab_service_direction_or_default(float value, float fallback)
{
    if (value == 0.0f)
    {
        value = fallback;
    }
    return (value < 0.0f) ? -1.0f : 1.0f;
}

static float rehab_service_clamp_current_limit(float value, float fallback)
{
    value = rehab_service_positive_or_default(value, fallback);
    if (value > CONTROL_MOTOR_CURRENT_CONTROL_MAX_A)
    {
        return CONTROL_MOTOR_CURRENT_CONTROL_MAX_A;
    }
    return value;
}

static rt_uint8_t rehab_service_supported_joint_mask(void)
{
    rt_uint8_t mask = 0U;
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        mask |= (rt_uint8_t)(1U << (joint - 1U));
    }
    return mask;
}

static rt_uint8_t rehab_service_m33_joint_to_mask(rt_uint8_t m33_joint)
{
    if ((m33_joint == 0U) || (m33_joint > CONTROL_MOTOR_JOINT_COUNT))
    {
        return 0U;
    }
    return (rt_uint8_t)(1U << (m33_joint - 1U));
}

static rt_bool_t rehab_service_joint_mask_has(rt_uint8_t joint_mask, rt_uint8_t m33_joint)
{
    return ((joint_mask & rehab_service_m33_joint_to_mask(m33_joint)) != 0U) ? RT_TRUE : RT_FALSE;
}

static rt_uint8_t rehab_service_first_joint_in_mask(rt_uint8_t joint_mask)
{
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        if (rehab_service_joint_mask_has(joint_mask, joint))
        {
            return joint;
        }
    }
    return 0U;
}

static rt_bool_t rehab_service_joint_mask_valid(rt_uint8_t joint_mask)
{
    rt_uint8_t supported_mask = rehab_service_supported_joint_mask();

    if (joint_mask == 0U)
    {
        return RT_FALSE;
    }
    return ((joint_mask & (rt_uint8_t)~supported_mask) == 0U) ? RT_TRUE : RT_FALSE;
}

static rt_err_t rehab_service_prepare_feedback_mask(rt_uint8_t joint_mask)
{
    rt_tick_t start;
    rt_tick_t timeout;
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        rt_err_t ret;

        if (!rehab_service_joint_mask_has(joint_mask, joint))
        {
            continue;
        }
        ret = control_motor_set_active_report(joint, RT_TRUE);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    start = rt_tick_get();
    timeout = rt_tick_from_millisecond(CONTROL_REHAB_FEEDBACK_PREPARE_TIMEOUT_MS);
    do
    {
        rt_bool_t all_fresh = RT_TRUE;

        for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
        {
            control_motor_feedback_t fb;
            rt_err_t feedback_ret;

            if (!rehab_service_joint_mask_has(joint_mask, joint))
            {
                continue;
            }
            feedback_ret = control_get_motor_feedback(joint, &fb);
            if (feedback_ret == RT_EOK)
            {
                feedback_ret = rehab_feedback_active_check(&fb, rt_tick_get());
            }
            if (feedback_ret == -RT_ERROR)
            {
                return feedback_ret;
            }
            if (feedback_ret != RT_EOK)
            {
                all_fresh = RT_FALSE;
                break;
            }
        }
        if (all_fresh)
        {
            return RT_EOK;
        }
        rt_thread_mdelay(10U);
    } while ((rt_tick_get() - start) < timeout);

    return -RT_ETIMEOUT;
}

static rt_err_t rehab_service_validate_assist_position_mask(rt_uint8_t joint_mask)
{
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        control_motor_feedback_t fb;
        rt_err_t ret;

        if (!rehab_service_joint_mask_has(joint_mask, joint))
        {
            continue;
        }
        ret = control_get_motor_feedback(joint, &fb);
        if (ret == RT_EOK)
        {
            ret = rehab_feedback_active_check(&fb, rt_tick_get());
        }
        if (ret != RT_EOK)
        {
            return ret;
        }
        if (!rehab_assist_position_safe(joint, &fb))
        {
            return -RT_EINVAL;
        }
    }
    return RT_EOK;
}

static void rehab_service_reset_all_strategy_states_locked(void)
{
    rt_uint8_t index;

    for (index = 0U; index < CONTROL_MOTOR_JOINT_COUNT; index++)
    {
        rehab_assist_strategy_reset(&s_rehab.assist_state[index]);
        rehab_resist_strategy_reset(&s_rehab.resist_state[index]);
    }
}

static rt_err_t rehab_service_stop_joint_mask(rt_uint8_t joint_mask, rt_bool_t clear_fault)
{
    rt_err_t first_error = RT_EOK;
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        rt_err_t ret;

        if (!rehab_service_joint_mask_has(joint_mask, joint))
        {
            continue;
        }

        ret = control_motor_stop(joint, clear_fault);
        if ((first_error == RT_EOK) && (ret != RT_EOK))
        {
            first_error = ret;
        }
    }
    return first_error;
}

static rt_err_t rehab_service_prepare_current_mask(rt_uint8_t active_joint_mask)
{
    rt_tick_t start;
    rt_tick_t timeout;
    rt_uint8_t joint;

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        rt_err_t ret;

        if (!rehab_service_joint_mask_has(active_joint_mask, joint))
        {
            continue;
        }
        ret = control_motor_current_prepare(joint);
        if (ret != RT_EOK)
        {
            (void)rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE);
            return ret;
        }
    }

    start = rt_tick_get();
    timeout = rt_tick_from_millisecond(CONTROL_REHAB_FEEDBACK_PREPARE_TIMEOUT_MS);
    do
    {
        rt_bool_t all_ready = RT_TRUE;

        for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
        {
            control_motor_feedback_t fb;
            rt_err_t ret;

            if (!rehab_service_joint_mask_has(active_joint_mask, joint))
            {
                continue;
            }
            ret = control_get_motor_feedback(joint, &fb);
            if (ret == RT_EOK)
            {
                ret = rehab_feedback_active_check(&fb, rt_tick_get());
            }
            if (ret == -RT_ERROR)
            {
                (void)rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE);
                return ret;
            }
            if ((ret != RT_EOK) || (fb.mode_state != 2U))
            {
                all_ready = RT_FALSE;
                break;
            }
        }
        if (all_ready)
        {
            return RT_EOK;
        }
        rt_thread_mdelay(5U);
    } while ((rt_tick_get() - start) < timeout);

    (void)rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE);
    return -RT_ETIMEOUT;
}

static void rehab_service_default_params(rehab_strategy_params_t *out)
{
    if (out == RT_NULL)
    {
        return;
    }

    out->follow_direction = CONTROL_REHAB_FOLLOW_DIRECTION;
    out->assist_direction = CONTROL_REHAB_ASSIST_DIRECTION;
    out->resist_direction = CONTROL_REHAB_RESIST_DIRECTION;
    out->active_min_current_a = CONTROL_REHAB_ACTIVE_MIN_CUR_A;
    out->active_max_current_a = CONTROL_REHAB_ACTIVE_LIMIT_CUR_A;
    out->active_current_gain_a_per_nm = CONTROL_REHAB_ACTIVE_GAIN_A_PER_NM;
    out->assist_max_current_a = CONTROL_REHAB_ASSIST_LIMIT_CUR_A;
    out->assist_current_gain_a_per_nm = CONTROL_REHAB_ASSIST_GAIN_A_PER_NM;
    out->assist_velocity_fallback_enabled =
        (CONTROL_REHAB_ASSIST_VELOCITY_FALLBACK_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->assist_velocity_enter_rad_s = CONTROL_REHAB_ASSIST_VEL_ENTER_RAD_S;
    out->assist_velocity_exit_rad_s = CONTROL_REHAB_ASSIST_VEL_EXIT_RAD_S;
    out->assist_min_current_a = CONTROL_REHAB_ASSIST_MIN_CUR_A;
    out->assist_velocity_gain_a_per_rad_s = CONTROL_REHAB_ASSIST_VEL_GAIN_A_PER_RAD_S;
    out->assist_slew_current_a_per_step = CONTROL_REHAB_ASSIST_SLEW_A_PER_STEP;
    out->adaptive_assist_enabled =
        (CONTROL_REHAB_ASSIST_ADAPTIVE_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->adaptive_assist_base_gain_a_per_nm =
        CONTROL_REHAB_ASSIST_ADAPTIVE_BASE_GAIN_A_PER_NM;
    out->adaptive_assist_load_gain_a_per_nm2 =
        CONTROL_REHAB_ASSIST_ADAPTIVE_LOAD_GAIN_A_PER_NM2;
    out->adaptive_assist_max_gain_a_per_nm =
        CONTROL_REHAB_ASSIST_ADAPTIVE_MAX_GAIN_A_PER_NM;
    out->adaptive_assist_gain_step_a_per_nm =
        CONTROL_REHAB_ASSIST_ADAPTIVE_GAIN_STEP_A_PER_NM;
    out->assist_adaptive_pid_enabled =
        (CONTROL_REHAB_ASSIST_PID_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->resist_adaptive_pid_enabled =
        (CONTROL_REHAB_RESIST_PID_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->assist_adrc_enabled =
        (CONTROL_REHAB_ASSIST_ADRC_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->resist_adrc_enabled =
        (CONTROL_REHAB_RESIST_ADRC_ENABLE != 0U) ? RT_TRUE : RT_FALSE;
    out->adaptive_pid_load_low_nm = CONTROL_REHAB_PID_LOAD_LOW_NM;
    out->adaptive_pid_load_high_nm = CONTROL_REHAB_PID_LOAD_HIGH_NM;
    out->adaptive_pid_speed_low_rad_s = CONTROL_REHAB_PID_SPEED_LOW_RAD_S;
    out->adaptive_pid_speed_high_rad_s = CONTROL_REHAB_PID_SPEED_HIGH_RAD_S;
    out->assist_pid.target = CONTROL_REHAB_ASSIST_PID_TARGET_NM;
    out->assist_pid.kp_base = CONTROL_REHAB_ASSIST_PID_KP_BASE;
    out->assist_pid.kp_load = CONTROL_REHAB_ASSIST_PID_KP_LOAD;
    out->assist_pid.kp_speed = CONTROL_REHAB_ASSIST_PID_KP_SPEED;
    out->assist_pid.ki_base = CONTROL_REHAB_ASSIST_PID_KI_BASE;
    out->assist_pid.ki_load = CONTROL_REHAB_ASSIST_PID_KI_LOAD;
    out->assist_pid.ki_speed_reduce = CONTROL_REHAB_ASSIST_PID_KI_SPEED_REDUCE;
    out->assist_pid.kd_base = CONTROL_REHAB_ASSIST_PID_KD_BASE;
    out->assist_pid.kd_speed = CONTROL_REHAB_ASSIST_PID_KD_SPEED;
    out->assist_pid.integral_limit = CONTROL_REHAB_ASSIST_PID_INTEGRAL_LIMIT;
    out->assist_pid.trim_limit = CONTROL_REHAB_ASSIST_PID_TRIM_LIMIT_A;
    out->resist_pid.target = CONTROL_REHAB_RESIST_PID_TARGET_RAD_S;
    out->resist_pid.kp_base = CONTROL_REHAB_RESIST_PID_KP_BASE;
    out->resist_pid.kp_load = CONTROL_REHAB_RESIST_PID_KP_LOAD;
    out->resist_pid.kp_speed = CONTROL_REHAB_RESIST_PID_KP_SPEED;
    out->resist_pid.ki_base = CONTROL_REHAB_RESIST_PID_KI_BASE;
    out->resist_pid.ki_load = CONTROL_REHAB_RESIST_PID_KI_LOAD;
    out->resist_pid.ki_speed_reduce = CONTROL_REHAB_RESIST_PID_KI_SPEED_REDUCE;
    out->resist_pid.kd_base = CONTROL_REHAB_RESIST_PID_KD_BASE;
    out->resist_pid.kd_speed = CONTROL_REHAB_RESIST_PID_KD_SPEED;
    out->resist_pid.integral_limit = CONTROL_REHAB_RESIST_PID_INTEGRAL_LIMIT;
    out->resist_pid.trim_limit = CONTROL_REHAB_RESIST_PID_TRIM_LIMIT_A;
    out->assist_adrc.target = CONTROL_REHAB_ASSIST_ADRC_TARGET_NM;
    out->assist_adrc.b0 = CONTROL_REHAB_ASSIST_ADRC_B0;
    out->assist_adrc.beta1 = CONTROL_REHAB_ADRC_BETA1;
    out->assist_adrc.beta2 = CONTROL_REHAB_ADRC_BETA2;
    out->assist_adrc.beta3 = CONTROL_REHAB_ADRC_BETA3;
    out->assist_adrc.kp = CONTROL_REHAB_ASSIST_ADRC_KP;
    out->assist_adrc.kd = CONTROL_REHAB_ASSIST_ADRC_KD;
    out->assist_adrc.disturbance_gain = CONTROL_REHAB_ASSIST_ADRC_DISTURBANCE_GAIN;
    out->assist_adrc.trim_limit = CONTROL_REHAB_ASSIST_ADRC_TRIM_LIMIT_A;
    out->resist_adrc.target = CONTROL_REHAB_RESIST_ADRC_TARGET_RAD_S;
    out->resist_adrc.b0 = CONTROL_REHAB_RESIST_ADRC_B0;
    out->resist_adrc.beta1 = CONTROL_REHAB_ADRC_BETA1;
    out->resist_adrc.beta2 = CONTROL_REHAB_ADRC_BETA2;
    out->resist_adrc.beta3 = CONTROL_REHAB_ADRC_BETA3;
    out->resist_adrc.kp = CONTROL_REHAB_RESIST_ADRC_KP;
    out->resist_adrc.kd = CONTROL_REHAB_RESIST_ADRC_KD;
    out->resist_adrc.disturbance_gain = CONTROL_REHAB_RESIST_ADRC_DISTURBANCE_GAIN;
    out->resist_adrc.trim_limit = CONTROL_REHAB_RESIST_ADRC_TRIM_LIMIT_A;
    out->resist_max_current_a = CONTROL_REHAB_RESIST_LIMIT_CUR_A;
    out->resist_current_gain_a_per_rad_s = CONTROL_REHAB_RESIST_CURRENT_GAIN_A_PER_RAD_S;
}

static void rehab_service_sanitize_pid_profile(rehab_adaptive_pid_profile_t *profile,
                                               const rehab_adaptive_pid_profile_t *defaults)
{
    if ((profile == RT_NULL) || (defaults == RT_NULL))
    {
        return;
    }

    profile->target = rehab_service_nonnegative_or_default(profile->target,
                                                           defaults->target);
    profile->kp_base = rehab_service_nonnegative_or_default(profile->kp_base,
                                                            defaults->kp_base);
    profile->kp_load = rehab_service_nonnegative_or_default(profile->kp_load,
                                                            defaults->kp_load);
    profile->kp_speed = rehab_service_nonnegative_or_default(profile->kp_speed,
                                                             defaults->kp_speed);
    profile->ki_base = rehab_service_nonnegative_or_default(profile->ki_base,
                                                            defaults->ki_base);
    profile->ki_load = rehab_service_nonnegative_or_default(profile->ki_load,
                                                            defaults->ki_load);
    profile->ki_speed_reduce =
        rehab_service_nonnegative_or_default(profile->ki_speed_reduce,
                                             defaults->ki_speed_reduce);
    profile->kd_base = rehab_service_nonnegative_or_default(profile->kd_base,
                                                            defaults->kd_base);
    profile->kd_speed = rehab_service_nonnegative_or_default(profile->kd_speed,
                                                             defaults->kd_speed);
    profile->integral_limit =
        rehab_service_positive_or_default(profile->integral_limit,
                                          defaults->integral_limit);
    profile->trim_limit = rehab_service_clamp_current_limit(profile->trim_limit,
                                                            defaults->trim_limit);
}

static void rehab_service_sanitize_adrc_profile(rehab_adrc_profile_t *profile,
                                                const rehab_adrc_profile_t *defaults)
{
    if ((profile == RT_NULL) || (defaults == RT_NULL))
    {
        return;
    }

    profile->target = rehab_service_nonnegative_or_default(profile->target,
                                                           defaults->target);
    profile->b0 = rehab_service_positive_or_default(profile->b0,
                                                    defaults->b0);
    profile->beta1 = rehab_service_positive_or_default(profile->beta1,
                                                       defaults->beta1);
    profile->beta2 = rehab_service_positive_or_default(profile->beta2,
                                                       defaults->beta2);
    profile->beta3 = rehab_service_positive_or_default(profile->beta3,
                                                       defaults->beta3);
    profile->kp = rehab_service_nonnegative_or_default(profile->kp,
                                                       defaults->kp);
    profile->kd = rehab_service_nonnegative_or_default(profile->kd,
                                                       defaults->kd);
    profile->disturbance_gain =
        rehab_service_nonnegative_or_default(profile->disturbance_gain,
                                             defaults->disturbance_gain);
    profile->trim_limit = rehab_service_clamp_current_limit(profile->trim_limit,
                                                            defaults->trim_limit);
}

static void rehab_service_sanitize_params(rehab_strategy_params_t *params)
{
    rehab_strategy_params_t defaults;

    if (params == RT_NULL)
    {
        return;
    }

    rehab_service_default_params(&defaults);
    params->follow_direction = rehab_service_direction_or_default(params->follow_direction,
                                                                  defaults.follow_direction);
    params->assist_direction = rehab_service_direction_or_default(params->assist_direction,
                                                                  defaults.assist_direction);
    params->resist_direction = rehab_service_direction_or_default(params->resist_direction,
                                                                  defaults.resist_direction);
    params->active_max_current_a = rehab_service_clamp_current_limit(params->active_max_current_a,
                                                                     defaults.active_max_current_a);
    params->active_min_current_a = rehab_service_clamp_current_limit(params->active_min_current_a,
                                                                     defaults.active_min_current_a);
    if (params->active_min_current_a > params->active_max_current_a)
    {
        params->active_min_current_a = params->active_max_current_a;
    }
    params->active_current_gain_a_per_nm =
        rehab_service_positive_or_default(params->active_current_gain_a_per_nm,
                                          defaults.active_current_gain_a_per_nm);
    params->assist_max_current_a = rehab_service_clamp_current_limit(params->assist_max_current_a,
                                                                     defaults.assist_max_current_a);
    params->assist_current_gain_a_per_nm =
        rehab_service_positive_or_default(params->assist_current_gain_a_per_nm,
                                          defaults.assist_current_gain_a_per_nm);
    params->assist_velocity_fallback_enabled =
        params->assist_velocity_fallback_enabled ? RT_TRUE : RT_FALSE;
    params->assist_velocity_enter_rad_s =
        rehab_service_nonnegative_or_default(params->assist_velocity_enter_rad_s,
                                             defaults.assist_velocity_enter_rad_s);
    params->assist_velocity_exit_rad_s =
        rehab_service_nonnegative_or_default(params->assist_velocity_exit_rad_s,
                                             defaults.assist_velocity_exit_rad_s);
    if (params->assist_velocity_exit_rad_s > params->assist_velocity_enter_rad_s)
    {
        params->assist_velocity_exit_rad_s = params->assist_velocity_enter_rad_s;
    }
    params->assist_min_current_a = rehab_service_clamp_current_limit(params->assist_min_current_a,
                                                                    defaults.assist_min_current_a);
    if (params->assist_min_current_a > params->assist_max_current_a)
    {
        params->assist_min_current_a = params->assist_max_current_a;
    }
    params->assist_velocity_gain_a_per_rad_s =
        rehab_service_nonnegative_or_default(params->assist_velocity_gain_a_per_rad_s,
                                             defaults.assist_velocity_gain_a_per_rad_s);
    params->assist_slew_current_a_per_step =
        rehab_service_nonnegative_or_default(params->assist_slew_current_a_per_step,
                                             defaults.assist_slew_current_a_per_step);
    params->adaptive_assist_enabled =
        params->adaptive_assist_enabled ? RT_TRUE : RT_FALSE;
    params->adaptive_assist_base_gain_a_per_nm =
        rehab_service_positive_or_default(params->adaptive_assist_base_gain_a_per_nm,
                                          defaults.adaptive_assist_base_gain_a_per_nm);
    params->adaptive_assist_load_gain_a_per_nm2 =
        rehab_service_nonnegative_or_default(params->adaptive_assist_load_gain_a_per_nm2,
                                             defaults.adaptive_assist_load_gain_a_per_nm2);
    params->adaptive_assist_max_gain_a_per_nm =
        rehab_service_positive_or_default(params->adaptive_assist_max_gain_a_per_nm,
                                          defaults.adaptive_assist_max_gain_a_per_nm);
    if (params->adaptive_assist_max_gain_a_per_nm < params->adaptive_assist_base_gain_a_per_nm)
    {
        params->adaptive_assist_max_gain_a_per_nm = params->adaptive_assist_base_gain_a_per_nm;
    }
    params->adaptive_assist_gain_step_a_per_nm =
        rehab_service_positive_or_default(params->adaptive_assist_gain_step_a_per_nm,
                                          defaults.adaptive_assist_gain_step_a_per_nm);
    params->assist_adaptive_pid_enabled =
        params->assist_adaptive_pid_enabled ? RT_TRUE : RT_FALSE;
    params->resist_adaptive_pid_enabled =
        params->resist_adaptive_pid_enabled ? RT_TRUE : RT_FALSE;
    params->assist_adrc_enabled =
        params->assist_adrc_enabled ? RT_TRUE : RT_FALSE;
    params->resist_adrc_enabled =
        params->resist_adrc_enabled ? RT_TRUE : RT_FALSE;
    params->adaptive_pid_load_low_nm =
        rehab_service_nonnegative_or_default(params->adaptive_pid_load_low_nm,
                                             defaults.adaptive_pid_load_low_nm);
    params->adaptive_pid_load_high_nm =
        rehab_service_positive_or_default(params->adaptive_pid_load_high_nm,
                                          defaults.adaptive_pid_load_high_nm);
    if (params->adaptive_pid_load_high_nm <= params->adaptive_pid_load_low_nm)
    {
        params->adaptive_pid_load_low_nm = defaults.adaptive_pid_load_low_nm;
        params->adaptive_pid_load_high_nm = defaults.adaptive_pid_load_high_nm;
    }
    params->adaptive_pid_speed_low_rad_s =
        rehab_service_nonnegative_or_default(params->adaptive_pid_speed_low_rad_s,
                                             defaults.adaptive_pid_speed_low_rad_s);
    params->adaptive_pid_speed_high_rad_s =
        rehab_service_positive_or_default(params->adaptive_pid_speed_high_rad_s,
                                          defaults.adaptive_pid_speed_high_rad_s);
    if (params->adaptive_pid_speed_high_rad_s <= params->adaptive_pid_speed_low_rad_s)
    {
        params->adaptive_pid_speed_low_rad_s = defaults.adaptive_pid_speed_low_rad_s;
        params->adaptive_pid_speed_high_rad_s = defaults.adaptive_pid_speed_high_rad_s;
    }
    rehab_service_sanitize_pid_profile(&params->assist_pid, &defaults.assist_pid);
    rehab_service_sanitize_pid_profile(&params->resist_pid, &defaults.resist_pid);
    rehab_service_sanitize_adrc_profile(&params->assist_adrc, &defaults.assist_adrc);
    rehab_service_sanitize_adrc_profile(&params->resist_adrc, &defaults.resist_adrc);
    params->resist_max_current_a = rehab_service_clamp_current_limit(params->resist_max_current_a,
                                                                     defaults.resist_max_current_a);
    params->resist_current_gain_a_per_rad_s =
        rehab_service_positive_or_default(params->resist_current_gain_a_per_rad_s,
                                          defaults.resist_current_gain_a_per_rad_s);
}

static rt_uint8_t rehab_status_flags_from_status(const rehab_service_status_t *status)
{
    rt_uint8_t flags = 0U;

    if (status == RT_NULL)
    {
        return 0U;
    }
    if (status->feedback_fresh)
    {
        flags |= REHAB_SERVICE_STATUS_FLAG_FRESH;
    }
    if (status->assist_engaged)
    {
        flags |= REHAB_SERVICE_STATUS_FLAG_ASSIST_ENGAGED;
    }
    if (status->mode == REHAB_DEMO_MODE_MEMORY_RECORD)
    {
        flags |= REHAB_SERVICE_STATUS_FLAG_RECORDING;
    }
    if (status->mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
    {
        flags |= REHAB_SERVICE_STATUS_FLAG_PLAYING;
    }
    if (status->detail != CONTROL_STATUS_DETAIL_NONE)
    {
        flags |= REHAB_SERVICE_STATUS_FLAG_FAULT;
    }

    return flags;
}

static rt_err_t rehab_service_resolve_joint(rehab_joint_id_t joint,
                                            rehab_joint_map_entry_t *entry)
{
    return rehab_joint_map_get(joint, entry) ? RT_EOK : -RT_EINVAL;
}

static void rehab_service_update_flags_locked(void)
{
    s_rehab.status.flags = rehab_status_flags_from_status(&s_rehab.status);
}

static void rehab_service_clear_observation_locked(void)
{
    s_rehab.status.feedback_torque_nm = 0.0f;
    s_rehab.status.feedback_vel_rad_s = 0.0f;
    s_rehab.status.output_current_a = 0.0f;
    s_rehab.status.output_limit_current_a = 0.0f;
    s_rehab.status.effective_gain = 0.0f;
    s_rehab.status.pid_kp = 0.0f;
    s_rehab.status.pid_ki = 0.0f;
    s_rehab.status.pid_kd = 0.0f;
    s_rehab.status.pid_load_level = 0.0f;
    s_rehab.status.pid_speed_level = 0.0f;
    s_rehab.status.pid_error = 0.0f;
    s_rehab.status.pid_trim_current_a = 0.0f;
    s_rehab.status.adrc_error = 0.0f;
    s_rehab.status.adrc_z1 = 0.0f;
    s_rehab.status.adrc_z2 = 0.0f;
    s_rehab.status.adrc_z3 = 0.0f;
    s_rehab.status.adrc_trim_current_a = 0.0f;
    s_rehab.status.output_saturated = RT_FALSE;
}

static void rehab_service_update_observation_locked(const control_motor_feedback_t *fb,
                                                    const rehab_strategy_output_t *out)
{
    if (fb != RT_NULL)
    {
        s_rehab.status.feedback_torque_nm = fb->torque_nm;
        s_rehab.status.feedback_vel_rad_s = fb->vel_rad_s;
    }
    else
    {
        s_rehab.status.feedback_torque_nm = 0.0f;
        s_rehab.status.feedback_vel_rad_s = 0.0f;
    }

    if (out != RT_NULL)
    {
        s_rehab.status.output_current_a =
            (out->type == REHAB_STRATEGY_OUTPUT_CURRENT) ? out->current_a : 0.0f;
        s_rehab.status.output_limit_current_a = out->limit_cur_a;
        s_rehab.status.effective_gain = out->effective_gain;
        s_rehab.status.pid_kp = out->pid_kp;
        s_rehab.status.pid_ki = out->pid_ki;
        s_rehab.status.pid_kd = out->pid_kd;
        s_rehab.status.pid_load_level = out->pid_load_level;
        s_rehab.status.pid_speed_level = out->pid_speed_level;
        s_rehab.status.pid_error = out->pid_error;
        s_rehab.status.pid_trim_current_a = out->pid_trim_current_a;
        s_rehab.status.adrc_error = out->adrc_error;
        s_rehab.status.adrc_z1 = out->adrc_z1;
        s_rehab.status.adrc_z2 = out->adrc_z2;
        s_rehab.status.adrc_z3 = out->adrc_z3;
        s_rehab.status.adrc_trim_current_a = out->adrc_trim_current_a;
        s_rehab.status.output_saturated = out->current_saturated;
    }
    else
    {
        s_rehab.status.output_current_a = 0.0f;
        s_rehab.status.output_limit_current_a = 0.0f;
        s_rehab.status.effective_gain = 0.0f;
        s_rehab.status.pid_kp = 0.0f;
        s_rehab.status.pid_ki = 0.0f;
        s_rehab.status.pid_kd = 0.0f;
        s_rehab.status.pid_load_level = 0.0f;
        s_rehab.status.pid_speed_level = 0.0f;
        s_rehab.status.pid_error = 0.0f;
        s_rehab.status.pid_trim_current_a = 0.0f;
        s_rehab.status.adrc_error = 0.0f;
        s_rehab.status.adrc_z1 = 0.0f;
        s_rehab.status.adrc_z2 = 0.0f;
        s_rehab.status.adrc_z3 = 0.0f;
        s_rehab.status.adrc_trim_current_a = 0.0f;
        s_rehab.status.output_saturated = RT_FALSE;
    }
}

static void rehab_service_set_result_locked(rt_uint8_t detail, rt_err_t result)
{
    s_rehab.status.detail = detail;
    s_rehab.status.last_result = result;
    s_rehab.status.timestamp = rt_tick_get();
    rehab_service_update_flags_locked();
}

static void rehab_service_apply_status_locked(rehab_demo_mode_t mode,
                                              rehab_joint_id_t joint,
                                              rehab_cmd_source_t source,
                                              rt_uint8_t m33_joint,
                                              rt_uint8_t active_joint_mask,
                                              rt_uint8_t detail,
                                              rt_err_t result)
{
    if (mode == REHAB_DEMO_MODE_PASSIVE)
    {
        active_joint_mask = 0U;
    }
    else if (!rehab_service_joint_mask_valid(active_joint_mask))
    {
        active_joint_mask = rehab_service_m33_joint_to_mask(m33_joint);
    }

    s_rehab.status.mode_generation++;
    s_rehab.status.mode = mode;
    s_rehab.status.source = source;
    s_rehab.status.joint = joint;
    s_rehab.status.m33_joint_id = m33_joint;
    s_rehab.status.active_joint_mask = active_joint_mask;
    s_rehab.status.detail = detail;
    s_rehab.status.last_fault_joint = 0U;
    s_rehab.status.last_fault_stage = 0U;
    s_rehab.status.last_fault_feedback_age_ms = 0U;
    s_rehab.status.last_fault_velocity_rad_s = 0.0f;
    s_rehab.status.last_result = result;
    s_rehab.stop_pending = RT_FALSE;
    s_rehab.status.feedback_fresh = RT_FALSE;
    s_rehab.status.assist_engaged = RT_FALSE;
    s_rehab.status.assist_engaged_mask = 0U;
    s_rehab.status.curl_phase = REHAB_CURL_PHASE_IDLE;
    s_rehab.status.curl_repetitions = 0U;
    s_rehab.status.fixed_action_id = (rt_uint8_t)REHAB_FIXED_ACTION_NONE;
    s_rehab.status.fixed_action_state = (rt_uint8_t)REHAB_FIXED_ACTION_STATE_IDLE;
    s_rehab.status.fixed_action_repetitions = 0U;
    s_rehab.status.fixed_action_fault = RT_EOK;
    rehab_service_clear_observation_locked();
    s_rehab.status.timestamp = rt_tick_get();
    rehab_service_update_flags_locked();
}

static void rehab_service_note_fault_mask(rt_uint8_t joint_mask,
                                          rt_uint8_t m33_joint,
                                          rehab_demo_mode_t expected_mode,
                                          rt_uint32_t expected_generation,
                                          rt_uint8_t detail,
                                          rt_err_t result,
                                          rt_uint8_t fault_stage,
                                          rt_uint16_t fault_age_ms,
                                          float fault_velocity_rad_s)
{
    rt_bool_t should_stop;

    if (!rehab_service_joint_mask_valid(joint_mask))
    {
        joint_mask = rehab_service_m33_joint_to_mask(m33_joint);
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode != expected_mode) ||
        (s_rehab.status.mode_generation != expected_generation) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return;
    }
    should_stop = !s_rehab.stopped_for_fault;
    s_rehab.status.feedback_fresh = RT_FALSE;
    s_rehab.status.assist_engaged = RT_FALSE;
    s_rehab.status.assist_engaged_mask = 0U;
    s_rehab.status.last_fault_joint = m33_joint;
    s_rehab.status.last_fault_stage = fault_stage;
    s_rehab.status.last_fault_feedback_age_ms = fault_age_ms;
    s_rehab.status.last_fault_velocity_rad_s = fault_velocity_rad_s;
    rehab_service_clear_observation_locked();
    s_rehab.stopped_for_fault = RT_TRUE;
    rehab_service_set_result_locked(detail, result);
    rt_mutex_release(&s_rehab.lock);

    if (should_stop)
    {
        (void)rehab_service_stop_joint_mask(joint_mask, RT_FALSE);
    }
    rt_mutex_release(&s_rehab.actuation_lock);
}

static void rehab_service_note_fault(rt_uint8_t m33_joint,
                                     rehab_demo_mode_t expected_mode,
                                     rt_uint32_t expected_generation,
                                     rt_uint8_t detail,
                                     rt_err_t result)
{
    rehab_service_note_fault_mask(rehab_service_m33_joint_to_mask(m33_joint),
                                  m33_joint,
                                  expected_mode,
                                  expected_generation,
                                  detail,
                                  result,
                                  3U,
                                  0xFFFFU,
                                  0.0f);
}

static void rehab_service_complete_to_passive(rt_uint8_t m33_joint, rt_err_t result)
{
    (void)control_motor_stop(m33_joint, RT_FALSE);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.mode = REHAB_DEMO_MODE_PASSIVE;
    s_rehab.status.assist_engaged = RT_FALSE;
    s_rehab.status.active_joint_mask = 0U;
    s_rehab.status.assist_engaged_mask = 0U;
    s_rehab.status.feedback_fresh = RT_TRUE;
    rehab_service_clear_observation_locked();
    s_rehab.stopped_for_fault = RT_FALSE;
    rehab_service_reset_all_strategy_states_locked();
    rehab_service_set_result_locked(CONTROL_STATUS_DETAIL_NONE, result);
    rt_mutex_release(&s_rehab.lock);
}

static void rehab_service_record_sample(const control_motor_feedback_t *fb, rt_tick_t now)
{
    rehab_trajectory_sample_t sample;
    rt_tick_t last_tick;
    rt_tick_t dt_tick;
    rt_err_t ret;

    if (fb == RT_NULL)
    {
        return;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    last_tick = s_rehab.last_record_tick;
    s_rehab.last_record_tick = now;
    rt_mutex_release(&s_rehab.lock);

    dt_tick = (last_tick == 0U) ? rt_tick_from_millisecond(CONTROL_REHAB_SERVICE_PERIOD_MS) : (now - last_tick);
    sample.dt_ms = rehab_ticks_to_ms_u16(dt_tick);
    sample.pos_rad = fb->pos_rad;
    sample.vel_rad_s = fb->vel_rad_s;
    sample.torque_nm = fb->torque_nm;

    ret = rehab_trajectory_bank_append(0U, &sample);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.last_result = ret;
    s_rehab.status.record_count = rehab_trajectory_bank_count(0U);
    if ((ret != RT_EOK) && (ret != -RT_EFULL))
    {
        s_rehab.status.detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
}

static void rehab_service_playback_step(rt_uint8_t m33_joint)
{
    rehab_trajectory_sample_t sample;
    rt_uint16_t index;
    rt_err_t ret;

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    index = s_rehab.status.playback_index;
    rt_mutex_release(&s_rehab.lock);

    ret = rehab_trajectory_bank_get(0U, index, &sample);
    if (ret != RT_EOK)
    {
        rehab_service_complete_to_passive(m33_joint, ret);
        return;
    }

    ret = control_motor_position_control(m33_joint,
                                         sample.pos_rad,
                                         CONTROL_REHAB_RESIST_MAX_VEL_RAD_S,
                                         RT_TRUE);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.last_result = ret;
    if (ret == RT_EOK)
    {
        s_rehab.status.playback_index = (rt_uint16_t)(index + 1U);
    }
    else
    {
        s_rehab.status.mode = REHAB_DEMO_MODE_PASSIVE;
        s_rehab.status.detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);

    if (ret != RT_EOK)
    {
        (void)control_motor_stop(m33_joint, RT_FALSE);
    }
}

static rt_err_t rehab_service_curl_step(rt_uint8_t m33_joint,
                                        rt_uint32_t expected_generation,
                                        const control_motor_feedback_t *fb)
{
    rehab_curl_output_t output;
    rt_tick_t check_now = rt_tick_get();
    rt_err_t ret = RT_EOK;

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode != REHAB_DEMO_MODE_CURL) ||
        (s_rehab.status.mode_generation != expected_generation) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        return -RT_EBUSY;
    }
    rehab_curl_planner_step(&s_rehab.curl_planner,
                            fb->pos_rad,
                            fb->vel_rad_s,
                            rehab_feedback_is_fresh(fb, check_now),
                            (fb->fault_summary != 0U) ? RT_TRUE : RT_FALSE,
                            rehab_ticks_to_ms_u32(check_now),
                            &output);
    s_rehab.status.curl_phase = (rt_uint8_t)output.phase;
    s_rehab.status.curl_repetitions = output.completed_repetitions;
    rt_mutex_release(&s_rehab.lock);

    if (output.action == REHAB_CURL_ACTION_STOP_FAULT)
    {
        rehab_service_note_fault(m33_joint,
                                 REHAB_DEMO_MODE_CURL,
                                 expected_generation,
                                 CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                 -RT_ERROR);
        return -RT_ERROR;
    }
    if (output.action != REHAB_CURL_ACTION_COMMAND_POSITION)
    {
        return RT_EOK;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode != REHAB_DEMO_MODE_CURL) ||
        (s_rehab.status.mode_generation != expected_generation) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);
    ret = control_motor_position_control_with_current_limit(
        m33_joint,
        rehab_service_curl_raw_to_joint_position(output.target_pos_rad),
        CONTROL_REHAB_CURL_COMMAND_SPEED_RAD_S,
        CONTROL_REHAB_CURL_LIMIT_CURRENT_A,
        RT_TRUE);
    rt_mutex_release(&s_rehab.actuation_lock);

    if (ret != RT_EOK)
    {
        rehab_service_note_fault(m33_joint,
                                 REHAB_DEMO_MODE_CURL,
                                 expected_generation,
                                 CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                 ret);
    }
    return ret;
}

static rt_err_t rehab_service_fixed_action_feedback(rt_uint8_t joint_mask,
                                                    rehab_fixed_action_feedback_t *feedback,
                                                    control_motor_feedback_t *last_fb)
{
    rt_uint8_t joint;

    if (feedback == RT_NULL)
    {
        return -RT_EINVAL;
    }
    rt_memset(feedback, 0, sizeof(*feedback));
    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        control_motor_feedback_t fb;
        rt_err_t ret;

        if ((joint >= REHAB_FIXED_ACTION_JOINT_SLOTS) ||
            !rehab_service_joint_mask_has(joint_mask, joint))
        {
            continue;
        }

        ret = control_get_motor_feedback(joint, &fb);
        if (ret == RT_EOK)
        {
            ret = rehab_feedback_active_check(&fb, rt_tick_get());
        }
        if (ret != RT_EOK)
        {
            return ret;
        }

        feedback->fresh_mask |= rehab_service_m33_joint_to_mask(joint);
        if (fb.fault_summary != 0U)
        {
            feedback->fault_mask |= rehab_service_m33_joint_to_mask(joint);
        }
        feedback->position_rad[joint] = fb.pos_rad;
        feedback->velocity_rad_s[joint] = fb.vel_rad_s;
        if (last_fb != RT_NULL)
        {
            *last_fb = fb;
        }
    }
    return RT_EOK;
}

static rt_err_t rehab_service_apply_fixed_action_output(
    rt_uint8_t joint_mask,
    rt_uint32_t expected_generation,
    const rehab_fixed_action_output_t *output)
{
    rt_err_t ret = RT_EOK;
    rt_uint8_t joint;

    if (output == RT_NULL)
    {
        return -RT_EINVAL;
    }

    if (output->action == REHAB_FIXED_ACTION_OUTPUT_NONE)
    {
        return RT_EOK;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode != REHAB_DEMO_MODE_FIXED_ACTION) ||
        (s_rehab.status.mode_generation != expected_generation) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);

    if (output->action == REHAB_FIXED_ACTION_OUTPUT_STOP)
    {
        ret = control_motor_csp_group_stop(joint_mask);
    }
    else
    {
        for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
        {
            if ((joint >= REHAB_FIXED_ACTION_JOINT_SLOTS) ||
                !rehab_service_joint_mask_has(joint_mask, joint))
            {
                continue;
            }

            if (output->action == REHAB_FIXED_ACTION_OUTPUT_PREPARE)
            {
                ret = control_motor_csp_prepare(
                    joint,
                    CONTROL_REHAB_FIXED_ACTION_COMMAND_SPEED_RAD_S,
                    CONTROL_REHAB_FIXED_ACTION_LIMIT_CURRENT_A);
            }
            else if (output->action == REHAB_FIXED_ACTION_OUTPUT_SETPOINT)
            {
                ret = control_motor_csp_setpoint(joint, output->target_rad[joint]);
            }
            if (ret != RT_EOK)
            {
                break;
            }
        }
    }

    rt_mutex_release(&s_rehab.actuation_lock);
    return ret;
}

static rt_err_t rehab_service_fixed_action_step(rt_uint8_t joint_mask,
                                                rt_uint32_t expected_generation)
{
    rehab_fixed_action_feedback_t feedback;
    rehab_fixed_action_output_t output;
    control_motor_feedback_t last_fb;
    rt_err_t ret;

    rt_memset(&last_fb, 0, sizeof(last_fb));
    ret = rehab_service_fixed_action_feedback(joint_mask, &feedback, &last_fb);
    if (ret != RT_EOK)
    {
        rehab_service_note_fault_mask(joint_mask,
                                      rehab_service_first_joint_in_mask(joint_mask),
                                      REHAB_DEMO_MODE_FIXED_ACTION,
                                      expected_generation,
                                      CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                      ret,
                                      1U,
                                      0xFFFFU,
                                      0.0f);
        return ret;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode != REHAB_DEMO_MODE_FIXED_ACTION) ||
        (s_rehab.status.mode_generation != expected_generation) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        return -RT_EBUSY;
    }
    rehab_fixed_action_step(&s_rehab.fixed_action_runner,
                            &feedback,
                            rehab_ticks_to_ms_u32(rt_tick_get()),
                            &output);
    s_rehab.status.fixed_action_state = (rt_uint8_t)output.state;
    s_rehab.status.fixed_action_repetitions = output.completed_repetitions;
    s_rehab.status.fixed_action_fault = output.result;
    s_rehab.status.feedback_fresh = RT_TRUE;
    rehab_service_update_observation_locked(&last_fb, RT_NULL);
    s_rehab.status.timestamp = rt_tick_get();
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);

    if (output.action == REHAB_FIXED_ACTION_OUTPUT_STOP)
    {
        rehab_service_note_fault_mask(joint_mask,
                                      rehab_service_first_joint_in_mask(joint_mask),
                                      REHAB_DEMO_MODE_FIXED_ACTION,
                                      expected_generation,
                                      CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                      output.result,
                                      2U,
                                      0xFFFFU,
                                      0.0f);
        return output.result;
    }

    ret = rehab_service_apply_fixed_action_output(joint_mask,
                                                  expected_generation,
                                                  &output);
    if (ret != RT_EOK)
    {
        rehab_service_note_fault_mask(joint_mask,
                                      rehab_service_first_joint_in_mask(joint_mask),
                                      REHAB_DEMO_MODE_FIXED_ACTION,
                                      expected_generation,
                                      CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                      ret,
                                      3U,
                                      0xFFFFU,
                                      0.0f);
    }
    return ret;
}

static rt_err_t rehab_service_apply_strategy_output(rt_uint8_t m33_joint,
                                                    rehab_demo_mode_t mode,
                                                    rt_uint32_t expected_generation,
                                                    const rehab_strategy_output_t *out)
{
    rt_err_t ret = RT_EOK;
    control_motor_feedback_t latest_fb;

    if (out == RT_NULL)
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if ((s_rehab.status.mode_generation != expected_generation) ||
        (s_rehab.status.mode != mode) ||
        s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);

    if (out->type == REHAB_STRATEGY_OUTPUT_CURRENT)
    {
        ret = control_get_motor_feedback(m33_joint, &latest_fb);
        if (ret == RT_EOK)
        {
            ret = rehab_feedback_active_check(&latest_fb, rt_tick_get());
        }
        if (ret != RT_EOK)
        {
            (void)control_motor_stop(m33_joint, RT_FALSE);
        }
        else
        {
            ret = control_motor_current_setpoint(m33_joint, out->current_a);
        }
    }
    else if ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
             (mode == REHAB_DEMO_MODE_ASSIST) ||
             (mode == REHAB_DEMO_MODE_RESIST))
    {
        ret = control_motor_current_setpoint(m33_joint, 0.0f);
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.last_result = ret;
    if (ret != RT_EOK)
    {
        s_rehab.status.detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);

    return ret;
}

static void rehab_service_worker(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
        rehab_demo_mode_t mode;
        rt_uint8_t m33_joint;
        rt_uint8_t active_joint_mask;
        rehab_strategy_params_t params;
        rt_bool_t stopped_for_fault;
        rt_tick_t worker_now;
        rt_tick_t now;
        rt_bool_t active_control_mode;
        rt_uint32_t mode_generation;

        worker_now = rt_tick_get();
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        rehab_worker_timing_note(&s_rehab.worker_timing,
                                 worker_now,
                                 rt_tick_from_millisecond(CONTROL_REHAB_SERVICE_PERIOD_MS),
                                 RT_TICK_PER_SECOND);
        s_rehab.status.worker_cycle_count = s_rehab.worker_timing.cycle_count;
        s_rehab.status.worker_last_tick = s_rehab.worker_timing.last_tick;
        s_rehab.status.worker_max_jitter_ms = s_rehab.worker_timing.max_jitter_ms;
        mode = s_rehab.status.mode;
        mode_generation = s_rehab.status.mode_generation;
        m33_joint = s_rehab.status.m33_joint_id;
        active_joint_mask = s_rehab.status.active_joint_mask;
        params = s_rehab.params;
        stopped_for_fault = s_rehab.stopped_for_fault;
        rt_mutex_release(&s_rehab.lock);

        if (mode == REHAB_DEMO_MODE_PASSIVE)
        {
            rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
            continue;
        }

        if (!rehab_service_joint_mask_valid(active_joint_mask))
        {
            active_joint_mask = rehab_service_m33_joint_to_mask(m33_joint);
        }

        now = rt_tick_get();
        active_control_mode =
            ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
             (mode == REHAB_DEMO_MODE_ASSIST) ||
             (mode == REHAB_DEMO_MODE_RESIST))
                ? RT_TRUE
                : RT_FALSE;

        if (active_control_mode)
        {
            control_motor_feedback_t last_fb;
            rehab_strategy_output_t last_out;
            rt_bool_t have_observation = RT_FALSE;
            rt_bool_t any_engaged = RT_FALSE;
            rt_uint8_t assist_engaged_mask = 0U;
            rt_uint8_t joint;
            rt_uint8_t fault_joint = m33_joint;
            rt_uint16_t fault_age_ms = 0xFFFFU;
            rt_err_t output_ret = RT_EOK;

            for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
            {
                control_motor_feedback_t fb;
                rt_tick_t feedback_check_tick = 0U;
                rt_err_t feedback_ret;

                if (!rehab_service_joint_mask_has(active_joint_mask, joint))
                {
                    continue;
                }
                rt_memset(&fb, 0, sizeof(fb));
                feedback_ret = control_get_motor_feedback(joint, &fb);
                if (feedback_ret == RT_EOK)
                {
                    feedback_check_tick = rt_tick_get();
                    feedback_ret = rehab_feedback_active_check(&fb, feedback_check_tick);
                }
                if ((feedback_ret == RT_EOK) &&
                    (mode == REHAB_DEMO_MODE_ASSIST) &&
                    !rehab_assist_position_safe(joint, &fb))
                {
                    fault_joint = joint;
                    rehab_service_note_fault_mask(active_joint_mask,
                                                  fault_joint,
                                                  mode,
                                                  mode_generation,
                                                  CONTROL_STATUS_DETAIL_TARGET_OUT_OF_LIMIT,
                                                  -RT_EINVAL,
                                                  5U,
                                                  0U,
                                                  fb.vel_rad_s);
                    output_ret = -RT_EINVAL;
                    break;
                }
                if ((feedback_ret == RT_EOK) &&
                    (mode == REHAB_DEMO_MODE_ASSIST) &&
                    rehab_assist_overspeed(&fb, CONTROL_REHAB_ASSIST_OVERSPEED_TRIP_RAD_S))
                {
                    fault_joint = joint;
                    rehab_service_note_fault_mask(active_joint_mask,
                                                  fault_joint,
                                                  mode,
                                                  mode_generation,
                                                  CONTROL_STATUS_DETAIL_VELOCITY_OUT_OF_LIMIT,
                                                  -RT_EINVAL,
                                                  4U,
                                                  0U,
                                                  fb.vel_rad_s);
                    output_ret = -RT_EINVAL;
                    break;
                }
                if (feedback_ret != RT_EOK)
                {
                    fault_joint = joint;
                    if (fb.timestamp != 0U)
                    {
                        fault_age_ms = rehab_ticks_to_ms_u16(feedback_check_tick - fb.timestamp);
                    }
                    rehab_service_note_fault_mask(active_joint_mask,
                                                  fault_joint,
                                                  mode,
                                                  mode_generation,
                                                  CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                                  feedback_ret,
                                                  1U,
                                                  fault_age_ms,
                                                  0.0f);
                    output_ret = feedback_ret;
                    break;
                }
            }

            if (output_ret != RT_EOK)
            {
                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }

            if (stopped_for_fault)
            {
                for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
                {
                    if (!rehab_service_joint_mask_has(active_joint_mask, joint))
                    {
                        continue;
                    }
                    if (control_get_motor_feedback(joint, &last_fb) == RT_EOK)
                    {
                        have_observation = RT_TRUE;
                        break;
                    }
                }

                rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
                if ((s_rehab.status.mode_generation == mode_generation) &&
                    (s_rehab.status.mode == mode))
                {
                    s_rehab.status.feedback_fresh = RT_TRUE;
                    s_rehab.status.active_joint_mask = active_joint_mask;
                    s_rehab.status.assist_engaged = RT_FALSE;
                    s_rehab.status.assist_engaged_mask = 0U;
                    rehab_service_update_observation_locked(have_observation ? &last_fb : RT_NULL,
                                                            RT_NULL);
                    s_rehab.status.timestamp = now;
                    rehab_service_update_flags_locked();
                }
                rt_mutex_release(&s_rehab.lock);

                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }

            for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
            {
                control_motor_feedback_t fb;
                rehab_strategy_output_t out;
                rt_uint8_t index;

                if (!rehab_service_joint_mask_has(active_joint_mask, joint))
                {
                    continue;
                }
                output_ret = control_get_motor_feedback(joint, &fb);
                if (output_ret == RT_EOK)
                {
                    output_ret = rehab_feedback_active_check(&fb, rt_tick_get());
                }
                if (output_ret != RT_EOK)
                {
                    fault_joint = joint;
                    break;
                }

                rt_memset(&out, 0, sizeof(out));
                out.type = REHAB_STRATEGY_OUTPUT_STOP;
                index = (rt_uint8_t)(joint - 1U);

                if (mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW)
                {
                    rehab_active_follow_step(&params, &fb, &out);
                }
                else if (mode == REHAB_DEMO_MODE_ASSIST)
                {
                    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
                    rehab_assist_strategy_step(&s_rehab.assist_state[index],
                                               &params,
                                               &fb,
                                               1.0f,
                                               &out);
                    if (!rehab_assist_current_direction_safe(joint, out.current_a))
                    {
                        rehab_assist_strategy_reset(&s_rehab.assist_state[index]);
                        out.current_a = 0.0f;
                        out.current_saturated = RT_FALSE;
                        out.engaged = RT_FALSE;
                    }
                    rt_mutex_release(&s_rehab.lock);
                }
                else
                {
                    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
                    rehab_resist_strategy_step(&s_rehab.resist_state[index],
                                               &params,
                                               &fb,
                                               &out);
                    rt_mutex_release(&s_rehab.lock);
                }

                output_ret = rehab_service_apply_strategy_output(joint,
                                                                 mode,
                                                                 mode_generation,
                                                                 &out);
                last_fb = fb;
                last_out = out;
                have_observation = RT_TRUE;
                if (out.engaged)
                {
                    any_engaged = RT_TRUE;
                    assist_engaged_mask |= rehab_service_m33_joint_to_mask(joint);
                }
                if (output_ret != RT_EOK)
                {
                    fault_joint = joint;
                    break;
                }
            }

            if (output_ret != RT_EOK)
            {
                if (output_ret == -RT_EBUSY)
                {
                    rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                    continue;
                }
                rehab_service_note_fault_mask(active_joint_mask,
                                              fault_joint,
                                              mode,
                                              mode_generation,
                                              CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                              output_ret,
                                              2U,
                                              0xFFFFU,
                                              0.0f);
                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }

            rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
            if ((s_rehab.status.mode_generation == mode_generation) &&
                (s_rehab.status.mode == mode))
            {
                s_rehab.status.feedback_fresh = RT_TRUE;
                s_rehab.status.active_joint_mask = active_joint_mask;
                s_rehab.status.assist_engaged = any_engaged;
                s_rehab.status.assist_engaged_mask = assist_engaged_mask;
                rehab_service_update_observation_locked(have_observation ? &last_fb : RT_NULL,
                                                        have_observation ? &last_out : RT_NULL);
                s_rehab.status.record_count = rehab_trajectory_bank_count(s_rehab.status.active_slot);
                s_rehab.status.timestamp = now;
                rehab_service_update_flags_locked();
            }
            rt_mutex_release(&s_rehab.lock);
        }
        else if (mode == REHAB_DEMO_MODE_FIXED_ACTION)
        {
            if (rehab_service_fixed_action_step(active_joint_mask,
                                                mode_generation) != RT_EOK)
            {
                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }
        }
        else
        {
            control_motor_feedback_t fb;
            rehab_strategy_output_t out;
            rt_bool_t fresh;

            fresh = (control_get_motor_feedback(m33_joint, &fb) == RT_EOK) &&
                    (rehab_feedback_active_check(&fb, rt_tick_get()) == RT_EOK);
            if (!fresh)
            {
                rehab_service_note_fault(m33_joint,
                                         mode,
                                         mode_generation,
                                         CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                                         -RT_ETIMEOUT);
                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }

            if (stopped_for_fault)
            {
                rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
                s_rehab.status.feedback_fresh = RT_TRUE;
                rehab_service_update_observation_locked(&fb, RT_NULL);
                s_rehab.status.timestamp = now;
                rehab_service_update_flags_locked();
                rt_mutex_release(&s_rehab.lock);

                rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                continue;
            }

            rt_memset(&out, 0, sizeof(out));
            out.type = REHAB_STRATEGY_OUTPUT_STOP;

            if (mode == REHAB_DEMO_MODE_MEMORY_RECORD)
            {
                rehab_service_record_sample(&fb, now);
            }
            else if (mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
            {
                rehab_service_playback_step(m33_joint);
            }
            else if (mode == REHAB_DEMO_MODE_CURL)
            {
                if (rehab_service_curl_step(m33_joint,
                                            mode_generation,
                                            &fb) != RT_EOK)
                {
                    rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
                    continue;
                }
            }

            rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
            s_rehab.status.feedback_fresh = RT_TRUE;
            s_rehab.status.assist_engaged = RT_FALSE;
            s_rehab.status.assist_engaged_mask = 0U;
            rehab_service_update_observation_locked(&fb, &out);
            s_rehab.status.record_count = rehab_trajectory_bank_count(s_rehab.status.active_slot);
            s_rehab.status.timestamp = now;
            rehab_service_update_flags_locked();
            rt_mutex_release(&s_rehab.lock);
        }

        rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
    }
}

rt_err_t rehab_service_init(void)
{
    rehab_joint_map_entry_t entry;
    rt_err_t ret;

    if (s_rehab.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&s_rehab, 0, sizeof(s_rehab));
    ret = rt_mutex_init(&s_rehab.actuation_lock, "rehabact", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        return ret;
    }
    ret = rt_mutex_init(&s_rehab.lock, "rehabs", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        rt_mutex_detach(&s_rehab.actuation_lock);
        return ret;
    }

    rehab_trajectory_bank_init();
    rehab_service_default_params(&s_rehab.params);
    rehab_service_sanitize_params(&s_rehab.params);
    (void)rehab_joint_map_get(REHAB_JOINT_ELBOW, &entry);
    s_rehab.status.mode = REHAB_DEMO_MODE_PASSIVE;
    s_rehab.status.source = REHAB_CMD_SOURCE_BENCH_MSH;
    s_rehab.status.joint = REHAB_JOINT_ELBOW;
    s_rehab.status.m33_joint_id = entry.m33_joint_id;
    s_rehab.status.active_joint_mask = 0U;
    s_rehab.status.detail = CONTROL_STATUS_DETAIL_NONE;
    s_rehab.status.assist_engaged_mask = 0U;
    s_rehab.status.active_slot = 0U;
    s_rehab.status.timestamp = rt_tick_get();
    rehab_service_update_flags_locked();

    s_rehab.thread = rt_thread_create("rehab_svc",
                                      rehab_service_worker,
                                      RT_NULL,
                                      CONTROL_REHAB_MODE_THREAD_STACK_SIZE,
                                      CONTROL_REHAB_MODE_THREAD_PRIORITY,
                                      CONTROL_REHAB_MODE_THREAD_TICK);
    if (s_rehab.thread == RT_NULL)
    {
        rt_mutex_detach(&s_rehab.lock);
        rt_mutex_detach(&s_rehab.actuation_lock);
        return -RT_ENOMEM;
    }

    s_rehab.initialized = RT_TRUE;
    rt_thread_startup(s_rehab.thread);
    return RT_EOK;
}

static rt_err_t rehab_service_enter_mode_on_m33(rehab_demo_mode_t mode,
                                                rt_uint8_t slot,
                                                rehab_joint_id_t joint,
                                                rt_uint8_t m33_joint_id,
                                                rehab_cmd_source_t source)
{
    rehab_joint_map_entry_t entry;
    rt_err_t ret;
    rt_uint8_t detail = CONTROL_STATUS_DETAIL_NONE;

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }
    ret = rehab_service_resolve_joint(joint, &entry);
    if (ret != RT_EOK)
    {
        return ret;
    }
    RT_UNUSED(entry);
    if ((m33_joint_id == 0U) || (m33_joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return -RT_EINVAL;
    }

    if (mode == REHAB_DEMO_MODE_MEMORY_RECORD)
    {
        ret = rehab_trajectory_bank_clear(slot);
        if (ret != RT_EOK)
        {
            detail = CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND;
        }
    }
    else if (mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
    {
        if (slot != 0U)
        {
            ret = -RT_ENOSYS;
            detail = CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND;
        }
        else if (!rehab_trajectory_bank_has_data(slot))
        {
            ret = -RT_EEMPTY;
            detail = CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND;
        }
        else if (!control_motor_is_joint_calibrated(m33_joint_id))
        {
            ret = -RT_EINVAL;
            detail = CONTROL_STATUS_DETAIL_JOINT_UNCALIBRATED;
        }
    }

    if ((ret == RT_EOK) &&
        ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
         (mode == REHAB_DEMO_MODE_ASSIST) ||
         (mode == REHAB_DEMO_MODE_RESIST)))
    {
        ret = rehab_service_prepare_feedback(m33_joint_id);
        if (ret != RT_EOK)
        {
            detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
        }
    }

    if (ret != RT_EOK)
    {
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        rehab_service_set_result_locked(detail, ret);
        rt_mutex_release(&s_rehab.lock);
        return ret;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending)
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    if ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
        (mode == REHAB_DEMO_MODE_ASSIST) ||
        (mode == REHAB_DEMO_MODE_RESIST))
    {
        rt_mutex_release(&s_rehab.lock);
        if (mode == REHAB_DEMO_MODE_ASSIST)
        {
            ret = rehab_service_validate_assist_position_mask(
                rehab_service_m33_joint_to_mask(m33_joint_id));
        }
        if (ret == RT_EOK)
        {
            ret = rehab_service_prepare_current_mask(
                rehab_service_m33_joint_to_mask(m33_joint_id));
        }
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        if (ret != RT_EOK)
        {
            rehab_service_set_result_locked(
                (ret == -RT_EINVAL) ? CONTROL_STATUS_DETAIL_TARGET_OUT_OF_LIMIT
                                    : CONTROL_STATUS_DETAIL_MOTOR_FAULT,
                ret);
            rt_mutex_release(&s_rehab.lock);
            rt_mutex_release(&s_rehab.actuation_lock);
            return ret;
        }
    }
    rehab_service_apply_status_locked(mode,
                                      joint,
                                      source,
                                      m33_joint_id,
                                      rehab_service_m33_joint_to_mask(m33_joint_id),
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    s_rehab.status.active_slot = slot;
    s_rehab.status.playback_index = 0U;
    s_rehab.status.record_count = rehab_trajectory_bank_count(slot);
    s_rehab.last_record_tick = 0U;
    s_rehab.stopped_for_fault = RT_FALSE;
    rehab_service_reset_all_strategy_states_locked();
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return RT_EOK;
}

static rt_err_t rehab_service_enter_mode(rehab_demo_mode_t mode,
                                         rt_uint8_t slot,
                                         rehab_joint_id_t joint,
                                         rehab_cmd_source_t source)
{
    rehab_joint_map_entry_t entry;
    rt_err_t ret;

    ret = rehab_service_resolve_joint(joint, &entry);
    if (ret != RT_EOK)
    {
        return ret;
    }
    return rehab_service_enter_mode_on_m33(mode, slot, joint, entry.m33_joint_id, source);
}

rt_err_t rehab_service_set_mode(rehab_demo_mode_t mode,
                                rehab_joint_id_t joint,
                                rehab_cmd_source_t source)
{
    if ((mode == REHAB_DEMO_MODE_MEMORY_RECORD) ||
        (mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK))
    {
        return -RT_EINVAL;
    }
    return rehab_service_enter_mode(mode, 0U, joint, source);
}

static rt_err_t rehab_service_set_mode_mask_internal(
    rehab_demo_mode_t mode,
    rt_uint8_t active_joint_mask,
    rehab_cmd_source_t source,
    rt_bool_t require_unchanged,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation)
{
    rt_uint8_t primary_joint;
    rt_err_t ret;

    if (mode == REHAB_DEMO_MODE_PASSIVE)
    {
        return require_unchanged ? -RT_EINVAL : rehab_service_stop(source);
    }
    if ((mode == REHAB_DEMO_MODE_MEMORY_RECORD) ||
        (mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK) ||
        !rehab_service_joint_mask_valid(active_joint_mask))
    {
        return -RT_EINVAL;
    }

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    primary_joint = rehab_service_first_joint_in_mask(active_joint_mask);
    if (primary_joint == 0U)
    {
        return -RT_EINVAL;
    }

    if (require_unchanged)
    {
        rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        if ((s_rehab.status.source != expected_source) ||
            (s_rehab.status.mode_generation != expected_generation))
        {
            rt_mutex_release(&s_rehab.lock);
            rt_mutex_release(&s_rehab.actuation_lock);
            return -RT_EBUSY;
        }
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
    }

    ret = rehab_service_prepare_feedback_mask(active_joint_mask);
    if (ret != RT_EOK)
    {
        if (require_unchanged)
        {
            rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
        }
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        if (require_unchanged &&
            ((s_rehab.status.source != expected_source) ||
             (s_rehab.status.mode_generation != expected_generation)))
        {
            rt_mutex_release(&s_rehab.lock);
            rt_mutex_release(&s_rehab.actuation_lock);
            return -RT_EBUSY;
        }
        rehab_service_set_result_locked(CONTROL_STATUS_DETAIL_MOTOR_FAULT, ret);
        rt_mutex_release(&s_rehab.lock);
        if (require_unchanged)
        {
            rt_mutex_release(&s_rehab.actuation_lock);
        }
        return ret;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending ||
        (require_unchanged &&
         ((s_rehab.status.source != expected_source) ||
          (s_rehab.status.mode_generation != expected_generation))))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);
    if (mode == REHAB_DEMO_MODE_ASSIST)
    {
        ret = rehab_service_validate_assist_position_mask(active_joint_mask);
    }
    if (ret == RT_EOK)
    {
        ret = rehab_service_prepare_current_mask(active_joint_mask);
    }
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (ret != RT_EOK)
    {
        rehab_service_set_result_locked(
            (ret == -RT_EINVAL) ? CONTROL_STATUS_DETAIL_TARGET_OUT_OF_LIMIT
                                : CONTROL_STATUS_DETAIL_MOTOR_FAULT,
            ret);
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return ret;
    }
    rehab_service_apply_status_locked(mode,
                                      REHAB_JOINT_ELBOW,
                                      source,
                                      primary_joint,
                                      active_joint_mask,
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    s_rehab.status.active_slot = 0U;
    s_rehab.status.playback_index = 0U;
    s_rehab.status.record_count = rehab_trajectory_bank_count(0U);
    s_rehab.last_record_tick = 0U;
    s_rehab.stopped_for_fault = RT_FALSE;
    rehab_service_reset_all_strategy_states_locked();
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return RT_EOK;
}

rt_err_t rehab_service_set_mode_mask(rehab_demo_mode_t mode,
                                     rt_uint8_t active_joint_mask,
                                     rehab_cmd_source_t source)
{
    return rehab_service_set_mode_mask_internal(mode,
                                                active_joint_mask,
                                                source,
                                                RT_FALSE,
                                                source,
                                                0U);
}

rt_err_t rehab_service_set_mode_mask_if_unchanged(
    rehab_demo_mode_t mode,
    rt_uint8_t active_joint_mask,
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation)
{
    return rehab_service_set_mode_mask_internal(mode,
                                                active_joint_mask,
                                                source,
                                                RT_TRUE,
                                                expected_source,
                                                expected_generation);
}

rt_err_t rehab_service_curl_start_if_unchanged(
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation)
{
    control_motor_feedback_t fb;
    rehab_curl_planner_t planner;
    rehab_curl_config_t config;
    rehab_curl_result_t planner_result;
    rt_err_t ret;

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }
    if (!control_motor_is_joint_calibrated(CONTROL_REHAB_CURL_M33_JOINT))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending ||
        (s_rehab.status.source != expected_source) ||
        (s_rehab.status.mode_generation != expected_generation))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);

    ret = rehab_service_prepare_feedback(CONTROL_REHAB_CURL_M33_JOINT);
    if (ret == RT_EOK)
    {
        ret = control_get_motor_feedback(CONTROL_REHAB_CURL_M33_JOINT, &fb);
    }
    if (ret != RT_EOK)
    {
        return ret;
    }

    config = rehab_service_curl_config();
    planner_result = rehab_curl_planner_start(&planner,
                                               &config,
                                               fb.pos_rad,
                                               fb.vel_rad_s,
                                               rehab_ticks_to_ms_u32(rt_tick_get()));
    if (planner_result != REHAB_CURL_RESULT_OK)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending ||
        (s_rehab.status.source != expected_source) ||
        (s_rehab.status.mode_generation != expected_generation))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rehab_service_apply_status_locked(REHAB_DEMO_MODE_CURL,
                                      REHAB_JOINT_ELBOW,
                                      source,
                                      CONTROL_REHAB_CURL_M33_JOINT,
                                      CONTROL_REHAB_CURL_JOINT_MASK,
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    s_rehab.curl_planner = planner;
    s_rehab.status.curl_phase = (rt_uint8_t)planner.phase;
    s_rehab.status.curl_repetitions = 0U;
    s_rehab.stopped_for_fault = RT_FALSE;
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return RT_EOK;
}

rt_err_t rehab_service_fixed_action_start_if_unchanged(
    rehab_fixed_action_id_t action,
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation)
{
    const rehab_fixed_action_profile_t *profile;
    rehab_fixed_action_feedback_t feedback;
    rehab_fixed_action_runner_t runner;
    rt_uint8_t primary_joint;
    rt_uint8_t joint;
    rt_err_t ret;

    profile = rehab_fixed_action_profile(action);
    if ((profile == RT_NULL) || !profile->enabled ||
        !rehab_service_joint_mask_valid(profile->joint_mask))
    {
        return -RT_EINVAL;
    }

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    for (joint = 1U; joint <= CONTROL_MOTOR_JOINT_COUNT; joint++)
    {
        if (!rehab_service_joint_mask_has(profile->joint_mask, joint))
        {
            continue;
        }
        if (!control_motor_is_joint_calibrated(joint))
        {
            return -RT_EINVAL;
        }
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending ||
        (s_rehab.status.source != expected_source) ||
        (s_rehab.status.mode_generation != expected_generation))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);

    ret = rehab_service_prepare_feedback_mask(profile->joint_mask);
    if (ret != RT_EOK)
    {
        return ret;
    }
    ret = rehab_service_fixed_action_feedback(profile->joint_mask, &feedback, RT_NULL);
    if (ret != RT_EOK)
    {
        return ret;
    }
    ret = rehab_fixed_action_start(&runner,
                                   action,
                                   &feedback,
                                   rehab_ticks_to_ms_u32(rt_tick_get()));
    if (ret != RT_EOK)
    {
        return ret;
    }

    primary_joint = rehab_service_first_joint_in_mask(profile->joint_mask);
    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (s_rehab.stop_pending ||
        (s_rehab.status.source != expected_source) ||
        (s_rehab.status.mode_generation != expected_generation))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }
    rehab_service_apply_status_locked(REHAB_DEMO_MODE_FIXED_ACTION,
                                      REHAB_JOINT_ELBOW,
                                      source,
                                      primary_joint,
                                      profile->joint_mask,
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    s_rehab.fixed_action_runner = runner;
    s_rehab.status.fixed_action_id = (rt_uint8_t)action;
    s_rehab.status.fixed_action_state = (rt_uint8_t)runner.state;
    s_rehab.status.fixed_action_repetitions = 0U;
    s_rehab.status.fixed_action_fault = RT_EOK;
    s_rehab.stopped_for_fault = RT_FALSE;
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return RT_EOK;
}

rt_err_t rehab_service_set_mode_on_m33(rehab_demo_mode_t mode,
                                       rehab_joint_id_t joint,
                                       rt_uint8_t m33_joint_id,
                                       rehab_cmd_source_t source)
{
    if ((mode == REHAB_DEMO_MODE_MEMORY_RECORD) ||
        (mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK))
    {
        return -RT_EINVAL;
    }
    return rehab_service_enter_mode_on_m33(mode, 0U, joint, m33_joint_id, source);
}

rt_err_t rehab_service_stop(rehab_cmd_source_t source)
{
    rt_uint8_t m33_joint;
    rt_uint8_t active_joint_mask;

    rt_err_t ret;
    rehab_joint_id_t joint;

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }
    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    m33_joint = s_rehab.status.m33_joint_id;
    joint = s_rehab.status.joint;
    active_joint_mask = s_rehab.status.active_joint_mask;
    if (!rehab_service_joint_mask_valid(active_joint_mask))
    {
        active_joint_mask = rehab_service_m33_joint_to_mask(m33_joint);
    }
    s_rehab.stop_pending = RT_TRUE;
    rt_mutex_release(&s_rehab.lock);

    ret = rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (ret == RT_EOK)
    {
        rehab_service_apply_status_locked(REHAB_DEMO_MODE_PASSIVE,
                                          joint,
                                          source,
                                          m33_joint,
                                          0U,
                                          CONTROL_STATUS_DETAIL_NONE,
                                          RT_EOK);
        rehab_service_reset_all_strategy_states_locked();
        s_rehab.stopped_for_fault = RT_FALSE;
    }
    else
    {
        rehab_service_set_result_locked(CONTROL_STATUS_DETAIL_MOTOR_FAULT, ret);
    }
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return ret;
}

rt_err_t rehab_service_stop_if_owned(rehab_cmd_source_t expected_source,
                                     rt_uint32_t expected_generation,
                                     rt_uint8_t success_detail)
{
    rt_uint8_t m33_joint;
    rt_uint8_t active_joint_mask;
    rehab_joint_id_t joint;
    rt_err_t ret;

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab.actuation_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (((expected_source != REHAB_CMD_SOURCE_CAN) &&
         (expected_source != REHAB_CMD_SOURCE_VOICE) &&
         (expected_source != REHAB_CMD_SOURCE_APP_BLE)) ||
        (s_rehab.status.source != expected_source) ||
        (s_rehab.status.mode == REHAB_DEMO_MODE_PASSIVE) ||
        (s_rehab.status.mode_generation != expected_generation))
    {
        rt_mutex_release(&s_rehab.lock);
        rt_mutex_release(&s_rehab.actuation_lock);
        return -RT_EBUSY;
    }

    m33_joint = s_rehab.status.m33_joint_id;
    joint = s_rehab.status.joint;
    active_joint_mask = s_rehab.status.active_joint_mask;
    if (!rehab_service_joint_mask_valid(active_joint_mask))
    {
        active_joint_mask = rehab_service_m33_joint_to_mask(m33_joint);
    }
    s_rehab.stop_pending = RT_TRUE;
    rt_mutex_release(&s_rehab.lock);

    ret = rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    if (ret == RT_EOK)
    {
        rehab_service_apply_status_locked(REHAB_DEMO_MODE_PASSIVE,
                                          joint,
                                          expected_source,
                                          m33_joint,
                                          0U,
                                          success_detail,
                                          RT_EOK);
        rehab_service_reset_all_strategy_states_locked();
        s_rehab.stopped_for_fault = RT_FALSE;
    }
    else
    {
        rehab_service_set_result_locked(CONTROL_STATUS_DETAIL_MOTOR_FAULT, ret);
    }
    rt_mutex_release(&s_rehab.lock);
    rt_mutex_release(&s_rehab.actuation_lock);
    return ret;
}

rt_err_t rehab_service_record_start(rt_uint8_t slot,
                                    rehab_joint_id_t joint,
                                    rehab_cmd_source_t source)
{
    return rehab_service_enter_mode(REHAB_DEMO_MODE_MEMORY_RECORD, slot, joint, source);
}

rt_err_t rehab_service_record_start_on_m33(rt_uint8_t slot,
                                           rehab_joint_id_t joint,
                                           rt_uint8_t m33_joint_id,
                                           rehab_cmd_source_t source)
{
    return rehab_service_enter_mode_on_m33(REHAB_DEMO_MODE_MEMORY_RECORD,
                                           slot,
                                           joint,
                                           m33_joint_id,
                                           source);
}

rt_err_t rehab_service_record_stop(rehab_cmd_source_t source)
{
    return rehab_service_stop(source);
}

rt_err_t rehab_service_play_start(rt_uint8_t slot,
                                  rehab_joint_id_t joint,
                                  rehab_cmd_source_t source)
{
    return rehab_service_enter_mode(REHAB_DEMO_MODE_MEMORY_PLAYBACK, slot, joint, source);
}

rt_err_t rehab_service_play_start_on_m33(rt_uint8_t slot,
                                         rehab_joint_id_t joint,
                                         rt_uint8_t m33_joint_id,
                                         rehab_cmd_source_t source)
{
    return rehab_service_enter_mode_on_m33(REHAB_DEMO_MODE_MEMORY_PLAYBACK,
                                           slot,
                                           joint,
                                           m33_joint_id,
                                           source);
}

rt_err_t rehab_service_play_stop(rehab_cmd_source_t source)
{
    return rehab_service_stop(source);
}

static rt_bool_t rehab_service_intensity_mode_supported(rehab_demo_mode_t mode)
{
    return ((mode == REHAB_DEMO_MODE_ASSIST) ||
            (mode == REHAB_DEMO_MODE_RESIST))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_err_t rehab_service_intensity_owner_check_locked(rehab_demo_mode_t mode,
                                                           rehab_cmd_source_t source)
{
    if ((source != REHAB_CMD_SOURCE_BENCH_MSH) &&
        (source != REHAB_CMD_SOURCE_VOICE))
    {
        return -RT_EINVAL;
    }
    if (s_rehab.status.mode == REHAB_DEMO_MODE_PASSIVE)
    {
        return (source == REHAB_CMD_SOURCE_BENCH_MSH) ? RT_EOK : -RT_EBUSY;
    }
    if ((s_rehab.status.mode != mode) || (s_rehab.status.source != source))
    {
        return -RT_EBUSY;
    }
    return RT_EOK;
}

rt_err_t rehab_service_get_intensity_level(rehab_demo_mode_t mode,
                                           rt_uint8_t *level,
                                           float *current_a)
{
    float selected_current;
    rt_err_t ret;

    if ((level == RT_NULL) || !rehab_service_intensity_mode_supported(mode))
    {
        return -RT_EINVAL;
    }
    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    selected_current = (mode == REHAB_DEMO_MODE_ASSIST) ?
                       s_rehab.params.assist_max_current_a :
                       s_rehab.params.resist_max_current_a;
    *level = rehab_intensity_level_for_current(selected_current);
    if (current_a != RT_NULL)
    {
        *current_a = selected_current;
    }
    rt_mutex_release(&s_rehab.lock);
    return RT_EOK;
}

rt_err_t rehab_service_set_intensity_level(rehab_demo_mode_t mode,
                                           rt_uint8_t level,
                                           rehab_cmd_source_t source,
                                           rt_uint8_t *applied_level)
{
    float selected_current;
    rt_err_t ret;

    if (!rehab_service_intensity_mode_supported(mode))
    {
        return -RT_EINVAL;
    }
    selected_current = rehab_intensity_current_for_level(level);
    if (selected_current <= 0.0f)
    {
        return -RT_EINVAL;
    }
    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    ret = rehab_service_intensity_owner_check_locked(mode, source);
    if (ret == RT_EOK)
    {
        if (mode == REHAB_DEMO_MODE_ASSIST)
        {
            s_rehab.params.assist_max_current_a = selected_current;
            s_rehab.params.assist_min_current_a = selected_current;
        }
        else
        {
            s_rehab.params.resist_max_current_a = selected_current;
        }
        if (applied_level != RT_NULL)
        {
            *applied_level = level;
        }
    }
    rt_mutex_release(&s_rehab.lock);
    return ret;
}

rt_err_t rehab_service_adjust_intensity_level(rehab_demo_mode_t mode,
                                              rt_int8_t delta,
                                              rehab_cmd_source_t source,
                                              rt_uint8_t *applied_level)
{
    float selected_current;
    rt_uint8_t current_level;
    rt_uint8_t target_level;
    rt_err_t ret;

    if (!rehab_service_intensity_mode_supported(mode) ||
        ((delta != -1) && (delta != 1)))
    {
        return -RT_EINVAL;
    }
    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    ret = rehab_service_intensity_owner_check_locked(mode, source);
    if (ret == RT_EOK)
    {
        selected_current = (mode == REHAB_DEMO_MODE_ASSIST) ?
                           s_rehab.params.assist_max_current_a :
                           s_rehab.params.resist_max_current_a;
        current_level = rehab_intensity_level_for_current(selected_current);
        target_level = rehab_intensity_adjust_level(current_level, delta);
        selected_current = rehab_intensity_current_for_level(target_level);
        if (mode == REHAB_DEMO_MODE_ASSIST)
        {
            s_rehab.params.assist_max_current_a = selected_current;
            s_rehab.params.assist_min_current_a = selected_current;
        }
        else
        {
            s_rehab.params.resist_max_current_a = selected_current;
        }
        if (applied_level != RT_NULL)
        {
            *applied_level = target_level;
        }
    }
    rt_mutex_release(&s_rehab.lock);
    return ret;
}

rt_err_t rehab_service_get_params(rehab_strategy_params_t *out)
{
    if (out == RT_NULL)
    {
        return -RT_EINVAL;
    }

    (void)rehab_service_init();
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    *out = s_rehab.params;
    rt_mutex_release(&s_rehab.lock);
    return RT_EOK;
}

rt_err_t rehab_service_set_params(const rehab_strategy_params_t *params)
{
    rehab_strategy_params_t sanitized;

    if (params == RT_NULL)
    {
        return -RT_EINVAL;
    }

    (void)rehab_service_init();
    sanitized = *params;
    rehab_service_sanitize_params(&sanitized);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.params = sanitized;
    rehab_service_reset_all_strategy_states_locked();
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
    return RT_EOK;
}

void rehab_service_get_status(rehab_service_status_t *out)
{
    if (out == RT_NULL)
    {
        return;
    }
    (void)rehab_service_init();

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.record_count = rehab_trajectory_bank_count(s_rehab.status.active_slot);
    rehab_service_update_flags_locked();
    *out = s_rehab.status;
    rt_mutex_release(&s_rehab.lock);
}

rt_bool_t rehab_service_accepts_ros_target(void)
{
    rehab_service_status_t status;

    rehab_service_get_status(&status);
    return (status.mode == REHAB_DEMO_MODE_PASSIVE) ? RT_TRUE : RT_FALSE;
}
