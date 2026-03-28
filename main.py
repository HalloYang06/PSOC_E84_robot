from __future__ import annotations

import json

from vla_system.services.vla_bridge_service import VLABridgeService


SAMPLE_REQUEST = {
    "text": "把水放到床上",
    "objects": [
        {
            "object_id": "bottle_01",
            "class_name": "bottle",
            "bbox": [120, 80, 200, 300],
            "position": [0.42, 0.13, 0.75],
        },
        {
            "object_id": "bottle_02",
            "class_name": "bottle",
            "bbox": [300, 100, 360, 220],
            "position": [0.22, 0.66, 1.22],
        },
    ],
    "regions": [
        {
            "region_id": "bed_surface_01",
            "region_type": "bed_surface",
            "position": [0.90, 0.10, 0.60],
        },
        {
            "region_id": "shelf_01",
            "region_type": "shelf",
            "position": [0.20, 0.60, 1.20],
        },
        {
            "region_id": "table_01",
            "region_type": "table",
            "position": [0.40, 0.10, 0.72],
        },
    ],
    "relations": [
        {"subject": "bottle_01", "predicate": "on", "object": "table_01"},
        {"subject": "bottle_02", "predicate": "on", "object": "shelf_01"},
        {"subject": "bottle_01", "predicate": "left_of", "object": "bottle_02"},
    ],
    "robot_state": {
        "joint_state": [0.1, -0.4, 0.8, 0.2, 1.1, 0.0],
        "ee_pose": [0.4, 0.1, 0.8, 0.0, 0.0, 0.0, 1.0],
        "gripper_open": True,
        "has_object": False,
        "current_phase": "search",
    },
    "execution_history": [],
}


def main() -> None:
    service = VLABridgeService()
    resolved_task = service.resolve(SAMPLE_REQUEST)
    print(json.dumps(resolved_task.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
