from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectThreadWorkstation, ProjectWorkstation
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
    project = create_project(
        client,
        owner_token,
        name_prefix=prefix,
        collaboration_config={
            "thread_workstations": [
                {
                    "id": workstation_id,
                    "name": "Claude Writer",
                    "status": "active",
                    "ai_provider_id": "claude",
                    "responsibility": "write final text after another AI gathers material",
                    "metadata": {"source_kind": "manual_user_entry"},
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    return owner_token, project_id, workstation_id


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
    assert data["delivery_mode"] == "codex_app_server"
    assert data["delivery_label"] == "Codex session append (not Desktop live)"
    assert data["desktop_thread_url"] == "codex://threads/019e0d07-85d5-7d92-b9da-69cc2e35f451"
    assert data["desktop_visible"] is False
    assert data["desktop_bridge_connected"] is False
    assert "该电脑 Runner 启动独立 Codex app-server" in data["delivery_warning"]
    assert "不是当前已打开 Codex Desktop 窗口的实时输入通道" in data["delivery_warning"]


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
    assert "Runner 上报检测到 Codex Desktop 进程" in data["delivery_warning"]


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
    assert data["delivery_label"] == "Codex Desktop UI automation"
    assert "普通用户消息发送" in data["delivery_warning"]


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
    assert data["delivery_label"] == "Codex Desktop UI automation"
    assert data["executor_cwd"] == "D:/english_a_agent"


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
                    "workstation_id": "frontend",
                    "ai_provider_id": "codex",
                },
                {
                    "id": "frontend-worker",
                    "name": "Frontend Worker",
                    "status": "active",
                    "workstation_id": "frontend",
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
    assert "来源：npc_pair:skip" in second["body"]

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
    assert "来源：hardware_risk:force" in message["body"]
    assert "硬件风险" in message["body"]


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
