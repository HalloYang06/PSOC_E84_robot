from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.context_health import ContextHealthRecord
from app.db.models.task import Task
from app.modules.audit.service import create_audit_log

from .schemas import ContextHealthCreate


def list_context_health_records(
    db: Session,
    *,
    task_id: str | None = None,
    project_id: str | None = None,
    agent_id: str | None = None,
    health: str | None = None,
    limit: int = 100,
) -> list[ContextHealthRecord]:
    stmt = select(ContextHealthRecord).order_by(ContextHealthRecord.created_at.desc())
    if task_id:
        stmt = stmt.where(ContextHealthRecord.task_id == task_id)
    if project_id:
        stmt = stmt.where(ContextHealthRecord.project_id == project_id)
    if agent_id:
        stmt = stmt.where(ContextHealthRecord.agent_id == agent_id)
    if health:
        stmt = stmt.where(ContextHealthRecord.health == health)
    return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))


def get_latest_context_health(db: Session, task_id: str, agent_id: str | None = None) -> ContextHealthRecord | None:
    stmt = select(ContextHealthRecord).where(ContextHealthRecord.task_id == task_id)
    if agent_id:
        stmt = stmt.where(ContextHealthRecord.agent_id == agent_id)
    stmt = stmt.order_by(ContextHealthRecord.created_at.desc()).limit(1)
    return db.scalar(stmt)


def create_context_health_record(db: Session, task_id: str, payload: ContextHealthCreate) -> ContextHealthRecord:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "task not found", status_code=404)
    if payload.project_id and payload.project_id != task.project_id:
        raise AppError("PROJECT_MISMATCH", "context health project does not match task scope", status_code=400)

    record = ContextHealthRecord(
        project_id=payload.project_id or task.project_id,
        task_id=task.id,
        agent_id=payload.agent_id,
        usage_ratio=payload.usage_ratio,
        health=payload.health,
        conversation_turns=payload.conversation_turns,
        files_loaded_count=payload.files_loaded_count,
        failed_retry_count=payload.failed_retry_count,
        summary=payload.summary,
        recommended_action=payload.recommended_action,
    )
    db.add(record)
    db.flush()
    create_audit_log(
        db,
        project_id=record.project_id,
        task_id=record.task_id,
        actor_type="system",
        actor_id=payload.agent_id,
        action="context_health.recorded",
        resource_type="context_health",
        resource_id=record.id,
        after={
            "usage_ratio": record.usage_ratio,
            "health": record.health,
            "conversation_turns": record.conversation_turns,
            "files_loaded_count": record.files_loaded_count,
            "failed_retry_count": record.failed_retry_count,
        },
    )
    db.commit()
    db.refresh(record)
    return record
