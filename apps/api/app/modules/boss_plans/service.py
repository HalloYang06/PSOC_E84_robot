from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.common.errors import AppError
from app.db.models.boss_plan import BossPlan, BossPlanItem
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.modules.knowledge.service import normalize_repo_relative_path

from .schemas import BossPlanCreate, BossPlanItemUpdate


VALID_PLAN_STATUSES = {"draft", "sent_to_boss", "dispatching", "dispatched", "in_progress", "blocked", "completed", "cancelled"}
VALID_ITEM_STATUSES = {"planned", "queued", "pending_review", "in_progress", "blocked", "completed", "failed", "cancelled"}

MESSAGE_STATUS_TO_ITEM_STATUS = {
    "acked": "in_progress",
    "cancelled": "cancelled",
    "completed": "completed",
    "done": "completed",
    "failed": "failed",
    "in_progress": "in_progress",
    "open": "queued",
    "pending": "queued",
    "pending_review": "pending_review",
    "queued": "queued",
    "rejected": "failed",
}


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    return project


def _resolve_seat_id(db: Session, project_id: str, seat_id: str | None) -> str | None:
    raw = str(seat_id or "").strip()
    if not raw:
        return None
    seat = db.scalar(
        select(ProjectThreadWorkstation).where(
            ProjectThreadWorkstation.project_id == project_id,
            (ProjectThreadWorkstation.id == raw)
            | (ProjectThreadWorkstation.config_id == raw)
        )
    )
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", f"NPC 不存在或不属于该项目正式 seat：{raw}", status_code=404)
    return seat.id


def _clean_status(value: str | None, allowed: set[str], default: str) -> str:
    status = str(value or default).strip().lower() or default
    if status not in allowed:
        raise AppError("BAD_STATUS", f"status must be one of {', '.join(sorted(allowed))}", status_code=422)
    return status


def _clean_paths(paths: list[str] | None) -> list[str] | None:
    cleaned: list[str] = []
    for path in paths or []:
        value = normalize_repo_relative_path(path, required=False)
        if value:
            cleaned.append(value)
    return cleaned or None


def get_boss_plan_or_404(db: Session, project_id: str, plan_id: str) -> BossPlan:
    plan = db.scalar(
        select(BossPlan)
        .options(selectinload(BossPlan.items))
        .where(BossPlan.project_id == project_id, BossPlan.id == plan_id)
    )
    if plan is None:
        raise AppError("BOSS_PLAN_NOT_FOUND", "Boss plan not found", status_code=404)
    return sync_boss_plan_status_from_messages(db, plan)


def list_boss_plans(db: Session, project_id: str, *, limit: int = 30) -> list[BossPlan]:
    _project_or_404(db, project_id)
    plans = list(
        db.scalars(
            select(BossPlan)
            .options(selectinload(BossPlan.items))
            .where(BossPlan.project_id == project_id)
            .order_by(BossPlan.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
    )
    return [sync_boss_plan_status_from_messages(db, plan) for plan in plans]


def _plan_status_from_items(items: list[BossPlanItem]) -> str:
    statuses = {item.status for item in items}
    if not statuses:
        return "draft"
    if statuses <= {"completed"}:
        return "completed"
    if statuses & {"blocked", "failed"}:
        return "blocked"
    if "in_progress" in statuses:
        return "in_progress"
    if statuses & {"queued", "pending_review"}:
        return "dispatched"
    if statuses <= {"cancelled"}:
        return "cancelled"
    return "dispatching"


def sync_boss_plan_status_from_messages(db: Session, plan: BossPlan) -> BossPlan:
    dispatch_ids = [item.dispatch_message_id for item in plan.items if item.dispatch_message_id]
    if not dispatch_ids:
        return plan

    messages = {
        message.id: message
        for message in db.scalars(
            select(CollaborationMessage).where(
                CollaborationMessage.project_id == plan.project_id,
                CollaborationMessage.id.in_(dispatch_ids),
            )
        )
    }
    receipts_by_source_id = {
        str(message.extra_data.get("source_message_id")): message
        for message in db.scalars(
            select(CollaborationMessage).where(
                CollaborationMessage.project_id == plan.project_id,
                CollaborationMessage.message_type.in_(["agent_result", "requirement_final_reply", "runner_result"]),
                CollaborationMessage.status.in_(["completed", "done", "failed", "rejected"]),
            )
        )
        if isinstance(message.extra_data, dict)
        and str(message.extra_data.get("source_message_id") or "") in dispatch_ids
    }
    fallback_receipts = list(
        db.scalars(
            select(CollaborationMessage).where(
                CollaborationMessage.project_id == plan.project_id,
                CollaborationMessage.message_type.in_(["agent_result", "requirement_final_reply", "runner_result"]),
                CollaborationMessage.status.in_(["completed", "done", "failed", "rejected"]),
            )
        )
    )
    changed = False
    for item in plan.items:
        if not item.dispatch_message_id:
            continue
        receipt = receipts_by_source_id.get(item.dispatch_message_id)
        if receipt is None:
            dispatch_id = str(item.dispatch_message_id)
            for candidate in fallback_receipts:
                if candidate.id == dispatch_id:
                    continue
                if candidate.extra_data and isinstance(candidate.extra_data, dict):
                    source_id = str(candidate.extra_data.get("source_message_id") or "")
                    if source_id in dispatch_ids and source_id != dispatch_id:
                        continue
                text = f"{candidate.title or ''}\n{candidate.body or ''}"
                if dispatch_id not in text:
                    continue
                receipt = candidate
                break
        if receipt is not None:
            target_status = "completed" if str(receipt.status or "").strip().lower() in {"completed", "done"} else "failed"
            if item.status != target_status:
                item.status = target_status
                changed = True
            if item.receipt_message_id != receipt.id:
                item.receipt_message_id = receipt.id
                changed = True
            continue
        message = messages.get(item.dispatch_message_id)
        if message is None:
            continue
        next_status = MESSAGE_STATUS_TO_ITEM_STATUS.get(str(message.status or "").strip().lower())
        if next_status and next_status != item.status:
            item.status = next_status
            changed = True
    next_plan_status = _plan_status_from_items(plan.items)
    if next_plan_status != plan.status:
        plan.status = next_plan_status
        changed = True
    if changed:
        db.add(plan)
        db.commit()
        db.refresh(plan)
    return plan


def sync_project_boss_plans_from_messages(db: Session, project_id: str) -> int:
    plans = list(
        db.scalars(
            select(BossPlan)
            .options(selectinload(BossPlan.items))
            .where(BossPlan.project_id == project_id)
            .order_by(BossPlan.updated_at.desc())
        )
    )
    for plan in plans:
        sync_boss_plan_status_from_messages(db, plan)
    return len(plans)


def create_boss_plan(db: Session, project_id: str, payload: BossPlanCreate) -> BossPlan:
    _project_or_404(db, project_id)
    boss_seat_id = _resolve_seat_id(db, project_id, payload.boss_seat_id)
    source_message_id = str(payload.source_message_id or "").strip() or None
    if source_message_id:
        message = db.get(CollaborationMessage, source_message_id)
        if message is None or message.project_id != project_id:
            raise AppError("MESSAGE_NOT_FOUND", "source_message_id 不属于该项目", status_code=404)
    contract_path = normalize_repo_relative_path(payload.contract_path, required=False)
    plan = BossPlan(
        project_id=project_id,
        boss_seat_id=boss_seat_id,
        goal=payload.goal.strip(),
        title=(payload.title or "").strip() or None,
        status=_clean_status(payload.status, VALID_PLAN_STATUSES, "draft"),
        source_message_id=source_message_id,
        summary=payload.summary,
        contract_path=contract_path,
        extra_data=payload.metadata or None,
    )
    for index, item in enumerate(payload.items):
        target_seat_id = _resolve_seat_id(db, project_id, item.target_seat_id)
        dispatch_message_id = str(item.dispatch_message_id or "").strip() or None
        if dispatch_message_id:
            message = db.get(CollaborationMessage, dispatch_message_id)
            if message is None or message.project_id != project_id:
                raise AppError("MESSAGE_NOT_FOUND", "dispatch_message_id 不属于该项目", status_code=404)
        plan.items.append(
            BossPlanItem(
                project_id=project_id,
                role=item.role.strip(),
                target_seat_id=target_seat_id,
                target_name=(item.target_name or "").strip() or None,
                title=item.title.strip(),
                body=item.body.strip(),
                status=_clean_status(item.status, VALID_ITEM_STATUSES, "planned"),
                dispatch_message_id=dispatch_message_id,
                receipt_message_id=(str(item.receipt_message_id or "").strip() or None),
                sort_order=item.sort_order if item.sort_order else index,
                skills=item.skills or None,
                knowledge_paths=_clean_paths(item.knowledge_paths),
                acceptance=item.acceptance,
                extra_data=item.metadata or None,
            )
        )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return get_boss_plan_or_404(db, project_id, plan.id)


def update_boss_plan_item(db: Session, project_id: str, plan_id: str, item_id: str, payload: BossPlanItemUpdate) -> BossPlan:
    plan = get_boss_plan_or_404(db, project_id, plan_id)
    item = next((candidate for candidate in plan.items if candidate.id == item_id), None)
    if item is None:
        raise AppError("BOSS_PLAN_ITEM_NOT_FOUND", "Boss plan item not found", status_code=404)
    if payload.status is not None:
        item.status = _clean_status(payload.status, VALID_ITEM_STATUSES, item.status)
    if payload.dispatch_message_id is not None:
        message_id = payload.dispatch_message_id.strip() or None
        if message_id:
            message = db.get(CollaborationMessage, message_id)
            if message is None or message.project_id != project_id:
                raise AppError("MESSAGE_NOT_FOUND", "dispatch_message_id 不属于该项目", status_code=404)
        item.dispatch_message_id = message_id
    if payload.receipt_message_id is not None:
        item.receipt_message_id = payload.receipt_message_id.strip() or None
    if payload.metadata is not None:
        item.extra_data = payload.metadata
    plan.status = _plan_status_from_items(plan.items)
    db.add(plan)
    db.commit()
    return get_boss_plan_or_404(db, project_id, plan.id)
