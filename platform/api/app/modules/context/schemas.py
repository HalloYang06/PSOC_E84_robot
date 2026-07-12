from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ContextHealthCreate(BaseModel):
    project_id: str | None = None
    agent_id: str | None = None
    usage_ratio: float = 0.0
    health: str = "green"
    conversation_turns: int = 0
    files_loaded_count: int = 0
    failed_retry_count: int = 0
    summary: str | None = None
    recommended_action: str | None = None


class ContextHealthRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str
    agent_id: str | None
    usage_ratio: float
    health: str
    conversation_turns: int
    files_loaded_count: int
    failed_retry_count: int
    summary: str | None
    recommended_action: str | None
    created_at: datetime | None

    class Config:
        from_attributes = True
