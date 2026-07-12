from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _session(email: str) -> tuple[str, str]:
    response = client.post("/api/auth/session", json={"email": email, "password": "password"})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["id"]


def _register_and_session(email: str, name: str) -> tuple[str, str]:
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": name,
            "password": "password",
            "global_role": "member",
        },
    )
    assert register_response.status_code == 200
    return _session(email)


def _create_project(token: str) -> str:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Permission Audit {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/project.git",
            "local_git_url": "/workspace/project.git",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _add_owner_member(project_id: str, token: str, user_id: str) -> None:
    response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert response.status_code == 200


def test_project_and_collaboration_writes_require_real_identity_and_membership() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    _add_owner_member(project_id, owner_token, owner_user_id)

    guest_email = f"guest-{uuid4().hex[:8]}@example.com"
    guest_token, guest_user_id = _register_and_session(guest_email, "Guest Writer")

    guest_member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": guest_user_id,
            "role": "member",
            "status": "active",
            "is_owner": False,
        },
    )
    assert guest_member_response.status_code == 200
    guest_member_id = guest_member_response.json()["data"]["id"]

    provider_response = client.post(
        f"/api/collaboration/projects/{project_id}/ai-providers",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "id": "codex",
            "label": "Codex",
            "kind": "openai",
            "enabled": True,
            "endpoint": "https://api.openai.com",
            "model": "gpt-5.4",
        },
    )
    assert provider_response.status_code == 200

    node_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "id": "pc-1",
            "label": "PC 1",
            "status": "online",
            "connection_kind": "ssh",
            "workspace_root": "D:/workspaces/pc-1",
            "git_root": "D:/workspaces/pc-1/repo",
        },
    )
    assert node_response.status_code == 200

    workstation_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "id": "frontend",
            "name": "Frontend",
            "agent_id": "ai-fe-lead",
            "computer_node_id": "pc-1",
            "ai_provider_id": "codex",
            "status": "active",
        },
    )
    assert workstation_response.status_code == 200

    invite_response = client.post(
        "/api/auth/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": guest_email,
            "project_id": project_id,
            "role": "collaborator",
            "note": "join the project",
        },
    )
    assert invite_response.status_code == 200
    _ = invite_response.json()["data"]["id"]

    collaboration_invite_response = client.post(
        f"/api/collaboration/projects/{project_id}/invites",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": guest_email,
            "role": "collaborator",
            "message": "join the collaboration workspace",
        },
    )
    assert collaboration_invite_response.status_code == 200
    collaboration_invitation_id = collaboration_invite_response.json()["data"]["id"]

    outsider_token, _ = _register_and_session(f"outsider-{uuid4().hex[:8]}@example.com", "Outsider Writer")

    forbidden_cases = [
        ("POST", f"/api/collaboration/projects/{project_id}/invites", {"email": "blocked@example.com", "role": "collaborator"}),
        ("PATCH", f"/api/collaboration/invites/{collaboration_invitation_id}", {"status": "revoked"}),
        ("POST", f"/api/collaboration/invites/{collaboration_invitation_id}/revoke", {}),
        ("POST", f"/api/collaboration/projects/{project_id}/members", {"user_id": guest_user_id, "role": "member"}),
        ("PATCH", f"/api/collaboration/projects/{project_id}/members/{guest_member_id}", {"role": "owner"}),
        ("DELETE", f"/api/collaboration/projects/{project_id}/members/{guest_member_id}", {}),
        ("PATCH", f"/api/collaboration/projects/{project_id}/config", {"ai_providers": []}),
        (
            "POST",
            f"/api/collaboration/projects/{project_id}/ai-providers",
            {"id": "blocked", "label": "Blocked", "kind": "openai", "enabled": True},
        ),
        (
            "PATCH",
            f"/api/collaboration/projects/{project_id}/ai-providers/codex",
            {"enabled": False},
        ),
        ("DELETE", f"/api/collaboration/projects/{project_id}/ai-providers/codex", {}),
        (
            "POST",
            f"/api/collaboration/projects/{project_id}/computer-nodes",
            {"id": "blocked-node", "label": "Blocked Node"},
        ),
        (
            "PATCH",
            f"/api/collaboration/projects/{project_id}/computer-nodes/pc-1",
            {"status": "standby"},
        ),
        ("DELETE", f"/api/collaboration/projects/{project_id}/computer-nodes/pc-1", {}),
        (
            "POST",
            f"/api/collaboration/projects/{project_id}/thread-workstations",
            {"id": "blocked-workstation", "name": "Blocked Workstation"},
        ),
        (
            "PATCH",
            f"/api/collaboration/projects/{project_id}/thread-workstations/frontend",
            {"status": "idle"},
        ),
        ("DELETE", f"/api/collaboration/projects/{project_id}/thread-workstations/frontend", {}),
        ("POST", "/api/messages", {"entity_type": "project", "entity_id": project_id, "project_id": project_id, "body": "blocked"}),
    ]

    for method, path, payload in forbidden_cases:
        response = client.request(method, path, headers={"Authorization": f"Bearer {outsider_token}"}, json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    allowed_member_message = client.post(
        "/api/messages",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={
            "entity_type": "project",
            "entity_id": project_id,
            "project_id": project_id,
            "message_type": "comment_message",
            "body": "member message",
        },
    )
    assert allowed_member_message.status_code == 200

    accept_response = client.post(
        f"/api/collaboration/invites/{collaboration_invitation_id}/accept",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"user_id": guest_user_id, "actor_type": "human", "actor_id": guest_user_id},
    )
    assert accept_response.status_code == 200


def test_project_member_can_manage_own_computer_node_but_not_others() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    _add_owner_member(project_id, owner_token, owner_user_id)

    member_email = f"member-node-{uuid4().hex[:8]}@example.com"
    member_token, member_user_id = _register_and_session(member_email, "Member Node Owner")

    member_add_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": member_user_id,
            "role": "member",
            "status": "active",
            "is_owner": False,
        },
    )
    assert member_add_response.status_code == 200

    owner_node_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "id": "owner-pc",
            "label": "Owner PC",
            "status": "online",
            "connection_kind": "local",
        },
    )
    assert owner_node_response.status_code == 200
    assert owner_node_response.json()["data"]["metadata"]["owner_user_id"] == owner_user_id

    member_node_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "id": "member-pc",
            "label": "Member PC",
            "status": "online",
            "connection_kind": "remote",
            "workspace_root": "D:/member/workspace",
        },
    )
    assert member_node_response.status_code == 200
    assert member_node_response.json()["data"]["metadata"]["owner_user_id"] == member_user_id

    member_update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/computer-nodes/member-pc",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"status": "standby", "git_root": "D:/member/workspace/repo"},
    )
    assert member_update_response.status_code == 200
    assert member_update_response.json()["data"]["status"] == "standby"
    assert member_update_response.json()["data"]["git_root"] == "D:/member/workspace/repo"

    member_pairing_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes/member-pc/pairing-token",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_pairing_response.status_code == 200
    assert member_pairing_response.json()["data"]["computer_node_id"] == "member-pc"
    assert member_pairing_response.json()["data"]["token"]

    member_workstation_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "id": "member-codex-thread",
            "name": "Member Codex Thread",
            "computer_node_id": "member-pc",
            "ai_provider_id": "codex",
            "status": "active",
        },
    )
    assert member_workstation_response.status_code == 200
    assert member_workstation_response.json()["data"]["computer_node_id"] == "member-pc"

    member_token_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/member-codex-thread/adapter-token",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_token_response.status_code == 200
    assert member_token_response.json()["data"]["token_available"] is True

    member_workstation_update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/member-codex-thread",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"status": "idle"},
    )
    assert member_workstation_update_response.status_code == 200
    assert member_workstation_update_response.json()["data"]["status"] == "idle"

    forbidden_owner_workstation_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "id": "owner-codex-thread",
            "name": "Owner Codex Thread",
            "computer_node_id": "owner-pc",
            "ai_provider_id": "codex",
            "status": "active",
        },
    )
    assert forbidden_owner_workstation_response.status_code == 403
    assert forbidden_owner_workstation_response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    forbidden_owner_pairing = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes/owner-pc/pairing-token",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert forbidden_owner_pairing.status_code == 403
    assert forbidden_owner_pairing.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    forbidden_owner_update = client.patch(
        f"/api/collaboration/projects/{project_id}/computer-nodes/owner-pc",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"status": "offline"},
    )
    assert forbidden_owner_update.status_code == 403
    assert forbidden_owner_update.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"


def test_collaboration_user_writes_require_authentication() -> None:
    response = client.post("/api/collaboration/users", json={"name": "No Auth User"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"

    token, _ = _session("lead@example.com")
    create_response = client.post(
        "/api/collaboration/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Auth User", "email": f"auth-{uuid4().hex[:8]}@example.com"},
    )
    assert create_response.status_code == 200
    user_id = create_response.json()["data"]["id"]

    update_response = client.patch(
        f"/api/collaboration/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "Auth User Updated"},
    )
    assert update_response.status_code == 200
