import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTROL_H = (ROOT / "applications" / "control" / "control_layer.h").read_text(encoding="utf-8")
CONTROL_C = (ROOT / "applications" / "control" / "control_layer.c").read_text(encoding="utf-8")


class M33SetModeMaskContractTest(unittest.TestCase):
    def test_parsed_command_carries_explicit_mask(self):
        self.assertIn("rt_uint8_t joint_mask;", CONTROL_H)
        self.assertIn("out->joint_mask = msg->data[3];", CONTROL_C)

    def test_active_mode_requires_supported_single_joint_mask(self):
        self.assertIn("ctrl_rehab_single_joint_mask_supported", CONTROL_C)
        self.assertIn("joint_mask & (rt_uint8_t)(joint_mask - 1U)", CONTROL_C)
        self.assertIn("CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK", CONTROL_C)

    def test_apply_path_does_not_expand_to_default_group(self):
        self.assertIn("mode_cmd.joint_mask = cmd->joint_mask;", CONTROL_C)
        self.assertNotIn(
            "mode_cmd.joint_mask = CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK;",
            CONTROL_C,
        )


if __name__ == "__main__":
    unittest.main()
