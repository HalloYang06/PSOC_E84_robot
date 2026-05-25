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
    assert quality["control_boundary"] == "data_quality_only_not_motion_permission"
    assert quality["adapter"] == "rehab_arm_sync_v1"
    get_settings.cache_clear()


def test_rehab_arm_motor_safety_and_dashboard_are_non_realtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    client.post(
        "/api/rehab-arm/v1/devices/register",
        json={"device_id": "nanopi-m5", "robot_id": "rehab-arm-alpha"},
    )
    safety = client.post(
        "/api/rehab-arm/v1/devices/nanopi-m5/safety-state",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": "nanopi-m5",
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
        },
    )
    assert motor.status_code == 200
    assert motor.json()["data"]["motor_count"] == 1

    dashboard = client.get("/api/rehab-arm/v1/devices/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()["data"]
    assert data["safety_boundary"]["m33_final_authority"] is True
    assert "can_frame" in data["safety_boundary"]["server_must_not_send"]
    assert data["devices"][0]["device_id"] == "nanopi-m5"
    assert data["devices"][0]["safety_state"] == "limited"
    assert data["devices"][0]["motion_allowed"] is False
    assert data["devices"][0]["motor_state"]["payload"]["motors"][0]["joint_name"] == "elbow"
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
    assert device["camera_keyframe"]["payload"]["detection_summary"] == "hand and elbow visible"
    get_settings.cache_clear()
