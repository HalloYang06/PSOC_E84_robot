from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member as shared_add_project_member
from tests.helpers import auth_headers
from tests.helpers import create_handoff as shared_create_handoff
from tests.helpers import create_project as shared_create_project
from tests.helpers import create_requirement as shared_create_requirement
from tests.helpers import create_task as shared_create_task
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
        name_prefix="Message Access",
        github_url="https://example.com/message.git",
        local_git_url="/workspace/message.git",
    )["id"]


def _add_member(project_id: str, token: str, user_id: str, role: str = "member", is_owner: bool = False) -> None:
    shared_add_project_member(client, project_id, token, user_id, role=role, is_owner=is_owner)


def _create_task(token: str, project_id: str) -> str:
    return shared_create_task(
        client,
        token,
        project_id,
        title="Message access task",
        description="Task used to scope message writes.",
        module="messages",
        priority="P2",
        status="waiting_approval",
        branch="feature/message-access",
        assignee_agent_id="agent-ui",
        reviewers=["lead"],
        acceptance_criteria=["messages are scoped to project membership"],
    )["id"]


def _create_requirement(token: str, project_id: str, task_id: str) -> str:
    return shared_create_requirement(
        client,
        token,
        project_id=project_id,
        task_id=task_id,
        title="Message access requirement",
        requirement_type="thread_request",
        status="waiting_response",
        context_summary="Scope requirement messages by project membership.",
        expected_output="Permission checks are enforced.",
        opening_message="Please protect requirement message writes.",
    )["id"]


def _create_approval(token: str, project_id: str, task_id: str) -> str:
    response = client.post(
        "/api/approvals",
        headers=auth_headers(token),
        json={
            "project_id": project_id,
            "task_id": task_id,
            "level": "H4",
            "action": "deploy",
            "notes": "approval for message access",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _create_handoff(token: str, project_id: str, task_id: str) -> str:
    return shared_create_handoff(
        client,
        token,
        project_id,
        task_id,
        handoff_from="agent-ui",
        handoff_to="agent-review",
        summary="handoff for message access",
        reason="validate project-scoped access",
        current_status="ready",
        notes="message access handoff",
    )["id"]


def test_message_writes_follow_project_membership_across_entities() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    member_token, member_user_id = _register_and_session(
        f"member-{uuid4().hex[:8]}@example.com",
        "Member Writer",
    )
    _add_member(project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_token, _ = _register_and_session(
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Outsider Writer",
    )

    task_id = _create_task(owner_token, project_id)
    requirement_id = _create_requirement(owner_token, project_id, task_id)
    approval_id = _create_approval(owner_token, project_id, task_id)
    handoff_id = _create_handoff(owner_token, project_id, task_id)

    for path, payload in [
        (
            "/api/messages",
            {
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "body": "project thread message",
            },
        ),
        (
            f"/api/messages/tasks/{task_id}",
            {
                "body": "task thread message",
            },
        ),
        (
            f"/api/requirements/{requirement_id}/messages",
            {
                "body": "requirement thread message",
            },
        ),
        (
            f"/api/approvals/{approval_id}/messages",
            {
                "body": "approval thread message",
            },
        ),
        (
            f"/api/handoffs/{handoff_id}/messages",
            {
                "body": "handoff thread message",
            },
        ),
        (
            "/api/messages/project/" + project_id,
            {
                "project_id": project_id,
                "body": "project alias thread message",
            },
        ),
        (
            f"/api/messages/task/{task_id}",
            {
                "project_id": project_id,
                "body": "task alias thread message",
            },
        ),
        (
            f"/api/messages/requirement/{requirement_id}",
            {
                "project_id": project_id,
                "body": "requirement alias thread message",
            },
        ),
        (
            f"/api/messages/approval/{approval_id}",
            {
                "project_id": project_id,
                "body": "approval alias thread message",
            },
        ),
        (
            f"/api/messages/handoff/{handoff_id}",
            {
                "project_id": project_id,
                "body": "handoff alias thread message",
            },
        ),
        (
            f"/api/messages/task/{task_id}/messages",
            {
                "project_id": project_id,
                "body": "task nested alias thread message",
            },
        ),
    ]:
        response = client.post(path, headers={"Authorization": f"Bearer {member_token}"}, json=payload)
        assert response.status_code == 200

    for path, payload in [
        (
            "/api/messages",
            {
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "body": "blocked project message",
            },
        ),
        (f"/api/messages/tasks/{task_id}", {"body": "blocked task message"}),
        (f"/api/messages/task/{task_id}", {"project_id": project_id, "body": "blocked task alias message"}),
        (f"/api/requirements/{requirement_id}/messages", {"body": "blocked requirement message"}),
        (f"/api/messages/requirement/{requirement_id}", {"project_id": project_id, "body": "blocked requirement alias message"}),
        (f"/api/approvals/{approval_id}/messages", {"body": "blocked approval message"}),
        (f"/api/messages/approval/{approval_id}", {"project_id": project_id, "body": "blocked approval alias message"}),
        (f"/api/handoffs/{handoff_id}/messages", {"body": "blocked handoff message"}),
        (f"/api/messages/handoff/{handoff_id}", {"project_id": project_id, "body": "blocked handoff alias message"}),
    ]:
        response = client.post(path, headers={"Authorization": f"Bearer {outsider_token}"}, json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
