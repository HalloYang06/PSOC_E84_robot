from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_C = (ROOT / "applications" / "control" / "control_layer.c").read_text(encoding="utf-8")
SERVICE_C = (ROOT / "applications" / "control" / "rehab_service.c").read_text(encoding="utf-8")
SERVICE_H = (ROOT / "applications" / "control" / "rehab_service.h").read_text(encoding="utf-8")
MANAGER_C = (ROOT / "applications" / "control" / "rehab_mode_manager.c").read_text(encoding="utf-8")


def function_body(text, signature, next_signature):
    start = text.index(signature)
    end = text.index(next_signature, start)
    return text[start:end]


class RehabCanLeaseStaticTest(unittest.TestCase):
    def test_service_exposes_generation_conditioned_stop(self):
        self.assertIn("rt_uint32_t mode_generation", SERVICE_H)
        self.assertIn("rehab_service_stop_if_owned", SERVICE_H)
        body = function_body(
            SERVICE_C,
            "rt_err_t rehab_service_stop_if_owned",
            "rt_err_t rehab_service_record_start",
        )
        self.assertIn("expected_generation", body)
        self.assertIn("REHAB_CMD_SOURCE_CAN", body)
        self.assertIn("rehab_service_stop_joint_mask", body)
        self.assertIn("stop_pending", body)

    def test_worker_output_is_generation_guarded(self):
        self.assertIn("struct rt_mutex actuation_lock", SERVICE_C)
        body = function_body(
            SERVICE_C,
            "static rt_err_t rehab_service_apply_strategy_output",
            "static void rehab_service_worker",
        )
        self.assertIn("expected_generation", body)
        self.assertIn("s_rehab.status.mode_generation != expected_generation", body)
        self.assertIn("s_rehab.stop_pending", body)
        self.assertIn("rt_mutex_take(&s_rehab.actuation_lock", body)

    def test_regular_stop_updates_passive_only_after_motor_stop(self):
        body = function_body(
            SERVICE_C,
            "rt_err_t rehab_service_stop(",
            "rt_err_t rehab_service_stop_if_owned",
        )
        self.assertLess(
            body.index("rehab_service_stop_joint_mask"),
            body.index("rehab_service_apply_status_locked"),
        )

    def test_manager_uses_lease_and_retries_conditioned_stop(self):
        self.assertIn("rehab_can_lease_claim_stop", MANAGER_C)
        self.assertIn("rehab_service_stop_if_owned", MANAGER_C)
        self.assertIn("rehab_can_lease_note_stop_result", MANAGER_C)
        self.assertIn("rehab_mode_adapter_lease_supervised", MANAGER_C)

    def test_tick_runs_in_consumer_not_can_rx_dispatch(self):
        worker = function_body(
            CONTROL_C,
            "static void ctrl_ros_cmd_entry",
            "int control_layer_init",
        )
        rx = function_body(
            CONTROL_C,
            "static void ctrl_handle_can_message",
            "static void ctrl_poll_can_messages",
        )
        self.assertIn("rehab_mode_manager_tick();", worker)
        self.assertNotIn("rehab_mode_manager_tick();", rx)

    def test_control_debug_exposes_lease_counters(self):
        self.assertIn("CTRL_DBG_LEASE:", CONTROL_C)
        self.assertIn("lease_timeout_count", CONTROL_C)
        self.assertIn("lease_stop_retry_count", CONTROL_C)


if __name__ == "__main__":
    unittest.main()
