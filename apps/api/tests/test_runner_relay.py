from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models.collaboration_message import CollaborationMessage
from app.db.session import SessionLocal
from app.main import app

from .helpers import auth_headers, issue_session_token, register_user


client = TestClient(app)


def _setup_runner_project() -> tuple[str, str, str, str]:
    owner_token, owner_user_id = issue_session_token(client)
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Relay Runner",
            "capabilities": ["git", "shell", "relay"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers=auth_headers(owner_token),
        json={
            "name": f"Runner Relay {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-relay",
                        "label": "中转电脑",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-relay",
                        "name": "协作工位",
                        "agent_id": "agent-relay",
                        "computer_node_id": "pc-relay",
                        "status": "active",
                    }
                ],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers=auth_headers(owner_token),
        json={
            "user_id": owner_user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    task_response = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Relay task",
            "description": "verify relay command flow",
            "module": "runner-relay",
            "priority": "P1",
            "status": "ready",
            "branch": "feature/relay",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["data"]["id"]
    return owner_token, project_id, runner_id, task_id


def test_runner_relay_command_round_trip() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()

    command_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(owner_token),
        json={
            "computer_node_id": "pc-relay",
            "task_id": task_id,
            "title": "同步代码",
            "body": "请先拉取 develop 分支，然后回传结果。",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]
    assert command["recipient_type"] == "runner"
    assert command["recipient_id"] == runner_id
    assert command["status"] == "pending"

    inbox_response = client.get(f"/api/runners/{runner_id}/inbox", headers={"X-Runner-Id": runner_id})
    assert inbox_response.status_code == 200
    inbox = inbox_response.json()["data"]
    assert len(inbox) >= 1
    assert inbox[0]["id"] == command["id"]

    ack_response = client.post(
        f"/api/runners/{runner_id}/messages/{command['id']}/ack",
        headers={"X-Runner-Id": runner_id},
        json={"note": "已收到，准备开始。"},
    )
    assert ack_response.status_code == 200
    ack_data = ack_response.json()["data"]
    assert ack_data["command"]["status"] == "acked"
    assert ack_data["receipt"]["message_type"] == "runner_ack"
    assert ack_data["receipt"]["sender_type"] == "runner"

    running_task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers(owner_token))
    assert running_task_response.status_code == 200
    assert running_task_response.json()["data"]["status"] == "running"

    complete_response = client.post(
        f"/api/runners/{runner_id}/messages/{command['id']}/complete",
        headers={"X-Runner-Id": runner_id},
        json={"result_status": "completed", "note": "代码已同步完毕。"},
    )
    assert complete_response.status_code == 200
    complete_data = complete_response.json()["data"]
    assert complete_data["command"]["status"] == "completed"
    assert complete_data["receipt"]["message_type"] == "runner_result"
    assert complete_data["receipt"]["status"] == "completed"

    reviewing_task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers(owner_token))
    assert reviewing_task_response.status_code == 200
    assert reviewing_task_response.json()["data"]["status"] == "reviewing"

    messages_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}&message_type=runner_result",
        headers=auth_headers(owner_token),
    )
    assert messages_response.status_code == 200
    result_messages = messages_response.json()["data"]
    assert any(item["recipient_type"] == "human" and item["sender_id"] == runner_id for item in result_messages)


def test_runner_relay_completion_preserves_structured_metadata() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()

    command_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(owner_token),
        json={
            "computer_node_id": "pc-relay",
            "task_id": task_id,
            "title": "采集回执",
            "body": "structured metadata result",
            "metadata": {
                "terminal_interface_id": "serial:COM1",
                "capture_id": "capture-structured",
            },
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    complete_response = client.post(
        f"/api/runners/{runner_id}/messages/{command['id']}/complete",
        headers={"X-Runner-Id": runner_id},
        json={
            "result_status": "completed",
            "note": "采集完成。",
            "metadata": {
                "runner_result": {
                    "capture_id": "capture-structured",
                    "sample_count": 12,
                    "preview": "device-captures/proj/pc/serial/capture/preview.jsonl",
                },
                "artifact_refs": [{"label": "采集预览", "path": "artifacts/robotics-captures/proj/capture.json"}],
            },
        },
    )
    assert complete_response.status_code == 200
    receipt = complete_response.json()["data"]["receipt"]
    assert receipt["message_type"] == "runner_result"
    assert receipt["metadata"]["terminal_interface_id"] == "serial:COM1"
    assert receipt["metadata"]["capture_id"] == "capture-structured"
    assert receipt["metadata"]["runner_result"]["sample_count"] == 12
    assert receipt["metadata"]["artifact_refs"][0]["label"] == "采集预览"


def test_runner_relay_command_accepts_structured_dispatch_id_without_legacy_body_hint() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()

    dispatch_response = client.post(
        f"/api/tasks/{task_id}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "workstation_id": "ws-relay",
            "notes": "queue through structured dispatch metadata",
        },
    )
    assert dispatch_response.status_code == 200
    dispatch = dispatch_response.json()["data"]

    command_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(owner_token),
        json={
            "dispatch_id": dispatch["id"],
            "title": "Structured follow-up",
            "body": "Continue the assigned task and report back.",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]
    assert command["recipient_type"] == "runner"
    assert command["recipient_id"] == runner_id
    assert command["task_id"] == task_id
    assert command["dispatch_id"] == dispatch["id"]
    assert f"Dispatch ID: {dispatch['id']}" in command["body"]

    with SessionLocal() as db:
        message = db.get(CollaborationMessage, command["id"])
        assert message is not None
        message.body = "Continue the assigned task and report back."
        db.add(message)
        db.commit()

    ack_response = client.post(
        f"/api/runners/{runner_id}/messages/{command['id']}/ack",
        headers={"X-Runner-Id": runner_id},
        json={"note": "runner picked up the structured command"},
    )
    assert ack_response.status_code == 200
    assert ack_response.json()["data"]["command"]["status"] == "acked"
    assert ack_response.json()["data"]["command"]["dispatch_id"] == dispatch["id"]
    assert ack_response.json()["data"]["receipt"]["dispatch_id"] == dispatch["id"]

    running_task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers(owner_token))
    assert running_task_response.status_code == 200
    running_task = running_task_response.json()["data"]
    assert running_task["status"] == "running"
    assert running_task["latest_dispatch"]["id"] == dispatch["id"]
    assert running_task["latest_dispatch"]["status"] == "acked"

    complete_response = client.post(
        f"/api/runners/{runner_id}/messages/{command['id']}/complete",
        headers={"X-Runner-Id": runner_id},
        json={"result_status": "completed", "note": "structured dispatch finished cleanly"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["command"]["status"] == "completed"
    assert complete_response.json()["data"]["command"]["dispatch_id"] == dispatch["id"]
    assert complete_response.json()["data"]["receipt"]["dispatch_id"] == dispatch["id"]

    reviewing_task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers(owner_token))
    assert reviewing_task_response.status_code == 200
    reviewing_task = reviewing_task_response.json()["data"]
    assert reviewing_task["status"] == "reviewing"
    assert reviewing_task["latest_dispatch"]["id"] == dispatch["id"]
    assert reviewing_task["latest_dispatch"]["status"] == "completed"


def test_runner_relay_command_rejects_dispatch_from_another_project() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()
    other_owner_token, other_project_id, _, _ = _setup_runner_project()

    dispatch_response = client.post(
        f"/api/tasks/{task_id}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-relay"},
    )
    assert dispatch_response.status_code == 200
    dispatch = dispatch_response.json()["data"]

    command_response = client.post(
        f"/api/collaboration/projects/{other_project_id}/runner-commands",
        headers=auth_headers(other_owner_token),
        json={
            "dispatch_id": dispatch["id"],
            "body": "This command should stay inside its own project.",
        },
    )
    assert command_response.status_code == 404
    assert command_response.json()["error"]["code"] == "TASK_DISPATCH_NOT_FOUND"


def test_runner_relay_respects_project_and_runner_scope() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()
    outsider_user_id, outsider_email = register_user(client, f"relay-outsider-{uuid4().hex[:8]}@example.com", "Relay Outsider")
    outsider_token, _ = issue_session_token(client, outsider_email)

    outsider_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(outsider_token),
        json={
            "workstation_id": "ws-relay",
            "task_id": task_id,
            "body": "outsider should not queue this",
        },
    )
    assert outsider_response.status_code == 403

    command_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(owner_token),
        json={
            "workstation_id": "ws-relay",
            "task_id": task_id,
            "body": "合法命令",
        },
    )
    assert command_response.status_code == 200
    message_id = command_response.json()["data"]["id"]

    other_runner_id = f"runner-{uuid4().hex[:8]}"
    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": other_runner_id,
            "runner_name": "Wrong Runner",
            "capabilities": ["relay"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    wrong_runner_response = client.post(
        f"/api/runners/{other_runner_id}/messages/{message_id}/ack",
        headers={"X-Runner-Id": other_runner_id},
        json={"note": "not my message"},
    )
    assert wrong_runner_response.status_code == 404
    assert wrong_runner_response.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_project_member_can_queue_readonly_robotics_scan_but_not_generic_runner_command() -> None:
    owner_token, project_id, runner_id, _ = _setup_runner_project()
    member_user_id, member_email = register_user(client, f"relay-member-{uuid4().hex[:8]}@example.com", "Relay Member")
    member_token, _ = issue_session_token(client, member_email)
    add_member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers=auth_headers(owner_token),
        json={
            "user_id": member_user_id,
            "role": "member",
            "status": "active",
            "is_owner": False,
        },
    )
    assert add_member_response.status_code == 200

    scan_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(member_token),
        json={
            "computer_node_id": "pc-relay",
            "title": "扫描真实接口",
            "body": '{"kind":"serial.usb.scan","scan":["serial_ports","usb_devices"]}',
        },
    )
    assert scan_response.status_code == 200
    assert scan_response.json()["data"]["recipient_id"] == runner_id

    generic_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(member_token),
        json={
            "computer_node_id": "pc-relay",
            "title": "通用命令",
            "body": "run a privileged generic command",
        },
    )
    assert generic_response.status_code == 403
    assert generic_response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"


def test_collaboration_message_read_and_runner_type_require_protected_paths() -> None:
    owner_token, project_id, runner_id, task_id = _setup_runner_project()

    command_response = client.post(
        f"/api/collaboration/projects/{project_id}/runner-commands",
        headers=auth_headers(owner_token),
        json={
            "runner_id": runner_id,
            "task_id": task_id,
            "body": "受保护命令",
        },
    )
    assert command_response.status_code == 200

    anonymous_messages = client.get(
        f"/api/collaboration/messages?project_id={project_id}&message_type=runner_command"
    )
    assert anonymous_messages.status_code == 401
    assert anonymous_messages.json()["error"]["code"] == "UNAUTHORIZED"

    forged_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task_id,
            "message_type": "runner_command",
            "recipient_type": "runner",
            "recipient_id": runner_id,
            "body": "不应该允许伪造 runner 命令",
        },
    )
    assert forged_response.status_code == 422 or forged_response.status_code == 403


def test_robotics_npc_terminal_review_approval_queues_runner_command() -> None:
    owner_token, project_id, runner_id, _ = _setup_runner_project()

    review_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": "ws-relay",
            "message_type": "robotics_terminal_npc_request",
            "title": "NPC 代操作待审：CAN can0",
            "body": "NPC 请求代用户发送一帧测试命令。",
            "sender_type": "agent",
            "sender_id": "ws-relay",
            "recipient_type": "human",
            "recipient_id": "project-owner",
            "status": "pending_review",
            "metadata": {
                "terminal_interface_id": "pc-relay:can:can0",
                "terminal_interface_name": "CAN · can0",
                "terminal_interface_kind": "CAN",
                "terminal_bound_npc_id": "ws-relay",
                "terminal_bound_npc": "协作工位",
                "terminal_command": "send 123#0102",
                "terminal_mode": "npc_terminal_request",
                "terminal_surface": "robotics",
                "computer_node_id": "pc-relay",
                "review_required_reason": "npc_operates_terminal",
            },
        },
    )
    assert review_response.status_code == 200
    review_message = review_response.json()["data"]
    assert review_message["status"] == "pending_review"

    approve_response = client.post(
        f"/api/collaboration/messages/{review_message['id']}/review/approve",
        headers=auth_headers(owner_token),
        json={},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["data"]["status"] == "queued"

    inbox_response = client.get(f"/api/runners/{runner_id}/inbox", headers={"X-Runner-Id": runner_id})
    assert inbox_response.status_code == 200
    inbox = inbox_response.json()["data"]
    command = next(
        item
        for item in inbox
        if item["message_type"] == "runner_command"
        and item["metadata"]["review_message_id"] == review_message["id"]
    )
    assert command["recipient_id"] == runner_id
    assert command["status"] == "pending"
    assert "审核通过的 NPC 终端操作" in command["title"]
    assert "send 123#0102" in command["body"]
    assert command["metadata"]["terminal_mode"] == "npc_terminal_approved"
