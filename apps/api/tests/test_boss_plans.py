from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import add_project_member, auth_headers, create_project, issue_session_token, register_user


client = TestClient(app)


def test_boss_plan_records_items_and_rejects_local_knowledge_paths() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan",
        collaboration_config={
            "thread_workstations": [
                {"id": "boss-seat", "name": "Boss NPC", "status": "active", "ai_provider_id": "codex"},
                {"id": "backend-seat", "name": "Backend NPC", "status": "active", "ai_provider_id": "codex"},
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    bad_response = client.post(
        f"/api/projects/{project_id}/boss-plans",
        headers=auth_headers(owner_token),
        json={
            "boss_seat_id": "boss-seat",
            "goal": "Plan with bad path",
            "contract_path": r"D:\\english_a_agent\\docs\\contract.md",
        },
    )
    assert bad_response.status_code == 422
    assert bad_response.json()["error"]["code"] == "BAD_REPO_PATH"

    message_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Backend slice",
            "body": "Implement backend slice.",
            "sender_type": "agent",
            "sender_id": "boss-seat",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend-seat",
            "status": "queued",
        },
    )
    assert message_response.status_code == 200, message_response.text
    dispatch_id = message_response.json()["data"]["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/boss-plans",
        headers=auth_headers(owner_token),
        json={
            "boss_seat_id": "boss-seat",
            "goal": "Build the first product slice.",
            "title": "First slice",
            "status": "dispatched",
            "contract_path": "docs/ai-handoffs/project-operating-contract.md",
            "items": [
                {
                    "role": "Backend",
                    "target_seat_id": "backend-seat",
                    "target_name": "Backend NPC",
                    "title": "Backend data contract",
                    "body": "Use repo-relative paths only.",
                    "status": "queued",
                    "dispatch_message_id": dispatch_id,
                    "skills": ["backend-api"],
                    "knowledge_paths": ["README.md", "docs/mvp/api.md"],
                    "acceptance": "Return changed / validated / blocked / next.",
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    plan = create_response.json()["data"]
    assert plan["boss_seat_id"]
    assert plan["status"] == "dispatched"
    assert plan["items"][0]["target_seat_id"]
    assert plan["items"][0]["dispatch_message_id"] == dispatch_id
    assert plan["items"][0]["knowledge_paths"] == ["README.md", "docs/mvp/api.md"]

    member_user_id, member_email = register_user(client, f"boss-plan-member-{uuid4().hex[:8]}@example.com", "Boss Plan Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    read_response = client.get(f"/api/projects/{project_id}/boss-plans", headers=auth_headers(member_token))
    assert read_response.status_code == 200
    assert read_response.json()["data"][0]["id"] == plan["id"]

    update_response = client.patch(
        f"/api/projects/{project_id}/boss-plans/{plan['id']}/items/{plan['items'][0]['id']}",
        headers=auth_headers(member_token),
        json={"status": "in_progress"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["data"]["status"] == "dispatched"

    outsider_user_id, outsider_email = register_user(
        client,
        f"boss-plan-outsider-{uuid4().hex[:8]}@example.com",
        "Boss Plan Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)
    outsider_response = client.get(f"/api/projects/{project_id}/boss-plans", headers=auth_headers(outsider_token))
    assert outsider_response.status_code == 403


def test_boss_plan_status_follows_dispatch_message_status() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Sync",
        collaboration_config={
            "thread_workstations": [
                {"id": "boss-seat", "name": "Boss NPC", "status": "active", "ai_provider_id": "codex"},
                {"id": "backend-seat", "name": "Backend NPC", "status": "active", "ai_provider_id": "codex"},
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    message_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Backend implementation",
            "body": "Implement backend.",
            "sender_type": "agent",
            "sender_id": "boss-seat",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend-seat",
            "status": "queued",
        },
    )
    assert message_response.status_code == 200, message_response.text
    dispatch_id = message_response.json()["data"]["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/boss-plans",
        headers=auth_headers(owner_token),
        json={
            "boss_seat_id": "boss-seat",
            "goal": "Sync status from real dispatch.",
            "title": "Sync plan",
            "status": "dispatched",
            "items": [
                {
                    "role": "Backend",
                    "target_seat_id": "backend-seat",
                    "title": "Backend implementation",
                    "body": "Do the backend slice.",
                    "status": "queued",
                    "dispatch_message_id": dispatch_id,
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    plan = create_response.json()["data"]
    item = plan["items"][0]

    progress_response = client.patch(
        f"/api/collaboration/messages/{dispatch_id}",
        headers=auth_headers(owner_token),
        json={"status": "in_progress"},
    )
    assert progress_response.status_code == 200, progress_response.text
    read_progress = client.get(f"/api/projects/{project_id}/boss-plans/{plan['id']}", headers=auth_headers(owner_token))
    assert read_progress.status_code == 200, read_progress.text
    progress_plan = read_progress.json()["data"]
    assert progress_plan["status"] == "in_progress"
    assert progress_plan["items"][0]["id"] == item["id"]
    assert progress_plan["items"][0]["status"] == "in_progress"

    completed_response = client.patch(
        f"/api/collaboration/messages/{dispatch_id}",
        headers=auth_headers(owner_token),
        json={"status": "completed"},
    )
    assert completed_response.status_code == 200, completed_response.text
    read_completed = client.get(f"/api/projects/{project_id}/boss-plans", headers=auth_headers(owner_token))
    assert read_completed.status_code == 200, read_completed.text
    completed_plan = read_completed.json()["data"][0]
    assert completed_plan["id"] == plan["id"]
    assert completed_plan["status"] == "completed"
    assert completed_plan["items"][0]["status"] == "completed"


def test_boss_plan_item_closes_from_final_receipt_source_message() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Receipt",
        collaboration_config={
            "thread_workstations": [
                {"id": "boss-seat", "name": "Boss NPC", "status": "active", "ai_provider_id": "codex"},
                {"id": "frontend-seat", "name": "Frontend NPC", "status": "active", "ai_provider_id": "codex"},
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    dispatch_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "requirement_dispatch",
            "title": "Frontend slice",
            "body": "Implement frontend slice.",
            "sender_type": "agent",
            "sender_id": "boss-seat",
            "recipient_type": "thread_workstation",
            "recipient_id": "frontend-seat",
            "status": "in_progress",
        },
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch_id = dispatch_response.json()["data"]["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/boss-plans",
        headers=auth_headers(owner_token),
        json={
            "boss_seat_id": "boss-seat",
            "goal": "Close from final receipt.",
            "title": "Receipt plan",
            "status": "in_progress",
            "items": [
                {
                    "role": "Frontend",
                    "target_seat_id": "frontend-seat",
                    "title": "Frontend slice",
                    "body": "Do frontend work.",
                    "status": "in_progress",
                    "dispatch_message_id": dispatch_id,
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    plan = create_response.json()["data"]

    receipt_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_result",
            "title": "Frontend slice",
            "body": "Final result.",
            "sender_type": "agent",
            "sender_id": "frontend-seat",
            "recipient_type": "agent",
            "recipient_id": "boss-seat",
            "status": "completed",
            "extra_data": {"source_message_id": dispatch_id},
        },
    )
    assert receipt_response.status_code == 200, receipt_response.text
    receipt_id = receipt_response.json()["data"]["id"]

    read_response = client.get(f"/api/projects/{project_id}/boss-plans/{plan['id']}", headers=auth_headers(owner_token))
    assert read_response.status_code == 200, read_response.text
    closed_plan = read_response.json()["data"]
    assert closed_plan["status"] == "completed"
    assert closed_plan["items"][0]["status"] == "completed"
    assert closed_plan["items"][0]["receipt_message_id"] == receipt_id
