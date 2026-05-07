from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal_for_target, resolve_task_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.approval import Approval
from app.db.session import get_db
from app.modules.audit.service import create_audit_log
from app.modules.messages.schemas import MessageCreate, MessageRead
from app.modules.messages.service import create_entity_message, list_entity_messages, resolve_message_project_id
from app.modules.read_access import (
    readable_project_ids,
    require_project_read_access,
    resolve_approval_project_id,
    resolve_task_project_id,
)
from app.modules.tasks.repo import create_task_event
from app.modules.tasks.service import get_task_or_404

from .schemas import ApprovalActionRequest, ApprovalCreate, ApprovalRead, ApprovalUpdate


router = APIRouter(prefix="/api/approvals", tags=["approvals"])

ALLOWED_APPROVAL_STATUSES = {"pending", "approved", "rejected", "cancelled", "needs_changes"}


def _approval_snapshot(approval: Approval) -> dict[str, object]:
    return jsonable_encoder(
        {
            "id": approval.id,
            "project_id": approval.project_id,
            "task_id": approval.task_id,
            "level": approval.level,
            "action": approval.action,
            "status": approval.status,
            "approver_user_id": approval.approver_user_id,
            "approved_at": approval.approved_at,
            "notes": approval.notes,
            "created_at": approval.created_at,
        }
    )


def _approval_or_404(db: Session, approval_id: str) -> Approval:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise AppError("APPROVAL_NOT_FOUND", "approval record not found", status_code=404)
    return approval


def _pending_high_risk_count(db: Session, task_id: str) -> int:
    stmt = select(Approval).where(
        Approval.task_id == task_id,
        Approval.status == "pending",
        Approval.level.in_(["H3", "H4"]),
    )
    return len(list(db.scalars(stmt)))


def _write_task_trail(
    db: Session,
    approval: Approval,
    *,
    event_type: str,
    message: str,
    actor_id: str | None,
    before: dict[str, object] | None = None,
) -> None:
    pending_high_risk_count = _pending_high_risk_count(db, approval.task_id)
    create_task_event(
        db,
        approval.task_id,
        event_type,
        message,
        {
            "approval": _approval_snapshot(approval),
            "approval_note": approval.notes,
            "before": before or {},
            "pending_high_risk_count": pending_high_risk_count,
            "gate_open": pending_high_risk_count == 0,
        },
        actor_type="human",
        actor_id=actor_id,
        commit=False,
    )


def _finalize_approval(
    approval: Approval,
    *,
    status: str,
    actor_id: str,
    level: str | None = None,
    notes: str | None = None,
) -> None:
    approval.status = status
    approval.approver_user_id = actor_id
    approval.approved_at = datetime.now(timezone.utc) if status == "approved" else None
    if level is not None:
        approval.level = level
    if notes is not None:
        approval.notes = notes


def _log_approval_mutation(
    db: Session,
    approval: Approval,
    *,
    action: str,
    actor_id: str | None,
    before: dict[str, object],
) -> None:
    create_audit_log(
        db,
        project_id=approval.project_id,
        task_id=approval.task_id,
        actor_type="human",
        actor_id=actor_id,
        action=action,
        resource_type="approval",
        resource_id=approval.id,
        before=before,
        after=_approval_snapshot(approval),
    )


def _extra_forbidden_detail(field: str, value: object) -> dict[str, object]:
    return {
        "type": "extra_forbidden",
        "loc": ["body", field],
        "msg": "Extra inputs are not permitted",
        "input": value,
    }


async def _approval_request_payload(request: Request) -> dict[str, object]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _approval_validation_response(details: list[dict[str, object]]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": details})


@router.get("")
def list_approvals(
    task_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    level: str | None = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    if task_id:
        scoped_project_ids = [resolve_task_project_id(db, task_id)]
        require_project_read_access(db, request, scoped_project_ids[0], action="approval.read")
    elif project_id:
        scoped_project_ids = [project_id]
        require_project_read_access(db, request, project_id, action="approval.read")
    else:
        scoped_project_ids = readable_project_ids(db, request)

    stmt = select(Approval).order_by(Approval.created_at.asc())
    if task_id:
        stmt = stmt.where(Approval.task_id == task_id)
    elif scoped_project_ids:
        stmt = stmt.where(Approval.project_id.in_(scoped_project_ids))
    else:
        return ok([])
    if status:
        stmt = stmt.where(Approval.status == status)
    if level:
        stmt = stmt.where(Approval.level == level)
    approvals = list(db.scalars(stmt))
    return ok([ApprovalRead.model_validate(item).model_dump(mode="json") for item in approvals])


@router.get("/{approval_id}")
def get_approval(approval_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_approval_project_id(db, approval_id), action="approval.read")
    approval = _approval_or_404(db, approval_id)
    return ok(ApprovalRead.model_validate(approval).model_dump(mode="json"))


@router.post("")
async def create_approval(payload: ApprovalCreate, request: Request, db: Session = Depends(get_db)):
    raw_payload = await _approval_request_payload(request)
    details: list[dict[str, object]] = []
    if "status" in raw_payload and str(raw_payload.get("status")).strip() != "pending":
        details.append(_extra_forbidden_detail("status", raw_payload.get("status")))
    if "approver_user_id" in raw_payload:
        details.append(_extra_forbidden_detail("approver_user_id", raw_payload.get("approver_user_id")))
    if details:
        return _approval_validation_response(details)
    principal = resolve_task_write_principal(db, request, payload.task_id, require_privileged=True, action="approval.create")
    task = get_task_or_404(db, payload.task_id)
    if payload.project_id is not None and payload.project_id != task.project_id:
        raise AppError("PROJECT_MISMATCH", "approval project does not match task project", status_code=400)

    approval = Approval(
        project_id=task.project_id,
        task_id=task.id,
        level=payload.level,
        action=payload.action,
        status="pending",
        approver_user_id=principal.user_id,
        notes=payload.notes,
    )
    db.add(approval)
    db.flush()
    _log_approval_mutation(db, approval, action="approval.create", actor_id=principal.user_id, before={})
    _write_task_trail(
        db,
        approval,
        event_type="approval_created",
        message=f"审批已发起：{approval.level} {approval.action}",
        actor_id=principal.user_id,
    )
    db.commit()
    db.refresh(approval)
    return ok(ApprovalRead.model_validate(approval).model_dump(mode="json"))


@router.patch("/{approval_id}")
async def update_approval(approval_id: str, payload: ApprovalUpdate, request: Request, db: Session = Depends(get_db)):
    raw_payload = await _approval_request_payload(request)
    details = [
        _extra_forbidden_detail(field, raw_payload.get(field))
        for field in ("status", "approver_user_id", "level", "action")
        if field in raw_payload
    ]
    if details:
        return _approval_validation_response(details)
    approval = _approval_or_404(db, approval_id)
    principal = resolve_project_write_principal_for_target(db, request, approval, require_privileged=True, action="approval.update")
    before = _approval_snapshot(approval)
    data = payload.model_dump(exclude_unset=True)

    if "level" in data or "action" in data:
        raise AppError(
            "APPROVAL_MUTATION_FORBIDDEN",
            "approval level and action are immutable after creation",
            status_code=400,
        )

    if "notes" in data:
        approval.notes = data["notes"]

    _log_approval_mutation(db, approval, action="approval.update", actor_id=principal.user_id, before=before)
    _write_task_trail(
        db,
        approval,
        event_type="approval_updated",
        message=f"审批已更新：{approval.level} {approval.action}",
        actor_id=principal.user_id,
        before=before,
    )
    db.commit()
    db.refresh(approval)
    return ok(ApprovalRead.model_validate(approval).model_dump(mode="json"))


async def _apply_action_async(
    approval_id: str,
    *,
    status: str,
    payload: ApprovalActionRequest,
    request: Request,
    db: Session,
):
    raw_payload = await _approval_request_payload(request)
    details = [
        _extra_forbidden_detail(field, raw_payload.get(field))
        for field in ("status", "level", "action")
        if field in raw_payload
    ]
    if details:
        return _approval_validation_response(details)
    approval = _approval_or_404(db, approval_id)
    principal = resolve_project_write_principal_for_target(
        db,
        request,
        approval,
        require_privileged=True,
        action=f"approval.{status}",
    )
    before = _approval_snapshot(approval)

    _finalize_approval(
        approval,
        status=status,
        actor_id=principal.user_id or principal.actor_id,
        notes=payload.notes,
    )
    db.add(approval)
    _log_approval_mutation(db, approval, action=f"approval.{status}", actor_id=principal.user_id, before=before)
    _write_task_trail(
        db,
        approval,
        event_type=f"approval_{status}",
        message=f"审批已处理：{approval.level} {approval.action} -> {status}",
        actor_id=principal.user_id,
        before=before,
    )
    db.commit()
    db.refresh(approval)
    return ok(ApprovalRead.model_validate(approval).model_dump(mode="json"))


@router.post("/{approval_id}/approve")
async def approve_approval(approval_id: str, payload: ApprovalActionRequest, request: Request, db: Session = Depends(get_db)):
    return await _apply_action_async(approval_id, status="approved", payload=payload, request=request, db=db)


@router.post("/{approval_id}/reject")
async def reject_approval(approval_id: str, payload: ApprovalActionRequest, request: Request, db: Session = Depends(get_db)):
    return await _apply_action_async(approval_id, status="rejected", payload=payload, request=request, db=db)


@router.post("/{approval_id}/request-changes")
async def approval_request_changes(
    approval_id: str,
    payload: ApprovalActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return await _apply_action_async(approval_id, status="needs_changes", payload=payload, request=request, db=db)


@router.get("/{approval_id}/messages")
def api_approval_messages(approval_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(
        db,
        request,
        resolve_approval_project_id(db, approval_id),
        action="approval.message.read",
    )
    items = list_entity_messages(db, "approval", approval_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{approval_id}/messages")
def api_create_approval_message(approval_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = resolve_message_project_id(db, "approval", approval_id, payload.project_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="approval.message.create")
    item = create_entity_message(
        db,
        "approval",
        approval_id,
        project_id=project_id,
        message_type=payload.message_type,
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        body=payload.body,
        parent_message_id=payload.parent_message_id,
        data=payload.data,
    )
    return ok(MessageRead.model_validate(item).model_dump(mode="json"))
