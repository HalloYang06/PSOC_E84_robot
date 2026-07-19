from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_C = ROOT / "applications" / "control" / "control_layer.c"
SERVICE_C = ROOT / "applications" / "control" / "rehab_service.c"
SERVICE_H = ROOT / "applications" / "control" / "rehab_service.h"
MANAGER_C = ROOT / "applications" / "control" / "rehab_mode_manager.c"


def function_body(text, signature, next_signature):
    start = text.index(signature)
    end = text.index(next_signature, start)
    return text[start:end]


class M33RosRehabOwnerStaticTest(unittest.TestCase):
    def setUp(self):
        self.control_c = CONTROL_C.read_text(encoding="utf-8")
        self.service_c = SERVICE_C.read_text(encoding="utf-8")
        self.service_h = SERVICE_H.read_text(encoding="utf-8")
        self.manager_c = MANAGER_C.read_text(encoding="utf-8")

    def test_ros_targets_are_owned_only_in_passive_mode(self):
        service_body = function_body(
            self.service_c,
            "rt_bool_t rehab_service_accepts_ros_target(void)",
            "\n}",
        )
        self.assertIn("status.mode == REHAB_DEMO_MODE_PASSIVE", service_body)
        self.assertRegex(self.service_h, r"REHAB_DEMO_MODE_ASSIST\s*(?:=\s*\d+)?\s*,")
        self.assertRegex(self.service_h, r"REHAB_DEMO_MODE_RESIST\s*(?:=\s*\d+)?\s*,")

        manager_body = function_body(
            self.manager_c,
            "rt_bool_t rehab_mode_manager_accepts_ros_target(void)",
            "rt_bool_t rehab_mode_manager_accepts_ros_stop(void)",
        )
        self.assertIn("return rehab_service_accepts_ros_target();", manager_body)

    def test_stop_and_mode_commands_bypass_target_owner_gate(self):
        body = function_body(
            self.control_c,
            "static void ctrl_assess_ros_command_safety",
            "#if CONTROL_ROS_COMMAND_LOGGING_ONLY",
        )
        owner_gate = body.index("rehab_mode_manager_accepts_ros_target()")
        self.assertLess(body.index("cmd->command == CONTROL_ROS_CMD_STOP"), owner_gate)
        self.assertLess(body.index("cmd->command == CONTROL_ROS_CMD_SET_MODE"), owner_gate)
        self.assertLess(body.index("cmd->command != CONTROL_ROS_CMD_SET_TARGET"), owner_gate)

    def test_target_owner_rejection_records_diagnostic(self):
        body = function_body(
            self.control_c,
            "static void ctrl_assess_ros_command_safety",
            "#if CONTROL_ROS_COMMAND_LOGGING_ONLY",
        )
        gate = body.index("if (!rehab_mode_manager_accepts_ros_target())")
        rejection = body[gate:body.index("if (!assessment->joint_known)", gate)]
        self.assertIn("CONTROL_ROS_REJECT_UNSUPPORTED_CMD", rejection)
        self.assertIn("CONTROL_ROS_DECISION_REJECT", rejection)
        self.assertIn("rehab_mode_manager_record_reject(", rejection)

    def test_can_admission_and_consumer_both_assess_current_owner(self):
        rx_body = function_body(
            self.control_c,
            "static void ctrl_handle_can_message",
            "static void ctrl_poll_can_messages",
        )
        consumer_body = function_body(
            self.control_c,
            "static void ctrl_ros_cmd_entry",
            "int control_layer_init",
        )
        self.assertIn("ctrl_assess_ros_command_safety(&ros_cmd, &assessment)", rx_body)
        self.assertIn("ctrl_assess_ros_command_safety(&cmd, &assessment)", consumer_body)
        self.assertLess(
            consumer_body.index("ctrl_assess_ros_command_safety(&cmd, &assessment)"),
            consumer_body.index("ctrl_apply_ros_command(&cmd)"),
        )

    def test_final_set_target_apply_has_owner_defense(self):
        body = function_body(
            self.control_c,
            "static rt_err_t ctrl_apply_ros_command",
            "static void ctrl_ros_cmd_entry",
        )
        case = body[body.index("case CONTROL_ROS_CMD_SET_TARGET:") :]
        self.assertLess(
            case.index("rehab_mode_manager_accepts_ros_target()"),
            case.index("control_joint_motor_set_target("),
        )


if __name__ == "__main__":
    unittest.main()
