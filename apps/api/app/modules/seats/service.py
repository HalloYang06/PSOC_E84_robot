from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.requirement import Requirement
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent

INBOX_STATUSES = ("waiting_response", "queued", "blocked", "pending_review", "routed", "in_progress", "answered")
TODO_STATUSES = ("draft", "ready", "queued", "running", "in_progress", "review", "reviewing", "blocked")


def get_seat_or_404(db: Session, seat_id: str, *, project_id: str | None = None) -> ProjectThreadWorkstation:
    seat = db.get(ProjectThreadWorkstation, seat_id)
    if seat is not None and project_id and seat.project_id != project_id:
        seat = None
    if seat is None:
        cleaned = str(seat_id or "").strip()
        if cleaned:
            stmt = select(ProjectThreadWorkstation).where(
                (ProjectThreadWorkstation.id == cleaned)
                | (ProjectThreadWorkstation.config_id == cleaned)
                | (ProjectThreadWorkstation.name == cleaned)
            )
            if project_id:
                stmt = stmt.where(ProjectThreadWorkstation.project_id == project_id)
            seat = db.scalars(stmt).first()
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", "formal seat not found", status_code=404)
    return seat


def _seat_identity_values(seat: ProjectThreadWorkstation) -> set[str]:
    values = {
        str(seat.id or ""),
        str(seat.config_id or ""),
    }
    return {v.strip() for v in values if v and v.strip()}


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _list_inbox(db: Session, seat: ProjectThreadWorkstation, *, limit: int) -> list[dict[str, object]]:
    """需求队列：以 seat 为收件人 + 还未关闭的 requirement。
    匹配 target_seat_id / to_agent 命中 seat 的多个身份。"""
    if not seat.project_id:
        return []
    candidates = list(_seat_identity_values(seat))
    if not candidates:
        return []
    stmt = (
        select(Requirement)
        .where(
            Requirement.project_id == seat.project_id,
            Requirement.status.in_(INBOX_STATUSES),
            or_(
                Requirement.target_seat_id.in_(candidates),
                Requirement.to_agent.in_(candidates),
            ),
        )
        .order_by(Requirement.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = list(db.scalars(stmt))
    return [_requirement_summary(r) for r in rows]


def _list_my_needs(db: Session, seat: ProjectThreadWorkstation, *, limit: int) -> list[dict[str, object]]:
    """我的需求：这个 NPC 自己提出、等待别人满足的 Need。
    这是新架构里的 requester queue；旧 requirement_inbox 继续表示别人指向我的需求。"""
    if not seat.project_id:
        return []
    candidates = list(_seat_identity_values(seat))
    if not candidates:
        return []
    stmt = (
        select(Requirement)
        .where(
            Requirement.project_id == seat.project_id,
            Requirement.status.in_(INBOX_STATUSES),
            Requirement.from_agent.in_(candidates),
        )
        .order_by(Requirement.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = list(db.scalars(stmt))
    return [_requirement_summary(r) for r in rows]


def _requirement_summary(r: Requirement) -> dict[str, object]:
    return {
        "id": r.id,
        "title": r.title,
        "status": r.status,
        "priority": r.priority,
        "requirement_type": r.requirement_type,
        "module": r.module,
        "from_agent": r.from_agent,
        "to_agent": r.to_agent,
        "target_seat_id": r.target_seat_id,
        "trigger_kind": r.trigger_kind,
        "context_summary": r.context_summary,
        "expected_output": r.expected_output,
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
        "last_response_at": _iso(r.last_response_at),
        "response_count": r.response_count,
    }


def _list_todo(db: Session, seat: ProjectThreadWorkstation, *, limit: int) -> list[dict[str, object]]:
    """任务队列：assignee_agent_id = seat.agent_id 的未结 task（兼容当前数据模型；
    蓝图里"assignee_seat_id"留待后续迁移加列）。"""
    if not seat.project_id:
        return []
    candidates = _seat_identity_values(seat)
    conditions = []
    if seat.agent_id:
        conditions.append(Task.assignee_agent_id == seat.agent_id)
    if candidates:
        linked_task_ids = [
            str(event.task_id)
            for event in db.scalars(
                select(TaskEvent).where(TaskEvent.event_type == "created_from_need")
            )
            if isinstance(event.data, dict)
            and str(event.data.get("assignee_seat_id") or "").strip() in candidates
        ]
        if linked_task_ids:
            conditions.append(Task.id.in_(linked_task_ids))
    if not conditions:
        return []
    stmt = (
        select(Task)
        .where(
            Task.project_id == seat.project_id,
            Task.status.in_(TODO_STATUSES),
            or_(*conditions),
        )
        .order_by(Task.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = list(db.scalars(stmt))
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "module": t.module,
            "branch": t.branch,
            "due_at": _iso(t.due_at),
            "assignee_agent_id": t.assignee_agent_id,
            "created_at": _iso(t.created_at),
            "updated_at": _iso(t.updated_at),
        }
        for t in rows
    ]


def _seat_summary(seat: ProjectThreadWorkstation) -> dict[str, object]:
    return {
        "id": seat.id,
        "config_id": seat.config_id,
        "name": seat.name,
        "agent_id": seat.agent_id,
        "project_id": seat.project_id,
        "workstation_id": seat.workstation_id,
        "computer_node_id": seat.computer_node_id,
        "ai_provider_id": seat.ai_provider_id,
        "status": seat.status,
    }


def get_seat_queues(db: Session, seat_id: str, *, project_id: str | None = None, limit: int = 50) -> dict[str, object]:
    seat = get_seat_or_404(db, seat_id, project_id=project_id)
    inbox = _list_inbox(db, seat, limit=limit)
    my_needs = _list_my_needs(db, seat, limit=limit)
    todo = _list_todo(db, seat, limit=limit)
    return {
        "seat": _seat_summary(seat),
        "my_needs": {
            "items": my_needs,
            "count": len(my_needs),
            "statuses_included": list(INBOX_STATUSES),
        },
        "my_tasks": {
            "items": todo,
            "count": len(todo),
            "statuses_included": list(TODO_STATUSES),
        },
        "requirement_inbox": {
            "items": inbox,
            "count": len(inbox),
            "statuses_included": list(INBOX_STATUSES),
        },
        "task_todo": {
            "items": todo,
            "count": len(todo),
            "statuses_included": list(TODO_STATUSES),
        },
    }


__all__ = ["get_seat_or_404", "get_seat_queues"]
