from __future__ import annotations

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.common.audit import append_audit_log
from app.common.errors import AppError
from app.db.models.approval import Approval
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


def _enqueue_runner_command_for_dispatch(
    db: Session,
    task: Task,
    dispatch: TaskDispatch,
    *,
    dispatched_by_user_id: str | None,
) -> CollaborationMessage | None:
    if not dispatch.runner_id:
        return None

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
