from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


def append_audit_log(
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
        before=before or {},
        after=after or {},
        success=success,
        error_message=error_message,
    )
    db.add(log)
    return log
