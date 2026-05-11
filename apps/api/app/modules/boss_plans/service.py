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
            | (ProjectThreadWorkstation.name == raw)
            | (ProjectThreadWorkstation.agent_id == raw),
        )
    )
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", f"NPC 不存在或不属于该项目：{raw}", status_code=404)
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
    return plan


def list_boss_plans(db: Session, project_id: str, *, limit: int = 30) -> list[BossPlan]:
    _project_or_404(db, project_id)
    return list(
        db.scalars(
            select(BossPlan)
            .options(selectinload(BossPlan.items))
            .where(BossPlan.project_id == project_id)
            .order_by(BossPlan.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
    )


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
    statuses = {candidate.status for candidate in plan.items}
    if statuses and statuses <= {"completed"}:
        plan.status = "completed"
    elif "in_progress" in statuses:
        plan.status = "in_progress"
    elif "blocked" in statuses or "failed" in statuses:
        plan.status = "blocked"
    elif any(status in statuses for status in {"queued", "pending_review"}):
        plan.status = "dispatched"
    db.add(plan)
    db.commit()
    return get_boss_plan_or_404(db, project_id, plan.id)
