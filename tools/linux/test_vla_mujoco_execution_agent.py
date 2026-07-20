from __future__ import annotations

import importlib.util
import time
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("vla_mujoco_execution_agent.py")
    spec = importlib.util.spec_from_file_location("vla_mujoco_execution_agent", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def candidate(now: float) -> dict:
    return {
        "schema_version": "rehab_arm_ik_candidate_evidence_v1",
        "candidate_id": "ik-test",
        "ik_status": "candidate_ready",
        "kinematic_profile": "three_motor_visual_zero_v1",
        "active_motor_ids": [4, 5, 6],
        "semantic_mode": "fetch_object",
        "source_calibration_id": "eye-to-hand-test",
        "source_frame_ts_unix": now - 0.1,
        "candidate_joint_trajectory": {
            "joint_names": ["j0", "j1", "j2", "j3", "j4", "j5"],
            "points": [
                {"positions_rad": [0.0] * 6, "time_from_start_s": 0.0},
                {"positions_rad": [0.1] * 6, "time_from_start_s": 2.0},
            ],
        },
        "hardware_joint_trajectory_candidate": {
            "joint_names": ["elbow_lift_joint", "shoulder_abduction_joint", "upper_arm_rotation_joint"],
            "points": [
                {"positions_rad": [0.0, 0.0, 0.0], "time_from_start_s": 0.0},
                {"positions_rad": [0.2, 0.3, -0.1], "time_from_start_s": 2.0},
            ],
        },
        "control_boundary": "ik_candidate_evidence_only_not_motion_permission",
    }


def test_candidate_validation_accepts_fresh_three_motor_contract():
    module = load_module()
    now = time.time()
    staged = module.validate_candidate(candidate(now), now=now, max_age_s=2.0)
    assert staged["candidate_id"] == "ik-test"
    assert staged["hardware_target"] == [0.2, 0.3, -0.1]


def test_candidate_validation_rejects_stale_or_wrong_motor_set():
    module = load_module()
    now = time.time()
    stale = candidate(now)
    stale["source_frame_ts_unix"] = now - 5.0
    try:
        module.validate_candidate(stale, now=now, max_age_s=2.0)
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale camera candidates must be rejected")

    wrong_motors = candidate(now)
    wrong_motors["active_motor_ids"] = [3, 4, 5]
    try:
        module.validate_candidate(wrong_motors, now=now, max_age_s=2.0)
    except ValueError as exc:
        assert "4,5,6" in str(exc)
    else:
        raise AssertionError("unexpected motor subsets must be rejected")
