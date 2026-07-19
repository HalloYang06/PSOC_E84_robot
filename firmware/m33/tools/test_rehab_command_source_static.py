from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_C = (ROOT / "applications" / "control" / "control_layer.c").read_text(encoding="utf-8")
MANAGER_C = (ROOT / "applications" / "control" / "rehab_mode_manager.c").read_text(encoding="utf-8")
MANAGER_H = (ROOT / "applications" / "control" / "rehab_mode_manager.h").read_text(encoding="utf-8")
SERVICE_C = (ROOT / "applications" / "control" / "rehab_service.c").read_text(encoding="utf-8")
SERVICE_H = (ROOT / "applications" / "control" / "rehab_service.h").read_text(encoding="utf-8")
SHELL_C = (ROOT / "applications" / "control" / "rehab_shell.c").read_text(encoding="utf-8")


def body(text, start_marker, end_marker):
    start = text.index(start_marker)
    return text[start:text.index(end_marker, start)]


class RehabCommandSourceStaticTest(unittest.TestCase):
    def test_app_ble_source_is_appended_without_renumbering_existing_sources(self):
        self.assertRegex(
            SERVICE_H,
            r"typedef enum\s*\{\s*"
            r"REHAB_CMD_SOURCE_BENCH_MSH\s*=\s*0\s*,\s*"
            r"REHAB_CMD_SOURCE_CAN\s*,\s*"
            r"REHAB_CMD_SOURCE_VOICE\s*,\s*"
            r"REHAB_CMD_SOURCE_APP_BLE\s*,\s*"
            r"\}\s*rehab_cmd_source_t\s*;",
        )

    def test_voice_is_distinct_and_command_source_is_explicit(self):
        self.assertIn("REHAB_CMD_SOURCE_VOICE", SERVICE_H)
        command = body(MANAGER_H, "typedef struct\n{\n    rehab_mode_t mode;", "} rehab_mode_command_t;")
        self.assertIn("rehab_cmd_source_t source;", command)

    def test_can_decoder_keeps_can_source(self):
        apply_can = body(CONTROL_C, "static rt_err_t ctrl_apply_rehab_mode_command", "static rt_err_t ctrl_apply_ros_command")
        self.assertIn("mode_cmd.source = REHAB_CMD_SOURCE_CAN;", apply_can)

    def test_manager_rejects_default_and_unknown_sources(self):
        apply_command = body(MANAGER_C, "rt_err_t rehab_mode_manager_apply_command", "void rehab_mode_manager_record_reject")
        self.assertIn("rehab_mode_adapter_source_supported(cmd->source)", apply_command)
        self.assertIn("return -RT_EINVAL;", apply_command)

    def test_manager_propagates_voice_without_hardcoded_can_calls(self):
        apply_command = body(MANAGER_C, "rt_err_t rehab_mode_manager_apply_command", "void rehab_mode_manager_record_reject")
        self.assertIn("rehab_service_stop(cmd->source)", apply_command)
        self.assertIn("rehab_service_record_start(0U, REHAB_JOINT_ELBOW, cmd->source)", apply_command)
        self.assertIn("rehab_service_play_start(0U, REHAB_JOINT_ELBOW, cmd->source)", apply_command)
        self.assertIn("rehab_service_set_mode_mask(service_mode, joint_mask, cmd->source)", apply_command)

    def test_command_lock_serializes_apply_and_timeout_stop(self):
        self.assertIn("struct rt_mutex command_lock;", MANAGER_C)
        self.assertIn(
            'rt_mutex_init(&s_rehab_adapter.command_lock, "rehabcmd", RT_IPC_FLAG_PRIO)',
            MANAGER_C,
        )
        apply_command = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_apply_command",
            "void rehab_mode_manager_record_reject",
        )
        tick = body(
            MANAGER_C,
            "void rehab_mode_manager_tick",
            "rt_bool_t rehab_mode_manager_accepts_ros_target",
        )
        apply_take = apply_command.index(
            "rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER)"
        )
        self.assertLess(apply_take, apply_command.index("rehab_service_stop(cmd->source)"))
        self.assertLess(apply_take, apply_command.index("rehab_can_lease_note_mode"))
        tick_take = tick.index(
            "rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER)"
        )
        self.assertLess(tick_take, tick.index("rehab_can_lease_claim_stop"))
        self.assertLess(tick.index("rehab_service_stop_if_owned"), tick.index("rehab_can_lease_note_stop_result"))

    def test_manager_initializes_service_before_publishing_ready(self):
        init = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_init",
            "rt_err_t rehab_mode_manager_apply_command",
        )
        self.assertLess(
            init.index("ret = rehab_service_init()"),
            init.index("s_rehab_adapter.initialized = RT_TRUE"),
        )
        self.assertIn("rt_mutex_detach(&s_rehab_adapter.command_lock)", init)
        self.assertIn("rt_mutex_detach(&s_rehab_adapter.lock)", init)

    def test_service_calls_do_not_hold_adapter_lock(self):
        for function in (
            body(
                MANAGER_C,
                "rt_err_t rehab_mode_manager_apply_command",
                "void rehab_mode_manager_record_reject",
            ),
            body(
                MANAGER_C,
                "void rehab_mode_manager_tick",
                "rt_bool_t rehab_mode_manager_accepts_ros_target",
            ),
        ):
            lock_ops = [
                (match.start(), match.group(1))
                for match in re.finditer(
                    r"rt_mutex_(take|release)\(&s_rehab_adapter\.lock",
                    function,
                )
            ]
            for call in re.finditer(r"rehab_service_[a-z_]+\(", function):
                prior_ops = [op for pos, op in lock_ops if pos < call.start()]
                if prior_ops:
                    self.assertEqual(prior_ops[-1], "release")

    def test_conditioned_stop_accepts_app_ble_and_matches_owner(self):
        stop = body(SERVICE_C, "rt_err_t rehab_service_stop_if_owned", "rt_err_t rehab_service_record_start")
        self.assertIn("expected_source != REHAB_CMD_SOURCE_CAN", stop)
        self.assertIn("expected_source != REHAB_CMD_SOURCE_VOICE", stop)
        self.assertIn("expected_source != REHAB_CMD_SOURCE_APP_BLE", stop)
        self.assertRegex(
            stop,
            r"expected_source != REHAB_CMD_SOURCE_CAN\)\s*&&\s*"
            r"\(expected_source != REHAB_CMD_SOURCE_VOICE\)\s*&&\s*"
            r"\(expected_source != REHAB_CMD_SOURCE_APP_BLE\)",
        )
        self.assertIn("s_rehab.status.source != expected_source", stop)
        self.assertIn("s_rehab.status.mode_generation != expected_generation", stop)
        self.assertNotIn("expected_source != REHAB_CMD_SOURCE_BENCH_MSH", stop)

    def test_service_exposes_generation_guarded_mode_switch(self):
        self.assertIn("rehab_service_set_mode_mask_if_unchanged", SERVICE_H)
        guarded = body(
            SERVICE_C,
            "rt_err_t rehab_service_set_mode_mask_if_unchanged",
            "rt_err_t rehab_service_set_mode_on_m33",
        )
        self.assertIn("expected_source", guarded)
        self.assertIn("expected_generation", guarded)
        self.assertIn("rehab_service_set_mode_mask_internal", guarded)
        internal = body(
            SERVICE_C,
            "static rt_err_t rehab_service_set_mode_mask_internal",
            "rt_err_t rehab_service_set_mode_mask(",
        )
        self.assertGreaterEqual(
            internal.count("s_rehab.status.source != expected_source"), 3
        )
        self.assertGreaterEqual(
            internal.count("s_rehab.status.mode_generation != expected_generation"), 3
        )
        self.assertLess(
            internal.index("rt_mutex_take(&s_rehab.actuation_lock"),
            internal.index("s_rehab.status.source != expected_source"),
        )
        self.assertLess(
            internal.index("rt_mutex_take(&s_rehab.lock"),
            internal.index("s_rehab.status.source != expected_source"),
        )
        self.assertLess(
            internal.index("s_rehab.status.source != expected_source"),
            internal.index("rehab_service_prepare_feedback_mask"),
        )
        self.assertLess(
            internal.rindex("s_rehab.status.mode_generation != expected_generation"),
            internal.index("rehab_service_apply_status_locked"),
        )
        regular = body(
            SERVICE_C,
            "rt_err_t rehab_service_set_mode_mask(",
            "rt_err_t rehab_service_set_mode_mask_if_unchanged",
        )
        self.assertIn("RT_FALSE", regular)

    def test_timeout_uses_leased_owner_source_and_shell_stays_bench(self):
        tick = body(MANAGER_C, "void rehab_mode_manager_tick", "rt_bool_t rehab_mode_manager_accepts_ros_target")
        self.assertIn("expected_source", tick)
        self.assertIn("rehab_service_stop_if_owned(expected_source", tick)
        self.assertIn("REHAB_CMD_SOURCE_BENCH_MSH", SHELL_C)
        self.assertNotIn("REHAB_CMD_SOURCE_VOICE", SHELL_C)


if __name__ == "__main__":
    unittest.main()
