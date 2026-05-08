from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.requirement import Requirement
from app.modules.requirements.service import (
    _seat_workstation_key,
    _seats_cross_workstation,
)

from .schemas import ReceiptCreate, ReceiptRead


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _seat_or_404(db: Session, seat_id: str) -> ProjectThreadWorkstation:
    seat = db.get(ProjectThreadWorkstation, seat_id)
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", f"seat {seat_id} not found", status_code=404)
    return seat


def _requirement_or_404(db: Session, requirement_id: str) -> Requirement:
    req = db.get(Requirement, requirement_id)
    if req is None:
        raise AppError(
            "REQUIREMENT_NOT_FOUND",
            f"requirement {requirement_id} not found",
            status_code=404,
        )
    return req


def _resolve_originator_seat(
    db: Session,
    requirement: Requirement,
) -> ProjectThreadWorkstation | None:
    """跨工位回执直返原 NPC 发起人：用 requirement.from_agent / dispatch_id 命中 sender。"""
    project_id = (requirement.project_id or "").strip()
    if not project_id:
        return None
    candidates = [
        str(requirement.from_agent or "").strip(),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return None
    stmt = select(ProjectThreadWorkstation).where(
        ProjectThreadWorkstation.project_id == project_id,
    )
    for seat in db.scalars(stmt):
        identity = {
            str(seat.id or ""),
            str(seat.config_id or ""),
            str(seat.name or ""),
            str(seat.agent_id or ""),
        }
        identity = {v for v in identity if v}
        if identity & set(candidates):
            return seat
    return None


def _build_receipt_body(payload: ReceiptCreate) -> str:
    base = (payload.body or "").strip()
    if payload.receipt_kind == "reject":
        extras: list[str] = []
        if payload.reject_reason:
            extras.append(f"原因：{payload.reject_reason}")
        if payload.suggested_seat_id:
            extras.append(f"建议改派给：{payload.suggested_seat_id}")
        if extras:
            return base + "\n\n" + "\n".join(extras) if base else "\n".join(extras)
    return base


def create_receipt(
    db: Session,
    payload: ReceiptCreate,
) -> ReceiptRead:
    requirement = _requirement_or_404(db, payload.parent_requirement_id)
    sender_seat = _seat_or_404(db, payload.sender_seat_id)

    if payload.recipient_seat_id:
        recipient_seat = _seat_or_404(db, payload.recipient_seat_id)
    else:
        recipient_seat = _resolve_originator_seat(db, requirement)

    cross = _seats_cross_workstation(sender_seat, recipient_seat) if recipient_seat else False

    extra: dict[str, Any] = {
        "receipt_kind": payload.receipt_kind,
        "parent_requirement_id": payload.parent_requirement_id,
        "sender_workstation_id": _seat_workstation_key(sender_seat) or None,
        "recipient_workstation_id": (
            _seat_workstation_key(recipient_seat) or None if recipient_seat else None
        ),
        "cross_workstation": cross,
    }
    if payload.artifacts:
        extra["artifacts"] = payload.artifacts
    if payload.receipt_kind == "reject":
        if payload.reject_reason:
            extra["reject_reason"] = payload.reject_reason
        if payload.suggested_seat_id:
            extra["suggested_seat_id"] = payload.suggested_seat_id

    title = payload.title or _default_title(payload.receipt_kind, requirement.title)

    message = CollaborationMessage(
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        requirement_id=requirement.id,
        agent_id=sender_seat.agent_id,
        message_type="agent_result",
        title=title,
        body=_build_receipt_body(payload),
        sender_type="agent",
        sender_id=sender_seat.id,
        recipient_type="thread_workstation" if recipient_seat else None,
        recipient_id=recipient_seat.id if recipient_seat else None,
        status=_status_for_kind(payload.receipt_kind),
        extra_data=extra,
    )
    db.add(message)
    db.flush()

    if payload.receipt_kind in {"done", "reject"}:
        new_req_status = "done" if payload.receipt_kind == "done" else "rejected"
        if requirement.status != new_req_status:
            requirement.status = new_req_status
            db.add(requirement)

    db.commit()
    db.refresh(message)

    return ReceiptRead(
        id=message.id,
        project_id=message.project_id,
        receipt_kind=payload.receipt_kind,
        parent_requirement_id=payload.parent_requirement_id,
        sender_seat_id=sender_seat.id,
        recipient_seat_id=recipient_seat.id if recipient_seat else None,
        cross_workstation=cross,
        title=message.title,
        body=message.body,
        extra_data=message.extra_data,
        created_at=_iso(message.created_at),
    )


def list_receipts_for_requirement(
    db: Session,
    requirement_id: str,
) -> list[ReceiptRead]:
    requirement = _requirement_or_404(db, requirement_id)
    stmt = (
        select(CollaborationMessage)
        .where(
            CollaborationMessage.requirement_id == requirement.id,
            CollaborationMessage.message_type == "agent_result",
        )
        .order_by(CollaborationMessage.created_at.asc())
    )
    rows = list(db.scalars(stmt))
    out: list[ReceiptRead] = []
    for row in rows:
        extra = row.extra_data if isinstance(row.extra_data, dict) else {}
        kind = str(extra.get("receipt_kind") or "").strip().lower()
        if kind not in {"ack", "progress", "done", "reject"}:
            continue
        out.append(
            ReceiptRead(
                id=row.id,
                project_id=row.project_id,
                receipt_kind=kind,  # type: ignore[arg-type]
                parent_requirement_id=str(extra.get("parent_requirement_id") or row.requirement_id or ""),
                sender_seat_id=row.sender_id,
                recipient_seat_id=row.recipient_id,
                cross_workstation=bool(extra.get("cross_workstation")),
                title=row.title,
                body=row.body,
                extra_data=row.extra_data,
                created_at=_iso(row.created_at),
            )
        )
    return out


def list_receipts_for_seat(
    db: Session,
    seat_id: str,
    *,
    direction: str = "incoming",
    limit: int = 50,
) -> list[ReceiptRead]:
    """direction = incoming（发给我的） / outgoing（我发的） / both"""
    seat = _seat_or_404(db, seat_id)
    stmt = select(CollaborationMessage).where(
        CollaborationMessage.message_type == "agent_result",
    )
    if direction == "incoming":
        stmt = stmt.where(CollaborationMessage.recipient_id == seat.id)
    elif direction == "outgoing":
        stmt = stmt.where(CollaborationMessage.sender_id == seat.id)
    else:
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(
                CollaborationMessage.recipient_id == seat.id,
                CollaborationMessage.sender_id == seat.id,
            )
        )
    stmt = stmt.order_by(CollaborationMessage.created_at.desc()).limit(max(1, min(limit, 200)))
    rows = list(db.scalars(stmt))
    out: list[ReceiptRead] = []
    for row in rows:
        extra = row.extra_data if isinstance(row.extra_data, dict) else {}
        kind = str(extra.get("receipt_kind") or "").strip().lower()
        if kind not in {"ack", "progress", "done", "reject"}:
            continue
        out.append(
            ReceiptRead(
                id=row.id,
                project_id=row.project_id,
                receipt_kind=kind,  # type: ignore[arg-type]
                parent_requirement_id=str(extra.get("parent_requirement_id") or row.requirement_id or ""),
                sender_seat_id=row.sender_id,
                recipient_seat_id=row.recipient_id,
                cross_workstation=bool(extra.get("cross_workstation")),
                title=row.title,
                body=row.body,
                extra_data=row.extra_data,
                created_at=_iso(row.created_at),
            )
        )
    return out


def _default_title(kind: str, req_title: str | None) -> str:
    label = {"ack": "已接收", "progress": "进度", "done": "已完成", "reject": "已拒绝"}.get(kind, kind)
    base = (req_title or "").strip() or "需求回执"
    return f"[{label}] {base}"


def _status_for_kind(kind: str) -> str:
    return {
        "ack": "acked",
        "progress": "in_progress",
        "done": "completed",
        "reject": "rejected",
    }.get(kind, "completed")


__all__ = [
    "create_receipt",
    "list_receipts_for_requirement",
    "list_receipts_for_seat",
]
