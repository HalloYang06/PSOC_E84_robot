from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.handoff import Handoff
from app.db.models.task import Task
from app.modules.audit.service import create_audit_log

from .schemas import HandoffAcceptRequest, HandoffAssignRequest, HandoffPackageCreate


def _package_payload(payload: HandoffPackageCreate) -> dict:
    data = payload.model_dump(exclude={"project_id", "task_id", "handoff_from", "handoff_to"})
    extra = data.pop("payload", {})
    return {**data, **extra}


def _to_read_dict(handoff: Handoff) -> dict:
    payload = dict(handoff.payload or {})
    return {
        "id": handoff.id,
        "project_id": handoff.project_id,
        "task_id": handoff.task_id,
        "handoff_from": handoff.handoff_from,
        "handoff_to": handoff.handoff_to,
        "summary": payload.get("summary"),
        "reason": payload.get("reason"),
        "current_status": payload.get("current_status"),
        "latest_files": payload.get("latest_files", []),
        "latest_diff": payload.get("latest_diff"),
        "open_questions": payload.get("open_questions", []),
        "next_steps": payload.get("next_steps", []),
        "blocked_by": payload.get("blocked_by", []),
        "linked_requirement_ids": payload.get("linked_requirement_ids", []),
        "linked_approval_ids": payload.get("linked_approval_ids", []),
        "context_health": payload.get("context_health", {}),
        "notes": payload.get("notes"),
        "payload": payload,
        "created_at": handoff.created_at,
    }


def list_handoffs(
    db: Session,
    *,
    task_id: str | None = None,
    project_id: str | None = None,
    handoff_from: str | None = None,
    handoff_to: str | None = None,
    limit: int = 100,
) -> list[Handoff]:
    stmt = select(Handoff).order_by(Handoff.created_at.desc())
    if task_id:
        stmt = stmt.where(Handoff.task_id == task_id)
    if project_id:
        stmt = stmt.where(Handoff.project_id == project_id)
    if handoff_from:
        stmt = stmt.where(Handoff.handoff_from == handoff_from)
    if handoff_to:
        stmt = stmt.where(Handoff.handoff_to == handoff_to)
    return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))


def get_handoff_or_404(db: Session, handoff_id: str) -> Handoff:
    handoff = db.get(Handoff, handoff_id)
    if handoff is None:
        raise AppError("HANDOFF_NOT_FOUND", "handoff record not found", status_code=404)
    return handoff


def create_handoff(db: Session, payload: HandoffPackageCreate) -> Handoff:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "task not found", status_code=404)

    handoff = Handoff(
        project_id=payload.project_id or task.project_id,
        task_id=task.id,
        handoff_from=payload.handoff_from,
        handoff_to=payload.handoff_to,
        payload=_package_payload(payload),
    )
    db.add(handoff)
    db.flush()
    create_audit_log(
        db,
        project_id=handoff.project_id,
        task_id=handoff.task_id,
        actor_type="system",
        actor_id=payload.handoff_from,
        action="handoff.created",
        resource_type="handoff",
        resource_id=handoff.id,
        after=_to_read_dict(handoff),
    )
    db.commit()
    db.refresh(handoff)
    return handoff


def accept_handoff(db: Session, task_id: str, handoff_id: str, payload: HandoffAcceptRequest) -> Handoff:
    handoff = get_handoff_or_404(db, handoff_id)
    if handoff.task_id != task_id:
        raise AppError("HANDOFF_NOT_FOUND", "handoff record not found for task", status_code=404)
    current = dict(handoff.payload or {})
    current["current_status"] = "accepted"
    current["accept_note"] = payload.note
    handoff.payload = current
    if payload.actor_id:
        handoff.handoff_to = payload.actor_id
    db.add(handoff)
    create_audit_log(
        db,
        project_id=handoff.project_id,
        task_id=handoff.task_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="handoff.accepted",
        resource_type="handoff",
        resource_id=handoff.id,
        after=_to_read_dict(handoff),
    )
    db.commit()
    db.refresh(handoff)
    return handoff


def assign_handoff_agent(db: Session, task_id: str, handoff_id: str, payload: HandoffAssignRequest) -> Handoff:
    handoff = get_handoff_or_404(db, handoff_id)
    if handoff.task_id != task_id:
        raise AppError("HANDOFF_NOT_FOUND", "handoff record not found for task", status_code=404)
    handoff.handoff_to = payload.handoff_to
    current = dict(handoff.payload or {})
    current["current_status"] = current.get("current_status") or "assigned"
    current["assign_note"] = payload.note
    handoff.payload = current
    db.add(handoff)
    create_audit_log(
        db,
        project_id=handoff.project_id,
        task_id=handoff.task_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="handoff.assigned",
        resource_type="handoff",
        resource_id=handoff.id,
        after=_to_read_dict(handoff),
    )
    db.commit()
    db.refresh(handoff)
    return handoff
