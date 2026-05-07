from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal_for_target
from app.common.errors import AppError
from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import MessageCreate, MessageRead
from .service import create_entity_message, create_message, list_entity_messages, list_messages, resolve_message_project_id


router = APIRouter(prefix="/api/messages", tags=["messages"])


def _authorize_message_write(
    db: Session,
    request: Request,
    *,
    entity_type: str,
    entity_id: str,
    project_id: str | None = None,
    action: str,
) -> str:
    resolved_project_id = resolve_message_project_id(db, entity_type, entity_id, project_id)
    if project_id is not None and project_id != resolved_project_id:
        raise AppError("PROJECT_MISMATCH", "message project does not match entity scope", status_code=400)
    resolve_project_write_principal_for_target(db, request, resolved_project_id, action=action)
    return resolved_project_id


def _authorize_message_read(
    db: Session,
    request: Request,
    *,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str,
) -> str:
    if entity_type and entity_id:
        resolved_project_id = resolve_message_project_id(db, entity_type, entity_id, project_id)
        if project_id is not None and project_id != resolved_project_id:
            raise AppError("PROJECT_MISMATCH", "message project does not match entity scope", status_code=400)
        require_project_read_access(db, request, resolved_project_id, action=action)
        return resolved_project_id
    if project_id:
        require_project_read_access(db, request, project_id, action=action)
        return project_id
    raise AppError("VALIDATION_ERROR", "message read requires project_id or entity target", status_code=422)


@router.get("")
def api_list_messages(
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    message_type: str | None = None,
    sender_type: str | None = None,
    limit: int = 100,
    request: Request = None,
    db: Session = Depends(get_db),
):
    scoped_project_id = _authorize_message_read(
        db,
        request,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action="message.read",
    )
    items = list_messages(
        db,
        project_id=scoped_project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        message_type=message_type,
        sender_type=sender_type,
        limit=limit,
    )
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("")
def api_create_message(payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type=str(payload.entity_type or ""),
        entity_id=str(payload.entity_id or ""),
        project_id=payload.project_id,
        action="message.create",
    )
    item = create_message(
        db,
        payload.model_copy(update={"project_id": project_id}),
    )
    return ok(MessageRead.model_validate(item).model_dump(mode="json"))


@router.get("/projects/{project_id}")
@router.get("/project/{project_id}")
def api_project_messages(project_id: str, message_type: str | None = None, limit: int = 100, request: Request = None, db: Session = Depends(get_db)):
    _authorize_message_read(db, request, project_id=project_id, action="project.message.read")
    items = list_entity_messages(db, "project", project_id, project_id=project_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items[: max(1, min(limit, 500))]])


@router.post("/projects/{project_id}")
@router.post("/project/{project_id}")
def api_create_project_message(project_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    _authorize_message_write(
        db,
        request,
        entity_type="project",
        entity_id=project_id,
        project_id=payload.project_id,
        action="project.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = "project"
    data["entity_id"] = project_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/tasks/{task_id}")
@router.get("/task/{task_id}")
def api_task_messages(task_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    _authorize_message_read(db, request, entity_type="task", entity_id=task_id, action="task.message.read")
    items = list_entity_messages(db, "task", task_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/tasks/{task_id}")
@router.post("/task/{task_id}")
def api_create_task_message(task_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type="task",
        entity_id=task_id,
        project_id=payload.project_id,
        action="task.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = "task"
    data["entity_id"] = task_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/requirements/{requirement_id}")
@router.get("/requirement/{requirement_id}")
def api_requirement_messages(requirement_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    _authorize_message_read(db, request, entity_type="requirement", entity_id=requirement_id, action="requirement.message.read")
    items = list_entity_messages(db, "requirement", requirement_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/requirements/{requirement_id}")
@router.post("/requirement/{requirement_id}")
def api_create_requirement_message(
    requirement_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)
):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type="requirement",
        entity_id=requirement_id,
        project_id=payload.project_id,
        action="requirement.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = "requirement"
    data["entity_id"] = requirement_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/approvals/{approval_id}")
@router.get("/approval/{approval_id}")
def api_approval_messages(approval_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    _authorize_message_read(db, request, entity_type="approval", entity_id=approval_id, action="approval.message.read")
    items = list_entity_messages(db, "approval", approval_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/approvals/{approval_id}")
@router.post("/approval/{approval_id}")
def api_create_approval_message(approval_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type="approval",
        entity_id=approval_id,
        project_id=payload.project_id,
        action="approval.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = "approval"
    data["entity_id"] = approval_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/handoffs/{handoff_id}")
@router.get("/handoff/{handoff_id}")
def api_handoff_messages(handoff_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    _authorize_message_read(db, request, entity_type="handoff", entity_id=handoff_id, action="handoff.message.read")
    items = list_entity_messages(db, "handoff", handoff_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/handoffs/{handoff_id}")
@router.post("/handoff/{handoff_id}")
def api_create_handoff_message(handoff_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type="handoff",
        entity_id=handoff_id,
        project_id=payload.project_id,
        action="handoff.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = "handoff"
    data["entity_id"] = handoff_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/{entity_type}/{entity_id}")
def api_entity_messages(
    entity_type: str,
    entity_id: str,
    message_type: str | None = None,
    sender_type: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
    request: Request = None,
    db: Session = Depends(get_db),
):
    scoped_project_id = _authorize_message_read(
        db,
        request,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=f"{entity_type}.message.read",
    )
    items = list_entity_messages(
        db,
        entity_type,
        entity_id,
        project_id=scoped_project_id,
        message_type=message_type,
    )
    if sender_type:
        items = [item for item in items if item.sender_type == sender_type]
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items[: max(1, min(limit, 500))]])


@router.post("/{entity_type}/{entity_id}")
def api_create_entity_message(
    entity_type: str, entity_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)
):
    project_id = _authorize_message_write(
        db,
        request,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=payload.project_id,
        action=f"{entity_type}.message.create",
    )
    data = payload.model_dump()
    data["entity_type"] = entity_type
    data["entity_id"] = entity_id
    data["project_id"] = project_id
    return ok(MessageRead.model_validate(create_message(db, MessageCreate(**data))).model_dump(mode="json"))


@router.get("/{entity_type}/{entity_id}/messages")
def api_entity_messages_alias(
    entity_type: str,
    entity_id: str,
    message_type: str | None = None,
    sender_type: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
    request: Request = None,
    db: Session = Depends(get_db),
):
    return api_entity_messages(
        entity_type=entity_type,
        entity_id=entity_id,
        message_type=message_type,
        sender_type=sender_type,
        project_id=project_id,
        limit=limit,
        request=request,
        db=db,
    )


@router.post("/{entity_type}/{entity_id}/messages")
def api_create_entity_message_alias(
    entity_type: str, entity_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)
):
    return api_create_entity_message(entity_type=entity_type, entity_id=entity_id, payload=payload, request=request, db=db)
