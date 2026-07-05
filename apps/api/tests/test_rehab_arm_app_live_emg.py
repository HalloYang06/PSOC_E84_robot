from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def _issue_rehab_app_token() -> tuple[str, str]:
    email = f"rehab-app-live-emg-{uuid4().hex}@example.com"
    register_user(client, email, "Rehab App Live EMG User")
    return issue_session_token(client, email=email)


def test_app_latest_emg_reads_project_sensor_state_with_m55_inference(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    token, _user_id = _issue_rehab_app_token()
    project = create_project(client, token, name_prefix="Rehab Arm App Live EMG")
    project_id = project["id"]
    headers = auth_headers(token)

    bind = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=headers,
        json={
            "m33_device_id": "m33-live-emg-alpha",
            "ble_name": "ArmControl-Live-EMG",
            "firmware_version": "m33-emg-can-dev",
            "trust_status": "trusted",
            "platform_project_id": project_id,
        },
    )
    assert bind.status_code == 200

    nanopi_device_id = f"nanopi-live-emg-{uuid4().hex[:8]}"
    sensor_state = client.post(
        f"/api/rehab-arm/v1/devices/{nanopi_device_id}/sensor-state",
        json={
            "robot_id": "rehab-arm-alpha",
            "device_id": nanopi_device_id,
            "project_id": project_id,
            "ts_unix": 1780000000.0,
            "source": "nanopi_sensor_node",
            "emg": {
                "schema_version": "rehab_arm_emg4_adc_v1",
                "source": "stm32_emg_sensor_node_can",
                "unit": "adc_count",
                "sample_rate_hz": 1000,
                "channels": [
                    {"channel": "ch1", "muscle": "biceps", "raw_adc": 1320, "value": 0.3223},
                    {"channel": "ch2", "muscle": "triceps", "raw_adc": 88, "value": 0.0215},
                    {"channel": "ch3", "muscle": "forearm_flexors", "raw_adc": 274, "value": 0.0669},
                ],
                "quality": {"status": "ok", "source_fresh": True},
            },
            "intent_prediction": {
                "source": "m55_emg_model",
                "predicted_action": "elbow_flexion",
                "confidence": 0.82,
            },
            "model_outputs": {
                "schema_version": "rehab_arm_m55_emg_intent_v1",
                "source": "m55_emg_model",
                "summary": "elbow_flexion",
                "candidates": [{"label": "elbow_flexion", "confidence": 0.82}],
            },
        },
    )
    assert sensor_state.status_code == 200

    latest = client.get("/api/rehab-arm/app/v1/emg/latest", headers=headers)
    assert latest.status_code == 200
    data = latest.json()["data"]
    assert data["source"] == "live_sensor_state"
    assert data["platform_project_id"] == project_id
    assert data["platform_device_id"] == nanopi_device_id
    assert data["channel_count"] == 4
    assert [channel["channel"] for channel in data["channels"]] == ["ch1", "ch2", "ch3", "ch4"]
    assert data["channels"][0]["raw_adc"] == 1320
    assert data["channels"][0]["voltage_v"] == 1.064
    assert data["channels"][3]["raw_adc"] == 0
    assert data["intent_prediction"]["predicted_action"] == "elbow_flexion"
    assert data["model_outputs"]["source"] == "m55_emg_model"

    bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=headers)
    assert bootstrap.status_code == 200
    assert bootstrap.json()["data"]["latest_emg"]["platform_device_id"] == nanopi_device_id
