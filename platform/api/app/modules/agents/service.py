from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.usage_log import UsageLog
from app.modules.audit.service import create_audit_log

from . import repo
from .schemas import AgentActionRequest, AgentCreate, AgentUpdate


PROVIDER_LABELS = {
    "manual_codex_thread": "手动线程",
    "codex_cli": "Codex CLI",
    "codex_sdk": "Codex SDK",
    "openai_api": "OpenAI API",
    "openai_responses_api": "OpenAI Responses API",
    "local_runner": "本地 Runner",
    "openhands": "OpenHands",
    "openclaw": "OpenClaw",
}

PROVIDER_KINDS = {
    "manual_codex_thread": "thread",
    "codex_cli": "cli",
    "codex_sdk": "sdk",
    "openai_api": "api",
    "openai_responses_api": "api",
    "local_runner": "runner",
    "openhands": "agent",
    "openclaw": "agent",
}


def serialize_agent_for_read(agent):
    runner = getattr(agent, "runner", None)
    provider_label = PROVIDER_LABELS.get(agent.provider, agent.provider)
    provider_kind = PROVIDER_KINDS.get(agent.provider, "custom")
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "provider": agent.provider,
        "provider_label": provider_label,
        "provider_kind": provider_kind,
        "execution_mode": agent.execution_mode,
        "model": agent.model,
        "agent_type": agent.agent_type,
        "responsibility": agent.responsibility,
        "modules": agent.modules,
        "runner_id": agent.runner_id,
        "runner_name": agent.runner_name,
        "computer_node_id": agent.runner_id,
        "computer_node_name": agent.runner_name or getattr(runner, "name", None),
        "computer_node_status": getattr(runner, "status", None),
        "computer_node_host": getattr(runner, "host", None),
        "computer_node_os": getattr(runner, "os", None),
        "thread_workstation": agent.runner_name or agent.name,
        "permission_level": agent.permission_level,
        "read_paths": agent.read_paths,
        "write_paths": agent.write_paths,
        "max_tokens_per_task": agent.max_tokens_per_task,
        "max_cost_per_day": agent.max_cost_per_day,
        "enabled": agent.enabled,
        "notes": agent.notes,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def list_agents(db: Session):
    return repo.list_agents(db)


def get_agent_or_404(db: Session, agent_id: str):
    agent = repo.get_agent(db, agent_id)
    if agent is None:
        raise AppError("NOT_FOUND", "AI 成员不存在", status_code=404)
    return agent


def create_agent(db: Session, payload: AgentCreate):
    return repo.create_agent(db, payload)


def update_agent(db: Session, agent_id: str, payload: AgentUpdate):
    agent = get_agent_or_404(db, agent_id)
    return repo.update_agent(db, agent, payload)


def set_agent_enabled(db: Session, agent_id: str, enabled: bool, payload: AgentActionRequest):
    agent = get_agent_or_404(db, agent_id)
    before = {"enabled": agent.enabled}
    agent = repo.update_agent(db, agent, AgentUpdate(enabled=enabled))
    create_audit_log(
        db,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="agent.enabled" if enabled else "agent.disabled",
        resource_type="agent",
        resource_id=agent.id,
        before=before,
        after={"enabled": agent.enabled, "note": payload.note},
    )
    db.commit()
    db.refresh(agent)
    return agent


def list_handoff_candidates(db: Session, *, exclude_agent_id: str | None = None):
    items = [agent for agent in list_agents(db) if agent.enabled]
    if exclude_agent_id:
        items = [agent for agent in items if agent.id != exclude_agent_id]
    return items


def get_agent_usage_summary(db: Session, agent_id: str):
    agent = get_agent_or_404(db, agent_id)
    logs = list(
        db.scalars(select(UsageLog).where(UsageLog.agent_id == agent_id).order_by(UsageLog.created_at.desc()).limit(50))
    )
    totals = db.execute(
        select(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.coalesce(func.sum(UsageLog.cached_tokens), 0),
            func.coalesce(func.sum(UsageLog.cost_cents), 0),
        ).where(UsageLog.agent_id == agent_id)
    ).one()
    return {
        "agent": serialize_agent_for_read(agent),
        "summary": {
            "usage_count": totals[0],
            "input_tokens": totals[1],
            "output_tokens": totals[2],
            "cached_tokens": totals[3],
            "cost_cents": totals[4],
        },
        "logs": logs,
    }
