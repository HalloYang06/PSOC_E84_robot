from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models.collaboration_message import CollaborationMessage
from app.db.session import SessionLocal
from app.main import app
from tests.helpers import auth_headers, create_project, create_task, issue_session_token


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

    message_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}&task_id={task['id']}&message_type=runner_command",
        headers=auth_headers(owner_token),
    )
    assert message_response.status_code == 200
    runner_messages = message_response.json()["data"]
    assert any(item["id"] == command["id"] for item in runner_messages)

    ack_response = client.post(
        f"/api/runners/runner-alpha/messages/{command['id']}/ack",
        headers={"X-Runner-Id": "runner-alpha"},
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
        f"/api/runners/runner-alpha/messages/{command['id']}/complete",
        headers={"X-Runner-Id": "runner-alpha"},
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
