from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient


DEFAULT_PASSWORD = "password"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def request_json(
    client: TestClient,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
):
    headers = auth_headers(token) if token else {}
    return client.request(method.upper(), path, headers=headers, json=payload)


def assert_write_allowed(
    client: TestClient,
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
):
    response = request_json(client, method, path, token, payload)
    assert response.status_code < 400
    return response


def assert_write_rejected(
    client: TestClient,
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
    *,
    expected_status: int = 403,
    expected_code: str = "PERMISSION_DENIED",
):
    response = request_json(client, method, path, token, payload)
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    return response


def issue_session_token(client: TestClient, email: str = "lead@example.com", password: str = DEFAULT_PASSWORD) -> tuple[str, str]:
    response = client.post("/api/auth/session", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["id"]


def register_user(client: TestClient, email: str, name: str, password: str = DEFAULT_PASSWORD) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": name,
            "password": password,
            "global_role": "member",
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["id"], payload["email"]


def create_project(client: TestClient, token: str, *, name_prefix: str = "Collaborative Project", **overrides: Any) -> dict[str, Any]:
    suffix = uuid4().hex[:8]
    payload: dict[str, Any] = {
        "name": f"{name_prefix} {suffix}",
        "project_type": overrides.pop("project_type", "robotics"),
        "github_url": overrides.pop("github_url", "https://example.com/project.git"),
        "local_git_url": overrides.pop("local_git_url", "/workspace/project.git"),
        "default_branch": overrides.pop("default_branch", "main"),
        "develop_branch": overrides.pop("develop_branch", "develop"),
    }
    payload.update(overrides)
    response = client.post("/api/projects", headers=auth_headers(token), json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def add_project_member(
    client: TestClient,
    project_id: str,
    token: str,
    user_id: str,
    *,
    role: str = "member",
    is_owner: bool = False,
    status: str = "active",
) -> None:
    response = client.post(
        f"/api/projects/{project_id}/members",
        headers=auth_headers(token),
        json={
            "user_id": user_id,
            "role": role,
            "status": status,
            "is_owner": is_owner,
        },
    )
    assert response.status_code == 200


def create_task(client: TestClient, token: str, project_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "title": overrides.pop("title", "Permission test task"),
        "description": overrides.pop("description", "Task used for permission tests."),
        "module": overrides.pop("module", "permissions"),
        "priority": overrides.pop("priority", "P2"),
        "status": overrides.pop("status", "ready"),
        "branch": overrides.pop("branch", f"feature/{uuid4().hex[:8]}"),
        "assignee_agent_id": overrides.pop("assignee_agent_id", "agent-ui"),
        "reviewers": overrides.pop("reviewers", ["lead"]),
        "acceptance_criteria": overrides.pop("acceptance_criteria", ["permission checks are enforced"]),
    }
    payload.update(overrides)
    response = client.post("/api/tasks", headers=auth_headers(token), json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def create_requirement(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": overrides.pop("project_id", None),
        "task_id": overrides.pop("task_id", None),
        "title": overrides.pop("title", "Permission test requirement"),
        "requirement_type": overrides.pop("requirement_type", "thread_request"),
        "module": overrides.pop("module", "permissions"),
        "priority": overrides.pop("priority", "high"),
        "status": overrides.pop("status", "waiting_response"),
        "from_agent": overrides.pop("from_agent", "agent-ui"),
        "to_agent": overrides.pop("to_agent", "agent-review"),
        "context_summary": overrides.pop("context_summary", "Requirement used for permission tests."),
        "expected_output": overrides.pop("expected_output", "Permission checks are enforced."),
        "related_files": overrides.pop("related_files", []),
        "max_response_tokens": overrides.pop("max_response_tokens", 3000),
        "opening_message": overrides.pop("opening_message", "Please protect requirement writes."),
    }
    payload.update(overrides)
    response = client.post("/api/requirements", headers=auth_headers(token), json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def create_approval(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": overrides.pop("project_id", None),
        "task_id": overrides.pop("task_id", None),
        "level": overrides.pop("level", "H1"),
        "action": overrides.pop("action", "merge"),
        "notes": overrides.pop("notes", "approval for permission tests"),
    }
    overrides.pop("status", None)
    overrides.pop("approver_user_id", None)
    payload.update(overrides)
    response = client.post("/api/approvals", headers=auth_headers(token), json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def create_handoff(client: TestClient, token: str, project_id: str, task_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "handoff_from": overrides.pop("handoff_from", "agent-ui"),
        "handoff_to": overrides.pop("handoff_to", "agent-review"),
        "summary": overrides.pop("summary", "handoff for permission tests"),
        "reason": overrides.pop("reason", "validate project-scoped access"),
        "current_status": overrides.pop("current_status", "ready"),
        "notes": overrides.pop("notes", "permission test handoff"),
    }
    payload.update(overrides)
    response = client.post(f"/api/tasks/{task_id}/handoffs", headers=auth_headers(token), json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def setup_permission_workspace(client: TestClient, *, name_prefix: str = "Permission Audit") -> dict[str, Any]:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix=name_prefix,
        github_url="https://example.com/permission-audit.git",
        local_git_url="/workspace/permission-audit.git",
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    member_user_id, member_email = register_user(client, f"member-{uuid4().hex[:8]}@example.com", "Permission Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Permission Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Permission audit task",
        description="Task used to drive permission matrix tests.",
        module="permissions",
        priority="P1",
        status="waiting_approval",
        branch=f"feature/permission-audit-{uuid4().hex[:8]}",
        assignee_agent_id="agent-ui",
    )
    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Permission audit requirement",
        status="waiting_response",
        opening_message="Protect requirement writes.",
    )
    approval = create_approval(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        level="H3",
        action="deploy",
        status="pending",
        notes="permission audit approval",
    )
    handoff = create_handoff(client, owner_token, project_id, task["id"])

    return {
        "owner_token": owner_token,
        "owner_user_id": owner_user_id,
        "member_token": member_token,
        "member_user_id": member_user_id,
        "outsider_token": outsider_token,
        "outsider_user_id": outsider_user_id,
        "project": project,
        "project_id": project_id,
        "task": task,
        "task_id": task["id"],
        "requirement": requirement,
        "requirement_id": requirement["id"],
        "approval": approval,
        "approval_id": approval["id"],
        "handoff": handoff,
        "handoff_id": handoff["id"],
    }
