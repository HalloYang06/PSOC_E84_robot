from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import (
    WorkstationCreate,
    WorkstationLeadSet,
    WorkstationSeatAssignRequest,
    WorkstationUpdate,
)
from .service import (
    assign_seats_to_workstation,
    create_workstation,
    delete_workstation,
    list_workstation_seats,
    list_workstations,
    set_workstation_lead,
    update_workstation,
)


router = APIRouter(prefix="/api/projects/{project_id}/workstations", tags=["workstations"])


@router.get("")
def api_list_workstations(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="workstations.read")
    return ok([row.model_dump() for row in list_workstations(db, project_id)])


@router.post("")
def api_create_workstation(
    project_id: str,
    payload: WorkstationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.write")
    return ok(create_workstation(db, project_id, payload).model_dump())


@router.patch("/{workstation_id}")
def api_update_workstation(
    project_id: str,
    workstation_id: str,
    payload: WorkstationUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.write")
    return ok(update_workstation(db, project_id, workstation_id, payload).model_dump())


@router.delete("/{workstation_id}")
def api_delete_workstation(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.write")
    delete_workstation(db, project_id, workstation_id)
    return ok({"deleted": True, "id": workstation_id})


@router.post("/{workstation_id}/lead")
def api_set_workstation_lead(
    project_id: str,
    workstation_id: str,
    payload: WorkstationLeadSet,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.write")
    return ok(set_workstation_lead(db, project_id, workstation_id, payload).model_dump())


@router.post("/{workstation_id}/seats")
def api_assign_seats(
    project_id: str,
    workstation_id: str,
    payload: WorkstationSeatAssignRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.write")
    return ok(assign_seats_to_workstation(db, project_id, workstation_id, payload).model_dump())


@router.get("/{workstation_id}/seats")
def api_list_seats(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="workstations.read")
    return ok(list_workstation_seats(db, project_id, workstation_id))
