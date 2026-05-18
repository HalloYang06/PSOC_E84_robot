from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.access import (
    resolve_project_write_principal,
    resolve_runner_task_principal,
    resolve_task_write_principal,
)
from app.common.response import ok
from app.common.response import ok_paginated
from app.db.session import get_db
from app.modules.read_access import (
    require_project_read_access,
    resolve_task_project_id,
    scoped_project_ids_for_read,
)
from app.modules.messages.schemas import MessageCreate, MessageRead
from app.modules.messages.service import create_entity_message, list_entity_messages

from .schemas import (
    ArtifactIndexEntryRead,
    ProfessionalTaskViewRead,
    TaskCreate,
    TaskEventRead,
    TaskLogCreate,
    TaskRead,
    TaskResultCreate,
    TaskActionRequest,
    TaskTransitionCreate,
    TaskDispatchCreate,
    TaskDispatchRead,
    TaskUpdate,
)
from .service import (
    add_task_log,
    add_task_result,
    create_task,
    dispatch_task,
    get_task_or_404,
    get_task_gate_state,
    list_task_dispatches,
    list_task_events,
    list_tasks,
    run_named_task_action,
    transition_task_status,
    update_task,
    get_task_professional_view,
)


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def api_list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: list[str] | None = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    scoped_project_ids = scoped_project_ids_for_read(db, request, project_id, action="task.read")
    items = list_tasks(db, project_ids=scoped_project_ids) if scoped_project_ids else []
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    rows = [TaskRead.model_validate(item).model_dump(mode="json") for item in items[start:end]]
    return ok_paginated(rows, page=page, page_size=page_size, total=total)


@router.post("")
def api_create_task(payload: TaskCreate, request: Request, db: Session = Depends(get_db)):
    resolve_project_write_principal(db, request, payload.project_id, action="task.create")
    return ok(TaskRead.model_validate(create_task(db, payload)).model_dump(mode="json"))


@router.get("/{task_id}")
def api_get_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.read")
    return ok(TaskRead.model_validate(get_task_or_404(db, task_id)).model_dump(mode="json"))


@router.get("/{task_id}/gate")
def api_task_gate(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.read")
    return ok(get_task_gate_state(db, task_id))


@router.get("/{task_id}/professional-view")
def api_task_professional_view(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.read")
    return ok(ProfessionalTaskViewRead.model_validate(get_task_professional_view(db, task_id)).model_dump(mode="json"))


@router.get("/{task_id}/artifact-index")
def api_task_artifact_index(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.read")
    from .service import get_task_artifact_index

    return ok([ArtifactIndexEntryRead.model_validate(item).model_dump(mode="json") for item in get_task_artifact_index(db, task_id)])


@router.patch("/{task_id}")
def api_update_task(task_id: str, payload: TaskUpdate, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.update")
    task = get_task_or_404(db, task_id)
    return ok(TaskRead.model_validate(update_task(db, task, payload)).model_dump(mode="json"))


@router.get("/{task_id}/events")
def api_task_events(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.events.read")
    return ok([TaskEventRead.model_validate(item).model_dump(mode="json") for item in list_task_events(db, task_id)])


@router.get("/{task_id}/dispatches")
def api_task_dispatches(task_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="task.dispatches.read")
    items = list_task_dispatches(db, task_id)
    return ok([TaskDispatchRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{task_id}/dispatch")
def api_task_dispatch(task_id: str, payload: TaskDispatchCreate, request: Request, db: Session = Depends(get_db)):
    principal = resolve_task_write_principal(db, request, task_id, action="task.dispatch")
    dispatch = dispatch_task(db, task_id, payload, dispatched_by_user_id=principal.user_id)
    return ok(TaskDispatchRead.model_validate(dispatch).model_dump(mode="json"))


@router.post("/{task_id}/logs")
def api_task_log(task_id: str, payload: TaskLogCreate, request: Request, db: Session = Depends(get_db)):
    principal = resolve_runner_task_principal(db, request, task_id, action="task.log")
    runner_id = payload.runner_id or principal.runner_id
    event = add_task_log(db, task_id, payload.level, payload.message, runner_id=runner_id, data=payload.data)
    return ok(TaskEventRead.model_validate(event).model_dump(mode="json"))


@router.post("/{task_id}/result")
def api_task_result(task_id: str, payload: TaskResultCreate, request: Request, db: Session = Depends(get_db)):
    principal = resolve_runner_task_principal(db, request, task_id, action="task.result")
    runner_id = payload.runner_id or principal.runner_id
    event = add_task_result(
        db,
        task_id,
        payload.result,
        runner_id=runner_id,
        status=payload.status,
        message=payload.message,
        data=payload.data,
    )
    return ok(TaskEventRead.model_validate(event).model_dump(mode="json"))


@router.post("/{task_id}/transition")
def api_task_transition(task_id: str, payload: TaskTransitionCreate, request: Request, db: Session = Depends(get_db)):
    has_runner_signal = bool(request.headers.get("x-runner-id"))
    if has_runner_signal:
        principal = resolve_runner_task_principal(db, request, task_id, require_claim=False, action="task.transition")
        payload = payload.model_copy(update={"actor_type": "runner", "actor_id": principal.actor_id})
    else:
        principal = resolve_task_write_principal(db, request, task_id, action="task.transition")
        payload = payload.model_copy(update={"actor_type": "human", "actor_id": principal.actor_id})
    task = transition_task_status(db, task_id, payload)
    return ok(TaskRead.model_validate(task).model_dump(mode="json"))


@router.post("/{task_id}/plan")
def api_task_plan(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.plan")
    return ok(run_named_task_action(db, task_id, "plan", payload))


@router.post("/{task_id}/approve-plan")
def api_task_approve_plan(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.approve_plan")
    return ok(run_named_task_action(db, task_id, "approve_plan", payload))


@router.post("/{task_id}/run")
def api_task_run(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.run")
    return ok(run_named_task_action(db, task_id, "run", payload))


@router.post("/{task_id}/cancel")
def api_task_cancel(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.cancel")
    return ok(run_named_task_action(db, task_id, "cancel", payload))


@router.post("/{task_id}/archive")
def api_task_archive(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.archive")
    return ok(run_named_task_action(db, task_id, "archive", payload))


@router.post("/{task_id}/review")
def api_task_review(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.review")
    return ok(run_named_task_action(db, task_id, "review", payload))


@router.post("/{task_id}/merge")
def api_task_merge(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, require_privileged=True, action="task.merge")
    return ok(run_named_task_action(db, task_id, "merge", payload))


@router.post("/{task_id}/rollback")
def api_task_rollback(task_id: str, payload: TaskActionRequest, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, require_privileged=True, action="task.rollback")
    return ok(run_named_task_action(db, task_id, "rollback", payload))


@router.get("/{task_id}/messages")
def api_task_messages(task_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    project_id = resolve_task_project_id(db, task_id)
    require_project_read_access(db, request, project_id, action="task.messages.read")
    items = list_entity_messages(db, "task", task_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{task_id}/messages")
def api_create_task_message(task_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.message.create")
    data = payload.model_dump()
    data["entity_type"] = "task"
    data["entity_id"] = task_id
    return ok(
        MessageRead.model_validate(
            create_entity_message(
                db,
                "task",
                task_id,
                project_id=data["project_id"],
                message_type=data["message_type"],
                sender_type=data["sender_type"],
                sender_id=data["sender_id"],
                body=data["body"],
                parent_message_id=data["parent_message_id"],
                data=data["data"],
            )
        ).model_dump(mode="json")
    )
