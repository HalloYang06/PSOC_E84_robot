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
            "name": f"Node Environment {suffix}",
            "project_type": "robotics",
            "github_url": "https://example.com/node-env.git",
            "local_git_url": "/workspace/node-env.git",
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


def test_computer_node_environment_fields_round_trip_through_inventory() -> None:
    token, user_id = _issue_session_token()
    project_id = _create_project(token)
    _add_owner_member(project_id, token, user_id)

    create_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "pc-lab-1",
            "label": "电脑实验位 1",
            "status": "online",
            "runner_id": "runner-lab-1",
            "connection_kind": "ssh",
            "workspace_root": "D:/workspace/lab-1",
            "git_root": "D:/workspace/lab-1/.git",
            "read_paths": ["D:/workspace/lab-1/src", "D:/workspace/lab-1/docs"],
            "write_paths": ["D:/workspace/lab-1/src", "D:/workspace/lab-1/tmp"],
            "host": "192.168.1.31",
            "os": "Windows 11",
            "metadata": {"rack": "A1"},
        },
    )
    assert create_response.status_code == 200
    create_data = create_response.json()["data"]
    assert create_data["connection_kind"] == "ssh"
    assert create_data["workspace_root"] == "D:/workspace/lab-1"
    assert create_data["read_paths"] == ["D:/workspace/lab-1/src", "D:/workspace/lab-1/docs"]
    assert create_data["metadata"]["rack"] == "A1"
    assert create_data["metadata"]["owner_user_id"] == user_id
    assert create_data["metadata"]["owner_email"] == "lead@example.com"
    assert create_data["metadata"]["source"] == "user_project_workbench"

    update_response = client.patch(
        f"/api/collaboration/projects/{project_id}/computer-nodes/pc-lab-1",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "status": "standby",
            "connection_kind": "local-ssh",
            "workspace_root": "D:/workspace/lab-1-v2",
            "git_root": "D:/workspace/lab-1-v2/.git",
            "read_paths": ["D:/workspace/lab-1-v2/src"],
            "write_paths": ["D:/workspace/lab-1-v2/src", "D:/workspace/lab-1-v2/scripts"],
        },
    )
    assert update_response.status_code == 200
    update_data = update_response.json()["data"]
    assert update_data["status"] == "standby"
    assert update_data["connection_kind"] == "local-ssh"
    assert update_data["workspace_root"] == "D:/workspace/lab-1-v2"
    assert update_data["write_paths"] == ["D:/workspace/lab-1-v2/src", "D:/workspace/lab-1-v2/scripts"]

    config_response = client.get(
        f"/api/collaboration/projects/{project_id}/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert config_response.status_code == 200
    config = config_response.json()["data"]["collaboration_config"]
    computer_node = config["computer_nodes"][0]
    assert computer_node["connection_kind"] == "local-ssh"
    assert computer_node["workspace_root"] == "D:/workspace/lab-1-v2"
    assert computer_node["git_root"] == "D:/workspace/lab-1-v2/.git"
    assert computer_node["read_paths"] == ["D:/workspace/lab-1-v2/src"]
    assert computer_node["write_paths"] == ["D:/workspace/lab-1-v2/src", "D:/workspace/lab-1-v2/scripts"]
