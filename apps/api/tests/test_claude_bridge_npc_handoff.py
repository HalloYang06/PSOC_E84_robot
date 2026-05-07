from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _auth() -> tuple[str, str]:
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
            "name": f"Bridge Handoff {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/bridge.git",
            "local_git_url": "/workspace/bridge.git",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _add_owner(project_id: str, token: str, user_id: str) -> None:
    response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert response.status_code == 200


def _create_npc(project_id: str, token: str) -> dict:
    response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"NPC-Bridge-{uuid4().hex[:6]}",
            "agent_id": "ai-fe-lead",
            "ai_provider_id": None,
            "computer_node_id": None,
            "status": "active",
            "description": "Bridge handoff test seat.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_task(project_id: str, token: str) -> dict:
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": "Bridge handoff task",
            "description": "Drives NPC handoff persistence test.",
            "module": "claude_bridge",
            "priority": "P2",
            "status": "ready",
            "branch": f"feature/bridge-{uuid4().hex[:8]}",
            "assignee_agent_id": "ai-fe-lead",
            "reviewers": ["lead"],
            "acceptance_criteria": ["handoff is persisted with reason=npc_thread_handover"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_npc_handoff_persists_record_and_returns_prompt() -> None:
    token, user_id = _auth()
    project_id = _create_project(token)
    _add_owner(project_id, token, user_id)
    npc = _create_npc(project_id, token)
    task = _create_task(project_id, token)

    auth = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/api/claude-bridge/projects/{project_id}/npcs/{npc['id']}/handoff",
        headers=auth,
        json={
            "task_id": task["id"],
            "summary": "切线程：上下文将满，下一任继续 NPC handoff 落库实现。",
            "next_steps": ["跑测试", "提交并 push"],
            "notes": "本次由测试触发。",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert isinstance(data.get("prompt"), str) and data["prompt"].strip()
    assert "你接手的岗位" in data["prompt"]

    handoff = data["handoff"]
    assert handoff["project_id"] == project_id
    assert handoff["task_id"] == task["id"]
    assert handoff["handoff_from"] == npc.get("agent_id") or handoff["handoff_from"] == npc["id"]
    assert handoff["handoff_to"] is None
    assert handoff["reason"] == "npc_thread_handover"
    assert handoff["current_status"] == "prepared"
    assert handoff["summary"].startswith("切线程")
    assert handoff["next_steps"] == ["跑测试", "提交并 push"]
    assert handoff["notes"] == "本次由测试触发。"
    payload_blob = handoff.get("payload") or {}
    assert payload_blob.get("source") == "claude_bridge.npc_handoff"
    assert payload_blob.get("npc_config_id") == npc["id"]
    assert payload_blob.get("npc_id")
    assert payload_blob.get("initiated_by_user_id") == user_id

    list_response = client.get(
        f"/api/handoffs?project_id={project_id}",
        headers=auth,
    )
    assert list_response.status_code == 200
    items = list_response.json()["data"]
    assert any(item["id"] == handoff["id"] for item in items)


def test_npc_handoff_requires_task_id() -> None:
    token, user_id = _auth()
    project_id = _create_project(token)
    _add_owner(project_id, token, user_id)
    npc = _create_npc(project_id, token)

    response = client.post(
        f"/api/claude-bridge/projects/{project_id}/npcs/{npc['id']}/handoff",
        headers={"Authorization": f"Bearer {token}"},
        json={"summary": "没传 task_id"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_npc_handoff_rejects_task_from_other_project() -> None:
    token, user_id = _auth()
    project_a = _create_project(token)
    _add_owner(project_a, token, user_id)
    project_b = _create_project(token)
    _add_owner(project_b, token, user_id)
    npc = _create_npc(project_a, token)
    task_b = _create_task(project_b, token)

    response = client.post(
        f"/api/claude-bridge/projects/{project_a}/npcs/{npc['id']}/handoff",
        headers={"Authorization": f"Bearer {token}"},
        json={"task_id": task_b["id"]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_npc_handoff_summary_falls_back_to_prompt_head() -> None:
    token, user_id = _auth()
    project_id = _create_project(token)
    _add_owner(project_id, token, user_id)
    npc = _create_npc(project_id, token)
    task = _create_task(project_id, token)

    response = client.post(
        f"/api/claude-bridge/projects/{project_id}/npcs/{npc['id']}/handoff",
        headers={"Authorization": f"Bearer {token}"},
        json={"task_id": task["id"]},
    )
    assert response.status_code == 200, response.text
    handoff = response.json()["data"]["handoff"]
    assert handoff["summary"] is not None
    assert "你接手的岗位" in handoff["summary"]
