from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.common.audit import append_audit_log
from app.common.collaboration_config import normalize_collaboration_config
from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_dispatch import TaskDispatch
from app.db.models.task_event import TaskEvent
from app.modules.projects.service import RUNNER_WATCH_FRESH_SECONDS, _runner_watch_snapshot, sync_project_collaboration_inventory
from app.modules.tasks import repo as task_repo
from app.modules.tasks.schemas import TaskTransitionCreate
from app.modules.tasks.service import record_task_log, record_task_result, transition_task_status

from . import repo
from .schemas import RunnerRegister
from .schemas import RunnerThreadWorkstationSyncCreate


def _runner_binding_rows(db: Session, runner_id: str) -> list[dict[str, object]]:
    stmt = (
        select(ProjectComputerNode, Project.name, Project.develop_branch, Project.default_branch)
        .join(Project, Project.id == ProjectComputerNode.project_id)
        .where(ProjectComputerNode.runner_id == runner_id)
        .order_by(Project.created_at.desc(), ProjectComputerNode.sort_order.asc(), ProjectComputerNode.created_at.asc())
    )
    bindings: list[dict[str, object]] = []
    now = datetime.now(timezone.utc)
    for node, project_name, develop_branch, default_branch in db.execute(stmt).all():
        watch = _runner_watch_snapshot(node, now=now)
        bindings.append(
            {
                "project_id": node.project_id,
                "project_name": project_name,
                "project_default_branch": default_branch,
                "project_develop_branch": develop_branch,
                "computer_node_id": node.config_id,
                "computer_node_label": node.label,
                "computer_node_status": node.status,
                "computer_node_host": node.host,
                "computer_node_os": node.os,
                "sort_order": node.sort_order,
                **watch,
            }
        )
    return bindings


def _workstation_source(extra_data: object | None) -> str | None:
    if not isinstance(extra_data, dict):
        return None
    source = str(extra_data.get("source") or "").strip()
    return source or None


def _workstation_metadata_label(extra_data: object | None, key: str) -> str | None:
    if not isinstance(extra_data, dict):
        return None
    value = str(extra_data.get(key) or "").strip()
    return value or None


def _runner_scan_provider_key(item: dict[str, object]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    candidates = [
        item.get("ai_provider_id"),
        metadata.get("provider_family"),
        metadata.get("ai_provider_id"),
        item.get("ai_provider"),
        metadata.get("ai_provider_label"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if not value:
            continue
        if "codex" in value:
            return "codex"
        if "claude" in value or "anthropic" in value:
            return "claude"
        if "qwen" in value:
            return "qwen"
        if "glm" in value:
            return "glm"
        if "openclaw" in value:
            return "openclaw"
        return value
    return ""


def _runner_workstation_rows(db: Session, runner_id: str) -> list[dict[str, object]]:
    stmt = (
        select(
            Project.id,
            Project.name,
            ProjectThreadWorkstation.config_id,
            ProjectThreadWorkstation.name,
            ProjectThreadWorkstation.status,
            ProjectThreadWorkstation.agent_id,
            ProjectThreadWorkstation.computer_node_id,
            ProjectThreadWorkstation.ai_provider_id,
            ProjectThreadWorkstation.description,
            ProjectThreadWorkstation.notes,
            ProjectThreadWorkstation.extra_data,
            ProjectComputerNode.label,
            ProjectAIProvider.label,
        )
        .join(Project, Project.id == ProjectThreadWorkstation.project_id)
        .outerjoin(
            ProjectComputerNode,
            (ProjectComputerNode.project_id == ProjectThreadWorkstation.project_id)
            & (ProjectComputerNode.config_id == ProjectThreadWorkstation.computer_node_id),
        )
        .outerjoin(
            ProjectAIProvider,
            (ProjectAIProvider.project_id == ProjectThreadWorkstation.project_id)
            & (ProjectAIProvider.config_id == ProjectThreadWorkstation.ai_provider_id),
        )
        .where(ProjectComputerNode.runner_id == runner_id)
        .order_by(Project.created_at.desc(), ProjectThreadWorkstation.sort_order.asc(), ProjectThreadWorkstation.created_at.asc())
    )

    workstations: list[dict[str, object]] = []
    for (
        project_id,
        project_name,
        workstation_id,
        workstation_name,
        workstation_status,
        agent_id,
        computer_node_id,
        ai_provider_id,
        description,
        notes,
        extra_data,
        computer_node_label,
        ai_provider_label,
    ) in db.execute(stmt).all():
        source = _workstation_source(extra_data)
        provider_label = _workstation_metadata_label(extra_data, "ai_provider_label") or ai_provider_label
        workstations.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "workstation_id": workstation_id,
                "workstation_name": workstation_name,
                "workstation_status": workstation_status,
                "source": source,
                "computer_node_id": computer_node_id,
                "computer_node_label": computer_node_label,
                "ai_provider_id": ai_provider_id,
                "ai_provider_label": provider_label,
                "agent_id": agent_id,
                "description": description,
                "notes": notes,
                "metadata": extra_data if isinstance(extra_data, dict) else {},
            }
        )
    return workstations


def _serialize_task_summary(task: Task | None) -> dict[str, object] | None:
    if task is None:
        return None
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "branch": task.branch,
        "assignee_agent_id": task.assignee_agent_id,
        "updated_at": task.updated_at,
    }


def _runner_active_tasks(db: Session, runner_id: str) -> list[Task]:
    picked_task_ids = list(
        db.scalars(
            select(TaskEvent.task_id)
            .where(TaskEvent.actor_type == "runner", TaskEvent.actor_id == runner_id, TaskEvent.event_type == "runner_picked")
            .order_by(TaskEvent.created_at.desc())
        )
    )
    if not picked_task_ids:
        return []
    stmt = (
        select(Task)
        .where(Task.id.in_(picked_task_ids), Task.status.in_(["running", "reviewing", "blocked", "needs_changes"]))
        .order_by(Task.updated_at.desc(), Task.created_at.desc())
    )
    return list(db.scalars(stmt))


def _runner_recent_events(db: Session, runner_id: str, *, limit: int = 8) -> list[dict[str, object]]:
    stmt = (
        select(TaskEvent, Task.title, Task.project_id)
        .join(Task, Task.id == TaskEvent.task_id)
        .where(TaskEvent.actor_type == "runner", TaskEvent.actor_id == runner_id)
        .order_by(TaskEvent.created_at.desc())
        .limit(limit)
    )
    rows: list[dict[str, object]] = []
    for event, task_title, project_id in db.execute(stmt).all():
        rows.append(
            {
                "task_id": event.task_id,
                "task_title": task_title,
                "project_id": project_id,
                "event_type": event.event_type,
                "message": event.message,
                "created_at": event.created_at,
                "data": event.data or {},
            }
        )
    return rows


def _runner_recent_errors(db: Session, runner_id: str, *, limit: int = 5) -> list[dict[str, object]]:
    events = _runner_recent_events(db, runner_id, limit=20)
    errors: list[dict[str, object]] = []
    for item in events:
        event_type = str(item.get("event_type") or "")
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        status = str(data.get("status") or "").lower()
        if event_type == "log:error" or status in {"failed", "blocked"}:
            errors.append(item)
        if len(errors) >= limit:
            break
    return errors


def serialize_runner_for_read(db: Session, runner):
    agents = getattr(runner, "agents", []) or []
    bindings = _runner_binding_rows(db, runner.id)
    primary_binding = bindings[0] if bindings else None
    active_tasks = _runner_active_tasks(db, runner.id)
    recent_events = _runner_recent_events(db, runner.id)
    recent_errors = _runner_recent_errors(db, runner.id)
    return {
        "id": runner.id,
        "name": runner.name,
        "host": runner.host,
        "os": runner.os,
        "capabilities": runner.capabilities,
        "status": runner.status,
        "allow_hardware_access": runner.allow_hardware_access,
        "max_concurrent_tasks": runner.max_concurrent_tasks,
        "computer_node_id": primary_binding["computer_node_id"] if primary_binding else None,
        "computer_node_label": primary_binding["computer_node_label"] if primary_binding else None,
        "node_kind": "computer_node" if bindings else "runner",
        "bound_project_count": len({str(binding["project_id"]) for binding in bindings}),
        "computer_node_bindings": bindings,
        "agent_count": len(agents),
        "current_task": _serialize_task_summary(active_tasks[0] if active_tasks else None),
        "recent_errors": recent_errors,
        "recent_events": recent_events,
        "last_heartbeat_at": runner.last_heartbeat_at,
        "created_at": runner.created_at,
        "updated_at": runner.updated_at,
    }


def serialize_runner_workspace(db: Session, runner):
    bindings = _runner_binding_rows(db, runner.id)
    workstations = _runner_workstation_rows(db, runner.id)
    active_tasks = _runner_active_tasks(db, runner.id)
    recent_events = _runner_recent_events(db, runner.id)
    recent_errors = _runner_recent_errors(db, runner.id)
    workstation_count_by_binding: dict[tuple[str, str], int] = {}
    for workstation in workstations:
        key = (str(workstation["project_id"]), str(workstation["computer_node_id"] or ""))
        workstation_count_by_binding[key] = workstation_count_by_binding.get(key, 0) + 1
    for binding in bindings:
        key = (str(binding["project_id"]), str(binding["computer_node_id"] or ""))
        binding["workstation_count"] = workstation_count_by_binding.get(key, 0)
    return {
        "runner": serialize_runner_for_read(db, runner),
        "binding_count": len(bindings),
        "project_count": len({str(binding["project_id"]) for binding in bindings}),
        "computer_node_count": len({str(binding["computer_node_id"]) for binding in bindings}),
        "bindings": bindings,
        "workstations": workstations,
        "active_task_count": len(active_tasks),
        "recent_errors": recent_errors,
        "recent_events": recent_events,
    }


def _binding_row_or_404(db: Session, project_id: str, computer_node_id: str) -> tuple[Project, ProjectComputerNode]:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    node = db.scalar(
        select(ProjectComputerNode).where(
            ProjectComputerNode.project_id == project_id,
            ProjectComputerNode.config_id == computer_node_id,
        )
    )
    if node is None:
        raise AppError("COMPUTER_NODE_NOT_FOUND", "computer node not found", status_code=404)
    return project, node


def _sync_binding_into_project_config(project: Project, computer_node_id: str, runner_id: str | None) -> None:
    config = normalize_collaboration_config(project.collaboration_config)
    for node in config.get("computer_nodes") or []:
        if isinstance(node, dict) and str(node.get("id") or "") == str(computer_node_id):
            node["runner_id"] = runner_id
            break
    project.collaboration_config = config


def _binding_read(db: Session, runner_id: str, project_id: str, computer_node_id: str) -> dict[str, object]:
    for binding in _runner_binding_rows(db, runner_id):
        if str(binding["project_id"]) == str(project_id) and str(binding["computer_node_id"]) == str(computer_node_id):
            return {"runner_id": runner_id, **binding}
    raise AppError("RUNNER_BINDING_NOT_FOUND", "runner binding not found", status_code=404)


def _runner_bound_project_ids(db: Session, runner_id: str) -> list[str]:
    stmt = select(ProjectComputerNode.project_id).where(ProjectComputerNode.runner_id == runner_id).distinct()
    return [str(project_id) for project_id in db.scalars(stmt).all() if str(project_id)]


def _pending_high_risk_approvals(db: Session, task_id: str) -> list[Approval]:
    stmt = (
        select(Approval)
        .where(
            Approval.task_id == task_id,
            Approval.status == "pending",
            Approval.level.in_(["H3", "H4"]),
        )
        .order_by(Approval.created_at.asc())
    )
    return list(db.scalars(stmt))


def bind_runner_to_computer_node(db: Session, runner_id: str, project_id: str, computer_node_id: str) -> dict[str, object]:
    runner = get_runner_or_404(db, runner_id)
    project, node = _binding_row_or_404(db, project_id, computer_node_id)
    if node.runner_id is not None and node.runner_id != runner.id:
        raise AppError("RUNNER_BINDING_CONFLICT", "computer node already bound to another runner", status_code=409)

    before = {
        "runner_id": node.runner_id,
        "project_id": project_id,
        "computer_node_id": computer_node_id,
    }
    node.runner_id = runner.id
    db.add(node)
    _sync_binding_into_project_config(project, computer_node_id, runner.id)
    sync_project_collaboration_inventory(db, project, project.collaboration_config)
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="system",
        actor_id=runner.id,
        action="runner.binding.created",
        resource_type="computer_node",
        resource_id=computer_node_id,
        before=before,
        after={
            "runner_id": runner.id,
            "project_id": project_id,
            "computer_node_id": computer_node_id,
        },
    )
    db.commit()
    return _binding_read(db, runner.id, project_id, computer_node_id)


def unbind_runner_from_computer_node(db: Session, runner_id: str, project_id: str, computer_node_id: str) -> dict[str, object]:
    runner = get_runner_or_404(db, runner_id)
    project, node = _binding_row_or_404(db, project_id, computer_node_id)
    if str(node.runner_id or "") != runner.id:
        raise AppError("RUNNER_BINDING_NOT_FOUND", "computer node is not bound to this runner", status_code=404)

    before = {
        "runner_id": node.runner_id,
        "project_id": project_id,
        "computer_node_id": computer_node_id,
    }
    node.runner_id = None
    db.add(node)
    _sync_binding_into_project_config(project, computer_node_id, None)
    sync_project_collaboration_inventory(db, project, project.collaboration_config)
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="system",
        actor_id=runner.id,
        action="runner.binding.deleted",
        resource_type="computer_node",
        resource_id=computer_node_id,
        before=before,
        after={
            "runner_id": runner.id,
            "project_id": project_id,
            "computer_node_id": computer_node_id,
            "status": "unbound",
        },
    )
    db.commit()
    return {
        "runner_id": runner.id,
        "project_id": project_id,
        "computer_node_id": computer_node_id,
        "status": "unbound",
    }


def sync_runner_thread_workstations(
    db: Session,
    runner_id: str,
    payload: RunnerThreadWorkstationSyncCreate,
) -> dict[str, object]:
    runner = get_runner_or_404(db, runner_id)
    project, node = _binding_row_or_404(db, payload.project_id, payload.computer_node_id)
    if str(node.runner_id or "") != runner.id:
        raise AppError("RUNNER_BINDING_NOT_FOUND", "computer node is not bound to this runner", status_code=404)

    config = normalize_collaboration_config(project.collaboration_config)
    existing = list(config.get("thread_workstations") or [])
    incoming_items = [workstation.model_dump(mode="json") for workstation in payload.workstations]
    incoming_provider_keys = {
        provider_key
        for provider_key in (_runner_scan_provider_key(item) for item in incoming_items)
        if provider_key
    }
    retained: list[dict[str, object]] = []
    for item in existing:
        if not isinstance(item, dict):
            continue
        same_node = str(item.get("computer_node_id") or "") == payload.computer_node_id
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source = str(metadata.get("source") or "").strip()
        provider_key = _runner_scan_provider_key(item)
        should_replace_scan = same_node and not item.get("authoritative_seat_id") and source == "runner_thread_scan" and (
            not incoming_provider_keys or (provider_key in incoming_provider_keys)
        )
        if not should_replace_scan:
            retained.append(dict(item))

    def _item_match_keys(raw_item: dict[str, object]) -> set[str]:
        metadata = raw_item.get("metadata") if isinstance(raw_item.get("metadata"), dict) else {}
        keys = {
            str(raw_item.get("id") or "").strip(),
            str(raw_item.get("config_id") or "").strip(),
            str(raw_item.get("agent_id") or "").strip(),
            str(raw_item.get("name") or "").strip(),
            str(metadata.get("thread_title") or "").strip(),
            str(metadata.get("bound_thread_label") or "").strip(),
        }
        return {key for key in keys if key}

    def _find_retained_index_for_scan(scan_item: dict[str, object]) -> int | None:
        scan_keys = _item_match_keys(
            {
                "id": scan_item.get("workstation_id"),
                "agent_id": scan_item.get("agent_id"),
                "name": scan_item.get("workstation_name"),
                "metadata": scan_item.get("metadata") if isinstance(scan_item.get("metadata"), dict) else {},
            }
        )
        if not scan_keys:
            return None
        for retained_index, retained_item in enumerate(retained):
            retained_keys = _item_match_keys(retained_item)
            if scan_keys & retained_keys:
                return retained_index
        return None

    synced_items: list[dict[str, object]] = []
    for index, item in enumerate(incoming_items):
        incoming_metadata = dict(item.get("metadata") or {})
        skill_loadout = [
            str(skill).strip()
            for skill in item.get("skill_loadout") or []
            if str(skill).strip()
        ]
        metadata = {
            "source": "runner_thread_scan",
            "cwd": item.get("cwd"),
            "runner_id": runner.id,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata.update(
            {
                key: value
                for key, value in incoming_metadata.items()
                if key not in {"source", "cwd", "runner_id", "synced_at"}
            }
        )
        if skill_loadout:
            metadata["skill_loadout"] = skill_loadout
        if item.get("ai_provider_label"):
            metadata["ai_provider_label"] = item.get("ai_provider_label")
        workstation_id = str(item.get("workstation_id") or item.get("workstation_name") or f"{payload.computer_node_id}-thread-{index+1}").strip()
        workstation_name = str(item.get("workstation_name") or item.get("workstation_id") or f"线程 {index+1}").strip()
        merged_item: dict[str, object] = {
            "id": workstation_id,
            "name": workstation_name,
            "agent_id": item.get("agent_id"),
            "computer_node_id": payload.computer_node_id,
            "computer_node": node.label,
            "ai_provider_id": item.get("ai_provider_id"),
            "ai_provider": item.get("ai_provider_label") or item.get("ai_provider_id"),
            "status": str(item.get("workstation_status") or "idle").strip() or "idle",
            "description": item.get("description"),
            "notes": item.get("notes"),
            "model": item.get("model"),
            "source_workstation_id": workstation_id,
            "bound_thread_id": workstation_id,
            "metadata": metadata,
        }
        retained_index = _find_retained_index_for_scan(item)
        if retained_index is not None:
            current = dict(retained[retained_index])
            current_metadata = dict(current.get("metadata") or {}) if isinstance(current.get("metadata"), dict) else {}
            existing_source = str(current_metadata.get("source") or "").strip()
            current_metadata.update(metadata)
            if existing_source and existing_source != "runner_thread_scan":
                current_metadata["source"] = existing_source
                current_metadata["runner_thread_scan_source"] = "runner_thread_scan"
            current_metadata["desktop_visible"] = True
            current_metadata["thread_binding_label"] = workstation_name
            current.update(
                {
                    key: value
                    for key, value in merged_item.items()
                    if value not in (None, "")
                    and key not in {"id", "name", "metadata"}
                }
            )
            current["id"] = str(current.get("id") or workstation_id).strip() or workstation_id
            current["name"] = str(current.get("name") or workstation_name).strip() or workstation_name
            current["metadata"] = current_metadata
            retained[retained_index] = current
            synced_items.append(current)
        else:
            synced_items.append(merged_item)

    retained_ids = {id(item) for item in synced_items}
    retained.extend(item for item in synced_items if id(item) not in retained_ids or item not in retained)
    config["thread_workstations"] = retained
    node_scan_items = [
        item
        for item in retained
        if isinstance(item, dict)
        and str(item.get("computer_node_id") or "") == payload.computer_node_id
        and (
            str((item.get("metadata") if isinstance(item.get("metadata"), dict) else {}).get("source") or "").strip()
            == "runner_thread_scan"
            or str((item.get("metadata") if isinstance(item.get("metadata"), dict) else {}).get("runner_thread_scan_source") or "").strip()
            == "runner_thread_scan"
        )
    ]

    for item in config.get("computer_nodes") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == payload.computer_node_id:
            metadata = dict(item.get("metadata") or {})
            metadata["thread_scan"] = {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "runner_id": runner.id,
                "thread_count": len(node_scan_items),
                "threads": [
                    {
                        "workstation_id": station["id"],
                        "workstation_name": station["name"],
                        "workstation_status": station["status"],
                    }
                    for station in node_scan_items
                ],
            }
            item["metadata"] = metadata
            break

    before = {
        "project_id": payload.project_id,
        "computer_node_id": payload.computer_node_id,
        "thread_count": len([item for item in existing if isinstance(item, dict) and str(item.get("computer_node_id") or "") == payload.computer_node_id]),
    }
    project.collaboration_config = config
    db.add(project)
    sync_project_collaboration_inventory(db, project, config)
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="runner",
        actor_id=runner.id,
        action="runner.thread_scan.synced",
        resource_type="computer_node",
        resource_id=payload.computer_node_id,
        before=before,
        after={
            "project_id": payload.project_id,
            "computer_node_id": payload.computer_node_id,
            "thread_count": len(synced_items),
        },
    )
    db.commit()
    return {
        "runner_id": runner.id,
        "project_id": payload.project_id,
        "computer_node_id": payload.computer_node_id,
        "thread_count": len(synced_items),
        "workstations": synced_items,
    }


def list_runners(db: Session):
    return repo.list_runners(db)


def get_runner_or_404(db: Session, runner_id: str):
    runner = repo.get_runner(db, runner_id)
    if runner is None:
        raise AppError("NOT_FOUND", "Runner not found", status_code=404)
    return runner


def register_runner(db: Session, payload: RunnerRegister):
    return repo.register_runner(db, payload)


def register_runner_with_binding(db: Session, payload: RunnerRegister, *, project_id: str, computer_node_id: str):
    runner = repo.register_runner(db, payload)
    bind_runner_to_computer_node(db, runner.id, project_id, computer_node_id)
    return get_runner_or_404(db, runner.id)


def heartbeat(db: Session, runner_id: str):
    return repo.heartbeat(db, get_runner_or_404(db, runner_id))


def mark_stale_runners_offline(db: Session, *, stale_after_seconds: int | None = None) -> dict[str, object]:
    """Flip Runner.status to "offline" for any runner whose heartbeat is past
    ``stale_after_seconds`` (default: ``RUNNER_WATCH_FRESH_SECONDS``).

    Without this sweep, Runner.status stays "online" forever — the value is only
    written by ``register`` and ``heartbeat``. The dashboard's online/offline
    counts (apps/api/app/modules/runners/router.py:144-145 and
    apps/api/app/modules/lab/service.py:28) read raw ``Runner.status`` and would
    keep counting dead runners as online even when their last heartbeat was
    hours old. Acceptance fix for "我刚接入 runner 时是在线的, 后面一堆操作不知道
    是不是掉了".
    """
    threshold_seconds = stale_after_seconds if stale_after_seconds is not None else RUNNER_WATCH_FRESH_SECONDS
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(0, int(threshold_seconds)))

    flipped: list[dict[str, object]] = []
    stmt = select(Runner).where(Runner.status.in_(["online", "ready", "active"]))
    for runner in db.scalars(stmt).all():
        last_hb = runner.last_heartbeat_at
        if last_hb is None:
            # Never heartbeated since registration. Treat as offline once we run
            # the sweep at least RUNNER_WATCH_FRESH_SECONDS after creation.
            created_at = runner.created_at
            if created_at is None:
                continue
            created_aware = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            if created_aware > cutoff:
                continue
        else:
            last_aware = last_hb if last_hb.tzinfo else last_hb.replace(tzinfo=timezone.utc)
            if last_aware > cutoff:
                continue
        before_status = runner.status
        runner.status = "offline"
        db.add(runner)
        flipped.append(
            {
                "runner_id": runner.id,
                "before": before_status,
                "after": "offline",
                "last_heartbeat_at": last_hb.isoformat() if last_hb else None,
            }
        )

    if flipped:
        db.commit()

    return {
        "checked_at": now.isoformat(),
        "stale_after_seconds": int(threshold_seconds),
        "flipped_count": len(flipped),
        "flipped": flipped,
    }


def fetch_next_task(db: Session, runner_id: str):
    get_runner_or_404(db, runner_id)
    project_ids = _runner_bound_project_ids(db, runner_id)
    if not project_ids:
        return None

    stmt = (
        select(Task, TaskDispatch)
        .join(TaskDispatch, TaskDispatch.task_id == Task.id)
        .where(
            Task.status.in_(["ready", "queued"]),
            Task.project_id.in_(project_ids),
            TaskDispatch.runner_id == runner_id,
            TaskDispatch.status.in_(["dispatched", "queued", "delivered", "pending", "created"]),
        )
        .order_by(
            case(
                (Task.priority == "P0", 0),
                (Task.priority == "P1", 1),
                (Task.priority == "P2", 2),
                (Task.priority == "P3", 3),
                else_=4,
            ),
            TaskDispatch.created_at.asc(),
            Task.created_at.asc(),
        )
    )
    task = None
    dispatch = None
    for candidate, candidate_dispatch in db.execute(stmt):
        if _pending_high_risk_approvals(db, candidate.id):
            continue
        task = candidate
        dispatch = candidate_dispatch
        break
    if task is None:
        single_runner_project_ids: list[str] = []
        for project_id in project_ids:
            bound_runner_ids = {
                str(value or "").strip()
                for value in db.scalars(
                    select(ProjectComputerNode.runner_id).where(
                        ProjectComputerNode.project_id == project_id,
                        ProjectComputerNode.runner_id.is_not(None),
                    )
                )
                if str(value or "").strip()
            }
            if bound_runner_ids == {runner_id}:
                single_runner_project_ids.append(project_id)
        if single_runner_project_ids:
            fallback_stmt = (
                select(Task)
                .where(
                    Task.status == "ready",
                    Task.project_id.in_(single_runner_project_ids),
                    ~select(TaskDispatch.id).where(TaskDispatch.task_id == Task.id).exists(),
                )
                .order_by(
                    case(
                        (Task.priority == "P0", 0),
                        (Task.priority == "P1", 1),
                        (Task.priority == "P2", 2),
                        (Task.priority == "P3", 3),
                        else_=4,
                    ),
                    Task.created_at.asc(),
                )
            )
            for candidate in db.scalars(fallback_stmt):
                if _pending_high_risk_approvals(db, candidate.id):
                    continue
                task = candidate
                break
    if task is None:
        return None

    before = {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "module": task.module,
        "priority": task.priority,
        "status": task.status,
        "branch": task.branch,
        "related_issue": task.related_issue,
        "assignee_agent_id": task.assignee_agent_id,
        "reviewers": list(task.reviewers or []),
        "acceptance_criteria": list(task.acceptance_criteria or []),
    }
    task.status = "running"
    db.add(task)
    if dispatch is not None:
        dispatch.status = "running"
        db.add(dispatch)
    task_repo.create_task_event(
        db,
        task.id,
        "runner_picked",
        f"Runner claimed task: {runner_id}",
        {
            "runner_id": runner_id,
            "dispatch_id": dispatch.id if dispatch is not None else None,
            "from_status": before["status"],
            "to_status": "running",
        },
        actor_type="runner",
        actor_id=runner_id,
        commit=False,
    )
    append_audit_log(
        db,
        task_id=task.id,
        actor_type="runner",
        actor_id=runner_id,
        action="runner.claim_task",
        resource_type="task",
        resource_id=task.id,
        before=before,
        after={
            **before,
            "status": "running",
        },
    )
    db.commit()
    db.refresh(task)
    return task


def record_runner_log(db: Session, runner_id: str, task_id: str, level: str, message: str, data: dict | None = None):
    get_runner_or_404(db, runner_id)
    return record_task_log(db, task_id, level, message, runner_id=runner_id, data=data)


def record_runner_result(
    db: Session,
    runner_id: str,
    task_id: str,
    result: dict,
    *,
    status: str | None = None,
    message: str | None = None,
    data: dict | None = None,
):
    get_runner_or_404(db, runner_id)
    return record_task_result(db, task_id, result, runner_id=runner_id, status=status, message=message, data=data)


def transition_runner_task(
    db: Session,
    runner_id: str,
    task_id: str,
    status: str,
    *,
    message: str | None = None,
    data: dict | None = None,
):
    get_runner_or_404(db, runner_id)
    return transition_task_status(
        db,
        task_id,
        TaskTransitionCreate(
            status=status,
            actor_type="runner",
            actor_id=runner_id,
            message=message,
            data=data or {},
        ),
    )
