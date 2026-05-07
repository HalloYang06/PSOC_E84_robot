from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> AuditLog:
    log = AuditLog(
        project_id=project_id,
        task_id=task_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=jsonable_encoder(before or {}),
        after=jsonable_encoder(after or {}),
        success=success,
        error_message=error_message,
    )
    db.add(log)
    return log


def list_audit_logs(
    db: Session,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    success: bool | None = None,
    limit: int = 100,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if task_id:
        stmt = stmt.where(AuditLog.task_id == task_id)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if success is not None:
        stmt = stmt.where(AuditLog.success.is_(success))
    return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))
