from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str | None = None
    provider: str = "manual_codex_thread"
    execution_mode: str = "manual"
    model: str | None = None
    agent_type: str | None = None
    responsibility: str | None = None
    modules: list[str] = Field(default_factory=list)
    runner_id: str | None = None
    runner_name: str | None = None
    permission_level: str = "L2"
    read_paths: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)
    max_tokens_per_task: int | None = None
    max_cost_per_day: int | None = None
    enabled: bool = True
    notes: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    provider: str | None = None
    execution_mode: str | None = None
    model: str | None = None
    agent_type: str | None = None
    responsibility: str | None = None
    modules: list[str] | None = None
    runner_id: str | None = None
    runner_name: str | None = None
    permission_level: str | None = None
    read_paths: list[str] | None = None
    write_paths: list[str] | None = None
    max_tokens_per_task: int | None = None
    max_cost_per_day: int | None = None
    enabled: bool | None = None
    notes: str | None = None


class AgentRead(BaseModel):
    id: str
    name: str
    role: str | None
    provider: str
    provider_label: str | None = None
    provider_kind: str | None = None
    execution_mode: str
    model: str | None
    agent_type: str | None
    responsibility: str | None
    modules: list[str]
    runner_id: str | None
    runner_name: str | None
    computer_node_id: str | None = None
    computer_node_name: str | None = None
    computer_node_status: str | None = None
    computer_node_host: str | None = None
    computer_node_os: str | None = None
    thread_workstation: str | None = None
    permission_level: str
    read_paths: list[str]
    write_paths: list[str]
    max_tokens_per_task: int | None
    max_cost_per_day: int | None
    enabled: bool
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class AgentActionRequest(BaseModel):
    actor_type: str = "system"
    actor_id: str | None = None
    note: str | None = None
