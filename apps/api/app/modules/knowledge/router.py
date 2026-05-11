from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal
from app.common.response import ok
from app.db.models.project_member import ProjectMember
from app.db.models.requirement import Requirement
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
    ProjectSkillCreate,
    ProjectSkillRead,
    SeatSkillAssignmentCreate,
    SeatSkillAssignmentRead,
)
from .service import (
    assign_seat_skill,
    list_knowledge_documents,
    list_project_skills,
    list_seat_skill_assignments,
    upsert_knowledge_document,
    upsert_project_skill,
)


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
def api_list_knowledge(request: Request, db: Session = Depends(get_db)):
    principal = resolve_human_principal(db, request, allow_bootstrap=False)
    memberships = list(
        db.scalars(
            select(ProjectMember.project_id).where(
                ProjectMember.user_id == (principal.user_id or ""),
                ProjectMember.status != "removed",
            )
        )
    )
    if not memberships:
        return ok([])
    items = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.requirement_type == "knowledge_note",
                Requirement.status.in_(["accepted", "closed", "escalated"]),
                Requirement.project_id.in_(memberships),
            )
            .order_by(Requirement.updated_at.desc())
            .limit(100)
        )
    )
    return ok(
        [
            {
                "id": item.id,
                "title": item.title,
                "requirement_type": item.requirement_type,
                "module": item.module,
                "summary": item.context_summary,
                "expected_output": item.expected_output,
                "source_type": "requirement",
                "source_id": item.id,
                "project_id": item.project_id,
                "task_id": item.task_id,
            }
            for item in items
        ]
    )


@router.get("/projects/{project_id}/documents")
def api_list_project_knowledge_documents(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="knowledge.documents.read")
    return ok(
        [
            KnowledgeDocumentRead.model_validate(item).model_dump(mode="json", by_alias=True)
            for item in list_knowledge_documents(db, project_id)
        ]
    )


@router.post("/projects/{project_id}/documents")
def api_upsert_project_knowledge_document(
    project_id: str,
    payload: KnowledgeDocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="knowledge.documents.write")
    item = upsert_knowledge_document(db, project_id, payload)
    return ok(KnowledgeDocumentRead.model_validate(item).model_dump(mode="json", by_alias=True))


@router.get("/projects/{project_id}/skills")
def api_list_project_skills(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="knowledge.skills.read")
    return ok([ProjectSkillRead.model_validate(item).model_dump(mode="json", by_alias=True) for item in list_project_skills(db, project_id)])


@router.post("/projects/{project_id}/skills")
def api_upsert_project_skill(
    project_id: str,
    payload: ProjectSkillCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="knowledge.skills.write")
    item = upsert_project_skill(db, project_id, payload)
    return ok(ProjectSkillRead.model_validate(item).model_dump(mode="json", by_alias=True))


@router.get("/projects/{project_id}/seat-skill-assignments")
def api_list_seat_skill_assignments(
    project_id: str,
    request: Request,
    seat_id: str | None = None,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="knowledge.seat_skill_assignments.read")
    return ok(
        [
            SeatSkillAssignmentRead.model_validate(item).model_dump(mode="json", by_alias=True)
            for item in list_seat_skill_assignments(db, project_id, seat_id=seat_id)
        ]
    )


@router.post("/projects/{project_id}/seat-skill-assignments")
def api_assign_seat_skill(
    project_id: str,
    payload: SeatSkillAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="knowledge.seat_skill_assignments.write")
    item = assign_seat_skill(db, project_id, payload)
    return ok(SeatSkillAssignmentRead.model_validate(item).model_dump(mode="json", by_alias=True))
