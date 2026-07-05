from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def require(text, needle, source):
    if needle not in text:
        raise AssertionError(f"{source} missing {needle!r}")


def forbid(text, needle, source):
    if needle in text:
        raise AssertionError(f"{source} must not contain {needle!r}")


def main():
    cfg = read_text("applications/control/control_layer_cfg.h")
    service_h = read_text("applications/control/rehab_service.h")
    service_c = read_text("applications/control/rehab_service.c")
    joint_map_c = read_text("applications/control/rehab_joint_map.c")
    joint_map_h = read_text("applications/control/rehab_joint_map.h")
    traj_c = read_text("applications/control/rehab_trajectory_bank.c")
    active_c = read_text("applications/control/rehab_active_follow.c")
    adaptive_pid_c = read_text("applications/control/rehab_adaptive_pid.c")
    adaptive_pid_h = read_text("applications/control/rehab_adaptive_pid.h")
    adrc_c = read_text("applications/control/rehab_adrc.c")
    adrc_h = read_text("applications/control/rehab_adrc.h")
    assist_c = read_text("applications/control/rehab_assist_strategy.c")
    resist_c = read_text("applications/control/rehab_resist_strategy.c")
    strategy_h = read_text("applications/control/rehab_strategy.h")
    shell_c = read_text("applications/control/rehab_shell.c")
    manager_h = read_text("applications/control/rehab_mode_manager.h")
    manager_c = read_text("applications/control/rehab_mode_manager.c")
    control_h = read_text("applications/control/control_layer.h")
    control_c = read_text("applications/control/control_layer.c")
    sensor_c = read_text("applications/control/sensor.c")

    for needle in (
        "#define CONTROL_REHAB_SERVICE_PERIOD_MS 20U",
        "#define CONTROL_REHAB_FEEDBACK_FRESH_MS 100U",
        "#define CONTROL_REHAB_DEFAULT_M33_JOINT 5U",
        "#define CONTROL_MOTOR_CURRENT_CONTROL_MAX_A",
        "#define CONTROL_REHAB_FOLLOW_DIRECTION",
        "#define CONTROL_REHAB_ACTIVE_GAIN_A_PER_NM",
        "#define CONTROL_REHAB_ASSIST_GAIN_A_PER_NM",
        "#define CONTROL_REHAB_ASSIST_ADAPTIVE_LOAD_GAIN_A_PER_NM2",
        "#define CONTROL_REHAB_ASSIST_ADAPTIVE_GAIN_STEP_A_PER_NM",
        "#define CONTROL_REHAB_PID_LOAD_LOW_NM",
        "#define CONTROL_REHAB_PID_SPEED_HIGH_RAD_S",
        "#define CONTROL_REHAB_ASSIST_PID_ENABLE",
        "#define CONTROL_REHAB_ASSIST_PID_KP_LOAD",
        "#define CONTROL_REHAB_ASSIST_PID_KD_SPEED",
        "#define CONTROL_REHAB_RESIST_PID_ENABLE",
        "#define CONTROL_REHAB_RESIST_PID_KP_SPEED",
        "#define CONTROL_REHAB_RESIST_PID_KD_SPEED",
        "#define CONTROL_REHAB_ASSIST_ADRC_ENABLE",
        "#define CONTROL_REHAB_RESIST_ADRC_ENABLE",
        "#define CONTROL_REHAB_ASSIST_ADRC_B0",
        "#define CONTROL_REHAB_RESIST_ADRC_B0",
        "#define CONTROL_REHAB_ADRC_BETA1",
        "#define CONTROL_REHAB_ADRC_BETA2",
        "#define CONTROL_REHAB_ADRC_BETA3",
        "#define CONTROL_REHAB_ASSIST_ADRC_TRIM_LIMIT_A",
        "#define CONTROL_REHAB_RESIST_ADRC_TRIM_LIMIT_A",
        "#define CONTROL_REHAB_RESIST_CURRENT_GAIN_A_PER_RAD_S",
        "#define CONTROL_REHAB_TRAJECTORY_MAX_SAMPLES",
    ):
        require(cfg, needle, "control_layer_cfg.h")

    for needle in (
        "REHAB_DEMO_MODE_PASSIVE = 0",
        "REHAB_DEMO_MODE_ACTIVE_FOLLOW",
        "REHAB_DEMO_MODE_ASSIST",
        "REHAB_DEMO_MODE_RESIST",
        "REHAB_DEMO_MODE_MEMORY_RECORD",
        "REHAB_DEMO_MODE_MEMORY_PLAYBACK",
        "REHAB_CMD_SOURCE_BENCH_MSH = 0",
        "REHAB_CMD_SOURCE_CAN",
        "rehab_service_set_mode",
        "rehab_service_record_start",
        "rehab_service_play_start",
        "rehab_service_set_mode_on_m33",
        "rehab_service_get_params",
        "rehab_service_set_params",
        "rehab_service_accepts_ros_target",
        "feedback_torque_nm",
        "feedback_vel_rad_s",
        "output_current_a",
        "effective_gain",
        "pid_kp",
        "pid_ki",
        "pid_kd",
        "pid_load_level",
        "pid_speed_level",
        "pid_trim_current_a",
        "output_saturated",
    ):
        require(service_h, needle, "rehab_service.h")

    for needle in (
        "adaptive_assist_enabled",
        "adaptive_assist_base_gain_a_per_nm",
        "adaptive_assist_load_gain_a_per_nm2",
        "adaptive_assist_max_gain_a_per_nm",
        "adaptive_assist_gain_step_a_per_nm",
        "assist_adaptive_pid_enabled",
        "resist_adaptive_pid_enabled",
        "adaptive_pid_load_low_nm",
        "adaptive_pid_load_high_nm",
        "adaptive_pid_speed_low_rad_s",
        "adaptive_pid_speed_high_rad_s",
        "rehab_adaptive_pid_profile_t",
        "rehab_adrc_profile_t",
        "float target",
        "float kp_load",
        "float kd_speed",
        "assist_pid",
        "resist_pid",
        "assist_adrc_enabled",
        "resist_adrc_enabled",
        "assist_adrc",
        "resist_adrc",
        "adrc_z1",
        "adrc_z2",
        "adrc_z3",
        "adrc_trim_current_a",
    ):
        require(strategy_h, needle, "rehab_strategy.h")

    for needle in (
        "rehab_adaptive_pid_reset",
        "rehab_adaptive_pid_step",
        "rehab_adaptive_pid_observation_t",
        "load_level",
        "speed_level",
        "kp_eff",
        "ki_eff",
        "kd_eff",
        "integral_limit",
        "trim_limit",
    ):
        require(adaptive_pid_h + adaptive_pid_c, needle, "rehab_adaptive_pid")

    for needle in (
        "rehab_adrc_reset",
        "rehab_adrc_step",
        "rehab_adrc_state_t",
        "rehab_adrc_observation_t",
        "float z1",
        "float z2",
        "float z3",
        "last_trim",
        "beta1",
        "beta2",
        "beta3",
        "disturbance_gain",
        "trim_limit",
    ):
        require(adrc_h + adrc_c, needle, "rehab_adrc")

    for needle in (
        "control_get_motor_feedback",
        "control_motor_current_control",
        "control_motor_position_control",
        "control_motor_stop",
        "control_motor_is_joint_calibrated",
        "rehab_active_follow_step",
        "rehab_assist_strategy_step",
        "rehab_resist_strategy_step",
        "rehab_trajectory_bank_append",
        "rehab_strategy_params_t",
        "s_rehab.params",
        "s_rehab.status.feedback_torque_nm",
        "s_rehab.status.output_current_a",
        "s_rehab.status.effective_gain",
        "s_rehab.status.pid_kp",
        "s_rehab.status.pid_load_level",
        "s_rehab.status.pid_trim_current_a",
        "s_rehab.status.adrc_z1",
        "s_rehab.status.adrc_z2",
        "s_rehab.status.adrc_z3",
        "s_rehab.status.adrc_trim_current_a",
        "s_rehab.status.output_saturated",
        "rehab_resist_strategy_reset(&s_rehab.resist_state)",
        "CONTROL_MOTOR_CURRENT_CONTROL_MAX_A",
        "stopped_for_fault = s_rehab.stopped_for_fault",
        "if (stopped_for_fault)",
    ):
        require(service_c, needle, "rehab_service.c")

    require(joint_map_c, "CONTROL_REHAB_DEFAULT_M33_JOINT", "rehab_joint_map.c")
    require(joint_map_c, "REHAB_JOINT_ELBOW", "rehab_joint_map.c")
    require(joint_map_h, "rehab_joint_map_parse_entry", "rehab_joint_map.h")
    require(joint_map_c, "m33:", "rehab_joint_map.c")
    require(joint_map_c, "motor", "rehab_joint_map.c")
    require(traj_c, "if (slot != 0U)", "rehab_trajectory_bank.c")
    require(service_c, "REHAB_STRATEGY_OUTPUT_CURRENT", "rehab_service.c")
    forbid(service_c, "control_motor_speed_control", "rehab_service.c")
    require(active_c, "CONTROL_REHAB_ACTIVE_TORQUE_DEADBAND_NM", "rehab_active_follow.c")
    require(active_c, "REHAB_STRATEGY_OUTPUT_CURRENT", "rehab_active_follow.c")
    require(active_c, "params->active_current_gain_a_per_nm", "rehab_active_follow.c")
    require(active_c, "params->follow_direction", "rehab_active_follow.c")
    require(active_c, "out->effective_gain", "rehab_active_follow.c")
    require(active_c, "out->current_saturated", "rehab_active_follow.c")
    require(assist_c, "CONTROL_REHAB_ASSIST_TORQUE_ENTER_NM", "rehab_assist_strategy.c")
    require(assist_c, "CONTROL_REHAB_ASSIST_TORQUE_EXIT_NM", "rehab_assist_strategy.c")
    require(assist_c, "REHAB_STRATEGY_OUTPUT_CURRENT", "rehab_assist_strategy.c")
    require(assist_c, "params->assist_current_gain_a_per_nm", "rehab_assist_strategy.c")
    require(assist_c, "params->adaptive_assist_enabled", "rehab_assist_strategy.c")
    require(assist_c, "adaptive_gain", "rehab_assist_strategy.c")
    require(assist_c, "adaptive_assist_load_gain_a_per_nm2", "rehab_assist_strategy.c")
    require(assist_c, "adaptive_assist_gain_step_a_per_nm", "rehab_assist_strategy.c")
    require(assist_c, "params->assist_adaptive_pid_enabled", "rehab_assist_strategy.c")
    require(assist_c, "rehab_adaptive_pid_step", "rehab_assist_strategy.c")
    require(assist_c, "params->assist_pid", "rehab_assist_strategy.c")
    require(assist_c, "params->assist_adrc_enabled", "rehab_assist_strategy.c")
    require(assist_c, "rehab_adrc_step", "rehab_assist_strategy.c")
    require(assist_c, "params->assist_adrc", "rehab_assist_strategy.c")
    require(assist_c, "out->effective_gain", "rehab_assist_strategy.c")
    require(assist_c, "out->pid_kp", "rehab_assist_strategy.c")
    require(assist_c, "out->pid_trim_current_a", "rehab_assist_strategy.c")
    require(assist_c, "out->adrc_trim_current_a", "rehab_assist_strategy.c")
    require(assist_c, "out->current_saturated", "rehab_assist_strategy.c")
    require(resist_c, "REHAB_STRATEGY_OUTPUT_CURRENT", "rehab_resist_strategy.c")
    require(resist_c, "params->resist_current_gain_a_per_rad_s", "rehab_resist_strategy.c")
    require(resist_c, "params->resist_adaptive_pid_enabled", "rehab_resist_strategy.c")
    require(resist_c, "rehab_adaptive_pid_step", "rehab_resist_strategy.c")
    require(resist_c, "params->resist_pid", "rehab_resist_strategy.c")
    require(resist_c, "params->resist_adrc_enabled", "rehab_resist_strategy.c")
    require(resist_c, "rehab_adrc_step", "rehab_resist_strategy.c")
    require(resist_c, "params->resist_adrc", "rehab_resist_strategy.c")
    require(resist_c, "out->effective_gain", "rehab_resist_strategy.c")
    require(resist_c, "out->pid_kp", "rehab_resist_strategy.c")
    require(resist_c, "out->pid_trim_current_a", "rehab_resist_strategy.c")
    require(resist_c, "out->adrc_trim_current_a", "rehab_resist_strategy.c")
    require(resist_c, "out->current_saturated", "rehab_resist_strategy.c")

    require(shell_c, "MSH_CMD_EXPORT(rehab", "rehab_shell.c")
    require(shell_c, "REHAB_CMD_SOURCE_BENCH_MSH", "rehab_shell.c")
    require(shell_c, "rehab_service_get_params", "rehab_shell.c")
    require(shell_c, "rehab_service_set_params", "rehab_shell.c")
    require(shell_c, "rehab_joint_map_parse_entry", "rehab_shell.c")
    require(shell_c, "torque_x1000", "rehab_shell.c")
    require(shell_c, "vel_x1000", "rehab_shell.c")
    require(shell_c, "current_x1000", "rehab_shell.c")
    require(shell_c, "gain_x1000", "rehab_shell.c")
    require(shell_c, "pid_kp_x1000", "rehab_shell.c")
    require(shell_c, "pid_load_x1000", "rehab_shell.c")
    require(shell_c, "pid_trim_x1000", "rehab_shell.c")
    require(shell_c, "adrc_z1_x1000", "rehab_shell.c")
    require(shell_c, "adrc_trim_x1000", "rehab_shell.c")
    require(shell_c, "sat=%u", "rehab_shell.c")
    require(shell_c, "adaptive=%u", "rehab_shell.c")
    require(shell_c, "assist_pid=%u", "rehab_shell.c")
    require(shell_c, "resist_pid=%u", "rehab_shell.c")
    require(shell_c, "assist_adrc=%u", "rehab_shell.c")
    require(shell_c, "resist_adrc=%u", "rehab_shell.c")
    require(shell_c, "adaptive_enable", "rehab_shell.c")
    require(shell_c, "adaptive_base", "rehab_shell.c")
    require(shell_c, "adaptive_load", "rehab_shell.c")
    require(shell_c, "adaptive_max", "rehab_shell.c")
    require(shell_c, "adaptive_step", "rehab_shell.c")
    require(shell_c, "assist_pid_enable", "rehab_shell.c")
    require(shell_c, "assist_pid_kp_load", "rehab_shell.c")
    require(shell_c, "assist_pid_kd_speed", "rehab_shell.c")
    require(shell_c, "resist_pid_enable", "rehab_shell.c")
    require(shell_c, "resist_pid_kp_speed", "rehab_shell.c")
    require(shell_c, "resist_pid_kd_speed", "rehab_shell.c")
    require(shell_c, "assist_adrc_enable", "rehab_shell.c")
    require(shell_c, "resist_adrc_enable", "rehab_shell.c")
    require(shell_c, "assist_adrc_b0", "rehab_shell.c")
    require(shell_c, "resist_adrc_b0", "rehab_shell.c")
    require(shell_c, "adrc_beta1", "rehab_shell.c")
    require(shell_c, "adrc_beta2", "rehab_shell.c")
    require(shell_c, "adrc_beta3", "rehab_shell.c")
    require(shell_c, "assist_adrc_trim", "rehab_shell.c")
    require(shell_c, "resist_adrc_trim", "rehab_shell.c")
    forbid(shell_c, "CONTROL_REHAB_ASSIST_LIMIT_CUR_A", "rehab_shell.c")

    for needle in (
        "rehab_mode_manager_init",
        "rehab_mode_manager_apply_command",
        "rehab_mode_manager_note_heartbeat",
        "rehab_mode_manager_accepts_ros_target",
        "rehab_mode_manager_get_status",
    ):
        require(manager_h, needle, "rehab_mode_manager.h")

    require(manager_c, "rehab_service_set_mode", "rehab_mode_manager.c")
    require(manager_c, "REHAB_CMD_SOURCE_CAN", "rehab_mode_manager.c")
    require(manager_c, "CONTROL_REHAB_MODE_CMD_MARKER", "rehab_mode_manager.c")
    forbid(manager_c, "control_motor_speed_control", "rehab_mode_manager.c")
    forbid(manager_c, "control_motor_position_control", "rehab_mode_manager.c")
    forbid(manager_c, "control_get_motor_feedback", "rehab_mode_manager.c")

    require(control_h, "control_motor_is_joint_calibrated", "control_layer.h")
    require(control_h, "control_motor_current_control", "control_layer.h")
    require(control_c, "rehab_service_init", "control_layer.c")
    require(control_c, "rehab_mode_manager_init", "control_layer.c")
    require(control_c, "MOTOR_PARAM_INDEX_IQ_REF", "control_layer.c")
    require(control_c, "cmd_motor_current_hold", "control_layer.c")
    require(control_c, "cmd_motor_report", "control_layer.c")
    require(control_c, "current_a > CONTROL_MOTOR_CURRENT_CONTROL_MAX_A", "control_layer.c")
    require(control_c, "(s_speed_hold_thread != RT_NULL) || (s_current_hold_thread != RT_NULL)", "control_layer.c")

    emg_stream_cmd = control_c[
        control_c.index("static int cmd_emg_motor_stream"):
        control_c.index("MSH_CMD_EXPORT(cmd_emg_motor_stream")
    ]
    require(
        emg_stream_cmd,
        "control_layer_init(CONTROL_CAN_DEV_DEFAULT)",
        "cmd_emg_motor_stream",
    )
    require(
        emg_stream_cmd,
        "emg_motor_stream init failed ret=%d",
        "cmd_emg_motor_stream",
    )
    require(control_c, "sensor_node.adc_raw[3]", "control_layer.c")

    require(sensor_c, "static rt_uint8_t s_f103_sensor_seq = 0U;", "sensor.c")
    require(sensor_c, "node.adc_raw[3] = adc3;", "sensor.c")
    require(sensor_c, "node.emg3_raw[0] = node.adc_raw[0];", "sensor.c")
    require(sensor_c, "node.emg3_raw[1] = node.adc_raw[1];", "sensor.c")
    require(sensor_c, "node.emg3_raw[2] = node.adc_raw[2];", "sensor.c")
    require(sensor_c, "node.emg3_flags = 0U;", "sensor.c")
    require(sensor_c, "node.emg3_seq = s_f103_sensor_seq++;", "sensor.c")
    forbid(sensor_c, "node.emg3_flags = msg->data[6];", "sensor.c")
    forbid(sensor_c, "node.emg3_seq = msg->data[7];", "sensor.c")


if __name__ == "__main__":
    main()
