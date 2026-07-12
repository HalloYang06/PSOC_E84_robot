from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _issue_session_token() -> tuple[str, str]:
    response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["id"]


def _register_user(email: str, name: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": name,
            "password": "password",
            "global_role": "member",
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["id"], payload["email"]


def _create_robot_project(token: str) -> dict[str, object]:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Robot Collaboration {suffix}",
            "description": "Productization test project for multi-computer AI collaboration",
            "project_type": "robotics",
            "github_url": "https://example.com/robot.git",
            "local_git_url": "/workspace/robot.git",
            "default_branch": "main",
            "develop_branch": "develop",
            "collaboration_config": {
                "providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "kind": "openai",
                        "enabled": True,
                        "endpoint": "https://api.openai.com",
                        "default_model": "gpt-5.1",
                    },
                    {
                        "id": "claude",
                        "label": "Claude",
                        "kind": "anthropic",
                        "enabled": True,
                        "endpoint": "https://api.anthropic.com",
                        "model": "claude-sonnet-4.5",
                    },
                ],
                "nodes": [
                    {
                        "id": "pc-1",
                        "label": "电脑 1",
                        "status": "online",
                        "runner_id": "runner-pc-1",
                        "host": "192.168.1.10",
                        "platform": "windows",
                    },
                    {
                        "id": "pc-2",
                        "label": "电脑 2",
                        "status": "online",
                        "runner_id": "runner-pc-2",
                        "host": "192.168.1.11",
                        "platform": "linux",
                    },
                ],
                "workstations": [
                    {
                        "name": "UI 工位",
                        "agent_id": "agent-ui",
                        "computer_node": "pc-1",
                        "ai_provider": "codex",
                        "status": "active",
                        "description": "电脑 1 的 Codex 负责前端与协作界面。",
                    },
                    {
                        "name": "机器人控制工位",
                        "agent_id": "agent-robot",
                        "computer_node_id": "pc-2",
                        "ai_provider_id": "claude",
                        "status": "active",
                        "notes": "电脑 2 的 Claude 负责机器人控制与策略。",
                    },
                ],
            },
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def _create_task(token: str, project_id: str, **overrides: object) -> dict[str, object]:
    payload = {
        "project_id": project_id,
        "title": "Frontend collaboration task",
        "description": "Use the matching AI employee and computer node for the branch work.",
        "module": "frontend",
        "priority": "P2",
        "status": "ready",
        "branch": "feature/frontend-work",
        "assignee_agent_id": "agent-ui",
        "reviewers": ["lead"],
        "acceptance_criteria": ["task/workstation pairing is readable from workspace data"],
    }
    payload.update(overrides)
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    return response.json()["data"]


def _score_workstation(task: dict[str, object], workstation: dict[str, object]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0

    if str(task.get("assignee_agent_id") or "") and str(task.get("assignee_agent_id")) == str(workstation.get("agent_id")):
        score += 4
        reasons.append("agent matches task assignee")
    else:
        reasons.append("agent mismatch")

    if str(workstation.get("status") or "").lower() in {"active", "ready", "online"}:
        score += 2
        reasons.append("workstation active")
    else:
        reasons.append("workstation not active")

    if str(workstation.get("permission_level") or "").upper() in {"L3", "L4", "L5"}:
        score += 2
        reasons.append("permission is sufficient")
    else:
        reasons.append("permission too low")

    if list(workstation.get("read_paths") or []) and list(workstation.get("write_paths") or []):
        score += 1
        reasons.append("paths configured")
    else:
        reasons.append("paths missing")

    return score, reasons


def test_project_collaboration_config_round_trips_multi_computer_layout() -> None:
    token, _ = _issue_session_token()
    project = _create_robot_project(token)
    project_id = project["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": _issue_session_token()[1],
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    config_response = client.patch(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "collaboration_config": {
                "providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "kind": "openai",
                        "enabled": True,
                        "endpoint": "https://api.openai.com",
                        "default_model": "gpt-5.1",
                    },
                    {
                        "id": "claude",
                        "label": "Claude",
                        "kind": "anthropic",
                        "enabled": True,
                        "endpoint": "https://api.anthropic.com",
                        "model": "claude-sonnet-4.5",
                    },
                ],
                "nodes": [
                    {
                        "id": "pc-1",
                        "label": "电脑 1",
                        "status": "online",
                        "runner_id": "runner-pc-1",
                        "host": "192.168.1.10",
                        "platform": "windows",
                    },
                    {
                        "id": "pc-2",
                        "label": "电脑 2",
                        "status": "online",
                        "runner_id": "runner-pc-2",
                        "host": "192.168.1.11",
                        "platform": "linux",
                    },
                ],
                "workstations": [
                    {
                        "name": "UI 工位",
                        "agent_id": "agent-ui",
                        "computer_node": "pc-1",
                        "ai_provider": "codex",
                        "status": "active",
                        "description": "电脑 1 的 Codex 负责前端与协作界面。",
                    },
                    {
                        "name": "机器人控制工位",
                        "agent_id": "agent-robot",
                        "computer_node_id": "pc-2",
                        "ai_provider_id": "claude",
                        "status": "active",
                        "notes": "电脑 2 的 Claude 负责机器人控制与策略。",
                    },
                ],
            }
        },
    )
    assert config_response.status_code == 200

    config = config_response.json()["data"]["collaboration_config"]
    assert [node["id"] for node in config["computer_nodes"]] == ["pc-1", "pc-2"]
    assert config["computer_nodes"][0]["os"] == "windows"
    assert config["computer_nodes"][1]["os"] == "linux"
    assert [provider["id"] for provider in config["ai_providers"]] == ["codex", "claude"]
    assert config["ai_providers"][0]["endpoint"] == "https://api.openai.com"
    assert config["ai_providers"][0]["model"] == "gpt-5.1"
    assert config["thread_workstations"][0]["computer_node_id"] == "pc-1"
    assert config["thread_workstations"][0]["ai_provider_id"] == "codex"
    assert config["thread_workstations"][1]["computer_node_id"] == "pc-2"
    assert config["thread_workstations"][1]["ai_provider_id"] == "claude"


def test_git_workflow_records_sync_and_rollback_activity() -> None:
    token, user_id = _issue_session_token()
    project = _create_robot_project(token)
    project_id = project["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    sync_response = client.post(
        f"/api/git/projects/{project_id}/sync-github",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "actor_type": "human",
            "actor_id": user_id,
            "provider": "github",
            "notes": "sync robot project before coordination work",
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["status"] == "queued"

    rollback_response = client.post(
        f"/api/git/projects/{project_id}/rollback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "actor_type": "human",
            "actor_id": user_id,
            "target_ref": "HEAD~1",
            "notes": "rollback after review",
        },
    )
    assert rollback_response.status_code == 200
    assert rollback_response.json()["data"]["status"] == "queued"

    second_user_id, second_user_email = _register_user(f"git-viewer-{uuid4().hex[:8]}@example.com", "Git Viewer")
    second_session = client.post(
        "/api/auth/session",
        json={"email": second_user_email, "password": "password"},
    )
    assert second_session.status_code == 200
    second_token = second_session.json()["data"]["access_token"]

    member_add_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": second_user_id,
            "role": "member",
            "status": "active",
            "is_owner": False,
        },
    )
    assert member_add_response.status_code == 200

    forbidden_sync_response = client.post(
        f"/api/git/projects/{project_id}/sync-github",
        headers={"Authorization": f"Bearer {second_token}"},
        json={
            "actor_type": "human",
            "actor_id": second_user_id,
            "provider": "github",
            "notes": "viewer should not be able to sync",
        },
    )
    assert forbidden_sync_response.status_code == 403

    forbidden_rollback_response = client.post(
        f"/api/git/projects/{project_id}/rollback",
        headers={"Authorization": f"Bearer {second_token}"},
        json={
            "actor_type": "human",
            "actor_id": second_user_id,
            "target_ref": "HEAD~1",
            "notes": "viewer should not be able to rollback",
        },
    )
    assert forbidden_rollback_response.status_code == 403

    activity_response = client.get(
        f"/api/git/projects/{project_id}/activity?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activity_response.status_code == 200

    activity_items = activity_response.json()["data"]
    actions = [item["action"] for item in activity_items]
    assert "project.sync_github" in actions
    assert "project.rollback_requested" in actions
    rollback_item = next(item for item in activity_items if item["action"] == "project.rollback_requested")
    assert rollback_item["title"] == "Git 回退请求"
    assert rollback_item["summary"] == "已登记回退到 HEAD~1"
    assert "rollback after review" in rollback_item["body"]


def test_git_rollback_preview_is_read_only() -> None:
    token, user_id = _issue_session_token()
    project = _create_robot_project(token)
    project_id = project["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    task_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": "Stabilize rollback preview",
            "description": "Make sure Git preview stays read-only.",
            "status": "ready",
            "priority": "P1",
            "branch": "feature/rollback-preview",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["data"]["id"]

    before_activity = client.get(
        f"/api/git/projects/{project_id}/activity?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before_activity.status_code == 200
    before_actions = [item["action"] for item in before_activity.json()["data"]]

    preview_response = client.post(
        f"/api/git/projects/{project_id}/rollback-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "target_ref": "develop",
            "notes": "preview only",
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["target_ref"] == "develop"
    assert preview["ready"] is True
    assert "这次只是预演，不会写入项目活动流。" in preview["preview_notes"]
    assert preview["branch_count"] == 1
    assert preview["merge_ready_count"] == 1
    assert preview["blocked_count"] == 0
    assert preview["pending_high_risk_count"] == 0
    assert preview["merge_ready_titles"] == ["Stabilize rollback preview"]
    assert preview["blocked_branch_titles"] == []

    after_activity = client.get(
        f"/api/git/projects/{project_id}/activity?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_activity.status_code == 200
    after_actions = [item["action"] for item in after_activity.json()["data"]]
    assert after_actions == before_actions
    assert "project.rollback_requested" not in after_actions


def test_git_sync_preview_is_read_only() -> None:
    token, user_id = _issue_session_token()
    project = _create_robot_project(token)
    project_id = project["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    task_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": project_id,
            "title": "Prepare sync preview",
            "description": "Make sure Git sync preview stays read-only.",
            "status": "ready",
            "priority": "P1",
            "branch": "feature/sync-preview",
        },
    )
    assert task_response.status_code == 200

    before_activity = client.get(
        f"/api/git/projects/{project_id}/activity?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before_activity.status_code == 200
    before_actions = [item["action"] for item in before_activity.json()["data"]]

    preview_response = client.post(
        f"/api/git/projects/{project_id}/sync-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "github",
            "notes": "preview only",
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["provider"] == "github"
    assert preview["ready"] is True
    assert preview["repository_target"] == "https://example.com/robot.git"
    assert "这次只是预演，不会写入项目活动流。" in preview["preview_notes"]
    assert preview["branch_count"] == 1
    assert preview["merge_ready_count"] == 1
    assert preview["blocked_count"] == 0
    assert preview["pending_high_risk_count"] == 0
    assert preview["merge_ready_titles"] == ["Prepare sync preview"]
    assert preview["blocked_branch_titles"] == []

    after_activity = client.get(
        f"/api/git/projects/{project_id}/activity?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_activity.status_code == 200
    after_actions = [item["action"] for item in after_activity.json()["data"]]
    assert after_actions == before_actions
    assert "project.sync_github" not in after_actions


def test_git_workspace_supports_local_task_to_workstation_readiness_scoring() -> None:
    token, user_id = _issue_session_token()
    project = _create_robot_project(token)
    project_id = project["id"]

    member_response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert member_response.status_code == 200

    collaboration_config = deepcopy(project["collaboration_config"])
    collaboration_config["thread_workstations"] = [
        {
            "name": "UI 宸ヤ綅",
            "agent_id": "agent-ui",
            "computer_node_id": "pc-1",
            "ai_provider_id": "codex",
            "status": "active",
            "responsibility": "frontend and coordination",
            "model": "gpt-5.4",
            "permission_level": "L3",
            "read_paths": ["D:/workspaces/robot/repo", "D:/shared/specs"],
            "write_paths": ["D:/workspaces/robot/repo/apps/web", "D:/workspaces/robot/repo/apps/api"],
        },
        {
            "name": "Robot 宸ヤ綅",
            "agent_id": "agent-robot",
            "computer_node_id": "pc-2",
            "ai_provider_id": "claude",
            "status": "idle",
            "responsibility": "robot ops",
            "model": "claude-opus-4.1",
            "permission_level": "L2",
            "read_paths": [],
            "write_paths": [],
        },
    ]

    patch_response = client.patch(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
        json={"collaboration_config": collaboration_config},
    )
    assert patch_response.status_code == 200

    task = _create_task(token, project_id)
    workspace_response = client.get(
        f"/api/git/projects/{project_id}/workspace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert workspace_response.status_code == 200

    workspace = workspace_response.json()["data"]
    task_branch = next(item for item in workspace["task_branches"] if item["id"] == task["id"])
    assert task_branch["assignee_agent_id"] == "agent-ui"

    scored = []
    for workstation in workspace["thread_workstations"]:
        score, reasons = _score_workstation(task_branch, workstation)
        scored.append((score, workstation["name"], reasons))

    scored.sort(reverse=True)
    top_score, top_name, top_reasons = scored[0]
    assert top_name == "UI 宸ヤ綅"
    assert top_score >= 7
    assert "agent matches task assignee" in top_reasons
    assert "paths configured" in top_reasons
