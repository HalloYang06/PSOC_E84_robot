from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import (
    require_platform_operator_principal,
    resolve_human_principal,
    resolve_project_write_principal,
    resolve_task_write_principal,
)
from app.common.response import ok
from app.db.session import get_db

from .schemas import AuditCreate, AuditRead
from .service import create_audit_log, list_audit_logs


router = APIRouter(prefix="/api", tags=["audit"])


def _serialize(logs):
    return [AuditRead.model_validate(item).model_dump(mode="json") for item in logs]


def _list_audit_logs(
    db: Session,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    success: bool | None = None,
    limit: int = 100,
):
    return list_audit_logs(
        db,
        project_id=project_id,
        task_id=task_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        success=success,
        limit=limit,
    )


@router.get("/audit")
def api_list_audit_logs(
    request: Request,
    project_id: str | None = None,
    task_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    success: bool | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if task_id:
        resolve_task_write_principal(db, request, task_id, action="audit.read")
    elif project_id:
        resolve_project_write_principal(db, request, project_id, action="audit.read")
    else:
        require_platform_operator_principal(db, request, action="audit.read")
    return ok(
        _serialize(
            _list_audit_logs(
                db,
                project_id=project_id,
                task_id=task_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                success=success,
                limit=limit,
            )
        )
    )


@router.get("/audit/projects/{project_id}")
@router.get("/projects/{project_id}/audit")
def api_list_project_audit_logs(
    project_id: str,
    request: Request,
    actor_type: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    success: bool | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(db, request, project_id, action="audit.read")
    return ok(
        _serialize(
            _list_audit_logs(
                db,
                project_id=project_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                success=success,
                limit=limit,
            )
        )
    )


@router.get("/audit/tasks/{task_id}")
@router.get("/tasks/{task_id}/audit")
def api_list_task_audit_logs(
    task_id: str,
    request: Request,
    actor_type: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    success: bool | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    resolve_task_write_principal(db, request, task_id, action="audit.read")
    return ok(
        _serialize(
            _list_audit_logs(
                db,
                task_id=task_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                success=success,
                limit=limit,
            )
        )
    )


@router.post("/audit")
def api_create_audit_log(payload: AuditCreate, request: Request, db: Session = Depends(get_db)):
    principal = resolve_human_principal(db, request, allow_bootstrap=False)
    if payload.task_id:
        resolve_task_write_principal(db, request, payload.task_id, action="audit.create")
    elif payload.project_id:
        resolve_project_write_principal(db, request, payload.project_id, action="audit.create")
    data = payload.model_dump()
    log = create_audit_log(
        db,
        actor_type="human",
        actor_id=principal.user_id,
        **data,
    )
    db.commit()
    db.refresh(log)
    return ok(AuditRead.model_validate(log).model_dump(mode="json"))
