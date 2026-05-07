from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member as shared_add_project_member
from tests.helpers import create_approval as shared_create_approval
from tests.helpers import create_project as shared_create_project
from tests.helpers import create_task as shared_create_task
from tests.helpers import issue_session_token as shared_issue_session_token
from tests.helpers import register_user as shared_register_user


client = TestClient(app)


def _validation_errors(response) -> list[dict[str, object]]:
    payload = response.json()
    if "detail" in payload and isinstance(payload["detail"], list):
        return payload["detail"]
    return ((payload.get("error") or {}).get("details") or {}).get("errors") or []


def _issue_session_token() -> tuple[str, str]:
    return shared_issue_session_token(client)


def _create_project(token: str) -> dict[str, object]:
    return shared_create_project(
        client,
        token,
        name_prefix="Approval Security",
        description="security regression project",
        project_type="robotics",
        default_branch="main",
        develop_branch="develop",
    )


def _grant_owner_member(project_id: str, token: str, user_id: str) -> None:
    shared_add_project_member(client, project_id, token, user_id, role="owner", is_owner=True)


def _create_task(token: str, project_id: str) -> dict[str, object]:
    return shared_create_task(
        client,
        token,
        project_id,
        title="Approval gate task",
        description="used to verify approval security",
        module="core",
        priority="P1",
        status="ready",
        branch="feature/approval-gate",
    )


def _create_pending_approval(token: str, project_id: str, task_id: str) -> dict[str, object]:
    return shared_create_approval(
        client,
        token,
        project_id=project_id,
        task_id=task_id,
        level="H3",
        action="deploy",
        status="pending",
        notes="awaiting human review",
    )


def test_approval_create_rejects_client_supplied_final_status() -> None:
    token, user_id = _issue_session_token()
    project = _create_project(token)
    _grant_owner_member(project["id"], token, user_id)
    task = _create_task(token, project["id"])

    response = client.post(
        "/api/approvals",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project["id"],
            "task_id": task["id"],
            "level": "H4",
            "action": "prod_release",
            "status": "approved",
            "approver_user_id": "spoofed-user",
            "notes": "should not be accepted",
        },
    )
    assert response.status_code == 422
    detail = _validation_errors(response)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "status" for item in detail)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "approver_user_id" for item in detail)


def test_approval_patch_rejects_client_supplied_status_change() -> None:
    token, user_id = _issue_session_token()
    project = _create_project(token)
    _grant_owner_member(project["id"], token, user_id)
    task = _create_task(token, project["id"])
    approval = _create_pending_approval(token, project["id"], task["id"])

    response = client.patch(
        f"/api/approvals/{approval['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "status": "approved",
            "approver_user_id": "spoofed-user",
            "notes": "direct patch should fail",
        },
    )
    assert response.status_code == 422
    detail = _validation_errors(response)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "status" for item in detail)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "approver_user_id" for item in detail)


def test_approval_patch_rejects_level_or_action_mutation() -> None:
    token, user_id = _issue_session_token()
    project = _create_project(token)
    _grant_owner_member(project["id"], token, user_id)
    task = _create_task(token, project["id"])
    approval = _create_pending_approval(token, project["id"], task["id"])

    response = client.patch(
        f"/api/approvals/{approval['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "level": "H1",
            "action": "downgrade",
            "notes": "mutating level should fail",
        },
    )
    assert response.status_code == 422
    detail = _validation_errors(response)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "level" for item in detail)
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "action" for item in detail)


def test_approval_actions_bind_to_authenticated_user() -> None:
    token, user_id = _issue_session_token()
    project = _create_project(token)
    _grant_owner_member(project["id"], token, user_id)
    task = _create_task(token, project["id"])

    scenarios = [
        ("approve", "approved"),
        ("reject", "rejected"),
        ("request-changes", "needs_changes"),
    ]

    for action_name, expected_status in scenarios:
        approval = _create_pending_approval(token, project["id"], task["id"])
        response = client.post(
            f"/api/approvals/{approval['id']}/{action_name}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "notes": f"{action_name} via real principal",
            },
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["status"] == expected_status
        assert payload["approver_user_id"] == user_id
        assert payload["approver_user_id"] != "spoofed-user"


def test_approval_actions_ignore_spoofed_level_overrides() -> None:
    token, user_id = _issue_session_token()
    project = _create_project(token)
    _grant_owner_member(project["id"], token, user_id)
    task = _create_task(token, project["id"])
    approval = _create_pending_approval(token, project["id"], task["id"])

    response = client.post(
        f"/api/approvals/{approval['id']}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "level": "H1",
            "notes": "approve should not let the client rewrite level",
        },
    )
    assert response.status_code == 422
    assert any(item["type"] == "extra_forbidden" and item["loc"][-1] == "level" for item in _validation_errors(response))
