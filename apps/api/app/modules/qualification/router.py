"""Project qualification dashboard.

Aggregates existing audit / usage / handoffs / runner / approval data into a
small set of SLO-style indicators that answer the user's core question:

> "Can this platform call my local Claude/Codex threads and have them
> collaborate reasonably?"

Design choices:
- Read-only and aggregation only — no new tables.
- Reuse existing models (Runner, TaskEvent, Approval, UsageLog,
  CollaborationMessage, Handoff).
- One endpoint, one project at a time. Cheap to call.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.common.response import ok
from app.db.models.approval import Approval
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.handoff import Handoff
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.models.usage_log import UsageLog
from app.db.session import get_db
from app.modules.read_access import require_project_read_access


router = APIRouter(prefix="/api/qualification", tags=["qualification"])


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _grade(score: float) -> str:
    """Map 0..1 score → A/B/C/D grade for at-a-glance display."""
    if score >= 0.85:
        return "A"
    if score >= 0.7:
        return "B"
    if score >= 0.5:
        return "C"
    return "D"


@router.get("/projects/{project_id}/scorecard")
def get_project_scorecard(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a compact qualification scorecard for one project.

    Indicators:
    - thread_call_health  ← Are runners online and heart-beating?
    - npc_handover_health ← Do NPCs accumulate handoff records (proxy for
      "AI换手成本低")?
    - human_review_responsiveness ← Median minutes to approve/reject
    - hardware_redline_count ← H3/H4 actions touched in the last 7 days
    - collaboration_density ← Messages per active task (协作合理性的一个简代理)
    - overall_grade ← A/B/C/D from a weighted average
    """
    require_project_read_access(db, request, project_id, action="qualification.scorecard.read")
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # 1. thread_call_health: any runner online recently?
    nodes = list(db.scalars(select(ProjectComputerNode).where(ProjectComputerNode.project_id == project_id)))
    runner_ids = [n.runner_id for n in nodes if n.runner_id]
    online_runners = 0
    total_runners = len(runner_ids)
    if runner_ids:
        runners = list(db.scalars(select(Runner).where(Runner.id.in_(runner_ids))))
        for r in runners:
            heartbeat = getattr(r, "last_heartbeat_at", None)
            if heartbeat is not None:
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                if (now - heartbeat).total_seconds() <= 300:
                    online_runners += 1
    thread_health_ratio = _ratio(online_runners, max(total_runners, 1))

    # 2. npc_handover_health: # of handoff events in last 7d / # of NPCs
    npcs = list(
        db.scalars(
            select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == project_id)
        )
    )
    npc_count = len(npcs)
    handoff_event_count = (
        db.scalar(
            select(func.count(TaskEvent.id))
            .join(Task, TaskEvent.task_id == Task.id)
            .where(
                Task.project_id == project_id,
                TaskEvent.event_type.in_(["claude_handoff", "claude_handoff_note", "handoff", "context_handoff"]),
                TaskEvent.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    handoff_records = (
        db.scalar(
            select(func.count(Handoff.id)).where(
                Handoff.project_id == project_id,
                Handoff.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    npc_handover_score = _ratio(handoff_event_count + handoff_records, max(npc_count, 1))

    # 3. human_review_responsiveness: avg minutes from approval.created_at to updated_at on approved/rejected
    closed_approvals = list(
        db.scalars(
            select(Approval)
            .where(
                Approval.project_id == project_id,
                Approval.status.in_(["approved", "rejected"]),
                Approval.approved_at >= seven_days_ago,
            )
        )
    )
    review_minutes: list[float] = []
    for ap in closed_approvals:
        if ap.created_at is None or ap.approved_at is None:
            continue
        c = ap.created_at if ap.created_at.tzinfo else ap.created_at.replace(tzinfo=timezone.utc)
        u = ap.approved_at if ap.approved_at.tzinfo else ap.approved_at.replace(tzinfo=timezone.utc)
        delta_min = max(0.0, (u - c).total_seconds() / 60.0)
        review_minutes.append(delta_min)
    median_review_min: float | None = None
    if review_minutes:
        review_minutes.sort()
        mid = len(review_minutes) // 2
        median_review_min = round(
            review_minutes[mid] if len(review_minutes) % 2 == 1 else (review_minutes[mid - 1] + review_minutes[mid]) / 2,
            1,
        )
    pending_approvals = (
        db.scalar(
            select(func.count(Approval.id)).where(
                Approval.project_id == project_id,
                Approval.status.in_(["pending", "needs_changes"]),
            )
        )
        or 0
    )

    # 4. hardware_redline_count: H3/H4 approvals touched in last 7d
    redline_count = (
        db.scalar(
            select(func.count(Approval.id)).where(
                Approval.project_id == project_id,
                Approval.level.in_(["H3", "H4"]),
                Approval.created_at >= seven_days_ago,
            )
        )
        or 0
    )

    # 5. collaboration_density: messages per active task
    active_tasks_count = (
        db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                ~Task.status.in_(["done", "completed", "archived"]),
            )
        )
        or 0
    )
    messages_count = (
        db.scalar(
            select(func.count(CollaborationMessage.id)).where(
                CollaborationMessage.project_id == project_id,
                CollaborationMessage.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    collab_density = round(messages_count / max(active_tasks_count, 1), 2)

    # 6. token spend last 7d
    spend_cents = (
        db.scalar(
            select(func.coalesce(func.sum(UsageLog.cost_cents), 0)).where(
                UsageLog.project_id == project_id,
                UsageLog.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    spend_yuan = round(int(spend_cents) / 100.0, 2)

    # weighted overall score
    review_score = 1.0 if median_review_min is not None and median_review_min <= 30 else (0.7 if median_review_min and median_review_min <= 120 else 0.4)
    collab_score = min(1.0, collab_density / 3.0) if active_tasks_count > 0 else 0.5
    overall_score = round(
        0.35 * thread_health_ratio
        + 0.25 * min(1.0, npc_handover_score)
        + 0.2 * review_score
        + 0.2 * collab_score,
        3,
    )

    return ok({
        "project_id": project_id,
        "window_days": 7,
        "indicators": {
            "thread_call_health": {
                "label": "本机线程调用通畅率",
                "value": thread_health_ratio,
                "detail": f"在线 {online_runners}/{total_runners} 个 runner",
                "grade": _grade(thread_health_ratio),
            },
            "npc_handover_health": {
                "label": "NPC 换手记录密度",
                "value": npc_handover_score,
                "detail": f"近 7 天 {handoff_event_count + handoff_records} 次交接 / {npc_count} 个 NPC",
                "grade": _grade(min(1.0, npc_handover_score)),
            },
            "human_review_responsiveness": {
                "label": "人工审核响应",
                "median_minutes": median_review_min,
                "pending_count": int(pending_approvals),
                "detail": (
                    f"中位数 {median_review_min} 分钟，{pending_approvals} 条待处理"
                    if median_review_min is not None
                    else f"暂无已闭合审批，{pending_approvals} 条待处理"
                ),
                "grade": _grade(review_score),
            },
            "hardware_redline_count": {
                "label": "硬件红线触发",
                "count_7d": int(redline_count),
                "detail": f"近 7 天 H3/H4 动作 {redline_count} 次",
                "grade": "A" if redline_count <= 5 else ("B" if redline_count <= 15 else "C"),
            },
            "collaboration_density": {
                "label": "协作消息密度",
                "messages_per_task": collab_density,
                "detail": f"近 7 天 {messages_count} 条消息 / {active_tasks_count} 条活跃任务",
                "grade": _grade(collab_score),
            },
            "token_spend_7d_yuan": {
                "label": "近 7 天 token 花费",
                "yuan": spend_yuan,
                "detail": f"￥{spend_yuan}",
            },
        },
        "overall": {
            "score": overall_score,
            "grade": _grade(overall_score),
            "summary": (
                "项目协作合格" if overall_score >= 0.7 else "项目可用但需关注红色指标" if overall_score >= 0.5 else "协作链路存在阻塞，建议先排查"
            ),
        },
    })
