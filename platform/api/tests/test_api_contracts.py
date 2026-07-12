from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _issue_session_token() -> str:
    response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _create_project(token: str) -> str:
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Git Contract Project", "default_branch": "main", "develop_branch": "develop"},
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def _route(path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"Route not found: {method} {path}")


def _dependency_names(route) -> set[str]:
    return {
        getattr(dependency.call, "__name__", str(dependency.call))
        for dependency in getattr(route.dependant, "dependencies", [])
    }


def _assert_paginated_response(payload: dict[str, object]) -> None:
    assert "data" in payload
    assert "meta" in payload
    assert "pagination" in payload

    data = payload["data"]
    meta = payload["meta"]
    pagination = payload["pagination"]

    assert isinstance(data, list)
    assert isinstance(meta, dict)
    assert isinstance(pagination, dict)
    assert isinstance(meta.get("request_id"), str)
    assert pagination["page"] == 1
    assert pagination["page_size"] == 20
    assert pagination["total"] >= len(data)


@pytest.mark.parametrize("path", ["/api/projects", "/api/tasks"])
def test_list_endpoints_follow_paginated_contract(path: str) -> None:
    token = _issue_session_token()
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    payload = response.json()
    _assert_paginated_response(payload)


def test_health_includes_request_id_and_status() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["version"] == "0.1.0"
    assert isinstance(payload["meta"]["request_id"], str)


def test_git_status_reports_safe_guardrails() -> None:
    anonymous = client.get("/api/git/status")
    assert anonymous.status_code == 401

    token = _issue_session_token()
    _create_project(token)
    response = client.get("/api/git/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    payload = response.json()["data"]
    assert payload["provider"] == "local"
    assert payload["dangerous_operations_blocked"] is True
    assert "status" in payload["supported"]
    assert "projects/{id}/execution" in payload["supported"]
    assert "projects/{id}/sync-preview" in payload["supported"]
    assert "projects/{id}/rollback-preview" in payload["supported"]
    assert "projects/{id}/sync-github" in payload["supported"]
    assert "projects/{id}/rollback" in payload["supported"]


def test_validation_errors_use_unified_error_shape() -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Validation Contract Project",
            "project_type": "robotics",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 401

    payload = response.json()
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert payload["error"]["message"] == "authentication required"
    assert isinstance(payload["meta"]["request_id"], str)
