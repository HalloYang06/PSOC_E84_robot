"""Claude Bridge — make the platform a first-class Claude Code companion.

Exposes lightweight read-only context endpoints + a single handoff endpoint so
that a Claude Code session running on a teammate's machine can:

- Pull a compact, prompt-ready project briefing in one call
- Get a copy-pasteable prompt for a specific task / requirement
- Push back a result summary to the platform so progress is visible to teammates

These endpoints are intentionally minimal — they wrap existing read access in
the projects/tasks/requirements modules and never bypass authorization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.common.response import ok
from app.db.models.project import Project
from app.db.models.requirement import Requirement
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.session import get_db
from app.modules.read_access import (
    require_project_read_access,
    require_real_human_principal,
)


router = APIRouter(prefix="/api/claude-bridge", tags=["claude-bridge"])


def _project_brief(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "type": project.project_type,
        "default_branch": project.default_branch,
        "develop_branch": project.develop_branch,
        "github_url": getattr(project, "github_url", None),
        "local_git_url": getattr(project, "local_git_url", None),
        "description": (project.description or "").strip(),
    }


def _task_brief(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "module": task.module,
        "branch": task.branch,
        "summary": (getattr(task, "summary", None) or getattr(task, "description", None) or "").strip(),
        "due_at": task.due_at.isoformat() if getattr(task, "due_at", None) else None,
    }


def _requirement_brief(req: Requirement) -> dict[str, Any]:
    return {
        "id": req.id,
        "title": req.title,
        "type": req.requirement_type,
        "status": req.status,
        "priority": req.priority,
        "context_summary": (req.context_summary or "").strip(),
        "expected_output": (req.expected_output or "").strip(),
        "related_files": list(req.related_files or []),
    }


def _build_prompt(project: Project, task: Task | None, requirement: Requirement | None) -> str:
    """Render a compact prompt that can be pasted directly into Claude Code."""
    lines: list[str] = []
    lines.append(f"# 项目上下文：{project.name}")
    if project.description:
        lines.append(project.description.strip())
    lines.append("")
    lines.append(f"- 仓库：{getattr(project, 'github_url', None) or getattr(project, 'local_git_url', None) or '（未配置）'}")
    lines.append(f"- 主分支：{project.default_branch or 'main'}")
    if project.develop_branch:
        lines.append(f"- 开发分支：{project.develop_branch}")
    lines.append("")
    if task is not None:
        lines.append(f"## 当前任务：{task.title}")
        lines.append(f"- 状态：{task.status} / 优先级：{task.priority}")
        if task.module:
            lines.append(f"- 模块：{task.module}")
        if task.branch:
            lines.append(f"- 分支：{task.branch}")
        summary = (getattr(task, "summary", None) or getattr(task, "description", None) or "").strip()
        if summary:
            lines.append("")
            lines.append(summary)
        lines.append("")
    if requirement is not None:
        lines.append(f"## 需求：{requirement.title}")
        if requirement.context_summary:
            lines.append(requirement.context_summary.strip())
        if requirement.expected_output:
            lines.append("")
            lines.append("**期望产出**：")
            lines.append(requirement.expected_output.strip())
        if requirement.related_files:
            lines.append("")
            lines.append("**相关文件**：")
            for f in requirement.related_files:
                lines.append(f"- `{f}`")
        lines.append("")
    lines.append("---")
    lines.append("请按上述上下文继续工作。完成后用一两句话回复我做了什么、改了哪些文件，便于我归档到平台。")
    return "\n".join(lines).strip() + "\n"


@router.get("/projects/{project_id}/context")
def get_project_context(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Compact JSON briefing for Claude Code: project + recent tasks + open requirements."""
    require_project_read_access(db, request, project_id, action="claude_bridge.context.read")
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)

    recent_tasks = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.updated_at.desc())
            .limit(5)
        )
    )
    open_requirements = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.status.in_(["waiting_response", "in_progress", "needs_changes"]),
            )
            .order_by(Requirement.updated_at.desc())
            .limit(5)
        )
    )

    return ok({
        "project": _project_brief(project),
        "recent_tasks": [_task_brief(t) for t in recent_tasks],
        "open_requirements": [_requirement_brief(r) for r in open_requirements],
        "hints": {
            "claude_code_command": "claude",
            "tip": "复制 prompt 字段到 Claude Code 里即可继续；完成后用 /api/claude-bridge/projects/{id}/handoff 归档。",
        },
        "prompt": _build_prompt(project, recent_tasks[0] if recent_tasks else None, open_requirements[0] if open_requirements else None),
    })


@router.get("/projects/{project_id}/tasks/{task_id}/prompt")
def get_task_prompt(
    project_id: str,
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Render a copy-pasteable Claude Code prompt for a specific task."""
    require_project_read_access(db, request, project_id, action="claude_bridge.task_prompt.read")
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    task = db.get(Task, task_id)
    if task is None or str(task.project_id) != project_id:
        raise AppError("TASK_NOT_FOUND", "task not found in project", status_code=404)

    return ok({
        "task": _task_brief(task),
        "prompt": _build_prompt(project, task, None),
    })


@router.post("/projects/{project_id}/handoff")
def post_project_handoff(
    project_id: str,
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Receive a result summary from a Claude Code session and store it as a task event."""
    principal = require_real_human_principal(db, request)
    require_project_read_access(db, request, project_id, action="claude_bridge.handoff.write")

    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)

    summary = str(payload.get("summary") or "").strip()
    if not summary:
        raise AppError("VALIDATION_ERROR", "summary is required", status_code=422)

    task_id = str(payload.get("task_id") or "").strip() or None
    files_changed = payload.get("files_changed") or []
    if not isinstance(files_changed, list):
        files_changed = []

    if task_id:
        task = db.get(Task, task_id)
        if task is None or str(task.project_id) != project_id:
            raise AppError("TASK_NOT_FOUND", "task not found in project", status_code=404)
        event = TaskEvent(
            task_id=task_id,
            event_type="claude_handoff",
            actor_type="human",
            actor_id=principal.user_id,
            message=summary[:4000],
            data={
                "source": "claude_code",
                "files_changed": [str(f) for f in files_changed][:50],
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return ok({"recorded": True, "event_id": event.id, "task_id": task_id})

    # No task — fall back to recording on a synthetic project-level event log.
    # Since task_events.task_id is non-nullable, we look for the most recent task
    # in the project and attach to it; if there's no task at all, return a hint.
    fallback_task = db.scalar(
        select(Task).where(Task.project_id == project_id).order_by(Task.updated_at.desc()).limit(1)
    )
    if fallback_task is None:
        raise AppError(
            "NO_TASK_TO_ATTACH",
            "project has no task yet; create a task first or pass task_id explicitly",
            status_code=409,
        )
    placeholder = TaskEvent(
        task_id=fallback_task.id,
        event_type="claude_handoff_note",
        actor_type="human",
        actor_id=principal.user_id,
        message=summary[:4000],
        data={
            "source": "claude_code",
            "project_id": project_id,
            "files_changed": [str(f) for f in files_changed][:50],
            "note": "no task_id provided — attached to most recent task as a project-level note",
        },
    )
    db.add(placeholder)
    db.commit()
    db.refresh(placeholder)
    return ok({"recorded": True, "event_id": placeholder.id, "task_id": fallback_task.id, "attached_as_note": True})
