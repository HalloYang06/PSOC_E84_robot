from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def test_development_framework_is_platform_neutral_and_has_guardrails() -> None:
    token, _ = issue_session_token(client)
    project = create_project(client, token, name_prefix="Development Framework")

    response = client.get(f"/api/development/projects/{project['id']}/framework", headers=auth_headers(token))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project["id"]
    assert "software-project" in data["product_scope"]
    assert "embedded-board" in data["product_scope"]
    assert "browser" in data["runtime_scope"]
    assert "development-board" in data["runtime_scope"]

    module_ids = {item["id"] for item in data["modules"]}
    assert {
        "project-generator",
        "environment-builder",
        "wiring-bom",
        "debug-console",
        "ai-coach",
        "simulation-lab",
    }.issubset(module_ids)
    assert all(item["npc_role_templates"] for item in data["modules"])
    assert all(item["assignment_keywords"] for item in data["modules"])

    guardrail_ids = {item["id"] for item in data["guardrails"]}
    assert {"firmware_flash", "parameter_write", "actuator_motion"}.issubset(guardrail_ids)


def test_project_development_framework_respects_project_read_isolation() -> None:
    owner_token, _ = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Development Framework Isolation")
    outsider_email = f"development-outsider-{uuid4().hex[:8]}@example.com"
    register_user(client, outsider_email, "Development Outsider")
    outsider_token, _ = issue_session_token(client, outsider_email)

    anonymous_response = client.get(f"/api/development/projects/{project['id']}/framework")
    outsider_response = client.get(
        f"/api/development/projects/{project['id']}/framework",
        headers=auth_headers(outsider_token),
    )

    assert anonymous_response.status_code == 401
    assert outsider_response.status_code == 403
