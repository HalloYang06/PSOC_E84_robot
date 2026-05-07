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
            "name": f"Merge Readiness {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/merge-readiness.git",
            "local_git_url": "/workspace/merge-readiness.git",
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
            "acceptance_criteria": ["merge readiness is surfaced"],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_git_merge_readiness_summarizes_blockers_and_ready_branches() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_member(project_id, token, user_id)

    ready_task = _create_task(token, project_id, title="Ready branch", branch="feature/ready-merge", status="ready")
    merged_task = _create_task(token, project_id, title="Merged branch", branch="feature/merged-merge", status="done")
    blocked_task = _create_task(
        token,
        project_id,
        title="Blocked branch",
        branch="feature/blocked-merge",
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
            "notes": "release gate pending",
        },
    )
    assert approval_response.status_code == 200

    response = client.get(
        f"/api/git/projects/{project_id}/merge-readiness",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["summary"]["total_branches"] == 3
    assert payload["summary"]["merge_ready_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["merged_count"] == 1
    assert payload["summary"]["attention_count"] >= 1

    branches = {item["task_id"]: item for item in payload["branches"]}
    assert branches[ready_task["id"]]["merge_ready"] is True
    assert branches[ready_task["id"]]["blocker_count"] == 0
    assert branches[merged_task["id"]]["pr_state"] == "merged"
    assert branches[blocked_task["id"]]["merge_ready"] is False
    assert branches[blocked_task["id"]]["blocker_count"] >= 2
    assert "high-risk approval" in " / ".join(branches[blocked_task["id"]]["blockers"])
