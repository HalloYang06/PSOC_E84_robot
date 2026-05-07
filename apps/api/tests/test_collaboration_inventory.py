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


def _create_project(token: str) -> str:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Collaborative Inventory {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/inventory.git",
            "local_git_url": "/workspace/inventory.git",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _add_owner_member(project_id: str, token: str, user_id: str) -> None:
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


def test_collaboration_inventory_crud_round_trips_all_entity_types() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    provider_response = client.post(
        f"/api/collaboration/projects/{project_id}/ai-providers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "codex",
            "label": "Codex",
            "kind": "openai",
            "enabled": True,
            "endpoint": "https://api.openai.com",
            "model": "gpt-5.1",
            "sort_order": 1,
        },
    )
    assert provider_response.status_code == 200
    assert provider_response.json()["data"]["id"] == "codex"

    node_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "pc-1",
            "label": "电脑1",
            "status": "online",
            "runner_id": "runner-codex",
            "connection_kind": "ssh",
            "workspace_root": "D:/work/inventory",
            "git_root": "D:/work/inventory/.git",
            "read_paths": "D:/work/inventory/src\nD:/work/inventory/docs",
            "write_paths": "D:/work/inventory/src, D:/work/inventory/tests",
            "host": "192.168.1.21",
            "os": "Windows 11",
            "sort_order": 0,
            "metadata": {"region": "lab-a"},
        },
    )
    assert node_response.status_code == 200
    assert node_response.json()["data"]["read_paths"] == ["D:/work/inventory/src", "D:/work/inventory/docs"]
    assert node_response.json()["data"]["write_paths"] == ["D:/work/inventory/src", "D:/work/inventory/tests"]
    assert node_response.json()["data"]["label"] == "电脑1"

    workstation_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "前端工位",
            "agent_id": "ai-fe-lead",
            "computer_node_id": "pc-1",
            "ai_provider_id": "codex",
            "status": "active",
            "description": "电脑1 上的 Codex 线程，负责前端与产品体验。",
        },
    )
    assert workstation_response.status_code == 200
    assert workstation_response.json()["data"]["computer_node_id"] == "pc-1"

    auth = {"Authorization": f"Bearer {token}"}

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers=auth,
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    assert [item["id"] for item in config["ai_providers"]] == ["codex"]
    assert [item["id"] for item in config["computer_nodes"]] == ["pc-1"]
    assert [item["name"] for item in config["thread_workstations"]] == ["前端工位"]

    update_provider_response = client.patch(
        f"/api/collaboration/projects/{project_id}/ai-providers/codex",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": False, "model": "gpt-5.2"},
    )
    assert update_provider_response.status_code == 200
    assert update_provider_response.json()["data"]["enabled"] is False

    update_node_response = client.patch(
        f"/api/collaboration/projects/{project_id}/computer-nodes/pc-1",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "status": "standby",
            "os": "Windows 11 Pro",
            "connection_kind": "local",
            "workspace_root": "D:/workspaces/pc-1",
            "git_root": "D:/workspaces/pc-1/repo",
            "read_paths": "D:/workspaces/pc-1/repo/apps/api",
            "write_paths": "D:/workspaces/pc-1/repo/apps/web",
        },
    )
    assert update_node_response.status_code == 200
    assert update_node_response.json()["data"]["status"] == "standby"
    assert update_node_response.json()["data"]["connection_kind"] == "local"
    assert update_node_response.json()["data"]["read_paths"] == ["D:/workspaces/pc-1/repo/apps/api"]
    assert update_node_response.json()["data"]["write_paths"] == ["D:/workspaces/pc-1/repo/apps/web"]

    update_workstation_response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/前端工位",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "idle", "notes": "切回待命"},
    )
    assert update_workstation_response.status_code == 200
    assert update_workstation_response.json()["data"]["status"] == "idle"

    provider_list_response = client.get(
        f"/api/collaboration/projects/{project_id}/ai-providers",
        headers=auth,
    )
    assert provider_list_response.status_code == 200
    assert provider_list_response.json()["data"][0]["model"] == "gpt-5.2"

    delete_workstation_response = client.delete(
        f"/api/collaboration/projects/{project_id}/thread-workstations/前端工位",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_workstation_response.status_code == 200

    delete_node_response = client.delete(
        f"/api/collaboration/projects/{project_id}/computer-nodes/pc-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_node_response.status_code == 200

    delete_provider_response = client.delete(
        f"/api/collaboration/projects/{project_id}/ai-providers/codex",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_provider_response.status_code == 200

    final_config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers=auth,
    )
    assert final_config_response.status_code == 200
    final_config = final_config_response.json()["data"]["collaboration_config"]
    assert final_config["ai_providers"] == []
    assert final_config["computer_nodes"] == []
    assert final_config["thread_workstations"] == []


def test_project_collaboration_config_preserves_computer_node_connection_details() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    patch_response = client.patch(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-robot-1",
                        "label": "Robot Node 1",
                        "status": "online",
                        "runner_id": "runner-robot-1",
                        "host": "10.0.0.21",
                        "os": "Windows 11",
                        "connection_kind": "remote-desktop",
                        "workspace_root": "D:/workspaces/robot-1",
                        "git_root": "D:/workspaces/robot-1/repo",
                        "read_paths": ["D:/workspaces/robot-1/repo", "D:/shared/docs"],
                        "write_paths": ["D:/workspaces/robot-1/repo/src", "D:/shared/inbox"],
                    }
                ],
                "ai_providers": [
                    {
                        "id": "claude",
                        "label": "Claude",
                        "kind": "anthropic",
                        "enabled": True,
                        "endpoint": "https://api.anthropic.com",
                        "model": "claude-opus-4.1",
                    }
                ],
                "thread_workstations": [
                    {
                        "name": "Robot execution",
                        "agent_id": "ai-robot-1",
                        "computer_node_id": "pc-robot-1",
                        "ai_provider_id": "claude",
                        "status": "active",
                        "description": "Robot control thread",
                        "notes": "Keeps the robot workspace in sync.",
                    }
                ],
            },
        },
    )
    assert patch_response.status_code == 200

    auth = {"Authorization": f"Bearer {token}"}

    project_response = client.get(
        f"/api/projects/{project_id}",
        headers=auth,
    )
    assert project_response.status_code == 200
    project = project_response.json()["data"]
    node = project["collaboration_config"]["computer_nodes"][0]
    assert node["connection_kind"] == "remote-desktop"
    assert node["workspace_root"] == "D:/workspaces/robot-1"
    assert node["git_root"] == "D:/workspaces/robot-1/repo"
    assert node["read_paths"] == ["D:/workspaces/robot-1/repo", "D:/shared/docs"]
    assert node["write_paths"] == ["D:/workspaces/robot-1/repo/src", "D:/shared/inbox"]

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers=auth,
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    assert [item["id"] for item in config["computer_nodes"]] == ["pc-robot-1"]
    assert [item["id"] for item in config["ai_providers"]] == ["claude"]
    assert [item["name"] for item in config["thread_workstations"]] == ["Robot execution"]


def test_project_collaboration_config_surfaces_runner_watch_state() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)
    runner_id = f"runner-watch-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Watch Runner",
            "capabilities": ["codex", "threads"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    patch_response = client.patch(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-watch-1",
                        "label": "Watch Node 1",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ],
                "ai_providers": [],
                "thread_workstations": [],
            },
        },
    )
    assert patch_response.status_code == 200

    config_response = client.get(
        f"/api/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert config_response.status_code == 200
    node = config_response.json()["data"]["collaboration_config"]["computer_nodes"][0]
    assert node["runner_watch_state"] == "watching"
    assert node["runner_effective_status"] == "online"
    assert node["runner_watch_fresh_seconds"] == 180
    assert isinstance(node["runner_heartbeat_age_seconds"], int)
    assert node["runner_last_heartbeat_at"]


def test_project_collaboration_config_preserves_custom_workshop_station_extras() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    station_payload = [
        {
            "id": "nanopi-station",
            "label": "NanoPi 工位",
            "icon": "板",
            "station": "开发工坊 / NanoPi 区",
            "mapScene": "map-farm",
            "mapLocation": "开发工坊东侧",
            "detail": "给 NanoPi 相关开发、烧录和验证做共用工位。",
            "runnerCapabilities": ["github-clone", "serial-open"],
            "aiResponsibilities": ["拉代码", "编译验证"],
            "npcRoleTemplates": ["NanoPi 负责人"],
            "assignmentKeywords": ["nanopi", "板卡"],
            "nextActions": ["补齐 NanoPi 环境", "绑定负责 NPC"],
            "approvalPolicy": "涉及真实板卡上电前先人工确认。",
            "riskLevel": "中",
        }
    ]

    patch_response = client.patch(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "collaboration_config": {
                "development_workshop_stations": station_payload,
                "computer_nodes": [],
                "ai_providers": [],
                "thread_workstations": [],
            }
        },
    )
    assert patch_response.status_code == 200

    auth = {"Authorization": f"Bearer {token}"}
    project_response = client.get(f"/api/projects/{project_id}", headers=auth)
    assert project_response.status_code == 200
    project = project_response.json()["data"]
    assert project["collaboration_config"]["development_workshop_stations"] == station_payload

    config_response = client.get(f"/api/collaboration/projects/{project_id}/config", headers=auth)
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    assert config["development_workshop_stations"] == station_payload


def test_thread_workstation_employee_metadata_round_trips_through_inventory() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    client.post(
        f"/api/collaboration/projects/{project_id}/ai-providers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "codex",
            "label": "Codex",
            "kind": "openai",
            "enabled": True,
            "endpoint": "https://api.openai.com",
            "model": "gpt-5.4",
        },
    ).raise_for_status()

    client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "pc-employee-1",
            "label": "Employee Node 1",
            "status": "online",
            "connection_kind": "ssh",
            "workspace_root": "D:/workspaces/employee-1",
            "git_root": "D:/workspaces/employee-1/repo",
        },
    ).raise_for_status()

    metadata = {
        "responsibility": "frontend",
        "model": "gpt-5.4",
        "permission_level": "L3",
        "read_paths": ["D:/workspaces/employee-1/repo", "D:/shared/specs"],
        "write_paths": ["D:/workspaces/employee-1/repo/apps/web", "D:/workspaces/employee-1/repo/packages/ui"],
    }

    create_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "frontend-employee",
            "name": "Frontend employee",
            "agent_id": "ai-fe-lead",
            "computer_node_id": "pc-employee-1",
            "ai_provider_id": "codex",
            "status": "active",
            "description": "Frontend AI employee for the main workspace.",
            "metadata": metadata,
        },
    )
    assert create_response.status_code == 200
    workstation_id = create_response.json()["data"]["id"]
    assert create_response.json()["data"]["metadata"] == metadata

    updated_metadata = {
        "responsibility": "full-stack",
        "model": "gpt-5.4.1",
        "permission_level": "L4",
        "read_paths": ["D:/workspaces/employee-1/repo", "D:/shared/specs", "D:/shared/docs"],
        "write_paths": ["D:/workspaces/employee-1/repo/apps/web"],
    }

    update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "status": "idle",
            "notes": "Shifting to a broader delivery scope.",
            "metadata": updated_metadata,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["metadata"] == updated_metadata

    auth = {"Authorization": f"Bearer {token}"}

    project_response = client.get(
        f"/api/projects/{project_id}",
        headers=auth,
    )
    assert project_response.status_code == 200
    project = project_response.json()["data"]
    workstation = project["collaboration_config"]["thread_workstations"][0]
    assert workstation["metadata"] == updated_metadata

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers=auth,
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    assert config["thread_workstations"][0]["metadata"] == updated_metadata


def test_thread_workstation_ai_employee_fields_round_trip_through_inventory() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    create_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "前端工位",
            "agent_id": "ai-fe-lead",
            "computer_node_id": "pc-1",
            "ai_provider_id": "codex",
            "status": "active",
            "role": "前端与协作界面",
            "default_model": "gpt-5.4",
            "permission": "L3",
            "read_dirs": "D:/workspaces/pc-1/repo\nD:/shared/specs",
            "write_dirs": ["D:/workspaces/pc-1/repo/apps/web", "D:/workspaces/pc-1/repo/apps/api"],
            "description": "电脑1 上的 Codex AI 员工。",
            "notes": "负责前端、交互和协作界面。",
        },
    )
    assert create_response.status_code == 200
    create_data = create_response.json()["data"]
    assert create_data["responsibility"] == "前端与协作界面"
    assert create_data["model"] == "gpt-5.4"
    assert create_data["permission_level"] == "L3"
    assert create_data["read_paths"] == ["D:/workspaces/pc-1/repo", "D:/shared/specs"]
    assert create_data["write_paths"] == ["D:/workspaces/pc-1/repo/apps/web", "D:/workspaces/pc-1/repo/apps/api"]

    update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/thread-workstations/前端工位",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "responsibility": "协作界面与联调",
            "model": "gpt-5.4.1",
            "permission_level": "L4",
            "read_paths": ["D:/workspaces/pc-1/repo", "D:/shared/designs"],
            "write_paths": "D:/workspaces/pc-1/repo/apps/web\nD:/workspaces/pc-1/repo/apps/api",
        },
    )
    assert update_response.status_code == 200
    update_data = update_response.json()["data"]
    assert update_data["responsibility"] == "协作界面与联调"
    assert update_data["model"] == "gpt-5.4.1"
    assert update_data["permission_level"] == "L4"
    assert update_data["read_paths"] == ["D:/workspaces/pc-1/repo", "D:/shared/designs"]
    assert update_data["write_paths"] == ["D:/workspaces/pc-1/repo/apps/web", "D:/workspaces/pc-1/repo/apps/api"]

    auth = {"Authorization": f"Bearer {token}"}

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers=auth,
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    workstation = config["thread_workstations"][0]
    assert workstation["name"] == "前端工位"
    assert workstation["responsibility"] == "协作界面与联调"
    assert workstation["model"] == "gpt-5.4.1"
    assert workstation["permission_level"] == "L4"
    assert workstation["read_paths"] == ["D:/workspaces/pc-1/repo", "D:/shared/designs"]
    assert workstation["write_paths"] == ["D:/workspaces/pc-1/repo/apps/web", "D:/workspaces/pc-1/repo/apps/api"]
