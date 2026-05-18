from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal, resolve_runner_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.project_collaboration import ProjectComputerNode
from app.db.models.project_member import ProjectMember
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.session import get_db
from app.modules.collaboration.schemas import RunnerRelayAckCreate, RunnerRelayCompleteCreate, RunnerRelayMessageRead
from app.modules.read_access import readable_project_ids
from app.modules.collaboration.service import (
    ack_runner_command,
    complete_runner_command,
    consume_runner_pairing_token,
    list_runner_inbox_messages,
)
from app.settings import get_settings
from app.modules.tasks.schemas import TaskEventRead, TaskRead

from .schemas import (
    RunnerBindingCreate,
    RunnerBindingDeleteRead,
    RunnerBindingRead,
    RunnerDeviceInterfaceScanCreate,
    RunnerDeviceInterfaceScanRead,
    RunnerHeartbeat,
    RunnerRead,
    RunnerRegister,
    RunnerTaskDispatchRead,
    RunnerThreadWorkstationSyncCreate,
    RunnerTaskLogCreate,
    RunnerTaskResultCreate,
    RunnerTaskTransitionCreate,
    RunnerWorkspaceRead,
)
from .service import (
    bind_runner_to_computer_node,
    fetch_next_task,
    get_runner_or_404,
    heartbeat,
    list_runners,
    record_runner_log,
    record_runner_result,
    register_runner,
    register_runner_with_binding,
    serialize_runner_for_read,
    serialize_runner_workspace,
    sync_runner_device_interfaces,
    sync_runner_thread_workstations,
    transition_runner_task,
    unbind_runner_from_computer_node,
)


router = APIRouter(prefix="/api/runners", tags=["runners"])


def _readable_runner_ids(db: Session, request: Request) -> tuple[list[str], list[str]]:
    scoped_project_ids = readable_project_ids(db, request)
    if not scoped_project_ids:
        return [], []
    runner_ids = [
        str(runner_id)
        for runner_id in db.scalars(
            select(ProjectComputerNode.runner_id).where(
                ProjectComputerNode.project_id.in_(scoped_project_ids),
                ProjectComputerNode.runner_id.is_not(None),
            )
        ).all()
        if str(runner_id or "").strip()
    ]
    deduped_runner_ids: list[str] = []
    seen: set[str] = set()
    for runner_id in runner_ids:
        if runner_id in seen:
            continue
        seen.add(runner_id)
        deduped_runner_ids.append(runner_id)
    return scoped_project_ids, deduped_runner_ids


def _require_runner_project_access(db: Session, request: Request, runner_id: str):
    if request.headers.get("x-runner-id"):
        return resolve_runner_principal(db, request, runner_id, action="runner.read")

    principal = resolve_human_principal(db, request)
    if principal.bootstrap:
        return principal
    project_ids = [
        str(project_id)
        for project_id in db.scalars(
            select(ProjectComputerNode.project_id).where(ProjectComputerNode.runner_id == runner_id).distinct()
        ).all()
        if str(project_id)
    ]
    if not project_ids:
        raise AppError("PERMISSION_DENIED", "当前用户没有这个 Runner 的项目访问权", status_code=403)
    member = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.user_id == principal.user_id,
            ProjectMember.project_id.in_(project_ids),
            ProjectMember.status != "removed",
        )
    )
    if member is None:
        raise AppError("PERMISSION_DENIED", "当前用户没有这个 Runner 的项目访问权", status_code=403)
    return principal


@router.get("")
def api_list_runners(request: Request, db: Session = Depends(get_db)):
    _, scoped_runner_ids = _readable_runner_ids(db, request)
    if not scoped_runner_ids:
        return ok([])
    scoped_runner_id_set = set(scoped_runner_ids)
    scoped = [item for item in list_runners(db) if str(item.id) in scoped_runner_id_set]
    return ok([RunnerRead.model_validate(serialize_runner_for_read(db, item)).model_dump(mode="json") for item in scoped])


@router.get("/summary")
def api_runner_summary(request: Request, db: Session = Depends(get_db)):
    scoped_project_ids, scoped_runner_ids = _readable_runner_ids(db, request)
    if not scoped_runner_ids:
        return ok(
            {
                "total": 0,
                "online": 0,
                "offline": 0,
                "hardware_access_enabled": 0,
                "claimed_tasks": 0,
                "active_runner_tasks": 0,
                "bound_computer_nodes": 0,
                "bound_projects": 0,
                "recent_error_events": 0,
                "last_heartbeat_at": None,
            }
        )

    total = db.scalar(select(func.count(Runner.id)).where(Runner.id.in_(scoped_runner_ids))) or 0
    online = db.scalar(select(func.count(Runner.id)).where(Runner.id.in_(scoped_runner_ids), Runner.status == "online")) or 0
    offline = db.scalar(select(func.count(Runner.id)).where(Runner.id.in_(scoped_runner_ids), Runner.status == "offline")) or 0
    hardware_access_enabled = (
        db.scalar(
            select(func.count(Runner.id)).where(
                Runner.id.in_(scoped_runner_ids),
                Runner.allow_hardware_access.is_(True),
            )
        )
        or 0
    )
    claimed_tasks = (
        db.scalar(
            select(func.count(TaskEvent.id))
            .join(Task, Task.id == TaskEvent.task_id)
            .where(
                TaskEvent.actor_type == "runner",
                TaskEvent.actor_id.in_(scoped_runner_ids),
                TaskEvent.event_type == "runner_picked",
                Task.project_id.in_(scoped_project_ids),
            )
        )
        or 0
    )
    bound_computer_nodes = (
        db.scalar(
            select(func.count(ProjectComputerNode.id)).where(
                ProjectComputerNode.project_id.in_(scoped_project_ids),
                ProjectComputerNode.runner_id.in_(scoped_runner_ids),
            )
        )
        or 0
    )
    bound_projects = (
        db.scalar(
            select(func.count(distinct(ProjectComputerNode.project_id))).where(
                ProjectComputerNode.project_id.in_(scoped_project_ids),
                ProjectComputerNode.runner_id.in_(scoped_runner_ids),
            )
        )
        or 0
    )
    active_runner_tasks = (
        db.scalar(
            select(func.count(distinct(TaskEvent.task_id)))
            .join(Task, Task.id == TaskEvent.task_id)
            .where(
                TaskEvent.actor_type == "runner",
                TaskEvent.actor_id.in_(scoped_runner_ids),
                TaskEvent.event_type == "runner_picked",
                Task.project_id.in_(scoped_project_ids),
            )
        )
        or 0
    )
    recent_error_events = (
        db.scalar(
            select(func.count(TaskEvent.id))
            .join(Task, Task.id == TaskEvent.task_id)
            .where(
                TaskEvent.actor_type == "runner",
                TaskEvent.actor_id.in_(scoped_runner_ids),
                TaskEvent.event_type == "log:error",
                Task.project_id.in_(scoped_project_ids),
            )
        )
        or 0
    )
    last_heartbeat_at = db.scalar(
        select(Runner.last_heartbeat_at).where(Runner.id.in_(scoped_runner_ids)).order_by(Runner.last_heartbeat_at.desc()).limit(1)
    )
    return ok(
        {
            "total": int(total),
            "online": int(online),
            "offline": int(offline),
            "hardware_access_enabled": int(hardware_access_enabled),
            "claimed_tasks": int(claimed_tasks),
            "active_runner_tasks": int(active_runner_tasks),
            "bound_computer_nodes": int(bound_computer_nodes),
            "bound_projects": int(bound_projects),
            "recent_error_events": int(recent_error_events),
            "last_heartbeat_at": last_heartbeat_at,
        }
    )


@router.post("/register")
def api_register_runner(payload: RunnerRegister, request: Request, db: Session = Depends(get_db)):
    resolve_runner_principal(db, request, payload.runner_id, action="runner.register", allow_missing=True)
    registration_token = request.headers.get("x-runner-registration-token", "").strip()
    settings = get_settings()

    if payload.computer_node_id:
        if not registration_token:
            raise AppError("PAIRING_TOKEN_REQUIRED", "computer_node_id requires a pairing token", status_code=422)
        node = consume_runner_pairing_token(
            db,
            registration_token,
            computer_node_id=payload.computer_node_id,
        )
        if node is None:
            raise AppError("PAIRING_TOKEN_INVALID", "computer node pairing token is invalid", status_code=403)
        runner = register_runner_with_binding(
            db,
            payload,
            project_id=str(node.project_id),
            computer_node_id=str(node.config_id),
        )
    else:
        configured_registration_token = settings.runner_registration_token.strip()
        if configured_registration_token:
            if not registration_token:
                raise AppError("UNAUTHORIZED", "Runner registration token is required", status_code=401)
            if registration_token != configured_registration_token:
                raise AppError("PERMISSION_DENIED", "Runner registration token is invalid", status_code=403)
        runner = register_runner(db, payload)

    return ok(RunnerRead.model_validate(serialize_runner_for_read(db, runner)).model_dump(mode="json"))


@router.post("/heartbeat")
def api_runner_heartbeat(payload: RunnerHeartbeat, request: Request, db: Session = Depends(get_db)):
    resolve_runner_principal(db, request, payload.runner_id, action="runner.heartbeat")
    return ok(RunnerRead.model_validate(serialize_runner_for_read(db, heartbeat(db, payload.runner_id))).model_dump(mode="json"))


@router.get("/{runner_id}")
def api_get_runner(runner_id: str, request: Request, db: Session = Depends(get_db)):
    _require_runner_project_access(db, request, runner_id)
    return ok(RunnerRead.model_validate(serialize_runner_for_read(db, get_runner_or_404(db, runner_id))).model_dump(mode="json"))


@router.get("/{runner_id}/workspace")
def api_get_runner_workspace(runner_id: str, request: Request, db: Session = Depends(get_db)):
    _require_runner_project_access(db, request, runner_id)
    runner = get_runner_or_404(db, runner_id)
    return ok(RunnerWorkspaceRead.model_validate(serialize_runner_workspace(db, runner)).model_dump(mode="json"))


@router.post("/{runner_id}/thread-workstations/sync")
def api_sync_runner_thread_workstations(
    runner_id: str,
    payload: RunnerThreadWorkstationSyncCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.thread_workstations.sync")
    return ok(sync_runner_thread_workstations(db, runner_id, payload))


@router.post("/{runner_id}/device-interfaces/sync")
def api_sync_runner_device_interfaces(
    runner_id: str,
    payload: RunnerDeviceInterfaceScanCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.device_interfaces.sync")
    result = sync_runner_device_interfaces(db, runner_id, payload)
    return ok(RunnerDeviceInterfaceScanRead.model_validate(result).model_dump(mode="json"))


@router.post("/{runner_id}/bindings")
def api_bind_runner_to_computer_node(
    runner_id: str,
    payload: RunnerBindingCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(
        db,
        request,
        payload.project_id,
        require_privileged=True,
        action="runner.binding.create",
    )
    binding = bind_runner_to_computer_node(db, runner_id, payload.project_id, payload.computer_node_id)
    return ok(RunnerBindingRead.model_validate(binding).model_dump(mode="json"))


@router.delete("/{runner_id}/bindings/{project_id}/{computer_node_id}")
def api_unbind_runner_from_computer_node(
    runner_id: str,
    project_id: str,
    computer_node_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(
        db,
        request,
        project_id,
        require_privileged=True,
        action="runner.binding.delete",
    )
    binding = unbind_runner_from_computer_node(db, runner_id, project_id, computer_node_id)
    return ok(RunnerBindingDeleteRead.model_validate(binding).model_dump(mode="json"))


@router.get("/{runner_id}/next-task")
def api_get_next_task(runner_id: str, request: Request, db: Session = Depends(get_db)):
    resolve_runner_principal(db, request, runner_id, action="runner.next_task")
    runner = get_runner_or_404(db, runner_id)
    workspace = RunnerWorkspaceRead.model_validate(serialize_runner_workspace(db, runner))
    task = fetch_next_task(db, runner_id)
    if task is None:
        return ok(
            RunnerTaskDispatchRead(
                runner_id=runner_id,
                workspace=workspace,
                task=None,
                claimed=False,
                note="No ready task is available for this runner.",
            ).model_dump(mode="json")
        )
    return ok(
        RunnerTaskDispatchRead(
            runner_id=runner_id,
            workspace=workspace,
            task=TaskRead.model_validate(task),
            id=task.id,
            title=task.title,
            status=task.status,
            commands=[["echo", f"Running {task.id}"]],
            claimed=True,
            note="Task claimed successfully.",
        ).model_dump(mode="json")
    )


@router.get("/{runner_id}/inbox")
def api_get_runner_inbox(
    runner_id: str,
    request: Request,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.inbox.read")
    items = list_runner_inbox_messages(db, runner_id, status=status, limit=limit)
    return ok([RunnerRelayMessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{runner_id}/messages/{message_id}/ack")
def api_ack_runner_message(
    runner_id: str,
    message_id: str,
    payload: RunnerRelayAckCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.inbox.ack")
    result = ack_runner_command(db, runner_id, message_id, payload)
    return ok(
        {
            "command": RunnerRelayMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": (
                RunnerRelayMessageRead.model_validate(result["receipt"]).model_dump(mode="json")
                if result["receipt"] is not None
                else None
            ),
        }
    )


@router.post("/{runner_id}/messages/{message_id}/complete")
def api_complete_runner_message(
    runner_id: str,
    message_id: str,
    payload: RunnerRelayCompleteCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.inbox.complete")
    result = complete_runner_command(db, runner_id, message_id, payload)
    return ok(
        {
            "command": RunnerRelayMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": (
                RunnerRelayMessageRead.model_validate(result["receipt"]).model_dump(mode="json")
                if result["receipt"] is not None
                else None
            ),
        }
    )


@router.post("/{runner_id}/tasks/{task_id}/logs")
def api_runner_task_log(
    runner_id: str,
    task_id: str,
    payload: RunnerTaskLogCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.task.log")
    event = record_runner_log(db, runner_id, task_id, payload.level, payload.message, payload.data)
    return ok(TaskEventRead.model_validate(event).model_dump(mode="json"))


@router.post("/{runner_id}/tasks/{task_id}/result")
def api_runner_task_result(
    runner_id: str,
    task_id: str,
    payload: RunnerTaskResultCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.task.result")
    event = record_runner_result(
        db,
        runner_id,
        task_id,
        payload.result,
        status=payload.status,
        message=payload.message,
        data=payload.data,
    )
    return ok(TaskEventRead.model_validate(event).model_dump(mode="json"))


@router.post("/{runner_id}/tasks/{task_id}/transition")
def api_runner_task_transition(
    runner_id: str,
    task_id: str,
    payload: RunnerTaskTransitionCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_runner_principal(db, request, runner_id, action="runner.task.transition")
    task = transition_runner_task(
        db,
        runner_id,
        task_id,
        payload.status,
        message=payload.message,
        data=payload.data,
    )
    return ok(TaskRead.model_validate(task).model_dump(mode="json"))
