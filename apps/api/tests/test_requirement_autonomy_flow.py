from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.requirement import Requirement, RequirementMessage
from app.db.session import SessionLocal
from app.main import app
from app.modules.requirements import service as requirement_service_module
from app.modules.requirements.schemas import RequirementDispatchRequest, RequirementFinalReplyRequest
from app.modules.requirements.service import (
    FOLLOW_UP_SUFFIX,
    MAINTENANCE_TEMPLATE_TITLES,
    add_requirement_final_reply,
    dispatch_requirement,
    sync_task_execution_to_requirements,
)
from tests.helpers import auth_headers, create_project, create_requirement, create_task, issue_session_token, setup_permission_workspace


client = TestClient(app)
PLATFORM_MAINLINE_TITLE = "平台主链自检"
THREAD_SCAN_TITLE = "复查电脑与线程扫描"
AUTONOMY_SUMMARY_TITLE = "平台自治推进摘要"


def _create_workstation(token: str, project_id: str) -> dict[str, object]:
    provider_response = client.post(
        f"/api/collaboration/projects/{project_id}/ai-providers",
        headers=auth_headers(token),
        json={
            "id": "codex",
            "label": "Codex",
            "kind": "openai",
            "enabled": True,
        },
    )
    assert provider_response.status_code == 200

    node_response = client.post(
        f"/api/collaboration/projects/{project_id}/computer-nodes",
        headers=auth_headers(token),
        json={
            "id": "pc-1",
            "label": "PC 1",
            "status": "online",
        },
    )
    assert node_response.status_code == 200

    workstation_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations",
        headers=auth_headers(token),
        json={
            "id": "frontend-seat",
            "name": "Frontend Seat",
            "agent_id": "agent-ui",
            "computer_node_id": "pc-1",
            "ai_provider_id": "codex",
            "status": "active",
        },
    )
    assert workstation_response.status_code == 200
    return workstation_response.json()["data"]


def test_requirement_dispatch_and_final_reply_form_minimal_autonomy_loop() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Autonomy")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]
    outsider_token = workspace["outsider_token"]
    requirement_id = workspace["requirement_id"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    dispatch_response = client.post(
        f"/api/requirements/{requirement_id}/dispatch",
        headers=auth_headers(member_token),
        json={
            "target_type": "workstation",
            "target_id": workstation_id,
            "note": "Dispatch this maintenance task to the frontend seat.",
            "status": "queued",
        },
    )
    assert dispatch_response.status_code == 200
    dispatch_payload = dispatch_response.json()["data"]
    assert dispatch_payload["requirement"]["status"] == "queued"
    assert dispatch_payload["requirement"]["to_agent"] == workstation_id
    assert dispatch_payload["message"]["message_type"] == "requirement_dispatch"
    assert dispatch_payload["message"]["recipient_type"] == "workstation"
    assert dispatch_payload["message"]["recipient_id"] == workstation_id
    assert dispatch_payload["message"]["status"] == "queued"

    in_progress_response = client.post(
        f"/api/requirements/{requirement_id}/final-reply",
        headers=auth_headers(member_token),
        json={
            "sender_type": "agent",
            "sender_id": "agent-ui",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "message": "Frontend seat acknowledged and is working on it.",
            "status": "in_progress",
        },
    )
    assert in_progress_response.status_code == 200
    in_progress_payload = in_progress_response.json()["data"]
    assert in_progress_payload["reply"]["status_after_reply"] == "in_progress"
    assert in_progress_payload["message"]["message_type"] == "requirement_final_reply"
    assert in_progress_payload["message"]["status"] == "in_progress"
    assert in_progress_payload["message"]["recipient_id"] == workstation_id

    done_response = client.post(
        f"/api/requirements/{requirement_id}/final-reply",
        headers=auth_headers(member_token),
        json={
            "sender_type": "agent",
            "sender_id": "agent-ui",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "message": "Frontend seat finished and returned the final result.",
            "status": "done",
        },
    )
    assert done_response.status_code == 200
    done_payload = done_response.json()["data"]
    assert done_payload["reply"]["status_after_reply"] == "done"
    assert done_payload["message"]["status"] == "done"

    requirement_response = client.get(
        f"/api/requirements/{requirement_id}",
        headers=auth_headers(member_token),
    )
    assert requirement_response.status_code == 200
    requirement_payload = requirement_response.json()["data"]
    assert requirement_payload["status"] in {"queued", "done"}
    assert requirement_payload["response_count"] >= 3
    assert requirement_payload["messages"][-1]["status_after_reply"] == "done"

    outsider_dispatch = client.post(
        f"/api/requirements/{requirement_id}/dispatch",
        headers=auth_headers(outsider_token),
        json={
            "target_type": "workstation",
            "target_id": workstation_id,
            "note": "Outsider should not dispatch",
        },
    )
    assert outsider_dispatch.status_code == 403
    assert outsider_dispatch.json()["error"]["code"] == "PERMISSION_DENIED"

    outsider_reply = client.post(
        f"/api/requirements/{requirement_id}/final-reply",
        headers=auth_headers(outsider_token),
        json={
            "sender_type": "agent",
            "sender_id": "agent-ui",
            "recipient_type": "workstation",
            "recipient_id": workstation_id,
            "message": "Outsider should not reply",
            "status": "done",
        },
    )
    assert outsider_reply.status_code == 403
    assert outsider_reply.json()["error"]["code"] == "PERMISSION_DENIED"


def test_dispatch_requirement_reuses_existing_message_when_dedupe_key_repeats() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Dispatch Dedupe")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    requirement_id = workspace["requirement_id"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]
    dedupe_key = f"auto_follow_up_dispatch:{requirement_id}"
    payload = RequirementDispatchRequest(
        actor_type="agent",
        actor_id="system-autonomy",
        target_type="workstation",
        target_id=workstation_id,
        note="Dispatch this requirement exactly once.",
        status="queued",
        title="Auto follow-up dispatch",
        body="This auto dispatch should be idempotent.",
    )

    with SessionLocal() as db:
        first = dispatch_requirement(db, requirement_id, payload, dedupe_key=dedupe_key)
        second = dispatch_requirement(db, requirement_id, payload, dedupe_key=dedupe_key)

        assert first["message"].id == second["message"].id
        assert first["message"].recipient_id == workstation_id

        dispatch_messages = list(
            db.scalars(
                select(CollaborationMessage).where(
                    CollaborationMessage.requirement_id == requirement_id,
                    CollaborationMessage.message_type == "requirement_dispatch",
                )
            )
        )
        assert len(dispatch_messages) == 1
        assert dispatch_messages[0].dedupe_key == dedupe_key


def test_add_requirement_final_reply_reuses_existing_result_when_dedupe_key_repeats() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Final Reply Dedupe")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    requirement_id = workspace["requirement_id"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]
    dedupe_key = f"auto_final_reply:{requirement_id}:done"
    payload = RequirementFinalReplyRequest(
        sender_type="agent",
        sender_id=workstation_id,
        recipient_type="project",
        recipient_id=project_id,
        message="Autonomy already received the final reply.",
        status="done",
        title="Auto final reply",
    )

    with SessionLocal() as db:
        first = add_requirement_final_reply(db, requirement_id, payload, dedupe_key=dedupe_key)
        second = add_requirement_final_reply(db, requirement_id, payload, dedupe_key=dedupe_key)

        assert first["message"].id == second["message"].id
        assert first["reply"].id == second["reply"].id

        requirement_row = db.get(Requirement, requirement_id)
        assert requirement_row is not None
        assert requirement_row.status == "done"
        assert requirement_row.response_count == 2

        reply_rows = list(
            db.scalars(
                select(RequirementMessage).where(
                    RequirementMessage.requirement_id == requirement_id,
                    RequirementMessage.status_after_reply == "done",
                )
            )
        )
        assert len(reply_rows) == 1

        final_reply_messages = list(
            db.scalars(
                select(CollaborationMessage).where(
                    CollaborationMessage.requirement_id == requirement_id,
                    CollaborationMessage.message_type == "requirement_final_reply",
                )
            )
        )
        assert len(final_reply_messages) == 1
        assert final_reply_messages[0].dedupe_key == dedupe_key


def test_add_requirement_final_reply_dedupe_conflict_keeps_outer_pending_changes(monkeypatch) -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Final Reply Savepoint")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    requirement_id = workspace["requirement_id"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]
    dedupe_key = f"auto_final_reply:{requirement_id}:done"
    payload = RequirementFinalReplyRequest(
        sender_type="agent",
        sender_id=workstation_id,
        recipient_type="project",
        recipient_id=project_id,
        message="Autonomy already received the final reply.",
        status="done",
        title="Auto final reply",
    )

    with SessionLocal() as seed_db:
        seeded = add_requirement_final_reply(seed_db, requirement_id, payload, dedupe_key=dedupe_key)
        seeded_message_id = seeded["message"].id
        seeded_reply_id = seeded["reply"].id

    existing_call_count = {"value": 0}
    original_existing = requirement_service_module._existing_final_reply_result

    def fake_existing(db, requirement_id, *, dedupe_key, payload):
        existing_call_count["value"] += 1
        if existing_call_count["value"] == 1:
            return None
        return original_existing(db, requirement_id, dedupe_key=dedupe_key, payload=payload)

    def fake_create_requirement_collaboration_message(*args, **kwargs):
        raise IntegrityError("forced dedupe collision", None, None)

    monkeypatch.setattr(requirement_service_module, "_existing_final_reply_result", fake_existing)
    monkeypatch.setattr(
        requirement_service_module.repo,
        "create_requirement_collaboration_message",
        fake_create_requirement_collaboration_message,
    )

    with SessionLocal() as db:
        outer_message = CollaborationMessage(
            project_id=project_id,
            requirement_id=requirement_id,
            message_type="comment_message",
            title="Outer pending message",
            body="This pending write should survive the inner dedupe collision.",
            sender_type="agent",
            sender_id="outer-agent",
            recipient_type="project",
            recipient_id=project_id,
            status="open",
        )
        db.add(outer_message)
        db.flush()
        outer_message_id = outer_message.id

        result = add_requirement_final_reply(db, requirement_id, payload, dedupe_key=dedupe_key)
        assert result["message"].id == seeded_message_id
        assert result["reply"].id == seeded_reply_id

        db.commit()

    with SessionLocal() as verify_db:
        assert verify_db.get(CollaborationMessage, outer_message_id) is not None
        requirement_row = verify_db.get(Requirement, requirement_id)
        assert requirement_row is not None
        assert requirement_row.response_count == 2

        reply_rows = list(
            verify_db.scalars(
                select(RequirementMessage).where(
                    RequirementMessage.requirement_id == requirement_id,
                    RequirementMessage.status_after_reply == "done",
                )
            )
        )
        assert len(reply_rows) == 1


def test_requirement_dispatch_rejects_unknown_target() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Dispatch Target")
    requirement_id = workspace["requirement_id"]
    member_token = workspace["member_token"]

    response = client.post(
        f"/api/requirements/{requirement_id}/dispatch",
        headers=auth_headers(member_token),
        json={
            "target_type": "workstation",
            "target_id": "missing-seat",
            "note": "This workstation does not exist.",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TARGET_NOT_FOUND"


def test_requirement_autonomy_sweep_dispatches_and_creates_follow_up_for_platform_templates() -> None:
    assert PLATFORM_MAINLINE_TITLE in MAINTENANCE_TEMPLATE_TITLES
    workspace = setup_permission_workspace(client, name_prefix="Requirement Autonomy Sweep")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="Autonomy sweep should dispatch to real workstation, then complete and create one follow-up.",
        expected_output="Dispatch to real workstation and produce a completed follow-up chain.",
        opening_message="Please run a mainline platform self-check.",
    )
    requirement_id = requirement["id"]

    report_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
        headers=auth_headers(member_token),
        json={
            "requirement_id": requirement_id,
            "message_type": "agent_report",
            "title": PLATFORM_MAINLINE_TITLE,
            "body": "Frontend seat completed the platform mainline self-check.",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "done",
        },
    )
    assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200
    sweep_payload = sweep_response.json()["data"]
    assert sweep_payload["requirements"] >= 1
    assert any(item["requirement_id"] == requirement_id and item["action"] == "dispatch" for item in sweep_payload["affected"])
    assert any(
        item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up"
        for item in sweep_payload["affected"]
    )
    assert any(
        item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up_dispatch"
        for item in sweep_payload["affected"]
    )

    requirement_response = client.get(
        f"/api/requirements/{requirement_id}",
        headers=auth_headers(member_token),
    )
    assert requirement_response.status_code == 200
    requirement_payload = requirement_response.json()["data"]
    assert requirement_payload["status"] in {"queued", "done"}
    assert requirement_payload["to_agent"] == workstation_id

    messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": requirement_id},
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()["data"]
    dispatch_messages = [item for item in messages if item["message_type"] == "requirement_dispatch"]
    final_messages = [item for item in messages if item["message_type"] == "requirement_final_reply"]
    assert len(dispatch_messages) == 1
    assert dispatch_messages[0]["recipient_type"] == "workstation"
    assert dispatch_messages[0]["recipient_id"] == requirement_payload["to_agent"]
    assert dispatch_messages[0]["status"] in {"queued", "in_progress"}
    assert len(final_messages) in {0, 1}
    if final_messages:
        assert final_messages[0]["status"] == "done"

    project_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert project_messages_response.status_code == 200
    project_messages = project_messages_response.json()["data"]
    sweep_summaries = [
        item
        for item in project_messages
        if item["message_type"] == "agent_report" and item.get("title") == AUTONOMY_SUMMARY_TITLE
    ]
    assert sweep_summaries
    assert "本轮自治推进完成" in sweep_summaries[0]["body"]
    assert "续推后续复查 1 条" in sweep_summaries[0]["body"]

    follow_up_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert follow_up_response.status_code == 200
    follow_ups = [
        item
        for item in follow_up_response.json()["data"]
        if item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 1
    assert follow_ups[0]["status"] == "queued"
    assert follow_ups[0]["to_agent"] == workstation_id

    follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": follow_ups[0]["id"]},
    )
    assert follow_up_messages_response.status_code == 200
    follow_up_messages = follow_up_messages_response.json()["data"]
    follow_up_dispatches = [item for item in follow_up_messages if item["message_type"] == "requirement_dispatch"]
    assert len(follow_up_dispatches) == 1
    assert follow_up_dispatches[0]["recipient_type"] == "workstation"
    assert follow_up_dispatches[0]["recipient_id"] == workstation_id
    assert follow_up_dispatches[0]["status"] == "queued"

    with SessionLocal() as db:
        follow_up_row = db.get(Requirement, follow_ups[0]["id"])
        assert follow_up_row is not None
        assert follow_up_row.follow_up_from_requirement_id == requirement_id


def test_requirement_autonomy_sweep_continues_done_maintenance_requirement() -> None:
    assert THREAD_SCAN_TITLE in MAINTENANCE_TEMPLATE_TITLES
    workspace = setup_permission_workspace(client, name_prefix="Requirement Done Follow Up")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=THREAD_SCAN_TITLE,
        requirement_type="thread_request",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Previous round is complete, continue one follow-up review cycle.",
        expected_output="Continue thread/computer scan review and provide a minimal acknowledgement.",
        opening_message="Continue the computer and thread scan review.",
    )
    requirement_id = requirement["id"]

    report_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
        headers=auth_headers(member_token),
        json={
            "requirement_id": requirement_id,
            "message_type": "agent_report",
            "title": f"{THREAD_SCAN_TITLE} done",
            "body": "Thread liaison completed one review cycle.",
            "status": "done",
        },
    )
    assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200
    sweep_payload = sweep_response.json()["data"]
    assert any(
        item["title"] == f"{THREAD_SCAN_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up"
        for item in sweep_payload["affected"]
    )
    assert any(
        item["title"] == f"{THREAD_SCAN_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up_dispatch"
        for item in sweep_payload["affected"]
    )

    follow_up_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert follow_up_response.status_code == 200
    follow_ups = [
        item
        for item in follow_up_response.json()["data"]
        if item["title"] == f"{THREAD_SCAN_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 1
    assert follow_ups[0]["status"] == "queued"
    follow_up_target = follow_ups[0]["to_agent"]
    assert follow_up_target == workstation_id
    follow_up_id = follow_ups[0]["id"]
    follow_up_title = follow_ups[0]["title"]

    follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": follow_up_id},
    )
    assert follow_up_messages_response.status_code == 200
    follow_up_messages = follow_up_messages_response.json()["data"]
    follow_up_dispatches = [item for item in follow_up_messages if item["message_type"] == "requirement_dispatch"]
    assert len(follow_up_dispatches) == 1
    assert follow_up_dispatches[0]["recipient_type"] == "workstation"
    assert follow_up_dispatches[0]["recipient_id"] == follow_up_target
    assert follow_up_dispatches[0]["status"] == "queued"

    second_sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert second_sweep_response.status_code == 200
    second_sweep_payload = second_sweep_response.json()["data"]
    assert second_sweep_payload["followups"] == 0
    assert not any(item["title"] == follow_up_title and item["action"] == "follow_up" for item in second_sweep_payload["affected"])
    assert not any(
        item["title"] == follow_up_title and item["action"] == "follow_up_dispatch"
        for item in second_sweep_payload["affected"]
    )

    second_follow_up_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert second_follow_up_response.status_code == 200
    second_follow_ups = [
        item
        for item in second_follow_up_response.json()["data"]
        if item["title"] == follow_up_title
    ]
    assert len(second_follow_ups) == 1

    second_follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": follow_up_id},
    )
    assert second_follow_up_messages_response.status_code == 200
    second_follow_up_messages = second_follow_up_messages_response.json()["data"]
    second_follow_up_dispatches = [
        item for item in second_follow_up_messages if item["message_type"] == "requirement_dispatch"
    ]
    assert len(second_follow_up_dispatches) == 1

    with SessionLocal() as db:
        follow_up_row = db.get(Requirement, follow_up_id)
        assert follow_up_row is not None
        assert follow_up_row.follow_up_from_requirement_id == requirement_id


def test_requirement_autonomy_sweep_creates_follow_ups_per_task() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Follow Up Scope")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]
    secondary_task = create_task(
        client,
        owner_token,
        project_id=project_id,
        title="Secondary maintenance task",
        description="Make sure task-scoped follow-up de-dupe does not cross wires.",
    )

    first_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Primary maintenance loop already completed one round.",
        expected_output="Continue the primary maintenance loop.",
        opening_message="Continue the primary maintenance loop.",
    )
    second_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=secondary_task["id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Secondary maintenance loop also completed one round.",
        expected_output="Continue the secondary maintenance loop.",
        opening_message="Continue the secondary maintenance loop.",
    )

    for requirement in (first_requirement, second_requirement):
        report_response = client.post(
            f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
            headers=auth_headers(member_token),
            json={
                "requirement_id": requirement["id"],
                "message_type": "agent_report",
                "title": f"{requirement['title']} done",
                "body": "Maintenance round completed and should continue.",
                "status": "done",
            },
        )
        assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200
    sweep_payload = sweep_response.json()["data"]
    assert sweep_payload["followups"] == 2

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    follow_ups = [
        item
        for item in requirements_response.json()["data"]
        if item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 2
    assert {item["task_id"] for item in follow_ups} == {workspace["task_id"], secondary_task["id"]}
    assert all(item["status"] == "queued" for item in follow_ups)
    assert all(item["to_agent"] == workstation_id for item in follow_ups)

    with SessionLocal() as db:
        follow_up_rows = [db.get(Requirement, item["id"]) for item in follow_ups]
        assert all(row is not None for row in follow_up_rows)
        lineage_pairs = {
            (row.task_id, row.follow_up_from_requirement_id)  # type: ignore[union-attr]
            for row in follow_up_rows
        }
    assert lineage_pairs == {
        (workspace["task_id"], first_requirement["id"]),
        (secondary_task["id"], second_requirement["id"]),
    }


def test_requirement_autonomy_sweep_keeps_same_task_siblings_on_distinct_follow_ups() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Same Task Follow Up")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    first_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=THREAD_SCAN_TITLE,
        requirement_type="thread_request",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="First same-task maintenance sibling is done.",
        expected_output="Keep the first sibling on its own follow-up.",
        opening_message="Continue the first same-task sibling.",
    )
    second_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=THREAD_SCAN_TITLE,
        requirement_type="thread_request",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Second same-task maintenance sibling is done too.",
        expected_output="Keep the second sibling on a distinct follow-up.",
        opening_message="Continue the second same-task sibling.",
    )

    for requirement in (first_requirement, second_requirement):
        report_response = client.post(
            f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
            headers=auth_headers(member_token),
            json={
                "requirement_id": requirement["id"],
                "message_type": "agent_report",
                "title": f"{THREAD_SCAN_TITLE} done",
                "body": "This same-task sibling completed one review cycle.",
                "status": "done",
            },
        )
        assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200
    sweep_payload = sweep_response.json()["data"]
    assert sweep_payload["followups"] == 2

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    follow_ups = [
        item
        for item in requirements_response.json()["data"]
        if item["title"] == f"{THREAD_SCAN_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 2
    assert all(item["task_id"] == workspace["task_id"] for item in follow_ups)
    assert all(item["status"] == "queued" for item in follow_ups)
    assert all(item["to_agent"] == workstation_id for item in follow_ups)

    with SessionLocal() as db:
        follow_up_rows = [db.get(Requirement, item["id"]) for item in follow_ups]
        assert all(row is not None for row in follow_up_rows)
        assert {row.follow_up_from_requirement_id for row in follow_up_rows} == {
            first_requirement["id"],
            second_requirement["id"],
        }


def test_requirement_task_sync_recovers_missing_follow_up_after_done_reply() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Follow Up Recovery")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="queued",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Recover follow-up creation after a partial runner completion failure.",
        expected_output="Create the missing follow-up and queue it for the same workstation.",
        opening_message="Recover the missing follow-up after the done reply landed.",
    )

    final_reply_response = client.post(
        f"/api/requirements/{requirement['id']}/final-reply",
        headers=auth_headers(member_token),
        json={
            "sender_type": "agent",
            "sender_id": workstation_id,
            "recipient_type": "project",
            "recipient_id": project_id,
            "message": "The maintenance round is done; recover the next follow-up.",
            "status": "done",
            "title": requirement["title"],
        },
    )
    assert final_reply_response.status_code == 200

    with SessionLocal() as db:
        recovery = sync_task_execution_to_requirements(
            db,
            task_id=workspace["task_id"],
            project_id=project_id,
            workstation_id=workstation_id,
            agent_id="agent-ui",
            reply_status="done",
            message="Retrying the same completion should still create the missing follow-up.",
            title=requirement["title"],
            actor_id="runner-retry",
        )

    assert not any(item["requirement_id"] == requirement["id"] and item["action"] == "final_reply" for item in recovery["affected"])
    assert any(
        item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up"
        for item in recovery["affected"]
    )
    assert any(
        item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}" and item["action"] == "follow_up_dispatch"
        for item in recovery["affected"]
    )

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    follow_ups = [
        item
        for item in requirements_response.json()["data"]
        if item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 1
    assert follow_ups[0]["task_id"] == workspace["task_id"]
    assert follow_ups[0]["status"] == "queued"
    assert follow_ups[0]["to_agent"] == workstation_id

    follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": follow_ups[0]["id"]},
    )
    assert follow_up_messages_response.status_code == 200
    follow_up_dispatches = [
        item
        for item in follow_up_messages_response.json()["data"]
        if item["message_type"] == "requirement_dispatch"
    ]
    assert len(follow_up_dispatches) == 1
    assert follow_up_dispatches[0]["recipient_id"] == workstation_id

    with SessionLocal() as db:
        follow_up_row = db.get(Requirement, follow_ups[0]["id"])
        assert follow_up_row is not None
        assert follow_up_row.follow_up_from_requirement_id == requirement["id"]


def test_requirement_autonomy_sweep_reuses_legacy_follow_up_without_lineage() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Legacy Follow Up")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="done",
        from_agent="human-chief",
        to_agent=workstation_id,
        context_summary="Legacy data may already have a follow-up row without lineage.",
        expected_output="Reuse the legacy follow-up instead of creating a duplicate.",
        opening_message="Recover legacy follow-up lineage.",
    )

    legacy_follow_up = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title=f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}",
        requirement_type="git_dispatch_ai",
        status="waiting_response",
        from_agent="legacy-bot",
        to_agent=workstation_id,
        context_summary="This is an older follow-up row created before lineage existed.",
        expected_output="Dispatch this existing follow-up once and reuse it.",
        opening_message="Legacy follow-up placeholder.",
    )

    report_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
        headers=auth_headers(member_token),
        json={
            "requirement_id": requirement["id"],
            "message_type": "agent_report",
            "title": PLATFORM_MAINLINE_TITLE,
            "body": "Legacy source requirement is done and should continue through the existing follow-up.",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "done",
        },
    )
    assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    follow_ups = [
        item
        for item in requirements_response.json()["data"]
        if item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 1
    assert follow_ups[0]["id"] == legacy_follow_up["id"]

    follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": legacy_follow_up["id"]},
    )
    assert follow_up_messages_response.status_code == 200
    follow_up_dispatches = [
        item
        for item in follow_up_messages_response.json()["data"]
        if item["message_type"] == "requirement_dispatch"
    ]
    assert len(follow_up_dispatches) == 1
    assert follow_up_dispatches[0]["recipient_id"] == workstation_id

    with SessionLocal() as db:
        follow_up_row = db.get(Requirement, legacy_follow_up["id"])
        assert follow_up_row is not None
        assert follow_up_row.follow_up_from_requirement_id == requirement["id"]


def test_requirement_autonomy_sweep_backfills_minimal_ack_once_when_progress_exists() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Minimal Ack")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title="Minimal progress ack requirement",
        requirement_type="thread_request",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="Capture a minimal progress acknowledgement before a final reply.",
        expected_output="Dispatch to real workstation, then write one in_progress ack.",
        opening_message="Start and report minimal progress first.",
    )
    requirement_id = requirement["id"]

    report_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
        headers=auth_headers(member_token),
        json={
            "requirement_id": requirement_id,
            "message_type": "agent_report",
            "title": "Progress started",
            "body": "Frontend seat started implementation and is still in progress.",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "in_progress",
        },
    )
    assert report_response.status_code == 200

    first_sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert first_sweep_response.status_code == 200
    first_sweep_payload = first_sweep_response.json()["data"]
    assert first_sweep_payload["minimal_acks"] == 1
    assert any(item["requirement_id"] == requirement_id and item["action"] == "dispatch" for item in first_sweep_payload["affected"])
    assert any(item["requirement_id"] == requirement_id and item["action"] == "minimal_ack" for item in first_sweep_payload["affected"])

    first_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": requirement_id},
    )
    assert first_messages_response.status_code == 200
    first_messages = first_messages_response.json()["data"]
    first_dispatches = [item for item in first_messages if item["message_type"] == "requirement_dispatch"]
    first_progress_acks = [item for item in first_messages if item["message_type"] == "requirement_progress_ack"]
    first_finals = [item for item in first_messages if item["message_type"] == "requirement_final_reply"]
    assert len(first_dispatches) == 1
    assert len(first_progress_acks) == 1
    assert first_progress_acks[0]["status"] == "in_progress"
    assert not first_finals

    second_sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert second_sweep_response.status_code == 200
    second_sweep_payload = second_sweep_response.json()["data"]
    assert second_sweep_payload["minimal_acks"] == 0
    assert not any(item["requirement_id"] == requirement_id and item["action"] == "minimal_ack" for item in second_sweep_payload["affected"])

    second_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(member_token),
        params={"project_id": project_id, "requirement_id": requirement_id},
    )
    assert second_messages_response.status_code == 200
    second_messages = second_messages_response.json()["data"]
    second_progress_acks = [item for item in second_messages if item["message_type"] == "requirement_progress_ack"]
    second_finals = [item for item in second_messages if item["message_type"] == "requirement_final_reply"]
    assert len(second_progress_acks) == 1
    assert second_progress_acks[0]["status"] == "in_progress"
    assert not second_finals


def test_requirement_autonomy_sweep_keeps_follow_up_limited_to_maintenance_templates() -> None:
    workspace = setup_permission_workspace(client, name_prefix="Requirement Non Maintenance")
    project_id = workspace["project_id"]
    owner_token = workspace["owner_token"]
    member_token = workspace["member_token"]

    workstation = _create_workstation(owner_token, project_id)
    workstation_id = workstation["id"]

    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=workspace["task_id"],
        title="General integration check",
        requirement_type="thread_request",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="This is not one of the maintenance templates.",
        expected_output="Backfill final reply when done, but do not create follow-up.",
        opening_message="Run once and report done.",
    )
    requirement_id = requirement["id"]

    report_response = client.post(
        f"/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages",
        headers=auth_headers(member_token),
        json={
            "requirement_id": requirement_id,
            "message_type": "agent_report",
            "title": "General integration check done",
            "body": "Frontend seat completed the general integration check.",
            "recipient_type": "project",
            "recipient_id": project_id,
            "status": "done",
        },
    )
    assert report_response.status_code == 200

    sweep_response = client.post(
        f"/api/requirements/projects/{project_id}/autonomy-sweep",
        headers=auth_headers(member_token),
    )
    assert sweep_response.status_code == 200
    sweep_payload = sweep_response.json()["data"]
    assert any(item["requirement_id"] == requirement_id and item["action"] == "dispatch" for item in sweep_payload["affected"])
    assert any(item["requirement_id"] == requirement_id and item["action"] == "final_reply" for item in sweep_payload["affected"])
    assert not any(item["action"] == "follow_up" and item["title"].startswith("General integration check") for item in sweep_payload["affected"])

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(member_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    generated_items = [
        item
        for item in requirements_response.json()["data"]
        if item["id"] != requirement_id and item["title"].startswith("General integration check")
    ]
    assert not generated_items


def test_runner_completion_backfills_requirement_final_reply_and_follow_up() -> None:
    owner_token, _ = issue_session_token(client)
    runner_register = client.post(
        "/api/runners/register",
        json={
            "runner_id": "runner-requirement-bridge",
            "runner_name": "Requirement Bridge Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert runner_register.status_code == 200

    project = create_project(client, owner_token, name_prefix="Requirement Bridge Project")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-bridge",
                        "label": "Requirement Bridge PC",
                        "status": "online",
                        "runner_id": "runner-requirement-bridge",
                    }
                ],
                "ai_providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "enabled": True,
                        "model": "gpt-5.1-codex",
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-bridge",
                        "name": "Requirement Bridge Seat",
                        "agent_id": "agent-ui",
                        "computer_node_id": "pc-bridge",
                        "ai_provider_id": "codex",
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Bridge requirement task",
        status="ready",
        assignee_agent_id=None,
    )
    requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title=PLATFORM_MAINLINE_TITLE,
        requirement_type="git_dispatch_ai",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="Runner completion should backfill requirement final reply and create a follow-up requirement.",
        expected_output="Acknowledge, finish, and continue with one follow-up requirement.",
        opening_message="Run the platform mainline self-check and keep the requirement loop moving.",
    )
    requirement_id = requirement["id"]

    dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "workstation_id": "ws-bridge",
            "notes": "dispatch to requirement bridge seat",
        },
    )
    assert dispatch_response.status_code == 200

    inbox_response = client.get(
        "/api/runners/runner-requirement-bridge/inbox",
        headers={"X-Runner-Id": "runner-requirement-bridge"},
    )
    assert inbox_response.status_code == 200
    command = inbox_response.json()["data"][0]

    with SessionLocal() as db:
        message = db.get(CollaborationMessage, command["id"])
        assert message is not None
        message.body = "Task: Bridge requirement task\nWorkstation: ws-bridge\nDispatch status: dispatched"
        db.add(message)
        db.commit()

    ack_response = client.post(
        f"/api/runners/runner-requirement-bridge/messages/{command['id']}/ack",
        headers={"X-Runner-Id": "runner-requirement-bridge"},
        json={"note": "Requirement bridge runner acknowledged the task."},
    )
    assert ack_response.status_code == 200

    ack_requirement_response = client.get(
        f"/api/requirements/{requirement_id}",
        headers=auth_headers(owner_token),
    )
    assert ack_requirement_response.status_code == 200
    ack_requirement = ack_requirement_response.json()["data"]
    assert ack_requirement["status"] == "in_progress"

    ack_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "requirement_id": requirement_id},
    )
    assert ack_messages_response.status_code == 200
    ack_progress_messages = [
        item for item in ack_messages_response.json()["data"] if item["message_type"] == "requirement_progress_ack"
    ]
    assert len(ack_progress_messages) == 1
    assert ack_progress_messages[0]["status"] == "in_progress"

    complete_response = client.post(
        f"/api/runners/runner-requirement-bridge/messages/{command['id']}/complete",
        headers={"X-Runner-Id": "runner-requirement-bridge"},
        json={"result_status": "completed", "note": "Requirement bridge runner completed the task."},
    )
    assert complete_response.status_code == 200

    completed_requirement_response = client.get(
        f"/api/requirements/{requirement_id}",
        headers=auth_headers(owner_token),
    )
    assert completed_requirement_response.status_code == 200
    completed_requirement = completed_requirement_response.json()["data"]
    assert completed_requirement["status"] == "done"

    completed_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "requirement_id": requirement_id},
    )
    assert completed_messages_response.status_code == 200
    completed_progress_messages = [
        item for item in completed_messages_response.json()["data"] if item["message_type"] == "requirement_progress_ack"
    ]
    completed_final_messages = [
        item for item in completed_messages_response.json()["data"] if item["message_type"] == "requirement_final_reply"
    ]
    assert len(completed_progress_messages) == 1
    assert completed_progress_messages[0]["status"] == "in_progress"
    assert len(completed_final_messages) == 1
    assert completed_final_messages[0]["status"] == "done"

    requirements_response = client.get(
        "/api/requirements",
        headers=auth_headers(owner_token),
        params={"project_id": project_id},
    )
    assert requirements_response.status_code == 200
    follow_ups = [
        item
        for item in requirements_response.json()["data"]
        if item["title"] == f"{PLATFORM_MAINLINE_TITLE} {FOLLOW_UP_SUFFIX}"
    ]
    assert len(follow_ups) == 1
    assert follow_ups[0]["status"] == "queued"
    assert follow_ups[0]["to_agent"] == "ws-bridge"

    follow_up_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "requirement_id": follow_ups[0]["id"]},
    )
    assert follow_up_messages_response.status_code == 200
    follow_up_dispatches = [
        item
        for item in follow_up_messages_response.json()["data"]
        if item["message_type"] == "requirement_dispatch"
    ]
    assert len(follow_up_dispatches) == 1
    assert follow_up_dispatches[0]["recipient_type"] == "workstation"
    assert follow_up_dispatches[0]["recipient_id"] == "ws-bridge"


def test_runner_completion_only_advances_the_active_requirement_for_a_shared_task() -> None:
    owner_token, _ = issue_session_token(client)
    runner_register = client.post(
        "/api/runners/register",
        json={
            "runner_id": "runner-requirement-active-only",
            "runner_name": "Requirement Active Only Runner",
            "capabilities": ["relay", "shell"],
            "hardware_access": False,
        },
    )
    assert runner_register.status_code == 200

    project = create_project(client, owner_token, name_prefix="Requirement Active Only Project")
    project_id = project["id"]

    config_response = client.patch(
        f"/api/projects/{project_id}",
        headers=auth_headers(owner_token),
        json={
            "collaboration_config": {
                "computer_nodes": [
                    {
                        "id": "pc-active",
                        "label": "Requirement Active PC",
                        "status": "online",
                        "runner_id": "runner-requirement-active-only",
                    }
                ],
                "ai_providers": [
                    {
                        "id": "codex",
                        "label": "Codex",
                        "enabled": True,
                        "model": "gpt-5.1-codex",
                    }
                ],
                "thread_workstations": [
                    {
                        "id": "ws-active",
                        "name": "Requirement Active Seat",
                        "agent_id": "agent-ui",
                        "computer_node_id": "pc-active",
                        "ai_provider_id": "codex",
                        "status": "idle",
                    }
                ],
            }
        },
    )
    assert config_response.status_code == 200

    task = create_task(
        client,
        owner_token,
        project_id,
        title="Requirement active task",
        status="ready",
        assignee_agent_id=None,
    )
    stale_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Older sibling requirement",
        requirement_type="thread_request",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="This older requirement should not be advanced by the runner completion.",
        expected_output="Leave this requirement untouched.",
        opening_message="Do not advance me unless explicitly selected.",
    )
    active_requirement = create_requirement(
        client,
        owner_token,
        project_id=project_id,
        task_id=task["id"],
        title="Active requirement to advance",
        requirement_type="thread_request",
        status="waiting_response",
        from_agent="human-chief",
        to_agent="ai:agent-ui",
        context_summary="This is the actively dispatched requirement for the shared task.",
        expected_output="Advance only this requirement when the runner reports progress.",
        opening_message="Dispatch and track this requirement.",
    )

    requirement_dispatch_response = client.post(
        f"/api/requirements/{active_requirement['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "target_type": "workstation",
            "target_id": "ws-active",
            "note": "dispatch only the active shared-task requirement",
            "status": "queued",
        },
    )
    assert requirement_dispatch_response.status_code == 200

    task_dispatch_response = client.post(
        f"/api/tasks/{task['id']}/dispatch",
        headers=auth_headers(owner_token),
        json={
            "workstation_id": "ws-active",
            "notes": "dispatch task for the active requirement only",
        },
    )
    assert task_dispatch_response.status_code == 200

    inbox_response = client.get(
        "/api/runners/runner-requirement-active-only/inbox",
        headers={"X-Runner-Id": "runner-requirement-active-only"},
    )
    assert inbox_response.status_code == 200
    command = inbox_response.json()["data"][0]

    with SessionLocal() as db:
        message = db.get(CollaborationMessage, command["id"])
        assert message is not None
        message.body = "Task: Requirement active task\nWorkstation: ws-active\nDispatch status: dispatched"
        db.add(message)
        db.commit()

    ack_response = client.post(
        f"/api/runners/runner-requirement-active-only/messages/{command['id']}/ack",
        headers={"X-Runner-Id": "runner-requirement-active-only"},
        json={"note": "runner acknowledged the active shared-task requirement"},
    )
    assert ack_response.status_code == 200

    complete_response = client.post(
        f"/api/runners/runner-requirement-active-only/messages/{command['id']}/complete",
        headers={"X-Runner-Id": "runner-requirement-active-only"},
        json={"result_status": "completed", "note": "runner completed the active shared-task requirement"},
    )
    assert complete_response.status_code == 200

    stale_requirement_response = client.get(
        f"/api/requirements/{stale_requirement['id']}",
        headers=auth_headers(owner_token),
    )
    assert stale_requirement_response.status_code == 200
    assert stale_requirement_response.json()["data"]["status"] == "waiting_response"

    active_requirement_response = client.get(
        f"/api/requirements/{active_requirement['id']}",
        headers=auth_headers(owner_token),
    )
    assert active_requirement_response.status_code == 200
    assert active_requirement_response.json()["data"]["status"] == "done"

    stale_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "requirement_id": stale_requirement["id"]},
    )
    assert stale_messages_response.status_code == 200
    stale_messages = stale_messages_response.json()["data"]
    assert not any(item["message_type"] == "requirement_final_reply" for item in stale_messages)

    active_messages_response = client.get(
        "/api/collaboration/messages",
        headers=auth_headers(owner_token),
        params={"project_id": project_id, "requirement_id": active_requirement["id"]},
    )
    assert active_messages_response.status_code == 200
    active_progress_messages = [
        item
        for item in active_messages_response.json()["data"]
        if item["message_type"] == "requirement_progress_ack"
    ]
    active_final_messages = [
        item
        for item in active_messages_response.json()["data"]
        if item["message_type"] == "requirement_final_reply"
    ]
    assert len(active_progress_messages) == 1
    assert active_progress_messages[0]["status"] == "in_progress"
    assert len(active_final_messages) == 1
    assert active_final_messages[0]["status"] == "done"
