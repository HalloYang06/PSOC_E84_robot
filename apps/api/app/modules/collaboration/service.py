from __future__ import annotations

import hashlib
import secrets
import re
from datetime import datetime, timezone
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import append_audit_log
from app.common.collaboration_config import normalize_collaboration_config
from app.common.errors import AppError
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.project_invite import ProjectInvite
from app.db.models.project_member import ProjectMember
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_dispatch import TaskDispatch
from app.db.models.user import User
from app.modules.projects.service import get_project_config, get_project_or_404, sync_project_collaboration_inventory
from app.modules.tasks import repo as task_repo
from app.modules.tasks.service import claim_task_for_runner, record_task_result, sync_task_dispatch_status

from .schemas import (
    CollaborationComputerNodeCreate,
    CollaborationComputerNodeUpdate,
    CollaborationConfigUpdate,
    CollaborationMessageCreate,
    CollaborationMessageUpdate,
    CollaborationProviderCreate,
    CollaborationProviderUpdate,
    RunnerRelayAckCreate,
    RunnerRelayCommandCreate,
    RunnerRelayCompleteCreate,
    WorkstationInboxAckCreate,
    WorkstationInboxCompleteCreate,
    ProjectInviteAcceptRequest,
    ProjectInviteCreate,
    ProjectInviteUpdate,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    CollaborationWorkstationCreate,
    CollaborationWorkstationUpdate,
    UserCreate,
    UserUpdate,
)


def _generate_unique_invite_token(db: Session) -> str:
    for _ in range(10):
        token = secrets.token_urlsafe(24)
        exists = db.scalar(select(ProjectInvite.id).where(ProjectInvite.token == token).limit(1))
        if not exists:
            return token
    raise AppError("INVITE_TOKEN_GENERATION_FAILED", "unable to generate a unique invite token", status_code=500)


def _generate_config_id(prefix: str, value: object, existing_ids: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    candidate = slug or f"{prefix}-{uuid.uuid4().hex[:8]}"
    while candidate in existing_ids:
        candidate = f"{candidate}-{uuid.uuid4().hex[:4]}"
    return candidate


def _project_collaboration_config(project: Project) -> dict[str, object]:
    return normalize_collaboration_config(project.collaboration_config)


def _project_collaboration_items(project: Project, section: str) -> list[dict[str, object]]:
    config = _project_collaboration_config(project)
    return [dict(item) for item in config.get(section) or []]


def _workstation_is_runner_scan(item: dict[str, object]) -> bool:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("source") or "").strip() == "runner_thread_scan"


def _save_project_collaboration_config(
    db: Session,
    project: Project,
    *,
    before: dict[str, object],
    after: dict[str, object],
    action: str,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> dict[str, object]:
    project.collaboration_config = normalize_collaboration_config(after)
    db.add(project)
    sync_project_collaboration_inventory(db, project, project.collaboration_config)
    append_audit_log(
        db,
        project_id=project.id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type="project",
        resource_id=project.id,
        before=before,
        after=project.collaboration_config,
    )
    db.commit()
    db.refresh(project)
    return get_project_config(db, project.id)


def _update_project_collaboration_section(
    db: Session,
    project_id: str,
    section: str,
    payload: list[dict[str, object]],
    *,
    action: str,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    after = dict(before)
    after[section] = payload
    return _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
    )


def _find_item_index(items: list[dict[str, object]], identifier: str, *, section: str) -> int:
    for index, item in enumerate(items):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        extra_data = item.get("extra_data") if isinstance(item.get("extra_data"), dict) else {}
        candidates = {
            str(item.get("id") or ""),
            str(item.get("config_id") or ""),
            str(item.get("label") or ""),
            str(item.get("name") or ""),
            str(item.get("row_id") or ""),
            str(item.get("source_workstation_id") or ""),
            str(metadata.get("source_workstation_id") or ""),
            str(extra_data.get("source_workstation_id") or ""),
        }
        if identifier in candidates:
            return index
    raise AppError("NOT_FOUND", f"{section} does not exist", status_code=404)


def _conflict_if_exists(
    items: list[dict[str, object]],
    *,
    key: str,
    value: str,
    section: str,
    excluding_index: int | None = None,
) -> None:
    for index, item in enumerate(items):
        if excluding_index is not None and index == excluding_index:
            continue
        if str(item.get(key) or "") == value:
            raise AppError("CONFLICT", f"{section} identifier already exists", status_code=409)


def _section_payload(project: Project, section: str) -> list[dict[str, object]]:
    return _project_collaboration_items(project, section)


def _enrich_computer_nodes_with_thread_scan(project: Project, nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    workstations = _project_collaboration_items(project, "thread_workstations")
    grouped: dict[str, list[dict[str, object]]] = {}
    for station in workstations:
        if not isinstance(station, dict):
            continue
        if not _workstation_is_runner_scan(station):
            continue
        node_id = str(station.get("computer_node_id") or "").strip()
        if not node_id:
            continue
        grouped.setdefault(node_id, []).append(station)

    enriched: list[dict[str, object]] = []
    for node in nodes:
        item = dict(node)
        node_id = str(item.get("id") or "").strip()
        node_threads = grouped.get(node_id, [])
        metadata = dict(item.get("metadata") or {})
        scan = dict(metadata.get("thread_scan") or {})
        if node_threads or scan:
            scan["status"] = scan.get("status") or "completed"
            scan["thread_count"] = len(node_threads)
            scan["threads"] = [
                {
                    "workstation_id": str(station.get("id") or station.get("workstation_id") or "").strip(),
                    "workstation_name": str(station.get("name") or station.get("workstation_name") or "").strip(),
                    "workstation_status": str(station.get("status") or station.get("workstation_status") or "idle").strip() or "idle",
                }
                for station in node_threads
            ]
        if scan:
            metadata["thread_scan"] = scan
        elif "thread_scan" in metadata:
            metadata.pop("thread_scan", None)
        item["metadata"] = metadata
        enriched.append(item)
    return enriched


def get_project_collaboration_config(db: Session, project_id: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    return get_project_config(db, project.id)


def update_project_collaboration_config(db: Session, project_id: str, payload: CollaborationConfigUpdate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    after = dict(before)
    data = payload.model_dump(exclude_unset=True)
    for section in ("thread_workstations", "ai_providers", "computer_nodes"):
        if section in data:
            after[section] = [dict(item) for item in data[section] or []]
    if "review_policy" in data:
        after["review_policy"] = dict(data["review_policy"] or {})
    if "workstation_profiles" in data:
        profiles = data["workstation_profiles"] or {}
        after["workstation_profiles"] = {
            str(k): dict(v) if isinstance(v, dict) else {}
            for k, v in profiles.items()
        }
    return _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_config_updated",
    )


def list_project_ai_providers(db: Session, project_id: str) -> list[dict[str, object]]:
    config = get_project_config(db, project_id).get("collaboration_config") or {}
    return [dict(item) for item in config.get("ai_providers") or []]


def get_project_ai_provider(db: Session, project_id: str, provider_id: str) -> dict[str, object]:
    for item in list_project_ai_providers(db, project_id):
        if provider_id in {str(item.get("id") or ""), str(item.get("label") or "")}:
            return item
    raise AppError("NOT_FOUND", "AI 鎻愪緵鏂逛笉瀛樺湪", status_code=404)


def create_project_ai_provider(db: Session, project_id: str, payload: CollaborationProviderCreate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "ai_providers")
    data = payload.model_dump(mode="json")
    provider_label = str(data.get("label") or "").strip()
    provider_id = str(data.get("id") or "").strip() or _generate_config_id(
        "provider",
        provider_label,
        {str(item.get("id") or "") for item in items},
    )
    _conflict_if_exists(items, key="id", value=provider_id, section="AI provider")
    _conflict_if_exists(items, key="label", value=provider_label, section="AI provider")
    data["id"] = provider_id
    data["label"] = provider_label
    items.append(data)
    after = dict(before)
    after["ai_providers"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_provider.created",
        actor_type="human",
        actor_id=None,
    )
    return get_project_ai_provider(db, project_id, provider_id)


def update_project_ai_provider(db: Session, project_id: str, provider_id: str, payload: CollaborationProviderUpdate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "ai_providers")
    index = _find_item_index(items, provider_id, section="AI provider")
    current = items[index]
    updated = dict(current)
    updated.update(payload.model_dump(exclude_unset=True))
    updated["id"] = str(current.get("id") or provider_id)
    updated["label"] = str(updated.get("label") or current.get("label") or provider_id).strip()
    _conflict_if_exists(items, key="id", value=str(updated["id"]), section="AI provider", excluding_index=index)
    _conflict_if_exists(items, key="label", value=updated["label"], section="AI provider", excluding_index=index)
    items[index] = updated
    after = dict(before)
    after["ai_providers"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_provider.updated",
    )
    return get_project_ai_provider(db, project_id, provider_id)


def delete_project_ai_provider(db: Session, project_id: str, provider_id: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "ai_providers")
    index = _find_item_index(items, provider_id, section="AI provider")
    removed = items.pop(index)
    after = dict(before)
    after["ai_providers"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_provider.deleted",
    )
    return removed


def list_project_computer_nodes(db: Session, project_id: str) -> list[dict[str, object]]:
    project = get_project_or_404(db, project_id)
    config = get_project_config(db, project_id).get("collaboration_config") or {}
    nodes = [dict(item) for item in config.get("computer_nodes") or []]
    return _enrich_computer_nodes_with_thread_scan(project, nodes)


def get_project_computer_node(db: Session, project_id: str, node_id: str) -> dict[str, object]:
    for item in list_project_computer_nodes(db, project_id):
        if node_id in {str(item.get("id") or ""), str(item.get("label") or "")}:
            return item
    raise AppError("NOT_FOUND", "computer node does not exist", status_code=404)


def create_project_computer_node(db: Session, project_id: str, payload: CollaborationComputerNodeCreate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "computer_nodes")
    data = payload.model_dump(mode="json")
    node_label = str(data.get("label") or "").strip()
    node_id = str(data.get("id") or "").strip() or _generate_config_id(
        "node",
        node_label,
        {str(item.get("id") or "") for item in items},
    )
    _conflict_if_exists(items, key="id", value=node_id, section="鐢佃剳鑺傜偣")
    _conflict_if_exists(items, key="label", value=node_label, section="鐢佃剳鑺傜偣")
    data["id"] = node_id
    data["label"] = node_label
    items.append(data)
    after = dict(before)
    after["computer_nodes"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_node.created",
    )
    return get_project_computer_node(db, project_id, node_id)


def update_project_computer_node(db: Session, project_id: str, node_id: str, payload: CollaborationComputerNodeUpdate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "computer_nodes")
    index = _find_item_index(items, node_id, section="鐢佃剳鑺傜偣")
    current = items[index]
    updated = dict(current)
    updated.update(payload.model_dump(exclude_unset=True))
    updated["id"] = str(current.get("id") or node_id)
    updated["label"] = str(updated.get("label") or current.get("label") or node_id).strip()
    _conflict_if_exists(items, key="id", value=str(updated["id"]), section="鐢佃剳鑺傜偣", excluding_index=index)
    _conflict_if_exists(items, key="label", value=updated["label"], section="鐢佃剳鑺傜偣", excluding_index=index)
    items[index] = updated
    after = dict(before)
    after["computer_nodes"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_node.updated",
    )
    return get_project_computer_node(db, project_id, node_id)


def delete_project_computer_node(db: Session, project_id: str, node_id: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "computer_nodes")
    index = _find_item_index(items, node_id, section="鐢佃剳鑺傜偣")
    removed = items.pop(index)
    after = dict(before)
    after["computer_nodes"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_node.deleted",
    )
    return removed


def list_project_thread_workstations(db: Session, project_id: str) -> list[dict[str, object]]:
    config = get_project_config(db, project_id).get("collaboration_config") or {}
    return [dict(item) for item in config.get("thread_workstations") or []]


def get_project_thread_workstation(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    for item in list_project_thread_workstations(db, project_id):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        extra_data = item.get("extra_data") if isinstance(item.get("extra_data"), dict) else {}
        if workstation_name in {
            str(item.get("id") or ""),
            str(item.get("config_id") or ""),
            str(item.get("name") or ""),
            str(item.get("row_id") or ""),
            str(item.get("source_workstation_id") or ""),
            str(metadata.get("source_workstation_id") or ""),
            str(extra_data.get("source_workstation_id") or ""),
        }:
            return item
    raise AppError("NOT_FOUND", "thread workstation does not exist", status_code=404)


def _workstation_adapter_token_state(workstation: dict[str, object]) -> dict[str, object]:
    metadata = _metadata_dict(workstation.get("metadata"))
    extra_data = _metadata_dict(workstation.get("extra_data"))
    return {
        "token_hash": (
            metadata.get("adapter_token_hash")
            or metadata.get("workstation_token_hash")
            or extra_data.get("adapter_token_hash")
            or extra_data.get("workstation_token_hash")
        ),
        "issued_at": (
            metadata.get("adapter_token_issued_at")
            or metadata.get("workstation_token_issued_at")
            or extra_data.get("adapter_token_issued_at")
            or extra_data.get("workstation_token_issued_at")
        ),
        "last_used_at": (
            metadata.get("adapter_token_last_used_at")
            or metadata.get("workstation_token_last_used_at")
            or extra_data.get("adapter_token_last_used_at")
            or extra_data.get("workstation_token_last_used_at")
        ),
    }


def _clear_workstation_adapter_token_fields(metadata: dict[str, object]) -> dict[str, object]:
    metadata.pop("adapter_token_hash", None)
    metadata.pop("workstation_token_hash", None)
    metadata.pop("adapter_token_issued_at", None)
    metadata.pop("workstation_token_issued_at", None)
    metadata.pop("adapter_token_last_used_at", None)
    metadata.pop("workstation_token_last_used_at", None)
    return metadata


def _update_workstation_adapter_token_row(
    workstation: ProjectThreadWorkstation,
    *,
    token_hash: str | None,
    issued_at: str | None,
) -> None:
    extra_data = _metadata_dict(workstation.extra_data)
    _clear_workstation_adapter_token_fields(extra_data)
    if token_hash:
        extra_data["adapter_token_hash"] = token_hash
        extra_data["adapter_token_issued_at"] = issued_at
        extra_data["adapter_token_last_used_at"] = None
    workstation.extra_data = extra_data or None


def mark_project_workstation_adapter_token_used(
    db: Session,
    project_id: str,
    workstation_name: str,
) -> ProjectThreadWorkstation:
    workstation = _project_workstation(db, project_id, workstation_name)
    extra_data = _metadata_dict(workstation.extra_data)
    token_hash = str(extra_data.get("adapter_token_hash") or extra_data.get("workstation_token_hash") or "").strip()
    if not token_hash:
        return workstation
    now = datetime.now(timezone.utc).isoformat()
    extra_data["adapter_token_last_used_at"] = now
    extra_data.pop("workstation_token_last_used_at", None)
    workstation.extra_data = extra_data or None
    db.add(workstation)
    db.commit()
    db.refresh(workstation)
    return workstation


def _workstation_token_payload(project_id: str, workstation: dict[str, object], token: str | None = None) -> dict[str, object]:
    state = _workstation_adapter_token_state(workstation)
    return {
        "project_id": project_id,
        "workstation_id": str(workstation.get("id") or workstation.get("config_id") or "").strip(),
        "workstation_name": str(workstation.get("name") or workstation.get("workstation_name") or "").strip(),
        "token": token,
        "token_available": bool(state["token_hash"]),
        "issued_at": state["issued_at"],
        "last_used_at": state["last_used_at"],
    }


def _metadata_dict(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_runtime_value(
    metadata: dict[str, object],
    field: str,
    *,
    aliases: tuple[str, ...] = (),
) -> tuple[object | None, str | None]:
    adapter = metadata.get("adapter")
    adapter_data = dict(adapter) if isinstance(adapter, dict) else {}
    for key in (field, *aliases):
        value = adapter_data.get(key)
        if value not in (None, ""):
            return value, f"metadata.adapter.{key}"
    for key in (field, *aliases):
        value = metadata.get(key)
        if value not in (None, ""):
            return value, f"metadata.{key}"
    return None, None


def _resolve_executor_timeout(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return None
    return timeout if timeout > 0 else None


def get_project_workstation_adapter_config(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    workstation = get_project_thread_workstation(db, project_id, workstation_name)
    workstation_metadata = _metadata_dict(workstation.get("metadata"))
    provider_id = str(workstation.get("ai_provider_id") or workstation.get("ai_provider") or "").strip() or None
    provider: dict[str, object] | None = None
    if provider_id:
        try:
            provider = get_project_ai_provider(db, project_id, provider_id)
        except AppError as exc:
            if exc.code != "NOT_FOUND":
                raise
    provider_metadata = _metadata_dict(provider.get("metadata") if isinstance(provider, dict) else None)
    node_id = str(workstation.get("computer_node_id") or workstation.get("computer_node") or "").strip() or None
    computer_node = get_project_computer_node(db, project_id, node_id) if node_id else None

    settings_source: dict[str, str] = {}

    def resolve_field(
        field: str,
        *,
        aliases: tuple[str, ...] = (),
        provider_aliases: tuple[str, ...] | None = None,
    ) -> object | None:
        workstation_value, workstation_source = _metadata_runtime_value(workstation_metadata, field, aliases=aliases)
        if workstation_source:
            settings_source[field] = f"workstation.{workstation_source}"
            return workstation_value
        provider_value, provider_source = _metadata_runtime_value(
            provider_metadata,
            field,
            aliases=provider_aliases if provider_aliases is not None else aliases,
        )
        if provider_source:
            settings_source[field] = f"provider.{provider_source}"
            return provider_value
        return None

    executor_command = resolve_field("executor_command", aliases=("command_template",))
    # Session scanners may report cwd/workspace_root as scan metadata. Do not
    # promote those scan hints into the execution directory unless the user
    # explicitly configured executor_cwd.
    executor_cwd = resolve_field("executor_cwd")
    if not executor_cwd and isinstance(computer_node, dict):
        fallback_cwd = str(computer_node.get("git_root") or computer_node.get("workspace_root") or "").strip()
        if fallback_cwd:
            executor_cwd = fallback_cwd
            settings_source["executor_cwd"] = "computer_node.git_root" if str(computer_node.get("git_root") or "").strip() else "computer_node.workspace_root"
    timeout_value = resolve_field("executor_timeout_seconds", aliases=("timeout_seconds",))
    executor_timeout_seconds = _resolve_executor_timeout(timeout_value)
    if executor_timeout_seconds and "executor_timeout_seconds" not in settings_source and "timeout_seconds" in settings_source:
        settings_source["executor_timeout_seconds"] = settings_source.pop("timeout_seconds")
    model = (
        str(workstation.get("model") or "").strip()
        or str(provider.get("model") or "").strip() if isinstance(provider, dict) else ""
    ) or None

    provider_label = None
    if isinstance(provider, dict):
        provider_label = str(provider.get("label") or provider.get("id") or "").strip() or None
    if not provider_label:
        provider_label = str(workstation.get("ai_provider") or workstation.get("ai_provider_id") or "").strip() or None

    return {
        "project_id": project_id,
        "workstation_id": str(workstation.get("id") or workstation.get("config_id") or workstation_name).strip() or workstation_name,
        "workstation_name": str(workstation.get("name") or workstation_name).strip() or workstation_name,
        "computer_node_id": node_id,
        "provider_id": provider_id,
        "provider_label": provider_label,
        "model": model,
        "executor_command": str(executor_command).strip() if executor_command not in (None, "") else None,
        "executor_cwd": str(executor_cwd).strip() if executor_cwd not in (None, "") else None,
        "executor_timeout_seconds": executor_timeout_seconds,
        "settings_source": settings_source,
    }


def create_project_thread_workstation(db: Session, project_id: str, payload: CollaborationWorkstationCreate) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "thread_workstations")
    data = payload.model_dump(mode="json")
    name = str(data.get("name") or "").strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "宸ヤ綅绾跨▼鍚嶇О涓嶈兘涓虹┖", status_code=422)
    _conflict_if_exists(items, key="name", value=name, section="宸ヤ綅绾跨▼")
    data["name"] = name
    data["id"] = str(data.get("id") or name).strip()
    _conflict_if_exists(items, key="id", value=str(data["id"]), section="瀹搞儰缍呯痪璺ㄢ柤")
    items.append(data)
    after = dict(before)
    after["thread_workstations"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_workstation.created",
    )
    return get_project_thread_workstation(db, project_id, name)


def update_project_thread_workstation(
    db: Session,
    project_id: str,
    workstation_name: str,
    payload: CollaborationWorkstationUpdate,
) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "thread_workstations")
    index = _find_item_index(items, workstation_name, section="宸ヤ綅绾跨▼")
    current = items[index]
    updated = dict(current)
    updated.update(payload.model_dump(exclude_unset=True))
    new_name = str(updated.get("name") or current.get("name") or workstation_name).strip()
    updated["name"] = new_name
    updated["id"] = str(updated.get("id") or current.get("id") or new_name).strip()
    _conflict_if_exists(items, key="id", value=str(updated["id"]), section="宸ヤ綅绾跨▼", excluding_index=index)
    _conflict_if_exists(items, key="name", value=new_name, section="宸ヤ綅绾跨▼", excluding_index=index)
    items[index] = updated
    after = dict(before)
    after["thread_workstations"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_workstation.updated",
    )
    return get_project_thread_workstation(db, project_id, new_name)


def delete_project_thread_workstation(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "thread_workstations")
    index = _find_item_index(items, workstation_name, section="宸ヤ綅绾跨▼")
    removed = items.pop(index)
    after = dict(before)
    after["thread_workstations"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_workstation.deleted",
    )
    return removed


def get_project_workstation_adapter_token_status(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    workstation = get_project_thread_workstation(db, project_id, workstation_name)
    return _workstation_token_payload(project_id, workstation)


def rotate_project_workstation_adapter_token(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    workstation_row = _project_workstation(db, project_id, workstation_name)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "thread_workstations")
    index = _find_item_index(items, workstation_name, section="工位线程")
    current = dict(items[index])
    metadata = _metadata_dict(current.get("metadata"))
    extra_data = _metadata_dict(current.get("extra_data"))
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    _clear_workstation_adapter_token_fields(metadata)
    _clear_workstation_adapter_token_fields(extra_data)
    token_hash = _pairing_token_hash(token)
    metadata["adapter_token_hash"] = token_hash
    metadata["adapter_token_issued_at"] = now
    metadata["adapter_token_last_used_at"] = None
    current["metadata"] = metadata
    current["extra_data"] = extra_data
    items[index] = current
    _update_workstation_adapter_token_row(
        workstation_row,
        token_hash=token_hash,
        issued_at=now,
    )
    db.add(workstation_row)
    after = dict(before)
    after["thread_workstations"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_workstation.adapter_token.rotated",
    )
    workstation = get_project_thread_workstation(db, project_id, workstation_name)
    return _workstation_token_payload(project_id, workstation, token=token)


def revoke_project_workstation_adapter_token(db: Session, project_id: str, workstation_name: str) -> dict[str, object]:
    project = get_project_or_404(db, project_id)
    workstation_row = _project_workstation(db, project_id, workstation_name)
    before = _project_collaboration_config(project)
    items = _project_collaboration_items(project, "thread_workstations")
    index = _find_item_index(items, workstation_name, section="工位线程")
    current = dict(items[index])
    metadata = _metadata_dict(current.get("metadata"))
    extra_data = _metadata_dict(current.get("extra_data"))
    _clear_workstation_adapter_token_fields(metadata)
    _clear_workstation_adapter_token_fields(extra_data)
    current["metadata"] = metadata
    current["extra_data"] = extra_data
    items[index] = current
    _update_workstation_adapter_token_row(
        workstation_row,
        token_hash=None,
        issued_at=None,
    )
    db.add(workstation_row)
    after = dict(before)
    after["thread_workstations"] = items
    _save_project_collaboration_config(
        db,
        project,
        before=before,
        after=after,
        action="project.collaboration_workstation.adapter_token.revoked",
    )
    workstation = get_project_thread_workstation(db, project_id, workstation_name)
    return _workstation_token_payload(project_id, workstation)


def list_users(db: Session):
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


def get_user_or_404(db: Session, user_id: str):
    user = db.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "user does not exist", status_code=404)
    return user


def create_user(db: Session, payload: UserCreate):
    user = User(**payload.model_dump())
    db.add(user)
    db.flush()
    append_audit_log(
        db,
        actor_type="human",
        actor_id=None,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        after={"name": user.name, "email": user.email, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: str, payload: UserUpdate):
    user = get_user_or_404(db, user_id)
    before = {"name": user.name, "email": user.email, "display_name": user.display_name, "is_active": user.is_active}
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    append_audit_log(
        db,
        actor_type="human",
        actor_id=None,
        action="user.updated",
        resource_type="user",
        resource_id=user.id,
        before=before,
        after={"name": user.name, "email": user.email, "display_name": user.display_name, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user


def list_project_invites(db: Session, *, project_id: str | None = None, status: str | None = None):
    stmt = select(ProjectInvite).order_by(ProjectInvite.created_at.desc())
    if project_id:
        stmt = stmt.where(ProjectInvite.project_id == project_id)
    if status:
        stmt = stmt.where(ProjectInvite.status == status)
    return list(db.scalars(stmt))


def get_invite_or_404(db: Session, invite_id: str):
    invite = db.get(ProjectInvite, invite_id)
    if invite is None:
        raise AppError("NOT_FOUND", "invite does not exist", status_code=404)
    return invite


def serialize_project_invite_for_read(invite: ProjectInvite) -> dict[str, object]:
    return {
        "id": invite.id,
        "project_id": invite.project_id,
        "email": invite.email,
        "role": invite.role,
        "token": None,
        "status": invite.status,
        "invited_by_user_id": invite.invited_by_user_id,
        "accepted_by_user_id": invite.accepted_by_user_id,
        "message": invite.message,
        "expires_at": invite.expires_at,
        "accepted_at": invite.accepted_at,
        "created_at": invite.created_at,
        "updated_at": invite.updated_at,
    }


def create_project_invite(db: Session, project_id: str, payload: ProjectInviteCreate):
    project = get_project_or_404(db, project_id)
    invite = ProjectInvite(
        project_id=project.id,
        email=payload.email,
        role=payload.role,
        token=_generate_unique_invite_token(db),
        status="pending",
        invited_by_user_id=payload.invited_by_user_id,
        message=payload.message,
        expires_at=payload.expires_at,
    )
    db.add(invite)
    db.flush()
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="human",
        actor_id=payload.invited_by_user_id,
        action="invite.created",
        resource_type="project_invite",
        resource_id=invite.id,
        after={
            "project_id": project.id,
            "email": invite.email,
            "role": invite.role,
            "status": invite.status,
            "token": invite.token,
        },
    )
    db.commit()
    db.refresh(invite)
    return invite


def update_project_invite(db: Session, invite_id: str, payload: ProjectInviteUpdate):
    invite = get_invite_or_404(db, invite_id)
    before = {
        "status": invite.status,
        "message": invite.message,
        "accepted_by_user_id": invite.accepted_by_user_id,
        "expires_at": invite.expires_at,
    }
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        invite.status = data["status"]
    if "message" in data:
        invite.message = data["message"]
    if "accepted_by_user_id" in data:
        invite.accepted_by_user_id = data["accepted_by_user_id"]
    if "expires_at" in data:
        invite.expires_at = data["expires_at"]
    if invite.status == "accepted" and invite.accepted_at is None:
        invite.accepted_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        project_id=invite.project_id,
        actor_type="human",
        actor_id=invite.accepted_by_user_id,
        action="invite.updated",
        resource_type="project_invite",
        resource_id=invite.id,
        before=before,
        after={
            "status": invite.status,
            "message": invite.message,
            "accepted_by_user_id": invite.accepted_by_user_id,
            "expires_at": invite.expires_at,
        },
    )
    db.commit()
    db.refresh(invite)
    return invite


def accept_invite(db: Session, invite_id: str, payload: ProjectInviteAcceptRequest):
    invite = get_invite_or_404(db, invite_id)
    if invite.status != "pending":
        raise AppError("INVITE_NOT_PENDING", "invite is not pending", status_code=400)

    user = get_user_or_404(db, payload.user_id)
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == invite.project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if member is None:
        member = ProjectMember(project_id=invite.project_id, user_id=user.id, role=invite.role, status="active")
        db.add(member)
        db.flush()
    else:
        member.role = invite.role
        member.status = "active"

    invite.status = "accepted"
    invite.accepted_by_user_id = user.id
    invite.accepted_at = datetime.now(timezone.utc)

    append_audit_log(
        db,
        project_id=invite.project_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id or user.id,
        action="invite.accepted",
        resource_type="project_invite",
        resource_id=invite.id,
        before={"status": "pending"},
        after={"status": "accepted", "user_id": user.id, "member_id": member.id if member.id else None},
    )
    append_audit_log(
        db,
        project_id=invite.project_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id or user.id,
        action="project_member.added",
        resource_type="project_member",
        resource_id=member.id,
        after={"project_id": invite.project_id, "user_id": user.id, "role": member.role, "status": member.status},
    )
    db.commit()
    db.refresh(invite)
    db.refresh(member)
    return {"invite": invite, "member": member, "user": user}


def revoke_invite(db: Session, invite_id: str, *, actor_type: str = "human", actor_id: str | None = None, note: str | None = None):
    invite = get_invite_or_404(db, invite_id)
    before = {"status": invite.status}
    invite.status = "revoked"
    append_audit_log(
        db,
        project_id=invite.project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="invite.revoked",
        resource_type="project_invite",
        resource_id=invite.id,
        before=before,
        after={"status": invite.status, "note": note},
    )
    db.commit()
    db.refresh(invite)
    return invite


def list_project_members(db: Session, project_id: str, *, include_removed: bool = False):
    get_project_or_404(db, project_id)
    stmt = select(ProjectMember).where(ProjectMember.project_id == project_id).order_by(ProjectMember.joined_at.desc())
    if not include_removed:
        stmt = stmt.where(ProjectMember.status != "removed")
    return list(db.scalars(stmt))


def get_project_member_or_404(db: Session, project_id: str, member_id: str):
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise AppError("NOT_FOUND", "project member does not exist", status_code=404)
    return member


def add_project_member(db: Session, project_id: str, payload: ProjectMemberCreate):
    project = get_project_or_404(db, project_id)
    user = get_user_or_404(db, payload.user_id)
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
    )
    before = None
    if member is None:
        member = ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=payload.role,
            status=payload.status,
            is_owner=payload.is_owner,
        )
        db.add(member)
        db.flush()
    else:
        before = {
            "role": member.role,
            "status": member.status,
            "is_owner": member.is_owner,
        }
        member.role = payload.role
        member.status = payload.status
        member.is_owner = payload.is_owner
    append_audit_log(
        db,
        project_id=project.id,
        actor_type="human",
        actor_id=None,
        action="project_member.added",
        resource_type="project_member",
        resource_id=member.id,
        before=before,
        after={"project_id": project.id, "user_id": user.id, "role": member.role, "status": member.status},
    )
    db.commit()
    db.refresh(member)
    return member


def update_project_member(db: Session, project_id: str, member_id: str, payload: ProjectMemberUpdate):
    member = get_project_member_or_404(db, project_id, member_id)
    before = {"role": member.role, "status": member.status, "is_owner": member.is_owner}
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] is not None:
        member.role = data["role"]
    if "is_owner" in data and data["is_owner"] is not None:
        member.is_owner = data["is_owner"]
    if "status" in data and data["status"] is not None:
        member.status = data["status"]
    append_audit_log(
        db,
        project_id=project_id,
        actor_type="human",
        actor_id=None,
        action="project_member.updated",
        resource_type="project_member",
        resource_id=member.id,
        before=before,
        after={"role": member.role, "status": member.status, "is_owner": member.is_owner},
    )
    db.commit()
    db.refresh(member)
    return member


def remove_project_member(db: Session, project_id: str, member_id: str, *, actor_type: str = "human", actor_id: str | None = None):
    member = get_project_member_or_404(db, project_id, member_id)
    before = {"role": member.role, "status": member.status, "is_owner": member.is_owner}
    member.status = "removed"
    member.is_owner = False
    append_audit_log(
        db,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="project_member.removed",
        resource_type="project_member",
        resource_id=member.id,
        before=before,
        after={"role": member.role, "status": member.status, "is_owner": member.is_owner},
    )
    db.commit()
    db.refresh(member)
    return member


def get_collaboration_summary(db: Session):
    users = db.scalar(select(func.count(User.id))) or 0
    pending_invites = db.scalar(select(func.count(ProjectInvite.id)).where(ProjectInvite.status == "pending")) or 0
    members = db.scalar(select(func.count(ProjectMember.id)).where(ProjectMember.status != "removed")) or 0
    return {
        "users": int(users),
        "pending_invites": int(pending_invites),
        "members": int(members),
    }


def _project_task_or_404(db: Session, project_id: str, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise AppError("TASK_NOT_FOUND", "task does not exist or does not belong to this project", status_code=404)
    return task


def _project_runner_node(db: Session, project_id: str, identifier: str) -> ProjectComputerNode:
    stmt = select(ProjectComputerNode).where(
        ProjectComputerNode.project_id == project_id,
        (ProjectComputerNode.id == identifier)
        | (ProjectComputerNode.config_id == identifier)
        | (ProjectComputerNode.label == identifier),
    )
    node = db.scalar(stmt)
    if node is None:
        raise AppError("COMPUTER_NODE_NOT_FOUND", "project computer node does not exist", status_code=404)
    return node


def _pairing_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _computer_node_pairing_state(node: ProjectComputerNode) -> dict[str, object]:
    extra_data = dict(node.extra_data or {})
    return {
        "token_hash": extra_data.get("runner_pairing_token_hash"),
        "issued_at": extra_data.get("runner_pairing_token_issued_at"),
        "last_used_at": extra_data.get("runner_pairing_token_last_used_at"),
    }


def get_project_computer_node_pairing_status(db: Session, project_id: str, node_id: str) -> dict[str, object]:
    node = _project_runner_node(db, project_id, node_id)
    pairing = _computer_node_pairing_state(node)
    return {
        "project_id": project_id,
        "computer_node_id": node.config_id,
        "computer_node_label": node.label,
        "token": None,
        "token_available": bool(pairing["token_hash"]),
        "issued_at": pairing["issued_at"],
        "last_used_at": pairing["last_used_at"],
    }


def rotate_project_computer_node_pairing_token(db: Session, project_id: str, node_id: str) -> dict[str, object]:
    node = _project_runner_node(db, project_id, node_id)
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    extra_data = dict(node.extra_data or {})
    extra_data["runner_pairing_token_hash"] = _pairing_token_hash(token)
    extra_data["runner_pairing_token_issued_at"] = now
    extra_data["runner_pairing_token_last_used_at"] = None
    node.extra_data = extra_data
    db.add(node)
    append_audit_log(
        db,
        project_id=project_id,
        actor_type="human",
        actor_id=None,
        action="project.computer_node.pairing_token.rotated",
        resource_type="computer_node",
        resource_id=node.config_id,
        after={"computer_node_id": node.config_id, "issued_at": now},
    )
    db.commit()
    db.refresh(node)
    return {
        "project_id": project_id,
        "computer_node_id": node.config_id,
        "computer_node_label": node.label,
        "token": token,
        "token_available": True,
        "issued_at": extra_data.get("runner_pairing_token_issued_at"),
        "last_used_at": extra_data.get("runner_pairing_token_last_used_at"),
    }


def revoke_project_computer_node_pairing_token(db: Session, project_id: str, node_id: str) -> dict[str, object]:
    node = _project_runner_node(db, project_id, node_id)
    extra_data = dict(node.extra_data or {})
    extra_data.pop("runner_pairing_token_hash", None)
    extra_data.pop("runner_pairing_token_issued_at", None)
    extra_data.pop("runner_pairing_token_last_used_at", None)
    node.extra_data = extra_data
    db.add(node)
    append_audit_log(
        db,
        project_id=project_id,
        actor_type="human",
        actor_id=None,
        action="project.computer_node.pairing_token.revoked",
        resource_type="computer_node",
        resource_id=node.config_id,
        after={"computer_node_id": node.config_id, "token_available": False},
    )
    db.commit()
    db.refresh(node)
    return {
        "project_id": project_id,
        "computer_node_id": node.config_id,
        "computer_node_label": node.label,
        "token": None,
        "token_available": False,
        "issued_at": None,
        "last_used_at": None,
    }


def consume_runner_pairing_token(
    db: Session,
    token: str,
    *,
    computer_node_id: str | None = None,
) -> ProjectComputerNode | None:
    token_hash = _pairing_token_hash(token)
    nodes = list(db.scalars(select(ProjectComputerNode).where(ProjectComputerNode.extra_data.is_not(None))))
    for node in nodes:
        if computer_node_id and str(node.config_id) != str(computer_node_id):
            continue
        extra_data = dict(node.extra_data or {})
        if extra_data.get("runner_pairing_token_hash") != token_hash:
            continue
        extra_data["runner_pairing_token_last_used_at"] = datetime.now(timezone.utc).isoformat()
        node.extra_data = extra_data
        db.add(node)
        db.flush()
        return node
    return None


def _project_workstation(db: Session, project_id: str, identifier: str) -> ProjectThreadWorkstation:
    cleaned = str(identifier or "").strip()
    stmt = select(ProjectThreadWorkstation).where(
        ProjectThreadWorkstation.project_id == project_id,
        (ProjectThreadWorkstation.id == cleaned)
        | (ProjectThreadWorkstation.config_id == cleaned)
        | (ProjectThreadWorkstation.name == cleaned)
        | (ProjectThreadWorkstation.agent_id == cleaned),
    )
    workstation = db.scalar(stmt)
    if workstation is None and cleaned:
        for item in db.scalars(
            select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == project_id)
        ):
            extra_data = dict(item.extra_data or {})
            if cleaned in {
                str(extra_data.get("source_workstation_id") or ""),
                str(extra_data.get("source_thread_id") or ""),
                str(extra_data.get("bound_thread_id") or ""),
            }:
                workstation = item
                break
    if workstation is None:
        raise AppError("WORKSTATION_NOT_FOUND", "project workstation does not exist", status_code=404)
    return workstation


def _workstation_identity_values(workstation: ProjectThreadWorkstation, requested_id: str | None = None) -> set[str]:
    extra_data = dict(workstation.extra_data or {})
    values = {
        str(requested_id or ""),
        str(workstation.id or ""),
        str(workstation.config_id or ""),
        str(workstation.name or ""),
        str(workstation.agent_id or ""),
        str(extra_data.get("source_workstation_id") or ""),
        str(extra_data.get("source_thread_id") or ""),
        str(extra_data.get("bound_thread_id") or ""),
    }
    return {value.strip() for value in values if value and value.strip()}


def _resolve_runner_command_target(
    db: Session,
    project_id: str,
    *,
    runner_id: str | None = None,
    computer_node_id: str | None = None,
    workstation_id: str | None = None,
) -> Runner:
    runner: Runner | None = None
    if runner_id:
        stmt = select(ProjectComputerNode).where(
            ProjectComputerNode.project_id == project_id,
            ProjectComputerNode.runner_id == runner_id,
        )
        node = db.scalar(stmt)
        if node is None:
            raise AppError("RUNNER_NOT_BOUND", "杩欎釜 Runner 杩樻病鏈夌粦瀹氬埌褰撳墠椤圭洰", status_code=409)
        runner = db.get(Runner, runner_id)
    elif computer_node_id:
        node = _project_runner_node(db, project_id, computer_node_id)
        if not node.runner_id:
            raise AppError("RUNNER_NOT_BOUND", "target computer is not bound to a Runner", status_code=409)
        runner = db.get(Runner, node.runner_id)
    elif workstation_id:
        workstation = _project_workstation(db, project_id, workstation_id)
        if not workstation.computer_node_id:
            raise AppError("RUNNER_NOT_BOUND", "target workstation is not attached to a computer node", status_code=409)
        node = _project_runner_node(db, project_id, workstation.computer_node_id)
        if not node.runner_id:
            raise AppError("RUNNER_NOT_BOUND", "鐩爣宸ヤ綅鎵€鍦ㄧ數鑴戣繕娌℃湁缁戝畾 Runner", status_code=409)
        runner = db.get(Runner, node.runner_id)
    if runner is None:
        raise AppError("RUNNER_NOT_FOUND", "target Runner does not exist", status_code=404)
    return runner


def _get_runner_command_or_404(db: Session, runner_id: str, message_id: str) -> CollaborationMessage:
    message = db.get(CollaborationMessage, message_id)
    if message is None or message.recipient_type != "runner" or message.recipient_id != runner_id:
        raise AppError("MESSAGE_NOT_FOUND", "Runner 鏀朵欢绠遍噷娌℃湁杩欐潯娑堟伅", status_code=404)
    if message.message_type != "runner_command":
        raise AppError("MESSAGE_NOT_COMMAND", "杩欐潯娑堟伅涓嶆槸 Runner 鍛戒护", status_code=409)
    return message


def _runner_command_dispatch_id(message: CollaborationMessage) -> str | None:
    match = re.search(r"^Dispatch ID:\s*([A-Za-z0-9-]+)\s*$", str(message.body or ""), re.MULTILINE)
    if match is None:
        return None
    return match.group(1)


def _project_dispatch_or_404(db: Session, project_id: str, dispatch_id: str) -> TaskDispatch:
    dispatch = db.get(TaskDispatch, dispatch_id)
    if dispatch is None or dispatch.project_id != project_id:
        raise AppError("TASK_DISPATCH_NOT_FOUND", "task dispatch does not exist or does not belong to this project", status_code=404)
    return dispatch


def _normalize_runner_command_body(body: str, dispatch_id: str | None = None) -> str:
    lines = []
    for line in str(body or "").splitlines():
        if re.match(r"^Dispatch ID:\s*([A-Za-z0-9-]+)\s*$", line.strip()):
            continue
        lines.append(line)
    cleaned_body = "\n".join(lines).strip()
    if not dispatch_id:
        return cleaned_body
    dispatch_line = f"Dispatch ID: {dispatch_id}"
    if not cleaned_body:
        return dispatch_line
    return f"{cleaned_body}\n\n{dispatch_line}"


def list_messages(
    db: Session,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    approval_id: str | None = None,
    handoff_id: str | None = None,
    requirement_id: str | None = None,
    agent_id: str | None = None,
    message_type: str | None = None,
    recipient_type: str | None = None,
    recipient_id: str | None = None,
    sender_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    stmt = select(CollaborationMessage).order_by(CollaborationMessage.created_at.desc())
    if project_id:
        stmt = stmt.where(CollaborationMessage.project_id == project_id)
    if task_id:
        stmt = stmt.where(CollaborationMessage.task_id == task_id)
    if approval_id:
        stmt = stmt.where(CollaborationMessage.approval_id == approval_id)
    if handoff_id:
        stmt = stmt.where(CollaborationMessage.handoff_id == handoff_id)
    if requirement_id:
        stmt = stmt.where(CollaborationMessage.requirement_id == requirement_id)
    if agent_id:
        stmt = stmt.where(CollaborationMessage.agent_id == agent_id)
    if message_type:
        stmt = stmt.where(CollaborationMessage.message_type == message_type)
    if recipient_type:
        stmt = stmt.where(CollaborationMessage.recipient_type == recipient_type)
    if recipient_id:
        stmt = stmt.where(CollaborationMessage.recipient_id == recipient_id)
    if status:
        stmt = stmt.where(CollaborationMessage.status == status)
    if sender_id:
        stmt = stmt.where(CollaborationMessage.sender_id == sender_id)
    return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))


def get_collaboration_message_or_404(db: Session, message_id: str) -> CollaborationMessage:
    message = db.get(CollaborationMessage, message_id)
    if message is None:
        raise AppError("MESSAGE_NOT_FOUND", "collaboration message does not exist", status_code=404)
    return message


def update_collaboration_message(
    db: Session,
    message_id: str,
    payload: CollaborationMessageUpdate,
    *,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> CollaborationMessage:
    message = get_collaboration_message_or_404(db, message_id)
    before = {
        "title": message.title,
        "body": message.body,
        "status": message.status,
    }
    changes: dict[str, object | None] = {}
    if payload.title is not None:
        message.title = payload.title
        changes["title"] = message.title
    if payload.body is not None:
        message.body = payload.body
        changes["body"] = message.body
    if payload.status is not None:
        next_status = str(payload.status or "").strip()
        if not next_status:
            raise AppError("BAD_REQUEST", "collaboration message status cannot be empty", status_code=400)
        message.status = next_status
        changes["status"] = message.status
    if not changes:
        return message
    db.add(message)
    db.flush()
    append_audit_log(
        db,
        project_id=message.project_id,
        task_id=message.task_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="collaboration.message.updated",
        resource_type="collaboration_message",
        resource_id=message.id,
        before=before,
        after=changes,
    )
    db.commit()
    db.refresh(message)
    return message


def list_runner_inbox_messages(db: Session, runner_id: str, *, status: str | None = None, limit: int = 50):
    stmt = (
        select(CollaborationMessage)
        .where(
            CollaborationMessage.recipient_type == "runner",
            CollaborationMessage.recipient_id == runner_id,
            CollaborationMessage.message_type == "runner_command",
        )
        .order_by(CollaborationMessage.created_at.desc())
    )
    if status and status != "all":
        stmt = stmt.where(CollaborationMessage.status == status)
    elif not status:
        stmt = stmt.where(CollaborationMessage.status.in_(["pending", "acked"]))
    return list(db.scalars(stmt.limit(max(1, min(limit, 200)))))


def list_workstation_inbox_messages(
    db: Session,
    project_id: str,
    workstation_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
):
    workstation = _project_workstation(db, project_id, workstation_id)
    candidate_ids = _workstation_identity_values(workstation, workstation_id)
    stmt = (
        select(CollaborationMessage)
        .where(
            CollaborationMessage.project_id == project_id,
            CollaborationMessage.recipient_type.in_(["workstation", "thread_workstation"]),
            CollaborationMessage.recipient_id.in_(candidate_ids),
            CollaborationMessage.message_type.in_(["agent_command", "requirement_dispatch"]),
        )
        .order_by(CollaborationMessage.created_at.desc())
    )
    if status and status != "all":
        stmt = stmt.where(CollaborationMessage.status == status)
    elif not status:
        stmt = stmt.where(CollaborationMessage.status.in_(["queued", "pending", "acked", "in_progress"]))
    return list(db.scalars(stmt.limit(max(1, min(limit, 200)))))


def _get_workstation_command_or_404(
    db: Session,
    project_id: str,
    workstation_id: str,
    message_id: str,
) -> tuple[ProjectThreadWorkstation, CollaborationMessage]:
    workstation = _project_workstation(db, project_id, workstation_id)
    candidate_ids = _workstation_identity_values(workstation, workstation_id)
    message = db.get(CollaborationMessage, message_id)
    # 兼容两种 recipient_type：
    # - "workstation"        → 老式 agent_command（recipient_id 通常是 config_id）
    # - "thread_workstation" → D1 修复后自主合作派的 requirement_dispatch（recipient_id = seat.row_id）
    if (
        message is None
        or message.project_id != project_id
        or message.recipient_type not in {"workstation", "thread_workstation"}
        or str(message.recipient_id or "") not in candidate_ids
    ):
        raise AppError("MESSAGE_NOT_FOUND", "workstation inbox does not contain this message", status_code=404)
    if message.message_type not in {"agent_command", "requirement_dispatch"}:
        raise AppError("MESSAGE_NOT_COMMAND", "this message is not a workstation command", status_code=409)
    return workstation, message


def _workstation_reply_payload(
    workstation: ProjectThreadWorkstation,
    *,
    note: str,
    status: str,
    title: str | None = None,
):
    from app.modules.requirements.schemas import RequirementFinalReplyRequest

    return RequirementFinalReplyRequest(
        sender_type="agent",
        sender_id=workstation.config_id,
        recipient_type="workstation",
        recipient_id=workstation.config_id,
        message=note,
        status=status,
        title=title,
    )


def ack_workstation_command(
    db: Session,
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: WorkstationInboxAckCreate,
):
    workstation, message = _get_workstation_command_or_404(db, project_id, workstation_id, message_id)
    # 队列原子化：只允许 queued/pending → acked，被并发抢占或已收尾时返回 409，避免两个 watcher 双跑
    if message.status not in {"queued", "pending"}:
        raise AppError("MESSAGE_ALREADY_CLAIMED", f"命令当前 status={message.status}，已被其他 watcher 接走或已收尾", status_code=409)
    before_status = message.status
    rowcount = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message.id,
        CollaborationMessage.status.in_(["queued", "pending"]),
    ).update({"status": "acked"}, synchronize_session=False)
    if rowcount == 0:
        db.rollback()
        raise AppError("MESSAGE_ALREADY_CLAIMED", "命令已被其他 watcher 接走", status_code=409)
    db.refresh(message)
    note = payload.note or "Agent acknowledged the command and is preparing to execute it."
    append_audit_log(
        db,
        project_id=message.project_id,
        task_id=message.task_id,
        actor_type="agent",
        actor_id=workstation.config_id,
        action="collaboration.workstation_command.acked",
        resource_type="collaboration_message",
        resource_id=message.id,
        before={"status": before_status},
        after={"status": message.status},
    )
    receipt: CollaborationMessage | None = None
    if message.requirement_id:
        from app.modules.requirements.service import add_requirement_progress_ack

        result = add_requirement_progress_ack(
            db,
            message.requirement_id,
            _workstation_reply_payload(workstation, note=note, status="in_progress", title=message.title),
            dedupe_key=f"workstation_ack:{message.id}",
        )
        receipt = result["message"]
        db.refresh(message)
        return {"command": message, "receipt": receipt}

    receipt = CollaborationMessage(
        project_id=message.project_id,
        task_id=message.task_id,
        approval_id=message.approval_id,
        handoff_id=message.handoff_id,
        requirement_id=message.requirement_id,
        dispatch_id=message.dispatch_id,
        agent_id=workstation.config_id,
        title=message.title or "Agent acknowledged command",
        body=note,
        message_type="agent_ack",
        sender_type="agent",
        sender_id=workstation.config_id,
        recipient_type=message.sender_type if message.sender_type else "project",
        recipient_id=message.sender_id or message.project_id,
        status="delivered",
    )
    db.add(receipt)
    db.commit()
    db.refresh(message)
    db.refresh(receipt)
    return {"command": message, "receipt": receipt}


def complete_workstation_command(
    db: Session,
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: WorkstationInboxCompleteCreate,
):
    workstation, message = _get_workstation_command_or_404(db, project_id, workstation_id, message_id)
    if message.status not in {"queued", "pending", "acked", "in_progress"}:
        raise AppError("MESSAGE_NOT_PENDING", "workstation command is already closed", status_code=409)
    before_status = message.status
    # 队列原子化：终态只允许从 open(queued/pending/acked/in_progress) 变更，被并发收尾时只有第一个 rowcount=1
    rowcount = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message.id,
        CollaborationMessage.status.in_(["queued", "pending", "acked", "in_progress"]),
    ).update({"status": payload.result_status}, synchronize_session=False)
    if rowcount == 0:
        db.rollback()
        raise AppError("MESSAGE_ALREADY_CLOSED", "命令已被其他线程收尾", status_code=409)
    db.refresh(message)
    note = payload.note or (
        "Agent completed the command and returned a final result."
        if payload.result_status == "completed"
        else "Agent reported a failure while executing the command."
    )
    append_audit_log(
        db,
        project_id=message.project_id,
        task_id=message.task_id,
        actor_type="agent",
        actor_id=workstation.config_id,
        action="collaboration.workstation_command.completed",
        resource_type="collaboration_message",
        resource_id=message.id,
        before={"status": before_status},
        after={"status": message.status},
    )
    receipt: CollaborationMessage | None = None
    if message.requirement_id and payload.result_status == "completed":
        from app.modules.requirements.service import add_requirement_final_reply

        result = add_requirement_final_reply(
            db,
            message.requirement_id,
            _workstation_reply_payload(workstation, note=note, status="done", title=message.title),
            dedupe_key=f"workstation_final:{message.id}",
        )
        receipt = result["message"]
        db.refresh(message)
        return {"command": message, "receipt": receipt}

    receipt = CollaborationMessage(
        project_id=message.project_id,
        task_id=message.task_id,
        approval_id=message.approval_id,
        handoff_id=message.handoff_id,
        requirement_id=message.requirement_id,
        dispatch_id=message.dispatch_id,
        agent_id=workstation.config_id,
        title=message.title or "Agent execution result",
        body=note,
        message_type="agent_result",
        sender_type="agent",
        sender_id=workstation.config_id,
        recipient_type=message.sender_type if message.sender_type else "project",
        recipient_id=message.sender_id or message.project_id,
        status=payload.result_status,
    )
    db.add(receipt)
    db.commit()
    db.refresh(message)
    db.refresh(receipt)
    return {"command": message, "receipt": receipt}


def create_message(
    db: Session,
    payload: CollaborationMessageCreate,
    *,
    dispatch_id: str | None = None,
    commit: bool = True,
):
    if not any(
        [
            payload.project_id,
            payload.task_id,
            payload.approval_id,
            payload.handoff_id,
            payload.requirement_id,
            payload.agent_id,
        ]
    ):
        raise AppError("BAD_REQUEST", "collaboration message requires a project, task, approval, handoff, requirement, or workstation scope", status_code=400)

    message = CollaborationMessage(**payload.model_dump(), dispatch_id=str(dispatch_id or "").strip() or None)
    db.add(message)
    db.flush()
    append_audit_log(
        db,
        project_id=payload.project_id,
        task_id=payload.task_id,
        actor_type=payload.sender_type,
        actor_id=payload.sender_id,
        action="collaboration.message.created",
        resource_type="collaboration_message",
        resource_id=message.id,
        after={
            "message_type": payload.message_type,
            "dispatch_id": message.dispatch_id,
            "recipient_type": payload.recipient_type,
            "recipient_id": payload.recipient_id,
            "status": payload.status,
            "title": payload.title,
        },
    )
    if commit:
        db.commit()
        db.refresh(message)
    return message


def create_runner_command(
    db: Session,
    project_id: str,
    *,
    sender_id: str,
    payload: RunnerRelayCommandCreate,
):
    get_project_or_404(db, project_id)
    dispatch: TaskDispatch | None = None
    task_id = str(payload.task_id or "").strip() or None
    body = payload.body
    agent_id: str | None = None

    if payload.dispatch_id:
        dispatch = _project_dispatch_or_404(db, project_id, payload.dispatch_id)
        if task_id and task_id != dispatch.task_id:
            raise AppError("TASK_DISPATCH_TASK_MISMATCH", "娲惧崟鍜屼换鍔′笉鍖归厤", status_code=409)
        task_id = dispatch.task_id
        if not dispatch.runner_id:
            raise AppError("RUNNER_NOT_BOUND", "target dispatch is not bound to a Runner", status_code=409)
        runner = db.get(Runner, dispatch.runner_id)
        if runner is None:
            raise AppError("RUNNER_NOT_FOUND", "target Runner does not exist", status_code=404)
        agent_id = dispatch.workstation_id
        body = _normalize_runner_command_body(payload.body, dispatch.id)
    else:
        if task_id:
            _project_task_or_404(db, project_id, task_id)
        runner = _resolve_runner_command_target(
            db,
            project_id,
            runner_id=payload.runner_id,
            computer_node_id=payload.computer_node_id,
            workstation_id=payload.workstation_id,
        )

    message = create_message(
        db,
        CollaborationMessageCreate(
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            title=payload.title,
            body=body,
            message_type="runner_command",
            sender_type="human",
            sender_id=sender_id,
            recipient_type="runner",
            recipient_id=runner.id,
            status="pending",
        ),
        dispatch_id=dispatch.id if dispatch is not None else None,
        commit=dispatch is None,
    )
    if dispatch is not None:
        task_repo.create_task_event(
            db,
            task_id or dispatch.task_id,
            "runner_command_enqueued",
            f"runner command queued for {runner.id}",
            {
                "dispatch_id": dispatch.id,
                "runner_id": runner.id,
                "workstation_id": dispatch.workstation_id,
                "message_id": message.id,
            },
            actor_type="human",
            actor_id=sender_id or None,
            commit=False,
        )
        db.commit()
        db.refresh(message)
    return message


def ack_runner_command(db: Session, runner_id: str, message_id: str, payload: RunnerRelayAckCreate):
    message = _get_runner_command_or_404(db, runner_id, message_id)
    if message.status not in {"pending", "acked"}:
        raise AppError("MESSAGE_NOT_PENDING", "runner command is already closed", status_code=409)
    before_status = message.status
    message.status = "acked"
    append_audit_log(
        db,
        project_id=message.project_id,
        task_id=message.task_id,
        actor_type="runner",
        actor_id=runner_id,
        action="collaboration.runner_command.acked",
        resource_type="collaboration_message",
        resource_id=message.id,
        before={"status": before_status},
        after={"status": message.status},
    )
    ack_message: CollaborationMessage | None = None
    if message.sender_type == "human" and message.sender_id:
        ack_message = CollaborationMessage(
            project_id=message.project_id,
            task_id=message.task_id,
            dispatch_id=message.dispatch_id,
            title=message.title or "Runner acknowledged command",
            body=payload.note or "Runner acknowledged the command and is preparing to execute it.",
            message_type="runner_ack",
            sender_type="runner",
            sender_id=runner_id,
            recipient_type="human",
            recipient_id=message.sender_id,
            status="delivered",
        )
        db.add(ack_message)
        db.flush()
    dispatch = sync_task_dispatch_status(
        db,
        task_id=message.task_id,
        runner_id=runner_id,
        status="acked",
        note=payload.note,
        relay_message_id=message.id,
        actor_type="runner",
        actor_id=runner_id,
    )
    dispatch_id = dispatch.id if dispatch is not None else _runner_command_dispatch_id(message)
    if message.task_id:
        claim_task_for_runner(
            db,
            message.task_id,
            runner_id,
            message=payload.note or f"runner acknowledged command: {message.id}",
            data={"relay_message_id": message.id, "dispatch_id": dispatch_id},
            commit=False,
        )
        from app.modules.requirements.service import sync_task_execution_to_requirements

        sync_task_execution_to_requirements(
            db,
            task_id=message.task_id,
            project_id=message.project_id,
            workstation_id=dispatch.workstation_id if dispatch is not None else None,
            agent_id=dispatch.agent_id if dispatch is not None else None,
            reply_status="in_progress",
            message=payload.note or "Runner acknowledged the task and started execution.",
            actor_id=runner_id,
        )
    db.commit()
    db.refresh(message)
    if ack_message is not None:
        db.refresh(ack_message)
    return {"command": message, "receipt": ack_message}


def complete_runner_command(db: Session, runner_id: str, message_id: str, payload: RunnerRelayCompleteCreate):
    message = _get_runner_command_or_404(db, runner_id, message_id)
    if message.status not in {"pending", "acked"}:
        raise AppError("MESSAGE_NOT_PENDING", "runner command is already closed", status_code=409)
    before_status = message.status
    message.status = payload.result_status
    append_audit_log(
        db,
        project_id=message.project_id,
        task_id=message.task_id,
        actor_type="runner",
        actor_id=runner_id,
        action="collaboration.runner_command.completed",
        resource_type="collaboration_message",
        resource_id=message.id,
        before={"status": before_status},
        after={"status": message.status},
    )
    result_message: CollaborationMessage | None = None
    if message.sender_type == "human" and message.sender_id:
        result_message = CollaborationMessage(
            project_id=message.project_id,
            task_id=message.task_id,
            dispatch_id=message.dispatch_id,
            title=message.title or "Runner execution result",
            body=payload.note or ("Runner completed the command." if payload.result_status == "completed" else "Runner reported a failure while executing the command."),
            message_type="runner_result",
            sender_type="runner",
            sender_id=runner_id,
            recipient_type="human",
            recipient_id=message.sender_id,
            status=payload.result_status,
        )
        db.add(result_message)
        db.flush()
    dispatch = sync_task_dispatch_status(
        db,
        task_id=message.task_id,
        runner_id=runner_id,
        status="completed" if payload.result_status == "completed" else "failed",
        note=payload.note,
        relay_message_id=message.id,
        actor_type="runner",
        actor_id=runner_id,
    )
    dispatch_id = dispatch.id if dispatch is not None else _runner_command_dispatch_id(message)
    if message.task_id:
        claim_task_for_runner(
            db,
            message.task_id,
            runner_id,
            message=f"runner completed command: {message.id}",
            data={"relay_message_id": message.id, "dispatch_id": dispatch_id},
            commit=False,
        )
        record_task_result(
            db,
            message.task_id,
            {
                "runner_command_id": message.id,
                "dispatch_id": dispatch_id,
                "result_status": payload.result_status,
                "note": payload.note,
            },
            runner_id=runner_id,
            status="reviewing" if payload.result_status == "completed" else "failed",
            message=payload.note or ("runner completed command" if payload.result_status == "completed" else "runner reported failure"),
            data={"relay_message_id": message.id, "dispatch_id": dispatch_id},
            commit=False,
        )
        from app.modules.requirements.service import sync_task_execution_to_requirements

        sync_task_execution_to_requirements(
            db,
            task_id=message.task_id,
            project_id=message.project_id,
            workstation_id=dispatch.workstation_id if dispatch is not None else None,
            agent_id=dispatch.agent_id if dispatch is not None else None,
            reply_status="done" if payload.result_status == "completed" else "in_progress",
            message=payload.note
            or (
                "Runner completed the task and returned the final result."
                if payload.result_status == "completed"
                else "Runner reported a failure and the task still needs follow-up."
            ),
            actor_id=runner_id,
        )
    db.commit()
    db.refresh(message)
    if result_message is not None:
        db.refresh(result_message)
    return {"command": message, "receipt": result_message}
