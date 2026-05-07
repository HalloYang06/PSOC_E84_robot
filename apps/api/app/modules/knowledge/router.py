from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal
from app.common.response import ok
from app.db.models.requirement import Requirement
from app.db.models.project_member import ProjectMember
from app.db.session import get_db


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
