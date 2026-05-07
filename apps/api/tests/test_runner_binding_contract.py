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


def test_runner_binding_contract_expects_explicit_bind_and_unbind_routes() -> None:
    token, user_id = _issue_session_token()
    runner_id = f"runner-{uuid4().hex[:8]}"
    project_id = None

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Binding Contract Runner",
            "capabilities": ["git", "python"],
            "hardware_access": True,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Binding Contract {uuid4().hex[:8]}",
            "project_type": "robotics",
            "github_url": "https://example.com/binding-contract.git",
            "local_git_url": "/workspace/binding-contract.git",
            "default_branch": "main",
            "develop_branch": "develop",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-1",
                        "label": "Binding Node 1",
                        "status": "online",
                        "host": "192.168.1.131",
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
        json={
            "project_id": project_id,
            "computer_node_id": "pc-1",
        },
    )
    assert bind_response.status_code == 200
    assert bind_response.json()["data"]["runner_id"] == runner_id
    assert bind_response.json()["data"]["project_id"] == project_id
    assert bind_response.json()["data"]["computer_node_id"] == "pc-1"

    workspace_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    assert workspace["binding_count"] == 1
    assert workspace["project_count"] == 1
    assert workspace["computer_node_count"] == 1
    assert workspace["bindings"][0]["computer_node_id"] == "pc-1"

    unbind_response = client.delete(
        f"/api/runners/{runner_id}/bindings/{project_id}/pc-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unbind_response.status_code == 200

    workspace_after_response = client.get(f"/api/runners/{runner_id}/workspace", headers={"Authorization": f"Bearer {token}"})
    assert workspace_after_response.status_code == 403
    assert workspace_after_response.json()["error"]["code"] == "PERMISSION_DENIED"
