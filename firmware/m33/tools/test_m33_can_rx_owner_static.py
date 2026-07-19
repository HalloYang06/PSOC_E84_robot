from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "applications" / "main.c"
CONTROL_C = ROOT / "applications" / "control" / "control_layer.c"
CONTROL_CFG = ROOT / "applications" / "control" / "control_layer_cfg.h"


def macro_u1(text, name):
    match = re.search(
        rf"^\s*#define\s+{re.escape(name)}\s+([01])U?\s*$",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing 0/1 macro {name}")
    return int(match.group(1))


def function_body(text, signature, next_signature):
    start = text.index(signature)
    end = text.index(next_signature, start)
    return text[start:end]


class M33CanRxOwnerStaticTest(unittest.TestCase):
    def setUp(self):
        self.main_c = MAIN_C.read_text(encoding="utf-8")
        self.control_c = CONTROL_C.read_text(encoding="utf-8")
        self.control_cfg = CONTROL_CFG.read_text(encoding="utf-8")

    def test_selected_framework_has_a_can_rx_owner(self):
        minimal = macro_u1(self.main_c, "M33_XIAOZHI_MINIMAL_FRAMEWORK")
        rx_thread = macro_u1(self.control_cfg, "CONTROL_CAN_RX_THREAD_ENABLE")

        if minimal == 0:
            self.assertEqual(
                rx_thread,
                1,
                "full framework requires the control-layer CAN RX thread",
            )
        else:
            main_start = self.main_c.index("int main(void)")
            minimal_start = self.main_c.index(
                "#if M33_XIAOZHI_MINIMAL_FRAMEWORK", main_start
            )
            full_start = self.main_c.index('[m33] framework ok', minimal_start)
            minimal_block = self.main_c[minimal_start:full_start]
            self.assertTrue(
                (rx_thread == 1) or ("control_layer_poll_once();" in minimal_block),
                "minimal framework requires either the RX thread or control poll",
            )

    def test_background_rx_owner_prevents_manual_fifo_drain(self):
        self.assertEqual(
            macro_u1(self.control_cfg, "CONTROL_CAN_RX_THREAD_ENABLE"), 1
        )
        body = function_body(
            self.control_c,
            "void control_layer_poll_once(void)",
            "static rt_err_t ctrl_apply_rehab_mode_command",
        )
        guard = body.index("s_can_rx_thread != RT_NULL")
        drain = body.index("ctrl_poll_can_messages();")

        self.assertLess(guard, drain)
        self.assertIn("return;", body[guard:drain])

    def test_ros_command_consumer_is_enabled_with_queue_producer(self):
        self.assertEqual(
            macro_u1(self.control_cfg, "CONTROL_ROS_CMD_THREAD_ENABLE"), 1
        )
        self.assertIn("rt_mq_send(&s_ros_cmd_mq", self.control_c)
        self.assertRegex(
            self.control_c,
            r"RT_MQ_BUF_SIZE\(\s*sizeof\(control_ros_command_t\),\s*"
            r"CONTROL_ROS_CMD_QUEUE_DEPTH\s*\)",
        )

    def test_can_rx_only_assesses_and_enqueues_ros_commands(self):
        body = function_body(
            self.control_c,
            "static void ctrl_handle_can_message",
            "static void ctrl_poll_can_messages",
        )
        self.assertIn("ctrl_enqueue_ros_command(&ros_cmd)", body)
        self.assertNotIn("ctrl_apply_ros_command(&ros_cmd)", body)

    def test_emergency_commands_use_an_independent_latch(self):
        self.assertIn("control_ros_emergency_latch_stop", self.control_c)
        self.assertIn("control_ros_emergency_latch_passive", self.control_c)
        self.assertIn("control_ros_emergency_take", self.control_c)
        self.assertNotIn("rt_mq_urgent(&s_ros_cmd_mq", self.control_c)
        self.assertNotIn(
            "rt_mq_control(&s_ros_cmd_mq, RT_IPC_CMD_RESET, RT_NULL)",
            self.control_c,
        )

    def test_ros_consumer_rechecks_safety_and_command_age(self):
        body = function_body(
            self.control_c,
            "static void ctrl_ros_cmd_entry",
            "int control_layer_init",
        )
        self.assertIn("ctrl_ros_command_is_stale(&cmd", body)
        self.assertIn("ctrl_assess_ros_command_safety(&cmd, &assessment)", body)
        self.assertLess(
            body.index("ctrl_assess_ros_command_safety(&cmd, &assessment)"),
            body.index("ctrl_apply_ros_command(&cmd)"),
        )
        self.assertIn("control_ros_command_t deferred_normal", body)
        self.assertIn("normal_pending = RT_TRUE", body)
        self.assertIn("cmd = deferred_normal", body)

    def test_ros_consumer_accepts_rt_mq_recv_message_length(self):
        body = function_body(
            self.control_c,
            "static void ctrl_ros_cmd_entry",
            "int control_layer_init",
        )
        self.assertIn("rt_ssize_t recv_size", body)
        self.assertIn("recv_size = rt_mq_recv(&s_ros_cmd_mq", body)
        self.assertIn(
            "recv_size != (rt_ssize_t)sizeof(deferred_normal)",
            body,
        )
        self.assertNotIn(
            "rt_mq_recv(&s_ros_cmd_mq,\n"
            "                           &deferred_normal,\n"
            "                           sizeof(deferred_normal),\n"
            "                           rt_tick_from_millisecond(CONTROL_ROS_EMERGENCY_POLL_MS)) != RT_EOK",
            body,
        )


if __name__ == "__main__":
    unittest.main()
