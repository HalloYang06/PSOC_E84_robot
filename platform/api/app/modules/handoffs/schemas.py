from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HandoffPackageCreate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    handoff_from: str | None = None
    handoff_to: str | None = None
    summary: str | None = None
    reason: str | None = None
    current_status: str | None = None
    latest_files: list[str] = Field(default_factory=list)
    latest_diff: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    linked_requirement_ids: list[str] = Field(default_factory=list)
    linked_approval_ids: list[str] = Field(default_factory=list)
    context_health: dict = Field(default_factory=dict)
    notes: str | None = None
    payload: dict = Field(default_factory=dict)


class HandoffPackageRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str
    handoff_from: str | None
    handoff_to: str | None
    summary: str | None
    reason: str | None
    current_status: str | None
    latest_files: list[str]
    latest_diff: str | None
    open_questions: list[str]
    next_steps: list[str]
    blocked_by: list[str]
    linked_requirement_ids: list[str]
    linked_approval_ids: list[str]
    context_health: dict
    notes: str | None
    payload: dict
    created_at: datetime | None

    class Config:
        from_attributes = True


class HandoffAcceptRequest(BaseModel):
    actor_type: str = "agent"
    actor_id: str | None = None
    note: str | None = None


class HandoffAssignRequest(BaseModel):
    handoff_to: str
    actor_type: str = "system"
    actor_id: str | None = None
    note: str | None = None
