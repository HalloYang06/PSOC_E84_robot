from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.response import ok
from app.db.models.requirement import Requirement
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import ReceiptCreate
from .service import create_receipt, get_receipt_seat_or_404, list_receipts_for_requirement, list_receipts_for_seat


router = APIRouter(prefix="/api/receipts", tags=["receipts"])


@router.post("")
def api_create_receipt(payload: ReceiptCreate, request: Request, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, payload.parent_requirement_id)
    project_id = (requirement.project_id if requirement else "") or ""
    if project_id:
        require_project_read_access(db, request, project_id, action="receipts.write")
    return ok(create_receipt(db, payload).model_dump())


@router.get("/by-requirement/{requirement_id}")
def api_list_receipts_for_requirement(
    requirement_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    requirement = db.get(Requirement, requirement_id)
    if requirement is not None and requirement.project_id:
        require_project_read_access(db, request, requirement.project_id, action="receipts.read")
    return ok([r.model_dump() for r in list_receipts_for_requirement(db, requirement_id)])


@router.get("/by-seat/{seat_id}")
def api_list_receipts_for_seat(
    seat_id: str,
    request: Request,
    project_id: str | None = None,
    direction: str = Query("incoming", pattern="^(incoming|outgoing|both)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    seat = get_receipt_seat_or_404(db, seat_id, project_id=project_id)
    if seat.project_id:
        require_project_read_access(db, request, seat.project_id, action="receipts.read")
    return ok([
        r.model_dump()
        for r in list_receipts_for_seat(db, seat_id, project_id=project_id, direction=direction, limit=limit)
    ])
