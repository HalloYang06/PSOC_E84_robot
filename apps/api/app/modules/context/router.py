from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.access import (
    require_platform_operator_principal,
    resolve_human_principal,
    resolve_project_write_principal,
    resolve_task_write_principal,
)
from app.common.response import ok
from app.db.models.task import Task
from app.db.session import get_db

from .schemas import ContextHealthCreate, ContextHealthRead
from .service import create_context_health_record, get_latest_context_health, list_context_health_records


router = APIRouter(prefix="/api", tags=["context"])


def _serialize(record) -> dict:
    if record is None:
        return {
            "id": "",
            "project_id": None,
            "task_id": "",
            "agent_id": None,
            "usage_ratio": 0.0,
            "health": "green",
            "conversation_turns": 0,
            "files_loaded_count": 0,
            "failed_retry_count": 0,
            "summary": None,
            "recommended_action": None,
            "created_at": None,
        }
    return ContextHealthRead.model_validate(record).model_dump(mode="json")


def _require_task_project_access(db: Session, request: Request, task_id: str) -> None:
    task = db.get(Task, task_id)
    if task is None:
        return
    resolve_project_write_principal(db, request, task.project_id, action="context_health.read")


@router.get("/tasks/{task_id}/context-health")
def get_context_health(task_id: str, request: Request, agent_id: str | None = None, db: Session = Depends(get_db)):
    _require_task_project_access(db, request, task_id)
    record = get_latest_context_health(db, task_id, agent_id)
    return ok(_serialize(record))


@router.get("/tasks/{task_id}/context-health/history")
def list_task_context_health(task_id: str, request: Request, limit: int = 100, db: Session = Depends(get_db)):
    _require_task_project_access(db, request, task_id)
    records = list_context_health_records(db, task_id=task_id, limit=limit)
    return ok([ContextHealthRead.model_validate(item).model_dump(mode="json") for item in records])


@router.get("/context-health")
def list_context_health(
    request: Request,
    task_id: str | None = None,
    project_id: str | None = None,
    agent_id: str | None = None,
    health: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if task_id:
        _require_task_project_access(db, request, task_id)
    elif project_id:
        resolve_project_write_principal(db, request, project_id, action="context_health.read")
    else:
        require_platform_operator_principal(db, request, action="context_health.read")
    records = list_context_health_records(
        db,
        task_id=task_id,
        project_id=project_id,
        agent_id=agent_id,
        health=health,
        limit=limit,
    )
    return ok([ContextHealthRead.model_validate(item).model_dump(mode="json") for item in records])


@router.post("/tasks/{task_id}/context-health")
def create_context_health(task_id: str, payload: ContextHealthCreate, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.context_health.create")
    record = create_context_health_record(db, task_id, payload)
    return ok(ContextHealthRead.model_validate(record).model_dump(mode="json"))


@router.post("/tasks/{task_id}/summarize-context")
def summarize_context(task_id: str, payload: ContextHealthCreate, request: Request, db: Session = Depends(get_db)):
    resolve_task_write_principal(db, request, task_id, action="task.context_health.summarize")
    record = create_context_health_record(db, task_id, payload)
    return ok(ContextHealthRead.model_validate(record).model_dump(mode="json"))
