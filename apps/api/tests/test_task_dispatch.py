from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.runner import Runner
from app.db.models.task_dispatch import TaskDispatch
from app.db.session import SessionLocal
from app.main import app
from tests.helpers import auth_headers, create_project, create_requirement, create_task, issue_session_token


client = TestClient(app)


def test_task_dispatch_assigns_workstation_and_updates_task_snapshot() -> None:
    owner_token, _ = issue_session_token(client)
    runner_register = client.post(
        "/api/runners/register",
        json={
            "runner_id": "runner-alpha",
            "runner_name": "Dispatch Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert runner_register.status_code == 200
    project = create_project(client, owner_token, name_prefix="Dispatch Project")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-1",
                        "label": "电脑1",
                        "status": "online",
                        "runner_id": "runner-alpha",
                    }
                ],
                "ai_providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "enabled": True,
                        "model": "gpt-5.1-codex",
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-frontend",
                        "name": "前端工位",
                        "agent_id": "agent-ui",
                        "computer_node_id": "pc-1",
                        "ai_provider_id": "codex",
                        "metadata": {"automation_thread_id": "codex-session-ws-frontend"},
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Dispatch target",
        status="ready",
        assignee_agent_id=None,
    )

    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "workstation_id": "ws-frontend",
            "notes": "dispatch to the frontend lane",
        },
    )
    assert dispatch_response.status_code == 200
    dispatch = dispatch_response.json()["data"]

    assert dispatch["workstation_id"] == "ws-frontend"
    assert dispatch["workstation_name"] == "前端工位"
    assert dispatch["agent_id"] == "agent-ui"
    assert dispatch["computer_node_id"] == "pc-1"
    assert dispatch["ai_provider_id"] == "codex"
    assert dispatch["runner_id"] == "runner-alpha"
    assert dispatch["status"] == "dispatched"

    task_response = client.get(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(owner_token),
    )
    assert task_response.status_code == 200
    task_payload = task_response.json()["data"]
    assert task_payload["assignee_agent_id"] == "agent-ui"
    assert task_payload["latest_dispatch"]["id"] == dispatch["id"]
    assert task_payload["latest_dispatch"]["workstation_id"] == "ws-frontend"

    list_response = client.get(
        f"/api/tasks/{task['id']}/dispatches",
        headers=auth_headers(owner_token),
    )
    assert list_response.status_code == 200
    items = list_response.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == dispatch["id"]

    inbox_response = client.get("/api/runners/runner-alpha/inbox", headers={"X-Runner-Id": "runner-alpha"})
    assert inbox_response.status_code == 200
    inbox = inbox_response.json()["data"]
    assert len(inbox) >= 1
    command = inbox[0]
    assert command["message_type"] == "runner_command"
    assert command["task_id"] == task["id"]
    assert command["dispatch_id"] == dispatch["id"]
    assert command["recipient_id"] == "runner-alpha"
    assert "Dispatch target" in command["body"]

    # The dispatch/result loop should keep working even if the legacy body hint disappears.
    with SessionLocal() as db:
        message = db.get(CollaborationMessage, command["id"])
        assert message is not None
        message.body = "Task: Dispatch target\nWorkstation: ws-frontend\nDispatch status: dispatched"
        db.add(message)
        db.commit()


def test_runner_next_task_only_claims_dispatch_bound_to_that_runner() -> None:
    owner_token, _ = issue_session_token(client)
    runner_a = f"runner-a-{uuid4().hex[:8]}"
    runner_b = f"runner-b-{uuid4().hex[:8]}"
    for runner_id in (runner_a, runner_b):
        response = client.post(
            "/api/runners/register",
            json={
                "runner_id": runner_id,
                "runner_name": runner_id,
                "capabilities": ["relay", "shell"],
                "hardware_access": False,
            },
        )
        assert response.status_code == 200

    project = create_project(client, owner_token, name_prefix="Runner Isolation")
    project_id = project["id"]
    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {"id": "pc-a", "label": "电脑 A", "status": "online", "runner_id": runner_a},
                    {"id": "pc-b", "label": "电脑 B", "status": "online", "runner_id": runner_b},
                ],
                "thread_workstations": [
                    {
                            "id": "ws-a",
                            "name": "A 工位",
                            "agent_id": "agent-a",
                            "computer_node_id": "pc-a",
                            "metadata": {"automation_thread_id": "codex-session-ws-a"},
                            "status": "idle",
                        },
                    {
                            "id": "ws-b",
                            "name": "B 工位",
                            "agent_id": "agent-b",
                            "computer_node_id": "pc-b",
                            "metadata": {"automation_thread_id": "codex-session-ws-b"},
                            "status": "idle",
                        },
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Only runner A may claim this",
        status="ready",
        assignee_agent_id=None,
    )
    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-a", "notes": "bound to runner A"},
    )
    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["data"]["runner_id"] == runner_a

    runner_b_response = client.get(f"/api/runners/{runner_b}/next-task", headers={"X-Runner-Id": runner_b})
    assert runner_b_response.status_code == 200
    runner_b_payload = runner_b_response.json()["data"]
    assert runner_b_payload["task"] is None
    assert runner_b_payload["claimed"] is False

    task_after_b = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token)).json()["data"]
    assert task_after_b["status"] == "queued"
    assert task_after_b["latest_dispatch"]["status"] == "dispatched"

    runner_a_response = client.get(f"/api/runners/{runner_a}/next-task", headers={"X-Runner-Id": runner_a})
    assert runner_a_response.status_code == 200
    runner_a_payload = runner_a_response.json()["data"]
    assert runner_a_payload["task"]["id"] == task["id"]
    assert runner_a_payload["claimed"] is True

    task_after_a = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token)).json()["data"]
    assert task_after_a["status"] == "running"
    assert task_after_a["latest_dispatch"]["status"] == "running"

    message_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}&task_id={task['id']}&message_type=runner_command",
        headers=auth_headers(owner_token),
    )
    assert message_response.status_code == 200
    runner_messages = message_response.json()["data"]
    assert len(runner_messages) == 1
    command = runner_messages[0]
    assert command["recipient_id"] == runner_a

    ack_response = client.post(
        f"/api/runners/{runner_a}/messages/{command['id']}/ack",
        headers={"X-Runner-Id": runner_a},
        json={"note": "runner picked up the task"},
    )
    assert ack_response.status_code == 200
    ack_payload = ack_response.json()["data"]
    assert ack_payload["command"]["status"] == "acked"

    acked_task_response = client.get(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(owner_token),
    )
    assert acked_task_response.status_code == 200
    acked_task = acked_task_response.json()["data"]
    assert acked_task["status"] == "running"
    assert acked_task["latest_dispatch"]["status"] == "acked"

    complete_response = client.post(
        f"/api/runners/{runner_a}/messages/{command['id']}/complete",
        headers={"X-Runner-Id": runner_a},
        json={"result_status": "completed", "note": "task finished"},
    )
    assert complete_response.status_code == 200
    complete_payload = complete_response.json()["data"]
    assert complete_payload["command"]["status"] == "completed"

    completed_task_response = client.get(
        f"/api/tasks/{task['id']}",
        headers=auth_headers(owner_token),
    )
    assert completed_task_response.status_code == 200
    completed_task = completed_task_response.json()["data"]
    assert completed_task["status"] == "reviewing"
    assert completed_task["latest_dispatch"]["status"] == "completed"


def test_task_dispatch_requires_existing_workstation() -> None:
    owner_token, _ = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Dispatch Missing Workstation")
    task = create_task(client, owner_token, project["id"], title="Missing workstation target", status="ready")

    response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-missing"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSTATION_NOT_FOUND"


def test_task_dispatch_rejects_unbound_runner_before_queueing() -> None:
    owner_token, _ = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Dispatch Needs Runner")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-unbound",
                        "label": "未接入电脑",
                        "status": "online",
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-unbound",
                        "name": "未接入工位",
                        "agent_id": "agent-unbound",
                        "computer_node_id": "pc-unbound",
                        "metadata": {"automation_thread_id": "codex-session-ws-unbound"},
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(client, owner_token, project_id, title="Should stay ready", status="ready")
    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-unbound"},
    )
    assert dispatch_response.status_code == 409
    payload = dispatch_response.json()["error"]
    assert payload["code"] == "TASK_DISPATCH_RUNNER_UNBOUND"
    assert "还没有完成执行程序接入" in payload["message"]
    assert payload["details"]["blocked_reason"] == "离线，需重连"
    assert payload["details"]["blocked_reason_code"] == "runner_unbound"

    task_after = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token))
    assert task_after.status_code == 200
    assert task_after.json()["data"]["status"] == "ready"
    assert task_after.json()["data"]["latest_dispatch"] is None

    with SessionLocal() as db:
        assert db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == task["id"])) is None


def test_task_dispatch_rejects_unbound_thread_before_queueing() -> None:
    owner_token, _ = issue_session_token(client)
    runner_id = f"runner-threadless-{uuid4().hex[:8]}"
    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Threadless Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project = create_project(client, owner_token, name_prefix="Dispatch Needs Thread")
    project_id = project["id"]
    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-threadless",
                        "label": "已接入电脑",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-threadless",
                        "name": "未绑线程工位",
                        "agent_id": "agent-threadless",
                        "computer_node_id": "pc-threadless",
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(client, owner_token, project_id, title="Should wait for thread binding", status="ready")
    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-threadless"},
    )
    assert dispatch_response.status_code == 409
    payload = dispatch_response.json()["error"]
    assert payload["code"] == "TASK_DISPATCH_THREAD_UNBOUND"
    assert "还没有绑定线程" in payload["message"]
    assert payload["details"]["blocked_reason"] == "待绑定线程"
    assert payload["details"]["blocked_reason_code"] == "thread_unbound"

    task_after = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token))
    assert task_after.status_code == 200
    assert task_after.json()["data"]["status"] == "ready"
    assert task_after.json()["data"]["latest_dispatch"] is None

    with SessionLocal() as db:
        assert db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == task["id"])) is None


def test_task_dispatch_queues_stale_runner_until_recovery() -> None:
    owner_token, _ = issue_session_token(client)
    runner_id = f"runner-stale-{uuid4().hex[:8]}"
    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Stale Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    with SessionLocal() as db:
        runner = db.get(Runner, runner_id)
        assert runner is not None
        runner.status = "online"
        runner.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.add(runner)
        db.commit()

    project = create_project(client, owner_token, name_prefix="Dispatch Stale Runner")
    project_id = project["id"]
    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-stale",
                        "label": "心跳过期电脑",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-stale",
                        "name": "心跳过期工位",
                        "agent_id": "agent-stale",
                        "computer_node_id": "pc-stale",
                        "metadata": {"automation_thread_id": "codex-session-ws-stale"},
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(client, owner_token, project_id, title="Should wait for runner recovery", status="ready")
    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-stale"},
    )
    assert dispatch_response.status_code == 200
    payload = dispatch_response.json()["data"]
    assert payload["runner_id"] == runner_id
    assert payload["status"] == "queued"
    assert "等待电脑恢复" in str(payload["notes"] or "")
    assert "重新运行持续接单命令" in str(payload["notes"] or "")

    task_after = client.get(f"/api/tasks/{task['id']}", headers=auth_headers(owner_token))
    assert task_after.status_code == 200
    assert task_after.json()["data"]["status"] == "queued"
    assert task_after.json()["data"]["latest_dispatch"]["status"] == "queued"

    inbox_response = client.get(f"/api/runners/{runner_id}/inbox", headers={"X-Runner-Id": runner_id})
    assert inbox_response.status_code == 200
    inbox_items = inbox_response.json()["data"]
    assert len(inbox_items) == 1
    assert inbox_items[0]["dispatch_id"] == payload["id"]
    assert inbox_items[0]["status"] == "pending"


def test_done_need_and_task_can_be_archived_without_deleting_evidence() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Queue Archive")
    project_id = project["id"]
    task = create_task(client, owner_token, project_id, title="Finished queue task", status="running")

    done_response = client.post(
        f"/api/tasks/{task['id']}/transition",
        headers=auth_headers(owner_token),
        json={"status": "done", "actor_type": "human", "actor_id": owner_user_id, "message": "done with GitHub evidence"},
    )
    assert done_response.status_code == 200, done_response.text
    assert done_response.json()["data"]["status"] == "done"

    archive_task_response = client.post(
        f"/api/tasks/{task['id']}/archive",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "message": "clear current queue only"},
    )
    assert archive_task_response.status_code == 200, archive_task_response.text
    assert archive_task_response.json()["data"]["status"] == "archived"

    open_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Open need should stay visible",
        status="waiting_response",
    )
    blocked_archive_response = client.post(
        f"/api/requirements/{open_requirement['id']}/archive",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id},
    )
    assert blocked_archive_response.status_code == 409
    assert blocked_archive_response.json()["error"]["code"] == "REQUIREMENT_NOT_DONE"

    close_response = client.post(
        f"/api/requirements/{open_requirement['id']}/close",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "note": "satisfied"},
    )
    assert close_response.status_code == 200, close_response.text
    assert close_response.json()["data"]["status"] == "closed"

    archive_requirement_response = client.post(
        f"/api/requirements/{open_requirement['id']}/archive",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "note": "clear current queue only"},
    )
    assert archive_requirement_response.status_code == 200, archive_requirement_response.text
    assert archive_requirement_response.json()["data"]["status"] == "archived"
