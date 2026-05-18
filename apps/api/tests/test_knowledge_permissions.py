from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.project import Project
from app.db.session import SessionLocal
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


def test_project_knowledge_documents_and_skill_assignments_are_project_scoped() -> None:
    owner_token, owner_user_id = issue_session_token(client)
    project = create_project(
        client,
        owner_token,
        name_prefix="Knowledge Documents",
        collaboration_config={
            "thread_workstations": [
                {
                    "id": "boss-seat",
                    "name": "Boss NPC",
                    "status": "active",
                    "ai_provider_id": "codex",
                }
            ],
        },
    )
    project_id = project["id"]
    add_project_member(client, project_id, owner_token, owner_user_id, role="owner", is_owner=True)

    member_user_id, member_email = register_user(client, f"knowledge-member-{uuid4().hex[:8]}@example.com", "Knowledge Member")
    member_token, _ = issue_session_token(client, member_email)
    add_project_member(client, project_id, owner_token, member_user_id, role="member", is_owner=False)

    outsider_user_id, outsider_email = register_user(
        client,
        f"knowledge-outsider-{uuid4().hex[:8]}@example.com",
        "Knowledge Outsider",
    )
    outsider_token, _ = issue_session_token(client, outsider_email)

    bad_path_response = client.post(
        f"/api/knowledge/projects/{project_id}/documents",
        headers=auth_headers(owner_token),
        json={
            "title": "Bad local path",
            "repo_relative_path": r"D:\\english_a_agent\\docs\\README.md",
        },
    )
    assert bad_path_response.status_code == 422
    assert bad_path_response.json()["error"]["code"] == "BAD_REPO_PATH"

    doc_response = client.post(
        f"/api/knowledge/projects/{project_id}/documents",
        headers=auth_headers(owner_token),
        json={
            "title": "Boss manual",
            "repo_relative_path": "docs/npcs/boss-seat/README.md",
            "scope": "npc",
            "owner_type": "seat",
            "owner_id": "boss-seat",
            "exists_in_repo": True,
            "summary": "Boss NPC operating manual.",
            "tags": ["boss", "planning"],
        },
    )
    assert doc_response.status_code == 200, doc_response.text
    doc = doc_response.json()["data"]
    assert doc["repo_relative_path"] == "docs/npcs/boss-seat/README.md"
    assert doc["exists_in_repo"] is True
    assert doc["last_synced_at"]

    member_write_response = client.post(
        f"/api/knowledge/projects/{project_id}/documents",
        headers=auth_headers(member_token),
        json={
            "title": "Member write",
            "repo_relative_path": "docs/member.md",
            "scope": "project",
            "summary": "A collaborator can add reusable knowledge without an approval gate.",
        },
    )
    assert member_write_response.status_code == 200, member_write_response.text
    assert member_write_response.json()["data"]["repo_relative_path"] == "docs/member.md"

    outsider_read_response = client.get(
        f"/api/knowledge/projects/{project_id}/documents",
        headers=auth_headers(outsider_token),
    )
    assert outsider_read_response.status_code == 403

    member_read_response = client.get(
        f"/api/knowledge/projects/{project_id}/documents",
        headers=auth_headers(member_token),
    )
    assert member_read_response.status_code == 200
    assert {item["repo_relative_path"] for item in member_read_response.json()["data"]} == {
        "docs/member.md",
        "docs/npcs/boss-seat/README.md",
    }

    skill_response = client.post(
        f"/api/knowledge/projects/{project_id}/skills",
        headers=auth_headers(owner_token),
        json={
            "skill_id": "speech-data-contracts",
            "label": "Speech Data Contracts",
            "source": "github",
            "category": "backend",
            "repo_relative_path": "docs/skills/speech-data-contracts/SKILL.md",
            "exists_in_repo": True,
        },
    )
    assert skill_response.status_code == 200, skill_response.text
    assert skill_response.json()["data"]["skill_id"] == "speech-data-contracts"

    bad_skill_path_response = client.post(
        f"/api/knowledge/projects/{project_id}/skills",
        headers=auth_headers(owner_token),
        json={
            "skill_id": "bad-local-skill",
            "label": "Bad Local Skill",
            "source": "npc-authored",
            "repo_relative_path": r"D:\\english_a_agent\\skills\\bad-local-skill\\SKILL.md",
        },
    )
    assert bad_skill_path_response.status_code == 422
    assert bad_skill_path_response.json()["error"]["code"] == "BAD_REPO_PATH"

    npc_authored_skill_response = client.post(
        f"/api/knowledge/projects/{project_id}/skills",
        headers=auth_headers(owner_token),
        json={
            "skill_id": "teacher-progress-review",
            "label": "Teacher Progress Review",
            "source": "npc-authored",
            "category": "npc-authored",
            "repo_relative_path": "skills/teacher-progress-review/SKILL.md",
            "exists_in_repo": False,
            "extra_data": {
                "author_seat_id": "boss-seat",
                "draft_status": "draft",
                "skill_creator_version": "openai-skill-creator",
            },
        },
    )
    assert npc_authored_skill_response.status_code == 200, npc_authored_skill_response.text
    npc_authored_skill = npc_authored_skill_response.json()["data"]
    assert npc_authored_skill["source"] == "npc-authored"
    assert npc_authored_skill["repo_relative_path"] == "skills/teacher-progress-review/SKILL.md"
    assert npc_authored_skill["extra_data"]["author_seat_id"] == "boss-seat"

    member_authored_skill_response = client.post(
        f"/api/knowledge/projects/{project_id}/skills",
        headers=auth_headers(member_token),
        json={
            "skill_id": "member-debug-note",
            "label": "Member Debug Note",
            "source": "human-authored",
            "category": "debug",
            "repo_relative_path": "skills/member-debug-note/SKILL.md",
            "exists_in_repo": False,
        },
    )
    assert member_authored_skill_response.status_code == 200, member_authored_skill_response.text
    assert member_authored_skill_response.json()["data"]["skill_id"] == "member-debug-note"

    assignment_response = client.post(
        f"/api/knowledge/projects/{project_id}/seat-skill-assignments",
        headers=auth_headers(owner_token),
        json={
            "seat_id": "boss-seat",
            "skill_id": "speech-data-contracts",
            "assignment_type": "direct",
            "notes": "Boss uses this for planning API/data work.",
        },
    )
    assert assignment_response.status_code == 200, assignment_response.text
    assignment = assignment_response.json()["data"]
    assert assignment["seat_id"]
    assert assignment["skill_id"] == "speech-data-contracts"
    with SessionLocal() as db:
        project_row = db.get(Project, project_id)
        assert project_row is not None
        project_row.collaboration_config = {
            **(project_row.collaboration_config or {}),
            "skill_library": [
                {"id": "speech-data-contracts", "label": "Speech Data Contracts"},
                {"id": "teacher-progress-review", "label": "Teacher Progress Review"},
            ],
        }
        db.add(project_row)
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="boss-seat").one()
        seat.extra_data = {
            **(seat.extra_data or {}),
            "skill_loadout": ["speech-data-contracts", "teacher-progress-review"],
            "additional_skill_ids": ["speech-data-contracts"],
            "skill_forge_snapshot": {
                "changed_skill_id": "speech-data-contracts",
                "summary": "Skill was active.",
            },
        }
        db.add(seat)
        db.commit()

    npc_authored_assignment_response = client.post(
        f"/api/knowledge/projects/{project_id}/seat-skill-assignments",
        headers=auth_headers(owner_token),
        json={
            "seat_id": "boss-seat",
            "skill_id": "teacher-progress-review",
            "assignment_type": "npc-authored-draft",
            "status": "draft",
            "notes": "NPC-authored reusable behavior draft.",
            "extra_data": {"author_seat_id": "boss-seat"},
        },
    )
    assert npc_authored_assignment_response.status_code == 200, npc_authored_assignment_response.text
    assert npc_authored_assignment_response.json()["data"]["status"] == "draft"

    assignment_list_response = client.get(
        f"/api/knowledge/projects/{project_id}/seat-skill-assignments",
        headers=auth_headers(member_token),
    )
    assert assignment_list_response.status_code == 200
    assert len(assignment_list_response.json()["data"]) == 2

    owner_delete_bound_skill_response = client.delete(
        f"/api/knowledge/projects/{project_id}/skills/speech-data-contracts",
        headers=auth_headers(owner_token),
    )
    assert owner_delete_bound_skill_response.status_code == 200, owner_delete_bound_skill_response.text
    with SessionLocal() as db:
        seat = db.query(ProjectThreadWorkstation).filter_by(project_id=project_id, config_id="boss-seat").one()
        metadata = seat.extra_data or {}
        assert metadata["skill_loadout"] == ["teacher-progress-review"]
        assert metadata["additional_skill_ids"] == []
        assert metadata["skill_forge_snapshot"]["removed_at"]
        project_row = db.get(Project, project_id)
        assert project_row is not None
        skill_ids = [item["id"] for item in (project_row.collaboration_config or {}).get("skill_library", [])]
        assert skill_ids == ["teacher-progress-review"]
    assignment_list_after_delete_response = client.get(
        f"/api/knowledge/projects/{project_id}/seat-skill-assignments",
        headers=auth_headers(member_token),
    )
    assert assignment_list_after_delete_response.status_code == 200
    assert {item["skill_id"] for item in assignment_list_after_delete_response.json()["data"]} == {"teacher-progress-review"}

    outsider_delete_skill_response = client.delete(
        f"/api/knowledge/projects/{project_id}/skills/member-debug-note",
        headers=auth_headers(outsider_token),
    )
    assert outsider_delete_skill_response.status_code == 403

    member_delete_skill_response = client.delete(
        f"/api/knowledge/projects/{project_id}/skills/member-debug-note",
        headers=auth_headers(member_token),
    )
    assert member_delete_skill_response.status_code == 200, member_delete_skill_response.text

    member_delete_document_response = client.delete(
        f"/api/knowledge/projects/{project_id}/documents/docs/member.md",
        headers=auth_headers(member_token),
    )
    assert member_delete_document_response.status_code == 200, member_delete_document_response.text
