from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import create_project as shared_create_project
from tests.helpers import issue_session_token as shared_issue_session_token
from tests.helpers import register_user as shared_register_user


client = TestClient(app)


def _session(email: str) -> tuple[str, str]:
    return shared_issue_session_token(client, email)


def _register_and_session(email: str, name: str) -> tuple[str, str]:
    user_id, registered_email = shared_register_user(client, email, name)
    token, _ = shared_issue_session_token(client, registered_email)
    return token, user_id


def _create_project(token: str) -> str:
    return shared_create_project(
        client,
        token,
        name_prefix="Requirements Permissions",
        github_url="https://example.com/req.git",
        local_git_url="/workspace/req.git",
    )["id"]


def _add_member(project_id: str, token: str, user_id: str, role: str = "member", is_owner: bool = False) -> None:
    response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": role,
            "status": "active",
            "is_owner": is_owner,
        },
    )
    assert response.status_code == 200


def _create_task(token: str, project_id: str) -> str:
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": "Requirement permission task",
            "description": "Task used to scope requirement permissions.",
            "module": "requirements",
            "priority": "P2",
            "status": "ready",
            "branch": "feature/requirement-permissions",
            "assignee_agent_id": "agent-ui",
            "reviewers": ["lead"],
            "acceptance_criteria": ["requirements writes are project-scoped"],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _create_requirement(token: str, project_id: str, task_id: str) -> str:
    response = client.post(
        "/api/requirements",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "task_id": task_id,
            "title": "Requirements need scoped permissions",
            "requirement_type": "thread_request",
            "status": "waiting_response",
            "context_summary": "Verify requirement writes respect project membership.",
            "expected_output": "Write permission is enforced.",
            "opening_message": "Please wire requirement permissions.",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] is None
    assert data["task_id"] == task_id
    return data["id"]


def test_requirement_writes_respect_membership_and_privilege() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    guest_token, guest_user_id = _register_and_session(
        f"guest-{uuid4().hex[:8]}@example.com",
        "Guest Writer",
    )
    _add_member(project_id, owner_token, guest_user_id, role="member", is_owner=False)

    outsider_token, _ = _register_and_session(
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Outsider Writer",
    )

    task_id = _create_task(owner_token, project_id)
    requirement_id = _create_requirement(guest_token, project_id, task_id)

    outsider_response = client.post(
        "/api/requirements",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={
            "project_id": project_id,
            "title": "Outsider should not create requirements",
            "requirement_type": "thread_request",
            "status": "waiting_response",
        },
    )
    assert outsider_response.status_code == 403
    assert outsider_response.json()["error"]["code"] == "PERMISSION_DENIED"

    update_response = client.patch(
        f"/api/requirements/{requirement_id}",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"status": "ready", "context_summary": "Member update is allowed."},
    )
    assert update_response.status_code == 200

    reply_response = client.post(
        f"/api/requirements/{requirement_id}/reply",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"sender_type": "agent", "sender_id": "agent-ui", "message": "member reply", "status": "answered"},
    )
    assert reply_response.status_code == 200

    respond_response = client.post(
        f"/api/requirements/{requirement_id}/respond",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"sender_type": "agent", "sender_id": "agent-ui", "message": "member respond", "status": "answered"},
    )
    assert respond_response.status_code == 200

    route_response = client.post(
        f"/api/requirements/{requirement_id}/route",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"from_agent": "agent-ui", "to_agent": "agent-robot", "note": "route by member"},
    )
    assert route_response.status_code == 200

    message_response = client.post(
        f"/api/requirements/{requirement_id}/messages",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={
            "project_id": project_id,
            "message_type": "requirement_message",
            "sender_type": "agent",
            "sender_id": "agent-ui",
            "body": "member requirement message",
            "data": {},
        },
    )
    assert message_response.status_code == 200

    for path, payload in [
        (f"/api/requirements/{requirement_id}/accept", {"actor_type": "human", "actor_id": guest_user_id}),
        (f"/api/requirements/{requirement_id}/escalate", {"actor_type": "human", "actor_id": guest_user_id}),
        (f"/api/requirements/{requirement_id}/close", {"actor_type": "human", "actor_id": guest_user_id}),
        (
            f"/api/requirements/{requirement_id}/promote-to-knowledge",
            {"actor_type": "human", "actor_id": guest_user_id, "target_type": "knowledge"},
        ),
        (
            f"/api/requirements/{requirement_id}/respond",
            {"sender_type": "agent", "sender_id": "agent-ui", "message": "member respond"},
        ),
    ]:
        response = client.post(path, headers={"Authorization": f"Bearer {guest_token}"}, json=payload)
        if path.endswith("/respond"):
            assert response.status_code == 200
        else:
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
