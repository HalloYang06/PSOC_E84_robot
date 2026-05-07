from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import (
    assert_write_allowed,
    assert_write_rejected,
    request_json,
    setup_permission_workspace,
)


client = TestClient(app)


def test_global_admin_writes_require_real_human_auth() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Global Admin Write Matrix")
    owner_token = workspace["owner_token"]

    assert_write_rejected(
        client,
        "POST",
        "/api/agents",
        None,
        {"name": "Anonymous Agent"},
        expected_status=401,
        expected_code="UNAUTHORIZED",
    )

    create_response = assert_write_allowed(
        client,
        "POST",
        "/api/agents",
        owner_token,
        {"name": "Matrix Agent"},
    )
    agent_id = create_response.json()["data"]["id"]

    assert_write_allowed(
        client,
        "PATCH",
        f"/api/agents/{agent_id}",
        owner_token,
        {"description": "updated by matrix test"},
    )
    assert_write_allowed(
        client,
        "POST",
        f"/api/agents/{agent_id}/enable",
        owner_token,
        {"note": "enable"},
    )
    assert_write_allowed(
        client,
        "POST",
        f"/api/agents/{agent_id}/disable",
        owner_token,
        {"note": "disable"},
    )


def test_scoped_write_matrix_covers_usage_audit_lab_handoffs_and_context_health() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Scoped Write Matrix")
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]
    outsider_token = workspace["outsider_token"]
    owner_user_id = workspace["owner_user_id"]
    project_id = workspace["project_id"]
    task_id = workspace["task_id"]
    handoff_id = workspace["handoff_id"]

    scoped_allowed = [
        (
            "POST",
            "/api/usage",
            {
                "project_id": project_id,
                "task_id": task_id,
                "agent_id": "agent-ui",
                "provider": "openai",
                "model": "gpt-5.4",
                "input_tokens": 12,
                "output_tokens": 8,
            },
        ),
        (
            "POST",
            "/api/audit",
            {
                "project_id": project_id,
                "task_id": task_id,
                "action": "permission.audit",
                "resource_type": "task",
                "resource_id": task_id,
                "before": {},
                "after": {},
            },
        ),
        (
            "POST",
            f"/api/tasks/{task_id}/context-health",
            {
                "project_id": project_id,
                "agent_id": "agent-ui",
                "usage_ratio": 0.4,
                "health": "yellow",
                "conversation_turns": 2,
                "files_loaded_count": 3,
                "failed_retry_count": 0,
                "summary": "context is still healthy",
                "recommended_action": "continue",
            },
        ),
        (
            "POST",
            f"/api/tasks/{task_id}/summarize-context",
            {
                "project_id": project_id,
                "agent_id": "agent-ui",
                "usage_ratio": 0.6,
                "health": "yellow",
                "conversation_turns": 4,
                "files_loaded_count": 7,
                "failed_retry_count": 1,
                "summary": "summarized by matrix test",
                "recommended_action": "continue",
            },
        ),
        (
            "POST",
            f"/api/tasks/{task_id}/handoffs",
            {
                "project_id": project_id,
                "handoff_from": "agent-ui",
                "handoff_to": "agent-review",
                "summary": "handoff from matrix test",
                "reason": "coverage",
                "current_status": "ready",
                "notes": "handoff write matrix",
            },
        ),
    ]

    for method, path, payload in scoped_allowed:
        assert_write_allowed(client, method, path, owner_token, payload)

    member_allowed = [
        (
            "POST",
            "/api/usage",
            {
                "project_id": project_id,
                "task_id": task_id,
                "agent_id": "agent-ui",
                "provider": "openai",
                "model": "gpt-5.4",
            },
        ),
        (
            "POST",
            f"/api/lab/checks",
            {
                "task_id": task_id,
                "item": "context-health",
                "passed": True,
                "notes": "member check",
            },
        ),
        (
            "POST",
            f"/api/handoffs/{handoff_id}/messages",
            {
                "project_id": project_id,
                "message_type": "comment_message",
                "sender_type": "human",
                "sender_id": owner_user_id,
                "body": "handoff message",
            },
        ),
    ]

    for method, path, payload in member_allowed:
        assert_write_allowed(client, method, path, member_token, payload)

    high_risk_forbidden = [
        (
            "POST",
            f"/api/lab/hardware-approvals",
            {
                "task_id": task_id,
                "action": "deploy arm firmware",
                "level": "H3",
                "notes": "request hardware approval",
            },
        ),
    ]
    for method, path, payload in high_risk_forbidden:
        response = request_json(client, method, path, member_token, payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"

    outsider_forbidden = [
        ("POST", "/api/usage", {"project_id": project_id, "task_id": task_id, "provider": "openai"}),
        ("POST", "/api/audit", {"project_id": project_id, "task_id": task_id, "action": "permission.audit"}),
        ("POST", f"/api/tasks/{task_id}/context-health", {"project_id": project_id, "usage_ratio": 0.5, "health": "green"}),
        ("POST", f"/api/tasks/{task_id}/summarize-context", {"project_id": project_id, "usage_ratio": 0.5, "health": "green"}),
        (
            "POST",
            f"/api/tasks/{task_id}/handoffs",
            {
                "project_id": project_id,
                "handoff_from": "agent-ui",
                "handoff_to": "agent-review",
                "summary": "outsider handoff",
            },
        ),
        (
            "POST",
            f"/api/handoffs/{handoff_id}/messages",
            {
                "project_id": project_id,
                "message_type": "comment_message",
                "sender_type": "human",
                "sender_id": workspace["outsider_user_id"],
                "body": "outsider handoff message",
            },
        ),
    ]
    for method, path, payload in outsider_forbidden:
        response = request_json(client, method, path, outsider_token, payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
