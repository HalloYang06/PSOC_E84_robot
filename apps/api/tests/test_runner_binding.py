from __future__ import annotations

from uuid import uuid4

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


def test_runner_read_model_reflects_project_computer_node_bindings() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Computer 7",
            "capabilities": ["git", "python"],
            "hardware_access": True,
        },
    )
    assert register_response.status_code == 200

    project_suffix = uuid4().hex[:8]
    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Binding {project_suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/runner-binding.git",
            "local_git_url": "/workspace/runner-binding.git",
            "default_branch": "main",
            "develop_branch": "develop",
            "collaboration_config": {
                "ai_providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "kind": "thread",
                        "enabled": True,
                        "endpoint": "local thread",
                        "model": "gpt-5",
                    }
                ],
                "computer_nodes": [
                    {
                        "id": "pc-7",
                        "label": "鐢佃剳 7",
                        "status": "online",
                        "runner_id": runner_id,
                        "host": "192.168.1.77",
                        "os": "Linux",
                    }
                ],
                "thread_workstations": [
                    {
                        "name": "前端工位",
                        "agent_id": "agent-ui",
                        "computer_node_id": "pc-7",
                        "ai_provider_id": "codex",
                        "status": "active",
                        "description": "电脑 7 上的 Codex 负责前端与协作界面。",
                    }
                ],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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

    config_response = client.patch(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "collaboration_config": {
                "ai_providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "kind": "thread",
                        "enabled": True,
                        "endpoint": "local thread",
                        "model": "gpt-5",
                    }
                ],
                "computer_nodes": [
                    {
                        "id": "pc-7",
                        "label": "鐢佃剳 7",
                        "status": "online",
                        "runner_id": runner_id,
                        "host": "192.168.1.77",
                        "os": "Linux",
                    }
                ],
                "thread_workstations": [
                    {
                        "name": "前端工位",
                        "agent_id": "agent-ui",
                        "computer_node_id": "pc-7",
                        "ai_provider_id": "codex",
                        "status": "active",
                        "description": "电脑 7 上的 Codex 负责前端与协作界面。",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    runner_response = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {token}"})
    assert runner_response.status_code == 200
    runner = runner_response.json()["data"]
    assert runner["computer_node_id"] == "pc-7"
    assert runner["computer_node_label"] == "鐢佃剳 7"
    assert runner["node_kind"] == "computer_node"
    assert runner["bound_project_count"] == 1
    assert runner["computer_node_bindings"][0]["project_id"] == project_id
    assert runner["computer_node_bindings"][0]["project_name"].startswith("Runner Binding")

    workspace_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    assert workspace["runner"]["id"] == runner_id
    assert workspace["binding_count"] == 1
    assert workspace["project_count"] == 1
    assert workspace["computer_node_count"] == 1
    assert workspace["bindings"][0]["computer_node_id"] == "pc-7"
    assert workspace["workstations"][0]["computer_node_id"] == "pc-7"
    assert workspace["workstations"][0]["ai_provider_id"] == "codex"
    assert workspace["workstations"][0]["ai_provider_label"] == "Codex"

    summary_response = client.get("/api/runners/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["bound_computer_nodes"] >= 1
    assert summary["bound_projects"] >= 1


def test_runner_workspace_surfaces_current_task_and_recent_errors() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Ops Runner",
            "capabilities": ["git", "python", "logs"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Ops {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-ops",
                        "label": "运维电脑",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-ops",
                        "name": "运维工位",
                        "agent_id": "agent-runner",
                        "computer_node_id": "pc-ops",
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
            "title": "Runner ops task",
            "description": "verify current task and errors",
            "module": "ops",
            "priority": "P1",
            "status": "ready",
            "branch": "feature/runner-ops",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["data"]["id"]

    next_task_response = client.get(f"/api/runners/{runner_id}/next-task", headers={"X-Runner-Id": runner_id})
    assert next_task_response.status_code == 200

    log_response = client.post(
        f"/api/runners/{runner_id}/tasks/{task_id}/logs",
        headers={"X-Runner-Id": runner_id},
        json={"level": "error", "message": "disk full on workspace"},
    )
    assert log_response.status_code == 200

    runner_response = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {token}"})
    assert runner_response.status_code == 200
    runner = runner_response.json()["data"]
    assert runner["current_task"]["id"] == task_id
    assert runner["current_task"]["status"] == "running"
    assert len(runner["recent_errors"]) >= 1
    assert runner["recent_errors"][0]["event_type"] == "log:error"

    workspace_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    assert workspace["active_task_count"] >= 1
    assert len(workspace["recent_events"]) >= 2
    assert len(workspace["recent_errors"]) >= 1

    summary_response = client.get("/api/runners/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["active_runner_tasks"] >= 1
    assert summary["recent_error_events"] >= 1


def test_runner_summary_tracks_multiple_project_bindings() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Multi Project Runner",
            "capabilities": ["git", "python"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_ids: list[str] = []
    for index in range(2):
        suffix = uuid4().hex[:8]
        project_response = client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Runner Multi Binding {index + 1} {suffix}",
                "project_type": "robotics",
                "github_url": "https://example.com/multi-binding.git",
                "local_git_url": f"/workspace/multi-binding-{index + 1}.git",
                "default_branch": "main",
                "develop_branch": "develop",
            },
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["id"]
        project_ids.append(project_id)

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

        config_response = client.patch(
            f"/api/projects/{project_id}/config",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "collaboration_config": {
                    "computer_nodes": [
                        {
                            "id": f"pc-{index + 1}",
                            "label": f"閻絻鍓?{index + 1}",
                            "status": "online",
                            "runner_id": runner_id,
                            "host": f"192.168.1.{80 + index}",
                            "os": "Linux",
                        }
                    ]
                }
            },
        )
        assert config_response.status_code == 200

    runner_response = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {token}"})
    assert runner_response.status_code == 200
    runner = runner_response.json()["data"]
    assert runner["bound_project_count"] == 2
    assert len(runner["computer_node_bindings"]) == 2
    assert {binding["project_id"] for binding in runner["computer_node_bindings"]} == set(project_ids)

    summary_response = client.get("/api/runners/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["bound_computer_nodes"] >= 2
    assert summary["bound_projects"] >= 2


def test_runner_explicit_bind_and_unbind_endpoints_update_project_and_runner_views() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Explicit Binding Runner",
            "capabilities": ["git", "python"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Explicit Binding {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-bind",
                        "label": "Binding Node",
                        "status": "online",
                        "host": "192.168.1.120",
                        "os": "Linux",
                    }
                ]
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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

    bind_response = client.post(
        f"/api/runners/{runner_id}/bindings",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id, "computer_node_id": "pc-bind"},
    )
    assert bind_response.status_code == 200
    binding = bind_response.json()["data"]
    assert binding["runner_id"] == runner_id
    assert binding["project_id"] == project_id
    assert binding["computer_node_id"] == "pc-bind"

    runner_response = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {token}"})
    assert runner_response.status_code == 200
    runner = runner_response.json()["data"]
    assert runner["computer_node_id"] == "pc-bind"
    assert runner["bound_project_count"] == 1

    project_config_response = client.get(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project_config_response.status_code == 200
    nodes = project_config_response.json()["data"]["collaboration_config"]["computer_nodes"]
    assert nodes[0]["runner_id"] == runner_id

    unbind_response = client.delete(
        f"/api/runners/{runner_id}/bindings/{project_id}/pc-bind",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unbind_response.status_code == 200

    runner_after_response = client.get(f"/api/runners/{runner_id}", headers={"Authorization": f"Bearer {token}"})
    assert runner_after_response.status_code == 403
    assert runner_after_response.json()["error"]["code"] == "PERMISSION_DENIED"

    project_config_after_response = client.get(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project_config_after_response.status_code == 200
    nodes_after = project_config_after_response.json()["data"]["collaboration_config"]["computer_nodes"]
    assert nodes_after[0]["runner_id"] is None


def test_runner_thread_sync_counts_only_scanned_threads_and_preserves_manual_seats() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Sync Runner",
            "capabilities": ["git", "python"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Sync {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "ai_providers": [
                    {"id": "codex", "label": "Codex", "kind": "thread", "enabled": True},
                ],
                "computer_nodes": [
                    {"id": "pc-sync", "label": "Sync Node", "status": "online", "runner_id": runner_id},
                ],
                "thread_workstations": [
                    {
                        "id": "manual-seat",
                        "name": "Manual NPC Seat",
                        "agent_id": "agent-seat",
                        "computer_node_id": "pc-sync",
                        "ai_provider_id": "codex",
                        "status": "active",
                        "metadata": {"source_workstation_id": "codex-session-keep"},
                    }
                ],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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
        f"/api/runners/{runner_id}/thread-workstations/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "pc-sync",
            "workstations": [
                {
                    "workstation_id": "codex-session-a",
                    "workstation_name": "Session A",
                    "workstation_status": "active",
                    "cwd": "D:/ai-collab-product",
                    "metadata": {
                        "desktop_process_detected": True,
                        "desktop_bridge_connected": True,
                        "desktop_delivery_mode": "codex_desktop_ui",
                        "desktop_bridge_label": "Codex Desktop UI automation",
                        "desktop_bridge_note": "Runner can open codex://threads/<id> and send a prompt.",
                    },
                },
                {
                    "workstation_id": "codex-session-b",
                    "workstation_name": "Session B",
                    "workstation_status": "idle",
                    "cwd": "D:/ai-collab-product",
                },
            ],
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["thread_count"] == 2

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    workstations = config["thread_workstations"]
    workstation_ids = {item["id"] for item in workstations}
    assert workstation_ids == {"manual-seat", "codex-session-a", "codex-session-b"}

    nodes_response = client.get(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert nodes_response.status_code == 200
    node = nodes_response.json()["data"][0]
    assert node["metadata"]["thread_scan"]["thread_count"] == 2
    assert node["metadata"]["thread_scan"]["desktop_process_detected"] is True
    assert node["metadata"]["thread_scan"]["desktop_bridge_connected"] is True
    assert node["metadata"]["thread_scan"]["desktop_delivery_mode"] == "codex_desktop_ui"
    assert node["metadata"]["thread_scan"]["desktop_bridge_label"] == "Codex Desktop UI automation"
    assert {item["workstation_id"] for item in node["metadata"]["thread_scan"]["threads"]} == {
        "codex-session-a",
        "codex-session-b",
    }

    workspace_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    sources = {item["workstation_id"]: item.get("source") for item in workspace["workstations"]}
    assert sources["manual-seat"] is None
    assert sources["codex-session-a"] == "runner_thread_scan"
    assert sources["codex-session-b"] == "runner_thread_scan"


def test_runner_thread_sync_merges_provider_scans_for_same_computer_node() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Multi Provider Sync Runner",
            "capabilities": ["codex", "claude", "threads"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Multi Provider Sync {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "ai_providers": [
                    {"id": "codex", "label": "Codex", "kind": "thread", "enabled": True},
                    {"id": "claude", "label": "Claude", "kind": "thread", "enabled": True},
                ],
                "computer_nodes": [
                    {"id": "pc-multi", "label": "Multi Provider Node", "status": "online", "runner_id": runner_id},
                ],
                "thread_workstations": [],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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

    codex_sync_response = client.post(
        f"/api/runners/{runner_id}/thread-workstations/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "pc-multi",
            "workstations": [
                {
                    "workstation_id": "codex-session-main",
                    "workstation_name": "Codex Main",
                    "workstation_status": "active",
                    "ai_provider_id": "codex",
                    "ai_provider_label": "Codex Desktop",
                    "cwd": "D:/ai-collab-product",
                    "metadata": {"provider_family": "codex"},
                },
                {
                    "workstation_id": "codex-session-sidecar",
                    "workstation_name": "Codex Sidecar",
                    "workstation_status": "idle",
                    "ai_provider_id": "codex",
                    "ai_provider_label": "Codex Desktop",
                    "cwd": "D:/ai-collab-product",
                    "metadata": {"provider_family": "codex"},
                },
            ],
        },
    )
    assert codex_sync_response.status_code == 200
    assert codex_sync_response.json()["data"]["thread_count"] == 2

    claude_sync_response = client.post(
        f"/api/runners/{runner_id}/thread-workstations/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "pc-multi",
            "workstations": [
                {
                    "workstation_id": "claude-session-main",
                    "workstation_name": "Claude Main",
                    "workstation_status": "active",
                    "ai_provider_id": "claude",
                    "ai_provider_label": "Claude CLI",
                    "cwd": "D:/ai-collab-product",
                    "metadata": {"provider_family": "claude"},
                },
            ],
        },
    )
    assert claude_sync_response.status_code == 200
    assert claude_sync_response.json()["data"]["thread_count"] == 1

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    workstation_ids = {item["id"] for item in config["thread_workstations"]}
    assert workstation_ids == {"codex-session-main", "codex-session-sidecar", "claude-session-main"}

    nodes_response = client.get(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert nodes_response.status_code == 200
    node = nodes_response.json()["data"][0]
    scan = node["metadata"]["thread_scan"]
    assert scan["thread_count"] == 3
    assert {item["workstation_id"] for item in scan["threads"]} == {
        "codex-session-main",
        "codex-session-sidecar",
        "claude-session-main",
    }


def test_runner_thread_sync_ignores_system_timestamps_in_manual_workstation_config() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Sync Runner Timestamp Guard",
            "capabilities": ["git", "python"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Sync Timestamp Guard {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "ai_providers": [
                    {"id": "codex", "label": "Codex", "kind": "thread", "enabled": True},
                ],
                "computer_nodes": [
                    {"id": "pc-sync", "label": "Sync Node", "status": "online", "runner_id": runner_id},
                ],
                "thread_workstations": [
                    {
                        "id": "manual-seat",
                        "name": "Manual NPC Seat",
                        "agent_id": "agent-seat",
                        "computer_node_id": "pc-sync",
                        "ai_provider_id": "codex",
                        "status": "active",
                        "created_at": "2026-04-21 14:49:53",
                        "updated_at": "2026-04-21 14:49:53",
                        "metadata": {"source_workstation_id": "codex-session-keep"},
                    }
                ],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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
        f"/api/runners/{runner_id}/thread-workstations/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "pc-sync",
            "workstations": [
                {
                    "workstation_id": "codex-session-npc1",
                    "workstation_name": "NPC1",
                    "workstation_status": "active",
                    "cwd": "D:/ai合作产品",
                },
                {
                    "workstation_id": "codex-session-npc2",
                    "workstation_name": "NPC2",
                    "workstation_status": "active",
                    "cwd": "D:/ai合作产品",
                },
            ],
        },
    )
    assert sync_response.status_code == 200

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert config_response.status_code == 200
    workstations = config_response.json()["data"]["collaboration_config"]["thread_workstations"]
    workstation_ids = {item["id"] for item in workstations}
    assert workstation_ids == {"manual-seat", "codex-session-npc1", "codex-session-npc2"}


def test_runner_thread_sync_preserves_provider_label_and_default_skill_loadout() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Runner Skill Sync",
            "capabilities": ["git", "python"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Runner Skill Sync {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "ai_providers": [
                    {"id": "codex", "label": "Codex", "kind": "thread", "enabled": True},
                ],
                "computer_nodes": [
                    {"id": "pc-skill", "label": "Skill Node", "status": "online", "runner_id": runner_id},
                ],
                "thread_workstations": [],
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

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
        f"/api/runners/{runner_id}/thread-workstations/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "pc-skill",
            "workstations": [
                {
                    "workstation_id": "codex-session-npc-skill",
                    "workstation_name": "NPC Skill Thread",
                    "workstation_status": "active",
                    "ai_provider_id": "codex",
                    "ai_provider_label": "Codex Desktop",
                    "cwd": "D:/ai合作产品",
                    "model": "gpt-5.4",
                    "skill_loadout": [
                        "ai-collab-productizer",
                        "continuous-orchestrator",
                        "handoff-path-output",
                    ],
                    "metadata": {
                        "connection_kind": "local",
                        "provider_family": "codex",
                    },
                }
            ],
        },
    )
    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]["workstations"][0]
    assert synced["ai_provider"] == "Codex Desktop"
    assert synced["metadata"]["skill_loadout"] == [
        "ai-collab-productizer",
        "continuous-orchestrator",
        "handoff-path-output",
    ]
    assert synced["metadata"]["connection_kind"] == "local"
    assert synced["metadata"]["provider_family"] == "codex"

    workspace_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    synced_workspace = next(
        item for item in workspace["workstations"] if item["workstation_id"] == "codex-session-npc-skill"
    )
    assert synced_workspace["ai_provider_label"] == "Codex Desktop"
    assert synced_workspace["metadata"]["skill_loadout"] == [
        "ai-collab-productizer",
        "continuous-orchestrator",
        "handoff-path-output",
    ]
