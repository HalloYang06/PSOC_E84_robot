#include "rehab_service.h"

#include <stdlib.h>
#include <string.h>

#ifdef RT_USING_FINSH
#include <finsh.h>

static int rehab_shell_scaled(float value)
{
    return (int)((value >= 0.0f) ? ((value * 1000.0f) + 0.5f) : ((value * 1000.0f) - 0.5f));
}

static rehab_joint_map_entry_t rehab_shell_parse_entry(int argc, char **argv, int index)
{
    rehab_joint_map_entry_t entry;

    (void)rehab_joint_map_get(REHAB_JOINT_ELBOW, &entry);

    if (argc > index)
    {
        if (!rehab_joint_map_parse_entry(argv[index], &entry))
        {
            rt_kprintf("rehab: unknown joint/motor %s, default elbow\n", argv[index]);
            (void)rehab_joint_map_get(REHAB_JOINT_ELBOW, &entry);
        }
    }
    return entry;
}

static const char *rehab_shell_mode_name(rehab_demo_mode_t mode)
{
    switch (mode)
    {
    case REHAB_DEMO_MODE_PASSIVE:
        return "passive";
    case REHAB_DEMO_MODE_ACTIVE_FOLLOW:
        return "active";
    case REHAB_DEMO_MODE_ASSIST:
        return "assist";
    case REHAB_DEMO_MODE_RESIST:
        return "resist";
    case REHAB_DEMO_MODE_MEMORY_RECORD:
        return "memory_record";
    case REHAB_DEMO_MODE_MEMORY_PLAYBACK:
        return "memory_playback";
    default:
        return "unknown";
    }
}

static void rehab_shell_print_status(void)
{
    rehab_service_status_t status;

    rehab_service_get_status(&status);
    rt_kprintf("rehab status mode=%s source=%u joint=%s m33_joint=%u fresh=%u detail=%u assist=%u torque_x1000=%d vel_x1000=%d current_x1000=%d limit_x1000=%d gain_x1000=%d pid_kp_x1000=%d pid_ki_x1000=%d pid_kd_x1000=%d pid_load_x1000=%d pid_speed_x1000=%d pid_err_x1000=%d pid_trim_x1000=%d adrc_err_x1000=%d adrc_z1_x1000=%d adrc_z2_x1000=%d adrc_z3_x1000=%d adrc_trim_x1000=%d sat=%u record_count=%u playback_index=%u last=%d\n",
               rehab_shell_mode_name(status.mode),
               (unsigned int)status.source,
               rehab_joint_map_name(status.joint),
               (unsigned int)status.m33_joint_id,
               status.feedback_fresh ? 1U : 0U,
               (unsigned int)status.detail,
               status.assist_engaged ? 1U : 0U,
               rehab_shell_scaled(status.feedback_torque_nm),
               rehab_shell_scaled(status.feedback_vel_rad_s),
               rehab_shell_scaled(status.output_current_a),
               rehab_shell_scaled(status.output_limit_current_a),
               rehab_shell_scaled(status.effective_gain),
               rehab_shell_scaled(status.pid_kp),
               rehab_shell_scaled(status.pid_ki),
               rehab_shell_scaled(status.pid_kd),
               rehab_shell_scaled(status.pid_load_level),
               rehab_shell_scaled(status.pid_speed_level),
               rehab_shell_scaled(status.pid_error),
               rehab_shell_scaled(status.pid_trim_current_a),
               rehab_shell_scaled(status.adrc_error),
               rehab_shell_scaled(status.adrc_z1),
               rehab_shell_scaled(status.adrc_z2),
               rehab_shell_scaled(status.adrc_z3),
               rehab_shell_scaled(status.adrc_trim_current_a),
               status.output_saturated ? 1U : 0U,
               (unsigned int)status.record_count,
               (unsigned int)status.playback_index,
               status.last_result);
}

static void rehab_shell_print_params(void)
{
    rehab_strategy_params_t params;

    if (rehab_service_get_params(&params) != RT_EOK)
    {
        rt_kprintf("rehab cfg unavailable\n");
        return;
    }

    rt_kprintf("rehab cfg direction_x1000=%d resist_dir_x1000=%d active_min_x1000=%d active_max_x1000=%d active_gain_x1000=%d assist_max_x1000=%d assist_gain_x1000=%d adaptive=%u adaptive_base_x1000=%d adaptive_load_x1000=%d adaptive_max_x1000=%d adaptive_step_x1000=%d resist_max_x1000=%d resist_gain_x1000=%d\n",
               rehab_shell_scaled(params.follow_direction),
               rehab_shell_scaled(params.resist_direction),
               rehab_shell_scaled(params.active_min_current_a),
               rehab_shell_scaled(params.active_max_current_a),
               rehab_shell_scaled(params.active_current_gain_a_per_nm),
               rehab_shell_scaled(params.assist_max_current_a),
               rehab_shell_scaled(params.assist_current_gain_a_per_nm),
               params.adaptive_assist_enabled ? 1U : 0U,
               rehab_shell_scaled(params.adaptive_assist_base_gain_a_per_nm),
               rehab_shell_scaled(params.adaptive_assist_load_gain_a_per_nm2),
               rehab_shell_scaled(params.adaptive_assist_max_gain_a_per_nm),
               rehab_shell_scaled(params.adaptive_assist_gain_step_a_per_nm),
               rehab_shell_scaled(params.resist_max_current_a),
               rehab_shell_scaled(params.resist_current_gain_a_per_rad_s));
    rt_kprintf("rehab pid assist_pid=%u resist_pid=%u load_low_x1000=%d load_high_x1000=%d speed_low_x1000=%d speed_high_x1000=%d assist_target_x1000=%d assist_kp_x1000=%d/%d/%d assist_ki_x1000=%d/%d/%d assist_kd_x1000=%d/%d assist_i_limit_x1000=%d assist_trim_x1000=%d resist_target_x1000=%d resist_kp_x1000=%d/%d/%d resist_ki_x1000=%d/%d/%d resist_kd_x1000=%d/%d resist_i_limit_x1000=%d resist_trim_x1000=%d\n",
               params.assist_adaptive_pid_enabled ? 1U : 0U,
               params.resist_adaptive_pid_enabled ? 1U : 0U,
               rehab_shell_scaled(params.adaptive_pid_load_low_nm),
               rehab_shell_scaled(params.adaptive_pid_load_high_nm),
               rehab_shell_scaled(params.adaptive_pid_speed_low_rad_s),
               rehab_shell_scaled(params.adaptive_pid_speed_high_rad_s),
               rehab_shell_scaled(params.assist_pid.target),
               rehab_shell_scaled(params.assist_pid.kp_base),
               rehab_shell_scaled(params.assist_pid.kp_load),
               rehab_shell_scaled(params.assist_pid.kp_speed),
               rehab_shell_scaled(params.assist_pid.ki_base),
               rehab_shell_scaled(params.assist_pid.ki_load),
               rehab_shell_scaled(params.assist_pid.ki_speed_reduce),
               rehab_shell_scaled(params.assist_pid.kd_base),
               rehab_shell_scaled(params.assist_pid.kd_speed),
               rehab_shell_scaled(params.assist_pid.integral_limit),
               rehab_shell_scaled(params.assist_pid.trim_limit),
               rehab_shell_scaled(params.resist_pid.target),
               rehab_shell_scaled(params.resist_pid.kp_base),
               rehab_shell_scaled(params.resist_pid.kp_load),
               rehab_shell_scaled(params.resist_pid.kp_speed),
               rehab_shell_scaled(params.resist_pid.ki_base),
               rehab_shell_scaled(params.resist_pid.ki_load),
               rehab_shell_scaled(params.resist_pid.ki_speed_reduce),
               rehab_shell_scaled(params.resist_pid.kd_base),
               rehab_shell_scaled(params.resist_pid.kd_speed),
               rehab_shell_scaled(params.resist_pid.integral_limit),
               rehab_shell_scaled(params.resist_pid.trim_limit));
    rt_kprintf("rehab adrc assist_adrc=%u resist_adrc=%u assist_target_x1000=%d assist_b0_x1000=%d assist_kp_x1000=%d assist_kd_x1000=%d assist_dist_x1000=%d assist_trim_x1000=%d resist_target_x1000=%d resist_b0_x1000=%d resist_kp_x1000=%d resist_kd_x1000=%d resist_dist_x1000=%d resist_trim_x1000=%d beta_x1000=%d/%d/%d\n",
               params.assist_adrc_enabled ? 1U : 0U,
               params.resist_adrc_enabled ? 1U : 0U,
               rehab_shell_scaled(params.assist_adrc.target),
               rehab_shell_scaled(params.assist_adrc.b0),
               rehab_shell_scaled(params.assist_adrc.kp),
               rehab_shell_scaled(params.assist_adrc.kd),
               rehab_shell_scaled(params.assist_adrc.disturbance_gain),
               rehab_shell_scaled(params.assist_adrc.trim_limit),
               rehab_shell_scaled(params.resist_adrc.target),
               rehab_shell_scaled(params.resist_adrc.b0),
               rehab_shell_scaled(params.resist_adrc.kp),
               rehab_shell_scaled(params.resist_adrc.kd),
               rehab_shell_scaled(params.resist_adrc.disturbance_gain),
               rehab_shell_scaled(params.resist_adrc.trim_limit),
               rehab_shell_scaled(params.assist_adrc.beta1),
               rehab_shell_scaled(params.assist_adrc.beta2),
               rehab_shell_scaled(params.assist_adrc.beta3));
}

static rt_bool_t rehab_shell_apply_cfg(rehab_strategy_params_t *params, const char *key, float value)
{
    if ((params == RT_NULL) || (key == RT_NULL))
    {
        return RT_FALSE;
    }

    if ((strcmp(key, "direction") == 0) || (strcmp(key, "follow_dir") == 0))
    {
        params->follow_direction = value;
    }
    else if (strcmp(key, "resist_dir") == 0)
    {
        params->resist_direction = value;
    }
    else if (strcmp(key, "active_min") == 0)
    {
        params->active_min_current_a = value;
    }
    else if (strcmp(key, "active_max") == 0)
    {
        params->active_max_current_a = value;
    }
    else if (strcmp(key, "active_gain") == 0)
    {
        params->active_current_gain_a_per_nm = value;
    }
    else if (strcmp(key, "assist_max") == 0)
    {
        params->assist_max_current_a = value;
    }
    else if (strcmp(key, "assist_gain") == 0)
    {
        params->assist_current_gain_a_per_nm = value;
    }
    else if (strcmp(key, "adaptive_enable") == 0)
    {
        params->adaptive_assist_enabled = (value != 0.0f) ? RT_TRUE : RT_FALSE;
    }
    else if (strcmp(key, "adaptive_base") == 0)
    {
        params->adaptive_assist_base_gain_a_per_nm = value;
    }
    else if (strcmp(key, "adaptive_load") == 0)
    {
        params->adaptive_assist_load_gain_a_per_nm2 = value;
    }
    else if (strcmp(key, "adaptive_max") == 0)
    {
        params->adaptive_assist_max_gain_a_per_nm = value;
    }
    else if (strcmp(key, "adaptive_step") == 0)
    {
        params->adaptive_assist_gain_step_a_per_nm = value;
    }
    else if (strcmp(key, "assist_pid_enable") == 0)
    {
        params->assist_adaptive_pid_enabled = (value != 0.0f) ? RT_TRUE : RT_FALSE;
    }
    else if (strcmp(key, "resist_pid_enable") == 0)
    {
        params->resist_adaptive_pid_enabled = (value != 0.0f) ? RT_TRUE : RT_FALSE;
    }
    else if (strcmp(key, "assist_adrc_enable") == 0)
    {
        params->assist_adrc_enabled = (value != 0.0f) ? RT_TRUE : RT_FALSE;
    }
    else if (strcmp(key, "resist_adrc_enable") == 0)
    {
        params->resist_adrc_enabled = (value != 0.0f) ? RT_TRUE : RT_FALSE;
    }
    else if (strcmp(key, "pid_load_low") == 0)
    {
        params->adaptive_pid_load_low_nm = value;
    }
    else if (strcmp(key, "pid_load_high") == 0)
    {
        params->adaptive_pid_load_high_nm = value;
    }
    else if (strcmp(key, "pid_speed_low") == 0)
    {
        params->adaptive_pid_speed_low_rad_s = value;
    }
    else if (strcmp(key, "pid_speed_high") == 0)
    {
        params->adaptive_pid_speed_high_rad_s = value;
    }
    else if (strcmp(key, "assist_pid_target") == 0)
    {
        params->assist_pid.target = value;
    }
    else if (strcmp(key, "assist_pid_kp_base") == 0)
    {
        params->assist_pid.kp_base = value;
    }
    else if (strcmp(key, "assist_pid_kp_load") == 0)
    {
        params->assist_pid.kp_load = value;
    }
    else if (strcmp(key, "assist_pid_kp_speed") == 0)
    {
        params->assist_pid.kp_speed = value;
    }
    else if (strcmp(key, "assist_pid_ki_base") == 0)
    {
        params->assist_pid.ki_base = value;
    }
    else if (strcmp(key, "assist_pid_ki_load") == 0)
    {
        params->assist_pid.ki_load = value;
    }
    else if (strcmp(key, "assist_pid_ki_speed_reduce") == 0)
    {
        params->assist_pid.ki_speed_reduce = value;
    }
    else if (strcmp(key, "assist_pid_kd_base") == 0)
    {
        params->assist_pid.kd_base = value;
    }
    else if (strcmp(key, "assist_pid_kd_speed") == 0)
    {
        params->assist_pid.kd_speed = value;
    }
    else if (strcmp(key, "assist_pid_i_limit") == 0)
    {
        params->assist_pid.integral_limit = value;
    }
    else if (strcmp(key, "assist_pid_trim") == 0)
    {
        params->assist_pid.trim_limit = value;
    }
    else if (strcmp(key, "resist_pid_target") == 0)
    {
        params->resist_pid.target = value;
    }
    else if (strcmp(key, "resist_pid_kp_base") == 0)
    {
        params->resist_pid.kp_base = value;
    }
    else if (strcmp(key, "resist_pid_kp_load") == 0)
    {
        params->resist_pid.kp_load = value;
    }
    else if (strcmp(key, "resist_pid_kp_speed") == 0)
    {
        params->resist_pid.kp_speed = value;
    }
    else if (strcmp(key, "resist_pid_ki_base") == 0)
    {
        params->resist_pid.ki_base = value;
    }
    else if (strcmp(key, "resist_pid_ki_load") == 0)
    {
        params->resist_pid.ki_load = value;
    }
    else if (strcmp(key, "resist_pid_ki_speed_reduce") == 0)
    {
        params->resist_pid.ki_speed_reduce = value;
    }
    else if (strcmp(key, "resist_pid_kd_base") == 0)
    {
        params->resist_pid.kd_base = value;
    }
    else if (strcmp(key, "resist_pid_kd_speed") == 0)
    {
        params->resist_pid.kd_speed = value;
    }
    else if (strcmp(key, "resist_pid_i_limit") == 0)
    {
        params->resist_pid.integral_limit = value;
    }
    else if (strcmp(key, "resist_pid_trim") == 0)
    {
        params->resist_pid.trim_limit = value;
    }
    else if (strcmp(key, "assist_adrc_target") == 0)
    {
        params->assist_adrc.target = value;
    }
    else if (strcmp(key, "resist_adrc_target") == 0)
    {
        params->resist_adrc.target = value;
    }
    else if (strcmp(key, "assist_adrc_b0") == 0)
    {
        params->assist_adrc.b0 = value;
    }
    else if (strcmp(key, "resist_adrc_b0") == 0)
    {
        params->resist_adrc.b0 = value;
    }
    else if (strcmp(key, "adrc_beta1") == 0)
    {
        params->assist_adrc.beta1 = value;
        params->resist_adrc.beta1 = value;
    }
    else if (strcmp(key, "adrc_beta2") == 0)
    {
        params->assist_adrc.beta2 = value;
        params->resist_adrc.beta2 = value;
    }
    else if (strcmp(key, "adrc_beta3") == 0)
    {
        params->assist_adrc.beta3 = value;
        params->resist_adrc.beta3 = value;
    }
    else if (strcmp(key, "assist_adrc_kp") == 0)
    {
        params->assist_adrc.kp = value;
    }
    else if (strcmp(key, "assist_adrc_kd") == 0)
    {
        params->assist_adrc.kd = value;
    }
    else if (strcmp(key, "assist_adrc_disturbance") == 0)
    {
        params->assist_adrc.disturbance_gain = value;
    }
    else if (strcmp(key, "assist_adrc_trim") == 0)
    {
        params->assist_adrc.trim_limit = value;
    }
    else if (strcmp(key, "resist_adrc_kp") == 0)
    {
        params->resist_adrc.kp = value;
    }
    else if (strcmp(key, "resist_adrc_kd") == 0)
    {
        params->resist_adrc.kd = value;
    }
    else if (strcmp(key, "resist_adrc_disturbance") == 0)
    {
        params->resist_adrc.disturbance_gain = value;
    }
    else if (strcmp(key, "resist_adrc_trim") == 0)
    {
        params->resist_adrc.trim_limit = value;
    }
    else if (strcmp(key, "resist_max") == 0)
    {
        params->resist_max_current_a = value;
    }
    else if (strcmp(key, "resist_gain") == 0)
    {
        params->resist_current_gain_a_per_rad_s = value;
    }
    else
    {
        return RT_FALSE;
    }

    return RT_TRUE;
}

static void rehab_shell_usage(void)
{
    rt_kprintf("usage: rehab status|cfg [key value|reset]|passive|active [joint|motor]|assist [joint|motor]|resist [joint|motor]|rec_start [joint|motor]|rec_stop|play [joint|motor]|stop\n");
}

int rehab(int argc, char **argv)
{
    rt_err_t ret = RT_EOK;
    rehab_joint_map_entry_t entry;
    rehab_strategy_params_t params;

    (void)rehab_service_init();
    if (argc < 2)
    {
        rehab_shell_usage();
        rehab_shell_print_status();
        return 0;
    }

    if (strcmp(argv[1], "status") == 0)
    {
        rehab_shell_print_status();
        rehab_shell_print_params();
        return 0;
    }
    if (strcmp(argv[1], "cfg") == 0)
    {
        if (argc == 2)
        {
            rehab_shell_print_params();
            return 0;
        }
        if (strcmp(argv[2], "reset") == 0)
        {
            rt_memset(&params, 0, sizeof(params));
            ret = rehab_service_set_params(&params);
            rt_kprintf("rehab cfg reset ret=%d\n", ret);
            rehab_shell_print_params();
            return 0;
        }
        if (argc < 4)
        {
            rt_kprintf("usage: rehab cfg direction|active_min|active_max|active_gain|assist_max|assist_gain|adaptive_enable|adaptive_base|adaptive_load|adaptive_max|adaptive_step|assist_pid_enable|resist_pid_enable|pid_load_low|pid_load_high|pid_speed_low|pid_speed_high|assist_pid_*|resist_pid_*|assist_adrc_*|resist_adrc_*|adrc_beta1|adrc_beta2|adrc_beta3|resist_dir|resist_max|resist_gain <value>\n");
            rehab_shell_print_params();
            return 0;
        }
        ret = rehab_service_get_params(&params);
        if (ret == RT_EOK)
        {
            if (!rehab_shell_apply_cfg(&params, argv[2], (float)atof(argv[3])))
            {
                rt_kprintf("rehab cfg unknown key %s\n", argv[2]);
                return 0;
            }
            ret = rehab_service_set_params(&params);
        }
        rt_kprintf("rehab cfg ret=%d\n", ret);
        rehab_shell_print_params();
        return 0;
    }
    if ((strcmp(argv[1], "passive") == 0) || (strcmp(argv[1], "stop") == 0))
    {
        ret = rehab_service_stop(REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "active") == 0)
    {
        entry = rehab_shell_parse_entry(argc, argv, 2);
        ret = rehab_service_set_mode_on_m33(REHAB_DEMO_MODE_ACTIVE_FOLLOW,
                                            entry.rehab_joint,
                                            entry.m33_joint_id,
                                            REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "assist") == 0)
    {
        entry = rehab_shell_parse_entry(argc, argv, 2);
        ret = rehab_service_set_mode_on_m33(REHAB_DEMO_MODE_ASSIST,
                                            entry.rehab_joint,
                                            entry.m33_joint_id,
                                            REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "resist") == 0)
    {
        entry = rehab_shell_parse_entry(argc, argv, 2);
        ret = rehab_service_set_mode_on_m33(REHAB_DEMO_MODE_RESIST,
                                            entry.rehab_joint,
                                            entry.m33_joint_id,
                                            REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "rec_start") == 0)
    {
        entry = rehab_shell_parse_entry(argc, argv, 2);
        ret = rehab_service_record_start_on_m33(0U,
                                                entry.rehab_joint,
                                                entry.m33_joint_id,
                                                REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "rec_stop") == 0)
    {
        ret = rehab_service_record_stop(REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else if (strcmp(argv[1], "play") == 0)
    {
        entry = rehab_shell_parse_entry(argc, argv, 2);
        ret = rehab_service_play_start_on_m33(0U,
                                              entry.rehab_joint,
                                              entry.m33_joint_id,
                                              REHAB_CMD_SOURCE_BENCH_MSH);
    }
    else
    {
        rehab_shell_usage();
        return 0;
    }

    rt_kprintf("rehab %s ret=%d\n", argv[1], ret);
    rehab_shell_print_status();
    return 0;
}
MSH_CMD_EXPORT(rehab, rehab bench mode command);

#endif
