from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.runner import Runner
from app.modules.tasks.service import claim_next_ready_task

from .schemas import RunnerHeartbeat, RunnerRegister


def list_runners(db: Session) -> list[Runner]:
    return list(db.scalars(select(Runner).options(selectinload(Runner.agents)).order_by(Runner.created_at.desc())))


def get_runner(db: Session, runner_id: str) -> Runner | None:
    stmt = select(Runner).options(selectinload(Runner.agents)).where(Runner.id == runner_id)
    return db.scalar(stmt)


def register_runner(db: Session, payload: RunnerRegister) -> Runner:
    runner = get_runner(db, payload.runner_id)
    if runner is None:
        runner = Runner(
            id=payload.runner_id,
            name=payload.runner_name,
            capabilities=payload.capabilities,
            # Hardware access must come from an existing trusted grant, not self-registration.
            allow_hardware_access=False,
            status="online",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
    else:
        runner.name = payload.runner_name
        runner.capabilities = payload.capabilities
        runner.status = "online"
        runner.last_heartbeat_at = datetime.now(timezone.utc)
    db.add(runner)
    db.commit()
    db.refresh(runner)
    return runner


def heartbeat(db: Session, runner: Runner, payload: RunnerHeartbeat | None = None) -> Runner:
    runner.status = "online"
    runner.last_heartbeat_at = datetime.now(timezone.utc)
    if payload is not None and payload.capabilities is not None:
        runner.capabilities = payload.capabilities
    db.add(runner)
    db.commit()
    db.refresh(runner)
    return runner


def fetch_next_task(db: Session, runner_id: str):
    return claim_next_ready_task(db, runner_id)
