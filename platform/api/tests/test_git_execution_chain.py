from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _issue_session_token() -> tuple[str, str]:
    response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["id"]


def _create_project(token: str) -> str:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Execution Chain {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/execution-chain.git",
            "local_git_url": "/workspace/execution-chain.git",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _add_member(project_id: str, token: str, user_id: str, *, role: str = "owner", is_owner: bool = True) -> None:
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


def _create_task(token: str, project_id: str, *, title: str, branch: str, status: str) -> dict[str, object]:
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": title,
            "description": f"{title} description",
            "module": "git",
            "priority": "P2",
            "status": status,
            "branch": branch,
            "assignee_agent_id": "agent-ui",
            "reviewers": ["lead"],
            "acceptance_criteria": ["execution chain reflects sync and rollback readiness"],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_git_execution_chain_links_branch_readiness_to_sync_and_rollback() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_member(project_id, token, user_id)

    ready_task = _create_task(token, project_id, title="Ready branch", branch="feature/execution-ready", status="ready")
    blocked_task = _create_task(
        token,
        project_id,
        title="Blocked branch",
        branch="feature/execution-blocked",
        status="reviewing",
    )

    approval_response = client.post(
        "/api/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "task_id": blocked_task["id"],
            "level": "H4",
            "action": "release",
            "notes": "execution gate pending",
        },
    )
    assert approval_response.status_code == 200

    sync_response = client.post(
        f"/api/git/projects/{project_id}/sync-github",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "actor_type": "human",
            "actor_id": user_id,
            "provider": "github",
            "notes": "sync before execution review",
        },
    )
    assert sync_response.status_code == 200

    rollback_response = client.post(
        f"/api/git/projects/{project_id}/rollback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "actor_type": "human",
            "actor_id": user_id,
            "target_ref": "develop",
            "notes": "rollback after execution review",
        },
    )
    assert rollback_response.status_code == 200

    response = client.get(
        f"/api/git/projects/{project_id}/execution",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["summary"]["branch_count"] == 2
    assert payload["summary"]["merge_ready_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["sync_status"] == "attention"
    assert payload["summary"]["rollback_status"] == "ready"
    assert payload["summary"]["last_sync_at"] is not None
    assert payload["summary"]["last_rollback_at"] is not None
    assert payload["summary"]["recent_activity_count"] >= 2
    assert ready_task["branch"] == "feature/execution-ready"

    actions = {item["action"]: item for item in payload["actions"]}
    assert actions["sync_github"]["ready"] is False
    assert actions["sync_github"]["status"] == "attention"
    assert actions["rollback"]["ready"] is True
    assert actions["rollback"]["status"] == "ready"
    assert "blocked branch" in " / ".join(actions["sync_github"]["blockers"])
