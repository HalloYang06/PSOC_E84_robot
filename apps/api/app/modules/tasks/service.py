from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.common.audit import append_audit_log
from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.audit_log import AuditLog
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.task import Task
from app.db.models.task_dispatch import TaskDispatch
from app.db.models.task_event import TaskEvent

from . import repo
from .schemas import TaskActionRequest, TaskCreate, TaskDispatchCreate, TaskTransitionCreate, TaskUpdate


ALLOWED_TASK_STATUSES = {
    "draft",
    "ready",
    "running",
    "reviewing",
    "blocked",
    "needs_changes",
    "done",
    "failed",
    "cancelled",
}

TASK_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"ready", "blocked", "cancelled"},
    "ready": {"running", "blocked", "cancelled"},
    "running": {"reviewing", "blocked", "failed", "done"},
    "reviewing": {"done", "needs_changes", "blocked", "failed"},
    "needs_changes": {"ready", "running", "blocked", "cancelled"},
    "blocked": {"ready", "running", "cancelled"},
    "done": set(),
    "failed": {"ready", "cancelled"},
    "cancelled": set(),
}


def _artifact_path_is_project_relative(path: str) -> bool:
    cleaned = str(path or "").strip().strip('"').strip("'")
    if not cleaned:
        return False
    normalized = cleaned.replace("\\", "/")
    lowered = normalized.lower()
    if "/artifacts/" in lowered:
        normalized = normalized[lowered.index("/artifacts/") + 1 :]
        lowered = normalized.lower()
    if not lowered.startswith("artifacts/"):
        return False
    if "\x00" in normalized or ".." in Path(normalized).parts:
        return False
    return True


def _task_snapshot(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "module": task.module,
        "priority": task.priority,
        "status": task.status,
        "due_at": task.due_at.isoformat() if hasattr(task.due_at, "isoformat") else task.due_at,
        "branch": task.branch,
        "related_issue": task.related_issue,
        "assignee_agent_id": task.assignee_agent_id,
        "reviewers": list(task.reviewers or []),
        "acceptance_criteria": list(task.acceptance_criteria or []),
        "latest_dispatch": serialize_task_dispatch(get_latest_task_dispatch(task)),
        "created_at": task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else task.created_at,
        "updated_at": task.updated_at.isoformat() if hasattr(task.updated_at, "isoformat") else task.updated_at,
    }


def serialize_task_dispatch(dispatch: TaskDispatch | None) -> dict[str, object] | None:
    if dispatch is None:
        return None
    return {
        "id": dispatch.id,
        "task_id": dispatch.task_id,
        "project_id": dispatch.project_id,
        "workstation_id": dispatch.workstation_id,
        "workstation_name": dispatch.workstation_name,
        "agent_id": dispatch.agent_id,
        "computer_node_id": dispatch.computer_node_id,
        "ai_provider_id": dispatch.ai_provider_id,
        "runner_id": dispatch.runner_id,
        "status": dispatch.status,
        "notes": dispatch.notes,
        "dispatched_by_user_id": dispatch.dispatched_by_user_id,
        "created_at": dispatch.created_at.isoformat() if hasattr(dispatch.created_at, "isoformat") else dispatch.created_at,
        "updated_at": dispatch.updated_at.isoformat() if hasattr(dispatch.updated_at, "isoformat") else dispatch.updated_at,
    }


def get_latest_task_dispatch(task: Task) -> TaskDispatch | None:
    dispatches = list(getattr(task, "dispatches", []) or [])
    if not dispatches:
        return None
    dispatches.sort(key=lambda item: item.created_at or 0, reverse=True)
    return dispatches[0]


def _build_runner_command_title(task: Task) -> str:
    return f"Task dispatch: {task.title}"


def _build_runner_command_body(task: Task, dispatch: TaskDispatch) -> str:
    lines = [
        f"Task: {task.title}",
        f"Dispatch ID: {dispatch.id}",
        f"Workstation: {dispatch.workstation_name or dispatch.workstation_id}",
        f"Dispatch status: {dispatch.status}",
    ]
    if task.module:
        lines.append(f"Module: {task.module}")
    if task.branch:
        lines.append(f"Branch: {task.branch}")
    if task.description:
        lines.append(f"Context: {task.description}")
    if dispatch.notes:
        lines.append(f"Dispatch notes: {dispatch.notes}")
    return "\n".join(lines)


def _append_dispatch_note(existing: str | None, status: str, note: str | None) -> str | None:
    cleaned_note = str(note or "").strip()
    if not cleaned_note:
        return existing

    cleaned_existing = str(existing or "").strip()
    update_line = f"[{status}] {cleaned_note}"
    if not cleaned_existing:
        return update_line
    if update_line in cleaned_existing:
        return cleaned_existing
    return f"{cleaned_existing}\n{update_line}"


def _enqueue_workstation_command_for_dispatch(
    db: Session,
    task: Task,
    dispatch: TaskDispatch,
    *,
    dispatched_by_user_id: str | None,
) -> CollaborationMessage:
    message = CollaborationMessage(
        project_id=task.project_id,
        task_id=task.id,
        agent_id=dispatch.workstation_id,
        dispatch_id=dispatch.id,
        message_type="agent_command",
        title=_build_runner_command_title(task),
        body=_build_runner_command_body(task, dispatch),
        sender_type="human",
        sender_id=dispatched_by_user_id,
        recipient_type="thread_workstation",
        recipient_id=dispatch.workstation_id,
        status="queued",
    )
    db.add(message)
    db.flush()

    repo.create_task_event(
        db,
        task.id,
        "workstation_command_enqueued",
        f"workstation command queued for {dispatch.workstation_id}",
        {
            "dispatch_id": dispatch.id,
            "workstation_id": dispatch.workstation_id,
            "message_id": message.id,
        },
        actor_type="human",
        actor_id=dispatched_by_user_id,
        commit=False,
    )
    append_audit_log(
        db,
        project_id=task.project_id,
        task_id=task.id,
        actor_type="human",
        actor_id=dispatched_by_user_id,
        action="task.dispatch_workstation_command",
        resource_type="collaboration_message",
        resource_id=message.id,
        after={
            "message_type": message.message_type,
            "recipient_type": message.recipient_type,
            "recipient_id": message.recipient_id,
            "task_id": task.id,
            "dispatch_id": dispatch.id,
            "status": message.status,
        },
    )
    return message


def _enqueue_runner_command_for_dispatch(
    db: Session,
    task: Task,
    dispatch: TaskDispatch,
    *,
    dispatched_by_user_id: str | None,
) -> CollaborationMessage | None:
    if not dispatch.runner_id:
        return _enqueue_workstation_command_for_dispatch(
            db,
            task,
            dispatch,
            dispatched_by_user_id=dispatched_by_user_id,
        )

    message = CollaborationMessage(
        project_id=task.project_id,
        task_id=task.id,
        agent_id=dispatch.workstation_id,
        dispatch_id=dispatch.id,
        message_type="runner_command",
        title=_build_runner_command_title(task),
        body=_build_runner_command_body(task, dispatch),
        sender_type="human",
        sender_id=dispatched_by_user_id,
        recipient_type="runner",
        recipient_id=dispatch.runner_id,
        status="pending",
    )
    db.add(message)
    db.flush()

    repo.create_task_event(
        db,
        task.id,
        "runner_command_enqueued",
        f"runner command queued for {dispatch.runner_id}",
        {
            "dispatch_id": dispatch.id,
            "runner_id": dispatch.runner_id,
            "workstation_id": dispatch.workstation_id,
            "message_id": message.id,
        },
        actor_type="human",
        actor_id=dispatched_by_user_id,
        commit=False,
    )
    append_audit_log(
        db,
        project_id=task.project_id,
        task_id=task.id,
        actor_type="human",
        actor_id=dispatched_by_user_id,
        action="task.dispatch_runner_command",
        resource_type="collaboration_message",
        resource_id=message.id,
        after={
            "message_type": message.message_type,
            "recipient_type": message.recipient_type,
            "recipient_id": message.recipient_id,
            "task_id": task.id,
            "dispatch_id": dispatch.id,
            "status": message.status,
        },
    )
    return message


def _resolve_dispatch_from_relay_message(
    db: Session,
    *,
    relay_message_id: str | None,
    task_id: str | None,
    runner_id: str | None,
) -> tuple[TaskDispatch | None, bool]:
    cleaned_relay_message_id = str(relay_message_id or "").strip()
    cleaned_task_id = str(task_id or "").strip()
    cleaned_runner_id = str(runner_id or "").strip()
    if not cleaned_relay_message_id or not cleaned_task_id:
        return None, False

    matched_event = False
    events = db.scalars(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == cleaned_task_id,
            TaskEvent.event_type == "runner_command_enqueued",
        )
        .order_by(TaskEvent.created_at.desc())
    )
    for event in events:
        data = dict(event.data or {})
        if str(data.get("message_id") or "").strip() != cleaned_relay_message_id:
            continue
        matched_event = True
        dispatch_id = str(data.get("dispatch_id") or "").strip()
        if not dispatch_id:
            break
        dispatch = db.get(TaskDispatch, dispatch_id)
        if dispatch is None:
            break
        if cleaned_runner_id and dispatch.runner_id and dispatch.runner_id != cleaned_runner_id:
            break
        return dispatch, True
    return None, matched_event


def sync_task_dispatch_status(
    db: Session,
    *,
    dispatch_id: str | None = None,
    task_id: str | None,
    runner_id: str | None,
    status: str,
    note: str | None = None,
    relay_message_id: str | None = None,
    actor_type: str = "runner",
    actor_id: str | None = None,
) -> TaskDispatch | None:
    cleaned_dispatch_id = str(dispatch_id or "").strip()
    cleaned_task_id = str(task_id or "").strip()
    cleaned_runner_id = str(runner_id or "").strip()
    matched_relay_event = False
    if cleaned_dispatch_id:
        dispatch = db.get(TaskDispatch, cleaned_dispatch_id)
    else:
        dispatch, matched_relay_event = _resolve_dispatch_from_relay_message(
            db,
            relay_message_id=relay_message_id,
            task_id=cleaned_task_id,
            runner_id=cleaned_runner_id,
        )
        if dispatch is None:
            if matched_relay_event or not cleaned_task_id or not cleaned_runner_id:
                return None
            dispatch = db.scalar(
                select(TaskDispatch)
                .where(TaskDispatch.task_id == cleaned_task_id, TaskDispatch.runner_id == cleaned_runner_id)
                .order_by(TaskDispatch.created_at.desc())
                .limit(1)
            )
    if dispatch is None:
        return None
    if cleaned_runner_id and dispatch.runner_id and dispatch.runner_id != cleaned_runner_id:
        return None

    before = serialize_task_dispatch(dispatch)
    dispatch.status = status
    dispatch.notes = _append_dispatch_note(dispatch.notes, status, note)
    db.add(dispatch)

    repo.create_task_event(
        db,
        cleaned_task_id or dispatch.task_id,
        "task_dispatch_status_synced",
        f"task dispatch status synced to {status}",
        {
            "dispatch_id": dispatch.id,
            "runner_id": cleaned_runner_id or dispatch.runner_id,
            "workstation_id": dispatch.workstation_id,
            "status": status,
            "relay_message_id": relay_message_id,
        },
        actor_type=actor_type,
        actor_id=actor_id,
        commit=False,
    )
    append_audit_log(
        db,
        project_id=dispatch.project_id,
        task_id=dispatch.task_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="task.dispatch_status_sync",
        resource_type="task_dispatch",
        resource_id=dispatch.id,
        before=before,
        after=serialize_task_dispatch(dispatch),
    )
    return dispatch


def _validate_task_status(status: str) -> None:
    if status not in ALLOWED_TASK_STATUSES:
        raise AppError("INVALID_TASK_STATUS", "任务状态不合法", status_code=400)


def _validate_transition(current_status: str, next_status: str) -> None:
    _validate_task_status(next_status)
    if current_status == next_status:
        return
    allowed = TASK_STATUS_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise AppError(
            "INVALID_TASK_STATUS_TRANSITION",
            f"任务状态不能从 {current_status} 直接切换到 {next_status}",
            status_code=409,
        )


def _latest_runner_claim(db: Session, task_id: str) -> str | None:
    stmt = (
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.event_type == "runner_picked")
        .order_by(TaskEvent.created_at.desc())
        .limit(1)
    )
    event = db.scalar(stmt)
    if event is None:
        return None
    return event.actor_id or (event.data or {}).get("runner_id")


def _ensure_task_claimed_by_runner(db: Session, task_id: str, runner_id: str) -> None:
    current_runner = _latest_runner_claim(db, task_id)
    if current_runner is None:
        raise AppError("TASK_NOT_CLAIMED", "任务还没有被任何执行节点领取", status_code=409)
    if current_runner != runner_id:
        raise AppError("TASK_CLAIMED_BY_OTHER_RUNNER", "该任务已经被其他执行节点领取", status_code=409)


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


def _ensure_high_risk_gate_open(db: Session, task_id: str, next_status: str) -> None:
    if next_status not in {"ready", "running", "reviewing", "done"}:
        return
    pending = _pending_high_risk_approvals(db, task_id)
    if not pending:
        return
    first = pending[0]
    raise AppError(
        "HIGH_RISK_APPROVAL_REQUIRED",
        f"任务仍有未完成的高风险审批，需先处理 {first.level} 闸门：{first.action}",
        status_code=409,
        details={
            "task_id": task_id,
            "approval_id": first.id,
            "approval_level": first.level,
            "approval_action": first.action,
            "approval_status": first.status,
            "blocked_next_status": next_status,
        },
    )


def get_task_gate_state(db: Session, task_id: str) -> dict[str, object]:
    task = get_task_or_404(db, task_id)
    pending = _pending_high_risk_approvals(db, task.id)
    first = pending[0] if pending else None
    blocked = first is not None
    return {
        "task_id": task.id,
        "status": task.status,
        "blocked": blocked,
        "pending_high_risk_count": len(pending),
        "blocked_next_statuses": ["ready", "running", "reviewing", "done"] if blocked else [],
        "first_blocking_approval": None
        if first is None
        else {
            "id": first.id,
            "task_id": first.task_id,
            "project_id": first.project_id,
            "level": first.level,
            "action": first.action,
            "status": first.status,
            "notes": first.notes,
            "approver_user_id": first.approver_user_id,
            "approved_at": first.approved_at,
        },
        "pending_high_risk_approvals": [
            {
                "id": item.id,
                "task_id": item.task_id,
                "project_id": item.project_id,
                "level": item.level,
                "action": item.action,
                "status": item.status,
                "notes": item.notes,
                "approver_user_id": item.approver_user_id,
                "approved_at": item.approved_at,
            }
            for item in pending
        ],
    }


def _task_artifact_refs_from_metadata(metadata: object | None) -> list[dict[str, str]]:
    if not isinstance(metadata, dict):
        return []
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    project_id = str(metadata.get("project_id") or "").strip() or None
    workstation_id = str(
        metadata.get("authoritative_seat_ref")
        or metadata.get("authoritative_seat_id")
        or metadata.get("canonical_workstation_id")
        or ""
    ).strip() or None
    for key in ("evidence_artifacts", "artifact_refs"):
        entries = metadata.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = _normalize_task_artifact_path(
                entry.get("path") or entry.get("uri"),
                project_id=project_id,
                workstation_id=workstation_id,
            )
            if not path or path in seen or not _artifact_path_is_project_relative(path):
                continue
            seen.add(path)
            refs.append({"label": str(entry.get("label") or "证据").strip() or "证据", "path": path})
    for key, label in (("stdout_path", "标准输出"), ("stderr_path", "错误输出")):
        path = _normalize_task_artifact_path(
            metadata.get(key),
            project_id=project_id,
            workstation_id=workstation_id,
        )
        if not path or path in seen:
            continue
        if "artifacts" not in path.replace("\\", "/").lower():
            continue
        seen.add(path)
        refs.append({"label": label, "path": path})
    return refs


def _task_artifact_preview_context(
    *,
    task_id: str | None,
    path: str | None,
    source_message_id: str | None = None,
    dispatch_id: str | None = None,
    workstation_id: str | None = None,
    sender_id: str | None = None,
    authoritative_seat_ref: str | None = None,
    authoritative_seat_id: str | None = None,
) -> dict[str, str] | None:
    cleaned_task_id = str(task_id or "").strip()
    cleaned_path = str(path or "").strip()
    if not cleaned_task_id or not cleaned_path:
        return None
    cleaned_source_message_id = str(source_message_id or "").strip() or None
    cleaned_dispatch_id = str(dispatch_id or "").strip() or None
    cleaned_workstation_id = (
        str(workstation_id or "").strip()
        or str(authoritative_seat_ref or "").strip()
        or str(authoritative_seat_id or "").strip()
        or str(sender_id or "").strip()
        or None
    )
    return {
        "task_id": cleaned_task_id,
        "path": cleaned_path,
        "source_message_id": cleaned_source_message_id,
        "dispatch_id": cleaned_dispatch_id,
        "workstation_id": cleaned_workstation_id,
    }


def _normalize_task_artifact_path(
    path: object | None,
    *,
    project_id: str | None = None,
    workstation_id: str | None = None,
) -> str | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/")
    marker = "artifacts/workstation-inbox"
    lowered = normalized.lower()
    idx = lowered.find(marker)
    if idx < 0:
        return raw
    tail = normalized[idx + len(marker):].lstrip("/")
    parts = [part for part in PurePosixPath(tail).parts if part not in {"", "."}]
    project = str(project_id or "").strip()
    workstation = str(workstation_id or "").strip()
    while parts and project and parts[0].lower() == project.lower():
        parts.pop(0)
    while parts and workstation and parts[0].lower() == workstation.lower():
        parts.pop(0)
    while len(parts) >= 2 and project and workstation and parts[0].lower() == "proj_ai_collab" and parts[1].lower() == workstation.lower():
        parts = parts[2:]
    rebuilt: list[str] = ["artifacts", "workstation-inbox"]
    if project:
        rebuilt.append(project)
    if workstation:
        rebuilt.append(workstation)
    rebuilt.extend(parts)
    return str(PurePosixPath(*rebuilt))


def _task_payload_json(metadata: object | None) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    payload = metadata.get("payload_json") or metadata.get("payloadJson")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _task_authority_fields(
    message: CollaborationMessage,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    source = dict(metadata or {}) if isinstance(metadata, dict) else {}
    authoritative_seat_id = str(
        source.get("authoritative_seat_id")
        or source.get("authoritative_sender_seat_id")
        or message.sender_id
        or ""
    ).strip() or None
    authoritative_seat_ref = str(
        source.get("authoritative_seat_ref")
        or source.get("canonical_workstation_id")
        or authoritative_seat_id
        or ""
    ).strip() or None
    authoritative_target_seat_id = str(
        source.get("authoritative_target_seat_id")
        or message.recipient_id
        or ""
    ).strip() or None
    return {
        "authoritative_seat_id": authoritative_seat_id,
        "authoritative_seat_ref": authoritative_seat_ref,
        "authoritative_target_seat_id": authoritative_target_seat_id,
        "historical_alias_non_authoritative": bool(source.get("historical_alias_non_authoritative")),
    }


def _task_message_exception_state(message: CollaborationMessage) -> dict[str, object]:
    metadata = dict(message.extra_data or {}) if isinstance(message.extra_data, dict) else {}
    payload = _task_payload_json(metadata) or {}
    body = str(message.body or "")
    lowered_status = str(message.status or "").lower()
    lowered_body = body.lower()
    taxonomy = metadata.get("blocked_taxonomy")
    if not isinstance(taxonomy, dict):
        taxonomy = payload.get("blocked_taxonomy")
    taxonomy = dict(taxonomy or {}) if isinstance(taxonomy, dict) else {}
    desktop_closeout_waiting = bool(
        taxonomy.get("desktop_closeout_waiting")
        or metadata.get("desktop_closeout_waiting")
        or metadata.get("needs_manual_closeout")
        or metadata.get("timeout_repair")
        or payload.get("desktop_closeout_waiting")
    )
    timed_out = bool(
        taxonomy.get("timed_out")
        or metadata.get("timeout_repair")
        or metadata.get("timed_out")
        or payload.get("timed_out")
        or "超时" in body
        or "timeout" in lowered_body
    )
    auto_closed = bool(
        taxonomy.get("auto_closed")
        or metadata.get("auto_closed")
        or payload.get("auto_closed")
    )
    failed = lowered_status in {"failed", "error", "rejected"} or (
        lowered_status == "blocked" and not desktop_closeout_waiting
    )
    retryable = bool(taxonomy.get("retryable") or metadata.get("retryable") or payload.get("retryable"))
    desktop_sync_retry_requested = bool(
        taxonomy.get("desktop_sync_retry_requested")
        or metadata.get("desktop_sync_retry_requested")
        or payload.get("desktop_sync_retry_requested")
    )
    desktop_sync_retry_count = taxonomy.get("desktop_sync_retry_count")
    if desktop_sync_retry_count is None:
        desktop_sync_retry_count = metadata.get("desktop_sync_retry_count")
    if desktop_sync_retry_count is None:
        desktop_sync_retry_count = payload.get("desktop_sync_retry_count")
    try:
        desktop_sync_retry_count = int(desktop_sync_retry_count or 0)
    except (TypeError, ValueError):
        desktop_sync_retry_count = 0
    log_available = bool(
        taxonomy.get("log_available")
        or _task_artifact_refs_from_metadata(metadata)
    )
    split_suggested = bool(
        taxonomy.get("split_suggested")
        or metadata.get("split_suggested")
        or payload.get("split_suggested")
        or "拆分" in body
        or "split" in lowered_body
    )
    exception_kind = str(
        taxonomy.get("exception_kind")
        or metadata.get("exception_kind")
        or payload.get("exception_kind")
        or ("timeout" if timed_out else "failed" if failed else "")
    ).strip() or None
    blocked_reason_code = str(
        taxonomy.get("blocked_reason_code")
        or metadata.get("blocked_reason_code")
        or payload.get("blocked_reason_code")
        or ("desktop_final_sync_lag" if metadata.get("timeout_repair") else "")
        or ""
    ).strip() or None
    blocked_reason_label = str(
        taxonomy.get("blocked_reason_label")
        or metadata.get("blocked_reason_label")
        or payload.get("blocked_reason_label")
        or ("桌面 final 同步滞后，等待催办或手动收口" if blocked_reason_code == "desktop_final_sync_lag" else "")
        or ""
    ).strip() or None
    platform_defect = bool(
        taxonomy.get("platform_defect")
        or metadata.get("platform_defect")
        or payload.get("platform_defect")
        or metadata.get("timeout_repair")
    )
    nudge_required = bool(
        taxonomy.get("nudge_required")
        or metadata.get("nudge_required")
        or payload.get("nudge_required")
        or metadata.get("timeout_repair")
    )
    wait_extension_available = bool(
        taxonomy.get("wait_extension_available")
        or metadata.get("wait_extension_available")
        or payload.get("wait_extension_available")
        or metadata.get("timeout_repair")
    )
    manual_close_required = bool(
        taxonomy.get("manual_close_required")
        or metadata.get("manual_close_required")
        or payload.get("manual_close_required")
        or metadata.get("timeout_repair")
    )
    evidence_complete = taxonomy.get("evidence_complete")
    if evidence_complete is None:
        evidence_complete = metadata.get("evidence_complete")
    if evidence_complete is None:
        evidence_complete = payload.get("evidence_complete")
    if metadata.get("timeout_repair"):
        evidence_complete = False
    tags: list[str] = []
    if failed:
        tags.append("failed")
    if timed_out:
        tags.append("timed_out")
    if auto_closed:
        tags.append("auto_closed")
    if retryable:
        tags.append("retryable")
    if desktop_sync_retry_requested:
        tags.append("desktop_sync_retry_requested")
    if log_available:
        tags.append("log_available")
    if split_suggested:
        tags.append("split_suggested")
    if blocked_reason_code:
        tags.append(f"reason:{blocked_reason_code}")
    if platform_defect:
        tags.append("platform_defect")
    if nudge_required:
        tags.append("nudge_required")
    if wait_extension_available:
        tags.append("wait_extension_available")
    if manual_close_required:
        tags.append("manual_close_required")
    if desktop_closeout_waiting:
        tags.append("desktop_closeout_waiting")
    if metadata.get("timeout_repair"):
        failed = False
        auto_closed = False
    return {
        "failed": failed,
        "timed_out": timed_out,
        "auto_closed": auto_closed,
        "retryable": retryable,
        "log_available": log_available,
        "split_suggested": split_suggested,
        "exception_kind": exception_kind,
        "blocked_reason_code": blocked_reason_code,
        "blocked_reason_label": blocked_reason_label,
        "evidence_complete": bool(evidence_complete) if evidence_complete is not None else None,
        "platform_defect": platform_defect,
        "nudge_required": nudge_required,
        "wait_extension_available": wait_extension_available,
        "manual_close_required": manual_close_required,
        "desktop_closeout_waiting": desktop_closeout_waiting,
        "desktop_sync_retry_requested": desktop_sync_retry_requested,
        "desktop_sync_retry_count": desktop_sync_retry_count,
        "tags": tags,
    }


def _task_professional_exception_summary(
    messages: list[CollaborationMessage],
    dispatches: list[TaskDispatch],
) -> dict[str, object]:
    failed_messages = [item for item in messages if str(item.status or "").lower() in {"failed", "error", "blocked"}]
    failed_dispatches = [item for item in dispatches if str(item.status or "").lower() in {"failed", "error", "blocked"}]
    timed_out = 0
    auto_closed = 0
    retryable = 0
    log_available = 0
    split_suggested = 0
    platform_defect = 0
    stale_sync_attention = 0
    evidence_incomplete = 0
    kinds: dict[str, int] = {}

    for item in failed_messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        body = str(item.body or "")
        payload = _task_payload_json(metadata) or {}
        state = _task_message_exception_state(item)
        kind = str(
            metadata.get("exception_kind")
            or payload.get("exception_kind")
            or ("timeout" if metadata.get("timeout_repair") else "failed_message")
        )
        kinds[kind] = kinds.get(kind, 0) + 1
        if metadata.get("timeout_repair") or "timeout" in kind.lower() or "超时" in body or "超过" in body:
            timed_out += 1
        if state.get("auto_closed"):
            auto_closed += 1
        if metadata.get("retryable") is not False:
            retryable += 1
        if _task_artifact_refs_from_metadata(metadata):
            log_available += 1
        if metadata.get("split_suggested") or "拆分" in body or "split" in body.lower():
            split_suggested += 1
        if state.get("platform_defect"):
            platform_defect += 1
        if state.get("nudge_required") or state.get("wait_extension_available") or state.get("manual_close_required"):
            stale_sync_attention += 1
        if state.get("evidence_complete") is False:
            evidence_incomplete += 1

    for item in failed_dispatches:
        kind = "failed_dispatch"
        kinds[kind] = kinds.get(kind, 0) + 1
        if str(item.notes or "").strip():
            retryable += 1

    total_failed = len(failed_messages) + len(failed_dispatches)
    primary_kind = sorted(kinds.items(), key=lambda pair: pair[1], reverse=True)[0][0] if kinds else None
    return {
        "status": "incomplete" if evidence_incomplete > 0 else "complete",
        "failed": total_failed,
        "timed_out": timed_out,
        "auto_closed": auto_closed,
        "retryable": retryable,
        "log_available": log_available,
        "split_suggested": split_suggested,
        "platform_defect": platform_defect,
        "stale_sync_requires_attention": stale_sync_attention,
        "exception_kind": primary_kind,
        "actionable": total_failed > 0,
    }


def _task_receipt_links(messages: list[CollaborationMessage]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in messages:
        if item.message_type not in {"agent_result", "runner_result", "requirement_final_reply", "agent_ack", "runner_ack", "agent_progress"}:
            continue
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        authority = _task_authority_fields(item, metadata)
        rows.append(
            {
                "message_id": item.id,
                "message_type": item.message_type,
                "status": item.status,
                "source_message_id": str(metadata.get("source_message_id") or "").strip() or None,
                "dispatch_id": item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId"),
                **authority,
                "created_at": item.created_at,
            }
        )
    return rows


def _first_task_payload_value(messages: list[CollaborationMessage], keys: tuple[str, ...]) -> object | None:
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        payload = _task_payload_json(metadata) or {}
        for key in keys:
            value = metadata.get(key)
            if value not in (None, ""):
                return value
            value = payload.get(key)
            if value not in (None, ""):
                return value
    return None


def _first_task_manifest_value(messages: list[CollaborationMessage], keys: tuple[str, ...]) -> object | None:
    containers = ("dataset_manifest", "datasetManifest", "manifest", "manifest_summary", "manifestSummary")
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        payload = _task_payload_json(metadata) or {}
        sources: list[dict[str, object]] = [metadata, payload]
        for source in (metadata, payload):
            for container in containers:
                value = source.get(container)
                if isinstance(value, dict):
                    sources.append(value)
        for source in sources:
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
    return None


def _task_int_or_none(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _task_bool(value: object | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "ready", "completed", "available"}:
            return True
        if lowered in {"0", "false", "no", "waiting", "missing", "unavailable"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _task_training_metrics_summary(messages: list[CollaborationMessage]) -> dict[str, object]:
    value = _first_task_payload_value(messages, ("metrics_summary", "metricsSummary", "eval_metrics", "evalMetrics", "metrics"))
    return dict(value) if isinstance(value, dict) else {}


def _task_dataset_manifest_artifact_path(messages: list[CollaborationMessage]) -> str | None:
    direct = _first_task_manifest_value(
        messages,
        (
            "dataset_manifest_artifact_path",
            "datasetManifestArtifactPath",
            "manifest_artifact_path",
            "manifestArtifactPath",
            "artifact_path",
            "artifactPath",
            "path",
        ),
    )
    if direct:
        return str(direct)
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        for ref in _task_artifact_refs_from_metadata(metadata):
            haystack = f"{ref.get('label', '')} {ref.get('path', '')}".lower()
            if "manifest" in haystack:
                return str(ref.get("path") or "")
    return None


def _task_manifest_version(messages: list[CollaborationMessage]) -> str | None:
    value = _first_task_manifest_value(messages, ("manifest_version", "manifestVersion", "version", "dataset_version", "datasetVersion"))
    return str(value) if value not in (None, "") else None


def _task_manifest_sample_count(messages: list[CollaborationMessage]) -> int | None:
    value = _first_task_manifest_value(messages, ("sample_count", "sampleCount", "samples", "total_samples", "totalSamples"))
    return _task_int_or_none(value)


def _task_manifest_low_confidence_count(messages: list[CollaborationMessage]) -> int | None:
    value = _first_task_manifest_value(
        messages,
        ("low_confidence_count", "lowConfidenceCount", "low_confidence_samples", "lowConfidenceSamples"),
    )
    return _task_int_or_none(value)


def _task_manifest_qa_status(messages: list[CollaborationMessage]) -> str:
    value = _first_task_manifest_value(messages, ("qa_status", "qaStatus", "quality_status", "qualityStatus"))
    return str(value) if value not in (None, "") else "waiting"


def _task_manifest_export_status(messages: list[CollaborationMessage]) -> str:
    value = _first_task_manifest_value(messages, ("export_status", "exportStatus", "dataset_export_status", "datasetExportStatus"))
    return str(value) if value not in (None, "") else "waiting"


def _task_replay_ready(messages: list[CollaborationMessage]) -> bool:
    direct = _first_task_manifest_value(messages, ("replay_ready", "replayReady", "simulation_replay_ready", "simulationReplayReady"))
    parsed = _task_bool(direct)
    if parsed is not None:
        return parsed
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        for ref in _task_artifact_refs_from_metadata(metadata):
            haystack = f"{ref.get('label', '')} {ref.get('path', '')}".lower()
            if any(token in haystack for token in ("replay", "simulation", "trace", "回放", "仿真")):
                return True
    return False


def _task_experiment_run_status(messages: list[CollaborationMessage], dispatches: list[TaskDispatch]) -> str:
    direct = _first_task_payload_value(messages, ("experiment_run_status", "experimentRunStatus", "run_status", "runStatus"))
    if direct:
        return str(direct)
    statuses = {str(item.status or "").lower() for item in messages} | {str(item.status or "").lower() for item in dispatches}
    if statuses & {"failed", "error", "blocked", "rejected"}:
        return "blocked"
    if statuses & {"running", "active", "in_progress", "queued", "accepted", "acked"}:
        return "active"
    if statuses & {"completed", "done", "delivered", "resolved"}:
        return "ready"
    return "waiting"


def _task_training_receipt_status(messages: list[CollaborationMessage]) -> str:
    direct = _first_task_payload_value(messages, ("training_receipt_status", "trainingReceiptStatus"))
    if direct:
        return str(direct)
    training_messages = []
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        payload = _task_payload_json(metadata) or {}
        haystack = f"{item.title or ''} {item.body or ''} {json.dumps(payload, ensure_ascii=False)}".lower()
        if any(token in haystack for token in ("training", "train", "训练", "模型评估", "eval")):
            training_messages.append(item)
    if any(str(item.status or "").lower() in {"failed", "error", "blocked", "rejected"} for item in training_messages):
        return "blocked"
    if any(str(item.status or "").lower() in {"pending_review", "review", "waiting_review"} for item in training_messages):
        return "needs_review"
    if any(str(item.status or "").lower() in {"completed", "done", "delivered", "resolved"} for item in training_messages):
        return "completed"
    return "waiting"


def _task_release_gate_status(gate: dict[str, object], pending_closeout_count: int, messages: list[CollaborationMessage]) -> str:
    direct = _first_task_payload_value(messages, ("release_gate_status", "releaseGateStatus", "gate_status", "gateStatus"))
    if direct:
        return str(direct)
    if bool(gate.get("blocked")) or int(gate.get("pending_high_risk_count") or 0) > 0:
        return "review_required"
    if pending_closeout_count > 0:
        return "pending_closeout"
    if _task_training_receipt_status(messages) == "blocked":
        return "pending_closeout"
    return "can_continue"


def _task_timeline(
    messages: list[CollaborationMessage],
    dispatches: list[TaskDispatch],
    approvals: list[Approval],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for approval in approvals:
        rows.append(
            {
                "kind": "approval",
                "status": approval.status,
                "label": f"{approval.level or '审批'} {approval.action or ''}".strip(),
                "source_id": approval.id,
                "source_type": "approval",
                "dispatch_id": None,
                "created_at": approval.created_at,
            }
        )
    for dispatch in dispatches:
        rows.append(
            {
                "kind": "dispatch",
                "status": dispatch.status,
                "label": dispatch.workstation_name or dispatch.workstation_id,
                "source_id": dispatch.id,
                "source_type": "task_dispatch",
                "dispatch_id": dispatch.id,
                "created_at": dispatch.created_at,
            }
        )
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        label = item.title or item.message_type
        rows.append(
            {
                "kind": "message",
                "status": item.status,
                "label": label,
                "source_id": item.id,
                "source_type": item.message_type,
                "dispatch_id": item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId"),
                "created_at": item.created_at,
            }
        )
    rows.sort(key=lambda item: str(item.get("created_at") or ""))
    return rows


def _task_capability_summary(
    db: Session,
    task: Task,
    dispatches: list[TaskDispatch],
) -> list[dict[str, object]]:
    from app.modules.collaboration.service import get_project_workstation_adapter_config

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for dispatch in dispatches:
        key = str(dispatch.id or "")
        if not key or key in seen:
            continue
        seen.add(key)
        capability_labels: list[str] = []
        if dispatch.runner_id:
            runner = db.scalar(select(ProjectComputerNode).where(
                ProjectComputerNode.project_id == task.project_id,
                ProjectComputerNode.runner_id == dispatch.runner_id,
            ))
            if runner is not None:
                extra = dict(runner.extra_data or {}) if isinstance(runner.extra_data, dict) else {}
                capability_labels.extend([str(item).strip() for item in extra.get("capabilities") or [] if str(item).strip()])
        if not capability_labels and dispatch.runner_id:
            from app.db.models.runner import Runner

            runner_row = db.get(Runner, dispatch.runner_id)
            if runner_row is not None:
                capability_labels.extend([str(item).strip() for item in list(runner_row.capabilities or []) if str(item).strip()])
        runner_payload: dict[str, object] = {}
        if dispatch.runner_id:
            from app.db.models.runner import Runner

            runner_row = db.get(Runner, dispatch.runner_id)
            if runner_row is not None:
                runner_payload = {
                    "id": runner_row.id,
                    "name": runner_row.name,
                    "status": runner_row.status,
                    "last_seen_at": runner_row.last_heartbeat_at.isoformat() if getattr(runner_row, "last_heartbeat_at", None) else None,
                    "hardware_access": bool(getattr(runner_row, "allow_hardware_access", False)),
                }
        adapter = {}
        try:
            adapter = get_project_workstation_adapter_config(db, task.project_id, dispatch.workstation_id)
        except Exception:
            adapter = {}
        rows.append(
            {
                "workstation_id": dispatch.workstation_id,
                "workstation_name": dispatch.workstation_name,
                "runner_id": dispatch.runner_id,
                "provider_id": dispatch.ai_provider_id,
                "capability_labels": capability_labels,
                "adapter": {
                    "delivery_mode": adapter.get("delivery_mode"),
                    "desktop_visible": adapter.get("desktop_visible"),
                    "desktop_thread_url": adapter.get("desktop_thread_url"),
                    "delivery_warning": adapter.get("delivery_warning"),
                } if isinstance(adapter, dict) else {},
                "runner": runner_payload,
            }
        )
    return rows


def get_task_professional_view(db: Session, task_id: str) -> dict[str, object]:
    task = get_task_or_404(db, task_id)
    gate = get_task_gate_state(db, task_id)
    dispatches = list_task_dispatches(db, task_id)
    approvals = list(
        db.scalars(
            select(Approval)
            .where(Approval.task_id == task_id)
            .order_by(Approval.created_at.asc())
        )
    )

    messages = list(
        db.scalars(
            select(CollaborationMessage)
            .where(CollaborationMessage.task_id == task_id)
            .order_by(CollaborationMessage.created_at.desc())
            .limit(50)
        )
    )
    audit_logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.task_id == task_id)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    )

    serialized_messages: list[dict[str, object]] = []
    artifact_count = 0
    latest_result_status: str | None = None
    latest_result_message_id: str | None = None
    evidence_chain_status = "complete"
    stale_sync_requires_attention = False
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        artifact_refs = _task_artifact_refs_from_metadata(metadata)
        exception_state = _task_message_exception_state(item)
        authority = _task_authority_fields(item, metadata)
        if exception_state.get("evidence_complete") is False:
            evidence_chain_status = "incomplete"
        if exception_state.get("nudge_required") or exception_state.get("wait_extension_available") or exception_state.get("manual_close_required"):
            stale_sync_requires_attention = True
        artifact_count += len(artifact_refs)
        if latest_result_status is None and item.message_type in {"agent_result", "runner_result", "requirement_final_reply"}:
            latest_result_status = item.status
            latest_result_message_id = item.id
        serialized_messages.append(
            {
                "id": item.id,
                "message_type": item.message_type,
                "status": item.status,
                "title": item.title,
                "body": item.body,
                "sender_type": item.sender_type,
                "sender_id": item.sender_id,
                "recipient_type": item.recipient_type,
                "recipient_id": item.recipient_id,
                "dispatch_id": item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId"),
                **authority,
                "metadata": metadata,
                "payload_json": _task_payload_json(metadata),
                "artifact_refs": [
                    {
                        **entry,
                        "source_message_id": item.id,
                        "source_message_type": item.message_type,
                        "task_id": item.task_id,
                        "dispatch_id": item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId"),
                        "authoritative_seat_id": authority["authoritative_seat_id"],
                        "authoritative_seat_ref": authority["authoritative_seat_ref"],
                        "authoritative_target_seat_id": authority["authoritative_target_seat_id"],
                        "historical_alias_non_authoritative": authority["historical_alias_non_authoritative"],
                        "preview_context": _task_artifact_preview_context(
                            task_id=item.task_id,
                            path=entry["path"],
                            source_message_id=item.id,
                            dispatch_id=item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId"),
                            sender_id=item.sender_id,
                            authoritative_seat_id=authority["authoritative_seat_id"],
                            authoritative_seat_ref=authority["authoritative_seat_ref"],
                        ),
                    }
                    for entry in artifact_refs
                ],
                "exception_state": exception_state,
                "created_at": item.created_at,
            }
        )

    serialized_audit = [
        {
            "id": item.id,
            "action": item.action,
            "actor_type": item.actor_type,
            "actor_id": item.actor_id,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "success": item.success,
            "created_at": item.created_at,
        }
        for item in audit_logs
    ]
    receipts = _task_receipt_links(messages)
    capability_summary = _task_capability_summary(db, task, dispatches)
    receipt_by_source: dict[str, str] = {}
    for receipt in receipts:
        source_message_id = str(receipt.get("source_message_id") or "").strip()
        if source_message_id and source_message_id not in receipt_by_source:
            receipt_by_source[source_message_id] = str(receipt.get("message_id") or "").strip() or None
    serialized_approvals = [
        {
            "approval_id": item.id,
            "level": item.level,
            "action": item.action,
            "status": item.status,
            "task_id": item.task_id,
            "receipt_message_id": None,
        }
        for item in approvals
    ]
    pending_closeout_count = sum(
        1
        for item in serialized_messages
        if bool(((item.get("exception_state") or {}).get("desktop_closeout_waiting")))
    )
    auto_retry_active = any(
        bool(((item.get("exception_state") or {}).get("desktop_sync_retry_requested")))
        for item in serialized_messages
    )
    runner_ids = {
        str(item.get("runner_id") or "").strip()
        for item in capability_summary
        if str(item.get("runner_id") or "").strip()
    }
    experiment_run_status = _task_experiment_run_status(messages, dispatches)
    metrics_summary = _task_training_metrics_summary(messages)
    dataset_manifest_artifact_path = _task_dataset_manifest_artifact_path(messages)
    manifest_version = _task_manifest_version(messages)
    sample_count = _task_manifest_sample_count(messages)
    low_confidence_count = _task_manifest_low_confidence_count(messages)
    qa_status = _task_manifest_qa_status(messages)
    export_status = _task_manifest_export_status(messages)
    training_receipt_status = _task_training_receipt_status(messages)
    release_gate_status = _task_release_gate_status(gate, pending_closeout_count, messages)
    replay_ready = _task_replay_ready(messages)

    return {
        "task": _task_snapshot(task),
        "gate": gate,
        "summary": {
            "task_id": task.id,
            "project_id": task.project_id,
            "task_status": task.status,
            "dispatch_count": len(dispatches),
            "message_count": len(serialized_messages),
            "audit_count": len(serialized_audit),
            "artifact_count": artifact_count,
            "latest_result_status": latest_result_status,
            "latest_result_message_id": latest_result_message_id,
            "pending_approval_count": gate["pending_high_risk_count"],
            "blocked": bool(gate["blocked"]),
            "exception_summary": _task_professional_exception_summary(messages, dispatches),
            "evidence_chain_status": evidence_chain_status,
            "stale_sync_requires_attention": stale_sync_requires_attention,
            "receipt_count": len(receipts),
            "capability_count": len(capability_summary),
            "runner_count": len(runner_ids),
            "auto_retry_active": auto_retry_active,
            "pending_closeout_count": pending_closeout_count,
            "experiment_run_status": experiment_run_status,
            "metrics_summary": metrics_summary,
            "dataset_manifest_artifact_path": dataset_manifest_artifact_path,
            "manifest_version": manifest_version,
            "sample_count": sample_count,
            "low_confidence_count": low_confidence_count,
            "qa_status": qa_status,
            "export_status": export_status,
            "training_receipt_status": training_receipt_status,
            "release_gate_status": release_gate_status,
            "replay_ready": replay_ready,
        },
        "dispatches": [serialize_task_dispatch(item) for item in dispatches],
        "messages": serialized_messages,
        "timeline": _task_timeline(messages, dispatches, approvals),
        "approvals": serialized_approvals,
        "receipts": receipts,
        "capability_summary": capability_summary,
        "audit": serialized_audit,
    }


def get_task_artifact_index(db: Session, task_id: str) -> list[dict[str, object]]:
    get_task_or_404(db, task_id)
    dispatches = {
        str(item.id or ""): item
        for item in list_task_dispatches(db, task_id)
        if str(item.id or "").strip()
    }
    source_messages = {
        str(item.id or ""): item
        for item in db.scalars(
            select(CollaborationMessage)
            .where(CollaborationMessage.task_id == task_id)
            .order_by(CollaborationMessage.created_at.desc())
            .limit(200)
        )
        if str(item.id or "").strip()
    }
    messages = list(source_messages.values())
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in messages:
        metadata = dict(item.extra_data or {}) if isinstance(item.extra_data, dict) else {}
        dispatch_id = str(item.dispatch_id or metadata.get("dispatch_id") or metadata.get("dispatchId") or "").strip() or None
        dispatch = dispatches.get(dispatch_id or "")
        exception_state = _task_message_exception_state(item)
        exception_tags = list(exception_state.get("tags") or [])
        authority = _task_authority_fields(item, metadata)
        source_message_id = str(metadata.get("source_message_id") or "").strip() or None
        source_message = source_messages.get(source_message_id or "")
        source_dispatch_id = str(
            getattr(source_message, "dispatch_id", None)
            or (dict(getattr(source_message, "extra_data", {}) or {}).get("dispatch_id") if source_message is not None else "")
            or ""
        ).strip() or None
        effective_dispatch_id = dispatch_id or source_dispatch_id
        effective_dispatch = dispatch or dispatches.get(effective_dispatch_id or "")
        authority_seat = str(authority.get("authoritative_seat_ref") or authority.get("authoritative_seat_id") or "").strip()
        source_authority_ok = True
        if source_message is not None:
            source_metadata = dict(source_message.extra_data or {}) if isinstance(source_message.extra_data, dict) else {}
            source_authority = _task_authority_fields(source_message, source_metadata)
            source_candidates = {
                str(source_authority.get("authoritative_target_seat_id") or "").strip(),
                str(source_authority.get("authoritative_seat_ref") or source_authority.get("authoritative_seat_id") or "").strip(),
                str(getattr(source_message, "recipient_id", None) or "").strip(),
                str(getattr(effective_dispatch, "workstation_id", None) or "").strip(),
            }
            source_candidates = {item for item in source_candidates if item}
            if authority_seat and source_candidates and authority_seat not in source_candidates:
                source_authority_ok = False
        for entry in _task_artifact_refs_from_metadata(metadata):
            if source_message_id and source_message is None and effective_dispatch is None:
                continue
            if source_message_id and not source_authority_ok:
                continue
            if effective_dispatch_id and effective_dispatch is None:
                continue
            key = (str(item.id), str(entry["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "label": entry["label"],
                    "path": entry["path"],
                    "task_id": task_id,
                    "source_message_id": item.id,
                    "source_message_type": item.message_type,
                    "dispatch_id": effective_dispatch_id,
                    "sender_id": item.sender_id,
                    "authoritative_seat_id": authority["authoritative_seat_id"],
                    "authoritative_seat_ref": authority["authoritative_seat_ref"],
                    "authoritative_target_seat_id": authority["authoritative_target_seat_id"],
                    "historical_alias_non_authoritative": authority["historical_alias_non_authoritative"],
                    "created_at": item.created_at,
                    "exception_tags": exception_tags,
                    "blocked_reason_code": exception_state.get("blocked_reason_code"),
                    "evidence_complete": exception_state.get("evidence_complete"),
                    "runner_id": effective_dispatch.runner_id if effective_dispatch is not None else None,
                    "workstation_id": effective_dispatch.workstation_id if effective_dispatch is not None else None,
                    "preview_context": _task_artifact_preview_context(
                        task_id=task_id,
                        path=entry["path"],
                        source_message_id=item.id,
                        dispatch_id=effective_dispatch_id,
                        workstation_id=effective_dispatch.workstation_id if effective_dispatch is not None else None,
                        sender_id=item.sender_id,
                        authoritative_seat_id=authority["authoritative_seat_id"],
                        authoritative_seat_ref=authority["authoritative_seat_ref"],
                    ),
                }
            )
    return rows


def list_tasks(db: Session, project_ids: list[str] | None = None):
    return repo.list_tasks(db, project_ids=project_ids)


def get_task_or_404(db: Session, task_id: str):
    task = repo.get_task(db, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "未找到任务", status_code=404)
    return task


def list_task_dispatches(db: Session, task_id: str) -> list[TaskDispatch]:
    get_task_or_404(db, task_id)
    stmt = select(TaskDispatch).where(TaskDispatch.task_id == task_id).order_by(TaskDispatch.created_at.desc())
    return list(db.scalars(stmt))


def dispatch_task(db: Session, task_id: str, payload: TaskDispatchCreate, *, dispatched_by_user_id: str | None = None) -> TaskDispatch:
    task = get_task_or_404(db, task_id)
    workstation = db.scalar(
        select(ProjectThreadWorkstation).where(
            ProjectThreadWorkstation.project_id == task.project_id,
            ProjectThreadWorkstation.config_id == payload.workstation_id,
        )
    )
    if workstation is None:
        raise AppError("WORKSTATION_NOT_FOUND", "workstation not found", status_code=404)

    computer_node = None
    if workstation.computer_node_id:
        computer_node = db.scalar(
            select(ProjectComputerNode).where(
                ProjectComputerNode.project_id == task.project_id,
                ProjectComputerNode.config_id == workstation.computer_node_id,
            )
        )
    ai_provider = None
    if workstation.ai_provider_id:
        ai_provider = db.scalar(
            select(ProjectAIProvider).where(
                ProjectAIProvider.project_id == task.project_id,
                ProjectAIProvider.config_id == workstation.ai_provider_id,
            )
        )

    before = _task_snapshot(task)
    task.assignee_agent_id = workstation.agent_id
    if task.status == "ready":
        task.status = "queued"
    db.add(task)

    dispatch = TaskDispatch(
        task_id=task.id,
        project_id=task.project_id,
        workstation_id=workstation.config_id,
        workstation_name=workstation.name,
        agent_id=workstation.agent_id,
        computer_node_id=workstation.computer_node_id,
        ai_provider_id=workstation.ai_provider_id,
        runner_id=computer_node.runner_id if computer_node else None,
        status=payload.status,
        notes=payload.notes,
        dispatched_by_user_id=dispatched_by_user_id,
    )
    db.add(dispatch)
    db.flush()

    repo.create_task_event(
        db,
        task.id,
        "task_dispatched",
        f"task dispatched to workstation {workstation.name}",
        {
            "dispatch_id": dispatch.id,
            "workstation_id": dispatch.workstation_id,
            "workstation_name": dispatch.workstation_name,
            "agent_id": dispatch.agent_id,
            "computer_node_id": dispatch.computer_node_id,
            "ai_provider_id": dispatch.ai_provider_id,
            "runner_id": dispatch.runner_id,
            "provider_enabled": ai_provider.enabled if ai_provider else None,
            "status": dispatch.status,
        },
        actor_type="human",
        actor_id=dispatched_by_user_id,
        commit=False,
    )
    _enqueue_runner_command_for_dispatch(
        db,
        task,
        dispatch,
        dispatched_by_user_id=dispatched_by_user_id,
    )
    append_audit_log(
        db,
        project_id=task.project_id,
        task_id=task.id,
        actor_type="human",
        actor_id=dispatched_by_user_id,
        action="task.dispatch",
        resource_type="task_dispatch",
        resource_id=dispatch.id,
        before=before,
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(dispatch)
    return dispatch


def create_task(db: Session, payload: TaskCreate):
    task = Task(**payload.model_dump())
    db.add(task)
    db.flush()

    if task.status != "draft":
        repo.create_task_event(
            db,
            task.id,
            "status_changed",
            f"任务初始状态已设置为 {task.status}",
            {"from_status": "draft", "to_status": task.status},
            actor_type="human",
            commit=False,
        )

    append_audit_log(
        db,
        task_id=task.id,
        actor_type="human",
        action="task.create",
        resource_type="task",
        resource_id=task.id,
        before={},
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(task)
    return task


def transition_task_status(db: Session, task_id: str, payload: TaskTransitionCreate):
    task = get_task_or_404(db, task_id)
    _validate_transition(task.status, payload.status)
    if task.status != payload.status:
        _ensure_high_risk_gate_open(db, task.id, payload.status)

    if task.status == payload.status and not payload.message and not payload.data:
        return task

    before = _task_snapshot(task)
    task.status = payload.status
    db.add(task)
    repo.create_task_event(
        db,
        task.id,
        "status_changed",
        payload.message or f"任务状态已调整为 {payload.status}",
        {
            "from_status": before["status"],
            "to_status": payload.status,
            "data": payload.data,
        },
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        commit=False,
    )
    append_audit_log(
        db,
        task_id=task.id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="task.transition",
        resource_type="task",
        resource_id=task.id,
        before=before,
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, payload: TaskUpdate):
    data = payload.model_dump(exclude_unset=True)
    before = _task_snapshot(task)
    status = data.pop("status", None)

    for key, value in data.items():
        setattr(task, key, value)

    if status is not None:
        _validate_transition(task.status, status)
        if status != task.status:
            _ensure_high_risk_gate_open(db, task.id, status)
            task.status = status
            repo.create_task_event(
                db,
                task.id,
                "status_changed",
                f"任务状态已从 {before['status']} 更新为 {status}",
                {"from_status": before["status"], "to_status": status},
                actor_type="system",
                commit=False,
            )

    db.add(task)
    append_audit_log(
        db,
        task_id=task.id,
        actor_type="system",
        action="task.update",
        resource_type="task",
        resource_id=task.id,
        before=before,
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(task)
    return task


def list_task_events(db: Session, task_id: str):
    get_task_or_404(db, task_id)
    return repo.list_task_events(db, task_id)


def claim_task_for_runner(
    db: Session,
    task_id: str,
    runner_id: str,
    *,
    message: str | None = None,
    data: dict | None = None,
    commit: bool = True,
):
    task = get_task_or_404(db, task_id)
    current_runner = _latest_runner_claim(db, task.id)
    if current_runner is not None and current_runner != runner_id:
        raise AppError("TASK_CLAIMED_BY_OTHER_RUNNER", "task already claimed by another runner", status_code=409)
    if task.status == "running" and current_runner == runner_id:
        return task

    before = _task_snapshot(task)
    if task.status != "running":
        _validate_transition(task.status, "running")
        _ensure_high_risk_gate_open(db, task.id, "running")
        task.status = "running"
        db.add(task)

    repo.create_task_event(
        db,
        task.id,
        "runner_picked",
        message or f"runner picked task: {runner_id}",
        {
            "runner_id": runner_id,
            "from_status": before["status"],
            "to_status": task.status,
            "data": data or {},
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
        after=_task_snapshot(task),
    )
    if commit:
        db.commit()
        db.refresh(task)
    return task


def claim_next_ready_task(db: Session, runner_id: str):
    stmt = (
        select(Task)
        .where(Task.status == "ready")
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
    task = None
    for candidate in db.scalars(stmt):
        if _pending_high_risk_approvals(db, candidate.id):
            continue
        task = candidate
        break
    if task is None:
        return None

    claim_task_for_runner(db, task.id, runner_id, commit=False)
    db.commit()
    db.refresh(task)
    return task


def record_task_log(
    db: Session,
    task_id: str,
    level: str,
    message: str,
    *,
    runner_id: str | None = None,
    data: dict | None = None,
):
    task = get_task_or_404(db, task_id)
    if runner_id is not None:
        _ensure_task_claimed_by_runner(db, task.id, runner_id)
    event = repo.create_task_event(
        db,
        task.id,
        f"log:{level}",
        message,
        {
            "level": level,
            "runner_id": runner_id,
            "data": data or {},
        },
        actor_type="runner" if runner_id else "system",
        actor_id=runner_id,
        commit=False,
    )
    append_audit_log(
        db,
        task_id=task.id,
        actor_type="runner" if runner_id else "system",
        actor_id=runner_id,
        action="runner.log_task",
        resource_type="task",
        resource_id=task.id,
        before=_task_snapshot(task),
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(event)
    return event


def record_task_result(
    db: Session,
    task_id: str,
    result: dict,
    *,
    runner_id: str | None = None,
    status: str | None = None,
    message: str | None = None,
    data: dict | None = None,
    commit: bool = True,
):
    task = get_task_or_404(db, task_id)
    if runner_id is not None:
        _ensure_task_claimed_by_runner(db, task.id, runner_id)

    next_status = status or "reviewing"
    _validate_transition(task.status, next_status)
    _ensure_high_risk_gate_open(db, task.id, next_status)
    before = _task_snapshot(task)
    task.status = next_status
    db.add(task)
    event = repo.create_task_event(
        db,
        task.id,
        "result",
        message or "runner submitted task result",
        {
            "runner_id": runner_id,
            "status": next_status,
            "result": result,
            "data": data or {},
        },
        actor_type="runner" if runner_id else "system",
        actor_id=runner_id,
        commit=False,
    )
    append_audit_log(
        db,
        task_id=task.id,
        actor_type="runner" if runner_id else "system",
        actor_id=runner_id,
        action="runner.submit_result",
        resource_type="task",
        resource_id=task.id,
        before=before,
        after=_task_snapshot(task),
    )
    if commit:
        db.commit()
        db.refresh(task)
        db.refresh(event)
    return event


def add_task_log(
    db: Session,
    task_id: str,
    level: str,
    message: str,
    *,
    runner_id: str | None = None,
    data: dict | None = None,
):
    return record_task_log(db, task_id, level, message, runner_id=runner_id, data=data)


def add_task_result(
    db: Session,
    task_id: str,
    result: dict,
    *,
    runner_id: str | None = None,
    status: str | None = None,
    message: str | None = None,
    data: dict | None = None,
):
    return record_task_result(
        db,
        task_id,
        result,
        runner_id=runner_id,
        status=status,
        message=message,
        data=data,
    )


TASK_ACTION_TO_STATUS: dict[str, str | None] = {
    "plan": "planning",
    "approve_plan": "ready",
    "run": "running",
    "cancel": "cancelled",
    "review": "reviewing",
    "merge": "done",
    "rollback": "blocked",
}

TASK_ACTION_TO_AUDIT: dict[str, str] = {
    "plan": "task.plan_requested",
    "approve_plan": "task.plan_approved",
    "run": "task.run_requested",
    "cancel": "task.cancel_requested",
    "review": "task.review_requested",
    "merge": "task.merge_requested",
    "rollback": "task.rollback_requested",
}

TASK_ACTION_DEFAULT_MESSAGE: dict[str, str] = {
    "plan": "已进入任务规划阶段",
    "approve_plan": "计划已通过，可以继续执行",
    "run": "任务已开始执行",
    "cancel": "任务已取消",
    "review": "任务已进入审查阶段",
    "merge": "任务已收口，等待版本合并",
    "rollback": "任务已登记回滚处理",
}


def run_named_task_action(db: Session, task_id: str, action: str, payload: TaskActionRequest):
    task = get_task_or_404(db, task_id)
    target_status = TASK_ACTION_TO_STATUS.get(action)
    if action not in TASK_ACTION_TO_AUDIT:
        raise AppError("UNKNOWN_TASK_ACTION", "?????????", status_code=400)

    if action in {"approve_plan", "run", "review", "merge"}:
        _ensure_high_risk_gate_open(db, task.id, target_status or task.status)

    before = _task_snapshot(task)
    if target_status is not None:
        _validate_transition(task.status, target_status)
        if target_status != task.status:
            _ensure_high_risk_gate_open(db, task.id, target_status)
            task.status = target_status
            db.add(task)

    repo.create_task_event(
        db,
        task.id,
        action,
        payload.message or TASK_ACTION_DEFAULT_MESSAGE[action],
        {
            "action": action,
            "target_status": target_status,
            "target_ref": payload.target_ref,
            "data": payload.data,
        },
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        commit=False,
    )
    append_audit_log(
        db,
        task_id=task.id,
        project_id=task.project_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action=TASK_ACTION_TO_AUDIT[action],
        resource_type="task",
        resource_id=task.id,
        before=before,
        after=_task_snapshot(task),
    )
    db.commit()
    db.refresh(task)
    return task
