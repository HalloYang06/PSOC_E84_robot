from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


client = TestClient(app)


def test_platform_preserves_robot_frame_vision_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vision/stereo-context",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "frame_ts_unix": 1780000100.0,
            "left_camera_id": "stereo_left",
            "right_camera_id": "stereo_right",
            "stereo_calibration_id": "stereo-calib-001",
            "target_3d_camera_frame": {"x_m": 0.2, "y_m": 0.05, "z_m": 0.4},
            "end_effector_3d_camera_frame": {"x_m": 0.1, "y_m": 0.02, "z_m": 0.35},
            "camera_to_robot_transform": {
                "calibration_id": "eye-to-hand-test",
                "source_stereo_calibration_id": "stereo-calib-001",
                "state": "accepted",
            },
            "transform_state": "calibrated",
            "target_3d_robot_frame": {"x_m": 0.3, "y_m": -0.15, "z_m": 0.7},
            "end_effector_3d_robot_frame": {"x_m": 0.2, "y_m": -0.18, "z_m": 0.65},
            "robot_frame_delta_to_target": {"dx_m": 0.1, "dy_m": 0.03, "dz_m": 0.05, "distance_m": 0.1158},
        },
    )
    assert response.status_code == 200
    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-rehab"})
    payload = dashboard.json()["data"]["devices"][0]["stereo_vision_context"]["payload"]
    assert payload["transform_state"] == "calibrated"
    assert payload["camera_to_robot_transform"]["calibration_id"] == "eye-to-hand-test"
    assert payload["target_3d_robot_frame"] == {"x_m": 0.3, "y_m": -0.15, "z_m": 0.7}
    assert payload["robot_frame_delta_to_target"]["distance_m"] == 0.1158
    get_settings.cache_clear()


def test_three_motor_ik_candidate_is_shadow_first_and_hardware_staged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_SIM_HOST", "10.101.106.90")
    get_settings.cache_clear()
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/ik-candidates",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "source": "stereo_eye_to_hand",
            "semantic_mode": "fetch_object",
            "kinematic_profile": "three_motor_visual_zero_v1",
            "target_robot_frame": {"x_m": 0.45, "y_m": 0.0, "z_m": 0.35},
            "source_frame_ts_unix": 1780000100.0,
            "source_calibration_id": "eye-to-hand-test",
        },
    )
    assert response.status_code == 200
    candidate = response.json()["data"]
    assert candidate["kinematic_profile"] == "three_motor_visual_zero_v1"
    assert candidate["active_motor_ids"] == [4, 5, 6]
    assert candidate["execution_stage"] == "shadow_candidate_only"
    assert candidate["candidate_joint_trajectory"]["joint_names"] == [
        "jian_hengxiang_joint",
        "jian_zongxiang_joint",
        "jian_xuanzhuan_joint",
        "zhou_zongxiang_joint",
        "wanbu_zongxiang_joint",
        "wanbu_hengxiang_joint",
    ]
    assert candidate["hardware_joint_trajectory_candidate"]["joint_names"] == [
        "elbow_lift_joint",
        "shoulder_abduction_joint",
        "upper_arm_rotation_joint",
    ]
    assert candidate["mujoco_shadow_validation_plan"]["sim_host"] == "10.101.106.90"
    assert candidate["mujoco_shadow_validation_plan"]["target_topic"] == "/sim/medical_arm/joint_trajectory"
    assert "/arm_controller/joint_trajectory" in candidate["mujoco_shadow_validation_plan"]["must_not_publish"]
    assert candidate["control_boundary"] == "ik_candidate_evidence_only_not_motion_permission"
    get_settings.cache_clear()


def test_calibrated_stereo_context_auto_creates_candidate_only_after_fetch_language(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    get_settings.cache_clear()
    relay = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "vla_language_from_voice",
            "prompt": "我口渴了，帮我拿水杯",
        },
    )
    assert relay.status_code == 200
    vision = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vision/stereo-context",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "frame_ts_unix": 1780000200.0,
            "left_camera_id": "stereo_left",
            "right_camera_id": "stereo_right",
            "stereo_calibration_id": "stereo-calib-001",
            "target_object": {"label": "water_bottle", "confidence": 0.91},
            "end_effector_object": {"label": "gripper", "confidence": 0.88},
            "visual_lock_stability": {"stable_for_dry_run": True},
            "target_3d_robot_frame": {"x_m": 0.45, "y_m": 0.0, "z_m": 0.35},
            "end_effector_3d_robot_frame": {"x_m": 0.40, "y_m": 0.0, "z_m": 0.36},
            "camera_to_robot_transform": {
                "calibration_id": "eye-to-hand-test",
                "source_stereo_calibration_id": "stereo-calib-001",
                "state": "accepted",
            },
            "transform_state": "calibrated",
        },
    )
    assert vision.status_code == 200
    assert vision.json()["data"]["auto_ik_candidate_state"] in {"candidate_ready", "candidate_approximate"}
    latest = client.get("/api/rehab-arm/v1/devices/nanopi-m5/ik-candidates/latest")
    assert latest.status_code == 200
    candidate = latest.json()["data"]
    assert candidate["semantic_mode"] == "fetch_object"
    assert candidate["source"] == "stereo_eye_to_hand"
    assert candidate["source_calibration_id"] == "eye-to-hand-test"
    get_settings.cache_clear()
