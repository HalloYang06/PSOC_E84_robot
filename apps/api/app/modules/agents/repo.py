from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.agent import Agent

from .schemas import AgentCreate, AgentUpdate


def list_agents(db: Session) -> list[Agent]:
    return list(db.scalars(select(Agent).options(selectinload(Agent.runner)).order_by(Agent.created_at.desc())))


def get_agent(db: Session, agent_id: str) -> Agent | None:
    stmt = select(Agent).options(selectinload(Agent.runner)).where(Agent.id == agent_id)
    return db.scalar(stmt)


def create_agent(db: Session, payload: AgentCreate) -> Agent:
    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def update_agent(db: Session, agent: Agent, payload: AgentUpdate) -> Agent:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent
