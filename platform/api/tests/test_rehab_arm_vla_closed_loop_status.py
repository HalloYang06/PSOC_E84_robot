from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


client = TestClient(app)


def test_dashboard_exposes_vla_closed_loop_status_without_robot_frame(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    get_settings.cache_clear()

    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    relay_response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "vla_language_from_voice",
            "prompt": "我口渴了，帮我拿水瓶",
        },
    )
    assert relay_response.status_code == 200

    stereo_response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vision/stereo-context",
        json={
            "schema_version": "stereo_rgb_yolo_context_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "frame_ts_unix": 1780000002.0,
            "capture_loop": {
                "loop_index": 1,
                "loop_count": 3,
                "interval_ms": 200,
                "sequence": 42,
                "frame_process_ms": 123.4,
                "loop_elapsed_ms": 456.7,
                "implementation": "opencv_cpp_persistent_loop",
            },
            "left_camera_id": "stereo_left",
            "right_camera_id": "stereo_right",
            "stereo_calibration_id": "calib-a1",
            "baseline_m": 0.08,
            "image_pair_ref": {"left_image_url": "/left.jpg", "right_image_url": "/right.jpg"},
            "detections": [
                {"label": "water_bottle", "confidence": 0.86, "bbox": [120, 80, 180, 220]},
                {"label": "gripper_tip", "confidence": 0.78, "bbox": [300, 100, 340, 180]},
            ],
            "target_object": {
                "label": "water_bottle",
                "confidence": 0.86,
                "bbox_xywh": [120, 80, 60, 140],
                "center_px": [150.0, 150.0],
            },
            "end_effector_object": {
                "label": "gripper_tip",
                "confidence": 0.78,
                "bbox_xywh": [300, 100, 40, 80],
                "center_px": [320.0, 140.0],
                "source": "opencv_marker_or_yolo_tool_tip",
            },
            "visual_lock_stability": {
                "schema_version": "visual_lock_stability_v1",
                "state": "stable_candidate",
                "reason": "multi_frame_same_label_stereo_lock",
                "candidate_label": "water_bottle",
                "same_label_frames": 3,
                "stereo_match_frames": 3,
                "stable_for_dry_run": True,
                "control_boundary": "visual_lock_stability_only_not_motion_permission",
            },
            "target_quality_gate": {
                "schema_version": "target_quality_gate_v1",
                "state": "candidate_accepted",
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
            "stereo_depth_evidence": {
                "state": "accepted",
                "disparity_px": 24.5,
                "depth_m": 0.72,
                "control_boundary": "stereo_depth_evidence_only_not_motion_permission",
            },
            "estimated_depth_m": 0.72,
            "target_3d_camera_frame": {"x_m": 0.12, "y_m": -0.04, "z_m": 0.72},
            "camera_to_robot_transform": None,
            "target_3d_robot_frame": None,
            "transform_state": "waiting",
            "scene_summary": "two RGB cameras see bottle and gripper tip",
            "vla_context": "stereo depth is approximate; robot-frame transform is still waiting",
            "confidence": 0.86,
        },
    )
    assert stereo_response.status_code == 200

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-rehab"})
    assert dashboard.status_code == 200
    device = dashboard.json()["data"]["devices"][0]
    closed_loop = device["vla_closed_loop_status"]

    assert closed_loop["schema_version"] == "rehab_arm_vla_closed_loop_status_v1"
    assert closed_loop["active_mode"] == "fetch_object"
    assert closed_loop["action_state"] == "hold_observe"
    assert closed_loop["next_step"] == "wait_camera_to_robot_transform_or_manual_target"
    assert closed_loop["l"]["ready"] is True
    assert closed_loop["v"]["target_ready"] is True
    assert closed_loop["v"]["end_effector_ready"] is True
    assert closed_loop["v"]["robot_frame_ready"] is False
    assert closed_loop["a"]["ready"] is False
    assert closed_loop["m33"]["ready"] is False
    assert "camera_to_robot_transform_missing" in closed_loop["blockers"]
    assert closed_loop["control_boundary"] == "vla_closed_loop_status_only_not_motion_permission"
    assert [stage["stage"] for stage in closed_loop["pipeline"]] == ["L", "V", "A", "SIM", "M33"]
    get_settings.cache_clear()
