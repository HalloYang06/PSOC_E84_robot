from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import (
    add_project_member,
    assert_write_allowed,
    assert_write_rejected,
    create_approval,
    create_handoff,
    create_project,
    create_requirement,
    create_task,
    issue_session_token,
    register_user,
)


client = TestClient(app)


def _setup_workspace():
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Write Audit",
        github_url="https://example.com/audit.git",
        local_git_url="/workspace/audit.git",
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    member_user_id, member_email = register_user(client, f"member-{uuid4().hex[:8]}@example.com", "Audit Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Audit Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Write audit task",
        description="task for global permission audit",
        module="audit",
        priority="P1",
        status="waiting_approval",
        branch=f"feature/write-audit-{uuid4().hex[:8]}",
        assignee_agent_id="agent-ui",
    )
    task_id = task["id"]
    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task_id,
        title="Write audit requirement",
        status="waiting_response",
        opening_message="protect this requirement",
    )
    approval = create_approval(
        client,
        owner_token,
        project_id=project_id,
        task_id=task_id,
        level="H4",
        action="deploy",
        notes="write audit approval",
    )
    handoff = create_handoff(client, owner_token, project_id, task_id)

    return {
        "owner_token": owner_token,
        "owner_user_id": owner_user_id,
        "member_token": member_token,
        "member_user_id": member_user_id,
        "outsider_token": outsider_token,
        "outsider_user_id": outsider_user_id,
        "project_id": project_id,
        "task_id": task_id,
        "requirement_id": requirement["id"],
        "approval_id": approval["id"],
        "handoff_id": handoff["id"],
    }


def test_write_permission_audit_blocks_outsiders_across_core_write_routes() -> None:
    ctx = _setup_workspace()
    outsider = ctx["outsider_token"]
    project_id = ctx["project_id"]
    task_id = ctx["task_id"]
    requirement_id = ctx["requirement_id"]
    approval_id = ctx["approval_id"]
    handoff_id = ctx["handoff_id"]

    forbidden_routes = [
        (
            "POST",
            "/api/messages",
            {
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "body": "outsider project message",
            },
        ),
        ("POST", f"/api/messages/tasks/{task_id}", {"body": "outsider task message"}),
        ("POST", f"/api/messages/requirements/{requirement_id}", {"body": "outsider requirement message"}),
        ("POST", f"/api/messages/approvals/{approval_id}", {"body": "outsider approval message"}),
        ("POST", f"/api/messages/handoffs/{handoff_id}", {"body": "outsider handoff message"}),
        (
            "POST",
            "/api/requirements",
            {
                "project_id": project_id,
                "task_id": task_id,
                "title": "outsider requirement create",
                "status": "waiting_response",
            },
        ),
        ("PATCH", f"/api/requirements/{requirement_id}", {"status": "ready"}),
        (
            "POST",
            "/api/approvals",
            {
                "project_id": project_id,
                "task_id": task_id,
                "level": "H4",
                "action": "deploy",
            },
        ),
        ("POST", f"/api/git/projects/{project_id}/sync-github", {"provider": "github"}),
        ("POST", f"/api/git/projects/{project_id}/rollback", {"target_ref": "HEAD~1"}),
    ]

    for method, path, payload in forbidden_routes:
        assert_write_rejected(client, method, path, outsider, payload)


def test_write_permission_audit_requires_privilege_for_high_risk_routes() -> None:
    ctx = _setup_workspace()
    member = ctx["member_token"]
    project_id = ctx["project_id"]
    task_id = ctx["task_id"]
    requirement_id = ctx["requirement_id"]

    allowed_routes = [
        ("POST", f"/api/messages/tasks/{task_id}", {"body": "member task message"}),
        ("POST", f"/api/messages/requirements/{requirement_id}", {"body": "member requirement message"}),
        ("POST", f"/api/requirements/{requirement_id}/reply", {"message": "reply from member"}),
    ]
    for method, path, payload in allowed_routes:
        assert_write_allowed(client, method, path, member, payload)

    privileged_routes = [
        ("POST", "/api/approvals", {"project_id": project_id, "task_id": task_id, "level": "H4", "action": "deploy"}),
        ("POST", f"/api/requirements/{requirement_id}/accept", {"actor_type": "human"}),
        ("POST", f"/api/requirements/{requirement_id}/escalate", {"actor_type": "human"}),
        ("POST", f"/api/requirements/{requirement_id}/close", {"actor_type": "human"}),
        (
            "POST",
            f"/api/requirements/{requirement_id}/promote-to-knowledge",
            {"actor_type": "human", "target_type": "knowledge"},
        ),
        ("POST", f"/api/git/projects/{project_id}/sync-github", {"provider": "github"}),
        ("POST", f"/api/git/projects/{project_id}/rollback", {"target_ref": "HEAD~1"}),
    ]
    for method, path, payload in privileged_routes:
        response = client.request(method, path, headers={"Authorization": f"Bearer {member}"}, json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
