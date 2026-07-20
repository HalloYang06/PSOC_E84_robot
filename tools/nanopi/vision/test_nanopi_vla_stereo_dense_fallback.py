import runpy
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("nanopi-vla-cpp-upload-loop.py")


def test_dense_disparity_summary_uses_robust_median_depth():
    module = runpy.run_path(str(MODULE_PATH))
    summarize = module["summarize_dense_disparities"]
    disparities = np.concatenate(
        [np.full(900, 60.0), np.full(50, 20.0), np.full(50, 100.0)]
    )
    result = summarize(disparities, focal_px=600.0, baseline_m=0.06)
    assert result["state"] == "accepted"
    assert result["median_disparity_px"] == 60.0
    assert result["depth_m"] == 0.6


def test_dense_disparity_summary_rejects_too_few_pixels():
    module = runpy.run_path(str(MODULE_PATH))
    summarize = module["summarize_dense_disparities"]
    result = summarize(np.full(20, 60.0), focal_px=600.0, baseline_m=0.06)
    assert result["state"] == "rejected"
    assert result["reason"] == "too_few_valid_disparity_pixels"


def test_dense_reference_candidate_rejects_frame_edge_false_positive():
    module = runpy.run_path(str(MODULE_PATH))
    choose = module["choose_dense_reference_candidate"]
    edge_false_positive = {"confidence": 0.54, "bbox_xywh": [0.0, 15.0, 54.0, 140.0]}
    complete_bottle = {"confidence": 0.27, "bbox_xywh": [143.0, 239.0, 58.0, 108.0]}
    assert choose([edge_false_positive, complete_bottle]) is complete_bottle


def test_point_stereo_rejects_depth_outside_workspace_range(monkeypatch):
    module = runpy.run_path(str(MODULE_PATH))
    monkeypatch.setenv("REHAB_STEREO_MAX_DEPTH_M", "1.5")
    calibration = {
        "calibration_state": "calibrated",
        "baseline_m": 0.06,
        "left_intrinsics": [[100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 1.0]],
        "right_intrinsics": [[100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 1.0]],
        "left_distortion": [0.0] * 5,
        "right_distortion": [0.0] * 5,
        "rectification": {
            "R1": np.eye(3).tolist(),
            "R2": np.eye(3).tolist(),
            "P1": [[100.0, 0.0, 0.0, 0.0], [0.0, 100.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
            "P2": [[100.0, 0.0, 0.0, -6.0], [0.0, 100.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        },
    }
    left = {"label": "target_bottle", "center_px": [100.0, 100.0], "bbox_xywh": [80.0, 50.0, 40.0, 100.0]}
    right = {"label": "target_bottle", "center_px": [98.0, 100.0], "bbox_xywh": [78.0, 50.0, 40.0, 100.0]}
    result = module["stereo_depth_from_targets"](calibration, left, right)
    assert result["state"] == "rejected"
    assert result["reason"] == "depth_outside_workspace_range"


def test_dense_depth_rejects_large_jump_from_recent_point_stereo():
    module = runpy.run_path(str(MODULE_PATH))
    result = module["assess_dense_temporal_consistency"](0.478, [0.59, 0.60, 0.61], max_relative_delta=0.18)
    assert result["state"] == "rejected"
    assert result["reason"] == "dense_depth_temporal_inconsistent"


def test_dense_depth_accepts_value_near_recent_point_stereo():
    module = runpy.run_path(str(MODULE_PATH))
    result = module["assess_dense_temporal_consistency"](0.608, [0.59, 0.60, 0.61], max_relative_delta=0.18)
    assert result["state"] == "accepted"


def test_complete_jpeg_reader_rejects_partial_capture_file(tmp_path):
    module = runpy.run_path(str(MODULE_PATH))
    path = tmp_path / "partial.jpg"
    path.write_bytes(b"\xff\xd8partial")
    try:
        module["read_complete_jpeg_bytes"](path, retries=1, delay_s=0.0)
    except RuntimeError as exc:
        assert "incomplete JPEG" in str(exc)
    else:
        raise AssertionError("partial JPEG must not be uploaded")


def test_complete_jpeg_reader_accepts_complete_capture_file(tmp_path):
    module = runpy.run_path(str(MODULE_PATH))
    path = tmp_path / "complete.jpg"
    payload = b"\xff\xd8payload\xff\xd9"
    path.write_bytes(payload)
    assert module["read_complete_jpeg_bytes"](path, retries=1, delay_s=0.0) == payload
