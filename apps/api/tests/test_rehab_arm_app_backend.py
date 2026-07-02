from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def _issue_rehab_app_token() -> tuple[str, str]:
    email = f"rehab-app-{uuid4().hex}@example.com"
    register_user(client, email, "Rehab App Test User")
    return issue_session_token(client, email=email)


def test_rehab_arm_app_profile_device_plan_sync_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, owner_user_id = _issue_rehab_app_token()
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

    ble_plan_message = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages",
        headers=auth_headers(owner_token),
        json={
            "message_type": "training_plan_push",
            "plan_id": plan["id"],
            "client_message_id": "phone-plan-msg-001",
        },
    )
    assert ble_plan_message.status_code == 200
    ble_message = ble_plan_message.json()["data"]
    assert ble_message["message_type"] == "training_plan_push"
    assert ble_message["ack_status"] == "pending"
    assert ble_message["payload"]["schema_version"] == "rehab_app_ble_v1"
    assert ble_message["payload"]["device_id"] == "m33-rehab-arm-alpha"
    assert ble_message["payload"]["plan_id"] == plan["id"]
    assert ble_message["payload"]["plan_version"] == 1
    assert ble_message["payload"]["movement_type"] == "elbow_flexion"
    assert ble_message["payload"]["control_boundary"] == "ble_message_contract_only_not_motor_command"

    ble_ack = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages/{ble_message['id']}/ack",
        headers=auth_headers(owner_token),
        json={
            "ack_status": "acknowledged",
            "ack_payload": {"related_message_id": "phone-plan-msg-001", "accepted_for_review": True},
        },
    )
    assert ble_ack.status_code == 200
    assert ble_ack.json()["data"]["ack_status"] == "acknowledged"
    assert ble_ack.json()["data"]["ack_payload"]["m33_authority"] == "final_safety_authority"
    assert ble_ack.json()["data"]["ack_payload"]["control_boundary"] == "ble_ack_evidence_only_not_motion_permission"

    unsafe_ble_message = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages",
        headers=auth_headers(owner_token),
        json={
            "message_type": "device_status_request",
            "extra_payload": {"motor_torque": 0.4},
        },
    )
    assert unsafe_ble_message.status_code == 422
    assert unsafe_ble_message.json()["error"]["code"] == "BLE_PAYLOAD_NOT_ALLOWED"

    blocked_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert blocked_start.status_code == 409
    assert blocked_start.json()["error"]["code"] == "M33_ACCEPTANCE_REQUIRED"
    assert blocked_start.json()["error"]["details"]["control_boundary"] == "training_session_blocked_not_motion_permission"

    m33_reject = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={
            "sync_id": sync["id"],
            "sync_status": "m33_rejected",
            "m33_reason": "joint_limit_or_estop_not_clear",
            "firmware_version": "m33-0.3.2",
        },
    )
    assert m33_reject.status_code == 200
    assert m33_reject.json()["data"]["sync_status"] == "m33_rejected"

    device_status = client.get(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/status",
        headers=auth_headers(owner_token),
    )
    assert device_status.status_code == 200
    assert device_status.json()["data"]["m33_state"] == "m33_rejected"
    assert device_status.json()["data"]["control_boundary"] == "device_status_only_not_motion_permission"

    m33_accept = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync["id"], "sync_status": "m33_accepted", "m33_reason": "plan within configured safety envelope"},
    )
    assert m33_accept.status_code == 200
    assert m33_accept.json()["data"]["sync_status"] == "m33_accepted"

    edited_plan = client.patch(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}",
        headers=auth_headers(owner_token),
        json={"reps": 9},
    )
    assert edited_plan.status_code == 200
    assert edited_plan.json()["data"]["version"] == 2

    stale_acceptance_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert stale_acceptance_start.status_code == 409
    assert stale_acceptance_start.json()["error"]["details"]["accepted_plan_version"] == 1
    assert stale_acceptance_start.json()["error"]["details"]["required_plan_version"] == 2

    resync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert resync_response.status_code == 200
    resync = resync_response.json()["data"]
    assert resync["plan_version"] == 2
    reaccept_response = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": resync["id"], "sync_status": "m33_accepted", "m33_reason": "updated plan accepted"},
    )
    assert reaccept_response.status_code == 200

    allowed_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert allowed_start.status_code == 200
    active_session = allowed_start.json()["data"]
    assert active_session["status"] == "started"

    duplicate_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert duplicate_start.status_code == 409
    assert duplicate_start.json()["error"]["code"] == "ACTIVE_TRAINING_SESSION_EXISTS"
    assert duplicate_start.json()["error"]["details"]["active_session_id"] == active_session["id"]

    finish_active = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{active_session['id']}/finish",
        headers=auth_headers(owner_token),
        json={"completion_rate": 1, "user_note": "complete before next session"},
    )
    assert finish_active.status_code == 200

    next_start_after_finish = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert next_start_after_finish.status_code == 200
    assert next_start_after_finish.json()["data"]["status"] == "started"

    revoked_bind = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={
            "m33_device_id": "m33-rehab-arm-alpha",
            "ble_name": "ArmControl-Alpha",
            "firmware_version": "m33-0.3.3",
            "platform_project_id": project_id,
            "trust_status": "revoked",
        },
    )
    assert revoked_bind.status_code == 200
    assert revoked_bind.json()["data"]["trust_status"] == "revoked"

    revoked_status = client.get(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/status",
        headers=auth_headers(owner_token),
    )
    assert revoked_status.status_code == 200
    assert revoked_status.json()["data"]["trust_status"] == "revoked"

    revoked_diagnostic = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostic-upload",
        headers=auth_headers(owner_token),
        json={"snapshot_type": "revoked_device_seen", "m33_state": "revoked"},
    )
    assert revoked_diagnostic.status_code == 200

    revoked_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert revoked_sync.status_code == 409
    assert revoked_sync.json()["error"]["code"] == "DEVICE_REVOKED"

    revoked_ble = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages",
        headers=auth_headers(owner_token),
        json={"message_type": "device_status_request"},
    )
    assert revoked_ble.status_code == 409
    assert revoked_ble.json()["error"]["code"] == "DEVICE_REVOKED"

    revoked_m33_status = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": resync["id"], "sync_status": "m33_accepted", "m33_reason": "should be blocked"},
    )
    assert revoked_m33_status.status_code == 409
    assert revoked_m33_status.json()["error"]["code"] == "DEVICE_REVOKED"

    revoked_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert revoked_start.status_code == 409
    assert revoked_start.json()["error"]["code"] == "DEVICE_REVOKED"

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


def test_rehab_arm_app_device_unbind_freezes_action_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()

    device_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={"m33_device_id": "m33-unbind-alpha", "ble_name": "ArmControl-Unbind", "trust_status": "trusted"},
    )
    assert device_response.status_code == 200
    device = device_response.json()["data"]

    plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={"title": "Unbind safety plan", "movement_type": "elbow_flexion", "sets": 1, "reps": 2},
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["data"]

    sync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert sync_response.status_code == 200
    sync = sync_response.json()["data"]

    accepted = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync["id"], "sync_status": "m33_accepted", "m33_reason": "accepted before unbind"},
    )
    assert accepted.status_code == 200

    unbind = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/unbind",
        headers=auth_headers(owner_token),
        json={"reason": "patient changed paired controller"},
    )
    assert unbind.status_code == 200
    unbound_device = unbind.json()["data"]
    assert unbound_device["trust_status"] == "revoked"
    assert unbound_device["unbind_reason"] == "patient changed paired controller"
    assert unbound_device["control_boundary"] == "device_unbound_history_retained_not_motion_permission"

    status = client.get(f"/api/rehab-arm/app/v1/devices/{device['id']}/status", headers=auth_headers(owner_token))
    assert status.status_code == 200
    assert status.json()["data"]["trust_status"] == "revoked"

    diagnostic = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostic-upload",
        headers=auth_headers(owner_token),
        json={"snapshot_type": "after_unbind_seen", "m33_state": "unbound"},
    )
    assert diagnostic.status_code == 200

    blocked_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert blocked_sync.status_code == 409
    assert blocked_sync.json()["error"]["code"] == "DEVICE_REVOKED"

    blocked_ble = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages",
        headers=auth_headers(owner_token),
        json={"message_type": "device_status_request"},
    )
    assert blocked_ble.status_code == 409
    assert blocked_ble.json()["error"]["code"] == "DEVICE_REVOKED"

    blocked_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert blocked_start.status_code == 409
    assert blocked_start.json()["error"]["code"] == "DEVICE_REVOKED"


def test_rehab_arm_app_training_session_pause_resume_cancel_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()

    device_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={"m33_device_id": "m33-session-state-alpha", "ble_name": "ArmControl-State", "trust_status": "trusted"},
    )
    assert device_response.status_code == 200
    device = device_response.json()["data"]

    plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={"title": "Session state plan", "movement_type": "wrist_extension", "sets": 1, "reps": 3},
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["data"]

    sync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert sync_response.status_code == 200
    sync = sync_response.json()["data"]

    accepted = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync["id"], "sync_status": "m33_accepted", "m33_reason": "state test accepted"},
    )
    assert accepted.status_code == 200

    start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert start.status_code == 200
    session = start.json()["data"]

    pause = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/pause",
        headers=auth_headers(owner_token),
        json={"reason": "patient reported pain"},
    )
    assert pause.status_code == 200
    assert pause.json()["data"]["status"] == "paused"
    assert "patient reported pain" in pause.json()["data"]["user_note"]

    paused_progress = client.patch(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/progress",
        headers=auth_headers(owner_token),
        json={"completion_rate": 0.5},
    )
    assert paused_progress.status_code == 409
    assert paused_progress.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"

    duplicate_while_paused = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert duplicate_while_paused.status_code == 409
    assert duplicate_while_paused.json()["error"]["code"] == "ACTIVE_TRAINING_SESSION_EXISTS"

    resume = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/resume",
        headers=auth_headers(owner_token),
        json={"note": "therapist checked strap"},
    )
    assert resume.status_code == 200
    assert resume.json()["data"]["status"] == "in_progress"

    progress = client.patch(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/progress",
        headers=auth_headers(owner_token),
        json={"completion_rate": 0.4, "interruption_count": 1},
    )
    assert progress.status_code == 200
    assert progress.json()["data"]["status"] == "in_progress"

    cancel = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/cancel",
        headers=auth_headers(owner_token),
        json={"reason": "stop for calibration"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancelled"
    assert cancel.json()["data"]["ended_at"]

    finish_cancelled = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/finish",
        headers=auth_headers(owner_token),
        json={"completion_rate": 1},
    )
    assert finish_cancelled.status_code == 409
    assert finish_cancelled.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"

    report_cancelled = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/report",
        headers=auth_headers(owner_token),
    )
    assert report_cancelled.status_code == 409
    assert report_cancelled.json()["error"]["code"] == "TRAINING_SESSION_NOT_FINISHED"

    restart_after_cancel = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert restart_after_cancel.status_code == 200
    assert restart_after_cancel.json()["data"]["status"] == "started"


def test_rehab_arm_app_session_emg_and_intent_summary_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()

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

    sync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan_id}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device_id},
    )
    sync_id = sync_response.json()["data"]["id"]
    accept_response = client.post(
        f"/api/rehab-arm/app/v1/devices/{device_id}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync_id, "sync_status": "m33_accepted", "m33_reason": "accepted for record-only session"},
    )
    assert accept_response.status_code == 200

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

    unfinished_report = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/report",
        headers=auth_headers(owner_token),
    )
    assert unfinished_report.status_code == 409
    assert unfinished_report.json()["error"]["code"] == "TRAINING_SESSION_NOT_FINISHED"

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

    progress_after_finish = client.patch(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/progress",
        headers=auth_headers(owner_token),
        json={"completion_rate": 0.2},
    )
    assert progress_after_finish.status_code == 409
    assert progress_after_finish.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"

    finish_again = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/finish",
        headers=auth_headers(owner_token),
        json={"completion_rate": 1},
    )
    assert finish_again.status_code == 409
    assert finish_again.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"

    report_response = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/report",
        headers=auth_headers(owner_token),
    )
    assert report_response.status_code == 200
    report = report_response.json()["data"]
    assert report["session_id"] == session["id"]
    assert report["control_boundary"] == "training_report_review_only_not_medical_diagnosis_or_motion_permission"
    assert report["summary"]["movement_type"] == "wrist_flexion"
    assert report["summary"]["completion_rate"] == 0.9
    assert report["emg_overview"]["sample_count"] == 1
    assert report["emg_overview"]["muscles"] == ["biceps"]
    assert report["intent_overview"]["sample_count"] == 1
    assert report["intent_overview"]["predicted_actions"] == ["wrist_flexion"]
    assert report["intent_overview"]["avg_confidence"] == 0.81
    assert report["safety_overview"]["control_boundary"] == "m33_final_safety_authority"
    assert report["recommendations"] == ["continue_current_plan_with_m33_review_required"]
    assert report["latest_review"] is None

    repeat_report_response = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/report",
        headers=auth_headers(owner_token),
    )
    assert repeat_report_response.status_code == 200
    assert repeat_report_response.json()["data"]["id"] == report["id"]
    assert repeat_report_response.json()["data"]["emg_overview"]["sample_count"] == 1

    late_emg = client.post(
        "/api/rehab-arm/app/v1/emg/summary",
        headers=auth_headers(owner_token),
        json={
            "session_id": session["id"],
            "channel": "ch9",
            "muscle_name": "late_sample",
            "rms_avg": 0.9,
            "peak": 0.9,
            "activation_avg": 0.9,
            "fatigue_index": 0.9,
            "contact_quality": "late",
        },
    )
    assert late_emg.status_code == 409
    assert late_emg.json()["error"]["code"] == "TRAINING_REPORT_ALREADY_GENERATED"

    late_intent = client.post(
        "/api/rehab-arm/app/v1/intent/summary",
        headers=auth_headers(owner_token),
        json={
            "session_id": session["id"],
            "source": "m55",
            "predicted_action": "late_action",
            "confidence": 0.9,
            "topk": [],
            "stability_score": 0.9,
        },
    )
    assert late_intent.status_code == 409
    assert late_intent.json()["error"]["code"] == "TRAINING_REPORT_ALREADY_GENERATED"

    review_response = client.post(
        f"/api/rehab-arm/app/v1/training-reports/{report['id']}/reviews",
        headers=auth_headers(owner_token),
        json={
            "reviewer_role": "therapist",
            "review_status": "reviewed",
            "reviewer_note": "Adjust next plan and re-check fatigue after next session.",
            "next_step": "adjust_plan",
            "request_new_plan": True,
            "follow_up_payload": {"review_window_days": 3},
        },
    )
    assert review_response.status_code == 200
    review = review_response.json()["data"]
    assert review["report_id"] == report["id"]
    assert review["reviewer_role"] == "therapist"
    assert review["next_step"] == "adjust_plan"
    assert review["request_new_plan"] is True
    assert review["control_boundary"] == "training_report_review_only_not_medical_diagnosis_or_motion_permission"

    next_draft_response = client.post(
        f"/api/rehab-arm/app/v1/training-reports/{report['id']}/draft-next-plan",
        headers=auth_headers(owner_token),
    )
    assert next_draft_response.status_code == 200
    next_draft = next_draft_response.json()["data"]
    assert next_draft["control_boundary"] == "ai_draft_only_not_execution_permission"
    assert next_draft["context_snapshot"]["source"] == "training_report_review"
    assert next_draft["context_snapshot"]["report_id"] == report["id"]
    assert next_draft["context_snapshot"]["latest_review"]["id"] == review["id"]
    assert next_draft["generated_plan"]["control_boundary"] == "ai_draft_only_not_execution_permission"
    assert next_draft["generated_plan"]["sets"] == 1
    assert next_draft["generated_plan"]["reps"] == 5
    assert next_draft["generated_plan"]["safety_constraints"]["source_report_id"] == report["id"]

    next_plan_response = client.post(
        f"/api/rehab-arm/app/v1/ai-training-drafts/{next_draft['id']}/accept",
        headers=auth_headers(owner_token),
    )
    assert next_plan_response.status_code == 200
    next_plan = next_plan_response.json()["data"]
    assert next_plan["source"] == "ai_generated"
    assert next_plan["sets"] == 1
    assert next_plan["control_boundary"] == "training_plan_only_not_motor_command"

    blocked_next_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": next_plan["id"], "device_id": device_id},
    )
    assert blocked_next_start.status_code == 409
    assert blocked_next_start.json()["error"]["code"] == "M33_ACCEPTANCE_REQUIRED"

    session_report = client.get(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/report",
        headers=auth_headers(owner_token),
    )
    assert session_report.status_code == 200
    assert session_report.json()["data"]["id"] == report["id"]
    assert session_report.json()["data"]["latest_review"]["id"] == review["id"]

    reports = client.get("/api/rehab-arm/app/v1/training-reports", headers=auth_headers(owner_token))
    assert reports.status_code == 200
    assert reports.json()["data"][0]["id"] == report["id"]
    assert reports.json()["data"][0]["latest_review"]["id"] == review["id"]

    report_by_id = client.get(f"/api/rehab-arm/app/v1/training-reports/{report['id']}", headers=auth_headers(owner_token))
    assert report_by_id.status_code == 200
    assert report_by_id.json()["data"]["session_id"] == session["id"]
    assert report_by_id.json()["data"]["latest_review"]["id"] == review["id"]

    reviews = client.get(f"/api/rehab-arm/app/v1/training-reports/{report['id']}/reviews", headers=auth_headers(owner_token))
    assert reviews.status_code == 200
    assert reviews.json()["data"][0]["id"] == review["id"]

    bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap.status_code == 200
    assert bootstrap.json()["data"]["latest_report"]["id"] == report["id"]
    assert bootstrap.json()["data"]["latest_report"]["latest_review"]["id"] == review["id"]

    sync_run = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["training_reports", "training_report_reviews", "ai_training_drafts"]},
    )
    assert sync_run.status_code == 200
    assert sync_run.json()["data"]["summary"]["training_reports"] == 1
    assert sync_run.json()["data"]["summary"]["training_report_reviews"] == 1
    assert sync_run.json()["data"]["summary"]["ai_training_drafts"] == 1

    latest_emg = client.get("/api/rehab-arm/app/v1/emg/latest", headers=auth_headers(owner_token))
    assert latest_emg.status_code == 200
    assert latest_emg.json()["data"]["muscle_name"] == "biceps"

    emg_history = client.get("/api/rehab-arm/app/v1/emg/history", headers=auth_headers(owner_token))
    assert emg_history.status_code == 200
    assert emg_history.json()["data"][0]["muscle_name"] == "biceps"


def test_rehab_arm_app_plan_edit_ai_draft_and_platform_sync(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()

    bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap.status_code == 200
    assert bootstrap.json()["data"]["control_boundary"] == "app_bootstrap_evidence_only_not_motion_permission"

    draft_response = client.post(
        "/api/rehab-arm/app/v1/ai-training-drafts/generate",
        headers=auth_headers(owner_token),
        json={
            "input_text": "Need low intensity elbow flexion training after mild fatigue.",
            "context_snapshot": {"movement_type": "elbow_flexion", "sets": 2, "reps": 5},
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()["data"]
    assert draft["control_boundary"] == "ai_draft_only_not_execution_permission"
    assert draft["generated_plan"]["control_boundary"] == "ai_draft_only_not_execution_permission"

    open_drafts = client.get("/api/rehab-arm/app/v1/ai-training-drafts?status=open", headers=auth_headers(owner_token))
    assert open_drafts.status_code == 200
    assert open_drafts.json()["data"][0]["id"] == draft["id"]

    bootstrap_with_draft = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_draft.status_code == 200
    assert bootstrap_with_draft.json()["data"]["latest_open_ai_draft"]["id"] == draft["id"]

    accepted_response = client.post(
        f"/api/rehab-arm/app/v1/ai-training-drafts/{draft['id']}/accept",
        headers=auth_headers(owner_token),
    )
    assert accepted_response.status_code == 200
    plan = accepted_response.json()["data"]
    assert plan["source"] == "ai_generated"
    assert plan["control_boundary"] == "training_plan_only_not_motor_command"

    open_drafts_after_accept = client.get("/api/rehab-arm/app/v1/ai-training-drafts?status=open", headers=auth_headers(owner_token))
    assert open_drafts_after_accept.status_code == 200
    assert open_drafts_after_accept.json()["data"] == []

    accepted_drafts = client.get("/api/rehab-arm/app/v1/ai-training-drafts?status=accepted", headers=auth_headers(owner_token))
    assert accepted_drafts.status_code == 200
    assert accepted_drafts.json()["data"][0]["accepted_plan_id"] == plan["id"]

    bootstrap_after_accept = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_accept.status_code == 200
    assert bootstrap_after_accept.json()["data"]["latest_open_ai_draft"] is None

    patch_response = client.patch(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}",
        headers=auth_headers(owner_token),
        json={"reps": 7, "status": "active"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()["data"]
    assert patched["reps"] == 7
    assert patched["version"] == 2

    archive_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/archive",
        headers=auth_headers(owner_token),
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["status"] == "archived"

    device_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={"m33_device_id": "m33-archived-plan-alpha", "ble_name": "ArmControl-Archived", "trust_status": "trusted"},
    )
    assert device_response.status_code == 200
    device = device_response.json()["data"]

    archived_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert archived_sync.status_code == 409
    assert archived_sync.json()["error"]["code"] == "TRAINING_PLAN_NOT_USABLE"
    assert archived_sync.json()["error"]["details"]["plan_status"] == "archived"

    archived_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert archived_start.status_code == 409
    assert archived_start.json()["error"]["code"] == "TRAINING_PLAN_NOT_USABLE"

    sync_response = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["training_plans", "m33_decisions"]},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["control_boundary"] == "platform_sync_evidence_only_not_motion_permission"


def test_rehab_arm_app_offline_diagnostics_sync_and_audit_loop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()

    device_response = client.post(
        "/api/rehab-arm/app/v1/devices/bind",
        headers=auth_headers(owner_token),
        json={"m33_device_id": "m33-offline-alpha", "ble_name": "ArmControl-Offline", "trust_status": "trusted"},
    )
    assert device_response.status_code == 200
    device = device_response.json()["data"]

    diagnostic = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostic-upload",
        headers=auth_headers(owner_token),
        json={
            "snapshot_type": "m33_status",
            "firmware_version": "m33-0.4.0",
            "battery_level": 0.76,
            "m33_state": "waiting_for_plan",
            "payload": {"heartbeat_age_ms": 120, "active_limits": []},
        },
    )
    assert diagnostic.status_code == 200
    assert diagnostic.json()["data"]["control_boundary"] == "diagnostic_snapshot_only_not_motion_permission"

    diagnostics = client.get(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostics",
        headers=auth_headers(owner_token),
    )
    assert diagnostics.status_code == 200
    assert diagnostics.json()["data"][0]["m33_state"] == "waiting_for_plan"

    plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={"title": "Offline replay plan", "movement_type": "elbow_flexion", "sets": 1, "reps": 4},
    )
    plan_id = plan_response.json()["data"]["id"]
    sync_response = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{plan_id}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    sync_id = sync_response.json()["data"]["id"]
    accept_response = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync_id, "sync_status": "m33_accepted", "m33_reason": "offline replay plan accepted"},
    )
    assert accept_response.status_code == 200

    start_response = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan_id, "device_id": device["id"]},
    )
    assert start_response.status_code == 200
    session_id = start_response.json()["data"]["id"]

    queued = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-emg-001",
            "operation_type": "emg_summary",
            "resource_type": "emg_summary",
            "payload": {
                "session_id": session_id,
                "channel": "ch2",
                "muscle_name": "triceps",
                "rms_avg": 0.31,
                "peak": 0.55,
                "activation_avg": 0.41,
                "fatigue_index": 0.12,
                "contact_quality": "good",
            },
        },
    )
    assert queued.status_code == 200
    queue_item = queued.json()["data"]
    assert queue_item["replay_status"] == "queued"

    forbidden = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-motor-001",
            "operation_type": "motor_command",
            "resource_type": "motor",
            "payload": {"torque": 1.0},
        },
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["error"]["code"] == "OFFLINE_OPERATION_NOT_ALLOWED"

    replay = client.post(
        "/api/rehab-arm/app/v1/offline-queue/replay",
        headers=auth_headers(owner_token),
        json={"item_ids": [queue_item["id"]]},
    )
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["replayed_count"] == 1
    assert replay_data["items"][0]["replay_status"] == "replayed"

    latest_emg = client.get("/api/rehab-arm/app/v1/emg/latest", headers=auth_headers(owner_token))
    assert latest_emg.status_code == 200
    assert latest_emg.json()["data"]["muscle_name"] == "triceps"

    sync_run = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["training_plans", "training_sessions", "emg_summaries", "m33_decisions"]},
    )
    assert sync_run.status_code == 200
    assert sync_run.json()["data"]["summary"]["emg_summaries"] >= 1

    sync_runs = client.get("/api/rehab-arm/app/v1/platform/sync-runs", headers=auth_headers(owner_token))
    assert sync_runs.status_code == 200
    assert sync_runs.json()["data"][0]["control_boundary"] == "platform_sync_evidence_only_not_motion_permission"

    audit = client.get("/api/rehab-arm/app/v1/safety-audit", headers=auth_headers(owner_token))
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["data"]}
    assert "rehab_app.training_plan.m33_accepted" in actions
    assert "rehab_app.device.diagnostic_uploaded" in actions
