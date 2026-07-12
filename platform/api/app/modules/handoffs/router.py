from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.task import Task
from app.db.session import get_db
from app.modules.messages.schemas import MessageCreate, MessageRead
from app.modules.messages.service import create_entity_message, list_entity_messages
from app.modules.read_access import (
    readable_project_ids,
    require_project_read_access,
    resolve_handoff_project_id,
    resolve_task_project_id,
)

from .schemas import HandoffAcceptRequest, HandoffAssignRequest, HandoffPackageCreate, HandoffPackageRead
from .service import (
    _to_read_dict,
    accept_handoff,
    assign_handoff_agent,
    create_handoff,
    get_handoff_or_404,
    list_handoffs,
)


router = APIRouter(prefix="/api", tags=["handoffs"])


def _handoff_project_id(db: Session, handoff_id: str) -> str:
    handoff = get_handoff_or_404(db, handoff_id)
    if handoff.project_id:
        return handoff.project_id
    if handoff.task_id:
        task = db.get(Task, handoff.task_id)
        if task is not None and task.project_id:
            return task.project_id
    raise AppError("PROJECT_NOT_FOUND", "handoff has no project context", status_code=404)


def _create_handoff_project_id(db: Session, project_id: str | None, task_id: str) -> str:
    if project_id:
        task = db.get(Task, task_id)
        if task is not None and task.project_id and task.project_id != project_id:
            raise AppError("PROJECT_MISMATCH", "handoff project does not match task scope", status_code=400)
        return project_id
    task = db.get(Task, task_id)
    if task is not None and task.project_id:
        return task.project_id
    raise AppError("PROJECT_NOT_FOUND", "handoff write requires a project context", status_code=404)


def _require_handoff_project_access(db: Session, request: Request, handoff_id: str) -> str:
    project_id = _handoff_project_id(db, handoff_id)
    require_project_read_access(db, request, project_id, action="handoff.read")
    return project_id


@router.get("/handoffs")
def api_list_handoffs(
    request: Request,
    task_id: str | None = None,
    project_id: str | None = None,
    handoff_from: str | None = None,
    handoff_to: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if task_id:
        project_ids = [resolve_task_project_id(db, task_id)]
        require_project_read_access(db, request, project_ids[0], action="handoff.read")
    elif project_id:
        project_ids = [project_id]
        require_project_read_access(db, request, project_id, action="handoff.read")
    else:
        project_ids = readable_project_ids(db, request)
    items = list_handoffs(
        db,
        task_id=task_id,
        project_id=project_id,
        handoff_from=handoff_from,
        handoff_to=handoff_to,
        limit=limit,
    )
    if not task_id and not project_id:
        allowed = set(project_ids)
        items = [item for item in items if str(item.project_id or "") in allowed]
    return ok([HandoffPackageRead.model_validate(_to_read_dict(item)).model_dump(mode="json") for item in items])


@router.get("/tasks/{task_id}/handoffs")
def api_list_task_handoffs(task_id: str, request: Request, limit: int = 100, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_task_project_id(db, task_id), action="handoff.read")
    items = list_handoffs(db, task_id=task_id, limit=limit)
    return ok([HandoffPackageRead.model_validate(_to_read_dict(item)).model_dump(mode="json") for item in items])


@router.post("/tasks/{task_id}/handoffs")
def api_create_task_handoff(task_id: str, payload: HandoffPackageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _create_handoff_project_id(db, payload.project_id, task_id)
    resolve_project_write_principal(db, request, project_id, action="handoff.create")
    data = payload.model_dump()
    data["task_id"] = task_id
    data["project_id"] = project_id
    handoff = create_handoff(db, HandoffPackageCreate(**data))
    return ok(HandoffPackageRead.model_validate(_to_read_dict(handoff)).model_dump(mode="json"))


@router.post("/tasks/{task_id}/create-handoff")
def api_create_task_handoff_alias(task_id: str, payload: HandoffPackageCreate, request: Request, db: Session = Depends(get_db)):
    return api_create_task_handoff(task_id=task_id, payload=payload, request=request, db=db)


@router.get("/tasks/{task_id}/handoffs/{handoff_id}")
def api_get_task_handoff(task_id: str, handoff_id: str, request: Request, db: Session = Depends(get_db)):
    handoff = get_handoff_or_404(db, handoff_id)
    require_project_read_access(db, request, _handoff_project_id(db, handoff_id), action="handoff.read")
    if handoff.task_id != task_id:
        return ok({})
    return ok(HandoffPackageRead.model_validate(_to_read_dict(handoff)).model_dump(mode="json"))


@router.post("/tasks/{task_id}/handoffs/{handoff_id}/accept")
def api_accept_handoff(task_id: str, handoff_id: str, payload: HandoffAcceptRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _handoff_project_id(db, handoff_id)
    resolve_project_write_principal(db, request, project_id, action="handoff.accept")
    handoff = accept_handoff(db, task_id, handoff_id, payload)
    return ok(HandoffPackageRead.model_validate(_to_read_dict(handoff)).model_dump(mode="json"))


@router.post("/tasks/{task_id}/handoffs/{handoff_id}/assign-agent")
def api_assign_handoff_agent(
    task_id: str, handoff_id: str, payload: HandoffAssignRequest, request: Request, db: Session = Depends(get_db)
):
    project_id = _handoff_project_id(db, handoff_id)
    resolve_project_write_principal(db, request, project_id, action="handoff.assign")
    handoff = assign_handoff_agent(db, task_id, handoff_id, payload)
    return ok(HandoffPackageRead.model_validate(_to_read_dict(handoff)).model_dump(mode="json"))


@router.get("/handoffs/{handoff_id}")
def api_get_handoff(handoff_id: str, request: Request, db: Session = Depends(get_db)):
    handoff = get_handoff_or_404(db, handoff_id)
    require_project_read_access(db, request, resolve_handoff_project_id(db, handoff_id), action="handoff.read")
    return ok(HandoffPackageRead.model_validate(_to_read_dict(handoff)).model_dump(mode="json"))


@router.get("/handoffs/{handoff_id}/messages")
def api_handoff_messages(handoff_id: str, request: Request, message_type: str | None = None, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_handoff_project_id(db, handoff_id), action="handoff.read")
    items = list_entity_messages(db, "handoff", handoff_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/handoffs/{handoff_id}/messages")
def api_create_handoff_message(handoff_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = payload.project_id or _handoff_project_id(db, handoff_id)
    resolve_project_write_principal(db, request, project_id, action="handoff.message.create")
    return ok(
        MessageRead.model_validate(
            create_entity_message(
                db,
                "handoff",
                handoff_id,
                project_id=project_id,
                message_type=payload.message_type,
                sender_type=payload.sender_type,
                sender_id=payload.sender_id,
                body=payload.body,
                parent_message_id=payload.parent_message_id,
                data=payload.data,
            )
        ).model_dump(mode="json")
    )
