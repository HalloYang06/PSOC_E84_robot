from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, create_requirement, create_task, issue_session_token, register_user


client = TestClient(app)


def test_knowledge_list_requires_membership_and_filters_by_project() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(client, owner_token, name_prefix="Knowledge Permissions")
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)
    task = create_task(client, owner_token, project_id, title="Knowledge task")
    promoted_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Knowledge source requirement",
        status="accepted",
        requirement_type="thread_request",
    )
    promote_response = client.post(
        f"/api/requirements/{promoted_requirement['id']}/promote-to-knowledge",
        headers=auth_headers(owner_token),
        json={"actor_type": "human", "actor_id": owner_user_id, "target_type": "knowledge", "note": "promote to knowledge"},
    )
    assert promote_response.status_code == 200
    promoted_requirement_id = promoted_requirement["id"]

    plain_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Accepted requirement that should stay out of knowledge",
        status="accepted",
        requirement_type="thread_request",
    )

    member_user_id, member_email = register_user(client, f"member-{uuid4().hex[:8]}@example.com", "Knowledge Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"outsider-{uuid4().hex[:8]}@example.com",
        "Knowledge Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    member_response = client.get("/api/knowledge", headers=auth_headers(member_token))
    assert member_response.status_code == 200
    items = member_response.json()["data"]
    assert any(
        isinstance(item, dict) and item.get("id") == promoted_requirement_id for item in items
    )
    assert all(
        not (isinstance(item, dict) and item.get("id") == plain_requirement["id"]) for item in items
    )

    outsider_response = client.get("/api/knowledge", headers=auth_headers(outsider_token))
    assert outsider_response.status_code == 200
    outsider_items = outsider_response.json()["data"]
    assert all(
        not (isinstance(item, dict) and item.get("project_id") == project_id) for item in outsider_items
    )

    anonymous_response = client.get("/api/knowledge")
    assert anonymous_response.status_code == 401
