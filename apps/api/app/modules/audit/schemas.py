from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    task_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    success: bool = True
    error_message: str | None = None


class AuditRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    before: dict
    after: dict
    success: bool
    error_message: str | None
    created_at: datetime | None

    class Config:
        from_attributes = True
