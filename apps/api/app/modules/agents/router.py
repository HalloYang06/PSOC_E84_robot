from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import require_platform_operator_principal
from app.common.response import ok
from app.db.session import get_db
from app.modules.usage.schemas import UsageRead

from .schemas import AgentActionRequest, AgentCreate, AgentRead, AgentUpdate
from .service import (
    create_agent,
    get_agent_or_404,
    get_agent_usage_summary,
    list_agents,
    list_handoff_candidates,
    serialize_agent_for_read,
    set_agent_enabled,
    update_agent,
)


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def api_list_agents(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.read")
    return ok([AgentRead.model_validate(serialize_agent_for_read(item)).model_dump(mode="json") for item in list_agents(db)])


@router.post("")
def api_create_agent(payload: AgentCreate, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.create")
    return ok(AgentRead.model_validate(serialize_agent_for_read(create_agent(db, payload))).model_dump(mode="json"))


@router.get("/handoff-candidates")
def api_handoff_candidates(request: Request, exclude_agent_id: str | None = None, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.read")
    items = list_handoff_candidates(db, exclude_agent_id=exclude_agent_id)
    return ok([AgentRead.model_validate(serialize_agent_for_read(item)).model_dump(mode="json") for item in items])


@router.get("/{agent_id}")
def api_get_agent(agent_id: str, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.read")
    return ok(AgentRead.model_validate(serialize_agent_for_read(get_agent_or_404(db, agent_id))).model_dump(mode="json"))


@router.patch("/{agent_id}")
def api_update_agent(agent_id: str, payload: AgentUpdate, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.update")
    return ok(AgentRead.model_validate(serialize_agent_for_read(update_agent(db, agent_id, payload))).model_dump(mode="json"))


@router.post("/{agent_id}/enable")
def api_enable_agent(agent_id: str, payload: AgentActionRequest, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.enable")
    return ok(AgentRead.model_validate(serialize_agent_for_read(set_agent_enabled(db, agent_id, True, payload))).model_dump(mode="json"))


@router.post("/{agent_id}/disable")
def api_disable_agent(agent_id: str, payload: AgentActionRequest, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.disable")
    return ok(AgentRead.model_validate(serialize_agent_for_read(set_agent_enabled(db, agent_id, False, payload))).model_dump(mode="json"))


@router.get("/{agent_id}/usage")
def api_agent_usage(agent_id: str, request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="agents.read")
    data = get_agent_usage_summary(db, agent_id)
    return ok(
        {
            "agent": AgentRead.model_validate(data["agent"]).model_dump(mode="json"),
            "summary": data["summary"],
            "logs": [UsageRead.model_validate(item).model_dump(mode="json") for item in data["logs"]],
        }
    )
