from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
import urllib.request
import wave
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.rehab_arm.service import record_xiaozhi_ws_event
from app.settings import get_settings
from tests.helpers import auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def _legacy_model_relay_only_token(project_id: str, device_id: str) -> str:
    from app.modules.rehab_arm import service as rehab_service

    now = 1_900_000_000
    payload = {
        "v": 1,
        "kind": "rehab_model_relay",
        "project_id": project_id,
        "device_id": device_id,
        "scope": ["rehab_arm.model_relay.invoke"],
        "label": "legacy-model-relay-only",
        "iat": now,
        "exp": now + 600,
    }
    encoded = rehab_service._encode_token_payload(payload)
    signature = rehab_service.hmac.new(
        rehab_service._relay_token_secret().encode("utf-8"),
        encoded.encode("utf-8"),
        rehab_service.hashlib.sha256,
    ).hexdigest()
    return f"{rehab_service.MODEL_RELAY_TOKEN_PREFIX}.{encoded}.{signature}"


def test_rehab_arm_sync_endpoints_store_non_realtime_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    register = client.post(
        "/api/rehab-arm/v1/devices/register",
        json={
            "device_id": "nanopi-m5",
            "robot_id": "rehab-arm-alpha",
            "device_type": "nanopi",
            "software_version": "dev",
            "computer_node_id": "nanopi-computer-1",
            "runner_id": "nanopi-runner-1",
            "capabilities": ["ros2_bridge", "jsonl_recorder"],
        },
    )
    assert register.status_code == 200
    assert register.json()["data"]["sync_role"] == "non_realtime_data_only"

    manifest = client.post(
        "/api/rehab-arm/v1/sessions/manifest",
        json={
            "manifest": {
                "schema_version": "rehab_arm_manifest_v1",
                "sessions": [
                    {
                        "ok": True,
                        "session_id": "s1",
                        "project_id": "project-rehab",
                        "device_id": "nanopi-m5",
                        "robot_id": "rehab-arm-alpha",
                        "file_name": "s1.jsonl",
                        "record_count": 120,
                        "summary": {
                            "schema_version": "rehab_arm_recording_summary_v1",
                            "topic_counts": {
                                "/joint_states": 100,
                                "/rehab_arm/motor_state": 100,
                                "/rehab_arm/safety_state": 3,
                                "/rehab_arm/sensor_state": 100,
                            },
                            "moving_joint_count": 5,
                            "motor_entry_count_min": 5,
                            "motor_entry_count_max": 5,
                            "motion_allowed_counts": {"true": 0, "false": 3, "missing": 0},
                        },
                        "quality_report": {
                            "schema_version": "rehab_arm_recording_quality_v1",
                            "ok": True,
                            "errors": [],
                            "warnings": [],
                            "criteria": {
                                "min_joint_messages": 2,
                                "min_moving_joints": 5,
                                "require_motor_state": True,
                                "min_motor_entry_count": 5,
                                "allow_motion_allowed_true": False,
                            },
                        },
                    }
                ],
            }
        },
    )
    assert manifest.status_code == 200
    assert manifest.json()["data"]["accepted_sessions"] == ["s1"]

    file_upload = client.post(
        "/api/rehab-arm/v1/sessions/s1/files",
        content=b"--boundary\r\nsession payload\r\n--boundary--\r\n",
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )
    assert file_upload.status_code == 200
    file_data = file_upload.json()["data"]
    assert file_data["sync_status"] == "uploaded"
    assert Path(file_data["stored_body_path"]).exists()

    status = client.post(
        "/api/rehab-arm/v1/sessions/s1/sync-status",
        json={
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "sync_status": "uploaded",
            "file_name": "s1.jsonl",
            "record_count": 1,
        },
    )
    assert status.status_code == 200
    assert status.json()["data"]["sync_status"] == "uploaded"

    event_lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(event_lines) == 4
    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    assert device["computer_node_id"] == "nanopi-computer-1"
    assert device["runner_id"] == "nanopi-runner-1"
    quality = dashboard.json()["data"]["devices"][0]["data_quality"]
    assert quality["schema_version"] == "device_recording_quality_index_v1"
    assert quality["annotation_ready"] is True
    assert quality["annotatable_session_count"] == 1
    assert quality["latest_session"]["moving_joint_count"] == 5
    assert quality["latest_session"]["quality_report_schema"] == "rehab_arm_recording_quality_v1"
    assert quality["latest_session"]["quality_report_ok"] is True
    assert quality["latest_session"]["quality_criteria"]["min_moving_joints"] == 5
    assert quality["control_boundary"] == "data_quality_only_not_motion_permission"
    assert quality["adapter"] == "rehab_arm_sync_v1"
    events = dashboard.json()["data"]["recent_events"]
    assert any(event["record_type"] == "manifest" and event["project_id"] == "project-rehab" for event in events)
    assert any(event["record_type"] == "sync_status" and event["payload"]["project_id"] == "project-rehab" for event in events)
    get_settings.cache_clear()


def test_rehab_arm_manifest_quality_report_can_gate_annotation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.post(
        "/api/rehab-arm/v1/sessions/manifest",
        json={
            "manifest": {
                "schema_version": "rehab_arm_manifest_v1",
                "sessions": [
                    {
                        "ok": True,
                        "session_id": "static-check",
                        "device_id": "nanopi-m5",
                        "robot_id": "rehab-arm-alpha",
                        "file_name": "static-check.jsonl",
                        "record_count": 4,
                        "quality_report": {
                            "schema_version": "rehab_arm_recording_quality_v1",
                            "ok": False,
                            "errors": ["moving joint count 0 below required 1"],
                            "warnings": [],
                            "criteria": {
                                "min_joint_messages": 2,
                                "min_moving_joints": 1,
                                "require_motor_state": False,
                                "min_motor_entry_count": 0,
                                "allow_motion_allowed_true": False,
                            },
                            "summary": {
                                "schema_version": "rehab_arm_recording_summary_v1",
                                "topic_counts": {"/joint_states": 2, "/rehab_arm/safety_state": 1, "/rehab_arm/sensor_state": 1},
                                "moving_joint_count": 0,
                                "motor_entry_count_min": 0,
                                "motor_entry_count_max": 0,
                                "motion_allowed_counts": {"true": 0, "false": 1, "missing": 0},
                            },
                        },
                    }
                ],
            }
        },
    )
    assert response.status_code == 200

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    quality = dashboard.json()["data"]["devices"][0]["data_quality"]
    assert quality["annotation_ready"] is False
    assert quality["annotatable_session_count"] == 0
    assert quality["latest_session"]["quality_report_ok"] is False
    assert quality["latest_session"]["moving_joint_count"] == 0
    assert quality["blocking_reasons"] == ["moving joint count 0 below required 1"]
    get_settings.cache_clear()


def test_rehab_arm_motor_safety_and_dashboard_are_non_realtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    safety = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/safety-state",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "state": "limited",
            "motion_allowed": False,
            "emergency_stop": False,
            "m33_mode": "guarded",
            "detail_code": "range_guard",
            "detail": "M33 limited movement envelope",
            "heartbeat_age_ms": 42,
            "fault_code": "",
            "fault_message": "",
        },
    )
    assert safety.status_code == 200
    assert safety.json()["data"]["sync_role"] == "non_realtime_telemetry_data_asset_only"

    motor = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/motor-state",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "ts_unix": 1710000000.0,
            "motors": [
                {
                    "motor_id": "m1",
                    "joint_name": "elbow",
                    "protocol": "CANSimple",
                    "position": 1.2,
                    "velocity": 0.1,
                    "torque": 0.3,
                    "current": 0.8,
                    "temperature": 31.5,
                    "voltage": 24.1,
                    "error_code": 0,
                    "enabled": True,
                    "fault": False,
                    "raw_can_id": "0x01",
                }
            ],
            "joint_state": {
                "name": ["shoulder_lift_joint", "elbow_lift_joint"],
                "position": [0.12, 1.2],
                "velocity": [0.01, 0.1],
                "effort": [0.2, 0.3],
            },
        },
    )
    assert motor.status_code == 200
    assert motor.json()["data"]["motor_count"] == 1
    assert motor.json()["data"]["joint_state_count"] == 2

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()["data"]
    assert data["safety_boundary"]["m33_final_authority"] is True
    assert "can_frame" in data["safety_boundary"]["server_must_not_send"]
    assert data["devices"][0]["device_id"] == "nanopi-m5"
    assert data["devices"][0]["project_id"] == "project-rehab"
    assert data["devices"][0]["safety_state"] == "limited"
    assert data["devices"][0]["motion_allowed"] is False
    assert data["devices"][0]["motor_state"]["payload"]["motors"][0]["joint_name"] == "elbow"
    assert data["devices"][0]["motor_state"]["payload"]["joint_state"]["name"] == ["shoulder_lift_joint", "elbow_lift_joint"]
    get_settings.cache_clear()


def test_rehab_arm_dashboard_filters_devices_and_events_by_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    for project_id, device_id in [("project-rehab-a", "nanopi-a"), ("project-rehab-b", "nanopi-b")]:
        register = client.post(
            "/api/rehab-arm/v1/devices/register",
            json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
        )
        assert register.status_code == 200
        motor = client.post(
            f"/api/rehab-arm/v1/devices/{device_id}/motor-state",
            json={
                "robot_id": "rehab-arm-alpha",
                "device_id": device_id,
                "project_id": project_id,
                "ts_unix": 1710000000.0,
                "motors": [{"motor_id": "m1", "joint_name": "elbow", "position": 1.2}],
            },
        )
        assert motor.status_code == 200

    project_a = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-rehab-a"})
    assert project_a.status_code == 200
    project_a_data = project_a.json()["data"]
    assert [item["device_id"] for item in project_a_data["devices"]] == ["nanopi-a"]
    assert project_a_data["recent_events"]
    assert all(event.get("project_id") == "project-rehab-a" for event in project_a_data["recent_events"])

    outsider = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-outsider"})
    assert outsider.status_code == 200
    assert outsider.json()["data"]["devices"] == []
    assert outsider.json()["data"]["recent_events"] == []
    get_settings.cache_clear()


def test_rehab_arm_board_manifest_upload_is_data_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/board-manifest",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "computer_node_id": "nanopi-node-from-board",
            "runner_id": "nanopi-runner-from-board",
            "manifest": {
                "schema_version": "linux_board_manifest_v1",
                "device_id": "nanopi-m5",
                "robot_id": "rehab-arm-alpha",
                "computer_node_id": "nanopi-node-from-manifest",
                "hostname": "NanoPi-M5",
                "capabilities": {
                    "can_interfaces": [{"name": "can0", "kind": "can", "operstate": "up"}],
                    "serial_devices": ["/dev/ttyUSB0"],
                    "camera_devices": ["/dev/video0"],
                    "usb_devices": [{"kind": "usb", "description": "USB camera"}],
                    "ros2": {"available": True, "version_text": "ros2 0.32"},
                },
                "control_boundary": "board_discovery_only_not_motion_permission",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "linux_board_manifest_v1"
    assert data["can_interface_count"] == 1
    assert data["serial_device_count"] == 1
    assert data["camera_device_count"] == 1
    assert data["ros2_available"] is True
    assert data["control_boundary"] == "board_manifest_only_not_motion_permission"

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    assert device["project_id"] == "project-rehab"
    assert device["computer_node_id"] == "nanopi-node-from-board"
    assert device["runner_id"] == "nanopi-runner-from-board"
    board_manifest = device["board_manifest"]
    assert board_manifest["record_type"] == "board_manifest"
    assert board_manifest["payload"]["manifest"]["hostname"] == "NanoPi-M5"
    get_settings.cache_clear()


def test_rehab_arm_camera_keyframe_upload_and_latest_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    image = b"\x89PNG\r\n\x1a\nfake-keyframe"
    digest = hashlib.sha256(image).hexdigest()
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes",
        data={
            "robot_id": "rehab-arm-alpha",
            "project_id": "project-rehab",
            "camera_id": "front",
            "frame_ts_unix": "1710000001.5",
            "image_format": "png",
            "width": "320",
            "height": "240",
            "sha256": digest,
            "detection_summary": "hand and elbow visible",
            "scene_summary": "training table",
            "vla_context": "reach preparation",
        },
        files={"file": ("frame.png", image, "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["sync_role"] == "non_realtime_telemetry_data_asset_only"
    assert payload["sha256"] == digest
    assert payload["image_url"].endswith("/devices/nanopi-m5/camera/keyframes/latest/file")

    latest = client.get("/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes/latest/file")
    assert latest.status_code == 200
    assert latest.content == image

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    assert device["camera_keyframe"]["project_id"] == "project-rehab"
    assert device["camera_keyframe"]["payload"]["detection_summary"] == "hand and elbow visible"
    get_settings.cache_clear()


def test_rehab_arm_stereo_vision_context_prefers_yolo_pair(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vision/stereo-context",
        json={
            "schema_version": "stereo_rgb_yolo_context_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "frame_ts_unix": 1780000002.0,
            "left_camera_id": "left_rgb",
            "right_camera_id": "right_rgb",
            "stereo_calibration_id": "calib-a1",
            "baseline_m": 0.08,
            "image_pair_ref": {"left_image_url": "/left.jpg", "right_image_url": "/right.jpg"},
            "detections": [
                {"label": "cup", "confidence": 0.88, "bbox": [120, 80, 180, 160]},
                {"label": "hand", "confidence": 0.91, "bbox": [210, 100, 260, 170]},
            ],
            "target_object": {"label": "cup", "confidence": 0.88},
            "estimated_depth_m": 0.72,
            "target_3d_camera_frame": {"x": 0.12, "y": -0.04, "z": 0.72},
            "scene_summary": "two RGB cameras see table and cup",
            "vla_context": "stereo depth is approximate; move only after operator review",
            "confidence": 0.88,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "stereo_rgb_yolo_context_v1"
    assert data["target_label"] == "cup"
    assert data["detection_count"] == 2
    assert data["control_boundary"] == "stereo_vision_context_only_not_motion_permission"

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    assert device["stereo_vision_context"]["payload"]["target_object"]["label"] == "cup"

    relay = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "vla_context",
            "prompt": "根据视觉上下文，准备拿起桌面杯子",
        },
    )
    assert relay.status_code == 200
    relay_data = relay.json()["data"]
    assert relay_data["vla_vision_context"]["source"] == "stereo_rgb_yolo_context_v1"
    assert relay_data["vla_vision_context"]["target_label"] == "cup"
    assert relay_data["vla_vision_context"]["camera_id"] == "left_rgb+right_rgb"
    get_settings.cache_clear()


def test_rehab_arm_device_model_package_is_project_device_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    model_bytes = b"PK\x03\x04fake-urdf-zip"
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model-package",
        data={
            "robot_id": "rehab-arm-alpha",
            "project_id": "project-rehab",
            "file_name": "medical_arm.zip",
            "package_name": "medical_arm",
            "urdf_path": "medical_arm/urdf/medical_arm.urdf",
            "joint_count": "6",
            "mesh_count": "7",
            "mapping_json": '[{"jointName":"elbow","sourceName":"elbow","unit":"rad","direction":1,"offsetRad":0}]',
        },
        files={"file": ("medical_arm.zip", model_bytes, "application/zip")},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["sync_role"] == "non_realtime_telemetry_data_asset_only"
    assert payload["control_boundary"] == "model_preview_only_not_motion_permission"
    assert payload["model_url"].endswith("/devices/nanopi-m5/model-package/latest/file")

    latest = client.get("/api/rehab-arm/v1/devices/nanopi-m5/model-package/latest/file")
    assert latest.status_code == 200
    assert latest.content == model_bytes

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    model = device["device_model"]
    assert device["project_id"] == "project-rehab"
    assert model["record_type"] == "device_model"
    assert model["payload"]["urdf_path"] == "medical_arm/urdf/medical_arm.urdf"
    assert model["payload"]["joint_count"] == 6
    assert "can_frame" in dashboard.json()["data"]["safety_boundary"]["server_must_not_send"]
    get_settings.cache_clear()


def test_rehab_arm_simulation_readiness_is_data_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/simulation-readiness",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "report": {
                "schema_version": "rehab_arm_sim_env_check_v1",
                "ok": True,
                "readiness": "ready_with_fallback_sim",
                "joint_contract": {
                    "count": 5,
                    "names": [
                        "shoulder_lift_joint",
                        "elbow_lift_joint",
                        "shoulder_abduction_joint",
                        "upper_arm_rotation_joint",
                        "forearm_rotation_joint",
                    ],
                },
                "safety_note": "read-only simulation environment check",
                "errors": [],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["readiness"] == "ready_with_fallback_sim"
    assert payload["control_boundary"] == "simulation_readiness_only_not_motion_permission"

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    device = dashboard.json()["data"]["devices"][0]
    sim = device["simulation_readiness"]["payload"]["report"]
    assert sim["schema_version"] == "rehab_arm_sim_env_check_v1"
    assert sim["joint_contract"]["count"] == 5
    assert "can_frame" in dashboard.json()["data"]["safety_boundary"]["server_must_not_send"]
    get_settings.cache_clear()


def test_command_center_protocol_snapshot_wiring_vla_and_estop_are_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    snapshot = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/command-center/snapshot",
        json={
            "schema_version": "command_center_snapshot_v1",
            "ts_unix": 1780916046.11,
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "source": "nanopi_ros",
            "robot_render_state": {
                "schema_version": "robot_render_state_v1",
                "joint_names": ["jian_hengxiang_joint", "jian_zongxiang_joint", "wanbu_zongxiang_joint"],
                "positions": [0.1, 1.2, 0],
                "velocities": [0, 0, 0],
                "fresh": [True, True, False],
                "limit_clamped": [False, True, False],
            },
            "safety": {
                "schema_version": "safety_state_v1",
                "state": "limited",
                "motion_allowed": False,
                "control_mode": "logging_only",
                "detail": "prearm_not_ready",
                "heartbeat_age_ms": 90,
                "source": "m33_can_0x322",
            },
            "wiring_health": {
                "schema_version": "wiring_health_v1",
                "overall": "degraded",
                "checks": [
                    {"channel": "motor_4_feedback", "status": "stale", "fresh_ms": 1200, "evidence": "0x331 stale bit set"},
                    {"channel": "motor_1_wrist", "status": "not_wired", "fresh_ms": None, "evidence": "not installed"},
                ],
            },
            "model_state": {
                "schema_version": "rehab_arm_model_state_v1",
                "control_boundary": "model_suggestion_only_not_motion_permission",
                "model_results": [],
            },
            "control_boundary": "telemetry_snapshot_only_not_motion_permission",
        },
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["control_boundary"] == "telemetry_snapshot_only_not_motion_permission"

    latest_snapshot = client.get("/api/rehab-arm/v1/devices/nanopi-m5/command-center/snapshot")
    render = latest_snapshot.json()["data"]["robot_render_state"]
    assert render["schema_version"] == "robot_render_state_v1"
    assert render["fresh"] == [True, True, False]
    assert render["positions"][2] is None
    assert render["limit_clamped"][1] is True

    wiring = client.get("/api/rehab-arm/v1/devices/nanopi-m5/wiring-health")
    assert wiring.status_code == 200
    assert wiring.json()["data"]["control_boundary"] == "diagnostic_only_not_motion_permission"
    assert {item["status"] for item in wiring.json()["data"]["checks"]} >= {"stale", "not_wired"}

    safety = client.get("/api/rehab-arm/v1/devices/nanopi-m5/safety")
    assert safety.status_code == 200
    assert safety.json()["data"]["motion_allowed"] is False
    assert safety.json()["data"]["control_boundary"] == "safety_status_only_not_motion_permission"

    stream_offer = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/camera/stream-offer",
        json={
            "schema_version": "camera_stream_offer_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "camera_id": "front_rgb",
            "transport": "webrtc_or_mjpeg",
            "max_fps": 15,
            "max_width": 1280,
            "max_height": 720,
            "control_boundary": "camera_preview_only_not_motion_permission",
        },
    )
    assert stream_offer.status_code == 200
    assert stream_offer.json()["data"]["control_boundary"] == "camera_preview_only_not_motion_permission"
    assert client.get("/api/rehab-arm/v1/devices/nanopi-m5/camera/stream-offer").json()["data"]["transport"] == "webrtc_or_mjpeg"

    vla = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vla/task-requests",
        json={
            "schema_version": "vla_task_request_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "language_goal": "协助患者完成一次缓慢肘屈曲训练",
            "allowed_outputs": ["high_level_task", "dry_run_joint_trajectory_candidate"],
            "forbidden_outputs": ["can_frame"],
            "control_boundary": "vla_planning_request_only_not_motion_permission",
        },
    )
    assert vla.status_code == 200
    candidate = vla.json()["data"]
    assert candidate["schema_version"] == "vla_plan_candidate_v1"
    assert candidate["candidate"]["type"] == "dry_run_joint_trajectory"
    assert candidate["control_boundary"] == "vla_candidate_only_not_motion_permission"

    blocked = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/vla/task-requests",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "language_goal": "bad low level output",
            "allowed_outputs": ["can_frame"],
        },
    )
    assert blocked.status_code == 422

    estop = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/estop",
        json={
            "schema_version": "estop_request_v1",
            "request_id": "estop_20260608_0001",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "source": "command_center",
            "operator_id": "operator_001",
            "reason": "operator_pressed_estop",
            "requested_action": "disable_motor_output",
            "control_boundary": "estop_request_requires_m33_ack",
        },
    )
    assert estop.status_code == 200
    ack = estop.json()["data"]
    assert ack["accepted_by_gateway"] is True
    assert ack["m33_ack"] is False
    assert ack["state"] == "pending_m33_ack"
    assert ack["control_boundary"] == "not_safe_until_m33_ack"

    with client.websocket_connect("/api/rehab-arm/v1/devices/nanopi-m5/events?project_id=project-rehab") as websocket:
        hello = websocket.receive_json()
        event = websocket.receive_json()
    assert hello["control_boundary"] == "telemetry_stream_only_not_motion_permission"
    assert event["type"] == "command_center_snapshot_v1"
    assert event["data"]["robot_render_state"]["positions"][2] is None

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-rehab"})
    device = dashboard.json()["data"]["devices"][0]
    assert device["robot_render_state"]["positions"][2] is None
    assert device["camera_stream_offer"]["payload"]["control_boundary"] == "camera_preview_only_not_motion_permission"
    assert device["wiring_health"]["overall"] == "degraded"
    assert device["estop_ack"]["payload"]["m33_ack"] is False
    forbidden = dashboard.json()["data"]["safety_boundary"]["server_must_not_send"]
    assert {"raw_motor_position", "raw_motor_velocity", "m33_safety_override"} <= set(forbidden)
    get_settings.cache_clear()


def test_rehab_arm_model_relay_keeps_provider_secret_server_side_and_blocks_low_level_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_PROVIDER", "openai")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "gpt-safe-relay")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    get_settings.cache_clear()

    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "schema_version": "model_relay_request_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "voice_intent",
            "prompt": "患者说请帮我慢慢抬高手臂，只生成建议，不允许下发运动。",
            "requested_outputs": ["high_level_task", "dry_run_joint_trajectory_candidate", "model_state_suggestion"],
            "control_boundary": "model_relay_request_only_not_motion_permission",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "model_relay_response_v1"
    assert data["provider"]["configured"] is True
    assert data["provider"]["api_key_exposed_to_device"] is False
    assert "sk-test-secret-never-return" not in response.text
    assert data["suggestion"]["control_boundary"] == "model_suggestion_only_not_motion_permission"
    assert data["vla_plan_candidate"]["control_boundary"] == "vla_candidate_only_not_motion_permission"
    assert data["vla_plan_candidate"]["candidate"]["candidate_only_not_motion_permission"] is True
    assert "can_frame" in data["blocked_outputs"]

    blocked = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "schema_version": "model_relay_request_v1",
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "high_level_task",
            "prompt": "bad request",
            "requested_outputs": ["motor_torque"],
        },
    )
    assert blocked.status_code == 422

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": "project-rehab"})
    latest = dashboard.json()["data"]["devices"][0]["model_relay_response"]
    assert latest["record_type"] == "model_relay_response"
    assert latest["payload"]["relay_response"]["provider"]["api_key_exposed_to_device"] is False
    assert "sk-test-secret-never-return" not in dashboard.text
    get_settings.cache_clear()


def test_rehab_arm_project_model_relay_requires_project_member_and_device_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-project-secret-never-return")
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab Relay Scope")
    project_id = project["id"]
    device_id = f"nanopi-scope-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    payload = {
        "schema_version": "model_relay_request_v1",
        "robot_id": "rehab-arm-alpha",
        "device_id": device_id,
        "project_id": project_id,
        "input_type": "sensor_summary",
        "prompt": "把肌电疲劳摘要转成康复训练建议，只允许建议和 dry-run 候选。",
        "requested_outputs": ["high_level_task", "model_state_suggestion"],
    }
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay"

    anonymous = client.post(path, json=payload)
    assert anonymous.status_code == 401

    _outsider_user_id, outsider_email = register_user(client, f"rehab-outsider-{uuid4().hex[:8]}@example.com", "Rehab Outsider")
    outsider_token, _ = issue_session_token(client, outsider_email)
    outsider = client.post(path, headers=auth_headers(outsider_token), json=payload)
    assert outsider.status_code == 403

    response = client.post(path, headers=auth_headers(owner_token), json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "model_relay_response_v1"
    assert data["provider"]["api_key_exposed_to_device"] is False
    assert data["control_boundary"] == "model_relay_only_not_motion_permission"
    assert "sk-project-secret-never-return" not in response.text

    other_project = create_project(client, owner_token, name_prefix="Rehab Relay Other")
    mismatched = client.post(
        f"/api/rehab-arm/v1/projects/{other_project['id']}/devices/{device_id}/model/relay",
        headers=auth_headers(owner_token),
        json={**payload, "project_id": other_project["id"]},
    )
    assert mismatched.status_code == 422
    assert "does not belong" in mismatched.text
    get_settings.cache_clear()


def test_rehab_arm_model_relay_config_is_privileged_and_never_returns_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_COLLAB_ROOT", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path / "rehab"))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_BASE_URL", raising=False)
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_MODEL", raising=False)
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab Provider Config")
    project_id = project["id"]
    _outsider_user_id, outsider_email = register_user(client, f"relay-config-outsider-{uuid4().hex[:8]}@example.com", "Relay Config Outsider")
    outsider_token, _ = issue_session_token(client, outsider_email)
    path = f"/api/rehab-arm/v1/projects/{project_id}/model-relay/config"
    payload = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "sk-config-secret-never-return",
        "external_enabled": True,
    }

    anonymous = client.put(path, json=payload)
    assert anonymous.status_code == 401
    outsider = client.put(path, headers=auth_headers(outsider_token), json=payload)
    assert outsider.status_code in {403, 404}

    saved = client.put(path, headers=auth_headers(owner_token), json=payload)
    assert saved.status_code == 200
    data = saved.json()["data"]
    assert data["provider"] == "deepseek"
    assert data["base_url"] == "https://api.deepseek.com/v1"
    assert data["model"] == "deepseek-chat"
    assert data["external_enabled"] is True
    assert data["api_key_configured"] is True
    assert data["api_key_exposed_to_browser"] is False
    assert "sk-config-secret-never-return" not in saved.text

    read_back = client.get(path, headers=auth_headers(owner_token))
    assert read_back.status_code == 200
    assert read_back.json()["data"]["api_key_configured"] is True
    assert "sk-config-secret-never-return" not in read_back.text
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "REHAB_ARM_MODEL_RELAY_API_KEY='sk-config-secret-never-return'" in env_text
    assert get_settings().rehab_arm_model_relay_api_key == "sk-config-secret-never-return"
    get_settings.cache_clear()


def test_rehab_arm_model_relay_exported_token_is_scoped_to_one_project_device(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab Relay Token")
    project_id = project["id"]
    device_id = f"nanopi-token-{uuid4().hex[:8]}"
    other_device_id = f"nanopi-token-other-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": other_device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "nanopi test relay"},
    )
    assert token_response.status_code == 200
    token_data = token_response.json()["data"]
    relay_token = token_data["token"]
    assert relay_token.startswith("rehab-relay.v1.")
    assert "rehab_arm.model_relay.invoke" in token_data["scope"]
    assert "rehab_arm.xiaozhi.websocket" in token_data["scope"]
    assert "rehab_arm.vla_task.invoke" in token_data["scope"]

    payload = {
        "schema_version": "model_relay_request_v1",
        "robot_id": "rehab-arm-alpha",
        "device_id": device_id,
        "project_id": project_id,
        "input_type": "vla_context",
        "prompt": "scoped relay token call",
    }
    relay = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay",
        headers=auth_headers(relay_token),
        json=payload,
    )
    assert relay.status_code == 200
    assert relay.json()["data"]["control_boundary"] == "model_relay_only_not_motion_permission"

    config_read = client.get(
        f"/api/rehab-arm/v1/projects/{project_id}/model-relay/config",
        headers=auth_headers(relay_token),
    )
    assert config_read.status_code == 401

    wrong_device = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{other_device_id}/model/relay",
        headers=auth_headers(relay_token),
        json={**payload, "device_id": other_device_id},
    )
    assert wrong_device.status_code == 401
    get_settings.cache_clear()


def test_rehab_arm_project_vla_task_accepts_scoped_token_and_rejects_low_level_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab VLA Task")
    project_id = project["id"]
    device_id = f"nanopi-vla-{uuid4().hex[:8]}"
    other_device_id = f"nanopi-vla-other-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": other_device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "vla task"},
    )
    relay_token = token_response.json()["data"]["token"]
    payload = {
        "schema_version": "vla_task_request_v1",
        "robot_id": "rehab-arm-alpha",
        "device_id": device_id,
        "project_id": project_id,
        "language_goal": "患者请求缓慢抬高手臂，请生成只用于 MuJoCo dry-run 的高层动作候选。",
        "context_refs": {
            "vla_language_context_id": "lang_ctx_test",
            "vla_vision_context_id": "vision_ctx_test",
            "sensor_state_ref": "sensor_latest",
        },
    }
    response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/vla/task-requests",
        headers=auth_headers(relay_token),
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "vla_plan_candidate_v1"
    assert data["control_boundary"] == "vla_candidate_only_not_motion_permission"
    assert "mujoco_dry_run_passed" in data["requires"]

    wrong_device = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{other_device_id}/vla/task-requests",
        headers=auth_headers(relay_token),
        json={**payload, "device_id": other_device_id},
    )
    assert wrong_device.status_code == 401

    dangerous = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/vla/task-requests",
        headers=auth_headers(relay_token),
        json={**payload, "allowed_outputs": ["joint_trajectory"]},
    )
    assert dangerous.status_code == 422
    get_settings.cache_clear()


def test_rehab_arm_model_relay_calls_external_provider_through_server_guard(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_PROVIDER", "openai_compatible")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "rehab-safe-model")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()

    from app.modules.rehab_arm import service as rehab_service

    def fake_provider(settings, payload, render):
        assert settings.rehab_arm_model_relay_api_key == "sk-test-secret-never-return"
        assert payload["input_type"] == "voice_intent"
        assert render["schema_version"] == "robot_render_state_v1"
        return {
            "ok": True,
            "payload": {
                "summary": "识别到患者希望慢速抬高手臂，建议先生成仿真 dry-run 候选。",
                "label": "slow_raise_arm_request",
                "confidence": 0.82,
            },
        }

    monkeypatch.setattr(rehab_service, "_post_openai_compatible_chat", fake_provider)
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "voice_intent",
            "prompt": "请慢慢抬高手臂",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"]["external_call_enabled"] is True
    assert data["provider"]["external_call_ok"] is True
    assert data["provider"]["api_key_exposed_to_device"] is False
    assert "sk-test-secret-never-return" not in response.text
    result = data["suggestion"]["model_results"][0]
    assert result["result_code"] == 1
    assert result["label"] == "slow_raise_arm_request"
    assert result["confidence"] == 0.82
    assert data["operator_facing_reply"] == "识别到患者希望慢速抬高手臂，建议先生成仿真 dry-run 候选。"
    assert data["control_boundary"] == "model_relay_only_not_motion_permission"
    get_settings.cache_clear()


def test_rehab_arm_model_relay_surfaces_real_daily_chat_reply(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_PROVIDER", "qwen")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "qwen-plus")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()

    from app.modules.rehab_arm import service as rehab_service

    def fake_provider(_settings, _payload, _render):
        return {
            "ok": True,
            "payload": {
                "classification": "daily_chat",
                "summary": "我是平台侧模型中转，当前通过服务器密钥调用千问兼容接口。",
                "label": "daily_chat",
                "confidence": 0.89,
            },
        }

    monkeypatch.setattr(rehab_service, "_post_openai_compatible_chat", fake_provider)
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "voice_intent",
            "prompt": "你好，你现在接入的是哪个模型？",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classification"]["type"] == "daily_chat"
    assert data["provider"]["external_call_ok"] is True
    assert data["vla_language_gate"]["participates_in_vla_l"] is False
    assert data["vla_language_gate"]["route"] == "daily_chat_only"
    assert data["vla_language_context"]["participates_in_vla_l"] is False
    assert data["operator_facing_reply"] == "我是平台侧模型中转，当前通过服务器密钥调用千问兼容接口。"
    assert data["operator_facing_reply"] != "已收到。"
    assert "sk-test-secret-never-return" not in response.text
    get_settings.cache_clear()


def test_rehab_arm_model_relay_blocks_external_low_level_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "rehab-safe-model")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()

    from app.modules.rehab_arm import service as rehab_service

    def fake_provider(_settings, _payload, _render):
        return {"ok": False, "error": "external_response_blocked_low_level_output"}

    monkeypatch.setattr(rehab_service, "_post_openai_compatible_chat", fake_provider)
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "voice_intent",
            "prompt": "bad provider output",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"]["external_call_enabled"] is True
    assert data["provider"]["external_call_ok"] is False
    assert data["provider"]["external_call_error"] == "external_response_blocked_low_level_output"
    assert data["suggestion"]["model_results"][0]["result_code"] == 0
    assert data["vla_plan_candidate"]["candidate"]["candidate_only_not_motion_permission"] is True
    assert "direct_motor_command" in data["blocked_outputs"]
    get_settings.cache_clear()


def test_rehab_arm_model_relay_vla_lva_contract_outputs_high_level_action_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "rehab-safe-model")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()

    from app.modules.rehab_arm import service as rehab_service

    def fake_provider(_settings, payload, _render):
        assert payload["input_type"] == "vla_language_from_voice"
        return {
            "ok": True,
            "payload": {
                "classification": "vla_command",
                "summary": "患者请求开始缓慢抬手训练，先进入仿真和安全检查。",
                "label": "assist_slow_arm_raise",
                "confidence": 0.91,
                "operator_facing_reply": "已理解为康复训练请求，将先做安全检查和仿真。",
            },
        }

    monkeypatch.setattr(rehab_service, "_post_openai_compatible_chat", fake_provider)
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha", "project_id": "project-rehab"},
    )
    client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes",
        content=(
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="robot_id"\r\n\r\nrehab-arm-alpha\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="project_id"\r\n\r\nproject-rehab\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="camera_id"\r\n\r\nfront\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="frame_ts_unix"\r\n\r\n1780000000\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="width"\r\n\r\n640\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="height"\r\n\r\n480\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="scene_summary"\r\n\r\npatient seated, arm visible\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="detection_summary"\r\n\r\nshoulder and elbow visible\r\n'
            b"--boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="frame.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\nimage-bytes\r\n"
            b"--boundary--\r\n"
        ),
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )

    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/model/relay",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "project_id": "project-rehab",
            "input_type": "vla_language_from_voice",
            "prompt": "患者说想慢慢抬高手臂",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classification"]["type"] == "vla_command"
    assert data["vla_language_gate"]["participates_in_vla_l"] is True
    assert data["vla_language_gate"]["route"] == "vla_l_input"
    assert data["vla_language_context"]["participates_in_vla_l"] is True
    assert data["vla_language_context"]["schema_version"] == "vla_language_context_v1"
    assert data["vla_vision_context"]["schema_version"] == "vla_vision_context_v1"
    action = data["server_action_command"]
    assert action["schema_version"] == "server_to_nanopi_high_level_command_v1"
    assert action["action"]["kind"] == "rehab_training_request"
    assert action["source_refs"]["vla_language_context_id"] == data["vla_language_context"]["context_id"]
    assert action["source_refs"]["vla_vision_context_id"] == data["vla_vision_context"]["context_id"]
    assert action["source_refs"]["robot_context_snapshot_id"]
    assert action["requires_before_motion"] == [
        "active_profile_loaded",
        "wiring_state_checked",
        "safety_state_fresh",
        "mujoco_dry_run_required",
        "operator_confirmation_required",
        "m33_final_gate_required",
    ]
    assert action["allowed_next_steps"] == [
        "vla_candidate_gate",
        "mujoco_dry_run_review",
        "operator_review",
    ]
    assert action["control_boundary"] == "server_action_high_level_only_not_motion_permission"
    forbidden = [
        "can_frame",
        "can_frames",
        "motor_current",
        "motor_torque",
        "motor_velocity",
        "raw_motor_position",
        "raw_motor_velocity",
        "joint_trajectory",
        "trajectory_points",
        "m33_safety_override",
        "motion_allowed_override",
        "motion_permission_granted",
        "direct_motor_command",
    ]
    assert set(forbidden) <= set(data["blocked_outputs"])
    assert not any(token in response.text for token in forbidden if token not in data["blocked_outputs"])
    assert "sk-test-secret-never-return" not in response.text
    get_settings.cache_clear()


def test_rehab_arm_project_model_relay_accepts_m55_voice_multipart_with_scoped_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab M55 Voice")
    project_id = project["id"]
    device_id = f"nanopi-m55-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "m55 voice"},
    )
    relay_token = token_response.json()["data"]["token"]
    metadata = {
        "schema_version": "voice_capture_v1",
        "robot_id": "rehab-arm-alpha",
        "device_id": device_id,
        "project_id": project_id,
        "input_type": "vla_language_from_voice",
        "transcript": "请帮我开始缓慢抬手训练",
        "audio_format": "wav",
    }
    body = (
        b"--voice\r\n"
        b'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        + json.dumps(metadata).encode("utf-8")
        + b"\r\n--voice\r\n"
        b'Content-Disposition: form-data; name="file"; filename="voice.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        b"RIFF....WAVEfmt audio bytes"
        b"\r\n--voice--\r\n"
    )

    response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay",
        headers={**auth_headers(relay_token), "content-type": "multipart/form-data; boundary=voice"},
        content=body,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["input_type"] == "vla_language_from_voice"
    assert data["classification"]["type"] == "vla_command"
    assert data["vla_language_context"]["source"] == "m55_voice_http"
    assert data["vla_language_context"]["audio_ref"]["sha256"]
    assert data["server_action_command"]["control_boundary"] == "server_action_high_level_only_not_motion_permission"

    dangerous = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay",
        headers=auth_headers(relay_token),
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": device_id,
            "project_id": project_id,
            "input_type": "vla_language_from_voice",
            "prompt": "bad",
            "requested_outputs": ["joint_trajectory"],
        },
    )
    assert dangerous.status_code == 422
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_accepts_scoped_token_and_records_io(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi ws"},
    )
    token_data = token_response.json()["data"]
    relay_token = token_data["token"]
    assert "rehab_arm.xiaozhi.websocket" in token_data["scope"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws"

    try:
        with client.websocket_connect(path) as websocket:
            websocket.receive_json()
    except Exception:
        pass
    else:
        raise AssertionError("xiaozhi websocket must reject missing bearer token")

    legacy_token = _legacy_model_relay_only_token(project_id, device_id)
    try:
        with client.websocket_connect(path, headers=auth_headers(legacy_token)) as websocket:
            websocket.receive_json()
    except Exception:
        pass
    else:
        raise AssertionError("xiaozhi websocket must reject tokens without xiaozhi websocket scope")

    with client.websocket_connect(path, headers=auth_headers(relay_token)) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 3,
                "features": {"mcp": True},
                "transport": "websocket",
                "audio_params": {
                    "format": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "bits_per_sample": 16,
                    "frame_duration": 20,
                },
            }
        )
        hello_ack = websocket.receive_json()
        assert hello_ack["type"] == "hello"
        assert hello_ack["transport"] == "websocket"
        assert hello_ack["audio_params"]["sample_rate"] == 16000
        websocket.send_json({"session_id": "xz-session-1", "type": "listen", "state": "start", "mode": "auto_stop"})
        listen_ack = websocket.receive_json()
        assert listen_ack == {"session_id": "xz-session-1", "type": "listen", "state": "start"}
        websocket.send_bytes(b"\x00\x01" * 320)
        websocket.send_json({"session_id": "xz-session-1", "type": "listen", "state": "stop", "transcript": "你好，帮我看看训练状态"})
        stt = websocket.receive_json()
        assert stt["type"] == "stt"
        assert stt["text"] == "你好，帮我看看训练状态"
        llm = websocket.receive_json()
        assert llm["type"] == "llm"
        chat = websocket.receive_json()
        assert chat["type"] == "chat"
        assert chat["kind"] in {"daily_chat", "vla_command", "none"}
        assert "reply" in chat
        if chat["kind"] == "vla_command":
            assert chat["language_context"]
            assert "can_frame" not in json.dumps(chat, ensure_ascii=False)
        tts_start = websocket.receive_json()
        assert tts_start == {"session_id": "xz-session-1", "type": "tts", "state": "start"}
        tts_stop = websocket.receive_json()
        assert tts_stop == {"session_id": "xz-session-1", "type": "tts", "state": "stop"}
        stop_ack = websocket.receive_json()
        assert stop_ack == {"session_id": "xz-session-1", "type": "listen", "state": "stop"}

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    events = dashboard.json()["data"]["recent_events"]
    assert any(event["record_type"] == "xiaozhi_ws_input" for event in events)
    assert any(event["record_type"] == "xiaozhi_ws_reply" for event in events)
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]
    assert latest["payload"]["schema_version"] == "xiaozhi_session_v1"
    assert latest["payload"]["audio_bytes"] == 640
    assert latest["payload"]["ui_state"] in {"thinking", "speaking", "idle", "error"}
    assert latest["payload"]["control_boundary"] == "xiaozhi_voice_relay_only_not_motion_permission"
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_defaults_to_m55_v1_pcm_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_DEFAULT_PROTOCOL_VERSION", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_DEFAULT_AUDIO_FORMAT", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_ASR_EXTERNAL_ENABLED", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi M55 V1")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-m55v1-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi m55 v1 pcm"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(path, headers={**auth_headers(relay_token), "Client-Id": "m55-client-test"}) as websocket:
        websocket.send_json({"type": "hello", "transport": "websocket"})
        hello_ack = websocket.receive_json()
        assert hello_ack["type"] == "hello"
        assert hello_ack["version"] == 1
        assert hello_ack["audio_params"]["format"] == "pcm_s16le"
        assert hello_ack["audio_params"]["sample_rate"] == 16000
        websocket.send_json({"session_id": "xz-m55-v1", "type": "listen", "state": "start"})
        assert websocket.receive_json() == {"session_id": "xz-m55-v1", "type": "listen", "state": "start"}
        websocket.send_bytes(b"\x01\x00" * 960)
        websocket.send_json({"session_id": "xz-m55-v1", "type": "listen", "state": "stop"})
        stt = websocket.receive_json()
        assert stt["type"] == "stt"
        assert stt["audio_duration_ms"] == 60
        assert stt["audio_format"] == "pcm_s16le"
        assert stt["error"] == "asr_not_configured"

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    events = dashboard.json()["data"]["recent_events"]
    audio_events = [event for event in events if event["record_type"] == "xiaozhi_ws_input" and event["payload"].get("event") == "audio_frame"]
    assert audio_events
    payload = audio_events[-1]["payload"]
    assert payload["protocol_version"] == 1
    assert payload["binary_protocol"] == "xiaozhi_v1_raw_audio"
    assert payload["payload_bytes"] == 1920
    assert payload["audio_duration_ms"] == 60
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_accepts_official_opus_v3_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi Opus")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-opus-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi official opus ws"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(
        path,
        headers={
            **auth_headers(relay_token),
            "Protocol-Version": "3",
            "Device-Id": device_id,
            "Client-Id": "m55-client-test",
        },
    ) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 3,
                "features": {"mcp": True},
                "transport": "websocket",
                "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60},
            }
        )
        hello_ack = websocket.receive_json()
        assert hello_ack["type"] == "hello"
        assert hello_ack["version"] == 3
        assert hello_ack["audio_params"]["format"] == "opus"
        websocket.send_json({"session_id": "xz-opus", "type": "listen", "state": "start", "mode": "auto_stop"})
        assert websocket.receive_json() == {"session_id": "xz-opus", "type": "listen", "state": "start"}
        websocket.send_json({"session_id": "xz-opus", "type": "listen", "state": "detect", "text": "你好小智"})
        detect_ack = websocket.receive_json()
        assert detect_ack["type"] == "listen"
        assert detect_ack["state"] == "detect"
        opus_payload = b"\xf8\xff\xfe" * 20
        frame = bytes([0, 0]) + len(opus_payload).to_bytes(2, "big") + opus_payload
        websocket.send_bytes(frame)
        websocket.send_json({"session_id": "xz-opus", "type": "listen", "state": "stop"})
        stt = websocket.receive_json()
        assert stt["type"] == "stt"
        assert stt["audio_format"] == "opus"
        assert stt["official_audio_path"] is True
        assert stt["error"] == "opus_decode_not_configured"
        llm = websocket.receive_json()
        assert llm["type"] == "llm"
        assert llm["entered_llm"] is False
        chat = websocket.receive_json()
        assert chat["type"] == "chat"
        assert websocket.receive_json()["type"] == "tts"
        assert websocket.receive_json()["type"] == "tts"
        assert websocket.receive_json() == {"session_id": "xz-opus", "type": "listen", "state": "stop"}

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    events = dashboard.json()["data"]["recent_events"]
    audio_events = [event for event in events if event["record_type"] == "xiaozhi_ws_input" and event["payload"].get("event") == "audio_frame"]
    assert audio_events[-1]["payload"]["official_audio_path"] is True
    assert audio_events[-1]["payload"]["binary_protocol"] == "xiaozhi_v3"
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["official_audio_path"] is True
    assert latest["asr_audio_format"] == "opus"
    assert latest["ui_state"] in {"thinking", "speaking", "idle", "error"}
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_reports_missing_tts_configuration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_TTS_API_KEY", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_TTS_BASE_URL", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_TTS_MODEL", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_TTS_EXTERNAL_ENABLED", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi TTS Missing")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-tts-missing-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi tts missing"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(path, headers=auth_headers(relay_token)) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 3,
                "transport": "websocket",
                "features": {"mcp": True},
                "audio_params": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1, "bits_per_sample": 16, "frame_duration": 60},
            }
        )
        assert websocket.receive_json()["type"] == "hello"
        websocket.send_json({"session_id": "xz-tts-missing", "type": "listen", "state": "start", "mode": "auto_stop"})
        assert websocket.receive_json()["state"] == "start"
        pcm = b"\x01\x00" * 960
        websocket.send_bytes(bytes([0, 0]) + len(pcm).to_bytes(2, "big") + pcm)
        websocket.send_json({"session_id": "xz-tts-missing", "type": "listen", "state": "stop", "transcript": "请回一句话"})

        assert websocket.receive_json()["type"] == "stt"
        assert websocket.receive_json()["type"] == "llm"
        assert websocket.receive_json()["type"] == "chat"
        assert websocket.receive_json() == {"session_id": "xz-tts-missing", "type": "tts", "state": "start"}
        assert websocket.receive_json() == {"session_id": "xz-tts-missing", "type": "tts", "state": "stop"}
        assert websocket.receive_json() == {"session_id": "xz-tts-missing", "type": "listen", "state": "stop"}

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["event"] == "tts"
    assert latest["provider_configured"] is False
    assert latest["error"] == "tts_not_configured"
    assert latest["ui_state"] == "error"
    assert latest["last_error"] == "tts_not_configured"
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_parses_v3_pcm_frames_and_surfaces_asr_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("REHAB_ARM_MODEL_RELAY_API_KEY", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_ASR_API_KEY", raising=False)
    monkeypatch.delenv("REHAB_ARM_XIAOZHI_ASR_EXTERNAL_ENABLED", raising=False)
    get_settings.cache_clear()

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi PCM")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-pcm-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi pcm ws"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(path, headers=auth_headers(relay_token)) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 3,
                "features": {"mcp": True},
                "transport": "websocket",
                "audio_params": {
                    "format": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "bits_per_sample": 16,
                    "frame_duration": 60,
                },
            }
        )
        assert websocket.receive_json()["type"] == "hello"
        websocket.send_json({"session_id": "xz-v3-pcm", "type": "listen", "state": "start", "mode": "auto_stop"})
        assert websocket.receive_json() == {"session_id": "xz-v3-pcm", "type": "listen", "state": "start"}
        pcm = b"\x01\x00" * 960
        frame = bytes([0, 0]) + len(pcm).to_bytes(2, "big") + pcm
        websocket.send_bytes(frame)
        websocket.send_json({"session_id": "xz-v3-pcm", "type": "listen", "state": "stop"})

        stt = websocket.receive_json()
        assert stt["type"] == "stt"
        assert stt["text"] == ""
        assert stt["error"] == "asr_not_configured"
        assert stt["audio_duration_ms"] == 60
        llm = websocket.receive_json()
        assert llm["type"] == "llm"
        assert llm["entered_llm"] is False
        chat = websocket.receive_json()
        assert chat["type"] == "chat"
        assert chat["kind"] == "none"
        assert websocket.receive_json() == {"session_id": "xz-v3-pcm", "type": "tts", "state": "start"}
        assert websocket.receive_json() == {"session_id": "xz-v3-pcm", "type": "tts", "state": "stop"}
        assert websocket.receive_json() == {"session_id": "xz-v3-pcm", "type": "listen", "state": "stop"}

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    events = dashboard.json()["data"]["recent_events"]
    audio_events = [event for event in events if event["record_type"] == "xiaozhi_ws_input" and event["payload"].get("event") == "audio_frame"]
    assert audio_events
    payload = audio_events[-1]["payload"]
    assert payload["binary_protocol"] == "xiaozhi_v3"
    assert payload["frame_type"] == 0
    assert payload["payload_size"] == 1920
    assert payload["audio_bytes"] == 1920
    assert payload["audio_duration_ms"] == 60
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["event"] == "reply"
    assert latest["asr_called"] is False
    assert latest["asr_error"] == "asr_not_configured"
    assert latest["compatibility_mode"] == "debug_pcm_s16le_not_official_xiaozhi_audio"
    assert latest["entered_llm"] is False
    assert latest["ui_state"] in {"thinking", "idle", "error"}
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_listen_stop_clears_stale_asr_text(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    device_id = "nanopi-stale-asr"
    project_id = "project-stale-asr"
    record_xiaozhi_ws_event(
        {
            "record_type": "xiaozhi_ws_reply",
            "robot_id": "rehab-arm-alpha",
            "device_id": device_id,
            "project_id": project_id,
            "session_id": "old",
            "event": "reply",
            "kind": "daily_chat",
            "transcript": "old transcript",
            "reply": "old reply",
            "asr_text": "old transcript",
            "asr_ok": True,
            "entered_llm": True,
            "entered_tts": True,
        }
    )
    record_xiaozhi_ws_event(
        {
            "record_type": "xiaozhi_ws_input",
            "robot_id": "rehab-arm-alpha",
            "device_id": device_id,
            "project_id": project_id,
            "session_id": "new",
            "event": "listen_stop",
            "audio_params": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1, "frame_duration": 60},
            "audio_bytes": 1920,
            "audio_duration_ms": 60,
            "asr_called": True,
            "asr_ok": True,
            "asr_text": "",
            "asr_error": "asr_empty_text",
            "asr_audio_format": "pcm_s16le",
            "compatibility_mode": "debug_pcm_s16le_not_official_xiaozhi_audio",
        }
    )

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["event"] == "listen_stop"
    assert latest["asr_text"] == ""
    assert latest["transcript"] == ""
    assert latest["reply"] == ""
    assert latest["kind"] == ""
    assert latest["entered_llm"] is False
    assert latest["entered_tts"] is False
    assert latest["last_error"] == "asr_empty_text"
    assert latest["ui_state"] == "idle"
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_websocket_qwen_asr_pcm_then_llm_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_PROVIDER", "qwen")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "qwen-plus")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_ASR_PROVIDER", "qwen")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_ASR_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_ASR_MODEL", "qwen3-asr-flash")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_ASR_API_KEY", "sk-asr-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_ASR_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_MODEL", "qwen-tts")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_VOICE", "Cherry")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_API_KEY", "sk-tts-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()


    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            if isinstance(self.payload, bytes):
                return self.payload
            return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    tts_pcm = b"\x02\x00" * 960
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(tts_pcm)

    def fake_urlopen(request: urllib.request.Request, timeout: int = 0):
        if request.full_url == "https://dashscope.test/tts.wav":
            calls.append({"url": request.full_url, "auth_present": False, "body": {"model": "downloaded_tts_wav"}})
            return FakeResponse(wav_buffer.getvalue())
        body = json.loads((request.data or b"{}").decode("utf-8"))
        headers = dict(request.header_items())
        calls.append({"url": request.full_url, "auth_present": bool(headers.get("Authorization") or headers.get("authorization")), "body": body})
        if "/services/aigc/multimodal-generation/generation" in request.full_url:
            assert body["model"] == "qwen-tts"
            assert body["input"]["voice"] == "Cherry"
            assert body["input"]["text"]
            return FakeResponse({"output": {"audio": {"url": "https://dashscope.test/tts.wav"}}})
        if body["model"] == "qwen3-asr-flash":
            audio_data = body["messages"][0]["content"][0]["input_audio"]["data"]
            assert audio_data.startswith("data:audio/wav;base64,")
            return FakeResponse({"choices": [{"message": {"content": "请帮我开始缓慢抬手训练"}}]})
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "classification": "vla_command",
                                    "operator_facing_reply": "已识别为康复训练意图，只作为 VLA 语言输入。",
                                    "summary": "慢速抬手训练意图",
                                    "label": "assist_slow_arm_raise",
                                    "confidence": 0.88,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi ASR")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-asr-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi qwen asr ws"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(path, headers=auth_headers(relay_token)) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 3,
                "transport": "websocket",
                "features": {"mcp": True},
                "audio_params": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1, "bits_per_sample": 16, "frame_duration": 60},
            }
        )
        assert websocket.receive_json()["type"] == "hello"
        websocket.send_json({"session_id": "xz-qwen-asr", "type": "listen", "state": "start", "mode": "auto_stop"})
        assert websocket.receive_json()["state"] == "start"
        pcm = b"\x01\x00" * 960
        websocket.send_bytes(bytes([0, 0]) + len(pcm).to_bytes(2, "big") + pcm)
        websocket.send_json({"session_id": "xz-qwen-asr", "type": "listen", "state": "stop"})

        stt = websocket.receive_json()
        assert stt["type"] == "stt"
        assert stt["ok"] is True
        assert stt["text"] == "请帮我开始缓慢抬手训练"
        llm = websocket.receive_json()
        assert llm["type"] == "llm"
        assert llm["entered_llm"] is True
        chat = websocket.receive_json()
        assert chat["type"] == "chat"
        assert chat["kind"] == "vla_command"
        assert websocket.receive_json() == {"session_id": "xz-qwen-asr", "type": "tts", "state": "start"}
        audio_reply = websocket.receive_bytes()
        assert audio_reply == bytes([0, 0]) + len(tts_pcm).to_bytes(2, "big") + tts_pcm
        assert websocket.receive_json() == {"session_id": "xz-qwen-asr", "type": "tts", "state": "stop"}
        assert websocket.receive_json()["type"] == "listen"

    assert [call["body"]["model"] for call in calls] == ["qwen3-asr-flash", "qwen-plus", "qwen-tts", "downloaded_tts_wav"]
    assert all(call["auth_present"] for call in calls[:-1])
    assert calls[-1]["auth_present"] is False
    serialized_calls = json.dumps(calls, ensure_ascii=False)
    assert "sk-asr-secret-never-return" not in serialized_calls
    assert "sk-test-secret-never-return" not in serialized_calls
    assert "sk-tts-secret-never-return" not in serialized_calls
    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    events = dashboard.json()["data"]["recent_events"]
    reply_events = [event for event in events if event["record_type"] == "xiaozhi_ws_reply" and event["payload"].get("event") == "reply"]
    assert reply_events
    assert reply_events[-1]["payload"]["asr_called"] is True
    assert reply_events[-1]["payload"]["asr_ok"] is True
    assert reply_events[-1]["payload"]["entered_llm"] is True
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["event"] == "tts"
    assert latest["ok"] is True
    assert latest["audio_format"] == "pcm_s16le"
    assert latest["audio_bytes"] == len(tts_pcm)
    assert latest["ui_state"] == "speaking"
    assert latest["last_error"] == ""
    get_settings.cache_clear()


def test_rehab_arm_xiaozhi_tts_rejects_too_short_pcm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_PROVIDER", "qwen")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_MODEL", "qwen-plus")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_API_KEY", "sk-test-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_MODEL", "qwen-tts")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_VOICE", "Cherry")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_API_KEY", "sk-tts-secret-never-return")
    monkeypatch.setenv("REHAB_ARM_XIAOZHI_TTS_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, payload: dict | bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            if isinstance(self.payload, bytes):
                return self.payload
            return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    short_pcm = b"\x02\x00" * 320
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(short_pcm)

    def fake_urlopen(request: urllib.request.Request, timeout: int = 0):
        if request.full_url == "https://dashscope.test/short.wav":
            return FakeResponse(wav_buffer.getvalue())
        return FakeResponse({"output": {"audio": {"url": "https://dashscope.test/short.wav"}}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab XiaoZhi Short TTS")
    project_id = project["id"]
    device_id = f"nanopi-xiaozhi-short-tts-{uuid4().hex[:8]}"
    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": device_id, "robot_id": "rehab-arm-alpha", "project_id": project_id},
    )
    token_response = client.post(
        f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay-token",
        headers=auth_headers(owner_token),
        json={"ttl_seconds": 600, "label": "xiaozhi short tts"},
    )
    relay_token = token_response.json()["data"]["token"]
    path = f"/api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/xiaozhi/ws?robot_id=rehab-arm-alpha"

    with client.websocket_connect(path, headers=auth_headers(relay_token)) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1, "bits_per_sample": 16, "frame_duration": 60},
            }
        )
        assert websocket.receive_json()["type"] == "hello"
        websocket.send_json({"session_id": "xz-short-tts", "type": "listen", "state": "start"})
        assert websocket.receive_json()["state"] == "start"
        websocket.send_json({"session_id": "xz-short-tts", "type": "listen", "state": "stop", "transcript": "请说一句话"})
        assert websocket.receive_json()["type"] == "stt"
        assert websocket.receive_json()["type"] == "llm"
        assert websocket.receive_json()["type"] == "chat"
        assert websocket.receive_json() == {"session_id": "xz-short-tts", "type": "tts", "state": "start"}
        assert websocket.receive_json() == {"session_id": "xz-short-tts", "type": "tts", "state": "stop"}
        assert websocket.receive_json()["type"] == "listen"

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard", params={"project_id": project_id})
    latest = dashboard.json()["data"]["devices"][0]["xiaozhi_session"]["payload"]
    assert latest["event"] == "tts"
    assert latest["ok"] is False
    assert latest["audio_bytes"] == 0
    assert latest["error"].startswith("tts_audio_too_short:640<")
    assert latest["ui_state"] == "error"
    get_settings.cache_clear()
