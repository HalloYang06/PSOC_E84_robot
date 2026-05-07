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
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.requirement import Requirement
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.session import get_db
from app.modules.handoffs.schemas import HandoffPackageCreate
from app.modules.handoffs.service import _to_read_dict as _handoff_to_read_dict
from app.modules.handoffs.service import create_handoff
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


def _npc_metadata(npc: ProjectThreadWorkstation) -> dict[str, Any]:
    raw = getattr(npc, "extra_data", None) or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _resolve_project_npc(db: Session, project_id: str, npc_id: str) -> ProjectThreadWorkstation | None:
    """Look up an NPC seat by PK, config_id, name, or agent_id within a project.

    The frontend passes whatever id field it has on hand; the JSON-backed list
    endpoint returns `id == config_id` while the table PK is a separate UUID,
    so we accept all common identifiers to avoid 404s on legitimate calls.
    """
    cleaned = str(npc_id or "").strip()
    if not cleaned:
        return None
    return db.scalar(
        select(ProjectThreadWorkstation).where(
            ProjectThreadWorkstation.project_id == project_id,
            (ProjectThreadWorkstation.id == cleaned)
            | (ProjectThreadWorkstation.config_id == cleaned)
            | (ProjectThreadWorkstation.name == cleaned)
            | (ProjectThreadWorkstation.agent_id == cleaned),
        )
    )


def _npc_brief(npc: ProjectThreadWorkstation) -> dict[str, Any]:
    meta = _npc_metadata(npc)
    knowledge = meta.get("npc_knowledge") if isinstance(meta.get("npc_knowledge"), dict) else {}
    return {
        "id": npc.id,
        "name": npc.name,
        "config_id": npc.config_id,
        "responsibility": (npc.description or meta.get("responsibility") or "").strip(),
        "current_thread": {
            "provider_id": npc.ai_provider_id or meta.get("ai_provider_id"),
            "provider_label": meta.get("ai_provider") or meta.get("provider_label"),
            "model": meta.get("model") or "",
            "computer_node_id": npc.computer_node_id or meta.get("computer_node_id"),
        },
        "permission_level": meta.get("permission_level") or "L2",
        "automation_enabled": bool(meta.get("automation_enabled")),
        "skill_loadout": list(meta.get("skill_loadout") or []),
        "knowledge": {
            "summary": (knowledge.get("summary") or meta.get("knowledge_summary") or "").strip(),
            "handoff_path": (knowledge.get("handoff_path") or meta.get("knowledge_handoff_path") or "").strip(),
        },
        "status": npc.status,
    }


def _build_npc_prompt(
    project: Project,
    npc: ProjectThreadWorkstation,
    recent_tasks: list[Task],
    recent_handoff_events: list[TaskEvent],
) -> str:
    """Pack a complete handoff prompt for a new AI taking over an NPC's role.

    Goal (per user 2026-05-06): "switching the AI behind an NPC should not
    require re-teaching the new AI". So this prompt includes the NPC's
    long-lived role, knowledge summary, skill loadout, and recent handoffs.
    """
    meta = _npc_metadata(npc)
    knowledge = meta.get("npc_knowledge") if isinstance(meta.get("npc_knowledge"), dict) else {}
    skills = list(meta.get("skill_loadout") or [])

    lines: list[str] = []
    lines.append(f"# 你接手的岗位：{npc.name}")
    responsibility = (npc.description or meta.get("responsibility") or "").strip()
    if responsibility:
        lines.append("")
        lines.append("## 这个岗位负责什么")
        lines.append(responsibility)
    lines.append("")
    lines.append("## 项目上下文")
    lines.append(f"- 项目：{project.name}")
    if project.description:
        lines.append(f"- 简介：{project.description.strip()}")
    repo = getattr(project, "github_url", None) or getattr(project, "local_git_url", None)
    if repo:
        lines.append(f"- 仓库：{repo}")
    lines.append(f"- 主分支：{project.default_branch or 'main'}")
    if project.develop_branch:
        lines.append(f"- 开发分支：{project.develop_branch}")
    lines.append("")
    knowledge_summary = (knowledge.get("summary") or meta.get("knowledge_summary") or "").strip()
    if knowledge_summary:
        lines.append("## 这个岗位的长期知识（前任沉淀，请视为权威）")
        lines.append(knowledge_summary)
        handoff_path = (knowledge.get("handoff_path") or meta.get("knowledge_handoff_path") or "").strip()
        if handoff_path:
            lines.append("")
            lines.append(f"_完整知识文档路径：`{handoff_path}`（如需深入请打开阅读）_")
        lines.append("")
    if skills:
        lines.append("## 已装备的 Skill（你可以并应该使用这些能力）")
        for s in skills:
            lines.append(f"- {s}")
        lines.append("")
    if recent_tasks:
        lines.append("## 最近任务（按时间倒序）")
        for t in recent_tasks[:3]:
            summary = (getattr(t, "summary", None) or getattr(t, "description", None) or "").strip()
            lines.append(f"- **{t.title}** [{t.status} / {t.priority}]")
            if summary:
                lines.append(f"  {summary[:280]}")
        lines.append("")
    if recent_handoff_events:
        lines.append("## 前任 AI 的交接记录")
        for ev in recent_handoff_events[:3]:
            msg = (ev.message or "").strip()
            if msg:
                lines.append(f"- {msg[:400]}")
        lines.append("")
    permission_level = meta.get("permission_level") or "L2"
    automation = "已开启自动化" if meta.get("automation_enabled") else "默认手动审批"
    lines.append("## 工作约束")
    lines.append(f"- 权限等级：{permission_level}")
    lines.append(f"- 自动化：{automation}")
    lines.append("- 高风险动作（硬件烧录、git push、删除）必须先走人工审批，不要自行执行")
    lines.append("")
    lines.append("---")
    lines.append("请先用一两句话告诉我你理解这个岗位的核心职责是什么、当前最重要的事是什么，再开始工作。")
    lines.append("完成后用 `POST /api/claude-bridge/projects/{project_id}/handoff` 把工作摘要回传，便于下一任 AI 接手。")
    return "\n".join(lines).strip() + "\n"


@router.get("/projects/{project_id}/npcs/{npc_id}/context")
def get_npc_context(
    project_id: str,
    npc_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Pack a complete onboarding prompt for an AI taking over this NPC's seat.

    This is the core of "reduce AI handover cost": include the NPC's role,
    long-term knowledge, skill loadout, recent tasks, and handoff history so
    that any new AI can pick up the work without being re-taught.
    """
    require_project_read_access(db, request, project_id, action="claude_bridge.npc_context.read")
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    npc = _resolve_project_npc(db, project_id, npc_id)
    if npc is None:
        raise AppError("NPC_NOT_FOUND", "npc not found in project", status_code=404)

    recent_tasks = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.assignee_agent_id == npc.agent_id)
            .order_by(Task.updated_at.desc())
            .limit(5)
        )
    ) if npc.agent_id else []

    if not recent_tasks:
        recent_tasks = list(
            db.scalars(
                select(Task)
                .where(Task.project_id == project_id)
                .order_by(Task.updated_at.desc())
                .limit(3)
            )
        )

    task_ids = [t.id for t in recent_tasks]
    handoff_events: list[TaskEvent] = []
    if task_ids:
        handoff_events = list(
            db.scalars(
                select(TaskEvent)
                .where(
                    TaskEvent.task_id.in_(task_ids),
                    TaskEvent.event_type.in_(["claude_handoff", "claude_handoff_note", "handoff", "context_handoff"]),
                )
                .order_by(TaskEvent.created_at.desc())
                .limit(5)
            )
        )

    return ok({
        "project": _project_brief(project),
        "npc": _npc_brief(npc),
        "recent_tasks": [_task_brief(t) for t in recent_tasks],
        "recent_handoffs": [
            {
                "task_id": ev.task_id,
                "event_type": ev.event_type,
                "message": (ev.message or "").strip(),
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in handoff_events
        ],
        "hints": {
            "tip": "把 prompt 字段粘到新 Claude Code/Codex/Qwen 线程中，新 AI 即可零指导接手这个岗位。",
        },
        "prompt": _build_npc_prompt(project, npc, recent_tasks, handoff_events),
    })


@router.post("/projects/{project_id}/npcs/{npc_id}/handoff")
def post_npc_handoff(
    project_id: str,
    npc_id: str,
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Pack the NPC onboarding prompt and persist a Handoff record in one call.

    Closes the "NPC reduces AI handover cost" loop: the existing GET endpoint
    only renders a prompt; this writes the same handover into the Handoffs
    table so qualification scorecard / handoff history can see it, and so the
    next AI taking the seat can read past handovers.
    """
    principal = require_real_human_principal(db, request)
    require_project_read_access(db, request, project_id, action="claude_bridge.npc_handoff.write")

    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    npc = _resolve_project_npc(db, project_id, npc_id)
    if npc is None:
        raise AppError("NPC_NOT_FOUND", "npc not found in project", status_code=404)

    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise AppError("VALIDATION_ERROR", "task_id is required", status_code=422)
    task = db.get(Task, task_id)
    if task is None or str(task.project_id) != project_id:
        raise AppError("TASK_NOT_FOUND", "task not found in project", status_code=404)

    recent_tasks_for_prompt = [task]
    handoff_events = list(
        db.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task_id,
                TaskEvent.event_type.in_(["claude_handoff", "claude_handoff_note", "handoff", "context_handoff"]),
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(3)
        )
    )
    prompt = _build_npc_prompt(project, npc, recent_tasks_for_prompt, handoff_events)

    summary_input = str(payload.get("summary") or "").strip()
    if not summary_input:
        first_block = prompt.strip().split("\n\n", 1)[0]
        summary_input = first_block[:600]

    next_steps_raw = payload.get("next_steps") or []
    if isinstance(next_steps_raw, list):
        next_steps = [str(s).strip() for s in next_steps_raw if str(s).strip()][:20]
    else:
        next_steps = []

    notes_input = str(payload.get("notes") or "").strip() or None

    meta = _npc_metadata(npc)
    context_health_raw = meta.get("context_health") if isinstance(meta.get("context_health"), dict) else {}

    create_payload = HandoffPackageCreate(
        project_id=project_id,
        task_id=task_id,
        handoff_from=npc.agent_id or npc.id,
        handoff_to=None,
        summary=summary_input or None,
        reason="npc_thread_handover",
        current_status="prepared",
        next_steps=next_steps,
        notes=notes_input,
        context_health=dict(context_health_raw or {}),
        payload={
            "source": "claude_bridge.npc_handoff",
            "npc_id": npc.id,
            "npc_config_id": npc.config_id,
            "npc_name": npc.name,
            "initiated_by_user_id": principal.user_id,
        },
    )
    handoff = create_handoff(db, create_payload)

    return ok({
        "prompt": prompt,
        "handoff": _handoff_to_read_dict(handoff),
        "npc": _npc_brief(npc),
        "task": _task_brief(task),
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
