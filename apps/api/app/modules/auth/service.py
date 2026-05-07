from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.invitation import Invitation
from app.db.models.project import Project
from app.db.models.project_member import ProjectMember
from app.db.models.task import Task
from app.db.models.user import User
from app.modules.audit.service import create_audit_log

from .schemas import InvitationAcceptRequest, InvitationCreate, LoginRequest, RegisterRequest


HUMAN_REVIEW_APPROVAL_STATUSES = {"pending", "needs_changes"}
HUMAN_REVIEW_TASK_STATUSES = {"waiting_approval", "reviewing", "blocked"}
HUMAN_ONLINE_FRESH_SECONDS = 5 * 60
PROJECT_PRESENCE_FRESH_SECONDS = 2 * 60


def _coerce_utc_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _freshness_snapshot(
    value: object | None,
    *,
    fresh_seconds: int,
    online_label: str,
    stale_label: str,
    never_label: str,
) -> dict[str, object | None]:
    seen_at = _coerce_utc_datetime(value)
    if seen_at is None:
        return {
            "state": "never_seen",
            "label": never_label,
            "age_seconds": None,
            "fresh_seconds": fresh_seconds,
        }
    now = datetime.now(timezone.utc)
    age_seconds = max(0, int((now - seen_at).total_seconds()))
    is_fresh = age_seconds <= fresh_seconds
    return {
        "state": "online" if is_fresh else "stale",
        "label": online_label if is_fresh else stale_label,
        "age_seconds": age_seconds,
        "fresh_seconds": fresh_seconds,
    }


def serialize_user_for_read(user: User | None):
    if user is None:
        return None
    global_role = (user.bio or "member").strip().lower() or "member"
    online = _freshness_snapshot(
        getattr(user, "last_seen_at", None),
        fresh_seconds=HUMAN_ONLINE_FRESH_SECONDS,
        online_label="账号在线",
        stale_label="账号离线",
        never_label="未见登录",
    )
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "global_role": global_role,
        "is_active": user.is_active,
        "notes": user.bio,
        "display_name": user.display_name,
        "bio": user.bio,
        "last_seen_at": getattr(user, "last_seen_at", None),
        "online_state": online["state"],
        "online_label": online["label"],
        "online_age_seconds": online["age_seconds"],
        "online_fresh_seconds": online["fresh_seconds"],
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def serialize_project_for_read(project: Project | None):
    if project is None:
        return None
    return {
        "id": project.id,
        "name": project.name,
        "project_type": project.project_type,
        "default_branch": project.default_branch,
        "develop_branch": project.develop_branch,
    }


def serialize_invitation_for_read(invitation: Invitation):
    return {
        "id": invitation.id,
        "email": invitation.email,
        "project_id": invitation.project_id,
        "role": invitation.role,
        "invited_by_user_id": invitation.invited_by_user_id,
        "status": invitation.status,
        "note": invitation.note,
        "accepted_by_user_id": invitation.accepted_by_user_id,
        "accepted_at": invitation.accepted_at,
        "created_at": invitation.created_at,
        "project": serialize_project_for_read(getattr(invitation, "project", None)),
        "invited_by_user": serialize_user_for_read(getattr(invitation, "invited_by_user", None)),
        "accepted_by_user": serialize_user_for_read(getattr(invitation, "accepted_by_user", None)),
    }


def serialize_member_for_read(member: ProjectMember):
    project_presence = _freshness_snapshot(
        getattr(member, "last_project_seen_at", None),
        fresh_seconds=PROJECT_PRESENCE_FRESH_SECONDS,
        online_label="正在项目里",
        stale_label="离开项目",
        never_label="未进入项目",
    )
    return {
        "id": member.id,
        "project_id": member.project_id,
        "user_id": member.user_id,
        "role": member.role,
        "status": member.status,
        "is_owner": member.is_owner,
        "last_project_seen_at": getattr(member, "last_project_seen_at", None),
        "last_project_path": getattr(member, "last_project_path", None),
        "project_presence_state": project_presence["state"],
        "project_presence_label": project_presence["label"],
        "project_presence_age_seconds": project_presence["age_seconds"],
        "project_presence_fresh_seconds": project_presence["fresh_seconds"],
        "joined_at": member.joined_at,
        "created_at": member.created_at,
        "updated_at": member.updated_at,
        "project": serialize_project_for_read(getattr(member, "project", None)),
        "user": serialize_user_for_read(getattr(member, "user", None)),
    }


def list_users(db: Session):
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


def list_invitations(db: Session, project_id: str | None = None, status: str | None = None):
    stmt = (
        select(Invitation)
        .options(
            selectinload(Invitation.project),
            selectinload(Invitation.invited_by_user),
            selectinload(Invitation.accepted_by_user),
        )
        .order_by(Invitation.created_at.desc())
    )
    if project_id:
        stmt = stmt.where(Invitation.project_id == project_id)
    if status:
        stmt = stmt.where(Invitation.status == status)
    return [serialize_invitation_for_read(item) for item in db.scalars(stmt)]


def list_project_members(db: Session, project_id: str):
    stmt = (
        select(ProjectMember)
        .options(selectinload(ProjectMember.project), selectinload(ProjectMember.user))
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.is_owner.desc(), ProjectMember.joined_at.desc())
    )
    return [serialize_member_for_read(item) for item in db.scalars(stmt)]


def _human_review_workspace_summaries(db: Session, project_ids: list[str]) -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {
        project_id: {
            "count": 0,
            "title": None,
            "detail": None,
            "level": None,
        }
        for project_id in project_ids
    }
    if not project_ids:
        return summaries

    approval_stmt = (
        select(Approval, Task)
        .join(Task, Approval.task_id == Task.id)
        .where(Task.project_id.in_(project_ids), Approval.status.in_(HUMAN_REVIEW_APPROVAL_STATUSES))
        .order_by(Approval.created_at.desc())
    )
    for approval, task in db.execute(approval_stmt):
        project_id = str(task.project_id)
        summary = summaries.setdefault(project_id, {"count": 0, "title": None, "detail": None, "level": None})
        summary["count"] = int(summary["count"] or 0) + 1
        if not summary["title"]:
            summary["title"] = task.title or approval.action or "待人工审核事项"
            summary["detail"] = f"{approval.level} / {approval.action} / {approval.status}"
            summary["level"] = approval.level

    task_stmt = (
        select(Task)
        .where(Task.project_id.in_(project_ids), Task.status.in_(HUMAN_REVIEW_TASK_STATUSES))
        .order_by(Task.updated_at.desc())
    )
    for task in db.scalars(task_stmt):
        project_id = str(task.project_id)
        summary = summaries.setdefault(project_id, {"count": 0, "title": None, "detail": None, "level": None})
        summary["count"] = int(summary["count"] or 0) + 1
        if not summary["title"]:
            summary["title"] = task.title or "待人工审核任务"
            summary["detail"] = f"任务状态：{task.status}"
            summary["level"] = "task"

    return summaries


def list_user_workspace_projects(db: Session, user_id: str):
    stmt = (
        select(ProjectMember)
        .options(selectinload(ProjectMember.project), selectinload(ProjectMember.user))
        .where(ProjectMember.user_id == user_id)
        .order_by(ProjectMember.joined_at.desc())
    )
    memberships = [item for item in db.scalars(stmt) if item.project is not None]
    review_summaries = _human_review_workspace_summaries(db, [str(item.project_id) for item in memberships])
    rows = []
    for item in memberships:
        if item.project is None:
            continue
        review_summary = review_summaries.get(str(item.project_id), {})
        rows.append(
            {
                "project_id": item.project_id,
                "project_name": item.project.name,
                "project_type": item.project.project_type,
                "default_branch": item.project.default_branch,
                "develop_branch": item.project.develop_branch,
                "description": item.project.description,
                "role": item.role,
                "is_owner": item.is_owner,
                "joined_at": item.joined_at,
                "pending_human_review_count": int(review_summary.get("count") or 0),
                "pending_human_review_title": review_summary.get("title"),
                "pending_human_review_detail": review_summary.get("detail"),
                "pending_human_review_level": review_summary.get("level"),
            }
        )
    return rows


def list_user_pending_invitations(db: Session, email: str):
    stmt = (
        select(Invitation)
        .options(
            selectinload(Invitation.project),
            selectinload(Invitation.invited_by_user),
            selectinload(Invitation.accepted_by_user),
        )
        .where(Invitation.email == email, Invitation.status == "pending")
        .order_by(Invitation.created_at.desc())
    )
    return [serialize_invitation_for_read(item) for item in db.scalars(stmt)]


def register_user(db: Session, payload: RegisterRequest):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise AppError("USER_EXISTS", "user already exists", status_code=400)
    user = User(
        email=payload.email,
        name=payload.name,
        display_name=payload.name,
        bio=payload.global_role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user.id,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        after={"email": user.email, "name": user.name, "display_name": user.display_name, "bio": user.bio},
    )
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, payload: LoginRequest):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise AppError("INVALID_CREDENTIALS", "invalid email or password", status_code=401)
    if not user.is_active:
        raise AppError("USER_DISABLED", "user is disabled", status_code=403)
    user.last_seen_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def mark_project_presence(db: Session, project_id: str, user_id: str, *, path: str | None = None):
    member = db.scalar(
        select(ProjectMember)
        .options(selectinload(ProjectMember.project), selectinload(ProjectMember.user))
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.status == "active",
        )
    )
    if member is None:
        raise AppError("PERMISSION_DENIED", "current user is not an active member of this project", status_code=403)
    now = datetime.now(timezone.utc)
    member.last_project_seen_at = now
    member.last_project_path = (path or "")[:500] or None
    if member.user is not None:
        member.user.last_seen_at = now
        db.add(member.user)
    db.add(member)
    db.commit()
    member = db.scalar(
        select(ProjectMember)
        .options(selectinload(ProjectMember.project), selectinload(ProjectMember.user))
        .where(ProjectMember.id == member.id)
    ) or member
    return serialize_member_for_read(member)


def create_invitation(db: Session, payload: InvitationCreate):
    project = None
    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    invitation = Invitation(
        email=payload.email,
        project_id=payload.project_id,
        role=payload.role,
        invited_by_user_id=payload.invited_by_user_id,
        token=secrets.token_urlsafe(24),
        note=payload.note,
    )
    db.add(invitation)
    db.flush()
    create_audit_log(
        db,
        project_id=invitation.project_id,
        actor_type="human",
        actor_id=payload.invited_by_user_id,
        action="invitation.created",
        resource_type="invitation",
        resource_id=invitation.id,
        after={"email": invitation.email, "role": invitation.role, "status": invitation.status},
    )
    db.commit()
    db.refresh(invitation)
    invitation = db.scalar(
        select(Invitation)
        .options(
            selectinload(Invitation.project),
            selectinload(Invitation.invited_by_user),
            selectinload(Invitation.accepted_by_user),
        )
        .where(Invitation.id == invitation.id)
    ) or invitation
    return invitation


def accept_invitation(db: Session, invitation_id: str, payload: InvitationAcceptRequest):
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise AppError("INVITATION_NOT_FOUND", "invitation not found", status_code=404)
    if invitation.status != "pending":
        raise AppError("INVITATION_CLOSED", "invitation already handled", status_code=400)

    user = db.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        if not payload.name:
            raise AppError("NAME_REQUIRED", "name is required for a new invited user", status_code=422)
        user = User(
            email=invitation.email,
            name=payload.name,
            display_name=payload.name,
            bio="member",
            is_active=True,
        )
        db.add(user)
        db.flush()

    invitation.status = "accepted"
    invitation.accepted_by_user_id = payload.accepted_by_user_id or user.id
    invitation.accepted_at = datetime.now(timezone.utc)
    db.add(invitation)

    if invitation.project_id:
        existing_member = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == invitation.project_id,
                ProjectMember.user_id == user.id,
            )
        )
        if existing_member is None:
            db.add(ProjectMember(project_id=invitation.project_id, user_id=user.id, role=invitation.role))

    create_audit_log(
        db,
        project_id=invitation.project_id,
        actor_type="human",
        actor_id=invitation.accepted_by_user_id,
        action="invitation.accepted",
        resource_type="invitation",
        resource_id=invitation.id,
        after={"email": invitation.email, "project_id": invitation.project_id, "role": invitation.role},
    )
    db.commit()
    db.refresh(invitation)
    return {"invitation": invitation, "user": user}


def get_auth_summary(db: Session) -> dict[str, int]:
    return {
        "users": int(db.scalar(select(func.count(User.id))) or 0),
        "pending_invitations": int(db.scalar(select(func.count(Invitation.id)).where(Invitation.status == "pending")) or 0),
        "accepted_invitations": int(db.scalar(select(func.count(Invitation.id)).where(Invitation.status == "accepted")) or 0),
        "project_members": int(db.scalar(select(func.count(ProjectMember.id))) or 0),
    }
