from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import RequestPrincipal, resolve_human_principal
from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.handoff import Handoff
from app.db.models.project import Project
from app.db.models.project_member import ProjectMember
from app.db.models.requirement import Requirement
from app.db.models.task import Task


def require_real_human_principal(db: Session, request: Request) -> RequestPrincipal:
    return resolve_human_principal(db, request, allow_bootstrap=False)


def _active_project_member(db: Session, project_id: str, user_id: str) -> ProjectMember | None:
    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.status == "active",
    )
    return db.scalar(stmt)


def require_project_read_access(
    db: Session,
    request: Request,
    project_id: str,
    *,
    action: str = "project.read",
) -> RequestPrincipal:
    cleaned_project_id = str(project_id or "").strip()
    if not cleaned_project_id:
        raise AppError("PROJECT_NOT_FOUND", "project context is required", status_code=404)

    principal = require_real_human_principal(db, request)
    project = db.get(Project, cleaned_project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)

    member = _active_project_member(db, cleaned_project_id, principal.user_id or "")
    if member is None:
        raise AppError(
            "PERMISSION_DENIED",
            f"missing permission for {action}",
            status_code=403,
            details={"project_id": cleaned_project_id, "action": action},
        )
    return principal


def require_project_read_access_for_target(
    db: Session,
    request: Request,
    target: Any,
    *,
    action: str = "project.read",
    project_id_attr: str = "project_id",
) -> RequestPrincipal:
    if isinstance(target, str):
        project_id = target.strip()
    elif isinstance(target, dict):
        project_id = str(target.get(project_id_attr) or "").strip()
    else:
        project_id = str(getattr(target, project_id_attr, "") or "").strip()
    if not project_id:
        raise AppError("PROJECT_NOT_FOUND", "project context is required", status_code=404)
    return require_project_read_access(db, request, project_id, action=action)


def readable_project_ids(db: Session, request: Request) -> list[str]:
    principal = require_real_human_principal(db, request)
    stmt = (
        select(ProjectMember.project_id)
        .where(ProjectMember.user_id == (principal.user_id or ""), ProjectMember.status == "active")
        .order_by(ProjectMember.created_at.desc())
    )
    values = [str(item or "").strip() for item in db.scalars(stmt)]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def scoped_project_ids_for_read(
    db: Session,
    request: Request,
    project_ids: list[str] | None,
    *,
    action: str,
) -> list[str]:
    scoped = [str(item or "").strip() for item in (project_ids or []) if str(item or "").strip()]
    if scoped:
        deduped: list[str] = []
        seen: set[str] = set()
        for project_id in scoped:
            if project_id in seen:
                continue
            seen.add(project_id)
            require_project_read_access(db, request, project_id, action=action)
            deduped.append(project_id)
        return deduped
    return readable_project_ids(db, request)


def resolve_task_project_id(db: Session, task_id: str) -> str:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "task not found", status_code=404)
    return str(task.project_id or "").strip()


def resolve_requirement_project_id(db: Session, requirement_id: str) -> str:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise AppError("NOT_FOUND", "requirement not found", status_code=404)
    project_id = str(requirement.project_id or "").strip()
    if project_id:
        return project_id
    if requirement.task_id:
        return resolve_task_project_id(db, requirement.task_id)
    raise AppError("PROJECT_NOT_FOUND", "requirement has no project context", status_code=404)


def resolve_approval_project_id(db: Session, approval_id: str) -> str:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise AppError("APPROVAL_NOT_FOUND", "approval record not found", status_code=404)
    project_id = str(approval.project_id or "").strip()
    if not project_id:
        raise AppError("PROJECT_NOT_FOUND", "approval has no project context", status_code=404)
    return project_id


def resolve_handoff_project_id(db: Session, handoff_id: str) -> str:
    handoff = db.get(Handoff, handoff_id)
    if handoff is None:
        raise AppError("HANDOFF_NOT_FOUND", "handoff record not found", status_code=404)
    project_id = str(handoff.project_id or "").strip()
    if project_id:
        return project_id
    if handoff.task_id:
        return resolve_task_project_id(db, handoff.task_id)
    raise AppError("PROJECT_NOT_FOUND", "handoff has no project context", status_code=404)
