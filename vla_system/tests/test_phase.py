from __future__ import annotations

import unittest

from vla_system.services.phase_service import PhaseService
from vla_system.utils.json_schema import RobotState, TaskType


class PhaseServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PhaseService()

    def test_search_when_object_is_missing(self) -> None:
        prediction = self.service.predict(
            task_type=TaskType.PICK_AND_PLACE,
            robot_state=RobotState(current_phase="search"),
            execution_history=[],
            object_id="",
            target_region_id="bed_surface_01",
        )
        self.assertEqual(prediction.phase.value, "search")

    def test_place_when_holding_object_for_pick_and_place(self) -> None:
        prediction = self.service.predict(
            task_type=TaskType.PICK_AND_PLACE,
            robot_state=RobotState(has_object=True, gripper_open=False, current_phase="lift"),
            execution_history=["grasp_succeeded"],
            object_id="bottle_01",
            target_region_id="bed_surface_01",
        )
        self.assertEqual(prediction.phase.value, "lift")

    def test_handover_when_holding_object_for_user(self) -> None:
        prediction = self.service.predict(
            task_type=TaskType.HANDOVER,
            robot_state=RobotState(has_object=True, gripper_open=False, current_phase="lift"),
            execution_history=[],
            object_id="cup_01",
            target_region_id="user",
        )
        self.assertEqual(prediction.phase.value, "handover")


if __name__ == "__main__":
    unittest.main()
