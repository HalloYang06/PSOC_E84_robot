import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("nanopi_stereo_natural_feature_calibration.py")


def load_module():
    spec = importlib.util.spec_from_file_location("natural_stereo_calibration", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_quality_gate_accepts_strong_epipolar_solution():
    module = load_module()
    result = module.assess_quality(
        ratio_matches=92,
        pose_inliers=37,
        median_vertical_error_px=0.26,
        p90_vertical_error_px=0.79,
        min_ratio_matches=40,
        min_pose_inliers=25,
        max_median_vertical_error_px=1.5,
        max_p90_vertical_error_px=3.0,
    )
    assert result["state"] == "accepted"
    assert result["calibration_kind"] == "natural_feature_provisional"


def test_quality_gate_rejects_stale_or_weak_solution():
    module = load_module()
    result = module.assess_quality(
        ratio_matches=92,
        pose_inliers=12,
        median_vertical_error_px=4.2,
        p90_vertical_error_px=8.8,
        min_ratio_matches=40,
        min_pose_inliers=25,
        max_median_vertical_error_px=1.5,
        max_p90_vertical_error_px=3.0,
    )
    assert result["state"] == "rejected"
    assert "pose_inliers_below_minimum" in result["reasons"]
    assert "median_vertical_error_above_limit" in result["reasons"]
    assert "p90_vertical_error_above_limit" in result["reasons"]
