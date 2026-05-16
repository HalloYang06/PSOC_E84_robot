from __future__ import annotations

from fastapi.testclient import TestClient
from pathlib import Path
from uuid import uuid4

from app.main import app
from tests.helpers import auth_headers, create_project, create_task, issue_session_token


client = TestClient(app)


def test_task_professional_view_aggregates_dispatch_messages_artifacts_and_audit() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    runner_register = client.post(
        "/api/runners/register",
        json={
            "runner_id": "runner-pro-view",
            "runner_name": "Professional View Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert runner_register.status_code == 200
    project = create_project(client, owner_token, name_prefix="Professional View")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-pro-view",
                        "label": "电脑专业视图",
                        "status": "online",
                        "runner_id": "runner-pro-view",
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
                        "id": "ws-pro-view",
                        "name": "专业视图工位",
                        "agent_id": "agent-pro-view",
                        "computer_node_id": "pc-pro-view",
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
        title="Professional view task",
        description="Aggregate professional view signals.",
        status="ready",
        assignee_agent_id=None,
    )

    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-pro-view", "notes": "open professional view"},
    )
    assert dispatch_response.status_code == 200
    dispatch = dispatch_response.json()["data"]

    command_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "task_id": task["id"], "message_type": "runner_command", "limit": 10},
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"][0]

    ack_response = client.post(
        f"/api/runners/runner-pro-view/messages/{command['id']}/ack",
        headers={"X-Runner-Id": "runner-pro-view"},
        json={"note": "runner accepted professional view task"},
    )
    assert ack_response.status_code == 200

    result_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "dispatch_id": dispatch["id"],
            "message_type": "agent_result",
            "title": "专业视图结果",
            "body": "专业视图薄片已准备。",
            "sender_type": "agent",
            "sender_id": "ws-pro-view",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "source_message_id": command["id"],
                "payload_json": {
                    "card_kind": "specialist_summary",
                    "kind": "professional_view",
                    "domain": "proj_ai_collab",
                },
                "evidence_artifacts": [
                    {"label": "执行日志", "path": "artifacts/tests/pro-view/stdout.log"},
                    {"label": "结果摘要", "path": "artifacts/tests/pro-view/summary.md"},
                ],
            },
        },
    )
    assert result_message.status_code == 200

    view_response = client.get(
        f"/api/tasks/{task['id']}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    data = view_response.json()["data"]

    assert data["task"]["id"] == task["id"]
    assert data["summary"]["dispatch_count"] == 1
    assert data["summary"]["message_count"] >= 2
    assert data["summary"]["audit_count"] >= 2
    assert data["summary"]["artifact_count"] >= 2
    assert data["summary"]["latest_result_status"] == "completed"
    assert data["summary"]["latest_result_message_id"] == result_message.json()["data"]["id"]
    assert data["summary"]["receipt_count"] >= 1
    assert data["summary"]["capability_count"] == 1
    assert data["summary"]["runner_count"] == 1
    assert data["summary"]["auto_retry_active"] is False
    assert data["summary"]["pending_closeout_count"] == 0
    assert data["summary"]["exception_summary"]["failed"] == 0
    assert data["summary"]["exception_summary"]["actionable"] is False
    assert data["dispatches"][0]["id"] == dispatch["id"]
    assert data["gate"]["task_id"] == task["id"]
    assert any(item["kind"] == "dispatch" for item in data["timeline"])
    assert any(item["kind"] == "message" and item["source_type"] == "runner_command" for item in data["timeline"])
    assert any(item["message_type"] == "runner_ack" for item in data["receipts"])
    assert data["capability_summary"][0]["workstation_id"] == "ws-pro-view"
    assert data["capability_summary"][0]["runner_id"] == "runner-pro-view"
    assert "relay" in data["capability_summary"][0]["capability_labels"]
    assert data["capability_summary"][0]["runner"]["id"] == "runner-pro-view"
    assert data["capability_summary"][0]["runner"]["hardware_access"] is False

    messages = data["messages"]
    final = next(item for item in messages if item["message_type"] == "agent_result")
    assert final["dispatch_id"] == dispatch["id"]
    assert final["authoritative_seat_id"] == "ws-pro-view"
    assert final["authoritative_target_seat_id"] == owner_user_id
    assert final["historical_alias_non_authoritative"] is False
    assert final["payload_json"]["kind"] == "professional_view"
    assert any(item["label"] == "执行日志" and item["path"] == "artifacts/tests/pro-view/stdout.log" for item in final["artifact_refs"])
    assert any(item["label"] == "结果摘要" and item["path"] == "artifacts/tests/pro-view/summary.md" for item in final["artifact_refs"])
    assert all(item["authoritative_seat_id"] == "ws-pro-view" for item in final["artifact_refs"])
    stdout_ref = next(item for item in final["artifact_refs"] if item["path"] == "artifacts/tests/pro-view/stdout.log")
    assert stdout_ref["preview_context"] == {
        "task_id": task["id"],
        "path": "artifacts/tests/pro-view/stdout.log",
        "source_message_id": final["id"],
        "dispatch_id": dispatch["id"],
        "workstation_id": "ws-pro-view",
    }
    assert final["exception_state"]["failed"] is False
    assert final["exception_state"]["log_available"] is True
    assert final["exception_state"]["tags"] == ["log_available"]

    audit_actions = {item["action"] for item in data["audit"]}
    assert "task.dispatch" in audit_actions
    assert "task.dispatch_runner_command" in audit_actions

    artifact_index_response = client.get(
        f"/api/tasks/{task['id']}/artifact-index",
        headers=auth_headers(owner_token),
    )
    assert artifact_index_response.status_code == 200
    artifact_index = artifact_index_response.json()["data"]
    assert {"label": "执行日志", "path": "artifacts/tests/pro-view/stdout.log"} == {
        "label": artifact_index[0]["label"],
        "path": artifact_index[0]["path"],
    } or {"label": "执行日志", "path": "artifacts/tests/pro-view/stdout.log"} == {
        "label": artifact_index[1]["label"],
        "path": artifact_index[1]["path"],
    }
    assert any(item["runner_id"] == "runner-pro-view" for item in artifact_index)
    assert any(item["workstation_id"] == "ws-pro-view" for item in artifact_index)
    assert any(item["authoritative_seat_id"] == "ws-pro-view" for item in artifact_index)
    indexed_stdout = next(item for item in artifact_index if item["path"] == "artifacts/tests/pro-view/stdout.log")
    assert indexed_stdout["preview_context"] == {
        "task_id": task["id"],
        "path": "artifacts/tests/pro-view/stdout.log",
        "source_message_id": final["id"],
        "dispatch_id": dispatch["id"],
        "workstation_id": "ws-pro-view",
    }


def test_scoped_artifact_preview_requires_task_evidence_membership() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Scoped Artifact Preview")
    project_id = project["id"]
    task = create_task(
        client,
        owner_token,
        project_id,
        title="Scoped artifact preview task",
        description="Only task evidence should be previewable from a professional surface.",
        status="ready",
    )
    repo_root = Path(__file__).resolve().parents[3]
    evidence_path = repo_root / "artifacts" / "tests" / f"scoped-preview-{uuid4().hex}.md"
    unrelated_path = repo_root / "artifacts" / "tests" / f"unrelated-preview-{uuid4().hex}.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("# Scoped Evidence\n\nThis belongs to the task.", encoding="utf-8")
    unrelated_path.write_text("# Unrelated Evidence\n\nThis must not leak through task context.", encoding="utf-8")
    evidence_rel = str(evidence_path.relative_to(repo_root)).replace("\\", "/")
    unrelated_rel = str(unrelated_path.relative_to(repo_root)).replace("\\", "/")
    try:
        result_message = client.post(
            "/api/collaboration/messages",
            headers=auth_headers(owner_token),
            json={
                "project_id": project_id,
                "task_id": task["id"],
                "message_type": "agent_result",
                "title": "Scoped evidence",
                "body": "Evidence is ready.",
                "sender_type": "agent",
                "sender_id": "ws-preview",
                "recipient_type": "human",
                "recipient_id": owner_user_id,
                "status": "completed",
                "metadata": {
                    "evidence_artifacts": [
                        {"label": "Scoped report", "path": evidence_rel},
                    ],
                },
            },
        )
        assert result_message.status_code == 200
        message_id = result_message.json()["data"]["id"]

        preview_response = client.get(
            f"/api/collaboration/projects/{project_id}/artifacts/preview",
            headers=auth_headers(owner_token),
            params={
                key: value
                for key, value in next(
                    item["preview_context"]
                    for item in client.get(
                        f"/api/tasks/{task['id']}/artifact-index",
                        headers=auth_headers(owner_token),
                    ).json()["data"]
                    if item["path"] == evidence_rel
                ).items()
                if value is not None
            },
        )
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.json()["data"]["content"].startswith("# Scoped Evidence")

        unrelated_response = client.get(
            f"/api/collaboration/projects/{project_id}/artifacts/preview",
            headers=auth_headers(owner_token),
            params={
                "path": unrelated_rel,
                "task_id": task["id"],
                "source_message_id": message_id,
            },
        )
        assert unrelated_response.status_code == 403
        assert unrelated_response.json()["error"]["code"] == "ARTIFACT_NOT_IN_CONTEXT"
    finally:
        evidence_path.unlink(missing_ok=True)
        unrelated_path.unlink(missing_ok=True)


def test_artifact_index_rejects_historical_alias_mismatch_even_when_source_message_id_matches() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Authoritative Artifact Chain")
    project_id = project["id"]
    task = create_task(
        client,
        owner_token,
        project_id,
        title="Authoritative artifact chain",
        description="Artifact index should ignore evidence whose authoritative seat mismatches the source chain.",
        status="ready",
    )

    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-pro-view", "notes": "authoritative chain"},
    )
    if dispatch_response.status_code != 200:
        config_response = client.patch(
            f"/api/projects/{project_id}",
            headers=auth_headers(owner_token),
            json={
                "collaboration_config": {
                    "thread_workstations": [
                        {
                            "id": "ws-pro-view",
                            "name": "专业视图工位",
                            "agent_id": "agent-pro-view",
                            "status": "idle",
                        }
                    ]
                }
            },
        )
        assert config_response.status_code == 200
        dispatch_response = client.post(
            f"/api/tasks/{task['id']}/dispatch",
            headers=auth_headers(owner_token),
            json={"workstation_id": "ws-pro-view", "notes": "authoritative chain"},
        )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()["data"]

    source_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "dispatch_id": dispatch["id"],
            "message_type": "agent_command",
            "title": "Source command",
            "body": "Canonical source command.",
            "sender_type": "human",
            "sender_id": owner_user_id,
            "recipient_type": "thread_workstation",
            "recipient_id": "ws-pro-view",
            "status": "queued",
            "metadata": {
                "authoritative_seat_id": "ws-pro-view",
                "authoritative_seat_ref": "ws-pro-view",
            },
        },
    )
    assert source_message.status_code == 200, source_message.text
    source_message_id = source_message.json()["data"]["id"]

    bad_result = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "dispatch_id": dispatch["id"],
            "message_type": "agent_result",
            "title": "Mismatched alias evidence",
            "body": "Should not enter authoritative artifact index.",
            "sender_type": "agent",
            "sender_id": "legacy-alias",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "source_message_id": source_message_id,
                "authoritative_seat_id": "legacy-alias",
                "authoritative_seat_ref": "legacy-alias",
                "evidence_artifacts": [
                    {"label": "Bad report", "path": "artifacts/tests/pro-view/bad-alias.md"},
                ],
            },
        },
    )
    assert bad_result.status_code == 200, bad_result.text

    good_result = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "dispatch_id": dispatch["id"],
            "message_type": "agent_result",
            "title": "Canonical evidence",
            "body": "Should stay in authoritative artifact index.",
            "sender_type": "agent",
            "sender_id": "ws-pro-view",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "source_message_id": source_message_id,
                "authoritative_seat_id": "ws-pro-view",
                "authoritative_seat_ref": "ws-pro-view",
                "evidence_artifacts": [
                    {"label": "Good report", "path": "artifacts/tests/pro-view/good-alias.md"},
                ],
            },
        },
    )
    assert good_result.status_code == 200, good_result.text

    artifact_index_response = client.get(
        f"/api/tasks/{task['id']}/artifact-index",
        headers=auth_headers(owner_token),
    )
    assert artifact_index_response.status_code == 200, artifact_index_response.text
    artifact_index = artifact_index_response.json()["data"]
    paths = {item["path"] for item in artifact_index}
    assert "artifacts/tests/pro-view/good-alias.md" in paths
    assert "artifacts/tests/pro-view/bad-alias.md" not in paths


def test_task_professional_view_summarizes_timeout_exception_receipt() -> None:
    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Professional Exception")
    project_id = project["id"]
    task = create_task(
        client,
        owner_token,
        project_id,
        title="Timeout exception summary",
        description="Show actionable timeout repair in professional views.",
        status="ready",
    )

    result_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_result",
            "title": "执行超时待收口",
            "body": "超过 10 分钟未返回 final，平台标记待收口并建议催办或手动收口。",
            "sender_type": "system",
            "sender_id": "stale-sweeper",
            "recipient_type": "human",
            "recipient_id": "owner",
            "status": "blocked",
            "metadata": {
                "timeout_repair": True,
                "retryable": True,
                "split_suggested": True,
                "stderr_path": "artifacts/workstation-inbox/timeout.err.log",
            },
        },
    )
    assert result_message.status_code == 200

    view_response = client.get(
        f"/api/tasks/{task['id']}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    summary = view_response.json()["data"]["summary"]["exception_summary"]
    assert summary["failed"] == 1
    assert summary["timed_out"] == 1
    assert summary["auto_closed"] == 0
    assert summary["retryable"] == 1
    assert summary["log_available"] == 1
    assert summary["split_suggested"] == 1
    assert summary["platform_defect"] == 1
    assert summary["stale_sync_requires_attention"] == 1
    assert summary["exception_kind"] == "timeout"
    assert summary["actionable"] is True

    view_data = view_response.json()["data"]
    assert view_data["summary"]["evidence_chain_status"] == "incomplete"
    assert view_data["summary"]["stale_sync_requires_attention"] is True
    assert view_data["summary"]["auto_retry_active"] is False
    assert view_data["summary"]["pending_closeout_count"] == 1
    failed_message = next(item for item in view_data["messages"] if item["message_type"] == "agent_result")
    assert failed_message["exception_state"]["failed"] is False
    assert failed_message["exception_state"]["timed_out"] is True
    assert failed_message["exception_state"]["auto_closed"] is False
    assert failed_message["exception_state"]["retryable"] is True
    assert failed_message["exception_state"]["log_available"] is True
    assert failed_message["exception_state"]["split_suggested"] is True
    assert failed_message["exception_state"]["platform_defect"] is True
    assert failed_message["exception_state"]["nudge_required"] is True
    assert failed_message["exception_state"]["wait_extension_available"] is True
    assert failed_message["exception_state"]["manual_close_required"] is True
    assert failed_message["exception_state"]["desktop_closeout_waiting"] is True
    assert failed_message["exception_state"]["evidence_complete"] is False
    assert failed_message["exception_state"]["blocked_reason_code"] == "desktop_final_sync_lag"
    assert "desktop_closeout_waiting" in failed_message["exception_state"]["tags"]
    assert "platform_defect" in failed_message["exception_state"]["tags"]


def test_task_professional_view_summarizes_runner_capability_and_active_auto_retry() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    runner_register = client.post(
        "/api/runners/register",
        json={
            "runner_id": "runner-auto-retry",
            "runner_name": "Auto Retry Runner",
            "capabilities": ["ros", "telemetry", "artifact-index"],
            "hardware_access": True,
        },
    )
    assert runner_register.status_code == 200
    project = create_project(client, owner_token, name_prefix="Professional Auto Retry")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-auto-retry",
                        "label": "机器人现场机",
                        "status": "online",
                        "runner_id": "runner-auto-retry",
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
                        "id": "ws-auto-retry",
                        "name": "机器人现场工位",
                        "agent_id": "agent-auto-retry",
                        "computer_node_id": "pc-auto-retry",
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
        title="Auto retry evidence chain",
        description="Expose runner/capability/receipt rollups for sibling workbenches.",
        status="ready",
    )
    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={"workstation_id": "ws-auto-retry", "notes": "robotics site execution"},
    )
    assert dispatch_response.status_code == 200
    dispatch = dispatch_response.json()["data"]

    command_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "task_id": task["id"], "message_type": "runner_command", "limit": 10},
    )
    assert command_response.status_code == 200
    command = command_response.json()["data"][0]

    result_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "dispatch_id": dispatch["id"],
            "message_type": "agent_progress",
            "title": "桌面自动重试中",
            "body": "平台已自动重试桌面同步，等待最终回执。",
            "sender_type": "agent",
            "sender_id": "ws-auto-retry",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "in_progress",
            "metadata": {
                "source_message_id": command["id"],
                "stdout_path": "artifacts/tests/pro-view/auto-retry.log",
                "blocked_taxonomy": {
                    "failed": False,
                    "timed_out": True,
                    "auto_closed": False,
                    "retryable": True,
                    "log_available": True,
                    "split_suggested": False,
                    "exception_kind": "desktop_sync_retry",
                    "blocked_reason_code": "desktop_sync_retry",
                    "blocked_reason_label": "平台已自动重试桌面同步",
                    "evidence_complete": False,
                    "desktop_sync_retry_requested": True,
                    "desktop_sync_retry_count": 1,
                    "desktop_closeout_waiting": True,
                    "wait_extension_available": True,
                },
            },
        },
    )
    assert result_message.status_code == 200

    view_response = client.get(
        f"/api/tasks/{task['id']}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    data = view_response.json()["data"]
    assert data["summary"]["capability_count"] == 1
    assert data["summary"]["runner_count"] == 1
    assert data["summary"]["receipt_count"] >= 1
    assert data["summary"]["auto_retry_active"] is True
    assert data["summary"]["pending_closeout_count"] == 1
    assert data["capability_summary"][0]["runner"]["id"] == "runner-auto-retry"
    # Runner self-registration may claim hardware access, but the platform must
    # not expose it as granted until a trusted project binding/approval does so.
    assert data["capability_summary"][0]["runner"]["hardware_access"] is False
    assert "ros" in data["capability_summary"][0]["capability_labels"]

    artifact_index_response = client.get(
        f"/api/tasks/{task['id']}/artifact-index",
        headers=auth_headers(owner_token),
    )
    assert artifact_index_response.status_code == 200
    artifact = artifact_index_response.json()["data"][0]
    assert artifact["runner_id"] == "runner-auto-retry"
    assert artifact["workstation_id"] == "ws-auto-retry"
    assert artifact["path"] == "artifacts/tests/pro-view/auto-retry.log"
    assert artifact["authoritative_seat_id"] == "ws-auto-retry"
    assert "desktop_closeout_waiting" in artifact["exception_tags"]
    assert artifact["blocked_reason_code"] == "desktop_sync_retry"
    assert artifact["evidence_complete"] is False


def test_task_professional_view_exposes_ai_lab_closure_fields() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="AI Lab Closure Fields")
    project_id = project["id"]
    task = create_task(
        client,
        owner_token,
        project_id,
        title="AI lab training closure",
        description="Expose experiment, metrics, manifest, training receipt and release gate fields.",
        status="running",
    )

    result_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_result",
            "title": "训练回执与模型评估",
            "body": "training completed; eval metrics passed; manifest ready.",
            "sender_type": "agent",
            "sender_id": "ai-lab-seat",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "metadata": {
                "payload_json": {
                    "experiment_run_status": "ready",
                    "metrics_summary": {
                        "accuracy": 0.93,
                        "latency_ms": 42,
                        "regression_delta": -0.01,
                    },
                    "dataset_manifest": {
                        "manifest_version": "dataset-v3",
                        "sample_count": 128,
                        "low_confidence_count": 7,
                        "qa_status": "needs_review",
                        "export_status": "ready",
                    },
                    "training_receipt_status": "completed",
                    "release_gate_status": "can_continue",
                    "replay_ready": True,
                },
                "evidence_artifacts": [
                    {"label": "dataset manifest", "path": "artifacts/tests/ai-lab/dataset_manifest.json"},
                    {"label": "simulation replay", "path": "artifacts/tests/ai-lab/replay.json"},
                    {"label": "eval report", "path": "artifacts/tests/ai-lab/eval.md"},
                ],
            },
        },
    )
    assert result_message.status_code == 200, result_message.text

    view_response = client.get(
        f"/api/tasks/{task['id']}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    summary = view_response.json()["data"]["summary"]
    assert summary["experiment_run_status"] == "ready"
    assert summary["metrics_summary"] == {
        "accuracy": 0.93,
        "latency_ms": 42,
        "regression_delta": -0.01,
    }
    assert summary["dataset_manifest_artifact_path"] == "artifacts/tests/ai-lab/dataset_manifest.json"
    assert summary["manifest_version"] == "dataset-v3"
    assert summary["sample_count"] == 128
    assert summary["low_confidence_count"] == 7
    assert summary["qa_status"] == "needs_review"
    assert summary["export_status"] == "ready"
    assert summary["training_receipt_status"] == "completed"
    assert summary["release_gate_status"] == "can_continue"
    assert summary["replay_ready"] is True


def test_task_professional_view_reads_blocked_taxonomy_fields() -> None:
    owner_token, _owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Professional Blocked Taxonomy")
    project_id = project["id"]
    task = create_task(
        client,
        owner_token,
        project_id,
        title="Blocked taxonomy summary",
        description="Expose stable blocked taxonomy fields to the frontend.",
        status="ready",
    )

    result_message = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "message_type": "agent_result",
            "title": "执行失败",
            "body": "依赖环境缺失，建议拆分后重试。",
            "sender_type": "agent",
            "sender_id": "backend-seat",
            "recipient_type": "human",
            "recipient_id": "owner",
            "status": "failed",
            "metadata": {
                "stderr_path": "artifacts/tests/pro-view/blocked.err.log",
                "blocked_taxonomy": {
                    "failed": True,
                    "timed_out": False,
                    "auto_closed": False,
                    "retryable": True,
                    "log_available": True,
                    "split_suggested": True,
                    "exception_kind": "dependency_missing",
                    "blocked_reason_code": "dependency_missing",
                    "blocked_reason_label": "依赖环境缺失",
                    "evidence_complete": True,
                },
            },
        },
    )
    assert result_message.status_code == 200

    view_response = client.get(
        f"/api/tasks/{task['id']}/professional-view",
        headers=auth_headers(owner_token),
    )
    assert view_response.status_code == 200, view_response.text
    failed_message = next(
        item for item in view_response.json()["data"]["messages"] if item["message_type"] == "agent_result"
    )
    assert failed_message["exception_state"]["blocked_reason_code"] == "dependency_missing"
    assert failed_message["exception_state"]["blocked_reason_label"] == "依赖环境缺失"
    assert failed_message["exception_state"]["evidence_complete"] is True
    assert "reason:dependency_missing" in failed_message["exception_state"]["tags"]
