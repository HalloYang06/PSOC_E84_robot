from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("post_calibration_preflight.py")
    spec = importlib.util.spec_from_file_location("post_calibration_preflight", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_preflight_accepts_loaded_calibration_while_waiting_for_objects():
    module = load_module()
    calibration = {
        "calibration_state": "accepted",
        "calibration_id": "eye-test",
        "source_stereo_calibration_id": "stereo-test",
    }
    context = {
        "frame_ts_unix": 100.0,
        "stereo_calibration_id": "stereo-test",
        "transform_state": "calibrated",
        "camera_to_robot_transform": {"calibration_id": "eye-test"},
        "target_3d_robot_frame": None,
        "end_effector_3d_robot_frame": None,
    }
    report = module.evaluate_post_calibration_readiness(calibration, context, now=100.2)
    assert report["calibration_ready"] is True
    assert report["ready_for_linux_shadow_candidate"] is False
    assert report["next_step"] == "place_target_and_gripper_in_both_cameras"


def test_preflight_rejects_stereo_mismatch_and_stale_context():
    module = load_module()
    calibration = {
        "calibration_state": "accepted",
        "calibration_id": "eye-test",
        "source_stereo_calibration_id": "stereo-a",
    }
    context = {
        "frame_ts_unix": 90.0,
        "stereo_calibration_id": "stereo-b",
        "transform_state": "calibrated",
        "camera_to_robot_transform": {"calibration_id": "eye-test"},
    }
    report = module.evaluate_post_calibration_readiness(calibration, context, now=100.0)
    assert report["calibration_ready"] is False
    assert "stereo_calibration_id_mismatch" in report["blockers"]
    assert "vision_context_stale" in report["blockers"]
