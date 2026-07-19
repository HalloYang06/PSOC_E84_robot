import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class M33FixedActionStaticTest(unittest.TestCase):
    def test_fixed_action_mode_and_service_api_are_declared(self):
        header = (ROOT / "applications/control/rehab_service.h").read_text(encoding="utf-8")

        self.assertIn("rehab_fixed_action.h", header)
        self.assertIn("REHAB_DEMO_MODE_FIXED_ACTION", header)
        self.assertIn("rehab_service_fixed_action_start_if_unchanged", header)
        self.assertIn("fixed_action_id", header)
        self.assertIn("fixed_action_state", header)
        self.assertIn("fixed_action_repetitions", header)

    def test_control_layer_has_prepare_once_and_setpoint_only_api(self):
        header = (ROOT / "applications/control/control_layer.h").read_text(encoding="utf-8")
        source = (ROOT / "applications/control/control_layer.c").read_text(encoding="utf-8")

        self.assertIn("control_motor_csp_prepare", header)
        self.assertIn("control_motor_csp_setpoint", header)
        self.assertIn("control_motor_csp_group_stop", header)
        self.assertIn("rt_err_t control_motor_csp_prepare", source)
        self.assertIn("rt_err_t control_motor_csp_setpoint", source)
        self.assertIn("rt_err_t control_motor_csp_group_stop", source)

    def test_service_uses_runner_without_legacy_position_entry(self):
        source = (ROOT / "applications/control/rehab_service.c").read_text(encoding="utf-8")

        self.assertIn("rehab_fixed_action_runner_t fixed_action_runner", source)
        self.assertIn("rehab_fixed_action_step", source)
        self.assertIn("control_motor_csp_prepare", source)
        self.assertIn("control_motor_csp_setpoint", source)
        fixed_start = source.index("REHAB_DEMO_MODE_FIXED_ACTION")
        fixed_slice = source[fixed_start:]
        self.assertNotIn("control_motor_position_control_with_current_limit(", fixed_slice)


if __name__ == "__main__":
    unittest.main()
