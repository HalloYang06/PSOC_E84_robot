from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, create_task, issue_session_token, register_user
from tests.helpers import create_handoff


client = TestClient(app)


def test_collaboration_invites_hide_token_and_require_project_privilege() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Collab Invite Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    create_response = client.post(
        f"/api/collaboration/projects/{project_id}/invites",
        headers=auth_headers(owner_token),
        json={
            "email": f"invite-{uuid4().hex[:8]}@example.com",
            "role": "collaborator",
            "message": "secure collaboration invite",
        },
    )
    assert create_response.status_code == 200
    invite = create_response.json()["data"]
    assert invite["token"] is None

    list_response = client.get(
        f"/api/collaboration/invites?project_id={project_id}",
        headers=auth_headers(owner_token),
    )
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert listed
    assert listed[0]["token"] is None


def test_collaboration_messages_require_membership_and_bind_sender_to_session() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Collab Message Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Secure collaboration message task")

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Collab Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    outsider_response = client.post(
        "/api/messages",
        headers=auth_headers(outsider_token),
        json={
            "entity_type": "task",
            "entity_id": task["id"],
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "comment_message",
            "body": "outsider should not write collaboration messages",
        },
    )
    assert outsider_response.status_code == 403

    member_response = client.post(
        "/api/messages",
        headers=auth_headers(owner_token),
        json={
            "entity_type": "task",
            "entity_id": task["id"],
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "comment_message",
            "body": "secure collaboration message",
        },
    )
    assert member_response.status_code == 200
    message = member_response.json()["data"]
    assert message["project_id"] == project_id
    assert message["entity_id"] == task["id"]


def test_platform_global_write_endpoints_require_explicit_auth() -> None:
    responses = [
        client.post("/api/agents", json={"name": "Blocked Agent"}),
        client.post("/api/usage", json={"provider": "openai", "model": "gpt-5"}),
        client.post("/api/audit", json={"action": "manual.audit"}),
        client.post("/api/lab/checks", json={"item": "power", "passed": True}),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_context_lab_usage_and_audit_writes_require_scoped_auth() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Scoped Write Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Scoped write task")

    context_response = client.post(
        f"/api/tasks/{task['id']}/context-health",
        headers=auth_headers(owner_token),
        json={"usage_ratio": 0.45, "health": "yellow", "summary": "context is growing"},
    )
    assert context_response.status_code == 200

    lab_response = client.post(
        "/api/lab/hardware-approvals",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "action": "deploy arm firmware",
            "level": "H3",
        },
    )
    assert lab_response.status_code == 200
    approval = lab_response.json()["data"]
    assert approval["status"] == "pending"
    assert approval["approver_user_id"] is None

    usage_response = client.post(
        "/api/usage",
        headers=auth_headers(owner_token),
        json={"project_id": project_id, "task_id": task["id"], "provider": "openai", "model": "gpt-5.4"},
    )
    assert usage_response.status_code == 200

    audit_response = client.post(
        "/api/audit",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "action": "manual.audit",
        },
    )
    assert audit_response.status_code == 200
    audit = audit_response.json()["data"]
    assert audit["actor_type"] == "human"
    assert audit["actor_id"] == owner_user_id


def test_context_health_and_handoffs_reads_are_project_scoped() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Scoped Read Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Scoped read task")

    context_write = client.post(
        f"/api/tasks/{task['id']}/context-health",
        headers=auth_headers(owner_token),
        json={"usage_ratio": 0.55, "health": "yellow", "summary": "context read protection"},
    )
    assert context_write.status_code == 200

    handoff = create_handoff(client, owner_token, project_id, task["id"], summary="read protection handoff")

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Scoped Read Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    global_context_response = client.get("/api/context-health")
    assert global_context_response.status_code == 401

    global_handoff_response = client.get("/api/handoffs")
    assert global_handoff_response.status_code == 401

    outsider_context_response = client.get(
        f"/api/tasks/{task['id']}/context-health",
        headers=auth_headers(outsider_token),
    )
    assert outsider_context_response.status_code == 403
    assert outsider_context_response.json()["error"]["code"] == "PERMISSION_DENIED"

    outsider_handoff_response = client.get(
        f"/api/handoffs/{handoff['id']}",
        headers=auth_headers(outsider_token),
    )
    assert outsider_handoff_response.status_code == 403
    assert outsider_handoff_response.json()["error"]["code"] == "PERMISSION_DENIED"

    member_context_response = client.get(
        f"/api/tasks/{task['id']}/context-health",
        headers=auth_headers(owner_token),
    )
    assert member_context_response.status_code == 200

    member_handoff_response = client.get(
        f"/api/tasks/{task['id']}/handoffs/{handoff['id']}",
        headers=auth_headers(owner_token),
    )
    assert member_handoff_response.status_code == 200

    global_audit_response = client.get("/api/audit")
    assert global_audit_response.status_code == 401

    member_global_context = client.get("/api/context-health", headers=auth_headers(outsider_token))
    assert member_global_context.status_code == 403
    assert member_global_context.json()["error"]["code"] == "PERMISSION_DENIED"

    member_global_audit = client.get("/api/audit", headers=auth_headers(outsider_token))
    assert member_global_audit.status_code == 403
    assert member_global_audit.json()["error"]["code"] == "PERMISSION_DENIED"

    outsider_audit_response = client.get(
        f"/api/tasks/{task['id']}/audit",
        headers=auth_headers(outsider_token),
    )
    assert outsider_audit_response.status_code == 403
    assert outsider_audit_response.json()["error"]["code"] == "PERMISSION_DENIED"

    member_audit_response = client.get(
        f"/api/tasks/{task['id']}/audit",
        headers=auth_headers(owner_token),
    )
    assert member_audit_response.status_code == 200


def test_lab_hardware_approvals_reject_low_risk_levels_and_pin_real_actor() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Lab Approval Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Lab hardware gate task")

    low_level_response = client.post(
        "/api/lab/hardware-approvals",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "action": "deploy arm firmware",
            "level": "H1",
        },
    )
    assert low_level_response.status_code == 400
    assert low_level_response.json()["error"]["code"] == "INVALID_APPROVAL_LEVEL"

    lab_response = client.post(
        "/api/lab/hardware-approvals",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "action": "deploy arm firmware",
            "level": "H3",
        },
    )
    assert lab_response.status_code == 200
    approval = lab_response.json()["data"]
    assert approval["status"] == "pending"
    assert approval["approver_user_id"] is None

    gate_response = client.get(
        f"/api/tasks/{task['id']}/gate",
        headers=auth_headers(owner_token),
    )
    assert gate_response.status_code == 200
    gate = gate_response.json()["data"]
    assert gate["blocked"] is True
    assert gate["pending_high_risk_count"] >= 1

    audit_response = client.get("/api/lab/audit?limit=5", headers=auth_headers(owner_token))
    assert audit_response.status_code == 200
    lab_audit = audit_response.json()["data"][0]
    assert lab_audit["action"] == "lab.hardware_approval_requested"
    assert lab_audit["actor_type"] == "human"
    assert lab_audit["actor_id"] == owner_user_id

    approval_response = client.post(
        f"/api/approvals/{approval['id']}/approve",
        headers=auth_headers(owner_token),
        json={
            "notes": "lab approval confirmed by the owner",
        },
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()["data"]
    assert approved["status"] == "approved"
    assert approved["approver_user_id"] == owner_user_id

    gate_after_response = client.get(
        f"/api/tasks/{task['id']}/gate",
        headers=auth_headers(owner_token),
    )
    assert gate_after_response.status_code == 200
    gate_after = gate_after_response.json()["data"]
    assert gate_after["blocked"] is False
    assert gate_after["pending_high_risk_count"] == 0


def test_lab_checks_ignore_spoofed_actor_fields_and_block_task_by_real_actor() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Lab Check Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Lab check security task", status="ready")

    check_response = client.post(
        "/api/lab/checks",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "item": "hardware wiring",
            "passed": False,
            "notes": "wiring needs human review",
        },
    )
    assert check_response.status_code == 200
    check = check_response.json()["data"]
    assert check["task_id"] == task["id"]
    assert check["passed"] is False

    task_response = client.get(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(owner_token),
    )
    assert task_response.status_code == 200
    assert task_response.json()["data"]["status"] == "blocked"

    audit_response = client.get(
        f"/api/tasks/{task['id']}/audit?limit=10",
        headers=auth_headers(owner_token),
    )
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["data"]
    lab_check_audit = next(item for item in audit_items if item["action"] == "lab.check_recorded")
    assert lab_check_audit["actor_type"] == "human"
    assert lab_check_audit["actor_id"] == owner_user_id


def test_cross_project_read_endpoints_reject_unscoped_or_outsider_reads() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Read Isolation Security")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Read isolation task")

    requirement_response = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "title": "Read isolation requirement",
            "description": "Validate cross-project requirement reads stay scoped.",
        },
    )
    assert requirement_response.status_code == 200
    requirement = requirement_response.json()["data"]

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-read-{uuid4().hex[:8]}@example.com",
        "Read Isolation Outsider",
    )
    assert outsider_user_id
    outsider_token, _ = issue_session_token(client, outsider_email)

    outsider_project_response = client.get(
        f"/api/projects/{project_id}",
        headers=auth_headers(outsider_token),
    )
    assert outsider_project_response.status_code == 403
    assert outsider_project_response.json()["error"]["code"] == "PERMISSION_DENIED"

    outsider_collaboration_response = client.get(
        f"/api/collaboration/messages?requirement_id={requirement['id']}",
        headers=auth_headers(outsider_token),
    )
    assert outsider_collaboration_response.status_code == 403
    assert outsider_collaboration_response.json()["error"]["code"] == "PERMISSION_DENIED"

    unscoped_messages_response = client.get(
        "/api/messages",
        headers=auth_headers(owner_token),
    )
    assert unscoped_messages_response.status_code == 422
    assert unscoped_messages_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_lab_and_audit_writes_reject_spoofed_actor_fields() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Spoofed Actor Rejection")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Spoofed actor rejection task")

    lab_check_response = client.post(
        "/api/lab/checks",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "item": "hardware wiring",
            "passed": True,
            "actor_type": "agent",
            "actor_id": "spoofed-agent",
        },
    )
    assert lab_check_response.status_code == 422

    hardware_response = client.post(
        "/api/lab/hardware-approvals",
        headers=auth_headers(owner_token),
        json={
            "task_id": task["id"],
            "action": "deploy arm firmware",
            "level": "H3",
            "actor_type": "agent",
            "actor_id": "spoofed-agent",
        },
    )
    assert hardware_response.status_code == 422

    audit_response = client.post(
        "/api/audit",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "actor_type": "system",
            "actor_id": "spoofed-system",
            "action": "manual.audit",
        },
    )
    assert audit_response.status_code == 422
