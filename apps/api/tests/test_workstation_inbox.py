from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.audit_log import AuditLog
from app.db.models.project_collaboration import ProjectThreadWorkstation, ProjectWorkstation
from app.db.models.runner import Runner
from app.db.session import SessionLocal
from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def _load_platform_workstation_adapter():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "platform-workstation-adapter.py"
    spec = importlib.util.spec_from_file_location("platform_workstation_adapter", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_with_workstation(prefix: str = "Workstation Inbox") -> tuple[str, str, str]:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    computer_node_id = f"pc-{uuid4().hex[:8]}"
    runner_id = f"runner-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix=prefix,
        collaboration_config={
            "computer_nodes": [
                {
                    "id": computer_node_id,
                    "label": "测试执行电脑",
                    "status": "online",
                    "runner_id": runner_id,
                }
            ],
            "ai_providers": [
                {
                    "id": "claude",
                    "label": "Claude",
                    "enabled": True,
                    "model": "claude-test",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Claude Writer",
                    "status": "active",
                    "computer_node_id": computer_node_id,
                    "ai_provider_id": "claude",
                    "responsibility": "write final text after another AI gathers material",
                    "metadata": {
                        "source_kind": "manual_user_entry",
                        "automation_thread_id": f"claude-session-{workstation_id}",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    with SessionLocal() as db:
        db.merge(
            Runner(
                id=runner_id,
                name="Workstation Inbox Test Runner",
                host="test-host",
                os="test",
                capabilities=["relay"],
                status="online",
                last_heartbeat_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    return owner_token, project_id, workstation_id


def _project_with_workstation_alias(prefix: str = "Workstation Alias") -> tuple[str, str, str, str]:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    agent_alias = f"platform-npc-{uuid4().hex[:6]}"
    project = create_project(
        client,
        owner_token,
        name_prefix=prefix,
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "5号 Runner 与桌面桥",
                    "agent_id": agent_alias,
                    "status": "active",
                    "ai_provider_id": "codex",
                    "responsibility": "sync Desktop thread follow-ups quickly",
                    "metadata": {
                        "source_kind": "manual_user_entry",
                        "source_thread_id": "codex-session-alias",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    return owner_token, project_id, workstation_id, agent_alias


def test_workstation_inbox_ack_and_complete_generic_agent_command() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation()

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Collaborative writing draft",
            "body": "Write the first draft after the researcher sends notes.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert inbox_response.status_code == 200
    inbox = inbox_response.json()["data"]
    assert [item["id"] for item in inbox] == [command["id"]]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Claude Writer has accepted the draft task."},
    )
    assert ack_response.status_code == 200
    ack = ack_response.json()["data"]
    assert ack["command"]["status"] == "acked"
    assert ack["receipt"]["message_type"] == "agent_ack"
    assert ack["receipt"]["sender_id"] == workstation_id

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Draft completed and ready for review."},
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["command"]["status"] == "completed"
    assert completed["receipt"]["message_type"] == "agent_result"
    assert completed["receipt"]["status"] == "completed"
    with SessionLocal() as db:
        ack_message = db.get(CollaborationMessage, ack["receipt"]["id"])
        assert ack_message is not None
        assert ack_message.status == "delivered"

    closed_inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert closed_inbox_response.status_code == 200
    assert all(item["id"] != command["id"] for item in closed_inbox_response.json()["data"])


def test_workstation_complete_closes_in_progress_launch_ack() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Launch Ack Closure")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Run desktop turn",
            "body": "Verify one-shot desktop dispatch.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    launch_ack_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": workstation_id,
            "message_type": "agent_ack",
            "title": "单次线程处理已启动 / Claude Writer",
            "body": "Desktop turn started.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "in_progress",
            "metadata": {"source_message_id": command["id"]},
        },
    )
    assert launch_ack_response.status_code == 200
    launch_ack = launch_ack_response.json()["data"]

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Validated."},
    )
    assert complete_response.status_code == 200
    with SessionLocal() as db:
        ack_message = db.get(CollaborationMessage, launch_ack["id"])
        assert ack_message is not None
        assert ack_message.status == "completed"


def test_workstation_final_receipt_closes_dispatch_immediately() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Immediate Dispatch Closure")

    task_response = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Close dispatch from final receipt",
            "description": "Dispatch should close as soon as the target NPC returns a final receipt.",
            "status": "ready",
        },
    )
    assert task_response.status_code == 200, task_response.text
    task_id = task_response.json()["data"]["id"]

    dispatch_response = client.post(
        f"/api/tasks/{task_id}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": workstation_id, "notes": "return deterministic final receipt"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch_id = dispatch_response.json()["data"]["id"]

    receipt_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task_id,
            "message_type": "agent_result",
            "title": "后端已完成",
            "body": "Final receipt arrived.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "agent",
            "recipient_id": "boss-seat",
            "status": "completed",
            "dispatch_id": dispatch_id,
            "metadata": {"dispatch_id": dispatch_id},
        },
    )
    assert receipt_response.status_code == 200, receipt_response.text

    dispatch_read = client.get(f"/api/tasks/{task_id}", headers=auth_headers(owner_token))
    assert dispatch_read.status_code == 200, dispatch_read.text
    assert dispatch_read.json()["data"]["latest_dispatch"]["id"] == dispatch_id
    assert dispatch_read.json()["data"]["latest_dispatch"]["status"] == "completed"


def test_message_list_marks_stale_acked_workstation_command_as_desktop_closeout_waiting() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Stale Ack Timeout")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Long running platform task",
            "body": "This task was accepted but never returned a final reply.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Accepted and started."},
    )
    assert ack_response.status_code == 200

    stale_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    with SessionLocal() as db:
        row = db.get(CollaborationMessage, command["id"])
        assert row is not None
        row.updated_at = stale_at
        db.add(row)
        db.commit()

    list_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "limit": 20},
    )
    assert list_response.status_code == 200
    messages = list_response.json()["data"]
    repaired = next(item for item in messages if item["id"] == command["id"])
    assert repaired["status"] == "in_progress"
    retry_receipt = next(
        item
        for item in messages
        if item["message_type"] == "agent_progress"
        and item["metadata"].get("source_message_id") == command["id"]
    )
    assert retry_receipt["status"] == "in_progress"
    assert retry_receipt["metadata"]["desktop_sync_retry_requested"] is True
    assert retry_receipt["metadata"]["desktop_sync_retry_count"] == 1
    assert retry_receipt["metadata"]["blocked_taxonomy"]["desktop_sync_retry_requested"] is True
    assert retry_receipt["metadata"]["blocked_taxonomy"]["desktop_sync_retry_count"] == 1
    assert retry_receipt["metadata"]["blocked_taxonomy"]["blocked_reason_code"] == "desktop_sync_retry"
    assert "自动重试" in retry_receipt["body"]

    stale_again_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    with SessionLocal() as db:
        row = db.get(CollaborationMessage, command["id"])
        assert row is not None
        row.updated_at = stale_again_at
        db.add(row)
        db.commit()

    second_list_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "limit": 30},
    )
    assert second_list_response.status_code == 200
    second_messages = second_list_response.json()["data"]
    timeout_receipt = next(
        item
        for item in second_messages
        if item["message_type"] == "agent_result"
        and item["metadata"].get("source_message_id") == command["id"]
    )
    assert timeout_receipt["status"] == "blocked"
    assert timeout_receipt["metadata"]["timeout_repair"] is True
    assert timeout_receipt["metadata"]["desktop_closeout_waiting"] is True
    assert timeout_receipt["metadata"]["needs_manual_closeout"] is True
    assert timeout_receipt["metadata"]["desktop_sync_retry_count"] == 2
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["failed"] is False
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["auto_closed"] is False
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["platform_defect"] is True
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["nudge_required"] is True
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["wait_extension_available"] is True
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["manual_close_required"] is True
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["desktop_closeout_waiting"] is True
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["desktop_sync_retry_count"] == 2
    assert timeout_receipt["metadata"]["blocked_taxonomy"]["blocked_reason_code"] == "desktop_final_sync_lag"
    assert "自动重试 2 次" in timeout_receipt["body"]


def test_desktop_closeout_actions_create_audited_receipts() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Desktop Closeout Action")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Needs desktop closeout",
            "body": "Desktop final did not sync yet.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Accepted."},
    )
    assert ack_response.status_code == 200

    nudge_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/closeout-action",
        headers=auth_headers(owner_token),
        json={"action": "nudge", "note": "请尽快同步 final。"},
    )
    assert nudge_response.status_code == 200, nudge_response.text
    nudge = nudge_response.json()["data"]
    assert nudge["command"]["status"] == "in_progress"
    assert nudge["receipt"]["message_type"] == "agent_progress"
    assert nudge["receipt"]["status"] == "in_progress"
    assert nudge["receipt"]["metadata"]["desktop_closeout_action"] == "nudge"
    assert nudge["receipt"]["metadata"]["desktop_closeout_waiting"] is True
    assert nudge["receipt"]["metadata"]["blocked_taxonomy"]["desktop_closeout_waiting"] is True

    extend_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/closeout-action",
        headers=auth_headers(owner_token),
        json={"action": "extend_wait"},
    )
    assert extend_response.status_code == 200, extend_response.text
    extend_receipt = extend_response.json()["data"]["receipt"]
    assert extend_receipt["metadata"]["desktop_closeout_action"] == "extend_wait"
    assert extend_receipt["metadata"]["blocked_taxonomy"]["wait_extension_available"] is True

    retry_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/closeout-action",
        headers=auth_headers(owner_token),
        json={"action": "retry_desktop_sync"},
    )
    assert retry_response.status_code == 200, retry_response.text
    retry = retry_response.json()["data"]
    assert retry["command"]["status"] == "in_progress"
    assert retry["receipt"]["message_type"] == "agent_progress"
    assert retry["receipt"]["metadata"]["desktop_closeout_action"] == "retry_desktop_sync"
    assert retry["receipt"]["metadata"]["blocked_taxonomy"]["desktop_sync_retry_requested"] is True
    assert retry["receipt"]["metadata"]["authoritative_seat_id"] == workstation_id
    assert retry["receipt"]["metadata"]["authoritative_seat_ref"] == workstation_id

    manual_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/closeout-action",
        headers=auth_headers(owner_token),
        json={"action": "manual_close", "note": "桌面结果已确认，人工收口。"},
    )
    assert manual_response.status_code == 200, manual_response.text
    manual = manual_response.json()["data"]
    assert manual["command"]["status"] == "completed"
    assert manual["receipt"]["message_type"] == "agent_result"
    assert manual["receipt"]["status"] == "completed"
    assert manual["receipt"]["metadata"]["desktop_closeout_action"] == "manual_close"
    assert manual["receipt"]["metadata"]["desktop_closeout_waiting"] is False
    assert manual["receipt"]["metadata"]["blocked_taxonomy"]["manual_close_required"] is False
    assert manual["receipt"]["metadata"]["blocked_taxonomy"]["evidence_complete"] is True


def test_queued_workstation_command_requests_auto_start_and_retry() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Auto Start Request")

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Please continue autonomously",
            "body": "Continue the platform implementation and report back.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    metadata = message["metadata"]

    assert message["status"] == "queued"
    assert metadata["auto_start_requested"] is True
    assert metadata["auto_start_target_workstation_id"] == workstation_id
    assert metadata["desktop_delivery_priority"] == "background_until_picked_up"
    assert metadata["desktop_delivery_auto_retry"] is True
    assert metadata["desktop_delivery_recoverable_on_focus_loss"] is True
    assert metadata["desktop_sync_retry_available"] is True


def test_queued_workstation_command_attempts_platform_autostart_when_automation_enabled() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Auto Start Launch",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Autostart Seat",
                    "status": "active",
                    "ai_provider_id": "claude",
                    "metadata": {
                        "automation_enabled": True,
                        "automation_mode": "thread_watcher",
                        "automation_thread_id": "claude-session-test",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 43210,
            "stdout_path": "artifacts/workstation-inbox/autostart.out.log",
            "stderr_path": "artifacts/workstation-inbox/autostart.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "Wake the target seat",
                "body": "Please continue automatically.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    metadata = message["metadata"]
    assert metadata["auto_start_requested"] is True
    assert metadata["auto_start_launch_status"] == "launched"
    assert metadata["auto_start_launch_pid"] == 43210
    assert metadata["auto_start_delivery_mode"] == "claude_bridge"
    assert metadata["auto_start_stdout_path"] == "artifacts/workstation-inbox/autostart.out.log"
    assert metadata["auto_start_stderr_path"] == "artifacts/workstation-inbox/autostart.err.log"


def test_visible_desktop_workstation_waits_for_bound_runner_by_default() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Desktop Visible Autostart",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Visible Desktop Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_enabled": False,
                        "desktop_visible": True,
                        "desktop_delivery_mode": "codex_desktop_ui",
                        "source_thread_id": "codex-session-visible",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 33333,
            "stdout_path": "visible.out.log",
            "stderr_path": "visible.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "Single dispatch should still wake desktop",
                "body": "Please handle this visible desktop dispatch.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    metadata = response.json()["data"]["metadata"]
    assert metadata["auto_start_requested"] is True
    assert metadata["auto_start_launch_status"] == "waiting_for_bound_runner"
    assert "auto_start_launch_pid" not in metadata
    assert launch_mock.call_count == 0


def test_server_desktop_autostart_can_be_enabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("AI_COLLAB_ENABLE_SERVER_DESKTOP_AUTOSTART", "1")
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Desktop Server Autostart",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Visible Desktop Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_enabled": False,
                        "desktop_visible": True,
                        "desktop_delivery_mode": "codex_desktop_ui",
                        "source_thread_id": "codex-session-visible",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 33333,
            "stdout_path": "visible.out.log",
            "stderr_path": "visible.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "Single dispatch may wake local desktop",
                "body": "Please handle this visible desktop dispatch.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    metadata = response.json()["data"]["metadata"]
    assert metadata["auto_start_launch_status"] == "launched"
    assert metadata["auto_start_launch_pid"] == 33333
    assert launch_mock.call_count == 1


def test_codex_app_server_waits_for_bound_runner_by_default() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"app-server-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Codex App Server Runner",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "App Server Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_enabled": True,
                        "automation_thread_id": "codex-session-app-server",
                        "desktop_delivery_mode": "codex_app_server",
                        "computer_node_id": "wjy-windows",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 33334,
            "stdout_path": "app-server.out.log",
            "stderr_path": "app-server.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "App-server dispatch should wait for bound runner",
                "body": "Please reply from the bound computer.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    metadata = response.json()["data"]["metadata"]
    assert metadata["auto_start_requested"] is True
    assert metadata["auto_start_delivery_mode"] == "codex_app_server"
    assert metadata["auto_start_launch_status"] == "waiting_for_bound_runner"
    assert "auto_start_launch_pid" not in metadata
    assert launch_mock.call_count == 0


def test_codex_app_server_server_autostart_can_be_enabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("AI_COLLAB_ENABLE_SERVER_CODEX_APP_SERVER_AUTOSTART", "1")
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"app-server-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Codex App Server API Autostart",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "App Server Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_enabled": True,
                        "automation_thread_id": "codex-session-app-server",
                        "desktop_delivery_mode": "codex_app_server",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 33335,
            "stdout_path": "app-server-api.out.log",
            "stderr_path": "app-server-api.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "App-server dispatch may run on API when explicitly enabled",
                "body": "Please reply from this server.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    metadata = response.json()["data"]["metadata"]
    assert metadata["auto_start_launch_status"] == "launched"
    assert metadata["auto_start_launch_pid"] == 33335
    assert launch_mock.call_count == 1


def test_review_approve_autostarts_visible_workstation_command() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Review Approved Autostart",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "robotics",
                    "name": "Robotics NPC",
                    "status": "active",
                    "workstation_id": "robotics",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_enabled": False,
                        "desktop_visible": True,
                        "desktop_delivery_mode": "codex_desktop_ui",
                        "source_thread_id": "codex-session-robotics",
                    },
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    message_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Read-only robotics page review",
            "body": "Please implement read-only robot topic and waveform UI. No hardware writes.",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "robotics",
            "status": "pending_review",
        },
    )
    assert message_response.status_code == 200, message_response.text
    message = message_response.json()["data"]
    assert message["status"] == "pending_review"

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 33445,
            "stdout_path": "review-approved.out.log",
            "stderr_path": "review-approved.err.log",
        }
        approve_response = client.post(
            f"/api/collaboration/messages/{message['id']}/review/approve",
            headers=auth_headers(owner_token),
            json={"reason": "Read-only frontend implementation approved."},
        )
    assert approve_response.status_code == 200, approve_response.text
    approved = approve_response.json()["data"]
    metadata = approved["metadata"]
    assert approved["status"] == "queued"
    assert metadata["auto_start_attempt_count"] == 1
    assert metadata["auto_start_trigger"] == "review_approved"
    assert metadata["auto_start_launch_status"] == "waiting_for_bound_runner"
    assert "auto_start_launch_pid" not in metadata
    assert launch_mock.call_count == 0


def test_open_user_to_boss_command_can_complete_after_desktop_final() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"boss-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Open Boss Complete",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Boss Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-boss-open",
                        "desktop_delivery_mode": "codex_desktop_ui",
                        "desktop_visible": True,
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Boss should close after final",
            "body": "Please split work and return final.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "open",
        },
    )
    assert response.status_code == 200, response.text
    command = response.json()["data"]
    assert command["status"] == "open"

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers=auth_headers(owner_token),
        json={"result_status": "completed", "note": "Boss completed and dispatched NPC work."},
    )
    assert complete_response.status_code == 200, complete_response.text
    payload = complete_response.json()["data"]
    assert payload["command"]["status"] == "completed"
    assert payload["receipt"]["message_type"] == "agent_result"
    assert payload["receipt"]["metadata"]["source_message_id"] == command["id"]


def test_retry_desktop_sync_relaunches_autostart_for_same_command() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Retry Desktop Autostart",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Retry Seat",
                    "status": "active",
                    "ai_provider_id": "claude",
                    "metadata": {
                        "automation_enabled": True,
                        "automation_mode": "thread_watcher",
                        "automation_thread_id": "claude-session-retry",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 11111,
            "stdout_path": "first.out.log",
            "stderr_path": "first.err.log",
        }
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "agent_command",
                "title": "Retry same command",
                "body": "Please continue automatically.",
                "recipient_type": "thread_workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
    assert response.status_code == 200, response.text
    command = response.json()["data"]
    assert command["metadata"]["auto_start_launch_status"] == "launched"
    assert command["metadata"]["auto_start_attempt_count"] == 1

    with patch("app.modules.collaboration.service._launch_workstation_autostart") as launch_mock:
        launch_mock.return_value = {
            "launched": True,
            "status": "launched",
            "pid": 22222,
            "stdout_path": "retry.out.log",
            "stderr_path": "retry.err.log",
        }
        retry_response = client.post(
            f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/closeout-action",
            headers=auth_headers(owner_token),
            json={"action": "retry_desktop_sync"},
        )
    assert retry_response.status_code == 200, retry_response.text
    payload = retry_response.json()["data"]
    retried_command = payload["command"]
    receipt = payload["receipt"]
    metadata = retried_command["metadata"]

    assert retried_command["status"] == "in_progress"
    assert metadata["desktop_sync_retry_requested"] is False
    assert metadata["desktop_sync_retry_count"] == 1
    assert metadata["desktop_closeout_waiting"] is True
    assert metadata["auto_start_launch_status"] == "launched"
    assert metadata["auto_start_trigger"] == "desktop_retry_action"
    assert metadata["auto_start_attempt_count"] == 2
    assert metadata["auto_start_launch_pid"] == 22222
    assert receipt["metadata"]["desktop_closeout_action"] == "retry_desktop_sync"
    assert receipt["metadata"]["auto_start_launch_status"] == "launched"
    assert receipt["metadata"]["auto_start_attempt_count"] == 2


def test_auto_retry_receipts_keep_formal_seat_and_delegation_context() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Auto Retry Authority",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-boss"},
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-backend"},
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::backend": {"policy": "skip", "reason": "trusted same-project implementation"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    dispatch_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Retry authority check",
            "body": "Please continue and keep the same proj_ai_collab authority chain.",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend",
            "status": "queued",
            "metadata": {
                "origin": "platform_peer_dispatches",
                "source_thread_id": "codex-session-legacy-dispatch",
            },
        },
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    command = dispatch_response.json()["data"]

    with SessionLocal() as db:
        row = db.get(CollaborationMessage, command["id"])
        assert row is not None
        row.status = "acked"
        row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        db.add(row)
        db.commit()

    messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "limit": 30},
    )
    assert messages_response.status_code == 200, messages_response.text
    messages = messages_response.json()["data"]
    retry_receipt = next(
        item
        for item in messages
        if item["message_type"] == "agent_progress"
        and item["metadata"].get("source_message_id") == command["id"]
    )
    assert retry_receipt["project_id"] == project_id
    assert retry_receipt["metadata"]["authoritative_seat_id"] == "backend"
    assert retry_receipt["metadata"]["authoritative_seat_ref"] == "backend"
    assert retry_receipt["metadata"]["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert retry_receipt["metadata"]["delegation_context"]["target_seat_id"] == "backend"
    assert retry_receipt["metadata"]["historical_alias_non_authoritative"] is False


def test_desktop_thread_sync_records_user_question_and_minimal_receipt_once() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Desktop Sync")
    url = f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/desktop-sync"

    question_response = client.post(
        url,
        headers={"X-Workstation-Id": workstation_id},
        json={
            "role": "user",
            "note": "桌面版里用户追问：这个异常能不能拆小任务？",
            "session_id": "desktop-session-1",
            "source_event_id": "event-user-1",
            "source_timestamp": "2026-05-13T00:00:00Z",
        },
    )
    assert question_response.status_code == 200, question_response.text
    question = question_response.json()["data"]["message"]
    assert question_response.json()["data"]["deduped"] is False
    assert question["message_type"] == "desktop_user_question"
    assert question["sender_type"] == "human"
    assert question["recipient_id"] == workstation_id
    assert question["metadata"]["desktop_sync"] is True
    assert question["metadata"]["desktop_sync_latency_ms"] is not None
    assert question["metadata"]["desktop_sync_received_at"]

    duplicate_response = client.post(
        url,
        headers={"X-Workstation-Id": workstation_id},
        json={
            "role": "user",
            "note": "桌面版里用户追问：这个异常能不能拆小任务？",
            "session_id": "desktop-session-1",
            "source_event_id": "event-user-1",
            "source_timestamp": "2026-05-13T00:00:00Z",
        },
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["data"]["deduped"] is True
    assert duplicate_response.json()["data"]["message"]["id"] == question["id"]

    receipt_response = client.post(
        url,
        headers={"X-Workstation-Id": workstation_id},
        json={
            "role": "assistant",
            "note": "最小回执：已理解，将拆成后端同步和前端提示两步。",
            "phase": "minimal_ack",
            "session_id": "desktop-session-1",
            "source_event_id": "event-assistant-1",
            "linked_message_id": question["id"],
        },
    )
    assert receipt_response.status_code == 200, receipt_response.text
    receipt = receipt_response.json()["data"]["message"]
    assert receipt["message_type"] == "desktop_minimal_receipt"
    assert receipt["sender_type"] == "agent"
    assert receipt["status"] == "delivered"
    assert receipt["metadata"]["linked_message_id"] == question["id"]
    assert receipt["metadata"]["desktop_sync_received_at"]


def test_desktop_thread_sync_accepts_user_visible_workstation_alias() -> None:
    _owner_token, project_id, workstation_id, agent_alias = _project_with_workstation_alias("Desktop Alias")
    url = f"/api/collaboration/projects/{project_id}/thread-workstations/{agent_alias}/desktop-sync"

    response = client.post(
        url,
        headers={"X-Workstation-Id": agent_alias},
        json={
            "role": "user",
            "note": "用户按前端显示的 5 号 NPC 别名同步桌面提问。",
            "session_id": "desktop-session-alias",
            "source_event_id": "event-alias-user-1",
            "source_timestamp": "2026-05-13T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]["message"]
    assert message["agent_id"] == workstation_id
    assert message["recipient_id"] == workstation_id
    assert message["metadata"]["requested_workstation_id"] == agent_alias
    assert message["metadata"]["canonical_workstation_id"] == workstation_id
    assert message["metadata"]["authoritative_seat_id"] == workstation_id
    assert message["metadata"]["historical_alias_non_authoritative"] is True

    messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(_owner_token),
        params={
            "project_id": project_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "limit": 20,
        },
    )
    assert messages_response.status_code == 200
    assert any(item["id"] == message["id"] for item in messages_response.json()["data"])


def test_message_list_attaches_related_artifact_evidence_from_launch_ack() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Artifact Evidence")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Run platform evidence task",
            "body": "Produce a visible evidence trail.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    ack_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": workstation_id,
            "message_type": "agent_ack",
            "title": "单次线程处理已启动 / Claude Writer",
            "body": "Adapter accepted.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "completed",
            "metadata": {
                "source_message_id": command["id"],
                "authoritative_seat_id": workstation_id,
                "authoritative_seat_ref": workstation_id,
                "stdout_path": rf"D:\ai合作产品\artifacts\workstation-inbox\{project_id}\{workstation_id}\proj_ai_collab\{workstation_id}\sample.out.log",
                "stderr_path": f"artifacts/workstation-inbox/{project_id}/{workstation_id}/proj_ai_collab/{workstation_id}/sample.err.log",
            },
        },
    )
    assert ack_response.status_code == 200

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Final result with evidence."},
    )
    assert complete_response.status_code == 200

    result_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "sender_id": workstation_id, "limit": 10},
    )
    assert result_response.status_code == 200
    messages = result_response.json()["data"]
    final = next(item for item in messages if item["message_type"] == "agent_result")
    evidence = final["metadata"]["evidence_artifacts"]
    assert {"label": "执行日志", "path": f"artifacts/workstation-inbox/{project_id}/{workstation_id}/sample.out.log"} in evidence
    assert {"label": "错误日志", "path": f"artifacts/workstation-inbox/{project_id}/{workstation_id}/sample.err.log"} in evidence


def test_platform_workstation_adapter_output_dir_normalization_avoids_nested_project_and_boss_paths() -> None:
    adapter = _load_platform_workstation_adapter()

    base = adapter._normalize_workstation_output_base(
        Path("artifacts/workstation-inbox/proj_ai_collab/platform-npc-6"),
        project_id="proj_ai_collab",
    )
    assert str(base).replace("\\", "/") == "artifacts/workstation-inbox"


def test_workstation_inbox_preserves_structured_message_payload_through_receipts() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Structured NPC Cards")
    structured_payload = {
        "payload_json": {
            "card_kind": "task",
            "title": "Structured front-end card",
            "summary": "Render this as a compact NPC workbench card without changing the tile layout.",
            "status": "queued",
            "risk_level": "L1",
            "items": [
                {"label": "project", "value": "proj_ai_collab"},
                {"label": "scope", "value": "single message content area"},
            ],
            "actions": [{"label": "receipt", "value": "return minimal review"}],
        }
    }

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Structured message payload",
            "body": "This command carries a structured card payload for the NPC workbench.",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
            "metadata": structured_payload,
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]
    assert command["metadata"]["payload_json"]["card_kind"] == "task"

    inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert inbox_response.status_code == 200
    inbox = inbox_response.json()["data"]
    assert inbox[0]["id"] == command["id"]
    assert inbox[0]["metadata"]["payload_json"] == structured_payload["payload_json"]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Structured card accepted."},
    )
    assert ack_response.status_code == 200
    ack = ack_response.json()["data"]
    assert ack["command"]["metadata"]["payload_json"]["card_kind"] == "task"
    assert ack["receipt"]["metadata"]["source_message_id"] == command["id"]
    assert "payload_json" not in ack["receipt"]["metadata"]

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Structured card rendered and verified."},
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["command"]["metadata"]["payload_json"] == structured_payload["payload_json"]
    assert completed["receipt"]["metadata"]["source_message_id"] == command["id"]
    assert "payload_json" not in completed["receipt"]["metadata"]
    with SessionLocal() as db:
        stored = db.get(CollaborationMessage, command["id"])
        assert stored is not None
        assert stored.extra_data is not None
        assert stored.extra_data["payload_json"] == structured_payload["payload_json"]


def test_project_artifact_preview_reads_only_text_artifacts_under_artifacts() -> None:
    owner_token, project_id, _workstation_id = _project_with_workstation("Artifact Preview")
    repo_root = Path(__file__).resolve().parents[3]
    artifact_path = repo_root / "artifacts" / "tests" / f"artifact-preview-{uuid4().hex}.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# NPC Evidence\n\nComplete receipt content.", encoding="utf-8")
    try:
        response = client.get(
            f"/api/collaboration/projects/{project_id}/artifacts/preview",
            headers=auth_headers(owner_token),
            params={"path": str(artifact_path)},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["path"].startswith("artifacts/")
        assert data["name"] == artifact_path.name
        assert data["content"].startswith("# NPC Evidence")
        assert data["truncated"] is False
    finally:
        artifact_path.unlink(missing_ok=True)


def test_project_artifact_download_reads_export_artifacts_under_artifacts() -> None:
    owner_token, project_id, _workstation_id = _project_with_workstation("Artifact Download")
    repo_root = Path(__file__).resolve().parents[3]
    artifact_path = repo_root / "artifacts" / "tests" / f"artifact-download-{uuid4().hex}.jsonl"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('{"label":"confirmed","value":1}\n', encoding="utf-8")
    try:
        response = client.get(
            f"/api/collaboration/projects/{project_id}/artifacts/download",
            headers=auth_headers(owner_token),
            params={"path": str(artifact_path)},
        )
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("attachment;")
        assert artifact_path.name in response.headers["content-disposition"]
        assert response.text.strip() == '{"label":"confirmed","value":1}'
    finally:
        artifact_path.unlink(missing_ok=True)


def test_project_artifact_preview_supports_proxy_safe_query_route() -> None:
    owner_token, project_id, _workstation_id = _project_with_workstation("Artifact Proxy Preview")
    repo_root = Path(__file__).resolve().parents[3]
    artifact_path = repo_root / "artifacts" / "tests" / f"artifact-proxy-preview-{uuid4().hex}.log"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("proxy-safe preview content", encoding="utf-8")
    try:
        response = client.get(
            "/api/collaboration/artifacts/preview",
            headers=auth_headers(owner_token),
            params={"project_id": project_id, "path": str(artifact_path)},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["path"].startswith("artifacts/")
        assert data["content"] == "proxy-safe preview content"
    finally:
        artifact_path.unlink(missing_ok=True)


def test_project_artifact_preview_rejects_paths_outside_artifacts() -> None:
    owner_token, project_id, _workstation_id = _project_with_workstation("Artifact Preview Scope")
    response = client.get(
        f"/api/collaboration/projects/{project_id}/artifacts/preview",
        headers=auth_headers(owner_token),
        params={"path": "apps/api/app/main.py"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ARTIFACT_PATH_NOT_ALLOWED"


def test_human_proxy_agent_dispatch_keeps_audit_origin() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Human Proxy Agent Audit")

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Proxy dispatch",
            "body": "Use the NPC tile to send a teammate request.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["sender_type"] == "agent"
    assert message["sender_id"] == workstation_id
    assert message["metadata"]["origin"] == "human_proxy"
    assert message["metadata"]["claimed_sender_agent_id"] == workstation_id
    assert message["metadata"]["actor_user_id"]


def test_workstation_progress_marks_command_in_progress_and_dedupes_receipt() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Desktop Progress")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Desktop visible turn",
            "body": "Send this to a bound Codex Desktop thread.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Accepted and delivering to Desktop."},
    )
    assert ack_response.status_code == 200

    progress_payload = {
        "note": "已送进 Codex Desktop，等待最终回复。",
        "state": "awaiting_desktop_reply",
        "metadata": {"delivery_mode": "codex_desktop_ui", "desktop_visible": True},
    }
    progress_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/progress",
        headers={"X-Workstation-Id": workstation_id},
        json=progress_payload,
    )
    assert progress_response.status_code == 200
    progress = progress_response.json()["data"]
    assert progress["command"]["status"] == "in_progress"
    assert progress["receipt"]["message_type"] == "agent_progress"
    assert progress["receipt"]["status"] == "in_progress"
    assert progress["receipt"]["metadata"]["source_message_id"] == command["id"]
    assert progress["receipt"]["metadata"]["progress_state"] == "awaiting_desktop_reply"
    progress_receipt_id = progress["receipt"]["id"]

    second_progress_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/progress",
        headers={"X-Workstation-Id": workstation_id},
        json={**progress_payload, "note": "仍在等待 Codex Desktop 最终回复。"},
    )
    assert second_progress_response.status_code == 200
    second_progress = second_progress_response.json()["data"]
    assert second_progress["receipt"]["id"] == progress_receipt_id
    assert second_progress["receipt"]["body"] == "仍在等待 Codex Desktop 最终回复。"

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Desktop final answer synced."},
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["command"]["status"] == "completed"
    assert completed["receipt"]["message_type"] == "agent_result"
    with SessionLocal() as db:
        progress_message = db.get(CollaborationMessage, progress_receipt_id)
        assert progress_message is not None
        assert progress_message.status == "completed"


def test_list_messages_repairs_stale_launch_ack_after_completed_command() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Launch Ack Read Repair")

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Already completed desktop turn",
            "body": "This command has a stale launch ack.",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "completed",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    launch_ack_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": workstation_id,
            "message_type": "agent_ack",
            "title": "单次线程处理已启动 / Claude Writer",
            "body": "Desktop turn started before the completion repair existed.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "in_progress",
            "metadata": {"source_message_id": command["id"]},
        },
    )
    assert launch_ack_response.status_code == 200
    launch_ack = launch_ack_response.json()["data"]

    list_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert list_response.status_code == 200
    messages = {item["id"]: item for item in list_response.json()["data"]}
    assert messages[launch_ack["id"]]["status"] == "completed"

    with SessionLocal() as db:
        ack_message = db.get(CollaborationMessage, launch_ack["id"])
        assert ack_message is not None
        assert ack_message.status == "completed"


def test_list_messages_repairs_legacy_launch_ack_without_source_id_when_final_exists() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Legacy Launch Ack Read Repair")

    launch_ack_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": workstation_id,
            "message_type": "agent_ack",
            "title": "单次线程处理已启动 / Claude Writer",
            "body": "Legacy launch ack without source_message_id.",
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "in_progress",
        },
    )
    assert launch_ack_response.status_code == 200
    launch_ack = launch_ack_response.json()["data"]

    final_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "agent_id": "Claude Writer",
            "message_type": "agent_result",
            "title": "Final desktop result",
            "body": "The visible desktop turn finished.",
            "sender_type": "agent",
            "sender_id": "Claude Writer",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "completed",
        },
    )
    assert final_response.status_code == 200

    list_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert list_response.status_code == 200
    messages = {item["id"]: item for item in list_response.json()["data"]}
    assert messages[launch_ack["id"]]["status"] == "completed"


def test_collaboration_message_preview_is_read_only_and_warns_about_pending_target_messages() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Workstation Preview")

    existing_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Existing queued command",
            "body": "Finish the current queued task before accepting more work.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert existing_response.status_code == 200

    preview_response = client.post(
        "/api/collaboration/messages/preview",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Preview only command",
            "body": "Plan the next collaborative writing step and report what should happen first.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["project_id"] == project_id
    assert preview["recipient_id"] == workstation_id
    assert preview["recipient_label"] == "Claude Writer"
    assert preview["ready"] is True
    assert preview["pending_target_message_count"] == 1
    assert preview["recent_same_type_count"] >= 1
    assert isinstance(preview["preview_signature"], str)
    assert any("未收口" in item for item in preview["warnings"])

    messages_response = client.get(
        f"/api/collaboration/messages?project_id={project_id}",
        headers=auth_headers(owner_token),
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()["data"]
    assert len(messages) == 1
    assert messages[0]["title"] == "Existing queued command"


def test_collaboration_message_preview_rejects_historical_seat_alias_name_lookup() -> None:
    owner_token, project_id, _workstation_id, agent_alias = _project_with_workstation_alias("Preview Alias Reject")

    preview_response = client.post(
        "/api/collaboration/messages/preview",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Preview only command",
            "body": "Use the formal seat id only and reject historical aliases in preview.",
            "recipient_type": "workstation",
            "recipient_id": agent_alias,
            "status": "queued",
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["ready"] is False
    assert any("可能已经被删除或换了项目" in item for item in preview["blockers"])


def test_seat_queue_and_receipts_are_scoped_by_project_id_for_same_named_npcs() -> None:
    owner_token, owner_user_id = issue_session_token(client)

    def make_project(prefix: str) -> tuple[str, str]:
        seat_name = "Shared NPC"
        project = create_project(
            client,
            owner_token,
            name_prefix=prefix,
            collaboration_config={
                "thread_workstations": [
                    {
                        "id": f"shared-{uuid4().hex[:8]}",
                        "name": seat_name,
                        "agent_id": seat_name,
                        "status": "active",
                        "ai_provider_id": "codex",
                    }
                ],
            },
        )
        project_id = project["id"]
        add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
        with SessionLocal() as db:
            seat = db.query(ProjectThreadWorkstation).filter(
                ProjectThreadWorkstation.project_id == project_id,
                ProjectThreadWorkstation.name == seat_name,
            ).one()
            return project_id, seat.id

    project_a, seat_a = make_project("Seat Scope A")
    project_b, seat_b = make_project("Seat Scope B")

    req_a = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_a,
            "title": "Project A requirement",
            "requirement_type": "thread_request",
            "status": "queued",
            "from_agent": "boss-a",
            "to_agent": seat_a,
            "target_seat_id": seat_a,
            "context_summary": "Only project A should see this.",
            "expected_output": "A only.",
        },
    )
    assert req_a.status_code == 200
    req_b = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_b,
            "title": "Project B requirement",
            "requirement_type": "thread_request",
            "status": "queued",
            "from_agent": "boss-b",
            "to_agent": seat_b,
            "target_seat_id": seat_b,
            "context_summary": "Only project B should see this.",
            "expected_output": "B only.",
        },
    )
    assert req_b.status_code == 200

    queue_a = client.get(
        f"/api/seats/Shared NPC/queues?project_id={project_a}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert queue_a.status_code == 200
    queue_a_items = queue_a.json()["data"]["requirement_inbox"]["items"]
    assert {item["title"] for item in queue_a_items} == {"Project A requirement"}
    assert queue_a.json()["data"]["my_needs"]["count"] == 0
    assert queue_a.json()["data"]["my_tasks"]["count"] == 0

    receipt_a = client.post(
        "/api/receipts",
        headers=auth_headers(owner_token),
        json={
            "parent_requirement_id": req_a.json()["data"]["id"],
            "receipt_kind": "progress",
            "sender_seat_id": seat_a,
            "recipient_seat_id": seat_a,
            "body": "Project A progress.",
        },
    )
    assert receipt_a.status_code == 200
    receipt_b = client.post(
        "/api/receipts",
        headers=auth_headers(owner_token),
        json={
            "parent_requirement_id": req_b.json()["data"]["id"],
            "receipt_kind": "progress",
            "sender_seat_id": seat_b,
            "recipient_seat_id": seat_b,
            "body": "Project B progress.",
        },
    )
    assert receipt_b.status_code == 200

    receipts_a = client.get(
        f"/api/receipts/by-seat/Shared NPC?project_id={project_a}&direction=both&limit=20",
        headers=auth_headers(owner_token),
    )
    assert receipts_a.status_code == 200
    assert [item["body"] for item in receipts_a.json()["data"]] == ["Project A progress."]


def test_seat_queues_split_my_needs_from_my_tasks() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Seat Need Task Split",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "seat-split-a",
                    "name": "Split A",
                    "agent_id": "agent-split-a",
                    "status": "active",
                },
                {
                    "id": "seat-split-b",
                    "name": "Split B",
                    "agent_id": "agent-split-b",
                    "status": "active",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    need_response = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "A needs B to review data",
            "requirement_type": "thread_request",
            "status": "queued",
            "from_agent": "seat-split-a",
            "to_agent": "seat-split-b",
            "target_seat_id": "seat-split-b",
            "context_summary": "A lacks review capacity.",
            "expected_output": "B returns a review note.",
        },
    )
    assert need_response.status_code == 200
    task_response = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Task owned by A",
            "description": "A should do this.",
            "module": "queue",
            "priority": "P1",
            "status": "queued",
            "assignee_agent_id": "agent-split-a",
        },
    )
    assert task_response.status_code == 200

    queue_a = client.get(
        f"/api/seats/seat-split-a/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert queue_a.status_code == 200
    queue_a_data = queue_a.json()["data"]
    assert {item["title"] for item in queue_a_data["my_needs"]["items"]} == {"A needs B to review data"}
    assert {item["title"] for item in queue_a_data["my_tasks"]["items"]} == {"Task owned by A"}
    assert queue_a_data["requirement_inbox"]["count"] == 0

    queue_b = client.get(
        f"/api/seats/seat-split-b/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert queue_b.status_code == 200
    queue_b_data = queue_b.json()["data"]
    assert {item["title"] for item in queue_b_data["requirement_inbox"]["items"]} == {"A needs B to review data"}
    assert queue_b_data["my_needs"]["count"] == 0
    assert queue_b_data["my_tasks"]["count"] == 0

    close_response = client.post(
        f"/api/requirements/{need_response.json()['data']['id']}/close",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "note": "review done"},
    )
    assert close_response.status_code == 200, close_response.text
    archive_response = client.post(
        f"/api/requirements/{need_response.json()['data']['id']}/archive",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "note": "clear current queue only"},
    )
    assert archive_response.status_code == 200, archive_response.text

    queue_after_archive = client.get(
        f"/api/seats/seat-split-a/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert queue_after_archive.status_code == 200
    assert queue_after_archive.json()["data"]["my_needs"]["count"] == 0


def test_seat_task_queue_matches_npc_seat_identity_without_agent() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Seat Identity Task Queue",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "seat-identity-a",
                    "config_id": "identity-config-a",
                    "name": "Identity A",
                    "status": "active",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="seat-identity-a").one()
        seat_id = str(seat.id)
        seat.config_id = "identity-config-a"
        db.add(seat)
        db.commit()

    task_by_seat_id = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Task indexed to NPC seat id",
            "description": "Created from a default NPC task receipt path.",
            "module": "queue",
            "priority": "P1",
            "status": "queued",
            "assignee_agent_id": seat_id,
        },
    )
    assert task_by_seat_id.status_code == 200, task_by_seat_id.text
    task_by_config_id = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Task indexed to NPC config id",
            "description": "Created from another NPC task receipt path.",
            "module": "queue",
            "priority": "P2",
            "status": "queued",
            "assignee_agent_id": "identity-config-a",
        },
    )
    assert task_by_config_id.status_code == 200, task_by_config_id.text

    queue = client.get(
        f"/api/seats/{seat_id}/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert queue.status_code == 200
    titles = {item["title"] for item in queue.json()["data"]["my_tasks"]["items"]}
    assert titles == {"Task indexed to NPC seat id", "Task indexed to NPC config id"}


def test_structured_need_queue_includes_pre_route_statuses() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Structured Need Queue Statuses",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "seat-need-owner",
                    "name": "Need Owner",
                    "agent_id": "agent-need-owner",
                    "status": "active",
                },
                {
                    "id": "seat-need-target",
                    "name": "Need Target",
                    "agent_id": "agent-need-target",
                    "status": "active",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    for status in ("ready_to_route", "needs_human_review"):
        response = client.post(
            "/api/requirements",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "title": f"Structured Need {status}",
                "requirement_type": "npc_structured_need",
                "status": status,
                "from_agent": "seat-need-owner",
                "to_agent": "seat-need-target",
                "target_seat_id": "seat-need-target",
                "context_summary": "Pre-route structured Need must stay visible to the requester.",
                "expected_output": "Target task after route.",
            },
        )
        assert response.status_code == 200, response.text

    owner_queue = client.get(
        f"/api/seats/seat-need-owner/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert owner_queue.status_code == 200, owner_queue.text
    owner_data = owner_queue.json()["data"]
    assert {"ready_to_route", "needs_human_review"}.issubset(set(owner_data["my_needs"]["statuses_included"]))
    assert {item["status"] for item in owner_data["my_needs"]["items"]} == {
        "ready_to_route",
        "needs_human_review",
    }

    target_queue = client.get(
        f"/api/seats/seat-need-target/queues?project_id={project_id}&limit=20",
        headers=auth_headers(owner_token),
    )
    assert target_queue.status_code == 200, target_queue.text
    target_data = target_queue.json()["data"]
    assert {"ready_to_route", "needs_human_review"}.issubset(set(target_data["requirement_inbox"]["statuses_included"]))
    assert {item["status"] for item in target_data["requirement_inbox"]["items"]} == {
        "ready_to_route",
        "needs_human_review",
    }


def test_human_review_request_can_be_closed_without_entering_workstation_inbox() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Human Review Queue")

    review_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "human_review_request",
            "title": "人工审核：烧录前确认",
            "body": "原始目标: ws\n目标类型: workstation\n原始指令:\n请先确认真实硬件边界。",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "pending_human_review",
        },
    )
    assert review_response.status_code == 200
    review = review_response.json()["data"]

    inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert inbox_response.status_code == 200
    assert all(item["id"] != review["id"] for item in inbox_response.json()["data"])

    outsider_user_id, outsider_email = register_user(
        client,
        f"human-review-outsider-{uuid4().hex[:8]}@example.com",
        "Human Review Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)
    outsider_patch = client.patch(
        f"/api/collaboration/messages/{review['id']}",
        headers=auth_headers(outsider_token),
        json={"status": "rejected"},
    )
    assert outsider_patch.status_code == 403

    patch_response = client.patch(
        f"/api/collaboration/messages/{review['id']}",
        headers=auth_headers(owner_token),
        json={"status": "rejected"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["status"] == "rejected"


def test_workstation_inbox_updates_requirement_ack_and_final_reply() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Workstation Requirement Inbox")

    task_response = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Requirement inbox task",
            "description": "Exercise workstation inbox requirement flow.",
            "module": "collaboration",
            "priority": "P1",
            "status": "ready",
            "branch": "feature/workstation-inbox",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["data"]["id"]

    requirement_response = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task_id,
            "title": "Workstation inbox requirement",
            "requirement_type": "thread_request",
            "status": "waiting_response",
            "from_agent": "human-chief",
            "to_agent": workstation_id,
            "context_summary": "Require a minimal ack and a final reply through the workstation inbox.",
            "expected_output": "Ack then final reply.",
            "opening_message": "Please accept and finish this requirement.",
        },
    )
    assert requirement_response.status_code == 200
    requirement_id = requirement_response.json()["data"]["id"]

    dispatch_response = client.post(
        f"/api/requirements/{requirement_id}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "target_type": "workstation",
            "target_id": workstation_id,
            "title": "Please handle requirement",
            "body": "Return one minimal ack first, then a final reply.",
        },
    )
    assert dispatch_response.status_code == 200
    command = dispatch_response.json()["data"]["message"]
    assert command["message_type"] == "requirement_dispatch"

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id},
        json={"note": "Minimum ack from workstation adapter."},
    )
    assert ack_response.status_code == 200
    ack = ack_response.json()["data"]
    assert ack["command"]["status"] == "acked"
    assert ack["receipt"]["message_type"] == "requirement_progress_ack"
    assert ack["receipt"]["status"] == "in_progress"

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": workstation_id},
        json={"result_status": "completed", "note": "Final reply from workstation adapter."},
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["command"]["status"] == "completed"
    assert completed["receipt"]["message_type"] == "requirement_final_reply"
    assert completed["receipt"]["status"] == "done"


def test_workstation_inbox_rejects_mismatched_adapter_identity() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Workstation Identity")
    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Identity check",
            "body": "Only the addressed workstation may receive this.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200

    inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": "other-workstation"},
    )
    assert inbox_response.status_code == 403
    assert inbox_response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_workstation_inbox_requires_bound_runner_for_computer_routing() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"npc-{uuid4().hex[:8]}"
    node_a = f"node-a-{uuid4().hex[:6]}"
    node_b = f"node-b-{uuid4().hex[:6]}"
    runner_a = f"runner-a-{uuid4().hex[:6]}"
    runner_b = f"runner-b-{uuid4().hex[:6]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Runner Routing",
        collaboration_config={
            "computer_nodes": [
                {"id": node_a, "label": "Windows dev box", "status": "online", "runner_id": runner_a},
                {"id": node_b, "label": "Linux dev box", "status": "online", "runner_id": runner_b},
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "1号 Codex",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "computer_node_id": node_a,
                    "metadata": {"source_kind": "runner_thread_scan"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    with SessionLocal() as db:
        db.merge(Runner(id=runner_a, name="Windows runner", capabilities=["codex"], status="online"))
        db.merge(Runner(id=runner_b, name="Linux runner", capabilities=["codex"], status="online"))
        db.commit()

    command_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Runner isolation check",
            "body": "Only the runner bound to node A may consume this.",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"]

    wrong_runner_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id, "X-Runner-Id": runner_b},
    )
    assert wrong_runner_response.status_code == 403
    assert wrong_runner_response.json()["error"]["code"] == "PERMISSION_DENIED"

    right_runner_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id, "X-Runner-Id": runner_a},
    )
    assert right_runner_response.status_code == 200
    assert [item["id"] for item in right_runner_response.json()["data"]] == [command["id"]]

    wrong_ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id, "X-Runner-Id": runner_b},
        json={"note": "Wrong runner should not claim this."},
    )
    assert wrong_ack_response.status_code == 403

    right_ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": workstation_id, "X-Runner-Id": runner_a},
        json={"note": "Bound runner accepted this task."},
    )
    assert right_ack_response.status_code == 200
    assert right_ack_response.json()["data"]["command"]["status"] == "acked"


def test_workstation_adapter_token_rotates_revokes_and_gates_inbox_access() -> None:
    owner_token, project_id, workstation_id = _project_with_workstation("Workstation Token")

    rotate_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token",
        headers=auth_headers(owner_token),
    )
    assert rotate_response.status_code == 200
    rotated = rotate_response.json()["data"]
    token = rotated["token"]
    assert isinstance(token, str) and token
    assert rotated["token_available"] is True
    assert rotated["issued_at"] is not None

    status_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token",
        headers=auth_headers(owner_token),
    )
    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["token"] is None
    assert status["token_available"] is True
    assert status["issued_at"] is not None

    no_token_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert no_token_response.status_code == 403
    assert no_token_response.json()["error"]["code"] == "PERMISSION_DENIED"

    wrong_token_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id, "X-Workstation-Token": "wrong-token"},
    )
    assert wrong_token_response.status_code == 403
    assert wrong_token_response.json()["error"]["code"] == "PERMISSION_DENIED"

    good_token_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id, "X-Workstation-Token": token},
    )
    assert good_token_response.status_code == 200
    used_status_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token",
        headers=auth_headers(owner_token),
    )
    assert used_status_response.status_code == 200
    used_status = used_status_response.json()["data"]
    assert used_status["token_available"] is True
    assert used_status["last_used_at"] is not None

    revoke_response = client.delete(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token",
        headers=auth_headers(owner_token),
    )
    assert revoke_response.status_code == 200
    revoked = revoke_response.json()["data"]
    assert revoked["token"] is None
    assert revoked["token_available"] is False
    assert revoked["last_used_at"] is None

    inbox_after_revoke = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert inbox_after_revoke.status_code == 200


def test_workstation_adapter_config_merges_workstation_provider_and_node_settings() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Config",
        collaboration_config={
            "ai_providers": [
                {
                    "id": "claude",
                    "label": "Claude",
                    "metadata": {
                        "adapter": {
                            "executor_command": "python provider-executor.py @PROMPT_FILE@",
                            "executor_cwd": "D:/providers/claude-runtime",
                            "executor_timeout_seconds": 910,
                        }
                    },
                }
            ],
            "computer_nodes": [
                {
                    "id": "node-1",
                    "label": "电脑 1",
                    "workspace_root": "D:/workspaces/node-1",
                    "git_root": "D:/workspaces/node-1/repo",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Claude Writer",
                    "status": "active",
                    "computer_node_id": "node-1",
                    "ai_provider_id": "claude",
                    "metadata": {
                        "automation_enabled": True,
                        "automation_mode": "thread_watcher",
                        "automation_thread_id": "claude-session-test",
                        "adapter": {
                            "executor_command": "python workstation-executor.py @PROMPT_FILE@",
                        },
                        "executor_timeout_seconds": 120,
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project_id
    assert data["workstation_id"] == workstation_id
    assert data["provider_id"] == "claude"
    assert data["provider_label"] == "Claude"
    assert data["automation_enabled"] is True
    assert data["automation_mode"] == "thread_watcher"
    assert data["automation_thread_id"] == "claude-session-test"
    assert data["delivery_mode"] == "custom"
    assert data["desktop_visible"] is False
    assert data["executor_command"] == "python workstation-executor.py @PROMPT_FILE@"
    assert data["executor_cwd"] == "D:/providers/claude-runtime"
    assert data["executor_timeout_seconds"] == 120
    assert data["settings_source"]["executor_command"] == "workstation.metadata.adapter.executor_command"
    assert data["settings_source"]["executor_cwd"] == "provider.metadata.adapter.executor_cwd"
    assert data["settings_source"]["executor_timeout_seconds"] == "workstation.metadata.executor_timeout_seconds"


def test_workstation_adapter_config_ignores_scanned_workspace_metadata_for_executor_cwd() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Scan Metadata",
        collaboration_config={
            "ai_providers": [
                {
                    "id": "codex",
                    "label": "Codex",
                    "metadata": {
                        "adapter": {
                            "executor_command": "python provider-executor.py @PROMPT_FILE@",
                        }
                    },
                }
            ],
            "computer_nodes": [
                {
                    "id": "node-scan",
                    "label": "扫描电脑",
                    "workspace_root": "D:/owner/workspace",
                    "git_root": "D:/owner/workspace/repo",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Scan Thread",
                    "status": "active",
                    "computer_node_id": "node-scan",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "cwd": "D:/scan-only/current-shell",
                        "workspace_root": "D:/scan-only/workspace",
                        "git_root": "D:/scan-only/git",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["executor_cwd"] == "D:/owner/workspace/repo"
    assert data["delivery_mode"] == "custom"
    assert data["desktop_visible"] is False
    assert data["settings_source"]["executor_cwd"] == "computer_node.git_root"
    assert "D:/scan-only" not in data["executor_cwd"]


def test_workstation_adapter_config_allows_missing_provider_registration() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Missing Provider",
        collaboration_config={
            "computer_nodes": [
                {
                    "id": "node-claude",
                    "label": "未登记 provider 的电脑",
                    "git_root": "D:/node/repo",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Claude Scanned Thread",
                    "status": "active",
                    "computer_node_id": "node-claude",
                    "ai_provider_id": "claude",
                    "metadata": {"source": "runner_thread_scan"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_id"] == "claude"
    assert data["provider_label"] == "claude"
    assert data["executor_cwd"] == "D:/node/repo"


def test_workstation_adapter_config_falls_back_to_project_local_git_url() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Project Cwd",
        local_git_url="D:/projects/current-platform",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Project Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-project-seat",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["executor_cwd"] == "D:/projects/current-platform"
    assert data["settings_source"]["executor_cwd"] == "project.local_git_url"
    assert "当前未解析到执行目录" not in (data["delivery_warning"] or "")


def test_workstation_adapter_config_does_not_use_local_git_alias_as_executor_cwd() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Project Alias",
        local_git_url="local://ai-collab",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Alias Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-project-alias",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["executor_cwd"] is None
    assert "executor_cwd" not in data["settings_source"]
    assert "当前未解析到执行目录" in (data["delivery_warning"] or "")


def test_workstation_adapter_config_labels_codex_resume_delivery() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Codex Resume",
        collaboration_config={
            "computer_nodes": [
                {
                    "id": "node-codex",
                    "label": "Codex 电脑",
                    "git_root": "D:/node/codex-repo",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Boss",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["automation_thread_id"] == "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451"
    assert data["delivery_mode"] == "codex_desktop_ui_required"
    assert data["delivery_label"] == "等待桌面线程接入"
    assert data["desktop_thread_url"] == "codex://threads/019e0d07-85d5-7d92-b9da-69cc2e35f451"
    assert data["desktop_visible"] is False
    assert data["desktop_bridge_connected"] is False
    assert "桌面版看到详细处理过程" in data["delivery_warning"]
    assert "还没有检测到可用的桌面版处理通道" in data["delivery_warning"]


def test_adapter_defaults_bound_codex_session_to_desktop_visible_delivery() -> None:
    adapter = _load_platform_workstation_adapter()

    template, mode = adapter._default_executor_template(
        "codex",
        None,
        True,
        automation_thread_id="codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451",
        desktop_delivery_mode=None,
    )

    assert template == adapter.CODEX_DESKTOP_UI_EXECUTOR
    assert mode == "codex_desktop_ui_required"


def test_adapter_honors_explicit_codex_app_server_override() -> None:
    adapter = _load_platform_workstation_adapter()

    template, mode = adapter._default_executor_template(
        "codex",
        None,
        True,
        automation_thread_id="codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451",
        desktop_delivery_mode="codex_app_server",
    )

    assert template == adapter.CODEX_APP_SERVER_EXECUTOR
    assert mode == "codex_app_server"


def test_adapter_prompt_does_not_require_missing_default_knowledge_paths() -> None:
    adapter = _load_platform_workstation_adapter()

    command = {
        "id": "msg-knowledge-path",
        "title": "Check prompt paths",
        "body": "请按真实项目上下文处理。",
        "recipient_id": "platform-npc-missing-docs",
        "message_type": "agent_command",
        "status": "queued",
    }

    markdown = adapter._command_markdown(
        command,
        project_id=f"proj-missing-{uuid4().hex[:6]}",
        workstation_id="platform-npc-missing-docs",
        provider="codex",
        computer_node_id=f"node-missing-{uuid4().hex[:6]}",
        workstation_knowledge_path="docs/workstations/definitely-missing.md",
    )
    prompt = adapter._extract_executor_prompt(markdown)

    assert "No project/NPC/workstation knowledge file is currently registered on disk" in markdown
    assert "不要报告默认路径缺失" in prompt
    assert "docs/npcs/platform-npc-missing-docs" not in prompt
    assert "docs/workstations/definitely-missing.md" not in prompt


def test_workstation_adapter_config_reports_codex_desktop_process_without_bridge() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Codex Desktop State",
        collaboration_config={
            "computer_nodes": [{"id": "node-codex", "label": "Codex 电脑", "git_root": "D:/node/repo"}],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Boss",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451",
                        "codex_desktop_process_detected": True,
                        "desktop_bridge_note": "Runner detected Desktop process, but no supported live UI bridge.",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["desktop_process_detected"] is True
    assert data["desktop_bridge_connected"] is False
    assert data["desktop_bridge_note"] == "Runner detected Desktop process, but no supported live UI bridge."
    assert data["desktop_visible"] is False
    assert data["delivery_mode"] == "codex_desktop_ui_required"
    assert "检测到桌面版进程" in data["delivery_warning"]


def test_workstation_adapter_config_reports_codex_desktop_ui_bridge() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Codex Desktop UI",
        collaboration_config={
            "computer_nodes": [{"id": "node-codex", "label": "Codex 电脑", "git_root": "D:/node/repo"}],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Boss",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451",
                        "codex_desktop_process_detected": True,
                        "desktop_bridge_connected": True,
                        "desktop_bridge_label": "Codex Desktop UI automation",
                        "desktop_delivery_mode": "codex_desktop_ui",
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_visible"] is True
    assert data["desktop_bridge_connected"] is True
    assert data["delivery_label"] == "桌面后台可接收"
    assert "不会抢占当前窗口" in data["delivery_warning"]


def test_workstation_adapter_config_inherits_cwd_from_bound_scanned_thread() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    bound_thread_id = "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Bound Thread Cwd",
        collaboration_config={
            "computer_nodes": [
                {
                    "id": "node-codex",
                    "label": "Codex 电脑",
                }
            ],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Boss",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": bound_thread_id,
                    },
                },
                {
                    "id": bound_thread_id,
                    "name": "Scanned Codex Thread",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "source": "runner_thread_scan",
                        "cwd": "D:/english_a_agent",
                        "workspace_root": "D:/scan-only",
                    },
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["executor_cwd"] == "D:/english_a_agent"
    assert data["settings_source"]["executor_cwd"] == "bound_thread.metadata.cwd"


def test_workstation_adapter_config_inherits_desktop_bridge_from_bound_scanned_thread() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"ws-{uuid4().hex[:8]}"
    bound_thread_id = "codex-session-019e0d07-85d5-7d92-b9da-69cc2e35f451"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Bound Thread Desktop Bridge",
        collaboration_config={
            "computer_nodes": [{"id": "node-codex", "label": "Codex 电脑"}],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Codex Boss",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "automation_thread_id": bound_thread_id,
                    },
                },
                {
                    "id": bound_thread_id,
                    "name": "Scanned Codex Thread",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "source": "runner_thread_scan",
                        "cwd": "D:/english_a_agent",
                        "desktop_process_detected": True,
                        "desktop_bridge_connected": True,
                        "desktop_bridge_label": "Codex Desktop UI automation",
                        "desktop_delivery_mode": "codex_desktop_ui",
                    },
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_visible"] is True
    assert data["desktop_bridge_connected"] is True
    assert data["delivery_label"] == "桌面后台可接收"
    assert data["executor_cwd"] == "D:/english_a_agent"


def test_workstation_adapter_config_accepts_platform_numbered_desktop_binding_metadata() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = f"platform-npc-{uuid4().hex[:6]}"
    bound_thread_id = "codex-session-019e1bc9-64d1-7d02-98a1-5a7d1d6c3356"
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Adapter Numbered Desktop Binding",
        collaboration_config={
            "computer_nodes": [{"id": "node-codex", "label": "Codex 电脑", "git_root": "D:/ai合作产品"}],
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "1号 前端实现",
                    "status": "active",
                    "computer_node_id": "node-codex",
                    "ai_provider_id": "codex",
                    "metadata": {
                        "desktop_visible": True,
                        "delivery_mode": "codex_desktop_ui",
                        "target_thread_id": bound_thread_id,
                        "bound_thread_id": bound_thread_id,
                    },
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["automation_thread_id"] == bound_thread_id
    assert data["delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_delivery_mode"] == "codex_desktop_ui"
    assert data["desktop_visible"] is True
    assert data["desktop_bridge_connected"] is True
    assert data["desktop_thread_url"] == "codex://threads/019e1bc9-64d1-7d02-98a1-5a7d1d6c3356"


def test_inbox_accepts_non_ascii_workstation_id_via_percent_encoding() -> None:
    """Regression: 中文 workstation_id 必须能通过 percent-encoded header 完成鉴权。

    urllib 默认按 latin-1 编码 header，所以远端 adapter 把非 ASCII id 用
    percent-encoding + X-Workstation-Id-Encoding: percent 一起发；API 端的
    read_identity_header 会还原。"""
    from urllib.parse import quote

    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = "前端工位"
    project = create_project(
        client,
        owner_token,
        name_prefix="Non-ASCII WS Inbox",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": workstation_id,
                    "status": "active",
                    "ai_provider_id": "claude",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    encoded_path_id = quote(workstation_id, safe="")
    encoded_header = quote(workstation_id, safe="")

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{encoded_path_id}/inbox",
        headers={
            "X-Workstation-Id": encoded_header,
            "X-Workstation-Id-Encoding": "percent",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


def test_thread_workstation_list_exposes_db_row_id_for_logical_workstation_leads() -> None:
    """Workbench uses row_id to match ProjectWorkstation.lead_seat_id UUIDs.

    Older JSON collaboration_config entries may keep a human-readable id such as
    "YueSpeak Boss", while logical workstation leads store the database seat id.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Logical Lead Row Id",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "YueSpeak Boss",
                    "name": "YueSpeak Boss",
                    "status": "idle",
                    "ai_provider_id": "codex",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="YueSpeak Boss").one()
        seat_pk = seat.id

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["id"] == "YueSpeak Boss"
    assert data[0]["row_id"] == seat_pk


def test_thread_workstation_update_keeps_thread_binding_fields_in_sync() -> None:
    """Binding from the main page must update both UI config and executable seat row.

    The 2D main page uses metadata for the selected option, while runner execution
    reads ProjectThreadWorkstation.extra_data. They must not drift apart.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Thread Binding Sync",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "YueSpeak Boss",
                    "name": "YueSpeak Boss",
                    "status": "idle",
                    "ai_provider_id": "codex",
                    "source_workstation_id": "codex-session-old-placeholder",
                    "metadata": {"source_workstation_id": "codex-session-real-boss-thread"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/YueSpeak%20Boss",
        headers=auth_headers(owner_token),
        json={
            "ai_provider_id": "codex",
            "source_workstation_id": "codex-session-real-boss-thread",
            "bound_thread_id": "codex-session-real-boss-thread",
            "target_thread_id": "codex-session-real-boss-thread",
            "metadata": {"source_workstation_id": "codex-session-real-boss-thread"},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source_workstation_id"] == "codex-session-real-boss-thread"
    assert data["metadata"]["source_workstation_id"] == "codex-session-real-boss-thread"

    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="YueSpeak Boss").one()
        assert seat.extra_data["source_workstation_id"] == "codex-session-real-boss-thread"
        assert seat.extra_data["bound_thread_id"] == "codex-session-real-boss-thread"
        assert seat.extra_data["target_thread_id"] == "codex-session-real-boss-thread"


def test_formal_npc_seats_cannot_share_one_bound_thread() -> None:
    """One real execution thread must not masquerade as multiple NPC seats."""
    owner_token, owner_user_id = issue_session_token(client)
    shared_thread = "codex-session-real-shared-thread"
    project = create_project(
        client,
        owner_token,
        name_prefix="Unique Formal Thread Binding",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": shared_thread,
                    "name": "Scanned Desktop Thread",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "metadata": {"source": "runner_thread_scan"},
                },
                {
                    "id": "qa-seat",
                    "name": "QA Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                    "source_workstation_id": shared_thread,
                    "metadata": {"source_workstation_id": shared_thread},
                },
                {
                    "id": "backend-seat",
                    "name": "Backend Seat",
                    "status": "active",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/backend-seat",
        headers=auth_headers(owner_token),
        json={
            "source_workstation_id": shared_thread,
            "bound_thread_id": shared_thread,
            "target_thread_id": shared_thread,
            "metadata": {"source_workstation_id": shared_thread},
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "THREAD_BINDING_CONFLICT"


def test_thread_workstation_occupancy_accepts_db_row_id_from_workbench() -> None:
    """The workbench renders row_id, so write actions must accept that id too."""
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Workbench Row Occupancy",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "platform-npc-6",
                    "name": "6号 Boss 总控",
                    "status": "idle",
                    "ai_provider_id": "codex",
                    "metadata": {"npc_identity_key": "platform-npc-6"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="platform-npc-6").one()
        row_id = seat.id

    occupy_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{row_id}/occupy",
        headers=auth_headers(owner_token),
        json={"force": False, "user_name": "Project Lead"},
    )
    assert occupy_response.status_code == 200, occupy_response.text
    assert occupy_response.json()["data"]["ok"] is True
    assert occupy_response.json()["data"]["occupancy"]["user_name"] == "Project Lead"

    release_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{row_id}/release",
        headers=auth_headers(owner_token),
    )
    assert release_response.status_code == 200, release_response.text
    assert release_response.json()["data"]["ok"] is True


def test_setting_logical_workstation_lead_assigns_unassigned_seat_to_that_workstation() -> None:
    """Selecting a lead should also make the lead a member of the logical workstation.

    Otherwise the UI can display "workstation lead: X" while the backend still
    treats X as unassigned, which breaks same/cross workstation routing.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Lead Assignment Sync",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "yuespeak-boss",
                    "name": "YueSpeak Boss",
                    "status": "idle",
                    "ai_provider_id": "codex",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    create_response = client.post(
        f"/api/projects/{project_id}/workstations",
        headers=auth_headers(owner_token),
        json={"name": "YueSpeak Boss / 产品与分工工位", "config_id": "yuespeak-boss-station"},
    )
    assert create_response.status_code == 200, create_response.text
    workstation_id = create_response.json()["data"]["id"]

    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="yuespeak-boss").one()
        assert seat.workstation_id is None
        seat_id = seat.id

    lead_response = client.post(
        f"/api/projects/{project_id}/workstations/{workstation_id}/lead",
        headers=auth_headers(owner_token),
        json={"seat_id": seat_id},
    )
    assert lead_response.status_code == 200, lead_response.text
    assert lead_response.json()["data"]["seat_count"] == 1

    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="yuespeak-boss").one()
        assert seat.workstation_id == workstation_id


def test_cross_workstation_agent_message_routes_to_target_lead_for_review() -> None:
    """Cross-workstation NPC messages must enter the target workstation lead first.

    Product rule: ordinary NPCs do not direct-message ordinary NPCs across
    logical workstations. The platform rewrites the recipient to the target
    workstation lead and marks it pending_review so the user can inspect the
    concrete body before it reaches the target team.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Cross Workstation Lead Routing",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "backend-worker",
                    "name": "Backend Worker",
                    "status": "active",
                    "workstation_id": "backend",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-worker",
                    "name": "Frontend Worker",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        frontend_lead = (
            db.query(ProjectThreadWorkstation)
            .filter_by(project_id=project_id, config_id="frontend-lead")
            .one()
        )
        db.add(
            ProjectWorkstation(
                project_id=project_id,
                config_id="frontend",
                name="Frontend Workstation",
                lead_seat_id=frontend_lead.id,
            )
        )
        db.add(
            ProjectWorkstation(
                project_id=project_id,
                config_id="backend",
                name="Backend Workstation",
            )
        )
        db.commit()
        frontend_lead_row_id = frontend_lead.id

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "title": "需要前端接 UI",
            "body": "请前端工位处理学生录音上传页面。",
            "sender_type": "agent",
            "sender_id": "backend-worker",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-worker",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["recipient_id"] == frontend_lead_row_id
    assert message["status"] == "pending_review"
    assert "跨工位：是" in message["body"]
    assert "经工位长 Frontend Lead 转交" in message["body"]
    assert "原始目标 NPC: Frontend Worker / frontend-worker" in message["body"]


def test_same_workstation_agent_message_stays_on_target_without_lead_rewrite() -> None:
    """Same-workstation dispatches should stay peer-to-peer and skip review by default.

    This locks the "project_id first, then same-workstation routing" rule for the
    specialist/professional surfaces: same workstation may collaborate directly,
    while only cross-workstation traffic escalates through lead + review.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Same Workstation Direct Routing",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-worker-a",
                    "name": "Frontend Worker A",
                    "status": "active",
                    "workstation_id": "frontend",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-worker-b",
                    "name": "Frontend Worker B",
                    "status": "active",
                    "workstation_id": "frontend",
                    "ai_provider_id": "codex",
                },
            ],
            "review_policy": {"default": "cross_workstation_only"},
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        frontend_lead = (
            db.query(ProjectThreadWorkstation)
            .filter_by(project_id=project_id, config_id="frontend-lead")
            .one()
        )
        db.add(
            ProjectWorkstation(
                project_id=project_id,
                config_id="frontend",
                name="Frontend Workstation",
                lead_seat_id=frontend_lead.id,
            )
        )
        db.commit()

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "title": "同工位 UI 联调",
            "body": "请直接联调专业工作台入口的前端状态显示。",
            "sender_type": "agent",
            "sender_id": "frontend-worker-a",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-worker-b",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["recipient_id"] == "frontend-worker-b"
    assert message["status"] == "queued"
    assert "跨工位：否" in message["body"]
    assert "审核：同工位免审" in message["body"]
    assert "project_default_cross_only" not in message["body"]
    assert "cross_workstation_only" not in message["body"]
    assert "经工位长" not in message["body"]


def test_project_scoped_agent_dispatch_rejects_session_alias_even_if_other_projects_share_it() -> None:
    """Agent routing must target formal seats, not session aliases shared by projects."""
    owner_token, owner_user_id = issue_session_token(client)
    shared_alias = "codex-session-shared-platform-thread"

    project_a = create_project(
        client,
        owner_token,
        name_prefix="Project Scoped Seat Resolution A",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "platform-npc-4",
                    "name": "4号 平台路由",
                    "status": "active",
                    "workstation_id": "platform-routing",
                    "ai_provider_id": "codex",
                    "source_workstation_id": shared_alias,
                    "metadata": {"source_workstation_id": shared_alias},
                }
            ],
        },
    )
    project_a_id = project_a["id"]
    add_project_member(client, project_a_id, owner_token, owner_user_id, role="owner", is_owner=True)

    project_b = create_project(
        client,
        owner_token,
        name_prefix="Project Scoped Seat Resolution B",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "yuespeak-boss",
                    "name": "YueSpeak Boss",
                    "status": "active",
                    "workstation_id": "yuespeak-planning",
                    "ai_provider_id": "codex",
                    "source_workstation_id": shared_alias,
                    "metadata": {"source_workstation_id": shared_alias},
                },
                {
                    "id": "platform-npc-6",
                    "name": "6号 Boss 总控",
                    "status": "active",
                    "workstation_id": "platform-planning",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_b_id = project_b["id"]
    add_project_member(client, project_b_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_b_id,
            "message_type": "comment_message",
            "title": "项目内 seat 解析隔离",
            "body": "请只在当前项目内解析同名 session 别名，不要串到历史验证项目。",
            "sender_type": "agent",
            "sender_id": "platform-npc-6",
            "recipient_type": "thread_workstation",
            "recipient_id": shared_alias,
            "status": "queued",
        },
    )
    assert response.status_code == 404, response.text
    error = response.json()["error"]
    assert error["code"] == "NPC_RECIPIENT_NOT_FOUND"
    assert project_a_id != project_b_id


def test_human_message_to_boss_is_not_rewritten_as_npc_cross_route() -> None:
    """User-to-Boss dialogue must reach Boss even when it mentions other teams.

    Boss is responsible for planning and deciding whether to route work. The
    platform should not keyword-route a human's planning prompt away from Boss.
    """
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Direct Dialogue",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend-lead",
                    "name": "Backend Lead",
                    "status": "active",
                    "workstation_id": "backend",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "[用户 → Boss NPC] 对话指令",
            "body": "请 Boss 制定方案，并给出下一步要分配给 Backend、Frontend、QA 的一句话任务。",
            "sender_type": "human",
            "sender_id": owner_user_id,
            "recipient_type": "thread_workstation",
            "recipient_id": "boss",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["sender_type"] == "human"
    assert message["recipient_id"] == "boss"
    assert message["status"] == "queued"
    assert "[路由]" not in message["body"]


def test_npc_pair_review_exemption_can_be_enabled_and_disabled() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="NPC Pair Review Exemption",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend-lead",
                    "name": "Backend Lead",
                    "status": "active",
                    "workstation_id": "backend",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "qa-lead",
                    "name": "QA Lead",
                    "status": "active",
                    "workstation_id": "qa",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    def create_dispatch(target_id: str, title: str = "Cross pair dispatch") -> dict:
        response = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "message_type": "requirement_dispatch",
                "title": title,
                "body": "请处理这条跨工位 NPC 派单。",
                "sender_type": "agent",
                "sender_id": "boss",
                "recipient_type": "thread_workstation",
                "recipient_id": target_id,
                "status": "queued",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    first = create_dispatch("backend-lead", "First needs review")
    assert first["status"] == "pending_review"

    approve_response = client.post(
        f"/api/collaboration/messages/{first['id']}/review/approve",
        headers=auth_headers(owner_token),
        json={"remember_pair_policy": "skip", "reason": "Trust Boss to Backend Lead"},
    )
    assert approve_response.status_code == 200, approve_response.text
    approved = approve_response.json()["data"]
    assert approved["status"] == "queued"
    assert approved["review_pair_policy"]["policy"] == "skip"

    second = create_dispatch("backend-lead", "Second skips review")
    assert second["status"] == "queued"
    assert "跨工位：是" in second["body"]
    assert "审核：按项目规则免审" in second["body"]
    assert "npc_pair:skip" not in second["body"]

    other_pair = create_dispatch("qa-lead", "Other pair still needs review")
    assert other_pair["status"] == "pending_review"

    with SessionLocal() as db:
        boss = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="boss").one()
        backend = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="backend-lead").one()
        boss_row_id = boss.id
        backend_row_id = backend.id

    disable_response = client.patch(
        f"/api/collaboration/projects/{project_id}/review-policy/npc-pairs",
        headers=auth_headers(owner_token),
        json={
            "upstream_seat_id": boss_row_id,
            "downstream_seat_id": backend_row_id,
            "policy": "inherit",
        },
    )
    assert disable_response.status_code == 200, disable_response.text
    assert disable_response.json()["data"]["policy"] == "inherit"

    third = create_dispatch("backend-lead", "Third needs review again")
    assert third["status"] == "pending_review"


def test_workstation_identity_can_create_peer_dispatch_without_human_token() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Peer Dispatch",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::frontend-lead": {"policy": "skip", "reason": "trusted autonomous pair"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers={"X-Workstation-Id": "boss"},
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Boss autonomous frontend task",
            "body": "请在不改变工作台结构的前提下检查待收口入口。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-lead",
            "status": "queued",
            "metadata": {"origin": "platform_peer_dispatches", "risk_level": "L1"},
        },
    )

    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["sender_type"] == "agent"
    assert message["sender_id"] == "boss"
    assert message["recipient_id"] == "frontend-lead"
    assert message["status"] == "queued"
    metadata = message.get("metadata") or message.get("extra_data") or {}
    assert metadata["actor_workstation_id"] == "boss"
    assert metadata["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert metadata["delegation_context"]["target_seat_id"] == "frontend-lead"


def test_workstation_peer_dispatch_inherits_human_delegator_from_source_message() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Workstation Peer Dispatch Delegator",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::frontend-lead": {"policy": "skip", "reason": "trusted autonomous pair"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    source_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "User asks Boss to coordinate",
            "body": "请 Boss 派 1 号复验数据工场。",
            "sender_type": "user",
            "sender_id": "lead@example.com",
            "recipient_type": "thread_workstation",
            "recipient_id": "boss",
            "status": "queued",
        },
    )
    assert source_response.status_code == 200, source_response.text
    source_message = source_response.json()["data"]

    response = client.post(
        "/api/collaboration/messages",
        headers={"X-Workstation-Id": "boss"},
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Boss autonomous frontend task",
            "body": "请检查数据工场中央工作面，不要改变 NPC 工作台结构。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-lead",
            "status": "queued",
            "metadata": {
                "origin": "platform_peer_dispatches",
                "risk_level": "L1",
                "source_message_id": source_message["id"],
            },
        },
    )

    assert response.status_code == 200, response.text
    metadata = response.json()["data"]["metadata"]
    assert metadata["delegated_by_user_id"] == owner_user_id
    assert metadata["delegation_context"]["delegated_by_user_id"] == owner_user_id
    assert metadata["delegation_context"]["source_message_id"] == source_message["id"]


def test_boundary_card_forces_pre_dispatch_human_review_even_for_exempt_pair() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boundary Card Gate",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "frontend",
                    "ai_provider_id": "codex",
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::frontend-lead": {"policy": "skip", "reason": "trusted pair"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "title": "边界卡：机器人开发平台薄片",
            "body": "只讨论目标、禁止触碰区域、验收方法；审批前不得启动实现。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-lead",
            "status": "queued",
            "metadata": {
                "payload_json": {
                    "card_kind": "boundary",
                    "title": "Boss 边界卡 + 派单前讨论闸口",
                    "summary": "审批前只允许讨论接口和验收，不允许执行。",
                    "items": [
                        {"label": "允许", "value": "消息内容区卡片、轻量元数据"},
                        {"label": "禁止", "value": "改 NPC 工作台布局、碰 YueSpeak"},
                    ],
                    "actions": [{"label": "审批后", "value": "再派正式实现"}],
                }
            },
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "pending_review"
    assert message["metadata"]["pre_dispatch_gate"] is True
    assert message["metadata"]["requires_human_review"] is True
    assert message["metadata"]["gate_policy"] == "boundary_card_before_dispatch"
    assert message["metadata"]["payload_json"]["card_kind"] == "boundary"


def test_message_list_repairs_stale_exempt_review_message() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Stale Exempt Review Repair",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend-lead",
                    "name": "Backend Lead",
                    "status": "active",
                    "workstation_id": "backend",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        stale = CollaborationMessage(
            project_id=project_id,
            message_type="requirement_dispatch",
            title="Stale exempt review",
            body="请处理这条历史派单。\n\n[路由] 跨工位：是；审核：免（来源：npc_pair:skip）",
            sender_type="agent",
            sender_id="boss",
            recipient_type="thread_workstation",
            recipient_id="backend-lead",
            status="pending_review",
        )
        db.add(stale)
        db.commit()
        stale_id = stale.id

    response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "status": "pending_review"},
    )
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["data"]}
    assert stale_id not in ids

    with SessionLocal() as db:
        repaired = db.get(CollaborationMessage, stale_id)
        assert repaired is not None
        assert repaired.status == "queued"


def test_hardware_risk_forces_review_even_when_npc_pair_is_exempt() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Hardware Risk Review Override",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Robot Boss",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "hardware-lead",
                    "name": "Hardware Lead",
                    "status": "active",
                    "workstation_id": "hardware",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    with SessionLocal() as db:
        boss = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="boss").one()
        hardware = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="hardware-lead").one()
        boss_row_id = boss.id
        hardware_row_id = hardware.id

    exempt_response = client.patch(
        f"/api/collaboration/projects/{project_id}/review-policy/npc-pairs",
        headers=auth_headers(owner_token),
        json={
            "upstream_seat_id": boss_row_id,
            "downstream_seat_id": hardware_row_id,
            "policy": "skip",
            "reason": "Routine robot planning can skip review.",
        },
    )
    assert exempt_response.status_code == 200, exempt_response.text

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Robot arm power-on test",
            "body": "请硬件工位准备机械臂上电，并在 ROS 实机环境执行电机校准。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "hardware-lead",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "pending_review"
    assert "审核：需要人工确认" in message["body"]
    assert "hardware_risk" not in message["body"]
    assert "force" not in message["body"]
    assert "硬件风险" in message["body"]


def test_readonly_robotics_work_surface_does_not_force_hardware_review() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Readonly Robotics Review",
        collaboration_config={
            "review_policy": {"default": "skip"},
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Robot Boss",
                    "status": "active",
                    "workstation_id": "robotics",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "robotics-ui",
                    "name": "Robotics UI",
                    "status": "active",
                    "workstation_id": "robotics",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Readonly robotics work surface",
            "body": (
                "请继续做机器人现场只读工作面：topic、diagnostics、logs、URDF、TF、rosbag、波形、"
                "电机参数卡、PID/FOC 调参建议和强审动作卡。真实硬件、部署、运动、firmware、"
                "ROS publish/service/action/write 参数必须单独做强审动作卡，不得自动执行。"
            ),
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "robotics-ui",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "queued"
    assert "审核：同工位免审" in message["body"]
    assert "硬件风险" not in message["body"]


def test_robotics_fullchain_browser_validation_does_not_force_hardware_review() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Robotics Browser Validation",
        collaboration_config={
            "review_policy": {"default": "skip"},
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "qa",
                    "name": "QA NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Professional surfaces fullchain 验收深化",
            "body": (
                "请只跑 CDP/DOM/截图验收和点击链验收，覆盖 datasets、ai-lab、robotics、observability。"
                "检查机器人现场页面只读工作面、强审动作卡和回 NPC 工作台链路；不改硬件，不执行 ROS publish/service/action，"
                "不部署、不运动、不写参数。"
            ),
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "qa",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "queued"
    assert "审核：同工位免审" in message["body"]
    assert "硬件风险" not in message["body"]


def test_npc_workbench_structure_fullchain_recheck_does_not_force_hardware_review() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Workbench Structure Fullchain Recheck",
        collaboration_config={
            "review_policy": {"default": "skip"},
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "qa",
                    "name": "QA NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "NPC4 fullchain 与五工作台结构复验",
            "body": (
                "复跑 fullchain 和五工作台结构契约，确认 NPC 工作台对话框结构未被破坏，"
                "确认 datasets、ai-lab、robotics、observability 等专业工作台无内部词。"
            ),
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "qa",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "queued"
    assert "审核：同工位免审" in message["body"]
    assert "硬件风险" not in message["body"]


def test_peer_dispatch_with_forbidden_ros_write_boundary_does_not_force_hardware_review() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Peer Dispatch Forbidden ROS Boundary",
        collaboration_config={
            "review_policy": {"default": "cross_workstation_only"},
            "thread_workstations": [
                {
                    "id": "frontend",
                    "name": "Frontend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers={"x-workstation-id": "frontend"},
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "补字段契约",
            "body": (
                "请补数据工场 manifest 字段契约；不要碰真实硬件/部署/运动/firmware/ROS 写操作，"
                "只做后端字段聚合和说明。"
            ),
            "sender_type": "agent",
            "sender_id": "frontend",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "queued"
    assert "审核：同工位免审" in message["body"]
    assert "硬件风险" not in message["body"]


def test_runner_desktop_recovery_with_ros_guardrail_does_not_force_hardware_review() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Runner Desktop Recovery Guardrail",
        collaboration_config={
            "review_policy": {"default": "cross_workstation_only"},
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "runner-sync",
                    "name": "Runner Sync NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers={"x-workstation-id": "boss"},
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Runner 与桌面同步抗干扰恢复",
            "body": (
                "只做平台桌面同步与执行线程恢复验证，不碰真实硬件。验证电脑重启、桌面误点、"
                "待收口、重新同步、延长等待、自动重试是否用户可理解；真实硬件、部署、运动、"
                "firmware、ROS publish/service/action/write 参数仍强审，不得执行。"
            ),
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "runner-sync",
            "status": "queued",
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["status"] == "queued"
    assert "审核：同工位免审" in message["body"]
    assert "硬件风险" not in message["body"]


def test_npc_peer_dispatch_gets_project_delegation_context_and_audit() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Peer Delegation Context",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::backend": {"policy": "skip", "reason": "trusted same-project implementation"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Continue delegated implementation",
            "body": "请继续实现免审自主推进的后端薄片。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend",
            "status": "queued",
            "metadata": {
                "origin": "platform_peer_dispatches",
                "source": "npc_final_reply",
                "source_message_id": "boss-final-1",
                "payload_json": {
                    "card_kind": "task",
                    "risk_level": "L1",
                    "title": "Delegated implementation",
                },
            },
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["data"]
    assert message["sender_type"] == "agent"
    assert message["sender_id"] == "boss"
    assert message["recipient_id"] == "backend"
    assert message["status"] == "queued"

    metadata = message["metadata"]
    context = metadata["delegation_context"]
    assert context["kind"] == "project_delegation"
    assert context["project_id"] == project_id
    assert context["delegated_by_user_id"] == owner_user_id
    assert context["delegated_via_seat_id"] == "boss"
    assert context["grantee_id"] == "boss"
    assert context["target_seat_id"] == "backend"
    assert "collaboration.peer_dispatch.create" in context["scope"]
    assert context["max_risk_level"] == "L1"
    assert context["source_message_id"] == "boss-final-1"
    assert metadata["delegated_by_user_id"] == owner_user_id
    assert metadata["delegated_via_seat_id"] == "boss"
    assert metadata["delegation_status"] == "active"

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.project_id == project_id,
                AuditLog.resource_id == message["id"],
                AuditLog.action == "collaboration.delegation.peer_dispatch.created",
            )
            .one_or_none()
        )
        assert audit is not None
        assert audit.actor_type == "agent"
        assert audit.actor_id == "boss"
        assert audit.after["delegation_context"]["target_seat_id"] == "backend"


def test_peer_dispatch_rejects_historical_seat_alias_and_writes_block_reason() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Formal Seat Routing",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "planning",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-lead",
                    "name": "Frontend Lead",
                    "status": "active",
                    "workstation_id": "frontend",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Alias should fail",
            "body": "Use historical names and expect a block.",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "Frontend Lead",
            "status": "queued",
        },
    )
    assert response.status_code == 404, response.text
    payload = response.json()["error"]
    assert payload["code"] == "NPC_RECIPIENT_NOT_FOUND"
    assert payload["details"]["blocked_reason"] == "NPC_RECIPIENT_NOT_FOUND"

    audit_response = client.get(
        "/api/audit",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "action": "dispatch.blocked_history_alias"},
    )
    assert audit_response.status_code == 200, audit_response.text
    logs = audit_response.json()["data"]
    assert len(logs) >= 1
    assert logs[0]["success"] is False
    assert logs[0]["after"]["blocked_reason"] == "NPC_RECIPIENT_NOT_FOUND"


def test_seat_queue_and_receipts_require_formal_seat_not_alias() -> None:
    owner_token, project_id, workstation_id, agent_alias = _project_with_workstation_alias("Formal Seat Queue")

    queue_response = client.get(
        f"/api/seats/{agent_alias}/queues",
        headers=auth_headers(owner_token),
        params={"project_id": project_id},
    )
    assert queue_response.status_code == 404
    assert queue_response.json()["error"]["code"] == "SEAT_NOT_FOUND"

    receipt_list_response = client.get(
        f"/api/receipts/by-seat/{agent_alias}",
        headers=auth_headers(owner_token),
        params={"project_id": project_id},
    )
    assert receipt_list_response.status_code == 404
    assert receipt_list_response.json()["error"]["code"] == "SEAT_NOT_FOUND"

    queue_by_formal_seat = client.get(
        f"/api/seats/{workstation_id}/queues",
        headers=auth_headers(owner_token),
        params={"project_id": project_id},
    )
    assert queue_by_formal_seat.status_code == 200, queue_by_formal_seat.text


def test_receipts_and_professional_view_surface_authoritative_seat_fields() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Receipt Authority Surface",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "ai_provider_id": "codex",
                },
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    task_response = client.post(
        "/api/tasks",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "title": "Authority field aggregation",
            "description": "Keep seat authority explicit across receipts and professional view.",
            "status": "ready",
        },
    )
    assert task_response.status_code == 200, task_response.text
    task_id = task_response.json()["data"]["id"]

    requirement_response = client.post(
        "/api/requirements",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task_id,
            "title": "Backend follow-up",
            "detail": "Return a progress receipt.",
            "from_agent": "boss",
            "to_agent": "backend",
            "target_seat_id": "backend",
            "context_summary": "Authority fields should stay explicit.",
            "expected_output": "Progress receipt.",
        },
    )
    assert requirement_response.status_code == 200, requirement_response.text
    requirement_id = requirement_response.json()["data"]["id"]

    receipt_create = client.post(
        "/api/receipts",
        headers=auth_headers(owner_token),
        json={
            "parent_requirement_id": requirement_id,
            "receipt_kind": "progress",
            "sender_seat_id": "backend",
            "recipient_seat_id": "boss",
            "body": "Backend progress receipt.",
        },
    )
    assert receipt_create.status_code == 200, receipt_create.text
    created_receipt = receipt_create.json()["data"]
    assert created_receipt["authoritative_seat_id"]
    assert created_receipt["authoritative_seat_ref"] == "backend"
    assert created_receipt["authoritative_target_seat_id"]
    assert created_receipt["historical_alias_non_authoritative"] is False

    receipt_list = client.get(
        f"/api/receipts/by-requirement/{requirement_id}",
        headers=auth_headers(owner_token),
    )
    assert receipt_list.status_code == 200, receipt_list.text
    listed_receipt = receipt_list.json()["data"][0]
    assert listed_receipt["authoritative_seat_ref"] == "backend"
    assert listed_receipt["historical_alias_non_authoritative"] is False

    view_response = client.get(
        f"/api/tasks/{task_id}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    data = view_response.json()["data"]
    receipt_link = next(item for item in data["receipts"] if item["message_id"] == created_receipt["id"])
    assert receipt_link["authoritative_seat_ref"] == "backend"
    assert receipt_link["historical_alias_non_authoritative"] is False


def test_artifact_index_and_delegation_context_stay_on_formal_seat_when_alias_metadata_exists() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Formal Seat Artifact Index",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-boss"},
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-backend"},
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::backend": {"policy": "skip", "reason": "trusted same-project implementation"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    from tests.helpers import create_task

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Formal seat receipt index",
        description="Keep receipt index on the project task and formal seat.",
        status="ready",
    )

    dispatch_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_command",
            "title": "Delegated implementation",
            "body": "请继续实现 formal seat 优先。",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend",
            "status": "queued",
            "metadata": {
                "origin": "platform_peer_dispatches",
                "source_thread_id": "codex-session-legacy-dispatch",
            },
        },
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch_message = dispatch_response.json()["data"]
    assert dispatch_message["recipient_id"] == "backend"
    assert dispatch_message["metadata"]["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert dispatch_message["metadata"]["delegation_context"]["target_seat_id"] == "backend"
    assert dispatch_message["metadata"]["authoritative_sender_seat_id"] == "boss"
    assert dispatch_message["metadata"]["authoritative_target_seat_id"] == "backend"

    with SessionLocal() as db:
        command_row = db.get(CollaborationMessage, dispatch_message["id"])
        assert command_row is not None
        command_row.status = "in_progress"
        db.add(command_row)
        from app.db.models.task import Task

        task_row = db.get(Task, task["id"])
        assert task_row is not None
        task_row.status = "running"
        db.add(task_row)
        db.commit()

    result_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_result",
            "title": "Backend result",
            "body": "已完成 formal seat 路由修复。",
            "sender_type": "agent",
            "sender_id": "backend",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "source_message_id": dispatch_message["id"],
                "source_thread_id": "codex-session-legacy-backend",
                "evidence_artifacts": [
                    {"label": "Formal seat report", "path": "artifacts/tests/formal-seat/report.md"}
                ],
            },
        },
    )
    assert result_response.status_code == 200, result_response.text
    result_message = result_response.json()["data"]
    assert result_message["dispatch_id"] is None

    artifact_index_response = client.get(
        f"/api/tasks/{task['id']}/artifact-index",
        headers=auth_headers(owner_token),
    )
    assert artifact_index_response.status_code == 200, artifact_index_response.text
    artifact_index = artifact_index_response.json()["data"]
    artifact = next(item for item in artifact_index if item["path"] == "artifacts/tests/formal-seat/report.md")
    assert artifact["task_id"] == task["id"]
    assert artifact["source_message_id"] == result_message["id"]
    assert artifact["sender_id"] == "backend"
    assert artifact["authoritative_seat_id"] == "backend"


def test_artifact_index_filters_non_project_paths_even_if_legacy_metadata_contains_them() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Artifact Path Governance",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-backend"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    from tests.helpers import create_task

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Artifact path filter",
        description="Only project artifact paths should survive indexing.",
        status="running",
    )

    result_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_result",
            "title": "Backend result",
            "body": "done",
            "sender_type": "agent",
            "sender_id": "backend",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "authoritative_seat_id": "backend",
                "authoritative_seat_ref": "backend",
                "evidence_artifacts": [
                    {"label": "good", "path": "artifacts/tests/formal-seat/report.md"},
                    {"label": "bad-abs", "path": "C:/temp/other-project/report.md"},
                    {"label": "bad-traversal", "path": "artifacts/../../secret.txt"},
                ],
            },
        },
    )
    assert result_response.status_code == 200, result_response.text

    artifact_index_response = client.get(
        f"/api/tasks/{task['id']}/artifact-index",
        headers=auth_headers(owner_token),
    )
    assert artifact_index_response.status_code == 200, artifact_index_response.text
    artifact_index = artifact_index_response.json()["data"]
    paths = {item["path"] for item in artifact_index}
    assert "artifacts/tests/formal-seat/report.md" in paths
    assert "C:/temp/other-project/report.md" not in paths
    assert "artifacts/../../secret.txt" not in paths


def test_cross_project_source_message_id_is_rejected_for_current_receipt_chain() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    source_project = create_project(client, owner_token, name_prefix="Source Project")
    target_project = create_project(client, owner_token, name_prefix="Target Project")
    source_project_id = source_project["id"]
    target_project_id = target_project["id"]
    add_project_member(client, source_project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    add_project_member(client, target_project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    source_message_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": source_project_id,
            "message_type": "comment_message",
            "title": "Old chain",
            "body": "legacy source message",
            "recipient_type": "project",
            "recipient_id": source_project_id,
            "status": "open",
        },
    )
    assert source_message_response.status_code == 200, source_message_response.text
    source_message_id = source_message_response.json()["data"]["id"]

    target_result_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": target_project_id,
            "message_type": "agent_result",
            "title": "Should fail",
            "body": "done",
            "sender_type": "agent",
            "sender_id": "backend",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "authoritative_seat_id": "backend",
                "authoritative_seat_ref": "backend",
                "source_message_id": source_message_id,
            },
        },
    )
    assert target_result_response.status_code == 409, target_result_response.text
    assert target_result_response.json()["error"]["code"] == "SOURCE_MESSAGE_PROJECT_MISMATCH"


def test_workstation_ack_progress_complete_keep_formal_seat_and_delegation_context() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Formal Seat Receipt Authority",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss",
                    "name": "Boss NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-boss"},
                },
                {
                    "id": "backend",
                    "name": "Backend NPC",
                    "status": "active",
                    "workstation_id": "platform",
                    "ai_provider_id": "codex",
                    "metadata": {"source_thread_id": "codex-session-old-backend"},
                },
            ],
            "review_policy": {
                "npc_pair_rules": {
                    "boss::backend": {"policy": "skip", "reason": "trusted same-project implementation"}
                }
            },
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    dispatch_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_command",
            "title": "Receipt authority check",
            "body": "Please continue using the formal seat only.",
            "sender_type": "agent",
            "sender_id": "boss",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend",
            "status": "queued",
            "metadata": {
                "origin": "platform_peer_dispatches",
                "source_thread_id": "codex-session-legacy-dispatch",
            },
        },
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    command = dispatch_response.json()["data"]

    ack_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/backend/messages/{command['id']}/ack",
        headers={"X-Workstation-Id": "backend"},
        json={"note": "Accepted."},
    )
    assert ack_response.status_code == 200, ack_response.text
    ack = ack_response.json()["data"]["receipt"]
    assert ack["metadata"]["authoritative_seat_id"] == "backend"
    assert ack["metadata"]["authoritative_seat_ref"] == "backend"
    assert ack["metadata"]["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert ack["metadata"]["delegation_context"]["target_seat_id"] == "backend"

    progress_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/backend/messages/{command['id']}/progress",
        headers={"X-Workstation-Id": "backend"},
        json={"note": "Still working.", "state": "implementation"},
    )
    assert progress_response.status_code == 200, progress_response.text
    progress = progress_response.json()["data"]["receipt"]
    assert progress["metadata"]["authoritative_seat_id"] == "backend"
    assert progress["metadata"]["authoritative_seat_ref"] == "backend"
    assert progress["metadata"]["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert progress["metadata"]["delegation_context"]["target_seat_id"] == "backend"

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/backend/messages/{command['id']}/complete",
        headers={"X-Workstation-Id": "backend"},
        json={"result_status": "completed", "note": "Done."},
    )
    assert complete_response.status_code == 200, complete_response.text
    completed = complete_response.json()["data"]["receipt"]
    assert completed["project_id"] == project_id
    assert completed["metadata"]["authoritative_seat_id"] == "backend"
    assert completed["metadata"]["authoritative_seat_ref"] == "backend"
    assert completed["metadata"]["delegation_context"]["delegated_via_seat_id"] == "boss"
    assert completed["metadata"]["delegation_context"]["target_seat_id"] == "backend"


def test_workstation_read_exposes_authoritative_formal_seat_and_non_authoritative_aliases() -> None:
    owner_token, project_id, workstation_id, _agent_alias = _project_with_workstation_alias("Formal Seat Display")

    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}",
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200, response.text
    seat = response.json()["data"]
    assert seat["authoritative_seat_id"] == seat["row_id"]
    assert seat["authoritative_seat_ref"] == workstation_id
    assert not (seat.get("historical_aliases") or [])


def test_workstation_detail_allows_historical_alias_read_but_not_stateful_update() -> None:
    owner_token, project_id, workstation_id, _agent_alias = _project_with_workstation_alias("Alias Read Only")

    read_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/codex-session-alias",
        headers=auth_headers(owner_token),
    )
    assert read_response.status_code == 200, read_response.text
    seat = read_response.json()["data"]
    assert seat["authoritative_seat_id"] == seat["row_id"]
    assert seat["authoritative_seat_ref"] == workstation_id
    assert not (seat.get("historical_aliases") or [])

    update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/codex-session-alias",
        headers=auth_headers(owner_token),
        json={"notes": "should not update through alias"},
    )
    assert update_response.status_code == 404
    assert update_response.json()["error"]["code"] == "NOT_FOUND"


def test_workstation_inbox_can_complete_legacy_comment_message_dispatch() -> None:
    """Older workbench NPC-to-NPC dispatches used comment_message.

    They still appear in the target NPC queue, so the target NPC must be able to
    complete them and write a receipt instead of getting stuck forever.
    """
    owner_token, project_id, workstation_id = _project_with_workstation("Legacy Comment Dispatch")
    create_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "comment_message",
            "title": "Legacy workbench dispatch",
            "body": "Please handle this legacy workbench dispatch.",
            "sender_type": "agent",
            "sender_id": "boss-seat",
            "recipient_type": "thread_workstation",
            "recipient_id": workstation_id,
            "status": "queued",
        },
    )
    assert create_response.status_code == 200, create_response.text
    message = create_response.json()["data"]

    complete_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages/{message['id']}/complete",
        headers=auth_headers(owner_token),
        json={"result_status": "completed", "note": "Legacy dispatch completed."},
    )
    assert complete_response.status_code == 200, complete_response.text
    data = complete_response.json()["data"]
    assert data["command"]["status"] == "completed"
    assert data["receipt"]["message_type"] == "agent_result"
    assert data["receipt"]["recipient_id"]


def test_codex_desktop_reply_sync_reads_final_answer_for_matching_message(tmp_path) -> None:
    adapter = _load_platform_workstation_adapter()
    previous_codex_home = os.environ.get("CODEX_HOME")
    codex_home = tmp_path / "codex-home"
    session_id = "019e153e-8202-7f51-bd36-13be006e801b"
    session_file = codex_home / "sessions" / "2026" / "05" / "11" / f"rollout-test-{session_id}.jsonl"
    session_file.parent.mkdir(parents=True)
    records = [
        {
            "timestamp": "2026-05-11T04:14:38.872Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "# Other\n\n- message_id: `other-message`\n\nIgnore this dispatch.",
            },
        },
        {
            "timestamp": "2026-05-11T04:14:39.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "Wrong dispatch result."}],
            },
        },
        {
            "timestamp": "2026-05-11T04:15:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "# Target\n\n- message_id: `platform-message-1`\n\nPlease handle it.",
            },
        },
        {
            "timestamp": "2026-05-11T04:15:04.000Z",
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "桌面最终回执：已完成目标派单。",
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records), encoding="utf-8")

    try:
        os.environ["CODEX_HOME"] = str(codex_home)
        reply = adapter._find_codex_desktop_reply(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-1",
        )
    finally:
        if previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_codex_home

    assert reply is not None
    assert reply["text"] == "桌面最终回执：已完成目标派单。"
    assert reply["session_file"] == str(session_file)


def test_codex_desktop_reply_sync_ignores_commentary_until_final_answer(tmp_path) -> None:
    adapter = _load_platform_workstation_adapter()
    previous_codex_home = os.environ.get("CODEX_HOME")
    codex_home = tmp_path / "codex-home"
    session_id = "019e153e-8202-7f51-bd36-13be006e801b"
    session_file = codex_home / "sessions" / "2026" / "05" / "11" / f"rollout-test-{session_id}.jsonl"
    session_file.parent.mkdir(parents=True)
    records = [
        {
            "timestamp": "2026-05-11T04:15:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "# Target\n\n- message_id: `platform-message-1`\n\nPlease handle it.",
            },
        },
        {
            "timestamp": "2026-05-11T04:15:01.000Z",
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "我先读取项目资料，这还不是最终回执。",
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records), encoding="utf-8")

    try:
        os.environ["CODEX_HOME"] = str(codex_home)
        reply = adapter._find_codex_desktop_reply(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-1",
        )
    finally:
        if previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_codex_home

    assert reply is None


def test_codex_desktop_prompt_seen_detects_existing_platform_dispatch(tmp_path) -> None:
    adapter = _load_platform_workstation_adapter()
    previous_codex_home = os.environ.get("CODEX_HOME")
    codex_home = tmp_path / "codex-home"
    session_id = "019e153e-8202-7f51-bd36-13be006e801b"
    session_file = codex_home / "sessions" / "2026" / "05" / "11" / f"rollout-test-{session_id}.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in [
                {
                    "timestamp": "2026-05-11T04:15:00.000Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "# Target\n\n- message_id: `platform-message-1`\n\nPlease handle it.",
                    },
                },
                {
                    "timestamp": "2026-05-11T04:15:04.000Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "phase": "commentary",
                        "message": "处理中。",
                    },
                },
            ]
        ),
        encoding="utf-8",
    )

    try:
        os.environ["CODEX_HOME"] = str(codex_home)
        seen = adapter._codex_desktop_prompt_seen(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-1",
        )
        missing = adapter._codex_desktop_prompt_seen(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-2",
        )
    finally:
        if previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_codex_home

        assert seen is not None
        assert seen["session_file"] == str(session_file)
        assert missing is None


def test_codex_desktop_prompt_seen_waits_for_matching_dispatch(tmp_path) -> None:
    adapter = _load_platform_workstation_adapter()
    previous_codex_home = os.environ.get("CODEX_HOME")
    codex_home = tmp_path / "codex-home"
    session_id = "019e153e-8202-7f51-bd36-13be006e801b"
    session_file = codex_home / "sessions" / "2026" / "05" / "11" / f"rollout-test-{session_id}.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-11T04:15:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "# Target\n\n- message_id: `platform-message-1`\n\nPlease handle it.",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        os.environ["CODEX_HOME"] = str(codex_home)
        seen = adapter._wait_for_codex_desktop_prompt_seen(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-1",
            timeout_seconds=1,
            poll_seconds=0.1,
        )
        missing = adapter._wait_for_codex_desktop_prompt_seen(
            session_id=f"codex-session-{session_id}",
            message_id="platform-message-2",
            timeout_seconds=0,
            poll_seconds=0.1,
        )
    finally:
        if previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_codex_home

    assert seen is not None
    assert seen["session_file"] == str(session_file)
    assert missing is None


def test_codex_desktop_executor_prompt_keeps_platform_message_id() -> None:
    adapter = _load_platform_workstation_adapter()

    prompt = adapter._extract_executor_prompt(
        "\n".join(
            [
                "# Target",
                "",
                "## Platform Envelope",
                "- project_id: `project-1`",
                "- workstation_id: `boss-seat`",
                "- message_id: `platform-message-1`",
                "",
                "## User Instruction",
                "请只回复 Validated。",
            ]
        )
    )

    assert "message_id: `platform-message-1`" in prompt
    assert "## Platform Envelope" not in prompt
    assert "请只回复 Validated。" in prompt


def test_executor_prompt_includes_peer_dispatch_fallback_for_autonomous_collaboration() -> None:
    adapter = _load_platform_workstation_adapter()

    prompt = adapter._extract_executor_prompt(
        "\n".join(
            [
                "# Boss 自主组织协作",
                "",
                "## Platform Envelope",
                "- project_id: `proj_ai_collab`",
                "- workstation_id: `platform-npc-6`",
                "- seat_id (your NPC identity for docs): `platform-npc-6`",
                "- message_id: `platform-message-1`",
                "",
                "## User Instruction",
                "请你自己组织 1、2、5 号 NPC 讨论机器人开发平台架构，不要让我手动派单。",
            ]
        )
    )

    assert "platform-peer-dispatches" in prompt
    assert "工具不可用" in prompt
    assert "platform-npc-1" in prompt
    assert "不能只写建议名单" in prompt


def test_adapter_peer_dispatch_inherits_source_and_root_message_id() -> None:
    adapter = _load_platform_workstation_adapter()
    captured: dict[str, object] = {}

    def fake_json_request(method: str, url: str, *, headers=None, payload=None):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {
            "data": {
                "id": "child-message-1",
                "recipient_id": "platform-npc-2",
                "status": "queued",
            }
        }

    with patch.object(adapter, "_json_request", side_effect=fake_json_request):
        result = adapter._create_peer_dispatch(
            base="http://127.0.0.1:8011",
            project_id="proj_ai_collab",
            sender_seat_id="platform-npc-6",
            headers={"Authorization": "Bearer test"},
            payload={
                "seat_id": "platform-npc-2",
                "title": "复验 AI 实验室中央工作面",
                "body": "请从训练工程师视角复验 run board，不要堆文本。",
                "risk_level": "L1",
            },
            source_message_id="boss-message-1",
            root_message_id="user-root-1",
        )

    assert result and result["id"] == "child-message-1"
    message_payload = captured["payload"]
    assert isinstance(message_payload, dict)
    metadata = message_payload["metadata"]
    assert metadata["source_message_id"] == "boss-message-1"
    assert metadata["root_message_id"] == "user-root-1"
    assert metadata["source_agent_id"] == "platform-npc-6"


def test_adapter_child_dispatch_root_prefers_existing_chain_context() -> None:
    adapter = _load_platform_workstation_adapter()

    root = adapter._root_message_id_for_child_dispatch(
        {
            "id": "boss-message-1",
            "metadata": {
                "source_message_id": "user-command-1",
                "delegation_context": {"source_message_id": "user-root-from-context"},
            },
        }
    )

    assert root == "user-command-1"
    assert adapter._root_message_id_for_child_dispatch({"id": "boss-message-1"}) == "boss-message-1"


def test_adapter_message_id_recovery_queries_all_statuses_by_default() -> None:
    adapter = _load_platform_workstation_adapter()

    url = adapter._workstation_inbox_url(
        "http://127.0.0.1:8011",
        "project-1",
        "boss-seat",
        limit=5,
        message_id="platform-message-1",
    )
    explicit_url = adapter._workstation_inbox_url(
        "http://127.0.0.1:8011",
        "project-1",
        "boss-seat",
        limit=5,
        status="queued",
        message_id="platform-message-1",
    )

    assert url.endswith("/inbox?limit=5&status=all")
    assert explicit_url.endswith("/inbox?limit=5&status=queued")


def test_inbox_rejects_mismatched_decoded_workstation_id() -> None:
    """When the percent-encoded header decodes to a different workstation than the
    URL path, auth must still fail."""
    from urllib.parse import quote

    owner_token, owner_user_id = issue_session_token(client)
    workstation_id = "前端工位"
    other_id = "执行工位"
    project = create_project(
        client,
        owner_token,
        name_prefix="Non-ASCII WS Mismatch",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": workstation_id,
                    "status": "active",
                    "ai_provider_id": "claude",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    encoded_path_id = quote(workstation_id, safe="")
    response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{encoded_path_id}/inbox",
        headers={
            "X-Workstation-Id": quote(other_id, safe=""),
            "X-Workstation-Id-Encoding": "percent",
        },
    )
    assert response.status_code == 403, response.text
