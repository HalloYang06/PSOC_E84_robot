from __future__ import annotations

from pathlib import Path
import hashlib

from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


client = TestClient(app)


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


def test_rehab_arm_board_manifest_upload_is_data_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/board-manifest",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
            "manifest": {
                "schema_version": "linux_board_manifest_v1",
                "device_id": "nanopi-m5",
                "robot_id": "rehab-arm-alpha",
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
