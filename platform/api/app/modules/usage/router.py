from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal, resolve_task_write_principal
from app.common.response import ok
from app.db.models.usage_log import UsageLog
from app.db.session import get_db
from app.modules.read_access import readable_project_ids, require_project_read_access, resolve_task_project_id

from .schemas import UsageCreate, UsageRead


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def list_usage_logs(
    project_id: str | None = None,
    task_id: str | None = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    if task_id:
        scoped_project_ids = [resolve_task_project_id(db, task_id)]
        require_project_read_access(db, request, scoped_project_ids[0], action="usage.read")
    elif project_id:
        scoped_project_ids = [project_id]
        require_project_read_access(db, request, project_id, action="usage.read")
    else:
        scoped_project_ids = readable_project_ids(db, request)

    stmt = select(UsageLog).order_by(UsageLog.created_at.desc())
    if task_id:
        stmt = stmt.where(UsageLog.task_id == task_id)
    elif project_id:
        stmt = stmt.where(UsageLog.project_id == project_id)
    elif scoped_project_ids:
        stmt = stmt.where(UsageLog.project_id.in_(scoped_project_ids))
    else:
        return ok([])

    items = list(db.scalars(stmt.limit(100)))
    return ok([UsageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("")
def create_usage_log(payload: UsageCreate, request: Request, db: Session = Depends(get_db)):
    resolve_human_principal(db, request, allow_bootstrap=False)
    if payload.task_id:
        resolve_task_write_principal(db, request, payload.task_id, action="usage.create")
    elif payload.project_id:
        resolve_project_write_principal(db, request, payload.project_id, action="usage.create")
    item = UsageLog(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return ok(UsageRead.model_validate(item).model_dump(mode="json"))
