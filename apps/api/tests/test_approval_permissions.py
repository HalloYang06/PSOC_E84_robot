from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, create_project, create_task, issue_session_token, register_user


client = TestClient(app)


def test_approval_writes_require_project_membership_and_privilege() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Approval Permissions",
        github_url="https://example.com/approval.git",
        local_git_url="/workspace/approval.git",
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Approval permissions task",
        branch=f"feature/approval-permissions-{uuid4().hex[:8]}",
        status="waiting_approval",
    )
    task_id = task["id"]

    member_user_id, member_email = register_user(client, f"member-{uuid4().hex[:8]}@example.com", "Approval Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Approval Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    outsider_response = client.post(
        "/api/approvals",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={
            "project_id": project_id,
            "task_id": task_id,
            "level": "H4",
            "action": "deploy",
            "notes": "outsider should not create approvals",
        },
    )
    assert outsider_response.status_code == 403
    assert outsider_response.json()["error"]["code"] == "PERMISSION_DENIED"

    member_response = client.post(
        "/api/approvals",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "project_id": project_id,
            "task_id": task_id,
            "level": "H4",
            "action": "deploy",
            "notes": "member should not create high risk approvals",
        },
    )
    assert member_response.status_code == 403
    assert member_response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    create_response = client.post(
        "/api/approvals",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "project_id": project_id,
            "task_id": task_id,
            "level": "H4",
            "action": "deploy",
            "notes": "owner can create the approval",
        },
    )
    assert create_response.status_code == 200
    approval = create_response.json()["data"]
    approval_id = approval["id"]
    assert approval["approver_user_id"] == owner_user_id

    outsider_message_response = client.post(
        f"/api/approvals/{approval_id}/messages",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "sender_type": "human",
            "sender_id": outsider_user_id,
            "body": "outsider should not write approval messages",
            "data": {},
        },
    )
    assert outsider_message_response.status_code == 403

    approval_response = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "notes": "approved by the owner",
        },
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()["data"]
    assert approved["status"] == "approved"
    assert approved["approver_user_id"] == owner_user_id

    message_response = client.post(
        f"/api/approvals/{approval_id}/messages",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "sender_type": "human",
            "sender_id": owner_user_id,
            "body": "approval message is now protected",
            "data": {},
        },
    )
    assert message_response.status_code == 200
