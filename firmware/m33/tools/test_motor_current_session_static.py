from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_C = (ROOT / "applications" / "control" / "control_layer.c").read_text(encoding="utf-8")
CONTROL_H = (ROOT / "applications" / "control" / "control_layer.h").read_text(encoding="utf-8")


def function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class MotorCurrentSessionStaticTest(unittest.TestCase):
    def test_header_exposes_prepare_and_setpoint(self):
        self.assertIn("control_motor_current_prepare(rt_uint8_t joint_id)", CONTROL_H)
        self.assertIn(
            "control_motor_current_setpoint(rt_uint8_t joint_id, float current_a)",
            CONTROL_H,
        )

    def test_prepare_writes_zero_before_enable(self):
        body = function_body(
            CONTROL_C,
            "rt_err_t control_motor_current_prepare(",
            "rt_err_t control_motor_current_setpoint(",
        )
        mode = body.index("control_motor_set_run_mode")
        zero = body.index("MOTOR_PARAM_INDEX_IQ_REF, 0.0f")
        enable = body.index("control_motor_enable")
        self.assertLess(mode, zero)
        self.assertLess(zero, enable)

    def test_periodic_setpoint_does_not_rearm_or_delay(self):
        body = function_body(
            CONTROL_C,
            "rt_err_t control_motor_current_setpoint(",
            "rt_err_t control_motor_current_control(",
        )
        self.assertIn("CONTROL_MOTOR_CURRENT_CONTROL_MAX_A", body)
        self.assertIn("MOTOR_PARAM_INDEX_IQ_REF", body)
        self.assertNotIn("control_motor_set_run_mode", body)
        self.assertNotIn("control_motor_enable", body)
        self.assertNotIn("rt_thread_mdelay", body)

    def test_legacy_wrapper_uses_new_split_api(self):
        body = function_body(
            CONTROL_C,
            "rt_err_t control_motor_current_control(",
            "rt_err_t control_motor_cansimple_set_input_pos(",
        )
        self.assertIn("control_motor_current_prepare(joint_id)", body)
        self.assertIn("control_motor_current_setpoint(joint_id, current_a)", body)


if __name__ == "__main__":
    unittest.main()
