from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, create_task, issue_session_token, register_user


client = TestClient(app)


def test_task_due_at_survives_create_update_and_read_paths() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Task Deadline")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    initial_due_at = "2026-04-24T10:30:00+08:00"
    task = create_task(
        client,
        owner_token,
        project_id,
        title="Schedule calendar task",
        description="Task created from the main-house calendar.",
        due_at=initial_due_at,
    )
    assert task["due_at"].startswith("2026-04-24T10:30:00")

    updated_due_at = "2026-04-24T18:00:00+08:00"
    update_response = client.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(owner_token),
        json={"due_at": updated_due_at},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["due_at"].startswith("2026-04-24T18:00:00")

    read_response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token))
    assert read_response.status_code == 200
    assert read_response.json()["data"]["due_at"].startswith("2026-04-24T18:00:00")

    list_response = client.get(f"/api/tasks?project_id={project_id}", headers=auth_headers(owner_token))
    assert list_response.status_code == 200
    rows = list_response.json()["data"]
    listed_task = next(item for item in rows if item["id"] == task["id"])
    assert listed_task["due_at"].startswith("2026-04-24T18:00:00")


def test_task_writes_require_membership_and_privilege() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Task Permissions")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    member_user_id, member_email = register_user(client, f"member-{uuid4().hex[:8]}@example.com", "Task Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Task Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    outsider_create = client.post(
        "/api/tasks",
        headers=auth_headers(outsider_token),
        json={
            "project_id": project_id,
            "title": "Outsider task",
            "description": "outsider should not create tasks",
            "module": "permissions",
            "priority": "P2",
            "status": "draft",
            "branch": f"feature/task-outsider-{uuid4().hex[:8]}",
            "assignee_agent_id": "agent-ui",
        },
    )
    assert outsider_create.status_code == 403
    assert outsider_create.json()["error"]["code"] == "PERMISSION_DENIED"

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Task permission target",
        description="Task used to verify task writes.",
        module="permissions",
        priority="P2",
        status="ready",
        branch=f"feature/task-permissions-{uuid4().hex[:8]}",
        assignee_agent_id="agent-ui",
    )

    outsider_update = client.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(outsider_token),
        json={"description": "blocked update"},
    )
    assert outsider_update.status_code == 403
    assert outsider_update.json()["error"]["code"] == "PERMISSION_DENIED"

    member_update = client.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(member_token),
        json={"description": "member update"},
    )
    assert member_update.status_code == 200

    member_transition = client.post(
        f"/api/tasks/{task['id']}/transition",
        headers=auth_headers(member_token),
        json={"status": "running", "message": "member transition"},
    )
    assert member_transition.status_code == 200
    assert member_transition.json()["data"]["status"] == "running"

    member_transition_reviewing = client.post(
        f"/api/tasks/{task['id']}/transition",
        headers=auth_headers(member_token),
        json={"status": "reviewing", "message": "member review transition"},
    )
    assert member_transition_reviewing.status_code == 200
    assert member_transition_reviewing.json()["data"]["status"] == "reviewing"

    merge_gate = client.post(
        f"/api/tasks/{task['id']}/merge",
        headers=auth_headers(member_token),
        json={"message": "member merge attempt"},
    )
    assert merge_gate.status_code == 403
    assert merge_gate.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    merge_response = client.post(
        f"/api/tasks/{task['id']}/merge",
        headers=auth_headers(owner_token),
        json={"message": "owner merge"},
    )
    assert merge_response.status_code == 200
    assert merge_response.json()["data"]["status"] == "done"

    rollback_task = create_task(
        client,
        owner_token,
        project_id,
        title="Task rollback target",
        description="Task used to verify rollback writes.",
        module="permissions",
        priority="P2",
        status="ready",
        branch=f"feature/task-rollback-{uuid4().hex[:8]}",
        assignee_agent_id="agent-ui",
    )
    client.post(
        f"/api/tasks/{rollback_task['id']}/transition",
        headers=auth_headers(owner_token),
        json={"status": "running", "message": "owner transition"},
    )
    client.post(
        f"/api/tasks/{rollback_task['id']}/transition",
        headers=auth_headers(owner_token),
        json={"status": "reviewing", "message": "owner review transition"},
    )

    rollback_gate = client.post(
        f"/api/tasks/{rollback_task['id']}/rollback",
        headers=auth_headers(member_token),
        json={"message": "member rollback attempt"},
    )
    assert rollback_gate.status_code == 403
    assert rollback_gate.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    rollback_response = client.post(
        f"/api/tasks/{rollback_task['id']}/rollback",
        headers=auth_headers(owner_token),
        json={"message": "owner rollback"},
    )
    assert rollback_response.status_code == 200
    assert rollback_response.json()["data"]["status"] == "blocked"

    for path in [
        f"/api/tasks/{task['id']}/plan",
        f"/api/tasks/{task['id']}/approve-plan",
        f"/api/tasks/{task['id']}/run",
        f"/api/tasks/{task['id']}/cancel",
        f"/api/tasks/{task['id']}/review",
    ]:
        response = client.post(
            path,
            headers=auth_headers(outsider_token),
            json={"message": "outsider blocked"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    handoff_response = client.post(
        f"/api/tasks/{task['id']}/create-handoff",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "handoff_from": "agent-ui",
            "handoff_to": "agent-review",
            "summary": "task alias handoff",
            "reason": "verify alias permissions",
            "current_status": "ready",
            "notes": "task alias handoff",
        },
    )
    assert handoff_response.status_code == 200

    outsider_handoff_response = client.post(
        f"/api/tasks/{task['id']}/create-handoff",
        headers=auth_headers(outsider_token),
        json={
            "project_id": project_id,
            "handoff_from": "agent-ui",
            "handoff_to": "agent-review",
            "summary": "outsider alias handoff",
        },
    )
    assert outsider_handoff_response.status_code == 403
    assert outsider_handoff_response.json()["error"]["code"] == "PERMISSION_DENIED"
