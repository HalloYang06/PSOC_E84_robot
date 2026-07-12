from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UsageCreate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_cents: int = 0
    status: str = "completed"


class UsageRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    agent_id: str | None
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_cents: int
    status: str
    created_at: datetime | None

    class Config:
        from_attributes = True

