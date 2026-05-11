from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .service import get_seat_or_404, get_seat_queues


router = APIRouter(prefix="/api/seats", tags=["seats"])


@router.get("/{seat_id}/queues")
def api_seat_queues(
    seat_id: str,
    request: Request,
    project_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    seat = get_seat_or_404(db, seat_id, project_id=project_id)
    require_project_read_access(db, request, seat.project_id or "", action="seats.queues.read")
    return ok(get_seat_queues(db, seat_id, project_id=seat.project_id, limit=limit))
