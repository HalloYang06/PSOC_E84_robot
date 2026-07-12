from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.project_member import ProjectMember
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.session import SessionLocal
from app.main import app
from app.settings import get_settings


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
            "name": f"Runner Permissions {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/runner-permissions.git",
            "local_git_url": "/workspace/runner-permissions.git",
            "default_branch": "main",
            "develop_branch": "develop",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-bind",
                        "label": "Bind Node",
                        "status": "online",
                        "host": "192.168.1.120",
                        "os": "Linux",
                    }
                ]
            },
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _add_member(project_id: str, token: str, user_id: str, role: str = "member", is_owner: bool = False) -> None:
    with SessionLocal() as db:
        member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        )
        if member is None:
            member = ProjectMember(project_id=project_id, user_id=user_id, role=role, status="active", is_owner=is_owner)
            db.add(member)
        else:
            member.role = role
            member.status = "active"
            member.is_owner = is_owner
        db.commit()


def _create_task(token: str, project_id: str, *, status: str = "ready") -> str:
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": "Runner permission task",
            "description": "Task used to verify transition permissions.",
            "module": "runner",
            "priority": "P2",
            "status": status,
            "branch": "feature/runner-permissions",
            "assignee_agent_id": "agent-ui",
            "reviewers": ["lead"],
            "acceptance_criteria": ["runner identity is enforced"],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _cleanup_runner_test_data(
    project_id: str,
    runner_id: str | None = None,
    task_id: str | None = None,
    claimed_task_id: str | None = None,
) -> None:
    with SessionLocal() as db:
        for target_task_id in {task_id, claimed_task_id}:
            if not target_task_id:
                continue
            db.query(TaskEvent).filter(TaskEvent.task_id == target_task_id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.task_id == target_task_id).delete(synchronize_session=False)
            db.query(Task).filter(Task.id == target_task_id).delete(synchronize_session=False)
        if runner_id:
            db.query(Runner).filter(Runner.id == runner_id).delete(synchronize_session=False)
        db.query(ProjectThreadWorkstation).filter(ProjectThreadWorkstation.project_id == project_id).delete(
            synchronize_session=False
        )
        db.query(ProjectAIProvider).filter(ProjectAIProvider.project_id == project_id).delete(synchronize_session=False)
        db.query(ProjectComputerNode).filter(ProjectComputerNode.project_id == project_id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.commit()


def test_runner_identity_is_not_derived_from_user_bearer() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    runner_id = None
    task_id = None
    claimed_task_id = None
    try:
        _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)
        task_id = _create_task(owner_token, project_id, status="ready")

        register_response = client.post(
            "/api/runners/register",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Bearer Runner",
                "capabilities": ["git"],
                "hardware_access": False,
            },
        )
        assert register_response.status_code == 401
        assert register_response.json()["error"]["code"] == "UNAUTHORIZED"

        heartbeat_response = client.post(
            "/api/runners/heartbeat",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"runner_id": f"runner-{uuid4().hex[:8]}"},
        )
        assert heartbeat_response.status_code == 401
        assert heartbeat_response.json()["error"]["code"] == "UNAUTHORIZED"

        register_ok_response = client.post(
            "/api/runners/register",
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Bootstrap Runner",
                "capabilities": ["git"],
                "hardware_access": False,
            },
        )
        assert register_ok_response.status_code == 200
        runner_id = register_ok_response.json()["data"]["id"]

        bind_response = client.post(
            f"/api/runners/{runner_id}/bindings",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"project_id": project_id, "computer_node_id": "pc-bind"},
        )
        assert bind_response.status_code == 200

        runner_detail_response = client.get(f"/api/runners/{runner_id}")
        assert runner_detail_response.status_code == 401
        assert runner_detail_response.json()["error"]["code"] == "UNAUTHORIZED"

        runner_workspace_response = client.get(f"/api/runners/{runner_id}/workspace")
        assert runner_workspace_response.status_code == 401
        assert runner_workspace_response.json()["error"]["code"] == "UNAUTHORIZED"

        runner_summary_response = client.get("/api/runners/summary")
        assert runner_summary_response.status_code == 401
        assert runner_summary_response.json()["error"]["code"] == "UNAUTHORIZED"

        next_task_bearer_response = client.get(
            f"/api/runners/{runner_id}/next-task",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert next_task_bearer_response.status_code == 401
        assert next_task_bearer_response.json()["error"]["code"] == "UNAUTHORIZED"

        next_task_response = client.get(f"/api/runners/{runner_id}/next-task")
        assert next_task_response.status_code == 200
        next_task = next_task_response.json()["data"]
        assert next_task["runner_id"] == runner_id
        assert next_task["claimed"] is True
        assert next_task["task"]["id"] == task_id
        assert next_task["task"]["status"] == "running"
        assert next_task["workspace"]["binding_count"] == 1
        assert next_task["workspace"]["bindings"][0]["project_id"] == project_id
        claimed_task_id = next_task["task"]["id"]

        runner_task_log_response = client.post(
            f"/api/runners/{runner_id}/tasks/{task_id}/logs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"level": "info", "message": "should not be accepted"},
        )
        assert runner_task_log_response.status_code == 401
        assert runner_task_log_response.json()["error"]["code"] == "UNAUTHORIZED"

        transition_response = client.post(
            f"/api/tasks/{task_id}/transition",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"status": "reviewing", "message": "human transition"},
        )
        assert transition_response.status_code == 200
        assert transition_response.json()["data"]["status"] == "reviewing"
    finally:
        _cleanup_runner_test_data(project_id, runner_id=runner_id, task_id=task_id, claimed_task_id=claimed_task_id)


def test_runner_binding_routes_remain_project_scoped() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    runner_id = None
    try:
        _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)

        outsider_token, outsider_user_id = _register_and_session(
            f"outsider-{uuid4().hex[:8]}@example.com",
            "Outsider Writer",
        )
        _add_member(project_id, owner_token, outsider_user_id, role="member", is_owner=False)

        runner_response = client.post(
            "/api/runners/register",
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Binding Runner",
                "capabilities": ["git"],
                "hardware_access": False,
            },
        )
        assert runner_response.status_code == 200
        runner_id = runner_response.json()["data"]["id"]

        bind_response = client.post(
            f"/api/runners/{runner_id}/bindings",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"project_id": project_id, "computer_node_id": "pc-bind"},
        )
        assert bind_response.status_code == 200
        assert bind_response.json()["data"]["runner_id"] == runner_id
        assert bind_response.json()["data"]["project_id"] == project_id

        outsider_bind_response = client.post(
            f"/api/runners/{runner_id}/bindings",
            headers={"Authorization": f"Bearer {outsider_token}"},
            json={"project_id": project_id, "computer_node_id": "pc-bind"},
        )
        assert outsider_bind_response.status_code == 403
        assert outsider_bind_response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

        unbind_response = client.delete(
            f"/api/runners/{runner_id}/bindings/{project_id}/pc-bind",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert unbind_response.status_code == 200
        assert unbind_response.json()["data"]["status"] == "unbound"
    finally:
        _cleanup_runner_test_data(project_id, runner_id=runner_id)


def test_runner_detail_and_workspace_reads_are_project_scoped() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    runner_id = None
    try:
        _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)
        outsider_token, outsider_user_id = _register_and_session(
            f"runner-read-outsider-{uuid4().hex[:8]}@example.com",
            "Runner Read Outsider",
        )
        _add_member(project_id, owner_token, outsider_user_id, role="member", is_owner=False)

        register_response = client.post(
            "/api/runners/register",
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Scoped Read Runner",
                "capabilities": ["git"],
                "hardware_access": False,
            },
        )
        assert register_response.status_code == 200
        runner_id = register_response.json()["data"]["id"]

        bind_response = client.post(
            f"/api/runners/{runner_id}/bindings",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"project_id": project_id, "computer_node_id": "pc-bind"},
        )
        assert bind_response.status_code == 200

        owner_detail = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {owner_token}"})
        assert owner_detail.status_code == 200

        owner_workspace = client.get(
            f"/api/runners/{runner_id}/workspace",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_workspace.status_code == 200
        runner_workspace = client.get(
            f"/api/runners/{runner_id}/workspace",
            headers={"X-Runner-Id": runner_id},
        )
        assert runner_workspace.status_code == 200
        assert runner_workspace.json()["data"]["bindings"][0]["project_id"] == project_id
        wrong_runner_workspace = client.get(
            f"/api/runners/{runner_id}/workspace",
            headers={"X-Runner-Id": f"{runner_id}-other"},
        )
        assert wrong_runner_workspace.status_code == 403
        assert wrong_runner_workspace.json()["error"]["code"] == "PERMISSION_DENIED"

        stranger_token, _ = _register_and_session(
            f"runner-stranger-{uuid4().hex[:8]}@example.com",
            "Runner Stranger",
        )
        stranger_detail = client.get(
            f"/api/runners/{runner_id}",
            headers={"Authorization": f"Bearer {stranger_token}"},
        )
        assert stranger_detail.status_code == 403
        assert stranger_detail.json()["error"]["code"] == "PERMISSION_DENIED"

        stranger_workspace = client.get(
            f"/api/runners/{runner_id}/workspace",
            headers={"Authorization": f"Bearer {stranger_token}"},
        )
        assert stranger_workspace.status_code == 403
        assert stranger_workspace.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        _cleanup_runner_test_data(project_id, runner_id=runner_id)


def test_runner_list_and_summary_are_scoped_to_readable_projects() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    outsider_project_id = None
    shared_runner_id = None
    outsider_runner_id = None
    try:
        _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)
        member_token, member_user_id = _register_and_session(
            f"runner-list-member-{uuid4().hex[:8]}@example.com",
            "Runner List Member",
        )
        _add_member(project_id, owner_token, member_user_id, role="member", is_owner=False)

        shared_runner = client.post(
            "/api/runners/register",
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Shared Scoped Runner",
                "capabilities": ["git", "python"],
                "hardware_access": False,
            },
        )
        assert shared_runner.status_code == 200
        shared_runner_id = shared_runner.json()["data"]["id"]

        bind_shared = client.post(
            f"/api/runners/{shared_runner_id}/bindings",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"project_id": project_id, "computer_node_id": "pc-bind"},
        )
        assert bind_shared.status_code == 200

        outsider_owner_token, outsider_owner_user_id = _register_and_session(
            f"runner-list-outsider-{uuid4().hex[:8]}@example.com",
            "Runner List Outsider Owner",
        )
        outsider_project_id = _create_project(outsider_owner_token)
        _add_member(outsider_project_id, outsider_owner_token, outsider_owner_user_id, role="owner", is_owner=True)

        outsider_runner = client.post(
            "/api/runners/register",
            json={
                "runner_id": f"runner-{uuid4().hex[:8]}",
                "runner_name": "Outsider Scoped Runner",
                "capabilities": ["git"],
                "hardware_access": False,
            },
        )
        assert outsider_runner.status_code == 200
        outsider_runner_id = outsider_runner.json()["data"]["id"]

        bind_outsider = client.post(
            f"/api/runners/{outsider_runner_id}/bindings",
            headers={"Authorization": f"Bearer {outsider_owner_token}"},
            json={"project_id": outsider_project_id, "computer_node_id": "pc-bind"},
        )
        assert bind_outsider.status_code == 200

        member_list = client.get("/api/runners", headers={"Authorization": f"Bearer {member_token}"})
        assert member_list.status_code == 200
        member_runner_ids = {str(item["id"]) for item in member_list.json()["data"]}
        assert shared_runner_id in member_runner_ids
        assert outsider_runner_id not in member_runner_ids

        member_summary = client.get("/api/runners/summary", headers={"Authorization": f"Bearer {member_token}"})
        assert member_summary.status_code == 200
        summary_payload = member_summary.json()["data"]
        assert summary_payload["total"] >= 1
        assert summary_payload["bound_projects"] == 1
        assert summary_payload["bound_computer_nodes"] == 1

        outsider_list = client.get("/api/runners", headers={"Authorization": f"Bearer {outsider_owner_token}"})
        assert outsider_list.status_code == 200
        outsider_runner_ids = {str(item["id"]) for item in outsider_list.json()["data"]}
        assert outsider_runner_id in outsider_runner_ids
        assert shared_runner_id not in outsider_runner_ids
    finally:
        _cleanup_runner_test_data(project_id, runner_id=shared_runner_id)
        if outsider_project_id:
            _cleanup_runner_test_data(outsider_project_id, runner_id=outsider_runner_id)


def test_runner_register_cannot_self_grant_hardware_access() -> None:
    runner_id = f"runner-{uuid4().hex[:8]}"

    first_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Hardware Claim Runner",
            "capabilities": ["gpio", "serial"],
            "hardware_access": True,
        },
    )
    assert first_response.status_code == 200
    assert first_response.json()["data"]["allow_hardware_access"] is False

    second_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Hardware Claim Runner 2",
            "capabilities": ["gpio", "serial", "camera"],
            "hardware_access": True,
        },
    )
    assert second_response.status_code == 200
    assert second_response.json()["data"]["allow_hardware_access"] is False

    with SessionLocal() as db:
        runner = db.get(Runner, runner_id)
        assert runner is not None
        runner.allow_hardware_access = True
        db.add(runner)
        db.commit()

    third_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Hardware Claim Runner 3",
            "capabilities": ["gpio"],
            "hardware_access": False,
        },
    )
    assert third_response.status_code == 200
    assert third_response.json()["data"]["allow_hardware_access"] is True

    with SessionLocal() as db:
        db.query(Runner).filter(Runner.id == runner_id).delete(synchronize_session=False)
        db.commit()


def test_runner_register_requires_pairing_token_when_configured(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("RUNNER_REGISTRATION_TOKEN", "pair-me")
    get_settings.cache_clear()

    runner_id = f"runner-{uuid4().hex[:8]}"

    missing_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Tokenless Runner",
            "capabilities": ["git"],
            "hardware_access": False,
        },
    )
    assert missing_response.status_code == 401
    assert missing_response.json()["error"]["code"] == "UNAUTHORIZED"

    wrong_response = client.post(
        "/api/runners/register",
        headers={"X-Runner-Registration-Token": "wrong-token"},
        json={
            "runner_id": runner_id,
            "runner_name": "Wrong Token Runner",
            "capabilities": ["git"],
            "hardware_access": False,
        },
    )
    assert wrong_response.status_code == 403
    assert wrong_response.json()["error"]["code"] == "PERMISSION_DENIED"

    ok_response = client.post(
        "/api/runners/register",
        headers={"X-Runner-Registration-Token": "pair-me"},
        json={
            "runner_id": runner_id,
            "runner_name": "Paired Runner",
            "capabilities": ["git"],
            "hardware_access": False,
        },
    )
    assert ok_response.status_code == 200
    assert ok_response.json()["data"]["id"] == runner_id

    with SessionLocal() as db:
        db.query(Runner).filter(Runner.id == runner_id).delete(synchronize_session=False)
        db.commit()

    monkeypatch.delenv("RUNNER_REGISTRATION_TOKEN", raising=False)
    get_settings.cache_clear()


def test_project_computer_node_pairing_token_can_bind_runner() -> None:
    owner_token, owner_user_id = _session("lead@example.com")
    project_id = _create_project(owner_token)
    runner_id = f"runner-{uuid4().hex[:8]}"
    try:
        _add_member(project_id, owner_token, owner_user_id, role="owner", is_owner=True)

        initial_status = client.get(
            f"/api/collaboration/projects/{project_id}/computer-nodes/pc-bind/pairing-token",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert initial_status.status_code == 200
        assert initial_status.json()["data"]["token"] is None
        assert initial_status.json()["data"]["token_available"] is False

        issue_response = client.post(
            f"/api/collaboration/projects/{project_id}/computer-nodes/pc-bind/pairing-token",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert issue_response.status_code == 200
        issued = issue_response.json()["data"]
        assert issued["computer_node_id"] == "pc-bind"
        assert issued["token"]
        assert issued["token_available"] is True

        hidden_status = client.get(
            f"/api/collaboration/projects/{project_id}/computer-nodes/pc-bind/pairing-token",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert hidden_status.status_code == 200
        assert hidden_status.json()["data"]["token"] is None
        assert hidden_status.json()["data"]["token_available"] is True

        register_response = client.post(
            "/api/runners/register",
            headers={"X-Runner-Registration-Token": issued["token"]},
            json={
                "runner_id": runner_id,
                "runner_name": "Paired Bind Runner",
                "capabilities": ["git", "shell"],
                "hardware_access": False,
                "computer_node_id": "pc-bind",
            },
        )
        assert register_response.status_code == 200
        assert register_response.json()["data"]["computer_node_id"] == "pc-bind"
        assert register_response.json()["data"]["bound_project_count"] == 1

        with SessionLocal() as db:
            node = db.scalar(
                select(ProjectComputerNode).where(
                    ProjectComputerNode.project_id == project_id,
                    ProjectComputerNode.config_id == "pc-bind",
                )
            )
            assert node is not None
            assert node.runner_id == runner_id
            extra_data = node.extra_data or {}
            assert extra_data.get("runner_pairing_token_last_used_at") is not None

        revoke_response = client.delete(
            f"/api/collaboration/projects/{project_id}/computer-nodes/pc-bind/pairing-token",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert revoke_response.status_code == 200
        assert revoke_response.json()["data"]["token_available"] is False

        second_runner_id = f"runner-{uuid4().hex[:8]}"
        failed_reuse = client.post(
            "/api/runners/register",
            headers={"X-Runner-Registration-Token": issued["token"]},
            json={
                "runner_id": second_runner_id,
                "runner_name": "Rejected Reuse Runner",
                "capabilities": ["git"],
                "hardware_access": False,
                "computer_node_id": "pc-bind",
            },
        )
        assert failed_reuse.status_code == 403
        assert failed_reuse.json()["error"]["code"] == "PAIRING_TOKEN_INVALID"

        with SessionLocal() as db:
            db.query(Runner).filter(Runner.id == second_runner_id).delete(synchronize_session=False)
            db.commit()
    finally:
        _cleanup_runner_test_data(project_id, runner_id=runner_id)
