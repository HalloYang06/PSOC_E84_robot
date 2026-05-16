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


def test_boss_plan_rejects_historical_seat_alias_name_lookup() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Formal Seat",
        collaboration_config={
            "thread_workstations": [
                {"id": "boss-seat", "name": "Boss NPC", "status": "active", "ai_provider_id": "codex"},
                {"id": "backend-seat", "name": "Backend NPC", "status": "active", "ai_provider_id": "codex"},
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    response = client.post(
        f"/api/projects/{project_id}/boss-plans",
        headers=auth_headers(owner_token),
        json={
            "boss_seat_id": "Boss NPC",
            "goal": "Should fail on seat alias lookup.",
            "items": [
                {
                    "role": "Backend",
                    "target_seat_id": "Backend NPC",
                    "title": "Backend data contract",
                    "body": "Use formal seat ids only.",
                }
            ],
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "SEAT_NOT_FOUND"


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


def test_boss_plan_item_closes_from_followup_final_that_mentions_dispatch_id() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Followup Receipt",
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
            "goal": "Close from follow-up final.",
            "title": "Follow-up receipt plan",
            "status": "in_progress",
            "items": [
                {
                    "role": "Frontend",
                    "target_seat_id": "frontend-seat",
                    "target_name": "Frontend NPC",
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

    followup_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_result",
            "title": "[用户 → Frontend NPC] 对话指令",
            "body": f"Understood / Changed / Validated / Blocked / Next. Frontend NPC 已完成 dispatch {dispatch_id}。",
            "sender_type": "agent",
            "sender_id": "Frontend NPC",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "extra_data": {"source_message_id": "follow-up-command"},
        },
    )
    assert followup_response.status_code == 200, followup_response.text
    receipt_id = followup_response.json()["data"]["id"]

    read_response = client.get(f"/api/projects/{project_id}/boss-plans/{plan['id']}", headers=auth_headers(owner_token))
    assert read_response.status_code == 200, read_response.text
    closed_plan = read_response.json()["data"]
    assert closed_plan["status"] == "completed"
    assert closed_plan["items"][0]["status"] == "completed"
    assert closed_plan["items"][0]["receipt_message_id"] == receipt_id


def test_boss_plan_item_closes_immediately_when_followup_final_is_written() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Immediate Receipt",
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
            "goal": "Close as soon as a desktop final arrives.",
            "title": "Immediate follow-up receipt plan",
            "status": "in_progress",
            "items": [
                {
                    "role": "Frontend",
                    "target_seat_id": "frontend-seat",
                    "target_name": "Frontend NPC",
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

    followup_response = client.post(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        json={
            "project_id": project_id,
            "message_type": "agent_result",
            "title": "[用户 -> Frontend NPC] 对话指令",
            "body": f"Understood: done. Changed: final receipt for dispatch_message_id: {dispatch_id}. Validated: yes. Blocked: none. Next: boss review.",
            "sender_type": "agent",
            "sender_id": "Frontend NPC",
            "recipient_type": "human",
            "recipient_id": owner_user_id,
            "status": "completed",
            "extra_data": {"source_message_id": "follow-up-command"},
        },
    )
    assert followup_response.status_code == 200, followup_response.text
    receipt_id = followup_response.json()["data"]["id"]

    immediate_read = client.get(f"/api/projects/{project_id}/boss-plans/{plan['id']}", headers=auth_headers(owner_token))
    assert immediate_read.status_code == 200, immediate_read.text
    immediate_plan = immediate_read.json()["data"]
    assert immediate_plan["status"] == "completed"
    assert immediate_plan["items"][0]["status"] == "completed"
    assert immediate_plan["items"][0]["receipt_message_id"] == receipt_id


def test_boss_plan_item_becomes_blocked_from_failed_final_receipt() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Boss Plan Failed Receipt",
        collaboration_config={
            "thread_workstations": [
                {"id": "boss-seat", "name": "Boss NPC", "status": "active", "ai_provider_id": "codex"},
                {"id": "backend-seat", "name": "Backend NPC", "status": "active", "ai_provider_id": "codex"},
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
            "title": "Backend slice",
            "body": "Implement backend slice.",
            "sender_type": "agent",
            "sender_id": "boss-seat",
            "recipient_type": "thread_workstation",
            "recipient_id": "backend-seat",
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
            "goal": "Observe failed final receipt.",
            "title": "Failed receipt plan",
            "status": "in_progress",
            "items": [
                {
                    "role": "Backend",
                    "target_seat_id": "backend-seat",
                    "title": "Backend slice",
                    "body": "Do backend work.",
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
            "title": "Backend slice failed",
            "body": "Final failure receipt.",
            "sender_type": "agent",
            "sender_id": "backend-seat",
            "recipient_type": "agent",
            "recipient_id": "boss-seat",
            "status": "failed",
            "metadata": {
                "source_message_id": dispatch_id,
                "blocked_taxonomy": {
                    "failed": True,
                    "timed_out": False,
                    "auto_closed": False,
                    "retryable": True,
                    "log_available": False,
                    "split_suggested": True,
                    "exception_kind": "dependency_missing",
                    "blocked_reason_code": "dependency_missing",
                    "blocked_reason_label": "依赖环境缺失",
                    "evidence_complete": True,
                },
            },
        },
    )
    assert receipt_response.status_code == 200, receipt_response.text

    read_response = client.get(f"/api/projects/{project_id}/boss-plans/{plan['id']}", headers=auth_headers(owner_token))
    assert read_response.status_code == 200, read_response.text
    blocked_plan = read_response.json()["data"]
    assert blocked_plan["status"] == "blocked"
    assert blocked_plan["items"][0]["status"] == "failed"
