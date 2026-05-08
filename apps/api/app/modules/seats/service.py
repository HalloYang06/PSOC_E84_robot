from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.requirement import Requirement
from app.db.models.task import Task

INBOX_STATUSES = ("waiting_response", "queued", "blocked", "pending_review", "routed", "in_progress", "answered")
TODO_STATUSES = ("draft", "ready", "in_progress", "review", "blocked")


def get_seat_or_404(db: Session, seat_id: str) -> ProjectThreadWorkstation:
    seat = db.get(ProjectThreadWorkstation, seat_id)
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", "seat not found", status_code=404)
    return seat


def _seat_identity_values(seat: ProjectThreadWorkstation) -> set[str]:
    extra = dict(seat.extra_data or {})
    values = {
        str(seat.id or ""),
        str(seat.config_id or ""),
        str(seat.name or ""),
        str(seat.agent_id or ""),
        str(extra.get("source_workstation_id") or ""),
        str(extra.get("source_thread_id") or ""),
        str(extra.get("bound_thread_id") or ""),
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
    return [
        {
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
        for r in rows
    ]


def _list_todo(db: Session, seat: ProjectThreadWorkstation, *, limit: int) -> list[dict[str, object]]:
    """任务队列：assignee_agent_id = seat.agent_id 的未结 task（兼容当前数据模型；
    蓝图里"assignee_seat_id"留待后续迁移加列）。"""
    if not seat.project_id:
        return []
    if not seat.agent_id:
        return []
    stmt = (
        select(Task)
        .where(
            Task.project_id == seat.project_id,
            Task.assignee_agent_id == seat.agent_id,
            Task.status.in_(TODO_STATUSES),
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


def get_seat_queues(db: Session, seat_id: str, *, limit: int = 50) -> dict[str, object]:
    seat = get_seat_or_404(db, seat_id)
    inbox = _list_inbox(db, seat, limit=limit)
    todo = _list_todo(db, seat, limit=limit)
    return {
        "seat": _seat_summary(seat),
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
