from __future__ import annotations

import unittest

from ai.vla.services.vla_bridge_service import VLABridgeService
from ai.vla.utils.validators import SchemaValidationError, validate_resolve_request, validate_resolved_task


class ValidatorTest(unittest.TestCase):
    def test_reject_invalid_request(self) -> None:
        with self.assertRaises(SchemaValidationError):
            validate_resolve_request({"text": "", "objects": []})

    def test_validate_bridge_output(self) -> None:
        payload = {
            "text": "把水放到床上",
            "objects": [
                {"object_id": "bottle_01", "class_name": "bottle", "position": [0.4, 0.1, 0.7]},
            ],
            "regions": [
                {"region_id": "bed_surface_01", "region_type": "bed_surface", "position": [0.9, 0.1, 0.6]},
            ],
            "relations": [],
            "robot_state": {"gripper_open": True, "has_object": False, "current_phase": "search"},
            "execution_history": [],
        }
        resolved = VLABridgeService().resolve(payload)
        validate_resolved_task(resolved)


if __name__ == "__main__":
    unittest.main()
