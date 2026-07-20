#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_file_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    spec.loader.exec_module(module)
    return module


def run_offline_qa() -> dict:
    eye = load_file_module(
        "eye_to_hand_calibration",
        REPO_ROOT / "tools" / "nanopi" / "vision" / "eye_to_hand_calibration.py",
    )
    agent = load_file_module(
        "vla_mujoco_execution_agent",
        REPO_ROOT / "tools" / "linux" / "vla_mujoco_execution_agent.py",
    )
    calibration = {
        "schema_version": "rehab_arm_eye_to_hand_calibration_v1",
        "calibration_id": "offline-qa-eye-to-hand",
        "calibration_state": "accepted",
        "source_stereo_calibration_id": "offline-stereo-calibration",
        "camera_frame_id": "stereo_left_optical_frame",
        "robot_base_frame_id": "base_link",
        "matrix_4x4": [
            [1.0, 0.0, 0.0, 0.10],
            [0.0, 1.0, 0.0, 0.00],
            [0.0, 0.0, 1.0, 0.10],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "quality": {"state": "accepted", "validation_rmse_m": 0.005},
    }
    evidence = eye.build_robot_frame_evidence(
        calibration,
        stereo_calibration_id="offline-stereo-calibration",
        target_camera_xyz={"x_m": 0.35, "y_m": 0.0, "z_m": 0.25},
        end_effector_camera_xyz={"x_m": 0.30, "y_m": 0.0, "z_m": 0.26},
    )
    if evidence.get("transform_state") != "calibrated":
        raise RuntimeError("offline camera-to-robot transform did not become calibrated")

    platform_api = REPO_ROOT / "platform" / "api"
    sys.path.insert(0, str(platform_api))
    with tempfile.TemporaryDirectory(prefix="rehab-vla-offline-qa-") as temp_dir:
        os.environ["REHAB_ARM_SYNC_STORAGE_DIR"] = temp_dir
        from app.settings import get_settings
        from app.modules.rehab_arm.service import record_ik_candidate_request

        get_settings.cache_clear()
        now = time.time()
        candidate = record_ik_candidate_request(
            {
                "robot_id": "rehab-arm-alpha",
                "device_id": "offline-nanopi",
                "project_id": "offline-project",
                "source": "stereo_eye_to_hand",
                "semantic_mode": "fetch_object",
                "kinematic_profile": "three_motor_visual_zero_v1",
                "target_robot_frame": evidence["target_3d_robot_frame"],
                "source_frame_ts_unix": now,
                "source_calibration_id": calibration["calibration_id"],
                "control_boundary": "ik_candidate_request_evidence_only_not_motion_permission",
            }
        )
        staged = agent.validate_candidate(candidate, now=now, max_age_s=2.0)
        get_settings.cache_clear()

    return {
        "schema_version": "rehab_arm_vla_offline_qa_v1",
        "ok": True,
        "transform_state": evidence["transform_state"],
        "target_robot_frame": evidence["target_3d_robot_frame"],
        "candidate_id": staged["candidate_id"],
        "ik_status": staged["ik_status"],
        "visual_joint_count": len(staged["visual_joint_names"]),
        "hardware_joint_count": len(staged["hardware_joint_names"]),
        "active_motor_ids": candidate["active_motor_ids"],
        "first_publish_scope": "/sim/medical_arm/joint_trajectory",
        "hardware_publish_scope": "/arm_controller/joint_trajectory_after_shadow_and_confirmation",
        "control_boundary": "offline_qa_only_not_motion_permission",
    }


def main() -> int:
    print(json.dumps(run_offline_qa(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
