from __future__ import annotations

import importlib.util
from pathlib import Path


def test_local_solver_matches_visual_zero_hardware_contract():
    path = Path(__file__).with_name("three_motor_visual_zero_ik.py")
    spec = importlib.util.spec_from_file_location("three_motor_visual_zero_ik", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    candidate = module.build_candidate(
        {"x_m": 0.45, "y_m": 0.0, "z_m": 0.35},
        source_frame_ts_unix=100.0,
        source_calibration_id="eye-test",
        semantic_mode="fetch_object",
        device_id="nanopi-m5",
    )

    assert candidate["ik_status"] == "candidate_ready"
    assert candidate["active_motor_ids"] == [4, 5, 6]
    assert candidate["candidate_joint_trajectory"]["points"][0]["positions_rad"] == module.VISUAL_ZERO
    assert candidate["hardware_joint_trajectory_candidate"]["joint_names"] == module.HARDWARE_NAMES
    assert candidate["control_boundary"] == "ik_candidate_evidence_only_not_motion_permission"
