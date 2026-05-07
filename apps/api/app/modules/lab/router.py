from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import require_platform_operator_principal, resolve_human_principal, resolve_task_write_principal
from app.common.response import ok
from app.db.session import get_db
from app.modules.approvals.schemas import ApprovalRead

from .schemas import (
    LabApprovalRequestCreate,
    LabAuditRead,
    LabCheckRecordCreate,
    LabChecklistItemRead,
    LabStatusRead,
)
from .service import (
    get_lab_checklist,
    get_lab_short_chain,
    get_lab_status,
    list_lab_audit,
    list_pending_hardware_approvals,
    record_lab_check,
    request_hardware_approval,
)


router = APIRouter(prefix="/api/lab", tags=["lab"])


@router.get("/status")
def api_lab_status(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="lab.read")
    return ok(LabStatusRead.model_validate(get_lab_status(db)).model_dump(mode="json"))


@router.get("/checklist")
def api_lab_checklist(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="lab.read")
    return ok([LabChecklistItemRead.model_validate(item).model_dump(mode="json") for item in get_lab_checklist(db)])


@router.get("/high-risk")
def api_lab_high_risk(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="lab.read")
    items = list_pending_hardware_approvals(db)
    return ok([ApprovalRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/audit")
def api_lab_audit(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="lab.read")
    items = list_lab_audit(db, limit=limit)
    return ok([LabAuditRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/short-chain")
def api_lab_short_chain(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="lab.read")
    return ok(get_lab_short_chain(db))


@router.post("/checks")
def api_record_lab_check(payload: LabCheckRecordCreate, request: Request, db: Session = Depends(get_db)):
    principal = (
        resolve_task_write_principal(db, request, payload.task_id, action="lab.check.record")
        if payload.task_id
        else resolve_human_principal(db, request, allow_bootstrap=False)
    )
    return ok(
        record_lab_check(
            db,
            payload,
            actor_type="human",
            actor_id=principal.user_id,
        )
    )


@router.post("/hardware-approvals")
def api_request_hardware_approval(payload: LabApprovalRequestCreate, request: Request, db: Session = Depends(get_db)):
    principal = resolve_task_write_principal(
        db,
        request,
        payload.task_id,
        require_privileged=True,
        action="lab.hardware_approval.request",
    )
    approval = request_hardware_approval(
        db,
        payload,
        actor_type="human",
        actor_id=principal.user_id,
    )
    return ok(ApprovalRead.model_validate(approval).model_dump(mode="json"))
