from __future__ import annotations

import unittest

from ai.vla.services.vla_bridge_service import VLABridgeService


class VLABridgeServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VLABridgeService()

    def test_end_to_end_pick_and_place(self) -> None:
        payload = {
            "text": "把水放到床上",
            "objects": [
                {"object_id": "bottle_01", "class_name": "bottle", "position": [0.4, 0.1, 0.7]},
                {"object_id": "cup_01", "class_name": "cup", "position": [0.2, 0.1, 0.7]},
            ],
            "regions": [
                {"region_id": "bed_surface_01", "region_type": "bed_surface", "position": [0.9, 0.1, 0.6]},
                {"region_id": "table_01", "region_type": "table", "position": [0.4, 0.1, 0.7]},
            ],
            "relations": [
                {"subject": "bottle_01", "predicate": "on", "object": "table_01"},
                {"subject": "cup_01", "predicate": "on", "object": "table_01"},
            ],
            "robot_state": {
                "gripper_open": True,
                "has_object": False,
                "current_phase": "search",
            },
            "execution_history": [],
        }
        resolved = self.service.resolve(payload)
        self.assertEqual(resolved.task_type, "pick_and_place")
        self.assertEqual(resolved.object_id, "bottle_01")
        self.assertEqual(resolved.target_region_id, "bed_surface_01")
        self.assertFalse(resolved.need_confirmation)


if __name__ == "__main__":
    unittest.main()
