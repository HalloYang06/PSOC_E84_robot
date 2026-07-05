#include "rehab_service.h"

#include "control_layer.h"
#include "control_layer_cfg.h"
#include "rehab_active_follow.h"
#include "rehab_assist_strategy.h"
#include "rehab_resist_strategy.h"
#include "rehab_trajectory_bank.h"

typedef struct
{
    struct rt_mutex lock;
    rt_thread_t thread;
    rehab_service_status_t status;
    rehab_strategy_params_t params;
    rehab_assist_strategy_state_t assist_state;
    rehab_resist_strategy_state_t resist_state;
    rt_tick_t last_record_tick;
    rt_bool_t initialized;
    rt_bool_t stopped_for_fault;
} rehab_service_runtime_t;

static rehab_service_runtime_t s_rehab;

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

static void rehab_service_default_params(rehab_strategy_params_t *out)
{
    if (out == RT_NULL)
    {
        return;
    }

    out->follow_direction = CONTROL_REHAB_FOLLOW_DIRECTION;
    out->resist_direction = CONTROL_REHAB_RESIST_DIRECTION;
    out->active_min_current_a = CONTROL_REHAB_ACTIVE_MIN_CUR_A;
    out->active_max_current_a = CONTROL_REHAB_ACTIVE_LIMIT_CUR_A;
    out->active_current_gain_a_per_nm = CONTROL_REHAB_ACTIVE_GAIN_A_PER_NM;
    out->assist_max_current_a = CONTROL_REHAB_ASSIST_LIMIT_CUR_A;
    out->assist_current_gain_a_per_nm = CONTROL_REHAB_ASSIST_GAIN_A_PER_NM;
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
                                              rt_uint8_t detail,
                                              rt_err_t result)
{
    s_rehab.status.mode = mode;
    s_rehab.status.source = source;
    s_rehab.status.joint = joint;
    s_rehab.status.m33_joint_id = m33_joint;
    s_rehab.status.detail = detail;
    s_rehab.status.last_result = result;
    s_rehab.status.feedback_fresh = RT_FALSE;
    s_rehab.status.assist_engaged = RT_FALSE;
    rehab_service_clear_observation_locked();
    s_rehab.status.timestamp = rt_tick_get();
    rehab_service_update_flags_locked();
}

static void rehab_service_note_fault(rt_uint8_t m33_joint, rt_uint8_t detail, rt_err_t result)
{
    rt_bool_t should_stop;

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    should_stop = !s_rehab.stopped_for_fault;
    s_rehab.status.feedback_fresh = RT_FALSE;
    s_rehab.status.assist_engaged = RT_FALSE;
    rehab_service_clear_observation_locked();
    s_rehab.stopped_for_fault = RT_TRUE;
    rehab_service_set_result_locked(detail, result);
    rt_mutex_release(&s_rehab.lock);

    if (should_stop)
    {
        (void)control_motor_stop(m33_joint, RT_FALSE);
    }
}

static void rehab_service_complete_to_passive(rt_uint8_t m33_joint, rt_err_t result)
{
    (void)control_motor_stop(m33_joint, RT_FALSE);

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.mode = REHAB_DEMO_MODE_PASSIVE;
    s_rehab.status.assist_engaged = RT_FALSE;
    s_rehab.status.feedback_fresh = RT_TRUE;
    rehab_service_clear_observation_locked();
    s_rehab.stopped_for_fault = RT_FALSE;
    rehab_assist_strategy_reset(&s_rehab.assist_state);
    rehab_resist_strategy_reset(&s_rehab.resist_state);
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

static void rehab_service_apply_strategy_output(rt_uint8_t m33_joint,
                                                rehab_demo_mode_t mode,
                                                const rehab_strategy_output_t *out)
{
    rt_err_t ret = RT_EOK;

    if (out == RT_NULL)
    {
        return;
    }

    if (out->type == REHAB_STRATEGY_OUTPUT_CURRENT)
    {
        ret = control_motor_current_control(m33_joint, out->current_a);
    }
    else if ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
             (mode == REHAB_DEMO_MODE_ASSIST) ||
             (mode == REHAB_DEMO_MODE_RESIST))
    {
        ret = control_motor_stop(m33_joint, RT_FALSE);
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    s_rehab.status.last_result = ret;
    if (ret != RT_EOK)
    {
        s_rehab.status.detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
}

static void rehab_service_worker(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
        rehab_demo_mode_t mode;
        rt_uint8_t m33_joint;
        control_motor_feedback_t fb;
        rehab_strategy_output_t out;
        rehab_strategy_params_t params;
        rt_bool_t fresh;
        rt_bool_t stopped_for_fault;
        rt_tick_t now;

        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        mode = s_rehab.status.mode;
        m33_joint = s_rehab.status.m33_joint_id;
        params = s_rehab.params;
        stopped_for_fault = s_rehab.stopped_for_fault;
        rt_mutex_release(&s_rehab.lock);

        if (mode == REHAB_DEMO_MODE_PASSIVE)
        {
            rt_thread_mdelay(CONTROL_REHAB_SERVICE_PERIOD_MS);
            continue;
        }

        now = rt_tick_get();
        fresh = (control_get_motor_feedback(m33_joint, &fb) == RT_EOK) &&
                rehab_feedback_is_fresh(&fb, now);
        if (!fresh)
        {
            rehab_service_note_fault(m33_joint, CONTROL_STATUS_DETAIL_MOTOR_FAULT, -RT_ETIMEOUT);
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

        switch (mode)
        {
        case REHAB_DEMO_MODE_ACTIVE_FOLLOW:
            rehab_active_follow_step(&params, &fb, &out);
            break;
        case REHAB_DEMO_MODE_ASSIST:
            rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
            rehab_assist_strategy_step(&s_rehab.assist_state, &params, &fb, 1.0f, &out);
            rt_mutex_release(&s_rehab.lock);
            break;
        case REHAB_DEMO_MODE_RESIST:
            rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
            rehab_resist_strategy_step(&s_rehab.resist_state, &params, &fb, &out);
            rt_mutex_release(&s_rehab.lock);
            break;
        case REHAB_DEMO_MODE_MEMORY_RECORD:
            rehab_service_record_sample(&fb, now);
            break;
        case REHAB_DEMO_MODE_MEMORY_PLAYBACK:
            rehab_service_playback_step(m33_joint);
            break;
        case REHAB_DEMO_MODE_PASSIVE:
        default:
            break;
        }

        if ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
            (mode == REHAB_DEMO_MODE_ASSIST) ||
            (mode == REHAB_DEMO_MODE_RESIST))
        {
            rehab_service_apply_strategy_output(m33_joint, mode, &out);
        }

        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        s_rehab.status.feedback_fresh = RT_TRUE;
        s_rehab.status.assist_engaged = out.engaged;
        rehab_service_update_observation_locked(&fb, &out);
        s_rehab.status.record_count = rehab_trajectory_bank_count(s_rehab.status.active_slot);
        s_rehab.status.timestamp = now;
        rehab_service_update_flags_locked();
        rt_mutex_release(&s_rehab.lock);

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
    ret = rt_mutex_init(&s_rehab.lock, "rehabs", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
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
    s_rehab.status.detail = CONTROL_STATUS_DETAIL_NONE;
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

    if (ret != RT_EOK)
    {
        rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
        rehab_service_apply_status_locked(REHAB_DEMO_MODE_PASSIVE,
                                          joint,
                                          source,
                                          m33_joint_id,
                                          detail,
                                          ret);
        rt_mutex_release(&s_rehab.lock);
        return ret;
    }

    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    rehab_service_apply_status_locked(mode,
                                      joint,
                                      source,
                                      m33_joint_id,
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    s_rehab.status.active_slot = slot;
    s_rehab.status.playback_index = 0U;
    s_rehab.status.record_count = rehab_trajectory_bank_count(slot);
    s_rehab.last_record_tick = 0U;
    s_rehab.stopped_for_fault = RT_FALSE;
    rehab_assist_strategy_reset(&s_rehab.assist_state);
    rehab_resist_strategy_reset(&s_rehab.resist_state);
    rehab_service_update_flags_locked();
    rt_mutex_release(&s_rehab.lock);
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

    (void)rehab_service_init();
    rt_mutex_take(&s_rehab.lock, RT_WAITING_FOREVER);
    m33_joint = s_rehab.status.m33_joint_id;
    rehab_service_apply_status_locked(REHAB_DEMO_MODE_PASSIVE,
                                      s_rehab.status.joint,
                                      source,
                                      m33_joint,
                                      CONTROL_STATUS_DETAIL_NONE,
                                      RT_EOK);
    rehab_assist_strategy_reset(&s_rehab.assist_state);
    rehab_resist_strategy_reset(&s_rehab.resist_state);
    s_rehab.stopped_for_fault = RT_FALSE;
    rt_mutex_release(&s_rehab.lock);

    return control_motor_stop(m33_joint, RT_FALSE);
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
    rehab_assist_strategy_reset(&s_rehab.assist_state);
    rehab_resist_strategy_reset(&s_rehab.resist_state);
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
