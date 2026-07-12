from __future__ import annotations

import unittest

from ai.vla.utils.json_schema import ResolvedTask


class ControlBoundaryTest(unittest.TestCase):
    def test_resolved_task_excludes_low_level_control_fields(self) -> None:
        output = ResolvedTask(
            task_type="retrieve_object",
            object_id="bottle_01",
            candidate_objects=["bottle_01"],
            target_region_id="user",
            phase="search",
            grasp_type="side_grasp",
            speed="slow",
            retry=False,
            confidence=0.9,
            need_confirmation=False,
            question="",
        ).to_dict()

        forbidden_fields = {
            "can",
            "motor_current",
            "torque",
            "raw_setpoints",
            "emergency_stop_release",
            "m33_safety_override",
        }
        self.assertTrue(output.keys().isdisjoint(forbidden_fields))


if __name__ == "__main__":
    unittest.main()
