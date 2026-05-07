from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


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

    closed_inbox_response = client.get(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/inbox",
        headers={"X-Workstation-Id": workstation_id},
    )
    assert closed_inbox_response.status_code == 200
    assert all(item["id"] != command["id"] for item in closed_inbox_response.json()["data"])


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
