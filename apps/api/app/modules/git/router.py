from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.response import ok
from app.common.access import require_platform_operator_principal, resolve_project_write_principal_for_target
from app.db.models.audit_log import AuditLog
from app.db.models.approval import Approval
from app.db.models.project import Project
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.session import get_db
from app.modules.projects.schemas import ProjectRead, ProjectRollbackRequest, ProjectSyncRequest
from app.modules.projects.service import get_project_or_404, rollback_project, serialize_project_for_read, sync_project_github
from app.modules.read_access import require_project_read_access
from app.modules.tasks.schemas import TaskRead


class GitActionRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    provider: str = "github"
    notes: str | None = None


class GitRollbackRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    target_ref: str
    notes: str | None = None


class GitRollbackPreviewRequest(BaseModel):
    target_ref: str
    notes: str | None = None


class GitSyncPreviewRequest(BaseModel):
    provider: str = "github"
    notes: str | None = None


class GitStatusRead(BaseModel):
    provider: str
    supported: list[str]
    dangerous_operations_blocked: bool
    project_count: int = 0
    task_branch_count: int = 0
    last_sync_at: datetime | None = None
    last_rollback_at: datetime | None = None
    recent_activity_count: int = 0


class GitRepositoryRead(BaseModel):
    github_url: str | None = None
    local_git_url: str | None = None
    default_branch: str
    develop_branch: str
    binding_status: str
    sync_status: str


class GitComputerNodeRead(BaseModel):
    id: str
    label: str
    status: str = "offline"
    runner_id: str | None = None
    runner_name: str | None = None
    runner_status: str | None = None
    host: str | None = None
    os: str | None = None


class GitRecommendedWorkstationRead(BaseModel):
    workstation_id: str
    workstation_name: str
    score: int
    reasons: list[str] = Field(default_factory=list)
    workstation_status: str
    task_assignee_agent_id: str | None = None
    workstation_agent_id: str | None = None
    computer_node_id: str | None = None
    ai_provider_id: str | None = None
    responsibility: str | None = None
    model: str | None = None
    permission_level: str | None = None
    read_paths: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)


class GitTaskBranchRead(BaseModel):
    id: str
    title: str
    branch: str | None = None
    status: str
    assignee_agent_id: str | None = None
    reviewer_count: int = 0
    requires_human_approval: bool = False
    recommended_workstations: list[GitRecommendedWorkstationRead] = Field(default_factory=list)
    diff_path: str
    logs_path: str
    context_path: str
    task_path: str
    rollback_path: str


class GitBranchRead(BaseModel):
    task_id: str
    branch: str | None = None
    title: str
    status: str
    priority: str
    assignee_agent_id: str | None = None
    reviewer_count: int = 0
    approval_count: int = 0
    pending_high_risk_approvals: int = 0
    pr_state: str
    merge_ready: bool = False
    latest_activity_at: datetime | None = None
    latest_event_type: str | None = None
    latest_event_message: str | None = None
    activity_count: int = 0
    diff_path: str
    logs_path: str
    context_path: str
    task_path: str
    review_path: str
    sync_path: str
    rollback_path: str


class GitBranchBoardSummaryRead(BaseModel):
    branch_count: int = 0
    pr_count: int = 0
    ready_count: int = 0
    blocked_count: int = 0
    merged_count: int = 0
    draft_count: int = 0
    activity_count: int = 0


class GitProjectBranchBoardRead(BaseModel):
    project: ProjectRead
    repository: GitRepositoryRead
    summary: GitBranchBoardSummaryRead
    branches: list[GitBranchRead] = Field(default_factory=list)
    recent_activity: list["GitActivityRead"] = Field(default_factory=list)
    workflow_notes: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class GitMergeReadinessBranchRead(BaseModel):
    task_id: str
    branch: str | None = None
    title: str
    status: str
    priority: str
    pr_state: str
    merge_ready: bool = False
    blocker_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    approval_count: int = 0
    pending_high_risk_approvals: int = 0
    latest_activity_at: datetime | None = None
    latest_event_type: str | None = None
    latest_event_message: str | None = None
    task_path: str
    diff_path: str
    review_path: str
    sync_path: str


class GitMergeReadinessSummaryRead(BaseModel):
    total_branches: int = 0
    merge_ready_count: int = 0
    blocked_count: int = 0
    review_count: int = 0
    merged_count: int = 0
    draft_count: int = 0
    attention_count: int = 0
    activity_count: int = 0


class GitProjectMergeReadinessRead(BaseModel):
    project: ProjectRead
    repository: GitRepositoryRead
    summary: GitMergeReadinessSummaryRead
    branches: list[GitMergeReadinessBranchRead] = Field(default_factory=list)
    recent_activity: list["GitActivityRead"] = Field(default_factory=list)
    workflow_notes: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class GitExecutionActionRead(BaseModel):
    action: str
    label: str
    status: str
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    latest_activity_at: datetime | None = None
    recent_activity_count: int = 0
    entry_point: str | None = None


class GitExecutionSummaryRead(BaseModel):
    branch_count: int = 0
    merge_ready_count: int = 0
    blocked_count: int = 0
    sync_status: str = "blocked"
    rollback_status: str = "blocked"
    last_sync_at: datetime | None = None
    last_rollback_at: datetime | None = None
    recent_activity_count: int = 0


class GitProjectExecutionRead(BaseModel):
    project: ProjectRead
    repository: GitRepositoryRead
    summary: GitExecutionSummaryRead
    actions: list[GitExecutionActionRead] = Field(default_factory=list)
    recent_activity: list["GitActivityRead"] = Field(default_factory=list)
    workflow_notes: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class GitRollbackPreviewRead(BaseModel):
    target_ref: str
    status: str
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preview_notes: list[str] = Field(default_factory=list)
    next_step: str
    branch_count: int = 0
    merge_ready_count: int = 0
    blocked_count: int = 0
    pending_high_risk_count: int = 0
    merge_ready_titles: list[str] = Field(default_factory=list)
    blocked_branch_titles: list[str] = Field(default_factory=list)


class GitSyncPreviewRead(BaseModel):
    provider: str
    repository_target: str | None = None
    status: str
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preview_notes: list[str] = Field(default_factory=list)
    next_step: str
    branch_count: int = 0
    merge_ready_count: int = 0
    blocked_count: int = 0
    pending_high_risk_count: int = 0
    merge_ready_titles: list[str] = Field(default_factory=list)
    blocked_branch_titles: list[str] = Field(default_factory=list)


class GitWorkstationMatchRead(BaseModel):
    task_id: str
    task_title: str
    task_status: str
    workstation_id: str
    workstation_name: str
    score: int
    reasons: list[str] = Field(default_factory=list)
    task_assignee_agent_id: str | None = None
    workstation_agent_id: str | None = None
    workstation_status: str
    computer_node_id: str | None = None
    ai_provider_id: str | None = None
    responsibility: str | None = None
    model: str | None = None
    permission_level: str | None = None
    read_paths: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)


class GitProjectWorkspaceRead(BaseModel):
    project: ProjectRead
    repository: GitRepositoryRead
    thread_workstations: list[dict] = Field(default_factory=list)
    ai_providers: list[dict] = Field(default_factory=list)
    computer_nodes: list[GitComputerNodeRead] = Field(default_factory=list)
    task_branches: list[GitTaskBranchRead] = Field(default_factory=list)
    workstation_matches: list[GitWorkstationMatchRead] = Field(default_factory=list)
    recent_activity: list["GitActivityRead"] = Field(default_factory=list)
    workflow_notes: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class GitActivityRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    actor_type: str
    actor_id: str | None
    action: str
    title: str | None = None
    summary: str | None = None
    body: str | None = None
    target_ref: str | None = None
    notes: str | None = None
    resource_type: str | None
    resource_id: str | None
    success: bool
    created_at: datetime | None

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/git", tags=["git"])


_ACTIVITY_ACTIONS = [
    "project.sync_github",
    "project.rollback_requested",
    "task.plan",
    "task.approve_plan",
    "task.run",
    "task.review",
    "task.merge",
    "task.rollback",
    "task.transition",
]


def _latest_action_time(db: Session, action: str, project_id: str | None = None):
    stmt = select(AuditLog.created_at).where(AuditLog.action == action)
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(1)
    return db.scalar(stmt)


def _list_git_activity(db: Session, project_id: str | None = None, limit: int = 50):
    stmt = select(AuditLog).where(AuditLog.action.in_(_ACTIVITY_ACTIONS))
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 200)))
    return list(db.scalars(stmt))


def _git_activity_title(action: str) -> str:
    return {
        "project.sync_github": "Git 同步请求",
        "project.rollback_requested": "Git 回退请求",
        "task.plan": "任务计划更新",
        "task.approve_plan": "任务计划已批准",
        "task.run": "任务开始执行",
        "task.review": "任务进入评审",
        "task.merge": "任务合并",
        "task.rollback": "任务回退",
        "task.transition": "任务状态变化",
    }.get(action, action)


def _git_activity_copy(item: AuditLog) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    after = item.after if isinstance(item.after, dict) else {}
    notes = str(after.get("notes") or "").strip() or None
    target_ref = str(after.get("target_ref") or "").strip() or None
    provider = str(after.get("provider") or "").strip() or None

    if item.action == "project.rollback_requested":
        summary = f"已登记回退到 {target_ref}" if target_ref else "已登记项目级 Git 回退请求"
        body = notes or "平台已记录这次回退请求，后续由真实线程或工位按项目约定执行。"
        return summary, body, target_ref, notes, provider

    if item.action == "project.sync_github":
        summary = f"已登记同步到 {provider}" if provider else "已登记仓库同步请求"
        body = notes or "平台已记录这次同步请求，后续由真实线程或工位继续执行。"
        return summary, body, target_ref, notes, provider

    if item.action == "task.merge":
        return "任务分支已进入合并动作", notes or "平台记录了一次任务合并动作。", target_ref, notes, provider
    if item.action == "task.rollback":
        return "任务分支已进入回退动作", notes or "平台记录了一次任务回退动作。", target_ref, notes, provider
    if item.action == "task.review":
        return "任务进入评审", notes or "平台记录了一次任务评审动作。", target_ref, notes, provider
    if item.action == "task.run":
        return "任务进入执行", notes or "平台记录了一次任务执行动作。", target_ref, notes, provider
    if item.action == "task.transition":
        status = str(after.get("status") or "").strip()
        summary = f"任务状态切到 {status}" if status else "任务状态已变化"
        return summary, notes or "平台记录了一次任务状态变化。", target_ref, notes, provider
    if item.action == "task.approve_plan":
        return "任务计划已批准", notes or "平台记录了一次计划批准。", target_ref, notes, provider
    if item.action == "task.plan":
        return "任务计划已更新", notes or "平台记录了一次计划更新。", target_ref, notes, provider
    return None, notes, target_ref, notes, provider


def _serialize_git_activity(item: AuditLog) -> dict[str, object]:
    summary, body, target_ref, notes, _provider = _git_activity_copy(item)
    return GitActivityRead(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        actor_type=item.actor_type,
        actor_id=item.actor_id,
        action=item.action,
        title=_git_activity_title(item.action),
        summary=summary,
        body=body,
        target_ref=target_ref,
        notes=notes,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        success=item.success,
        created_at=item.created_at,
    ).model_dump(mode="json")


def _text_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _permission_rank(value: object | None) -> int:
    text = str(value or "").strip().upper()
    if not text:
        return 0
    if text.startswith("L"):
        text = text[1:]
    try:
        return int(text)
    except ValueError:
        return {"LOW": 1, "READ": 1, "MEDIUM": 2, "WRITE": 3, "ADMIN": 4}.get(text, 0)


def _priority_rank(value: object | None) -> int:
    text = str(value or "").strip().upper()
    if not text:
        return 2
    if text in {"P0", "CRITICAL"}:
        return 4
    if text in {"P1", "HIGH"}:
        return 3
    if text in {"P2", "MEDIUM"}:
        return 2
    if text in {"P3", "LOW"}:
        return 1
    if text.isdigit():
        return max(1, min(4, 5 - int(text)))
    return 2


def _required_permission_level(task_status: str, task_priority: object | None) -> int:
    required = _priority_rank(task_priority)
    if task_status in {"waiting_approval", "reviewing", "blocked"}:
        required = max(required, 3)
    return required


def _status_score(status: object | None) -> int:
    text = str(status or "").strip().lower()
    if text in {"online", "active", "enabled", "ready", "working"}:
        return 30
    if text in {"standby", "idle", "pending"}:
        return 16
    if text in {"offline", "disabled", "blocked", "failed"}:
        return 0
    return 8


def _normalize_workstation(item: dict[str, object], *, node_lookup: dict[str, dict[str, object]]) -> dict[str, object]:
    computer_node_id = str(item.get("computer_node_id") or item.get("computer_node") or "").strip() or None
    node = node_lookup.get(computer_node_id or "") if computer_node_id else None
    permission_level = item.get("permission_level") or item.get("permissionLevel") or item.get("permission")
    return {
        "id": str(item.get("id") or item.get("name") or item.get("agent_id") or "").strip(),
        "name": str(item.get("name") or item.get("id") or item.get("agent_id") or "workstation").strip(),
        "agent_id": str(item.get("agent_id") or "").strip() or None,
        "computer_node_id": computer_node_id,
        "ai_provider_id": str(item.get("ai_provider_id") or item.get("ai_provider") or "").strip() or None,
        "status": str(item.get("status") or "idle"),
        "responsibility": str(item.get("responsibility") or item.get("role") or item.get("description") or "").strip() or None,
        "model": str(item.get("model") or item.get("default_model") or "").strip() or None,
        "permission_level": str(permission_level).strip() or None,
        "read_paths": _text_list(item.get("read_paths") or item.get("read_dirs") or item.get("readable_paths")),
        "write_paths": _text_list(item.get("write_paths") or item.get("write_dirs") or item.get("writable_paths")),
        "node_status": str((node or {}).get("status") or "offline"),
    }


def _score_workstation_for_task(task: dict[str, object], workstation: dict[str, object]) -> tuple[int, list[str], bool]:
    reasons: list[str] = []
    score = 0
    status = str(workstation["status"]).lower()
    node_status = str(workstation["node_status"]).lower()
    task_assignee = str(task.get("assignee_agent_id") or "").strip() or None
    workstation_agent = workstation.get("agent_id")
    permission_rank = _permission_rank(workstation.get("permission_level"))
    required_permission = _required_permission_level(str(task.get("status") or ""), task.get("priority"))

    status_score = _status_score(status)
    score += status_score
    if status_score >= 30:
        reasons.append("workstation is active")
    elif status_score > 0:
        reasons.append("workstation is available but not fully active")
    else:
        reasons.append("workstation is offline or blocked")

    node_score = _status_score(node_status)
    score += min(node_score, 10)
    if node_status in {"online", "active", "ready"}:
        reasons.append("computer node is online")
    elif node_status:
        reasons.append(f"computer node status is {node_status}")

    if task_assignee and workstation_agent:
        if task_assignee == workstation_agent:
            score += 60
            reasons.append("workstation agent matches task assignee")
        else:
            score -= 10
            reasons.append(f"task assignee is {task_assignee}, workstation agent is {workstation_agent}")
    elif task_assignee:
        score += 8
        reasons.append(f"task assignee is {task_assignee}, workstation agent is unassigned")
    elif workstation_agent:
        score += 4
        reasons.append(f"workstation agent is {workstation_agent}")

    if permission_rank >= required_permission and permission_rank > 0:
        score += 20
        reasons.append(f"permission level {workstation.get('permission_level')} covers task requirement")
    else:
        score -= 12
        reasons.append(f"permission level {workstation.get('permission_level') or 'unset'} is below task requirement")

    if workstation["responsibility"]:
        score += 4
    if workstation["model"]:
        score += 4
    if workstation["read_paths"]:
        score += 4
    if workstation["write_paths"]:
        score += 4

    recommended = status_score > 0 and permission_rank >= required_permission and score >= 35
    return score, reasons, recommended


def _branch_pr_state(task_status: str, approval_count: int, pending_high_risk_count: int) -> tuple[str, bool]:
    status = str(task_status or "").strip().lower()
    if status == "done":
        return "merged", False
    if pending_high_risk_count > 0 or status == "blocked":
        return "blocked", False
    if status in {"reviewing", "needs_changes"} or approval_count > 0:
        return "review", True
    if status in {"ready", "running"}:
        return "open", True
    return "draft", False


def _branch_blockers(task_status: str, approval_count: int, pending_high_risk_count: int) -> list[str]:
    blockers: list[str] = []
    status = str(task_status or "").strip().lower()
    if status == "blocked":
        blockers.append("task is blocked")
    elif status in {"reviewing", "needs_changes"}:
        blockers.append("task still needs review")
    elif status not in {"ready", "running", "done"}:
        blockers.append(f"task status is {status or 'draft'}")
    if approval_count > 0:
        blockers.append(f"{approval_count} approval record(s) attached")
    if pending_high_risk_count > 0:
        blockers.append(f"{pending_high_risk_count} high-risk approval(s) pending")
    return blockers


def _execution_action_status(
    action: str,
    *,
    repository: GitRepositoryRead,
    branch_count: int,
    blocked_count: int,
    merge_ready_count: int,
) -> tuple[str, bool, list[str]]:
    blockers: list[str] = []
    if action == "sync_github":
        if repository.binding_status == "unbound":
            blockers.append("repository is not bound")
            return "blocked", False, blockers
        if branch_count == 0:
            blockers.append("no task branches yet")
            return "blocked", False, blockers
        if blocked_count > 0:
            blockers.append(f"{blocked_count} blocked branch(es) still need attention")
            return "attention", False, blockers
        if merge_ready_count == 0:
            blockers.append("no merge-ready branches yet")
            return "attention", False, blockers
        return "ready", True, blockers
    if action == "rollback":
        if repository.binding_status == "unbound":
            blockers.append("repository is not bound")
            return "blocked", False, blockers
        if branch_count == 0:
            blockers.append("no task branches available for rollback context")
            return "blocked", False, blockers
        return "ready", True, blockers
    return "blocked", False, ["unsupported execution action"]


def _build_git_repository(project: Project) -> GitRepositoryRead:
    return GitRepositoryRead(
        github_url=project.github_url,
        local_git_url=project.local_git_url,
        default_branch=project.default_branch,
        develop_branch=project.develop_branch,
        binding_status="double-bound"
        if project.github_url and project.local_git_url
        else "github-bound"
        if project.github_url
        else "local-bound"
        if project.local_git_url
        else "unbound",
        sync_status="syncable" if project.github_url or project.local_git_url else "waiting-for-bind",
    )


def _resolve_sync_provider(provider: object | None, repository: GitRepositoryRead) -> tuple[str, str | None]:
    normalized = str(provider or "").strip().lower()
    if normalized not in {"github", "local"}:
        normalized = "github" if repository.github_url else "local" if repository.local_git_url else "github"
    repository_target = repository.github_url if normalized == "github" else repository.local_git_url
    return normalized, repository_target


def _project_git_rollup(db: Session, project_id: str) -> dict[str, object]:
    task_rows = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.updated_at.desc())
        )
    )

    branch_count = 0
    merge_ready_count = 0
    blocked_count = 0
    activity_count = 0
    pending_high_risk_count = 0
    merge_ready_titles: list[str] = []
    blocked_branch_titles: list[str] = []

    for task in task_rows:
        if not task.branch:
            continue
        approval_count = int(db.scalar(select(func.count(Approval.id)).where(Approval.task_id == task.id)) or 0)
        task_pending_high_risk_count = int(
            db.scalar(
                select(func.count(Approval.id)).where(
                    Approval.task_id == task.id,
                    Approval.status == "pending",
                    Approval.level.in_(["H3", "H4"]),
                )
            )
            or 0
        )
        pr_state, merge_ready = _branch_pr_state(task.status, approval_count, task_pending_high_risk_count)
        branch_count += 1
        activity_count += int(db.scalar(select(func.count(TaskEvent.id)).where(TaskEvent.task_id == task.id)) or 0)
        pending_high_risk_count += task_pending_high_risk_count

        title = str(task.title or task.branch or task.id)
        if merge_ready:
            merge_ready_count += 1
            merge_ready_titles.append(title)
        elif pr_state == "blocked":
            blocked_count += 1
            blocked_branch_titles.append(title)

    return {
        "branch_count": branch_count,
        "merge_ready_count": merge_ready_count,
        "blocked_count": blocked_count,
        "activity_count": activity_count,
        "pending_high_risk_count": pending_high_risk_count,
        "merge_ready_titles": merge_ready_titles,
        "blocked_branch_titles": blocked_branch_titles,
    }


@router.get("/status")
def api_git_status(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="git.status.read")
    project_count = db.scalar(select(func.count(Project.id))) or 0
    task_branch_count = db.scalar(select(func.count(Task.id)).where(Task.branch.is_not(None))) or 0
    payload = GitStatusRead(
        provider="local",
        supported=[
            "status",
            "projects/{id}/workspace",
            "projects/{id}/branches",
            "projects/{id}/merge-readiness",
            "projects/{id}/execution",
            "projects/{id}/sync-preview",
            "projects/{id}/rollback-preview",
            "projects/{id}/sync-github",
            "projects/{id}/rollback",
            "projects/{id}/activity",
            "activity",
        ],
        dangerous_operations_blocked=True,
        project_count=int(project_count),
        task_branch_count=int(task_branch_count),
        last_sync_at=_latest_action_time(db, "project.sync_github"),
        last_rollback_at=_latest_action_time(db, "project.rollback_requested"),
        recent_activity_count=len(_list_git_activity(db, limit=20)),
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/projects/{project_id}/workspace")
def api_git_project_workspace(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    project_payload = ProjectRead.model_validate(serialize_project_for_read(project))
    project_data = project_payload.model_dump(mode="json")
    collaboration_config = project_data.get("collaboration_config") or {}

    runner_rows = {
        runner.id: runner
        for runner in db.scalars(select(Runner).order_by(Runner.last_heartbeat_at.desc())).all()
    }

    node_rows: list[dict[str, object]] = []
    for node in collaboration_config.get("computer_nodes", []) or []:
        runner_id = str(node.get("runner_id") or "").strip() or None
        runner = runner_rows.get(runner_id) if runner_id else None
        node_rows.append(
            {
                "id": str(node.get("id") or node.get("label") or node.get("name") or ""),
                "label": str(node.get("label") or node.get("name") or node.get("id") or "node"),
                "status": str(node.get("status") or "offline"),
                "runner_id": runner_id,
                "runner_name": runner.name if runner is not None else None,
                "runner_status": runner.status if runner is not None else "offline",
                "host": runner.host if runner is not None else node.get("host"),
                "os": runner.os if runner is not None else node.get("os"),
            }
        )
    computer_nodes = [GitComputerNodeRead.model_validate(item) for item in node_rows]
    node_lookup = {str(node["id"]): node for node in node_rows}
    workstation_rows = [
        _normalize_workstation(item, node_lookup=node_lookup)
        for item in collaboration_config.get("thread_workstations", []) or []
    ]

    task_rows = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.updated_at.desc())
        )
    )
    task_branches: list[GitTaskBranchRead] = []
    workstation_matches: list[GitWorkstationMatchRead] = []
    for task in task_rows:
        task_payload = TaskRead.model_validate(task).model_dump(mode="json")
        ranked_matches: list[GitWorkstationMatchRead] = []
        for workstation in workstation_rows:
            score, reasons, recommended = _score_workstation_for_task(task_payload, workstation)
            match = GitWorkstationMatchRead(
                task_id=task_payload["id"],
                task_title=task_payload["title"],
                task_status=task_payload["status"],
                workstation_id=workstation["id"],
                workstation_name=workstation["name"],
                score=score,
                reasons=reasons,
                task_assignee_agent_id=task_payload.get("assignee_agent_id"),
                workstation_agent_id=workstation.get("agent_id"),
                workstation_status=workstation["status"],
                computer_node_id=workstation.get("computer_node_id"),
                ai_provider_id=workstation.get("ai_provider_id"),
                responsibility=workstation.get("responsibility"),
                model=workstation.get("model"),
                permission_level=workstation.get("permission_level"),
                read_paths=workstation.get("read_paths") or [],
                write_paths=workstation.get("write_paths") or [],
            )
            if recommended:
                workstation_matches.append(match)
                ranked_matches.append(match)
        ranked_matches.sort(key=lambda item: (item.score, item.workstation_status == "active", item.workstation_id), reverse=True)
        task_branches.append(
            GitTaskBranchRead(
                id=task_payload["id"],
                title=task_payload["title"],
                branch=task_payload.get("branch"),
                status=task_payload["status"],
                assignee_agent_id=task_payload.get("assignee_agent_id"),
                reviewer_count=len(task_payload.get("reviewers") or []),
                requires_human_approval=task_payload["status"] in {"waiting_approval", "reviewing", "blocked"}
                or len(task_payload.get("reviewers") or []) > 0,
                recommended_workstations=[
                    GitRecommendedWorkstationRead(
                        workstation_id=item.workstation_id,
                        workstation_name=item.workstation_name,
                        score=item.score,
                        reasons=item.reasons,
                        workstation_status=item.workstation_status,
                        task_assignee_agent_id=item.task_assignee_agent_id,
                        workstation_agent_id=item.workstation_agent_id,
                        computer_node_id=item.computer_node_id,
                        ai_provider_id=item.ai_provider_id,
                        responsibility=item.responsibility,
                        model=item.model,
                        permission_level=item.permission_level,
                        read_paths=item.read_paths,
                        write_paths=item.write_paths,
                    )
                    for item in ranked_matches[:3]
                ],
                diff_path=f"/tasks/{task_payload['id']}/diff",
                logs_path=f"/tasks/{task_payload['id']}/logs",
                context_path=f"/tasks/{task_payload['id']}/context",
                task_path=f"/tasks/{task_payload['id']}",
                rollback_path=f"/git?project_id={project_id}#rollback-panel",
            )
        )

    recent_activity = [GitActivityRead.model_validate(_serialize_git_activity(item)) for item in _list_git_activity(db, project_id=project_id, limit=12)]
    repository = GitRepositoryRead(
        github_url=project.github_url,
        local_git_url=project.local_git_url,
        default_branch=project.default_branch,
        develop_branch=project.develop_branch,
        binding_status="double-bound"
        if project.github_url and project.local_git_url
        else "github-bound"
        if project.github_url
        else "local-bound"
        if project.local_git_url
        else "unbound",
        sync_status="syncable" if project.github_url or project.local_git_url else "waiting-for-bind",
    )

    payload = GitProjectWorkspaceRead(
        project=project_payload,
        repository=repository,
        thread_workstations=collaboration_config.get("thread_workstations", []) or [],
        ai_providers=collaboration_config.get("ai_providers", []) or [],
        computer_nodes=computer_nodes,
        task_branches=task_branches,
        workstation_matches=workstation_matches,
        recent_activity=recent_activity,
        workflow_notes=[
            "Bind the repository first, then attach nodes, AI providers, and workstations.",
            "Task branches are matched to workstations using task assignee, workstation agent, status, and permission level.",
            "Different computers can host different AI workers, but they still belong to one project workspace.",
        ],
        entry_points=[
            f"/projects/{project_id}",
            f"/projects/{project_id}/messages",
            f"/tasks?project_id={project_id}",
            f"/git?project_id={project_id}#sync-panel",
            f"/git?project_id={project_id}#rollback-panel",
            f"/git?project_id={project_id}#activity-panel",
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/projects/{project_id}/branches")
def api_git_project_branches(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    project_payload = ProjectRead.model_validate(serialize_project_for_read(project))
    project_data = project_payload.model_dump(mode="json")
    collaboration_config = project_data.get("collaboration_config") or {}

    task_rows = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.updated_at.desc())
        )
    )

    branch_rows: list[GitBranchRead] = []
    branch_count = 0
    pr_count = 0
    ready_count = 0
    blocked_count = 0
    merged_count = 0
    draft_count = 0
    activity_count = 0

    for task in task_rows:
        if not task.branch:
            continue
        approval_count = int(db.scalar(select(func.count(Approval.id)).where(Approval.task_id == task.id)) or 0)
        pending_high_risk_count = int(
            db.scalar(
                select(func.count(Approval.id)).where(
                    Approval.task_id == task.id,
                    Approval.status == "pending",
                    Approval.level.in_(["H3", "H4"]),
                )
            )
            or 0
        )
        latest_event = db.scalar(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at.desc()).limit(1))
        item_activity_count = int(db.scalar(select(func.count(TaskEvent.id)).where(TaskEvent.task_id == task.id)) or 0)
        pr_state, merge_ready = _branch_pr_state(task.status, approval_count, pending_high_risk_count)

        branch_rows.append(
            GitBranchRead(
                task_id=task.id,
                branch=task.branch,
                title=task.title,
                status=task.status,
                priority=task.priority,
                assignee_agent_id=task.assignee_agent_id,
                reviewer_count=len(task.reviewers or []),
                approval_count=approval_count,
                pending_high_risk_approvals=pending_high_risk_count,
                pr_state=pr_state,
                merge_ready=merge_ready,
                latest_activity_at=latest_event.created_at if latest_event is not None else task.updated_at,
                latest_event_type=latest_event.event_type if latest_event is not None else None,
                latest_event_message=latest_event.message if latest_event is not None else None,
                activity_count=item_activity_count,
                diff_path=f"/tasks/{task.id}/diff",
                logs_path=f"/tasks/{task.id}/logs",
                context_path=f"/tasks/{task.id}/context",
                task_path=f"/tasks/{task.id}",
                review_path=f"/tasks/{task.id}",
                sync_path=f"/git?project_id={project_id}#sync-panel",
                rollback_path=f"/git?project_id={project_id}#rollback-panel",
            )
        )
        branch_count += 1
        pr_count += 1
        activity_count += item_activity_count
        if merge_ready:
            ready_count += 1
        elif pr_state == "blocked":
            blocked_count += 1
        elif pr_state == "merged":
            merged_count += 1
        else:
            draft_count += 1

    recent_activity = [GitActivityRead.model_validate(_serialize_git_activity(item)) for item in _list_git_activity(db, project_id=project_id, limit=12)]
    repository = GitRepositoryRead(
        github_url=project.github_url,
        local_git_url=project.local_git_url,
        default_branch=project.default_branch,
        develop_branch=project.develop_branch,
        binding_status="double-bound"
        if project.github_url and project.local_git_url
        else "github-bound"
        if project.github_url
        else "local-bound"
        if project.local_git_url
        else "unbound",
        sync_status="syncable" if project.github_url or project.local_git_url else "waiting-for-bind",
    )
    summary = GitBranchBoardSummaryRead(
        branch_count=branch_count,
        pr_count=pr_count,
        ready_count=ready_count,
        blocked_count=blocked_count,
        merged_count=merged_count,
        draft_count=draft_count,
        activity_count=activity_count,
    )
    payload = GitProjectBranchBoardRead(
        project=project_payload,
        repository=repository,
        summary=summary,
        branches=branch_rows,
        recent_activity=recent_activity,
        workflow_notes=[
            "Branches are derived from task records so the Git board can stay aligned with task flow.",
            "Pull request state is inferred from task status plus approval pressure, keeping the read model stable even before a real PR service exists.",
            "High-risk approvals still block readiness, so the board shows where human sign-off is still required.",
        ],
        entry_points=[
            f"/projects/{project_id}",
            f"/projects/{project_id}/messages",
            f"/tasks?project_id={project_id}",
            f"/git?project_id={project_id}#sync-panel",
            f"/git?project_id={project_id}#rollback-panel",
            f"/git?project_id={project_id}#activity-panel",
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/projects/{project_id}/merge-readiness")
def api_git_project_merge_readiness(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    project_payload = ProjectRead.model_validate(serialize_project_for_read(project))
    project_data = project_payload.model_dump(mode="json")
    collaboration_config = project_data.get("collaboration_config") or {}

    task_rows = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.updated_at.desc())
        )
    )

    branch_rows: list[GitMergeReadinessBranchRead] = []
    total_branches = 0
    merge_ready_count = 0
    blocked_count = 0
    review_count = 0
    merged_count = 0
    draft_count = 0
    attention_count = 0
    activity_count = 0

    for task in task_rows:
        if not task.branch:
            continue
        approval_count = int(db.scalar(select(func.count(Approval.id)).where(Approval.task_id == task.id)) or 0)
        pending_high_risk_count = int(
            db.scalar(
                select(func.count(Approval.id)).where(
                    Approval.task_id == task.id,
                    Approval.status == "pending",
                    Approval.level.in_(["H3", "H4"]),
                )
            )
            or 0
        )
        latest_event = db.scalar(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at.desc()).limit(1))
        item_activity_count = int(db.scalar(select(func.count(TaskEvent.id)).where(TaskEvent.task_id == task.id)) or 0)
        pr_state, merge_ready = _branch_pr_state(task.status, approval_count, pending_high_risk_count)
        blockers = _branch_blockers(task.status, approval_count, pending_high_risk_count)
        if task.branch and not task.branch.strip():
            blockers.append("branch name missing")

        branch_rows.append(
            GitMergeReadinessBranchRead(
                task_id=task.id,
                branch=task.branch,
                title=task.title,
                status=task.status,
                priority=task.priority,
                pr_state=pr_state,
                merge_ready=merge_ready,
                blocker_count=len(blockers),
                blockers=blockers,
                approval_count=approval_count,
                pending_high_risk_approvals=pending_high_risk_count,
                latest_activity_at=latest_event.created_at if latest_event is not None else task.updated_at,
                latest_event_type=latest_event.event_type if latest_event is not None else None,
                latest_event_message=latest_event.message if latest_event is not None else None,
                task_path=f"/tasks/{task.id}",
                diff_path=f"/tasks/{task.id}/diff",
                review_path=f"/tasks/{task.id}",
                sync_path=f"/git?project_id={project_id}#sync-panel",
            )
        )

        total_branches += 1
        attention_count += len(blockers)
        activity_count += item_activity_count
        if str(task.status or "").strip().lower() in {"reviewing", "needs_changes"}:
            review_count += 1
        if merge_ready:
            merge_ready_count += 1
        elif pr_state == "blocked":
            blocked_count += 1
        elif pr_state == "merged":
            merged_count += 1
        else:
            draft_count += 1

    recent_activity = [GitActivityRead.model_validate(_serialize_git_activity(item)) for item in _list_git_activity(db, project_id=project_id, limit=12)]
    repository = GitRepositoryRead(
        github_url=project.github_url,
        local_git_url=project.local_git_url,
        default_branch=project.default_branch,
        develop_branch=project.develop_branch,
        binding_status="double-bound"
        if project.github_url and project.local_git_url
        else "github-bound"
        if project.github_url
        else "local-bound"
        if project.local_git_url
        else "unbound",
        sync_status="syncable" if project.github_url or project.local_git_url else "waiting-for-bind",
    )
    payload = GitProjectMergeReadinessRead(
        project=project_payload,
        repository=repository,
        summary=GitMergeReadinessSummaryRead(
            total_branches=total_branches,
            merge_ready_count=merge_ready_count,
            blocked_count=blocked_count,
            review_count=review_count,
            merged_count=merged_count,
            draft_count=draft_count,
            attention_count=attention_count,
            activity_count=activity_count,
        ),
        branches=branch_rows[:],
        recent_activity=recent_activity,
        workflow_notes=[
            "Merge readiness is derived from task state, branch presence, and approval pressure.",
            "A branch is only marked ready when it is not blocked and has no pending high-risk approvals.",
            "The panel stays read-only so it can safely summarize readiness without executing repository actions.",
        ],
        entry_points=[
            f"/projects/{project_id}",
            f"/projects/{project_id}/messages",
            f"/tasks?project_id={project_id}",
            f"/git?project_id={project_id}#rollback-panel",
            f"/git?project_id={project_id}#activity-panel",
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/projects/{project_id}/execution")
def api_git_project_execution(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    project_payload = ProjectRead.model_validate(serialize_project_for_read(project))
    rollup = _project_git_rollup(db, project_id)
    branch_count = int(rollup["branch_count"])
    merge_ready_count = int(rollup["merge_ready_count"])
    blocked_count = int(rollup["blocked_count"])
    activity_count = int(rollup["activity_count"])

    latest_sync_at = _latest_action_time(db, "project.sync_github", project_id=project_id)
    latest_rollback_at = _latest_action_time(db, "project.rollback_requested", project_id=project_id)
    repository = _build_git_repository(project)

    sync_status, sync_ready, sync_blockers = _execution_action_status(
        "sync_github",
        repository=repository,
        branch_count=branch_count,
        blocked_count=blocked_count,
        merge_ready_count=merge_ready_count,
    )
    rollback_status, rollback_ready, rollback_blockers = _execution_action_status(
        "rollback",
        repository=repository,
        branch_count=branch_count,
        blocked_count=blocked_count,
        merge_ready_count=merge_ready_count,
    )

    recent_activity = [GitActivityRead.model_validate(_serialize_git_activity(item)) for item in _list_git_activity(db, project_id=project_id, limit=12)]
    payload = GitProjectExecutionRead(
        project=project_payload,
        repository=repository,
        summary=GitExecutionSummaryRead(
            branch_count=branch_count,
            merge_ready_count=merge_ready_count,
            blocked_count=blocked_count,
            sync_status=sync_status,
            rollback_status=rollback_status,
            last_sync_at=latest_sync_at,
            last_rollback_at=latest_rollback_at,
            recent_activity_count=len(recent_activity),
        ),
        actions=[
            GitExecutionActionRead(
                action="sync_github",
                label="同步 GitHub",
                status=sync_status,
                ready=sync_ready,
                blockers=sync_blockers,
                latest_activity_at=latest_sync_at,
                recent_activity_count=sum(1 for item in recent_activity if item.action == "project.sync_github"),
                entry_point=f"/git?project_id={project_id}#sync-panel",
            ),
            GitExecutionActionRead(
                action="rollback",
                label="登记回滚",
                status=rollback_status,
                ready=rollback_ready,
                blockers=rollback_blockers,
                latest_activity_at=latest_rollback_at,
                recent_activity_count=sum(1 for item in recent_activity if item.action == "project.rollback_requested"),
                entry_point=f"/git?project_id={project_id}#rollback-panel",
            ),
        ],
        recent_activity=recent_activity,
        workflow_notes=[
            "Execution view is a safe read model that composes branch readiness, merge pressure, and the write entry points.",
            "Sync is considered attention-worthy while blocked branches remain open so operators can stage the right handoff first.",
            "Rollback stays available as a project-level action, but it is only marked ready when the repository is bound and branch context exists.",
        ],
        entry_points=[
            f"/projects/{project_id}",
            f"/projects/{project_id}/messages",
            f"/tasks?project_id={project_id}",
            f"/git?project_id={project_id}#sync-panel",
            f"/git?project_id={project_id}#rollback-panel",
            f"/git?project_id={project_id}#activity-panel",
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.post("/projects/{project_id}/rollback-preview")
def api_git_rollback_preview(
    project_id: str,
    payload: GitRollbackPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    repository = _build_git_repository(project)
    rollup = _project_git_rollup(db, project_id)
    branch_count = int(rollup["branch_count"])
    merge_ready_count = int(rollup["merge_ready_count"])
    blocked_count = int(rollup["blocked_count"])
    pending_high_risk_count = int(rollup["pending_high_risk_count"])
    merge_ready_titles = [str(item) for item in rollup["merge_ready_titles"]][:5]
    blocked_branch_titles = [str(item) for item in rollup["blocked_branch_titles"]][:5]

    status, ready, blockers = _execution_action_status(
        "rollback",
        repository=repository,
        branch_count=branch_count,
        blocked_count=blocked_count,
        merge_ready_count=merge_ready_count,
    )

    target_ref = str(payload.target_ref or "").strip()
    warnings: list[str] = []
    if target_ref:
        if target_ref == project.default_branch:
            warnings.append(f"当前目标是默认分支 {project.default_branch}，真实执行前要确认是否会覆盖最近稳定交付。")
        elif target_ref == project.develop_branch:
            warnings.append(f"当前目标是开发分支 {project.develop_branch}，适合回到协作主线，但仍要通知正在工作的线程重新对齐。")
        else:
            warnings.append(f"当前目标是自定义引用 {target_ref}，要确认真实执行线程能解析这个 ref。")
    if merge_ready_count > 0:
        warnings.append(f"还有 {merge_ready_count} 个可合并分支，回退前要确认是否先收口这些结果。")
    if blocked_count > 0:
        warnings.append(f"还有 {blocked_count} 个阻塞分支，回退后它们通常需要重新对齐。")
    if pending_high_risk_count > 0:
        warnings.append(f"还有 {pending_high_risk_count} 条高风险审批未完成，建议先人工确认。")
    if not str(payload.notes or "").strip():
        warnings.append("还没有填写回退原因，建议先补一句让协作线程知道为什么回退。")

    next_step = (
        "先处理上面的阻塞，再回来重新预演。"
        if blockers
        else "如果这次预演结果符合预期，就可以点击“登记 Git 回退请求”，把动作交给真实线程或工位继续执行。"
    )

    preview = GitRollbackPreviewRead(
        target_ref=target_ref,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        preview_notes=[
            "这次只是预演，不会写入项目活动流。",
            "浏览器里不会直接执行 git reset / git revert。",
            "正式登记后，平台只记录请求，真正执行仍交给真实线程或工位。",
        ],
        next_step=next_step,
        branch_count=branch_count,
        merge_ready_count=merge_ready_count,
        blocked_count=blocked_count,
        pending_high_risk_count=pending_high_risk_count,
        merge_ready_titles=merge_ready_titles,
        blocked_branch_titles=blocked_branch_titles,
    )
    return ok(preview.model_dump(mode="json"))


@router.post("/projects/{project_id}/sync-preview")
def api_git_sync_preview(
    project_id: str,
    payload: GitSyncPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="project.git.read")
    project = get_project_or_404(db, project_id)
    repository = _build_git_repository(project)
    provider, repository_target = _resolve_sync_provider(payload.provider, repository)
    rollup = _project_git_rollup(db, project_id)
    branch_count = int(rollup["branch_count"])
    merge_ready_count = int(rollup["merge_ready_count"])
    blocked_count = int(rollup["blocked_count"])
    pending_high_risk_count = int(rollup["pending_high_risk_count"])
    merge_ready_titles = [str(item) for item in rollup["merge_ready_titles"]][:5]
    blocked_branch_titles = [str(item) for item in rollup["blocked_branch_titles"]][:5]

    status, ready, blockers = _execution_action_status(
        "sync_github",
        repository=repository,
        branch_count=branch_count,
        blocked_count=blocked_count,
        merge_ready_count=merge_ready_count,
    )
    if not repository_target:
        blockers = [
            "repository is not bound" if provider == "github" else "local repository is not bound",
            *[item for item in blockers if "repository" not in item.lower()],
        ]
        status = "blocked"
        ready = False

    warnings: list[str] = []
    if provider == "github":
        warnings.append("这次预演面向 GitHub 同步，请先确认远端仓库仍然是当前项目的唯一主仓。")
    else:
        warnings.append("这次预演面向本地仓库镜像，请先确认执行线程所在电脑能访问这条本地路径。")
    if merge_ready_count > 0:
        warnings.append(f"当前有 {merge_ready_count} 个可合并分支，正式登记同步后这些结果会更接近被汇总进主线。")
    if blocked_count > 0:
        warnings.append(f"当前还有 {blocked_count} 个阻塞分支，正式同步前最好先明确它们是否需要延后。")
    if pending_high_risk_count > 0:
        warnings.append(f"当前还有 {pending_high_risk_count} 条高风险审批未完成，建议同步前先让人工确认。")
    if not str(payload.notes or "").strip():
        warnings.append("还没有填写同步原因，建议先补一句让协作线程知道为什么现在要同步。")

    next_step = (
        "先处理上面的阻塞，再回来重新预演同步。"
        if blockers
        else "如果这次预演结果符合预期，就可以点击“登记 Git 同步请求”，把动作交给真实线程或工位继续执行。"
    )

    preview = GitSyncPreviewRead(
        provider=provider,
        repository_target=repository_target,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        preview_notes=[
            "这次只是预演，不会写入项目活动流。",
            "浏览器里不会直接执行 git push / git pull / git merge。",
            "正式登记后，平台只记录同步请求，真正执行仍交给真实线程或工位。",
        ],
        next_step=next_step,
        branch_count=branch_count,
        merge_ready_count=merge_ready_count,
        blocked_count=blocked_count,
        pending_high_risk_count=pending_high_risk_count,
        merge_ready_titles=merge_ready_titles,
        blocked_branch_titles=blocked_branch_titles,
    )
    return ok(preview.model_dump(mode="json"))


@router.post("/projects/{project_id}/sync-github")
def api_git_sync_project(
    project_id: str,
    payload: GitActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="project.sync_github",
    )
    get_project_or_404(db, project_id)
    result = sync_project_github(
        db,
        project_id,
        ProjectSyncRequest(
            actor_type=payload.actor_type,
            actor_id=payload.actor_id,
            provider=payload.provider,
            notes=payload.notes,
        ),
    )
    return ok(result)


@router.post("/projects/{project_id}/rollback")
def api_git_rollback_project(
    project_id: str,
    payload: GitRollbackRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="project.rollback",
    )
    get_project_or_404(db, project_id)
    result = rollback_project(
        db,
        project_id,
        ProjectRollbackRequest(
            actor_type=payload.actor_type,
            actor_id=payload.actor_id,
            target_ref=payload.target_ref,
            notes=payload.notes,
        ),
    )
    return ok(result)


@router.get("/projects/{project_id}/activity")
def api_git_activity(project_id: str, request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.git.read")
    items = _list_git_activity(db, project_id=project_id, limit=limit)
    return ok([_serialize_git_activity(item) for item in items])


@router.get("/activity")
def api_git_activity_all(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="git.activity.read")
    items = _list_git_activity(db, limit=limit)
    return ok([_serialize_git_activity(item) for item in items])
