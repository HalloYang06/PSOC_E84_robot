from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    module: str | None = None
    priority: str = "P2"
    status: str = "draft"
    due_at: datetime | None = None
    branch: str | None = None
    related_issue: str | None = None
    assignee_agent_id: str | None = None
    reviewers: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    module: str | None = None
    priority: str | None = None
    status: str | None = None
    due_at: datetime | None = None
    branch: str | None = None
    related_issue: str | None = None
    assignee_agent_id: str | None = None
    reviewers: list[str] | None = None
    acceptance_criteria: list[str] | None = None


class TaskLogCreate(BaseModel):
    level: str = "info"
    message: str
    runner_id: str | None = None
    data: dict = Field(default_factory=dict)


class TaskResultCreate(BaseModel):
    runner_id: str | None = None
    status: str | None = None
    message: str | None = None
    result: dict = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)


class TaskTransitionCreate(BaseModel):
    status: str
    actor_type: str = "system"
    actor_id: str | None = None
    message: str | None = None
    data: dict = Field(default_factory=dict)


class TaskActionRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    message: str | None = None
    data: dict = Field(default_factory=dict)
    target_ref: str | None = None


class TaskDispatchCreate(BaseModel):
    workstation_id: str = Field(min_length=1, max_length=64)
    status: str = "dispatched"
    notes: str | None = None


class TaskDispatchRead(BaseModel):
    id: str
    task_id: str
    project_id: str
    workstation_id: str
    workstation_name: str | None = None
    agent_id: str | None = None
    computer_node_id: str | None = None
    ai_provider_id: str | None = None
    runner_id: str | None = None
    status: str
    notes: str | None = None
    dispatched_by_user_id: str | None = None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class TaskRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: str | None
    module: str | None
    priority: str
    status: str
    due_at: datetime | None
    branch: str | None
    related_issue: str | None
    assignee_agent_id: str | None
    reviewers: list[str]
    acceptance_criteria: list[str]
    latest_dispatch: TaskDispatchRead | None = None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class TaskEventRead(BaseModel):
    id: str
    task_id: str
    event_type: str
    message: str | None
    data: dict
    actor_type: str
    actor_id: str | None
    created_at: datetime | None

    class Config:
        from_attributes = True
