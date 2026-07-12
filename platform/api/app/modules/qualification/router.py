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


# 项目刚创建、还没接入数据时，对应指标显示为中性"-"，而不是把"什么都没发生"
# 误判成红色的 D。前端 CSS 对 "-" 走灰色样式（与 D 红色区分）。
NEUTRAL_GRADE = "-"


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
    if total_runners == 0:
        thread_health_ratio = None
        thread_health_grade = NEUTRAL_GRADE
        thread_health_detail = "尚未绑定 runner，先到电脑接入抽屉登记一台"
    else:
        thread_health_ratio = _ratio(online_runners, total_runners)
        thread_health_grade = _grade(thread_health_ratio)
        thread_health_detail = f"在线 {online_runners}/{total_runners} 个 runner"

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
    total_handoffs = handoff_event_count + handoff_records
    if npc_count == 0:
        npc_handover_score = None
        npc_handover_grade = NEUTRAL_GRADE
        npc_handover_detail = "尚未创建 NPC，先到 NPC 管理器创建一个长期员工"
    elif total_handoffs == 0:
        # 有 NPC 但 7 天没换手，是稳态项目的常态，不该判 D。给 B（达标）。
        npc_handover_score = 0.75
        npc_handover_grade = "B"
        npc_handover_detail = f"近 7 天无换手记录 / {npc_count} 个 NPC（稳态运行）"
    else:
        raw = _ratio(total_handoffs, npc_count)
        npc_handover_score = min(1.0, raw)
        npc_handover_grade = _grade(npc_handover_score)
        npc_handover_detail = f"近 7 天 {total_handoffs} 次交接 / {npc_count} 个 NPC"

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
    # 显式判 None，避免 0.0 被 truthy 误判为"无数据"
    if median_review_min is None:
        if pending_approvals == 0:
            review_score = None
            review_grade = NEUTRAL_GRADE
            review_detail = "暂无审批记录"
        else:
            review_score = 0.5
            review_grade = "C"
            review_detail = f"{pending_approvals} 条待处理，无已闭合审批"
    else:
        if median_review_min <= 30:
            review_score = 1.0
        elif median_review_min <= 120:
            review_score = 0.7
        else:
            review_score = 0.4
        review_grade = _grade(review_score)
        review_detail = f"中位数 {median_review_min} 分钟，{pending_approvals} 条待处理"

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
    if active_tasks_count == 0 and messages_count == 0:
        collab_density = None
        collab_score = None
        collab_grade = NEUTRAL_GRADE
        collab_detail = "暂无活跃任务，也无近 7 天协作消息"
    elif active_tasks_count == 0:
        # 有消息但没活跃任务（任务都做完了），按消息绝对值给中性偏好评价
        collab_density = round(messages_count, 2)
        collab_score = 0.75
        collab_grade = "B"
        collab_detail = f"近 7 天 {messages_count} 条消息，活跃任务已清空"
    else:
        collab_density = round(messages_count / active_tasks_count, 2)
        collab_score = min(1.0, collab_density / 3.0)
        collab_grade = _grade(collab_score)
        collab_detail = f"近 7 天 {messages_count} 条消息 / {active_tasks_count} 条活跃任务"

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

    # weighted overall score：只对"有数据"的指标加权，避免空项目被零分母兜底拉成 D。
    weighted_components: list[tuple[float, float]] = []  # (weight, score)
    if thread_health_ratio is not None:
        weighted_components.append((0.35, thread_health_ratio))
    if npc_handover_score is not None:
        weighted_components.append((0.25, npc_handover_score))
    if review_score is not None:
        weighted_components.append((0.2, review_score))
    if collab_score is not None:
        weighted_components.append((0.2, collab_score))

    if weighted_components:
        total_weight = sum(w for w, _ in weighted_components)
        overall_score: float | None = round(
            sum(w * s for w, s in weighted_components) / total_weight, 3
        )
        overall_grade = _grade(overall_score)
        if overall_score >= 0.7:
            overall_summary = "项目协作合格"
        elif overall_score >= 0.5:
            overall_summary = "项目可用但需关注红色指标"
        else:
            overall_summary = "协作链路存在阻塞，建议先排查"
    else:
        overall_score = None
        overall_grade = NEUTRAL_GRADE
        overall_summary = "项目刚开始，先绑电脑 / 创建 NPC / 创建任务，让数据流起来"

    return ok({
        "project_id": project_id,
        "window_days": 7,
        "indicators": {
            "thread_call_health": {
                "label": "本机线程调用通畅率",
                "value": thread_health_ratio,
                "detail": thread_health_detail,
                "grade": thread_health_grade,
            },
            "npc_handover_health": {
                "label": "NPC 换手记录密度",
                "value": npc_handover_score,
                "detail": npc_handover_detail,
                "grade": npc_handover_grade,
            },
            "human_review_responsiveness": {
                "label": "人工审核响应",
                "median_minutes": median_review_min,
                "pending_count": int(pending_approvals),
                "detail": review_detail,
                "grade": review_grade,
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
                "detail": collab_detail,
                "grade": collab_grade,
            },
            "token_spend_7d_yuan": {
                "label": "近 7 天 token 花费",
                "yuan": spend_yuan,
                "detail": f"￥{spend_yuan}",
                "grade": NEUTRAL_GRADE,
            },
        },
        "overall": {
            "score": overall_score,
            "grade": overall_grade,
            "summary": overall_summary,
        },
    })
