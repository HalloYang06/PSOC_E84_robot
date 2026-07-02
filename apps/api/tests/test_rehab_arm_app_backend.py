from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import auth_headers, create_project, issue_session_token


client = TestClient(app)


def test_rehab_arm_app_profile_device_plan_sync_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Rehab Arm App")
    project_id = project["id"]

    profile_response = client.patch(
        "/api/rehab-arm/app/v1/me/profile",
        headers=auth_headers(owner_token),
        json={
            "name": "Patient Alpha",
            "role": "patient",
            "affected_side": "left",
            "rehab_stage": "early_active",
            "medical_constraints": ["no overhead motion"],
            "pain_baseline": 2,
        },
    )
    assert profile_response.status_code == 200
    profile = profile_response.json()["data"]
    assert profile["user_id"] == owner_user_id
    assert profile["role"] == "patient"
    assert profile["control_boundary"] == "profile_data_only_not_medical_diagnosis"

    bind_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={
            "m33_device_id": "m33-rehab-arm-alpha",
            "ble_name": "ArmControl-Alpha",
            "firmware_version": "m33-0.3.1",
            "platform_project_id": project_id,
            "trust_status": "trusted",
        },
    )
    assert bind_response.status_code == 200
    device = bind_response.json()["data"]
    assert device["m33_device_id"] == "m33-rehab-arm-alpha"
    assert device["platform_project_id"] == project_id
    assert device["control_boundary"] == "device_binding_only_not_motion_permission"

    plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={
            "title": "Elbow flexion intro",
            "source": "therapist",
            "goal": "low intensity elbow flexion",
            "target_joints": ["elbow"],
            "movement_type": "elbow_flexion",
            "sets": 3,
            "reps": 8,
            "duration_sec": 600,
            "target_angle_range": {"min_deg": 15, "max_deg": 70},
            "speed_level": "slow",
            "assist_level": 0.25,
            "emg_policy": {"intent_source": "m55", "assist_when_confidence_above": 0.72},
            "safety_constraints": {"stop_on_pain_report": True},
            "status": "active",
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["data"]
    assert plan["version"] == 1
    assert plan["control_boundary"] == "training_plan_only_not_motor_command"

    sync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert sync_response.status_code == 200
    sync = sync_response.json()["data"]
    assert sync["plan_id"] == plan["id"]
    assert sync["sync_status"] == "pending"
    assert sync["m33_authority"] == "required_before_motion"
    assert sync["control_boundary"] == "training_plan_sync_only_not_motion_permission"

    devices = client.get("/api/rehab-arm/app/v1/devices", headers=auth_headers(owner_token))
    assert devices.status_code == 200
    assert devices.json()["data"][0]["latest_sync"]["sync_status"] == "pending"

    forbidden = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={
            "title": "Bad plan",
            "movement_type": "elbow_flexion",
            "sets": 1,
            "reps": 1,
            "motor_torque": 0.8,
        },
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rehab_arm_app_session_emg_and_intent_summary_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = issue_session_token(client)

    device_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={"m33_device_id": "m33-session-alpha", "ble_name": "ArmControl-Session"},
    )
    device_id = device_response.json()["data"]["id"]

    plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={"title": "Wrist warmup", "movement_type": "wrist_flexion", "sets": 2, "reps": 6},
    )
    plan_id = plan_response.json()["data"]["id"]

    start_response = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan_id, "device_id": device_id},
    )
    assert start_response.status_code == 200
    session = start_response.json()["data"]
    assert session["status"] == "started"
    assert session["control_boundary"] == "training_session_record_only_not_motion_permission"

    emg_response = client.post(
        "/api/rehab-arm/app/v1/emg/summary",
        headers=auth_headers(owner_token),
        json={
            "session_id": session["id"],
            "channel": "ch1",
            "muscle_name": "biceps",
            "rms_avg": 0.42,
            "peak": 0.7,
            "activation_avg": 0.55,
            "fatigue_index": 0.18,
            "contact_quality": "good",
        },
    )
    assert emg_response.status_code == 200
    assert emg_response.json()["data"]["control_boundary"] == "emg_summary_only_not_motion_permission"

    intent_response = client.post(
        "/api/rehab-arm/app/v1/intent/summary",
        headers=auth_headers(owner_token),
        json={
            "session_id": session["id"],
            "source": "m55",
            "predicted_action": "wrist_flexion",
            "confidence": 0.81,
            "topk": [{"action": "wrist_flexion", "confidence": 0.81}],
            "stability_score": 0.76,
        },
    )
    assert intent_response.status_code == 200
    assert intent_response.json()["data"]["control_boundary"] == "intent_summary_only_not_motion_permission"

    finish_response = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/finish",
        headers=auth_headers(owner_token),
        json={
            "completion_rate": 0.9,
            "interruption_count": 1,
            "avg_assist_level": 0.2,
            "max_assist_level": 0.35,
            "m33_reject_count": 0,
            "pain_after": 3,
            "user_note": "felt mild fatigue",
        },
    )
    assert finish_response.status_code == 200
    finished = finish_response.json()["data"]
    assert finished["status"] == "finished"
    assert finished["pain_after"] == 3

    latest_emg = client.get("/api/rehab-arm/app/v1/emg/latest", headers=auth_headers(owner_token))
    assert latest_emg.status_code == 200
    assert latest_emg.json()["data"]["muscle_name"] == "biceps"
