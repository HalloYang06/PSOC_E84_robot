from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import append_audit_log
from app.common.errors import AppError
from app.db.models.approval import Approval
from app.db.models.audit_log import AuditLog
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.modules.tasks.schemas import TaskTransitionCreate
from app.modules.tasks.service import get_task_or_404, transition_task_status

from .schemas import LabApprovalRequestCreate, LabCheckRecordCreate


ALLOWED_HARDWARE_APPROVAL_LEVELS = {"H3", "H4"}


def get_lab_status(db: Session) -> dict[str, int]:
    pending_human_approvals = db.scalar(
        select(func.count(Approval.id)).where(Approval.status == "pending")
    ) or 0
    high_risk_approvals = db.scalar(
        select(func.count(Approval.id)).where(Approval.status == "pending", Approval.level.in_(["H3", "H4"]))
    ) or 0
    online_runners = db.scalar(select(func.count(Runner.id)).where(Runner.status == "online")) or 0
    blocked_tasks = db.scalar(select(func.count(Task.id)).where(Task.status.in_(["blocked", "failed"]))) or 0
    active_tasks = db.scalar(
        select(func.count(Task.id)).where(Task.status.in_(["ready", "running", "reviewing", "testing"]))
    ) or 0
    recent_audit_count = db.scalar(select(func.count(AuditLog.id))) or 0
    return {
        "pending_human_approvals": int(pending_human_approvals),
        "high_risk_approvals": int(high_risk_approvals),
        "online_runners": int(online_runners),
        "blocked_tasks": int(blocked_tasks),
        "active_tasks": int(active_tasks),
        "recent_audit_count": int(recent_audit_count),
    }


def get_lab_checklist(db: Session) -> list[dict]:
    status = get_lab_status(db)
    return [
        {
            "key": "power",
            "title": "电源与执行节点",
            "status": "pass" if status["online_runners"] > 0 else "warn",
            "detail": "至少有一个 Runner 在线，才能形成真实可执行链路。"
            if status["online_runners"] > 0
            else "当前没有在线 Runner，需要先启动执行节点。",
        },
        {
            "key": "approval",
            "title": "高风险审批",
            "status": "pass" if status["high_risk_approvals"] == 0 else "warn",
            "detail": "没有待确认的 H3/H4 高风险审批。"
            if status["high_risk_approvals"] == 0
            else "仍有高风险审批未通过，需要人工确认。",
        },
        {
            "key": "task",
            "title": "活跃任务",
            "status": "pass" if status["active_tasks"] > 0 else "warn",
            "detail": "当前已有任务在主流程流转。"
            if status["active_tasks"] > 0
            else "还没有进入主流程的任务。",
        },
        {
            "key": "audit",
            "title": "审计留痕",
            "status": "pass" if status["recent_audit_count"] > 0 else "warn",
            "detail": "审计库已有动作记录。"
            if status["recent_audit_count"] > 0
            else "审计库暂时还没有动作记录。",
        },
    ]


def list_lab_audit(db: Session, limit: int = 50):
    stmt = (
        select(AuditLog)
        .where(AuditLog.resource_type == "lab")
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(db.scalars(stmt))


def list_pending_hardware_approvals(db: Session):
    stmt = (
        select(Approval)
        .where(Approval.status == "pending", Approval.level.in_(["H3", "H4"]))
        .order_by(Approval.created_at.asc())
    )
    return list(db.scalars(stmt))


def request_hardware_approval(
    db: Session,
    payload: LabApprovalRequestCreate,
    *,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> Approval:
    task = get_task_or_404(db, payload.task_id)
    if payload.level not in ALLOWED_HARDWARE_APPROVAL_LEVELS:
        raise AppError("INVALID_APPROVAL_LEVEL", "hardware approval level must be H3 or H4", status_code=400)
    approval = Approval(
        project_id=task.project_id,
        task_id=task.id,
        level=payload.level,
        action=payload.action,
        status="pending",
        approver_user_id=None,
        notes=payload.notes or "由实验室动作发起的硬件审批请求。",
    )
    db.add(approval)
    db.flush()
    append_audit_log(
        db,
        project_id=task.project_id,
        task_id=task.id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="lab.hardware_approval_requested",
        resource_type="lab",
        resource_id=approval.id,
        after={
            "task_id": task.id,
            "level": payload.level,
            "action": payload.action,
            "notes": payload.notes,
        },
    )
    db.commit()
    db.refresh(approval)
    return approval


def record_lab_check(
    db: Session,
    payload: LabCheckRecordCreate,
    *,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor_type = actor_type or "human"
    task = get_task_or_404(db, payload.task_id) if payload.task_id else None
    if task is not None and not payload.passed and task.status not in {"blocked", "failed", "done", "cancelled"}:
        transition_task_status(
            db,
            task.id,
            TaskTransitionCreate(
                status="blocked",
                actor_type=actor_type,
                actor_id=actor_id,
                message=f"实验室检查未通过：{payload.item}",
                data={"notes": payload.notes or ""},
            ),
        )
    append_audit_log(
        db,
        project_id=task.project_id if task else None,
        task_id=task.id if task else None,
        actor_type=actor_type,
        actor_id=actor_id,
        action="lab.check_recorded",
        resource_type="lab",
        resource_id=task.id if task else payload.item,
        after={
            "item": payload.item,
            "passed": payload.passed,
            "notes": payload.notes,
            "task_id": payload.task_id,
        },
    )
    db.commit()
    return {
        "task_id": payload.task_id,
        "item": payload.item,
        "passed": payload.passed,
        "notes": payload.notes,
    }


def get_lab_short_chain(db: Session) -> dict:
    status = get_lab_status(db)
    checklist = get_lab_checklist(db)
    pending_hardware_approvals = list_pending_hardware_approvals(db)
    online_runner = db.scalar(select(Runner).where(Runner.status == "online").order_by(Runner.last_heartbeat_at.desc()))  # type: ignore[arg-type]
    runner_summary = {
        "online_runner_id": online_runner.id if online_runner else None,
        "online_runner_name": online_runner.name if online_runner else None,
        "allow_hardware_access": bool(online_runner.allow_hardware_access) if online_runner else False,
    }
    git_status = {
        "supported": ["status", "projects/{id}/sync-github", "projects/{id}/rollback", "activity"],
        "dangerous_operations_blocked": True,
        "recent_activity_count": db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.action.in_(["project.sync_github", "project.rollback_requested"]))
        )
        or 0,
    }
    suggested_chain = [
        {
            "step": "lab.status",
            "status": "pass" if status["online_runners"] > 0 else "warn",
            "note": "先确认实验室总态和 Runner 在线情况。",
        },
        {
            "step": "lab.checklist",
            "status": "pass" if all(item["status"] == "pass" for item in checklist) else "warn",
            "note": "查看检查项，定位是否有高风险审批或无在线执行节点。",
        },
        {
            "step": "runners.next-task",
            "status": "pass" if online_runner else "warn",
            "note": "把任务交给在线 Runner 领取下一条 ready 任务。",
        },
        {
            "step": "git.activity",
            "status": "pass" if git_status["recent_activity_count"] else "warn",
            "note": "查看 Git 同步和回滚审计，确认真实链路已落账。",
        },
    ]
    return {
        "status": status,
        "checklist": checklist,
        "pending_hardware_approvals": [
            {
                "id": item.id,
                "project_id": item.project_id,
                "task_id": item.task_id,
                "level": item.level,
                "action": item.action,
                "status": item.status,
                "notes": item.notes,
                "created_at": item.created_at,
            }
            for item in pending_hardware_approvals
        ],
        "runner_summary": runner_summary,
        "git_status": git_status,
        "suggested_chain": suggested_chain,
    }
