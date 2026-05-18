from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

from .helpers import auth_headers, issue_session_token, register_user


client = TestClient(app)


def test_runner_can_sync_device_interface_scan_to_bound_computer() -> None:
    email = f"device-scan-{uuid4().hex[:8]}@example.com"
    register_user(client, email, "Device Scan Owner")
    owner_token, _ = issue_session_token(client, email=email)
    runner_id = f"runner-device-scan-{uuid4().hex[:8]}"

    register_response = client.post(
        "/api/runners/register",
        json={
            "runner_id": runner_id,
            "runner_name": "Device Scan Runner",
            "capabilities": ["relay", "device-scan"],
            "hardware_access": False,
        },
    )
    assert register_response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers=auth_headers(owner_token),
        json={
            "name": f"Device Scan Project {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "nanopi-board",
                        "label": "NanoPi Linux 板",
                        "status": "online",
                        "runner_id": runner_id,
                        "os": "linux",
                    }
                ]
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

    sync_response = client.post(
        f"/api/runners/{runner_id}/device-interfaces/sync",
        headers={"X-Runner-Id": runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "nanopi-board",
            "platform": "linux",
            "host": "nanopi-test",
            "scanner_version": "test",
            "interfaces": [
                {
                    "id": "can:can0",
                    "kind": "can",
                    "name": "can0",
                    "status": "available",
                    "transport": "socketcan",
                    "details": {"bitrate": "500000"},
                    "read_capability": True,
                    "write_capability": "review_required",
                    "risk_level": "medium",
                },
                {
                    "id": "spi-can:kernel-driver",
                    "kind": "spi-can",
                    "name": "SPI-CAN driver clue",
                    "status": "available",
                    "transport": "socketcan-via-spi",
                    "details": {"driver_hint": "mcp251x"},
                    "read_capability": True,
                    "write_capability": "review_required",
                    "risk_level": "high",
                },
            ],
            "summary": {"total": 2, "can_count": 1, "spi-can_count": 1},
        },
    )
    assert sync_response.status_code == 200
    scan = sync_response.json()["data"]
    assert scan["interface_count"] == 2
    assert scan["interfaces"][0]["name"] == "can0"

    nodes_response = client.get(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers=auth_headers(owner_token),
    )
    assert nodes_response.status_code == 200
    node = nodes_response.json()["data"][0]
    device_scan = node["metadata"]["device_interface_scan"]
    assert device_scan["interface_count"] == 2
    assert {item["kind"] for item in device_scan["interfaces"]} == {"can", "spi-can"}
    assert device_scan["safety"]["write_actions"] == "review_required"


def test_runner_device_scan_rejects_unbound_runner() -> None:
    email = f"device-scan-deny-{uuid4().hex[:8]}@example.com"
    register_user(client, email, "Device Scan Deny Owner")
    owner_token, _ = issue_session_token(client, email=email)
    runner_id = f"runner-device-scan-deny-{uuid4().hex[:8]}"
    other_runner_id = f"runner-device-scan-other-{uuid4().hex[:8]}"
    for rid in (runner_id, other_runner_id):
        response = client.post(
            "/api/runners/register",
            json={
                "runner_id": rid,
                "runner_name": rid,
                "capabilities": ["device-scan"],
                "hardware_access": False,
            },
        )
        assert response.status_code == 200

    project_response = client.post(
        "/api/projects",
        headers=auth_headers(owner_token),
        json={
            "name": f"Device Scan Deny {uuid4().hex[:8]}",
            "project_type": "robotics",
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "linux-board",
                        "label": "Linux 板",
                        "status": "online",
                        "runner_id": runner_id,
                    }
                ]
            },
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]

    sync_response = client.post(
        f"/api/runners/{other_runner_id}/device-interfaces/sync",
        headers={"X-Runner-Id": other_runner_id},
        json={
            "project_id": project_id,
            "computer_node_id": "linux-board",
            "interfaces": [],
        },
    )
    assert sync_response.status_code == 404
    assert sync_response.json()["error"]["code"] == "RUNNER_BINDING_NOT_FOUND"
