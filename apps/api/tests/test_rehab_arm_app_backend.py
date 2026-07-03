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


def _pass_preflight(token: str, plan_id: str, device_id: str, sync_id: str, *, pain_before: float = 1.0) -> dict:
    response = client.post(
        "/api/rehab-arm/app/v1/training-preflight",
        headers=auth_headers(token),
        json={
            "plan_id": plan_id,
            "device_id": device_id,
            "sync_id": sync_id,
            "checked_by_role": "patient",
            "pain_before": pain_before,
            "checklist": {
                "device_worn_correctly": True,
                "pain_within_limit": True,
                "stop_explained": True,
                "m33_plan_accepted": True,
            },
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def _preflight_payload(plan_id: str, device_id: str, sync_id: str, *, pain_before: float = 1.0, checked_by_role: str = "patient") -> dict:
    return {
        "plan_id": plan_id,
        "device_id": device_id,
        "sync_id": sync_id,
        "checked_by_role": checked_by_role,
        "pain_before": pain_before,
        "checklist": {
            "device_worn_correctly": True,
            "pain_within_limit": True,
            "stop_explained": True,
            "m33_plan_accepted": True,
        },
    }


def test_rehab_arm_app_profile_device_plan_sync_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, owner_user_id = _issue_rehab_app_token()
    project = create_project(client, owner_token, name_prefix="Rehab Arm App")
    project_id = project["id"]

    empty_bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert empty_bootstrap.status_code == 200
    assert empty_bootstrap.json()["data"]["onboarding_guide"]["status"] == "incomplete"
    assert empty_bootstrap.json()["data"]["onboarding_guide"]["next_step"]["code"] == "PROFILE_REQUIRED"
    assert {item["code"] for item in empty_bootstrap.json()["data"]["onboarding_guide"]["actions"]} == {
        "PROFILE_REQUIRED",
        "TRUSTED_DEVICE_REQUIRED",
        "TRAINING_PLAN_REQUIRED",
    }
    assert empty_bootstrap.json()["data"]["primary_start_guide"] is None
    empty_home_status = empty_bootstrap.json()["data"]["home_status_guide"]
    assert empty_home_status["tone"] == "info"
    assert empty_home_status["primary_action"]["code"] == "PROFILE_REQUIRED"
    assert {item["code"] for item in empty_home_status["secondary_actions"]} == {"TRUSTED_DEVICE_REQUIRED", "TRAINING_PLAN_REQUIRED"}
    assert "疼痛基线" in empty_home_status["body"]
    assert "onboarding_incomplete" in empty_home_status["blockers"]
    assert empty_home_status["progress"]["stage"] == "setup"
    assert empty_home_status["progress"]["stage_title"] == "先完成首次设置"
    assert empty_home_status["progress"]["stage_tone"] == "info"
    assert empty_home_status["progress"]["remaining"] > 0
    assert empty_home_status["progress"]["next_item"]["code"] == "onboarding"
    onboarding_progress = next(item for item in empty_home_status["progress"]["items"] if item["code"] == "onboarding")
    assert onboarding_progress["done"] is False
    assert onboarding_progress["title"] == "首次设置"
    assert "onboarding_incomplete" in onboarding_progress["related_blocker_codes"]
    assert "PROFILE_REQUIRED" in onboarding_progress["related_action_codes"]
    assert empty_home_status["blocker_details"][0]["code"] == "onboarding_incomplete"
    assert empty_bootstrap.json()["data"]["care_summary"]["primary_blocker"]["code"] == "onboarding_incomplete"
    assert empty_home_status["primary_blocker"]["code"] == "onboarding_incomplete"
    assert empty_home_status["blocker_details"][0]["severity"] == "warning"
    assert empty_home_status["blocker_details"][0]["title"] == "完成首次设置"
    assert "绑定可信 M33" in empty_home_status["blocker_details"][0]["clear_condition"]
    assert "PROFILE_REQUIRED" in empty_home_status["blocker_details"][0]["related_action_codes"]
    onboarding_group = empty_home_status["action_groups"]["blocker_related"][0]
    assert onboarding_group["blocker_code"] == "onboarding_incomplete"
    assert {item["code"] for item in onboarding_group["actions"]} == {"PROFILE_REQUIRED", "TRUSTED_DEVICE_REQUIRED", "TRAINING_PLAN_REQUIRED"}
    assert empty_home_status["control_boundary"] == "app_home_status_guide_evidence_only_not_motion_permission"
    assert empty_bootstrap.json()["data"]["device_operational_guide"]["status"] == "device_required"
    assert "BIND_TRUSTED_DEVICE" in {item["code"] for item in empty_bootstrap.json()["data"]["device_operational_guide"]["actions"]}

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
    bootstrap_after_basics = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_basics.status_code == 200
    onboarding = bootstrap_after_basics.json()["data"]["onboarding_guide"]
    assert onboarding["status"] == "complete"
    assert onboarding["next_step"] is None
    assert onboarding["actions"] == []
    assert bootstrap_after_basics.json()["data"]["primary_start_guide"]["next_action"]["code"] == "M33_ACCEPTANCE_REQUIRED"
    assert {"VIEW_START_GUIDE", "CHECK_START_READINESS", "M33_ACCEPTANCE_REQUIRED"}.issubset(
        {item["code"] for item in bootstrap_after_basics.json()["data"]["primary_start_guide"]["actions"]}
    )
    assert bootstrap_after_basics.json()["data"]["daily_action_guide"]["next_action"]["code"] == "M33_ACCEPTANCE_REQUIRED"
    assert bootstrap_after_basics.json()["data"]["device_operational_guide"]["status"] == "plan_sync_required"
    assert "SYNC_PLAN_TO_M33" in {item["code"] for item in bootstrap_after_basics.json()["data"]["device_operational_guide"]["actions"]}
    care_summary_after_basics = bootstrap_after_basics.json()["data"]["care_summary"]
    assert care_summary_after_basics["status"] == "attention_required"
    assert care_summary_after_basics["can_start"] is False
    assert care_summary_after_basics["counts"]["reports_pending_review"] == 0
    start_blocker = care_summary_after_basics["blocker_details"][0]
    assert start_blocker["code"] == "start_readiness_blocked"
    assert care_summary_after_basics["primary_blocker"]["code"] == "start_readiness_blocked"
    assert start_blocker["severity"] == "warning"
    assert "can_start=true" in start_blocker["clear_condition"]
    assert "M33_ACCEPTANCE_REQUIRED" in start_blocker["related_action_codes"]
    start_home_status = bootstrap_after_basics.json()["data"]["home_status_guide"]
    assert start_home_status["primary_blocker"]["code"] == "start_readiness_blocked"
    assert start_home_status["progress"]["stage"] == "resolve_blockers"
    assert start_home_status["progress"]["stage_title"] == "先处理阻塞事项"
    assert start_home_status["progress"]["stage_tone"] == "warning"
    assert start_home_status["progress"]["next_item"]["code"] == "start_ready"
    assert next(item for item in start_home_status["progress"]["items"] if item["code"] == "onboarding")["done"] is True
    start_ready_progress = next(item for item in start_home_status["progress"]["items"] if item["code"] == "start_ready")
    assert start_ready_progress["done"] is False
    assert "start_readiness_blocked" in start_ready_progress["related_blocker_codes"]
    assert "CHECK_START_READINESS" in start_ready_progress["related_action_codes"]
    start_group = next(item for item in start_home_status["action_groups"]["blocker_related"] if item["blocker_code"] == "start_readiness_blocked")
    assert {"VIEW_START_GUIDE", "CHECK_START_READINESS", "M33_ACCEPTANCE_REQUIRED"}.issubset({item["code"] for item in start_group["actions"]})

    contraindicated_plan_response = client.post(
        "/api/rehab-arm/app/v1/training-plans",
        headers=auth_headers(owner_token),
        json={
            "title": "Shoulder overhead reach",
            "source": "therapist",
            "goal": "shoulder range check",
            "target_joints": ["shoulder"],
            "movement_type": "shoulder_overhead_reach",
            "sets": 1,
            "reps": 3,
            "target_angle_range": {"min_deg": 20, "max_deg": 120},
            "status": "active",
        },
    )
    assert contraindicated_plan_response.status_code == 200
    contraindicated_plan = contraindicated_plan_response.json()["data"]
    blocked_constraint_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert blocked_constraint_sync.status_code == 409
    assert blocked_constraint_sync.json()["error"]["code"] == "TRAINING_PLAN_CONTRAINDICATED"
    assert blocked_constraint_sync.json()["error"]["details"]["violations"][0]["reason"] == "overhead_or_shoulder_motion"
    therapist_reviewed_plan = client.patch(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}",
        headers=auth_headers(owner_token),
        json={"safety_constraints": {"therapist_constraint_reviewed": True, "review_note": "limited supervised range only"}},
    )
    assert therapist_reviewed_plan.status_code == 200
    still_blocked_constraint_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert still_blocked_constraint_sync.status_code == 409
    assert still_blocked_constraint_sync.json()["error"]["code"] == "TRAINING_PLAN_CONTRAINDICATED"
    constraint_review = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}/constraint-reviews",
        headers=auth_headers(owner_token),
        json={
            "reviewer_role": "therapist",
            "review_status": "conditional",
            "reviewed_constraints": ["no overhead motion"],
            "review_note": "limited supervised range only",
        },
    )
    assert constraint_review.status_code == 200
    assert constraint_review.json()["data"]["plan_version"] == 2
    assert constraint_review.json()["data"]["review_status"] == "conditional"
    constraint_reviews = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}/constraint-reviews",
        headers=auth_headers(owner_token),
    )
    assert constraint_reviews.status_code == 200
    assert constraint_reviews.json()["data"][0]["id"] == constraint_review.json()["data"]["id"]
    reviewed_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{contraindicated_plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert reviewed_sync.status_code == 200

    constraint_sync = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["plan_constraint_reviews"]},
    )
    assert constraint_sync.status_code == 200
    assert constraint_sync.json()["data"]["summary"]["plan_constraint_reviews"] == 1

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
    bootstrap_pending_m33 = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_pending_m33.status_code == 200
    pending_device_guide = bootstrap_pending_m33.json()["data"]["device_operational_guide"]
    assert pending_device_guide["status"] == "m33_decision_pending"
    assert {"REQUEST_DEVICE_STATUS", "RECORD_M33_DECISION"}.issubset({item["code"] for item in pending_device_guide["actions"]})
    pending_home_status = bootstrap_pending_m33.json()["data"]["home_status_guide"]
    assert pending_home_status["primary_action"]["code"] == "M33_ACCEPTANCE_REQUIRED"
    assert {"VIEW_START_GUIDE", "CHECK_START_READINESS"}.issubset({item["code"] for item in pending_home_status["secondary_actions"]})

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
    bootstrap_rejected_m33 = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_rejected_m33.status_code == 200
    rejected_device_guide = bootstrap_rejected_m33.json()["data"]["device_operational_guide"]
    assert rejected_device_guide["status"] == "m33_rejected_review_required"
    assert "RESYNC_PLAN_AFTER_REVIEW" in {item["code"] for item in rejected_device_guide["actions"]}

    m33_accept = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": sync["id"], "sync_status": "m33_accepted", "m33_reason": "plan within configured safety envelope"},
    )
    assert m33_accept.status_code == 200
    assert m33_accept.json()["data"]["sync_status"] == "m33_accepted"
    bootstrap_accepted_m33 = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_accepted_m33.status_code == 200
    accepted_device_guide = bootstrap_accepted_m33.json()["data"]["device_operational_guide"]
    assert accepted_device_guide["status"] == "m33_acceptance_ready"
    assert accepted_device_guide["heartbeat_status"] == "seen"
    assert "CHECK_START_READINESS" in {item["code"] for item in accepted_device_guide["actions"]}

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

    missing_preflight_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert missing_preflight_start.status_code == 409
    assert missing_preflight_start.json()["error"]["code"] == "PREFLIGHT_CHECK_REQUIRED"
    readiness_missing_preflight = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/readiness",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert readiness_missing_preflight.status_code == 200
    readiness_checks = {item["name"]: item for item in readiness_missing_preflight.json()["data"]["checks"]}
    assert readiness_missing_preflight.json()["data"]["can_start"] is False
    assert readiness_checks["m33_acceptance"]["status"] == "passed"
    assert readiness_checks["preflight"]["code"] == "PREFLIGHT_CHECK_REQUIRED"
    start_guide_missing_preflight = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/start-guide",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert start_guide_missing_preflight.status_code == 200
    guide_data = start_guide_missing_preflight.json()["data"]
    assert guide_data["can_start"] is False
    assert guide_data["next_action"]["code"] == "PREFLIGHT_CHECK_REQUIRED"
    assert guide_data["next_action"]["method"] == "POST"
    assert guide_data["next_action"]["endpoint"] == "/api/rehab-arm/app/v1/training-preflight"
    assert guide_data["control_boundary"] == "training_start_guide_evidence_only_not_motion_permission"

    high_pain_preflight = client.post(
        "/api/rehab-arm/app/v1/training-preflight",
        headers=auth_headers(owner_token),
        json=_preflight_payload(plan["id"], device["id"], resync["id"], pain_before=4.0),
    )
    assert high_pain_preflight.status_code == 409
    assert high_pain_preflight.json()["error"]["code"] == "PREFLIGHT_PAIN_REVIEW_REQUIRED"
    assert high_pain_preflight.json()["error"]["details"]["pain_baseline"] == 2

    therapist_preflight = client.post(
        "/api/rehab-arm/app/v1/training-preflight",
        headers=auth_headers(owner_token),
        json=_preflight_payload(plan["id"], device["id"], resync["id"], pain_before=4.0, checked_by_role="therapist"),
    )
    assert therapist_preflight.status_code == 200
    assert therapist_preflight.json()["data"]["checked_by_role"] == "therapist"

    preflight = _pass_preflight(owner_token, plan["id"], device["id"], resync["id"])
    assert preflight["plan_version"] == 2
    readiness_ready = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/readiness",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert readiness_ready.status_code == 200
    assert readiness_ready.json()["data"]["can_start"] is True
    start_guide_ready = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/start-guide",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert start_guide_ready.status_code == 200
    assert start_guide_ready.json()["data"]["can_start"] is True
    assert start_guide_ready.json()["data"]["next_action"]["code"] == "READY_TO_START"
    assert start_guide_ready.json()["data"]["next_action"]["payload_hint"] == {"plan_id": plan["id"], "device_id": device["id"]}
    preflight_history = client.get(
        "/api/rehab-arm/app/v1/training-preflight",
        headers=auth_headers(owner_token),
        params={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert preflight_history.status_code == 200
    preflight_history_items = preflight_history.json()["data"]
    assert any(item["id"] == preflight["id"] for item in preflight_history_items)
    bootstrap_after_preflight = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_preflight.status_code == 200
    latest_preflight = bootstrap_after_preflight.json()["data"]["latest_preflight"]
    assert latest_preflight["plan_id"] == plan["id"]
    assert latest_preflight["device_id"] == device["id"]
    assert latest_preflight["sync_id"] == resync["id"]
    primary_guide = bootstrap_after_preflight.json()["data"]["primary_start_guide"]
    assert primary_guide["can_start"] is True
    assert primary_guide["next_action"]["code"] == "READY_TO_START"
    assert primary_guide["readiness"]["plan_id"] == plan["id"]
    assert primary_guide["readiness"]["device_id"] == device["id"]
    ready_home_status = bootstrap_after_preflight.json()["data"]["home_status_guide"]
    assert ready_home_status["progress"]["stage"] == "ready_to_start"
    assert ready_home_status["progress"]["stage_title"] == "可以记录训练开始"
    assert ready_home_status["progress"]["stage_tone"] == "success"
    assert ready_home_status["progress"]["remaining"] == 0
    assert ready_home_status["progress"]["next_item"] is None
    ready_progress_item = next(item for item in ready_home_status["progress"]["items"] if item["code"] == "start_ready")
    assert ready_progress_item["done"] is True
    assert ready_progress_item["title"] == "开始条件"

    allowed_start = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan["id"], "device_id": device["id"]},
    )
    assert allowed_start.status_code == 200
    active_session = allowed_start.json()["data"]
    assert active_session["status"] == "started"
    readiness_active_session = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan['id']}/readiness",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert readiness_active_session.status_code == 200
    active_checks = {item["name"]: item for item in readiness_active_session.json()["data"]["checks"]}
    assert active_checks["device_session_available"]["code"] == "ACTIVE_TRAINING_SESSION_EXISTS"
    bootstrap_with_active = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_active.status_code == 200
    assert bootstrap_with_active.json()["data"]["active_session"]["id"] == active_session["id"]
    assert bootstrap_with_active.json()["data"]["primary_start_guide"]["next_action"]["code"] == "ACTIVE_TRAINING_SESSION_EXISTS"
    assert bootstrap_with_active.json()["data"]["daily_action_guide"]["next_action"]["code"] == "RECOVER_ACTIVE_SESSION"
    assert "active_session" in bootstrap_with_active.json()["data"]["care_summary"]["blockers"]
    active_recovery_codes = {item["code"] for item in bootstrap_with_active.json()["data"]["session_recovery_guide"]["actions"]}
    assert {"RECORD_PROGRESS", "FINISH_SESSION", "CANCEL_SESSION"}.issubset(active_recovery_codes)

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

    _pass_preflight(owner_token, plan["id"], device["id"], resync["id"])

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

    _pass_preflight(owner_token, plan["id"], device["id"], sync["id"])

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
    paused_bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert paused_bootstrap.status_code == 200
    assert paused_bootstrap.json()["data"]["active_session"]["id"] == session["id"]
    assert paused_bootstrap.json()["data"]["active_session"]["status"] == "paused"
    recovery_guide = paused_bootstrap.json()["data"]["session_recovery_guide"]
    assert recovery_guide["status"] == "paused_can_resume"
    assert recovery_guide["control_boundary"] == "session_recovery_guide_evidence_only_not_motion_permission"
    assert "RESUME_SESSION" in {item["code"] for item in recovery_guide["actions"]}

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

    _pass_preflight(owner_token, plan["id"], device["id"], sync["id"])

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

    _pass_preflight(owner_token, plan_id, device_id, sync_id)

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

    fit_event = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/safety-events",
        headers=auth_headers(owner_token),
        json={"event_type": "device_fit_issue", "severity": "warning", "source": "patient", "note": "strap felt loose"},
    )
    assert fit_event.status_code == 200
    assert fit_event.json()["data"]["control_boundary"] == "session_safety_event_evidence_only_not_motion_permission"

    pain_event = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/safety-events",
        headers=auth_headers(owner_token),
        json={"event_type": "pain_report", "severity": "critical", "source": "patient", "pain_score": 8, "note": "sharp wrist pain"},
    )
    assert pain_event.status_code == 200
    safety_events = client.get(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/safety-events",
        headers=auth_headers(owner_token),
    )
    assert safety_events.status_code == 200
    assert [item["event_type"] for item in safety_events.json()["data"]] == ["device_fit_issue", "pain_report"]

    paused_after_event = client.get(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}",
        headers=auth_headers(owner_token),
    )
    assert paused_after_event.status_code == 200
    assert paused_after_event.json()["data"]["status"] == "paused"
    blocked_recovery_bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert blocked_recovery_bootstrap.status_code == 200
    blocked_recovery = blocked_recovery_bootstrap.json()["data"]["session_recovery_guide"]
    assert blocked_recovery["status"] == "safety_review_required"
    assert blocked_recovery["blocking_event"]["event_type"] == "pain_report"
    assert "RECORD_SAFETY_REVIEW" in {item["code"] for item in blocked_recovery["actions"]}
    blocked_recovery_home = blocked_recovery_bootstrap.json()["data"]["home_status_guide"]
    assert blocked_recovery_home["primary_action"]["code"] == "RECOVER_ACTIVE_SESSION"
    assert "safety_review_required" in blocked_recovery_home["blockers"]
    assert blocked_recovery_home["primary_blocker"]["code"] == "active_session"
    safety_blocker = next(item for item in blocked_recovery_home["blocker_details"] if item["code"] == "safety_review_required")
    assert safety_blocker["severity"] == "critical"
    assert "safety_review" in safety_blocker["clear_condition"]
    assert "RECORD_SAFETY_REVIEW" in safety_blocker["related_action_codes"]
    assert {"RECORD_SAFETY_REVIEW", "CANCEL_SESSION"}.issubset({item["code"] for item in blocked_recovery_home["secondary_actions"]})
    paused_event_progress = client.patch(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/progress",
        headers=auth_headers(owner_token),
        json={"completion_rate": 0.6},
    )
    assert paused_event_progress.status_code == 409
    assert paused_event_progress.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"
    blocked_resume_after_event = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/resume",
        headers=auth_headers(owner_token),
        json={"note": "try resume without review"},
    )
    assert blocked_resume_after_event.status_code == 409
    assert blocked_resume_after_event.json()["error"]["code"] == "SAFETY_REVIEW_REQUIRED"
    safety_review = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/safety-events",
        headers=auth_headers(owner_token),
        json={
            "event_type": "safety_review",
            "severity": "info",
            "source": "therapist",
            "payload": {"review_status": "approved"},
            "note": "therapist reviewed pain and strap fit",
        },
    )
    assert safety_review.status_code == 200
    resume_after_event = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session['id']}/resume",
        headers=auth_headers(owner_token),
        json={"note": "therapist checked pain and fit"},
    )
    assert resume_after_event.status_code == 200

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

    bootstrap_needs_report = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_report.status_code == 200
    finished_report_guide = bootstrap_needs_report.json()["data"]["finished_session_report_guide"]
    assert finished_report_guide["status"] == "report_required"
    assert finished_report_guide["session"]["id"] == session["id"]
    assert finished_report_guide["control_boundary"] == "finished_session_report_guide_evidence_only_not_motion_permission"
    assert finished_report_guide["next_action"]["code"] == "GENERATE_TRAINING_REPORT"
    assert "GENERATE_TRAINING_REPORT" in {item["code"] for item in finished_report_guide["actions"]}
    assert bootstrap_needs_report.json()["data"]["daily_action_guide"]["next_action"]["code"] == "GENERATE_TRAINING_REPORT"
    finished_home_status = bootstrap_needs_report.json()["data"]["home_status_guide"]
    assert finished_home_status["primary_action"]["code"] == "GENERATE_TRAINING_REPORT"
    assert "finished_report_required" in finished_home_status["blockers"]
    assert finished_home_status["primary_blocker"]["code"] == "finished_report_required"
    assert finished_home_status["counts"]["finished_sessions_pending_report"] == 1
    finished_report_blocker = next(item for item in finished_home_status["blocker_details"] if item["code"] == "finished_report_required")
    assert "生成训练报告" in finished_report_blocker["clear_condition"]
    assert finished_report_blocker["related_action_codes"] == ["GENERATE_TRAINING_REPORT", "VIEW_SESSION"]
    assert finished_home_status["secondary_actions"][0]["code"] == "VIEW_SESSION"
    assert finished_home_status["secondary_actions"][0]["endpoint"] == f"/api/rehab-arm/app/v1/training-sessions/{session['id']}"

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
    assert report["safety_overview"]["event_count"] == 3
    assert report["safety_overview"]["critical_event_count"] == 1
    assert report["safety_overview"]["max_pain_score"] == 8
    assert "critical_safety_event_review_required_before_next_session" in report["recommendations"]
    assert "high_in_session_pain_review_with_therapist" in report["recommendations"]
    assert report["latest_review"] is None
    bootstrap_needs_report_review = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_report_review.status_code == 200
    assert bootstrap_needs_report_review.json()["data"]["finished_session_report_guide"] is None
    assert bootstrap_needs_report_review.json()["data"]["daily_action_guide"]["next_action"]["code"] == "REVIEW_LATEST_REPORT"
    report_followup_review = bootstrap_needs_report_review.json()["data"]["report_followup_guide"]
    assert report_followup_review["status"] == "review_required"
    assert report_followup_review["control_boundary"] == "report_followup_guide_evidence_only_not_motion_permission"
    assert "RECORD_REPORT_REVIEW" in {item["code"] for item in report_followup_review["actions"]}

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
    bootstrap_needs_next_draft = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_next_draft.status_code == 200
    assert bootstrap_needs_next_draft.json()["data"]["daily_action_guide"]["next_action"]["code"] == "DRAFT_NEXT_PLAN_FROM_REPORT"
    report_followup_draft = bootstrap_needs_next_draft.json()["data"]["report_followup_guide"]
    assert report_followup_draft["status"] == "next_plan_draft_required"
    assert "DRAFT_NEXT_PLAN_FROM_REPORT" in {item["code"] for item in report_followup_draft["actions"]}

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
    bootstrap_needs_draft_review = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_draft_review.status_code == 200
    report_followup_accept = bootstrap_needs_draft_review.json()["data"]["report_followup_guide"]
    assert report_followup_accept["status"] == "ai_draft_review_required"
    assert report_followup_accept["report_draft"]["id"] == next_draft["id"]
    assert {"VIEW_AI_DRAFT", "ACCEPT_AI_DRAFT"}.issubset({item["code"] for item in report_followup_accept["actions"]})

    next_plan_response = client.post(
        f"/api/rehab-arm/app/v1/ai-training-drafts/{next_draft['id']}/accept",
        headers=auth_headers(owner_token),
    )
    assert next_plan_response.status_code == 200
    next_plan = next_plan_response.json()["data"]
    assert next_plan["source"] == "ai_generated"
    assert next_plan["sets"] == 1
    assert next_plan["control_boundary"] == "training_plan_only_not_motor_command"
    bootstrap_needs_next_plan_sync = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_next_plan_sync.status_code == 200
    report_followup_sync = bootstrap_needs_next_plan_sync.json()["data"]["report_followup_guide"]
    assert report_followup_sync["status"] == "accepted_plan_sync_required"
    assert report_followup_sync["report_draft"]["accepted_plan_id"] == next_plan["id"]
    assert "SYNC_ACCEPTED_PLAN_TO_M33" in {item["code"] for item in report_followup_sync["actions"]}

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
    care_timeline = bootstrap.json()["data"]["care_timeline"]
    assert care_timeline["control_boundary"] == "app_care_timeline_evidence_only_not_motion_permission"
    care_summary = bootstrap.json()["data"]["care_summary"]
    assert care_summary["counts"]["finished_sessions"] >= 1
    assert care_summary["counts"]["reports"] == 1
    assert care_summary["counts"]["reports_pending_review"] == 0
    assert care_summary["counts"]["ai_drafts_open"] == 0
    timeline_kinds = {item["kind"] for item in care_timeline["items"]}
    assert {"training_session", "training_report", "ai_training_draft"}.issubset(timeline_kinds)
    report_timeline = next(item for item in care_timeline["items"] if item["kind"] == "training_report")
    assert report_timeline["source_id"] == report["id"]
    assert report_timeline["status"] == "reviewed"

    sync_run = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["training_reports", "training_report_reviews", "ai_training_drafts", "session_safety_events"]},
    )
    assert sync_run.status_code == 200
    assert sync_run.json()["data"]["summary"]["training_reports"] == 1
    assert sync_run.json()["data"]["summary"]["training_report_reviews"] == 1
    assert sync_run.json()["data"]["summary"]["ai_training_drafts"] == 1
    assert sync_run.json()["data"]["summary"]["session_safety_events"] == 3

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
    ai_draft_guide = bootstrap_with_draft.json()["data"]["ai_draft_review_guide"]
    assert ai_draft_guide["status"] == "review_required"
    assert ai_draft_guide["draft"]["id"] == draft["id"]
    assert ai_draft_guide["control_boundary"] == "ai_draft_review_guide_draft_only_not_motion_permission"
    assert {"VIEW_AI_DRAFT", "ACCEPT_AI_DRAFT"}.issubset({item["code"] for item in ai_draft_guide["actions"]})
    draft_daily_action = bootstrap_with_draft.json()["data"]["daily_action_guide"]["next_action"]
    assert draft_daily_action["code"] == "REVIEW_AI_DRAFT"
    assert draft_daily_action["source"] == {"draft_id": draft["id"], "guide": "ai_draft_review_guide"}
    draft_home_status = bootstrap_with_draft.json()["data"]["home_status_guide"]
    assert draft_home_status["primary_action"]["code"] == "REVIEW_AI_DRAFT"
    assert draft_home_status["secondary_actions"][0]["code"] == "ACCEPT_AI_DRAFT"
    assert draft_home_status["secondary_actions"][0]["endpoint"] == f"/api/rehab-arm/app/v1/ai-training-drafts/{draft['id']}/accept"

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
    assert bootstrap_after_accept.json()["data"]["ai_draft_review_guide"] is None
    accepted_plan_guide = bootstrap_after_accept.json()["data"]["accepted_plan_guide"]
    assert accepted_plan_guide["status"] == "device_required"
    assert accepted_plan_guide["plan"]["id"] == plan["id"]
    assert accepted_plan_guide["draft"]["id"] == draft["id"]
    assert accepted_plan_guide["control_boundary"] == "accepted_plan_guide_evidence_only_not_motion_permission"
    assert bootstrap_after_accept.json()["data"]["daily_action_guide"]["next_action"]["code"] == "BIND_TRUSTED_DEVICE"

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
    bootstrap_after_device = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_device.status_code == 200
    accepted_plan_with_device = bootstrap_after_device.json()["data"]["accepted_plan_guide"]
    assert accepted_plan_with_device["status"] == "plan_closed"

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

    followup_draft = client.post(
        "/api/rehab-arm/app/v1/ai-training-drafts/generate",
        headers=auth_headers(owner_token),
        json={"input_text": "Need gentle wrist follow-up.", "context_snapshot": {"movement_type": "wrist_extension", "sets": 1, "reps": 4}},
    )
    assert followup_draft.status_code == 200
    followup_plan_response = client.post(
        f"/api/rehab-arm/app/v1/ai-training-drafts/{followup_draft.json()['data']['id']}/accept",
        headers=auth_headers(owner_token),
    )
    assert followup_plan_response.status_code == 200
    followup_plan = followup_plan_response.json()["data"]
    bootstrap_followup_plan = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_followup_plan.status_code == 200
    followup_guide = bootstrap_followup_plan.json()["data"]["accepted_plan_guide"]
    assert followup_guide["status"] == "sync_required"
    assert followup_guide["plan"]["id"] == followup_plan["id"]
    assert followup_guide["device"]["id"] == device["id"]
    assert followup_guide["next_action"]["code"] == "SYNC_ACCEPTED_PLAN_TO_M33"
    assert bootstrap_followup_plan.json()["data"]["daily_action_guide"]["next_action"]["code"] == "SYNC_ACCEPTED_PLAN_TO_M33"
    followup_home_status = bootstrap_followup_plan.json()["data"]["home_status_guide"]
    assert followup_home_status["primary_action"]["code"] == "SYNC_ACCEPTED_PLAN_TO_M33"
    assert followup_home_status["secondary_actions"][0]["code"] == "VIEW_ACCEPTED_PLAN"
    assert followup_home_status["secondary_actions"][0]["endpoint"] == f"/api/rehab-arm/app/v1/training-plans/{followup_plan['id']}"
    followup_sync = client.post(
        f"/api/rehab-arm/app/v1/training-plans/{followup_plan['id']}/sync-to-device",
        headers=auth_headers(owner_token),
        json={"device_id": device["id"]},
    )
    assert followup_sync.status_code == 200
    pending_followup_bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert pending_followup_bootstrap.status_code == 200
    assert pending_followup_bootstrap.json()["data"]["accepted_plan_guide"]["status"] == "m33_decision_pending"
    accept_followup = client.post(
        f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
        headers=auth_headers(owner_token),
        json={"sync_id": followup_sync.json()["data"]["id"], "sync_status": "m33_accepted", "m33_reason": "accepted AI follow-up"},
    )
    assert accept_followup.status_code == 200
    accepted_followup_bootstrap = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert accepted_followup_bootstrap.status_code == 200
    assert accepted_followup_bootstrap.json()["data"]["accepted_plan_guide"]["status"] == "preflight_required"


def test_rehab_arm_app_daily_action_prioritizes_offline_sync_without_active_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))

    owner_token, _owner_user_id = _issue_rehab_app_token()
    queued_platform_sync = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-platform-sync-001",
            "operation_type": "platform_sync",
            "resource_type": "platform_sync",
            "payload": {"resource_types": ["training_plans"]},
        },
    )
    assert queued_platform_sync.status_code == 200
    queued_item = queued_platform_sync.json()["data"]
    bootstrap_with_queued = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_queued.status_code == 200
    queued_daily_action = bootstrap_with_queued.json()["data"]["daily_action_guide"]["next_action"]
    assert queued_daily_action["code"] == "REPLAY_OFFLINE_EVIDENCE"
    assert queued_daily_action["endpoint"] == "/api/rehab-arm/app/v1/offline-queue/replay"
    assert queued_daily_action["payload_hint"] == {"item_ids": [queued_item["id"]]}

    queued_bad_diagnostic = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-diagnostic-missing-device-002",
            "operation_type": "device_diagnostic_upload",
            "resource_type": "device_diagnostic_upload",
            "payload": {
                "device_id": "missing-device-id",
                "snapshot_type": "m33_status",
                "m33_state": "offline",
            },
        },
    )
    assert queued_bad_diagnostic.status_code == 200
    failed_source = queued_bad_diagnostic.json()["data"]
    failed_replay = client.post(
        "/api/rehab-arm/app/v1/offline-queue/replay",
        headers=auth_headers(owner_token),
        json={"item_ids": [failed_source["id"]]},
    )
    assert failed_replay.status_code == 200
    assert failed_replay.json()["data"]["items"][0]["replay_status"] == "failed"
    bootstrap_with_failed = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_failed.status_code == 200
    failed_daily_action = bootstrap_with_failed.json()["data"]["daily_action_guide"]["next_action"]
    assert failed_daily_action["code"] == "VIEW_OFFLINE_QUEUE"
    assert failed_daily_action["endpoint"] == "/api/rehab-arm/app/v1/offline-queue?status=failed"
    assert failed_daily_action["source"] == {"guide": "offline_sync_guide", "offline_status": "review_failed_items"}
    failed_home_status = bootstrap_with_failed.json()["data"]["home_status_guide"]
    assert failed_home_status["tone"] == "critical"
    assert failed_home_status["primary_action"]["code"] == "VIEW_OFFLINE_QUEUE"
    assert failed_home_status["secondary_actions"][0]["code"] == "REVIEW_FAILED_OFFLINE_ITEM"
    assert failed_home_status["secondary_actions"][0]["endpoint"] == f"/api/rehab-arm/app/v1/offline-queue/{failed_source['id']}/review"
    assert failed_home_status["counts"]["offline_items_failed"] == 1
    assert "offline_queue_failed" in failed_home_status["blockers"]
    assert failed_home_status["progress"]["stage"] == "resolve_blockers"
    assert failed_home_status["progress"]["next_item"]["code"] == "offline_clear"
    offline_progress = next(item for item in failed_home_status["progress"]["items"] if item["code"] == "offline_clear")
    assert offline_progress["done"] is False
    assert "offline_queue_failed" in offline_progress["related_blocker_codes"]
    assert "REVIEW_FAILED_OFFLINE_ITEM" in offline_progress["related_action_codes"]
    assert bootstrap_with_failed.json()["data"]["care_summary"]["primary_blocker"]["code"] == "offline_queue_failed"
    assert failed_home_status["primary_blocker"]["code"] == "offline_queue_failed"
    failed_blocker = next(item for item in failed_home_status["blocker_details"] if item["code"] == "offline_queue_failed")
    assert failed_blocker["severity"] == "critical"
    assert failed_blocker["title"] == "处理离线失败证据"
    assert "人工复核" in failed_blocker["clear_condition"]
    assert failed_blocker["related_action_codes"] == ["VIEW_OFFLINE_QUEUE", "REVIEW_FAILED_OFFLINE_ITEM"]
    failed_group = next(item for item in failed_home_status["action_groups"]["blocker_related"] if item["blocker_code"] == "offline_queue_failed")
    assert [item["code"] for item in failed_group["actions"]] == ["VIEW_OFFLINE_QUEUE", "REVIEW_FAILED_OFFLINE_ITEM"]


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
    bootstrap_after_diagnostic = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_diagnostic.status_code == 200
    diagnostic_device_guide = bootstrap_after_diagnostic.json()["data"]["device_operational_guide"]
    assert diagnostic_device_guide["latest_diagnostic"]["m33_state"] == "waiting_for_plan"
    assert diagnostic_device_guide["latest_diagnostic"]["battery_level"] == 0.76
    assert diagnostic_device_guide["control_boundary"] == "device_operational_guide_evidence_only_not_motion_permission"

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

    _pass_preflight(owner_token, plan_id, device["id"], sync_id)

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

    queued_safety = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-safety-001",
            "operation_type": "session_safety_event",
            "resource_type": "session_safety_event",
            "payload": {
                "session_id": session_id,
                "event_type": "pain_report",
                "severity": "critical",
                "source": "patient",
                "pain_score": 8,
                "note": "offline pain event",
            },
        },
    )
    assert queued_safety.status_code == 200
    safety_queue_item = queued_safety.json()["data"]
    assert safety_queue_item["replay_status"] == "queued"

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
    bootstrap_with_offline_queue = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_offline_queue.status_code == 200
    offline_guide = bootstrap_with_offline_queue.json()["data"]["offline_sync_guide"]
    assert offline_guide["status"] == "ready_to_replay"
    assert offline_guide["counts"]["queued"] == 2
    assert set(offline_guide["queued_item_ids"]) == {queue_item["id"], safety_queue_item["id"]}
    assert offline_guide["payload_hint"] == {"item_ids": [queue_item["id"], safety_queue_item["id"]]}
    assert offline_guide["actions"] == [
        {
            "code": "REPLAY_OFFLINE_EVIDENCE",
            "label": "重放离线证据",
            "endpoint": "/api/rehab-arm/app/v1/offline-queue/replay",
            "method": "POST",
            "payload_hint": {"item_ids": [queue_item["id"], safety_queue_item["id"]]},
        }
    ]

    queued_bad_diagnostic = client.post(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        json={
            "client_item_id": "phone-diagnostic-missing-device-001",
            "operation_type": "device_diagnostic_upload",
            "resource_type": "device_diagnostic_upload",
            "payload": {
                "device_id": "missing-device-id",
                "snapshot_type": "m33_status",
                "m33_state": "offline",
            },
        },
    )
    assert queued_bad_diagnostic.status_code == 200
    bad_queue_item = queued_bad_diagnostic.json()["data"]
    failed_replay = client.post(
        "/api/rehab-arm/app/v1/offline-queue/replay",
        headers=auth_headers(owner_token),
        json={"item_ids": [bad_queue_item["id"]]},
    )
    assert failed_replay.status_code == 200
    failed_item = failed_replay.json()["data"]["items"][0]
    assert failed_item["replay_status"] == "failed"
    assert "error" in failed_item["replay_result"]
    bootstrap_with_failed_offline_item = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_with_failed_offline_item.status_code == 200
    failed_offline_guide = bootstrap_with_failed_offline_item.json()["data"]["offline_sync_guide"]
    assert failed_offline_guide["status"] == "review_failed_items"
    assert failed_offline_guide["counts"]["failed"] == 1
    assert failed_offline_guide["failed_item_ids"] == [bad_queue_item["id"]]
    assert failed_offline_guide["actions"][0]["code"] == "VIEW_OFFLINE_QUEUE"
    assert failed_offline_guide["actions"][0]["endpoint"] == "/api/rehab-arm/app/v1/offline-queue?status=failed"
    assert failed_offline_guide["actions"][1]["code"] == "REVIEW_FAILED_OFFLINE_ITEM"
    assert failed_offline_guide["actions"][1]["endpoint"] == f"/api/rehab-arm/app/v1/offline-queue/{bad_queue_item['id']}/review"
    failed_queue = client.get(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        params={"status": "failed"},
    )
    assert failed_queue.status_code == 200
    assert [item["id"] for item in failed_queue.json()["data"]] == [bad_queue_item["id"]]
    queued_queue = client.get(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        params={"status": "queued"},
    )
    assert queued_queue.status_code == 200
    assert {item["id"] for item in queued_queue.json()["data"]} == {queue_item["id"], safety_queue_item["id"]}
    review_queued_item = client.post(
        f"/api/rehab-arm/app/v1/offline-queue/{queue_item['id']}/review",
        headers=auth_headers(owner_token),
        json={"reviewer_role": "therapist", "review_status": "reviewed", "note": "should not close queued evidence"},
    )
    assert review_queued_item.status_code == 409
    assert review_queued_item.json()["error"]["code"] == "OFFLINE_QUEUE_ITEM_NOT_FAILED"
    assert review_queued_item.json()["error"]["details"]["replay_status"] == "queued"
    empty_review_note = client.post(
        f"/api/rehab-arm/app/v1/offline-queue/{bad_queue_item['id']}/review",
        headers=auth_headers(owner_token),
        json={"reviewer_role": "therapist", "review_status": "reviewed", "note": ""},
    )
    assert empty_review_note.status_code == 422
    assert empty_review_note.json()["error"]["code"] == "VALIDATION_ERROR"
    reviewed_failed = client.post(
        f"/api/rehab-arm/app/v1/offline-queue/{bad_queue_item['id']}/review",
        headers=auth_headers(owner_token),
        json={"reviewer_role": "therapist", "review_status": "reviewed", "note": "device id was stale; evidence ignored"},
    )
    assert reviewed_failed.status_code == 200
    reviewed_item = reviewed_failed.json()["data"]
    assert reviewed_item["replay_status"] == "reviewed"
    assert reviewed_item["replay_result"]["review"]["reviewer_role"] == "therapist"
    assert reviewed_item["replay_result"]["control_boundary"] == "offline_queue_evidence_only_not_motion_permission"
    reviewed_queue = client.get(
        "/api/rehab-arm/app/v1/offline-queue",
        headers=auth_headers(owner_token),
        params={"status": "reviewed"},
    )
    assert reviewed_queue.status_code == 200
    assert [item["id"] for item in reviewed_queue.json()["data"]] == [bad_queue_item["id"]]
    review_already_reviewed = client.post(
        f"/api/rehab-arm/app/v1/offline-queue/{bad_queue_item['id']}/review",
        headers=auth_headers(owner_token),
        json={"reviewer_role": "therapist", "review_status": "duplicate", "note": "already reviewed"},
    )
    assert review_already_reviewed.status_code == 409
    assert review_already_reviewed.json()["error"]["code"] == "OFFLINE_QUEUE_ITEM_NOT_FAILED"
    assert review_already_reviewed.json()["error"]["details"]["replay_status"] == "reviewed"

    replay = client.post(
        "/api/rehab-arm/app/v1/offline-queue/replay",
        headers=auth_headers(owner_token),
        json={"item_ids": [queue_item["id"], safety_queue_item["id"]]},
    )
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["replayed_count"] == 2
    assert {item["replay_status"] for item in replay_data["items"]} == {"replayed"}
    bootstrap_after_offline_replay = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_offline_replay.status_code == 200
    assert bootstrap_after_offline_replay.json()["data"]["offline_sync_guide"]["status"] == "synced"
    assert bootstrap_after_offline_replay.json()["data"]["offline_sync_guide"]["actions"] == []

    latest_emg = client.get("/api/rehab-arm/app/v1/emg/latest", headers=auth_headers(owner_token))
    assert latest_emg.status_code == 200
    assert latest_emg.json()["data"]["muscle_name"] == "triceps"

    offline_safety_events = client.get(
        f"/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
        headers=auth_headers(owner_token),
    )
    assert offline_safety_events.status_code == 200
    assert offline_safety_events.json()["data"][0]["event_type"] == "pain_report"
    paused_after_offline_event = client.get(
        f"/api/rehab-arm/app/v1/training-sessions/{session_id}",
        headers=auth_headers(owner_token),
    )
    assert paused_after_offline_event.status_code == 200
    assert paused_after_offline_event.json()["data"]["status"] == "paused"

    cancel_after_offline_event = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session_id}/cancel",
        headers=auth_headers(owner_token),
        json={"reason": "offline critical pain event"},
    )
    assert cancel_after_offline_event.status_code == 200
    bootstrap_needs_safety_review = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_needs_safety_review.status_code == 200
    safety_review_guide = bootstrap_needs_safety_review.json()["data"]["safety_review_guide"]
    assert safety_review_guide["status"] == "review_required"
    assert safety_review_guide["blocking_event"]["session_id"] == session_id
    assert safety_review_guide["blocking_event"]["event_type"] == "pain_report"
    assert "RECORD_SAFETY_REVIEW" in {item["code"] for item in safety_review_guide["actions"]}
    assert bootstrap_needs_safety_review.json()["data"]["daily_action_guide"]["next_action"]["code"] == "REVIEW_BLOCKING_SAFETY_EVENT"
    safety_review_home = bootstrap_needs_safety_review.json()["data"]["home_status_guide"]
    assert "safety_review_required" in safety_review_home["blockers"]
    assert safety_review_home["primary_blocker"]["code"] == "safety_review_required"
    assert safety_review_home["counts"]["safety_reviews_pending"] == 1
    safety_review_blocker = next(item for item in safety_review_home["blocker_details"] if item["code"] == "safety_review_required")
    assert "RECORD_SAFETY_REVIEW" in safety_review_blocker["related_action_codes"]
    safety_review_group = next(item for item in safety_review_home["action_groups"]["blocker_related"] if item["blocker_code"] == "safety_review_required")
    assert {"REVIEW_BLOCKING_SAFETY_EVENT", "VIEW_SESSION", "VIEW_SAFETY_EVENTS"}.issubset({item["code"] for item in safety_review_group["actions"]})
    _pass_preflight(owner_token, plan_id, device["id"], sync_id)
    blocked_restart_without_review = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan_id, "device_id": device["id"]},
    )
    assert blocked_restart_without_review.status_code == 409
    assert blocked_restart_without_review.json()["error"]["code"] == "SAFETY_REVIEW_REQUIRED"
    readiness_needs_safety_review = client.get(
        f"/api/rehab-arm/app/v1/training-plans/{plan_id}/readiness",
        headers=auth_headers(owner_token),
        params={"device_id": device["id"]},
    )
    assert readiness_needs_safety_review.status_code == 200
    safety_checks = {item["name"]: item for item in readiness_needs_safety_review.json()["data"]["checks"]}
    assert readiness_needs_safety_review.json()["data"]["can_start"] is False
    assert safety_checks["safety_review"]["code"] == "SAFETY_REVIEW_REQUIRED"
    offline_safety_review = client.post(
        f"/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
        headers=auth_headers(owner_token),
        json={
            "event_type": "safety_review",
            "severity": "info",
            "source": "therapist",
            "payload": {"review_status": "approved"},
            "note": "reviewed offline pain report before next start",
        },
    )
    assert offline_safety_review.status_code == 200
    bootstrap_after_safety_review = client.get("/api/rehab-arm/app/v1/me", headers=auth_headers(owner_token))
    assert bootstrap_after_safety_review.status_code == 200
    assert bootstrap_after_safety_review.json()["data"]["safety_review_guide"]["status"] == "clear"
    _pass_preflight(owner_token, plan_id, device["id"], sync_id)
    restart_after_review = client.post(
        "/api/rehab-arm/app/v1/training-sessions/start",
        headers=auth_headers(owner_token),
        json={"plan_id": plan_id, "device_id": device["id"]},
    )
    assert restart_after_review.status_code == 200

    sync_run = client.post(
        "/api/rehab-arm/app/v1/platform/sync",
        headers=auth_headers(owner_token),
        json={"resource_types": ["training_plans", "training_sessions", "emg_summaries", "m33_decisions", "session_safety_events"]},
    )
    assert sync_run.status_code == 200
    assert sync_run.json()["data"]["summary"]["emg_summaries"] >= 1
    assert sync_run.json()["data"]["summary"]["session_safety_events"] == 2

    sync_runs = client.get("/api/rehab-arm/app/v1/platform/sync-runs", headers=auth_headers(owner_token))
    assert sync_runs.status_code == 200
    assert sync_runs.json()["data"][0]["control_boundary"] == "platform_sync_evidence_only_not_motion_permission"

    audit = client.get("/api/rehab-arm/app/v1/safety-audit", headers=auth_headers(owner_token))
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["data"]}
    assert "rehab_app.training_plan.m33_accepted" in actions
    assert "rehab_app.device.diagnostic_uploaded" in actions
