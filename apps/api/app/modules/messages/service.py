from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.handoff import Handoff
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.requirement import Requirement
from app.db.models.task import Task

from .schemas import ALLOWED_MESSAGE_TYPES, MessageCreate


def _resolve_project_id(db: Session, entity_type: str, entity_id: str, project_id: str | None) -> str | None:
    if project_id:
        return project_id
    if entity_type == "project":
        return entity_id
    if entity_type == "task":
        item = db.get(Task, entity_id)
        return item.project_id if item else None
    if entity_type == "requirement":
        item = db.get(Requirement, entity_id)
        return item.project_id if item else None
    if entity_type == "approval":
        item = db.get(Approval, entity_id)
        return item.project_id if item else None
    if entity_type == "handoff":
        item = db.get(Handoff, entity_id)
        return item.project_id if item else None
    return None


def resolve_message_project_id(db: Session, entity_type: str, entity_id: str, project_id: str | None = None) -> str:
    resolved = _resolve_project_id(db, entity_type, entity_id, project_id)
    if resolved is not None:
        return resolved
    _ensure_entity_exists(db, entity_type, entity_id)
    raise AppError("ENTITY_NOT_FOUND", "message entity not found", status_code=404)


def _ensure_entity_exists(db: Session, entity_type: str, entity_id: str) -> None:
    if entity_type == "project":
        exists = db.get(Project, entity_id)
    elif entity_type == "task":
        exists = db.get(Task, entity_id)
    elif entity_type == "requirement":
        exists = db.get(Requirement, entity_id)
    elif entity_type == "approval":
        exists = db.get(Approval, entity_id)
    elif entity_type == "handoff":
        exists = db.get(Handoff, entity_id)
    else:
        raise AppError("INVALID_ENTITY_TYPE", "unsupported message entity type", status_code=400)
    if exists is None:
        raise AppError("ENTITY_NOT_FOUND", "message entity not found", status_code=404)


def list_messages(
    db: Session,
    *,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    message_type: str | None = None,
    sender_type: str | None = None,
    limit: int = 100,
):
    stmt = select(Message).order_by(Message.created_at.asc())
    if project_id:
        stmt = stmt.where(Message.project_id == project_id)
    if entity_type:
        stmt = stmt.where(Message.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Message.entity_id == entity_id)
    if message_type:
        stmt = stmt.where(Message.message_type == message_type)
    if sender_type:
        stmt = stmt.where(Message.sender_type == sender_type)
    return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))


def create_message(db: Session, payload: MessageCreate) -> Message:
    if not payload.entity_type or not payload.entity_id:
        raise AppError("INVALID_MESSAGE_TARGET", "message entity target is required", status_code=400)
    if payload.message_type not in ALLOWED_MESSAGE_TYPES:
        raise AppError("INVALID_MESSAGE_TYPE", "unsupported message type", status_code=400)
    _ensure_entity_exists(db, payload.entity_type, payload.entity_id)
    message = Message(
        project_id=_resolve_project_id(db, payload.entity_type, payload.entity_id, payload.project_id),
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        message_type=payload.message_type,
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        body=payload.body,
        parent_message_id=payload.parent_message_id,
        data=payload.data,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_entity_messages(db: Session, entity_type: str, entity_id: str, *, project_id: str | None = None, message_type: str | None = None):
    return list_messages(
        db,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        message_type=message_type,
    )


def create_entity_message(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    project_id: str | None = None,
    message_type: str = "comment_message",
    sender_type: str = "system",
    sender_id: str | None = None,
    body: str,
    parent_message_id: str | None = None,
    data: dict | None = None,
):
    return create_message(
        db,
        MessageCreate(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            message_type=message_type,
            sender_type=sender_type,
            sender_id=sender_id,
            body=body,
            parent_message_id=parent_message_id,
            data=data or {},
        ),
    )
