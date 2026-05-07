from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from fastapi.encoders import jsonable_encoder

from app.common.audit import append_audit_log
from app.common.collaboration_config import normalize_collaboration_config
from app.common.errors import AppError
from app.db.models.invitation import Invitation
from app.db.models.project_member import ProjectMember
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.user import User

from . import repo
from .schemas import (
    CollaborationConfigRead,
    ProjectConfigRead,
    ProjectConfigUpdate,
    ProjectCreate,
    ProjectRollbackRequest,
    ProjectSyncRequest,
    ProjectUpdate,
)

RUNNER_WATCH_FRESH_SECONDS = 180


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


def _runner_watch_snapshot(row: ProjectComputerNode, *, now: datetime) -> dict[str, object | None]:
    runner_id = str(row.runner_id or "").strip()
    runner = getattr(row, "runner", None)
    runner_status = str(getattr(runner, "status", "") or "").strip().lower() if runner else None
    runner_name = str(getattr(runner, "name", "") or "").strip() if runner else None
    last_heartbeat_at = _coerce_utc_datetime(getattr(runner, "last_heartbeat_at", None) if runner else None)
    heartbeat_age_seconds: int | None = None
    if last_heartbeat_at:
        heartbeat_age_seconds = max(0, int((now - last_heartbeat_at).total_seconds()))

    if not runner_id:
        watch_state = "unbound"
        effective_status = "offline"
        watch_detail = "This computer node has no runner binding yet."
    elif runner is None:
        watch_state = "runner_missing"
        effective_status = "offline"
        watch_detail = "The bound runner record was not found."
    elif not last_heartbeat_at:
        watch_state = "not_started"
        effective_status = runner_status or "offline"
        watch_detail = "The runner is registered, but no heartbeat has been received."
    elif heartbeat_age_seconds is not None and heartbeat_age_seconds <= RUNNER_WATCH_FRESH_SECONDS and runner_status in {
        "online",
        "ready",
        "active",
    }:
        watch_state = "watching"
        effective_status = "online"
        watch_detail = "The runner is actively heartbeating and can poll platform work."
    elif runner_status not in {"online", "ready", "active"}:
        watch_state = "runner_offline"
        effective_status = runner_status or "offline"
        watch_detail = "The runner is not online, so queued platform work will not be picked up."
    else:
        watch_state = "stale"
        effective_status = "stale"
        watch_detail = "The runner heartbeat is stale; restart the runner in watch mode."

    return {
        "runner_name": runner_name,
        "runner_status": runner_status,
        "runner_last_heartbeat_at": last_heartbeat_at,
        "runner_heartbeat_age_seconds": heartbeat_age_seconds,
        "runner_watch_state": watch_state,
        "runner_effective_status": effective_status,
        "runner_watch_fresh_seconds": RUNNER_WATCH_FRESH_SECONDS,
        "runner_watch_detail": watch_detail,
    }


def _store_inventory_rows(
    db: Session,
    model,
    project_id: str,
    rows: list[dict[str, object]],
    *,
    recognized_keys: set[str],
) -> None:
    system_keys = {"config_id", "row_id", "created_at", "updated_at"}
    existing_rows = list(db.scalars(select(model).where(model.project_id == project_id)))
    existing_by_config_id = {str(row.config_id): row for row in existing_rows}
    incoming_ids: set[str] = set()

    for index, item in enumerate(rows):
        config_id = str(item["id"])
        incoming_ids.add(config_id)
        row = existing_by_config_id.get(config_id)
        if row is None:
            row = model(project_id=project_id, config_id=config_id)
            db.add(row)

        row.sort_order = index
        row.project_id = project_id
        extra_data: dict[str, object] = dict(row.extra_data or {}) if getattr(row, "extra_data", None) else {}
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            extra_data.update(metadata)
        for key, value in item.items():
            if key in {"id", "project_id", "sort_order", "metadata"} or key in system_keys:
                continue
            if key in recognized_keys and hasattr(row, key):
                setattr(row, key, value)
            elif value is not None:
                extra_data[key] = value

        row.extra_data = extra_data or None

    for row in existing_rows:
        if str(row.config_id) not in incoming_ids:
            db.delete(row)


def sync_project_collaboration_inventory(db: Session, project: Project, raw_config: object | None = None) -> dict[str, object]:
    normalized = _normalize_collaboration_config(raw_config if raw_config is not None else project.collaboration_config)
    project.collaboration_config = normalized
    db.add(project)

    _store_inventory_rows(
        db,
        ProjectAIProvider,
        project.id,
        normalized.get("ai_providers") or [],
        recognized_keys={"id", "project_id", "label", "kind", "enabled", "endpoint", "model", "sort_order", "metadata"},
    )
    _store_inventory_rows(
        db,
        ProjectComputerNode,
        project.id,
        normalized.get("computer_nodes") or [],
        recognized_keys={"id", "project_id", "label", "status", "runner_id", "host", "os", "sort_order", "metadata"},
    )
    _store_inventory_rows(
        db,
        ProjectThreadWorkstation,
        project.id,
        normalized.get("thread_workstations") or [],
        recognized_keys={
            "id",
            "project_id",
            "name",
            "agent_id",
            "computer_node",
            "computer_node_id",
            "ai_provider",
            "ai_provider_id",
            "status",
            "description",
            "notes",
            "sort_order",
            "metadata",
        },
    )
    db.flush()
    return normalized


def _normalize_collaboration_config(raw: object | None) -> dict[str, object]:
    normalized = normalize_collaboration_config(raw)
    for index, item in enumerate(normalized.get("ai_providers") or []):
        if isinstance(item, dict):
            item.setdefault("sort_order", index)
    for index, item in enumerate(normalized.get("computer_nodes") or []):
        if isinstance(item, dict):
            item.setdefault("sort_order", index)
    for index, item in enumerate(normalized.get("thread_workstations") or []):
        if isinstance(item, dict):
            item.setdefault("sort_order", index)
    return normalized


def _build_collaboration_config_from_inventory(project: Project) -> dict[str, object]:
    stored_config = _normalize_collaboration_config(project.collaboration_config)
    extras = {
        key: value
        for key, value in stored_config.items()
        if key not in {"ai_providers", "computer_nodes", "thread_workstations"}
    }
    ai_rows = sorted(list(project.ai_providers or []), key=lambda item: (item.sort_order, str(item.created_at or "")))
    node_rows = sorted(list(project.computer_nodes or []), key=lambda item: (item.sort_order, str(item.created_at or "")))
    workstation_rows = sorted(
        list(project.thread_workstations or []), key=lambda item: (item.sort_order, str(item.created_at or ""))
    )

    provider_labels = {str(row.config_id): row.label for row in ai_rows}
    node_labels = {str(row.config_id): row.label for row in node_rows}
    now = datetime.now(timezone.utc)

    ai_providers: list[dict[str, object]] = []
    for row in ai_rows:
        metadata = dict(row.extra_data or {})
        ai_providers.append(
            {
                "id": row.config_id,
                "project_id": project.id,
                "label": row.label,
                "kind": row.kind,
                "enabled": bool(row.enabled),
                "endpoint": row.endpoint,
                "model": row.model or metadata.get("model"),
                "sort_order": row.sort_order,
                "metadata": metadata or None,
            }
        )

    computer_nodes: list[dict[str, object]] = []
    for row in node_rows:
        metadata = dict(row.extra_data or {})
        connection_kind = metadata.pop("connection_kind", None) or metadata.pop("kind", None)
        workspace_root = metadata.pop("workspace_root", None)
        git_root = metadata.pop("git_root", None)
        read_paths = metadata.pop("read_paths", None)
        write_paths = metadata.pop("write_paths", None)
        runner_watch = _runner_watch_snapshot(row, now=now)
        computer_nodes.append(
            {
                "id": row.config_id,
                "project_id": project.id,
                "label": row.label,
                "status": row.status,
                "runner_id": row.runner_id,
                **runner_watch,
                "connection_kind": connection_kind,
                "workspace_root": workspace_root,
                "git_root": git_root,
                "read_paths": read_paths,
                "write_paths": write_paths,
                "host": row.host,
                "os": row.os,
                "sort_order": row.sort_order,
                "metadata": metadata or None,
            }
        )

    thread_workstations: list[dict[str, object]] = []
    for row in workstation_rows:
        metadata = dict(row.extra_data or {})
        metadata.pop("computer_node", None)
        metadata.pop("ai_provider", None)
        node_id = row.computer_node_id
        provider_id = row.ai_provider_id
        thread_workstations.append(
            {
                "id": row.config_id,
                "config_id": row.config_id,
                "row_id": row.id,
                "project_id": project.id,
                "name": row.name,
                "agent_id": row.agent_id,
                "source_workstation_id": metadata.get("source_workstation_id"),
                "computer_node_id": node_id,
                "computer_node": metadata.get("computer_node") or node_labels.get(str(node_id or "")),
                "ai_provider_id": provider_id,
                "ai_provider": metadata.get("ai_provider") or provider_labels.get(str(provider_id or "")),
                "responsibility": metadata.get("responsibility"),
                "model": metadata.get("model"),
                "permission_level": metadata.get("permission_level"),
                "read_paths": metadata.get("read_paths"),
                "write_paths": metadata.get("write_paths"),
                "status": row.status,
                "description": row.description,
                "notes": row.notes,
                "sort_order": row.sort_order,
                "metadata": metadata or None,
            }
        )

    return _normalize_collaboration_config(
        {
            **extras,
            "ai_providers": ai_providers,
            "computer_nodes": computer_nodes,
            "thread_workstations": thread_workstations,
        }
    )


def _normalize_project_payload(payload: ProjectCreate | ProjectUpdate | ProjectConfigUpdate) -> dict[str, object]:
    data = payload.model_dump(exclude_unset=isinstance(payload, (ProjectUpdate, ProjectConfigUpdate)))
    if "collaboration_config" in data:
        data["collaboration_config"] = _normalize_collaboration_config(data["collaboration_config"])
    elif isinstance(payload, ProjectCreate):
        data["collaboration_config"] = _normalize_collaboration_config(None)
    if "requirement_policy" in data and data["requirement_policy"] is not None and isinstance(data["requirement_policy"], dict):
        data["requirement_policy"] = jsonable_encoder(data["requirement_policy"])
    return data


def serialize_project_for_read(project: Project) -> dict[str, object]:
    collaboration_config = _build_collaboration_config_from_inventory(project)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type,
        "requirement_policy": project.requirement_policy,
        "collaboration_config": collaboration_config,
        "github_url": project.github_url,
        "local_git_url": project.local_git_url,
        "default_branch": project.default_branch,
        "develop_branch": project.develop_branch,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def list_projects(db: Session):
    return repo.list_projects(db)


def get_project_or_404(db: Session, project_id: str):
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.ai_providers),
            selectinload(Project.computer_nodes).selectinload(ProjectComputerNode.runner),
            selectinload(Project.thread_workstations),
        )
    )
    if project is None:
        raise AppError("NOT_FOUND", "项目不存在", status_code=404)
    return project


def create_project(db: Session, payload: ProjectCreate, *, owner_user_id: str | None = None):
    project = repo.create_project(db, ProjectCreate(**_normalize_project_payload(payload)))
    sync_project_collaboration_inventory(db, project, project.collaboration_config)
    if owner_user_id:
        existing_member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == owner_user_id)
        )
        if existing_member is None:
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=owner_user_id,
                    role="owner",
                    status="active",
                    is_owner=True,
                )
            )
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project_id: str, payload: ProjectUpdate):
    project = get_project_or_404(db, project_id)
    updates = _normalize_project_payload(payload)
    updated_project = repo.update_project(db, project, ProjectUpdate(**updates))
    if "collaboration_config" in updates:
        sync_project_collaboration_inventory(db, updated_project, updates["collaboration_config"])
    db.commit()
    db.refresh(updated_project)
    return updated_project


def get_project_config(db: Session, project_id: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    collaboration_config = _build_collaboration_config_from_inventory(project)
    member_count = int(db.scalar(select(func.count(ProjectMember.id)).where(ProjectMember.project_id == project.id)) or 0)
    invitation_count = int(db.scalar(select(func.count(Invitation.id)).where(Invitation.project_id == project.id)) or 0)
    pending_invitation_count = int(
        db.scalar(select(func.count(Invitation.id)).where(Invitation.project_id == project.id, Invitation.status == "pending"))
        or 0
    )
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type,
        "requirement_policy": project.requirement_policy,
        "collaboration_config": collaboration_config,
        "github_url": project.github_url,
        "local_git_url": project.local_git_url,
        "default_branch": project.default_branch,
        "develop_branch": project.develop_branch,
        "member_count": member_count,
        "invitation_count": invitation_count,
        "pending_invitation_count": pending_invitation_count,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def update_project_config(db: Session, project_id: str, payload: ProjectConfigUpdate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = {
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type,
        "requirement_policy": project.requirement_policy,
        "collaboration_config": _normalize_collaboration_config(project.collaboration_config),
        "github_url": project.github_url,
        "local_git_url": project.local_git_url,
        "default_branch": project.default_branch,
        "develop_branch": project.develop_branch,
    }
    updates = _normalize_project_payload(payload)
    for key, value in updates.items():
        setattr(project, key, value)
    db.add(project)
    if "collaboration_config" in updates:
        sync_project_collaboration_inventory(db, project, updates["collaboration_config"])
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="human",
        actor_id=None,
        action="project.config_updated",
        resource_type="project",
        resource_id=project.id,
        before=jsonable_encoder(before),
        after=jsonable_encoder(get_project_config(db, project_id)),
    )
    db.commit()
    db.refresh(project)
    return get_project_config(db, project_id)


def add_project_member_to_project(
    db: Session,
    project_id: str,
    *,
    user_id: str,
    role: str = "member",
    status: str = "active",
    is_owner: bool = False,
) -> ProjectMember:
    project = get_project_or_404(db, project_id)
    user = db.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "user not found", status_code=404)
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id))
    before = None
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role, status=status, is_owner=is_owner)
        db.add(member)
        db.flush()
    else:
        before = {"role": member.role, "status": member.status, "is_owner": member.is_owner}
        member.role = role
        member.status = status
        member.is_owner = is_owner
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="human",
        actor_id=None,
        action="project_member.added",
        resource_type="project_member",
        resource_id=member.id,
        before=before,
        after={"project_id": project.id, "user_id": user.id, "role": member.role, "status": member.status, "is_owner": member.is_owner},
    )
    db.commit()
    db.refresh(member)
    member = (
        db.query(ProjectMember)
        .options(selectinload(ProjectMember.project), selectinload(ProjectMember.user))
        .filter(ProjectMember.id == member.id)
        .one()
    )
    return member


def sync_project_github(db: Session, project_id: str, payload: ProjectSyncRequest):
    project = get_project_or_404(db, project_id)
    result = {
        "project_id": project.id,
        "provider": payload.provider,
        "github_url": project.github_url,
        "local_git_url": project.local_git_url,
        "status": "queued",
        "notes": payload.notes or "已登记同步请求，第一版保留审计记录并由人工或外部任务执行实际同步。",
    }
    append_audit_log(
        db,
        project_id=project.id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="project.sync_github",
        resource_type="project",
        resource_id=project.id,
        before={},
        after=result,
    )
    db.commit()
    return result


def rollback_project(db: Session, project_id: str, payload: ProjectRollbackRequest):
    project = get_project_or_404(db, project_id)
    result = {
        "project_id": project.id,
        "target_ref": payload.target_ref,
        "status": "queued",
        "notes": payload.notes or "已登记回滚请求，第一版保留审计记录并由人类确认后执行。",
    }
    append_audit_log(
        db,
        project_id=project.id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="project.rollback_requested",
        resource_type="project",
        resource_id=project.id,
        before={},
        after=result,
    )
    db.commit()
    return result
