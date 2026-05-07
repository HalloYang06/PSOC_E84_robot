from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RequirementMessageCreate(BaseModel):
    sender_type: str = "agent"
    sender_id: str | None = None
    message: str = Field(min_length=1)
    status_after_reply: str | None = None


class RequirementMessageRead(BaseModel):
    id: str
    requirement_id: str
    sender_type: str
    sender_id: str | None
    message: str
    status_after_reply: str | None
    created_at: datetime | None

    class Config:
        from_attributes = True


class RequirementCreate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    requirement_type: str = "thread_request"
    module: str | None = None
    priority: str = "high"
    status: str = "waiting_response"
    from_agent: str | None = None
    to_agent: str | None = None
    context_summary: str | None = None
    expected_output: str | None = None
    related_files: list[str] = Field(default_factory=list)
    max_response_tokens: int = 3000
    opening_message: str | None = None


class RequirementUpdate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    title: str | None = None
    requirement_type: str | None = None
    module: str | None = None
    priority: str | None = None
    status: str | None = None
    from_agent: str | None = None
    to_agent: str | None = None
    context_summary: str | None = None
    expected_output: str | None = None
    related_files: list[str] | None = None
    max_response_tokens: int | None = None


class RequirementReplyCreate(BaseModel):
    sender_type: str = "agent"
    sender_id: str | None = None
    message: str = Field(min_length=1)
    status: str | None = None


class RequirementRouteRequest(BaseModel):
    to_agent: str | None = None
    from_agent: str | None = None
    note: str | None = None


class RequirementDispatchRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    target_type: str = Field(default="workstation", pattern="^(workstation|agent|human)$")
    target_id: str = Field(min_length=1, max_length=128)
    note: str | None = None
    status: str = "queued"
    title: str | None = Field(default=None, max_length=300)
    body: str | None = None


class RequirementFinalReplyRequest(BaseModel):
    sender_type: str = Field(default="agent", pattern="^(agent|human|runner|system)$")
    sender_id: str | None = None
    recipient_type: str = Field(default="project", pattern="^(project|human|agent|workstation)$")
    recipient_id: str | None = None
    message: str = Field(min_length=1)
    status: str = Field(default="done", pattern="^(in_progress|done)$")
    title: str | None = Field(default=None, max_length=300)


class RequirementActionRequest(BaseModel):
    actor_type: str = "system"
    actor_id: str | None = None
    note: str | None = None
    status: str | None = None


class RequirementPromoteRequest(BaseModel):
    actor_type: str = "system"
    actor_id: str | None = None
    target_type: str = "knowledge"
    status: str | None = None
    note: str | None = None


class RequirementRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    title: str
    requirement_type: str
    module: str | None
    priority: str
    status: str
    from_agent: str | None
    to_agent: str | None
    context_summary: str | None
    expected_output: str | None
    related_files: list[str]
    max_response_tokens: int
    response_count: int
    last_response_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    messages: list[RequirementMessageRead] = Field(default_factory=list)

    class Config:
        from_attributes = True
