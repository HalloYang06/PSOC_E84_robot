from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import _ensure_runtime_configuration
from app.main import app
from app.settings import get_settings
from tests.helpers import create_approval, create_task


client = TestClient(app)


def _issue_session() -> tuple[str, str]:
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
            "name": f"Invitation Audit {suffix}",
            "project_type": "platform",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


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
    payload = register_response.json()["data"]
    session_response = client.post("/api/auth/session", json={"email": email, "password": "password"})
    assert session_response.status_code == 200
    session_payload = session_response.json()["data"]
    return session_payload["access_token"], session_payload["user"]["id"]


def test_auth_session_issues_access_token() -> None:
    response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    assert response.status_code == 200

    payload = response.json()["data"]
    assert payload["token_type"] == "bearer"
    assert payload["access_token"].startswith("ai-auth.v1.")
    assert payload["principal"]["actor_type"] == "human"
    assert payload["principal"]["authenticated"] is True
    assert payload["user"]["last_seen_at"]
    assert payload["user"]["online_state"] == "online"
    assert payload["user"]["online_label"] == "账号在线"


def test_invalid_bearer_blocks_project_write() -> None:
    response = client.post(
        "/api/projects",
        headers={"Authorization": "Bearer invalid-token"},
        json={"name": "Blocked Project"},
    )
    assert response.status_code == 401

    payload = response.json()
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_missing_auth_does_not_bootstrap_project_write() -> None:
    response = client.post(
        "/api/projects",
        json={"name": "No Bootstrap Project"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_session_token_allows_project_create() -> None:
    session_response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    token = session_response.json()["data"]["access_token"]

    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Auth Guarded Project"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Auth Guarded Project"


def test_project_creator_is_added_as_owner_member() -> None:
    token, user_id = _issue_session()

    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Owner Linked Project"},
    )
    assert response.status_code == 200
    project_id = response.json()["data"]["id"]

    members_response = client.get(
        f"/api/auth/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert members_response.status_code == 200
    members = members_response.json()["data"]
    owner_member = next((item for item in members if item["user_id"] == user_id), None)

    assert owner_member is not None
    assert owner_member["role"] == "owner"
    assert owner_member["is_owner"] is True
    assert owner_member["status"] == "active"


def test_project_presence_marks_member_inside_project() -> None:
    token, user_id = _issue_session()
    project_id = _create_project(token)

    response = client.post(
        f"/api/projects/{project_id}/presence",
        headers={"Authorization": f"Bearer {token}"},
        json={"path": f"/projects/{project_id}?tab=human-party"},
    )
    assert response.status_code == 200

    payload = response.json()["data"]
    assert payload["user_id"] == user_id
    assert payload["project_presence_state"] == "online"
    assert payload["project_presence_label"] == "正在项目里"
    assert payload["last_project_seen_at"]
    assert payload["last_project_path"].startswith(f"/projects/{project_id}")

    members_response = client.get(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert members_response.status_code == 200
    owner_member = next((item for item in members_response.json()["data"] if item["user_id"] == user_id), None)
    assert owner_member is not None
    assert owner_member["project_presence_state"] == "online"
    assert owner_member["user"]["online_state"] == "online"


def test_project_presence_rejects_non_member() -> None:
    owner_token, _ = _issue_session()
    project_id = _create_project(owner_token)
    outsider_email = f"presence-outsider-{uuid4().hex[:8]}@example.com"
    outsider_token, _ = _register_and_session(outsider_email, "Presence Outsider")

    response = client.post(
        f"/api/projects/{project_id}/presence",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={"path": f"/projects/{project_id}"},
    )
    assert response.status_code == 403


def test_session_token_round_trips_to_me_endpoint() -> None:
    session_response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    payload = session_response.json()["data"]
    token = payload["access_token"]
    user_id = payload["user"]["id"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    me = response.json()["data"]
    assert me["principal"]["user_id"] == user_id
    assert me["principal"]["actor_type"] == "human"
    assert me["user"]["id"] == user_id


def test_workspace_endpoint_returns_user_projects() -> None:
    token, user_id = _issue_session()
    project_id = _create_project(token)

    response = client.get("/api/auth/workspace", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    payload = response.json()["data"]
    assert payload["user"]["id"] == user_id
    project = next((item for item in payload["projects"] if item["project_id"] == project_id), None)

    assert project is not None
    assert project["role"] == "owner"
    assert project["is_owner"] is True
    assert project["pending_human_review_count"] == 0


def test_workspace_endpoint_surfaces_pending_human_reviews() -> None:
    token, _ = _issue_session()
    project_id = _create_project(token)
    task = create_task(
        client,
        token,
        project_id,
        title="真实板卡上电前确认",
        status="waiting_approval",
        branch=f"feature/human-review-{uuid4().hex[:8]}",
    )
    create_approval(
        client,
        token,
        project_id=project_id,
        task_id=task["id"],
        level="H3",
        action="power_on_board",
        notes="真实硬件上电前必须人工确认。",
    )

    response = client.get("/api/auth/workspace", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    project = next((item for item in response.json()["data"]["projects"] if item["project_id"] == project_id), None)
    assert project is not None
    assert project["pending_human_review_count"] == 2
    assert project["pending_human_review_title"] == "真实板卡上电前确认"
    assert project["pending_human_review_level"] in {"H3", "task"}


def test_workspace_and_project_list_are_isolated_per_account() -> None:
    owner_token, _ = _issue_session()
    owner_project_id = _create_project(owner_token)

    member_email = f"workspace-isolation-{uuid4().hex[:8]}@example.com"
    member_token, _ = _register_and_session(member_email, "Workspace Isolation Member")
    member_project_id = _create_project(member_token)

    owner_workspace = client.get("/api/auth/workspace", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_workspace.status_code == 200
    owner_project_ids = {str(item["project_id"]) for item in owner_workspace.json()["data"]["projects"]}
    assert owner_project_id in owner_project_ids
    assert member_project_id not in owner_project_ids

    member_workspace = client.get("/api/auth/workspace", headers={"Authorization": f"Bearer {member_token}"})
    assert member_workspace.status_code == 200
    member_project_ids = {str(item["project_id"]) for item in member_workspace.json()["data"]["projects"]}
    assert member_project_id in member_project_ids
    assert owner_project_id not in member_project_ids

    owner_projects = client.get("/api/projects", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_projects.status_code == 200
    owner_list_ids = {str(item["id"]) for item in owner_projects.json()["data"]}
    assert owner_project_id in owner_list_ids
    assert member_project_id not in owner_list_ids

    member_projects = client.get("/api/projects", headers={"Authorization": f"Bearer {member_token}"})
    assert member_projects.status_code == 200
    member_list_ids = {str(item["id"]) for item in member_projects.json()["data"]}
    assert member_project_id in member_list_ids
    assert owner_project_id not in member_list_ids


def test_auth_metadata_endpoints_require_real_auth() -> None:
    responses = [
        client.get("/api/auth/users"),
        client.get("/api/auth/summary"),
        client.get("/api/auth/invitations"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_platform_auth_metadata_endpoints_require_operator_role() -> None:
    owner_token, user_id = _issue_session()
    project_id = _create_project(owner_token)
    invitee_email = f"metadata-invitee-{uuid4().hex[:8]}@example.com"
    member_token, _ = _register_and_session(f"metadata-member-{uuid4().hex[:8]}@example.com", "Metadata Member")

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    invite_response = client.post(
        "/api/auth/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": invitee_email,
            "project_id": project_id,
            "role": "collaborator",
            "note": "operator-only metadata listing check",
        },
    )
    assert invite_response.status_code == 200

    member_responses = [
        client.get("/api/auth/users", headers={"Authorization": f"Bearer {member_token}"}),
        client.get("/api/auth/summary", headers={"Authorization": f"Bearer {member_token}"}),
        client.get("/api/auth/invitations", headers={"Authorization": f"Bearer {member_token}"}),
    ]
    for response in member_responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    owner_users = client.get("/api/auth/users", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_users.status_code == 200
    assert any(item["email"] == "lead@example.com" for item in owner_users.json()["data"])

    owner_summary = client.get("/api/auth/summary", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_summary.status_code == 200
    assert owner_summary.json()["data"]["users"] >= 1

    owner_invitations = client.get("/api/auth/invitations", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_invitations.status_code == 200
    assert any(item["email"] == invitee_email for item in owner_invitations.json()["data"])


def test_platform_diagnostic_reads_require_operator_role() -> None:
    owner_token, owner_user_id = _issue_session()
    project_id = _create_project(owner_token)
    member_token, _ = _register_and_session(
        f"diag-member-{uuid4().hex[:8]}@example.com",
        "Diagnostic Member",
    )

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": owner_user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    protected_paths = [
        "/api/agents",
        "/api/git/status",
        "/api/git/activity",
        "/api/lab/status",
        "/api/lab/checklist",
        "/api/lab/high-risk",
        "/api/lab/audit",
        "/api/lab/short-chain",
    ]
    for path in protected_paths:
        anonymous = client.get(path)
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "UNAUTHORIZED"

        member = client.get(path, headers={"Authorization": f"Bearer {member_token}"})
        assert member.status_code == 403
        assert member.json()["error"]["code"] == "PERMISSION_DENIED"

        owner = client.get(path, headers={"Authorization": f"Bearer {owner_token}"})
        assert owner.status_code == 200


def test_project_member_and_invitation_reads_require_project_access() -> None:
    owner_token, user_id = _issue_session()
    project_id = _create_project(owner_token)
    outsider_token, _ = _register_and_session(f"auth-outsider-{uuid4().hex[:8]}@example.com", "Auth Outsider")

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    anonymous_members = client.get(f"/api/auth/projects/{project_id}/members")
    assert anonymous_members.status_code == 401

    outsider_members = client.get(
        f"/api/auth/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert outsider_members.status_code == 403
    assert outsider_members.json()["error"]["code"] == "PERMISSION_DENIED"

    anonymous_invites = client.get(f"/api/auth/projects/{project_id}/invitations")
    assert anonymous_invites.status_code == 401

    outsider_invites = client.get(
        f"/api/auth/projects/{project_id}/invitations",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert outsider_invites.status_code == 403
    assert outsider_invites.json()["error"]["code"] == "PERMISSION_DENIED"


def test_project_git_reads_require_project_access() -> None:
    owner_token, user_id = _issue_session()
    project_id = _create_project(owner_token)
    outsider_token, _ = _register_and_session(f"git-outsider-{uuid4().hex[:8]}@example.com", "Git Outsider")

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    protected_paths = [
        f"/api/git/projects/{project_id}/workspace",
        f"/api/git/projects/{project_id}/branches",
        f"/api/git/projects/{project_id}/merge-readiness",
        f"/api/git/projects/{project_id}/execution",
        f"/api/git/projects/{project_id}/activity",
    ]

    for path in protected_paths:
        anonymous = client.get(path)
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "UNAUTHORIZED"

        outsider = client.get(path, headers={"Authorization": f"Bearer {outsider_token}"})
        assert outsider.status_code == 403
        assert outsider.json()["error"]["code"] == "PERMISSION_DENIED"

        owner = client.get(path, headers={"Authorization": f"Bearer {owner_token}"})
        assert owner.status_code == 200


def test_invitations_do_not_expose_tokens_but_accept_still_works() -> None:
    token, user_id = _issue_session()
    project_id = _create_project(token)
    invitee_email = f"invitee-{uuid4().hex[:8]}@example.com"
    invitee_token, invitee_user_id = _register_and_session(invitee_email, "Invitee User")

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    create_response = client.post(
        "/api/auth/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": invitee_email,
            "project_id": project_id,
            "role": "collaborator",
            "invited_by_user_id": user_id,
            "note": "join the project",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert "token" not in created

    list_response = client.get(
        "/api/auth/invitations",
        params={"project_id": project_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    invitations = list_response.json()["data"]
    assert invitations
    assert "token" not in invitations[0]

    invitation_id = created["id"]
    accept_response = client.post(
        f"/api/auth/invitations/{invitation_id}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
        json={"name": "Invitee User", "password": "password123"},
    )
    assert accept_response.status_code == 200
    accepted = accept_response.json()["data"]
    assert "token" not in accepted["invitation"]
    assert accepted["invitation"]["status"] == "accepted"
    assert accepted["user"]["id"] == invitee_user_id
    assert accepted["user"]["email"] == invitee_email


def test_logged_in_user_can_accept_workspace_invitation_without_profile_payload() -> None:
    token, user_id = _issue_session()
    project_id = _create_project(token)
    invitee_email = f"workspace-{uuid4().hex[:8]}@example.com"
    invitee_token, invitee_user_id = _register_and_session(invitee_email, "Workspace User")

    owner_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert owner_response.status_code == 200

    create_response = client.post(
        "/api/auth/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": invitee_email,
            "project_id": project_id,
            "role": "collaborator",
            "invited_by_user_id": user_id,
            "note": "join from workspace",
        },
    )
    assert create_response.status_code == 200
    invitation_id = create_response.json()["data"]["id"]

    accept_response = client.post(
        f"/api/auth/invitations/{invitation_id}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
        json={},
    )
    assert accept_response.status_code == 200
    accepted = accept_response.json()["data"]

    assert accepted["user"]["id"] == invitee_user_id
    assert accepted["invitation"]["status"] == "accepted"

    workspace_response = client.get("/api/auth/workspace", headers={"Authorization": f"Bearer {invitee_token}"})
    assert workspace_response.status_code == 200
    workspace_projects = workspace_response.json()["data"]["projects"]
    project = next((item for item in workspace_projects if item["project_id"] == project_id), None)

    assert project is not None
    assert project["role"] == "collaborator"


def test_production_rejects_insecure_runtime_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("ALLOW_BOOTSTRAP_AUTH", "true")
    monkeypatch.setenv("DATABASE_AUTO_CREATE", "false")
    monkeypatch.setenv("DATABASE_AUTO_SEED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ALLOW_BOOTSTRAP_AUTH"):
            _ensure_runtime_configuration()
    finally:
        get_settings.cache_clear()
