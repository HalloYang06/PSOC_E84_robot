from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.requirement import Requirement, RequirementMessage
from app.db.models.task import Task
from app.modules.audit.service import create_audit_log

from .schemas import RequirementCreate, RequirementReplyCreate, RequirementUpdate


def list_requirements(db: Session, project_ids: list[str] | None = None) -> list[Requirement]:
    stmt = (
        select(Requirement)
        .options(selectinload(Requirement.messages))
        .order_by(Requirement.updated_at.desc())
    )
    if project_ids:
        stmt = (
            stmt.outerjoin(Task, Requirement.task_id == Task.id)
            .where(
                or_(
                    Requirement.project_id.in_(project_ids),
                    Requirement.project_id.is_(None) & Task.project_id.in_(project_ids),
                )
            )
        )
    return list(db.scalars(stmt))


def get_requirement(db: Session, requirement_id: str) -> Requirement | None:
    stmt = (
        select(Requirement)
        .options(selectinload(Requirement.messages))
        .where(Requirement.id == requirement_id)
    )
    return db.scalar(stmt)


def create_requirement(
    db: Session,
    payload: RequirementCreate,
    *,
    extra_fields: dict[str, object] | None = None,
) -> Requirement:
    requirement_data = payload.model_dump(exclude={"opening_message"})
    if extra_fields:
        requirement_data.update(extra_fields)
    requirement = Requirement(**requirement_data)
    db.add(requirement)
    db.flush()

    opening_message = payload.opening_message or payload.context_summary or payload.expected_output
    if opening_message:
        db.add(
            RequirementMessage(
                requirement_id=requirement.id,
                sender_type="human" if payload.from_agent is None else "agent",
                sender_id=payload.from_agent,
                message=opening_message,
            )
        )
        requirement.response_count = 1
        requirement.last_response_at = datetime.now(timezone.utc)

    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type="human" if payload.from_agent is None else "agent",
        actor_id=payload.from_agent,
        action="requirement.created",
        resource_type="requirement",
        resource_id=requirement.id,
        after={
            "title": requirement.title,
            "requirement_type": requirement.requirement_type,
            "status": requirement.status,
            "priority": requirement.priority,
            "to_agent": requirement.to_agent,
        },
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def update_requirement(db: Session, requirement: Requirement, payload: RequirementUpdate) -> Requirement:
    before = {
        "title": requirement.title,
        "requirement_type": requirement.requirement_type,
        "status": requirement.status,
        "priority": requirement.priority,
        "to_agent": requirement.to_agent,
    }
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(requirement, key, value)
    db.add(requirement)
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type="system",
        action="requirement.updated",
        resource_type="requirement",
        resource_id=requirement.id,
        before=before,
        after={
            "title": requirement.title,
            "requirement_type": requirement.requirement_type,
            "status": requirement.status,
            "priority": requirement.priority,
            "to_agent": requirement.to_agent,
        },
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def add_requirement_reply(
    db: Session,
    requirement: Requirement,
    payload: RequirementReplyCreate,
    *,
    commit: bool = True,
) -> RequirementMessage:
    reply = RequirementMessage(
        requirement_id=requirement.id,
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        message=payload.message,
        status_after_reply=payload.status or "answered",
    )
    requirement.response_count += 1
    requirement.last_response_at = datetime.now(timezone.utc)
    requirement.status = payload.status or "answered"
    db.add_all([requirement, reply])
    db.flush()
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type=payload.sender_type,
        actor_id=payload.sender_id,
        action="requirement.reply",
        resource_type="requirement_message",
        resource_id=reply.id,
        after={
            "status": requirement.status,
            "message": payload.message,
        },
    )
    if commit:
        db.commit()
        db.refresh(reply)
    return reply


def create_requirement_collaboration_message(
    db: Session,
    requirement: Requirement,
    *,
    message_type: str,
    title: str | None,
    body: str,
    sender_type: str,
    sender_id: str | None,
    recipient_type: str | None,
    recipient_id: str | None,
    status: str,
    agent_id: str | None = None,
    dedupe_key: str | None = None,
) -> CollaborationMessage:
    message = CollaborationMessage(
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        requirement_id=requirement.id,
        agent_id=agent_id,
        dedupe_key=dedupe_key,
        message_type=message_type,
        title=title,
        body=body,
        sender_type=sender_type,
        sender_id=sender_id,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        status=status,
    )
    db.add(message)
    db.flush()
    return message
