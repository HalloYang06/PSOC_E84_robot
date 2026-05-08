from __future__ import annotations

import re
import secrets
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectThreadWorkstation, ProjectWorkstation

from .schemas import (
    WorkstationCreate,
    WorkstationLeadSet,
    WorkstationRead,
    WorkstationSeatAssignRequest,
    WorkstationUpdate,
)


def _slugify(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9一-鿿]+", "-", str(value or "").strip().lower()).strip("-")
    return text


def _ensure_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    return project


def _seat_count_map(db: Session, project_id: str) -> dict[str, int]:
    stmt = (
        select(ProjectThreadWorkstation.workstation_id, func.count(ProjectThreadWorkstation.id))
        .where(ProjectThreadWorkstation.project_id == project_id)
        .group_by(ProjectThreadWorkstation.workstation_id)
    )
    return {str(ws_id or ""): int(cnt or 0) for ws_id, cnt in db.execute(stmt).all()}


def _to_read(row: ProjectWorkstation, *, seat_count: int) -> WorkstationRead:
    return WorkstationRead(
        id=row.id,
        project_id=row.project_id,
        config_id=row.config_id,
        name=row.name,
        description=row.description,
        lead_seat_id=row.lead_seat_id,
        review_policy=row.review_policy,
        sort_order=row.sort_order,
        seat_count=seat_count,
        extra_data=row.extra_data,
    )


def _next_sort_order(db: Session, project_id: str) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(ProjectWorkstation.sort_order), 0)).where(
            ProjectWorkstation.project_id == project_id
        )
    )
    return int(current or 0) + 1


def _generate_config_id(db: Session, project_id: str, hint: str | None) -> str:
    base = _slugify(hint) or "ws"
    base = base[:48]
    candidate = base
    suffix = 0
    while True:
        if suffix:
            candidate = f"{base}-{suffix}"
        existing = db.scalar(
            select(ProjectWorkstation.id).where(
                ProjectWorkstation.project_id == project_id,
                ProjectWorkstation.config_id == candidate,
            )
        )
        if existing is None:
            return candidate
        suffix += 1
        if suffix > 30:
            return f"{base}-{secrets.token_hex(3)}"


def list_workstations(db: Session, project_id: str) -> list[WorkstationRead]:
    _ensure_project(db, project_id)
    stmt = (
        select(ProjectWorkstation)
        .where(ProjectWorkstation.project_id == project_id)
        .order_by(ProjectWorkstation.sort_order, ProjectWorkstation.created_at)
    )
    rows = list(db.scalars(stmt))
    counts = _seat_count_map(db, project_id)
    return [_to_read(row, seat_count=counts.get(row.id, 0)) for row in rows]


def get_workstation_or_404(db: Session, project_id: str, workstation_id: str) -> ProjectWorkstation:
    row = db.scalar(
        select(ProjectWorkstation).where(
            ProjectWorkstation.project_id == project_id,
            ProjectWorkstation.id == workstation_id,
        )
    )
    if row is None:
        raise AppError("WORKSTATION_NOT_FOUND", "workstation not found", status_code=404)
    return row


def create_workstation(db: Session, project_id: str, payload: WorkstationCreate) -> WorkstationRead:
    _ensure_project(db, project_id)
    config_id = (payload.config_id or "").strip() or _generate_config_id(db, project_id, payload.name)
    if db.scalar(
        select(ProjectWorkstation.id).where(
            ProjectWorkstation.project_id == project_id,
            ProjectWorkstation.config_id == config_id,
        )
    ):
        raise AppError(
            "WORKSTATION_CONFLICT",
            f"workstation config_id {config_id!r} already exists",
            status_code=409,
        )
    if payload.lead_seat_id:
        _validate_seat_belongs_to_project(db, project_id, payload.lead_seat_id)
    sort_order = payload.sort_order if payload.sort_order is not None else _next_sort_order(db, project_id)
    row = ProjectWorkstation(
        project_id=project_id,
        config_id=config_id,
        name=payload.name.strip(),
        description=payload.description,
        lead_seat_id=payload.lead_seat_id,
        review_policy=payload.review_policy,
        sort_order=sort_order,
        extra_data=payload.extra_data,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(row, seat_count=0)


def update_workstation(
    db: Session,
    project_id: str,
    workstation_id: str,
    payload: WorkstationUpdate,
) -> WorkstationRead:
    row = get_workstation_or_404(db, project_id, workstation_id)
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description
    if payload.lead_seat_id is not None:
        if payload.lead_seat_id:
            _validate_seat_belongs_to_project(db, project_id, payload.lead_seat_id)
        row.lead_seat_id = payload.lead_seat_id or None
    if payload.review_policy is not None:
        row.review_policy = payload.review_policy or None
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.extra_data is not None:
        row.extra_data = payload.extra_data
    db.add(row)
    db.commit()
    db.refresh(row)
    counts = _seat_count_map(db, project_id)
    return _to_read(row, seat_count=counts.get(row.id, 0))


def delete_workstation(db: Session, project_id: str, workstation_id: str) -> None:
    row = get_workstation_or_404(db, project_id, workstation_id)
    seat_count = db.scalar(
        select(func.count(ProjectThreadWorkstation.id)).where(
            ProjectThreadWorkstation.project_id == project_id,
            ProjectThreadWorkstation.workstation_id == workstation_id,
        )
    )
    if int(seat_count or 0) > 0:
        raise AppError(
            "WORKSTATION_HAS_SEATS",
            "workstation still has seats; reassign seats before deleting",
            status_code=409,
            details={"seat_count": int(seat_count or 0)},
        )
    db.delete(row)
    db.commit()


def set_workstation_lead(
    db: Session,
    project_id: str,
    workstation_id: str,
    payload: WorkstationLeadSet,
) -> WorkstationRead:
    row = get_workstation_or_404(db, project_id, workstation_id)
    seat_id = (payload.seat_id or "").strip() or None
    if seat_id:
        seat = _validate_seat_belongs_to_project(db, project_id, seat_id)
        if seat.workstation_id and seat.workstation_id != row.id:
            raise AppError(
                "WORKSTATION_LEAD_FOREIGN_SEAT",
                "lead seat must belong to this workstation",
                status_code=409,
                details={"seat_workstation_id": seat.workstation_id, "workstation_id": row.id},
            )
    row.lead_seat_id = seat_id
    db.add(row)
    db.commit()
    db.refresh(row)
    counts = _seat_count_map(db, project_id)
    return _to_read(row, seat_count=counts.get(row.id, 0))


def assign_seats_to_workstation(
    db: Session,
    project_id: str,
    workstation_id: str,
    payload: WorkstationSeatAssignRequest,
) -> WorkstationRead:
    row = get_workstation_or_404(db, project_id, workstation_id)
    target_ids = [str(sid).strip() for sid in (payload.seat_ids or []) if str(sid).strip()]
    if not target_ids:
        return _to_read(row, seat_count=_seat_count_map(db, project_id).get(row.id, 0))
    seats = list(
        db.scalars(
            select(ProjectThreadWorkstation).where(
                ProjectThreadWorkstation.project_id == project_id,
                ProjectThreadWorkstation.id.in_(target_ids),
            )
        )
    )
    found_ids = {seat.id for seat in seats}
    missing = [sid for sid in target_ids if sid not in found_ids]
    if missing:
        raise AppError(
            "SEATS_NOT_FOUND",
            f"some seats are not in this project: {missing}",
            status_code=404,
            details={"missing_seat_ids": missing},
        )
    for seat in seats:
        seat.workstation_id = row.id
        db.add(seat)
    db.commit()
    db.refresh(row)
    counts = _seat_count_map(db, project_id)
    return _to_read(row, seat_count=counts.get(row.id, 0))


def list_workstation_seats(db: Session, project_id: str, workstation_id: str) -> list[dict[str, object]]:
    get_workstation_or_404(db, project_id, workstation_id)
    seats = list(
        db.scalars(
            select(ProjectThreadWorkstation)
            .where(
                ProjectThreadWorkstation.project_id == project_id,
                ProjectThreadWorkstation.workstation_id == workstation_id,
            )
            .order_by(ProjectThreadWorkstation.sort_order, ProjectThreadWorkstation.created_at)
        )
    )
    return [
        {
            "id": seat.id,
            "config_id": seat.config_id,
            "name": seat.name,
            "agent_id": seat.agent_id,
            "computer_node_id": seat.computer_node_id,
            "ai_provider_id": seat.ai_provider_id,
            "status": seat.status,
            "description": seat.description,
        }
        for seat in seats
    ]


def _validate_seat_belongs_to_project(
    db: Session,
    project_id: str,
    seat_id: str,
) -> ProjectThreadWorkstation:
    seat = db.scalar(
        select(ProjectThreadWorkstation).where(
            ProjectThreadWorkstation.project_id == project_id,
            ProjectThreadWorkstation.id == seat_id,
        )
    )
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", "seat not found in this project", status_code=404)
    return seat


__all__ = [
    "list_workstations",
    "get_workstation_or_404",
    "create_workstation",
    "update_workstation",
    "delete_workstation",
    "set_workstation_lead",
    "assign_seats_to_workstation",
    "list_workstation_seats",
]
