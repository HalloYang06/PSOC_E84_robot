from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.tasks.schemas import TaskRead


class RunnerRegister(BaseModel):
    runner_id: str
    runner_name: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=list)
    hardware_access: bool = False
    computer_node_id: str | None = None


class RunnerHeartbeat(BaseModel):
    runner_id: str
    capabilities: list[str] | None = None


class RunnerTaskLogCreate(BaseModel):
    level: str = "info"
    message: str
    data: dict = Field(default_factory=dict)


class RunnerTaskResultCreate(BaseModel):
    result: dict = Field(default_factory=dict)
    status: str | None = None
    message: str | None = None
    data: dict = Field(default_factory=dict)


class RunnerTaskTransitionCreate(BaseModel):
    status: str
    message: str | None = None
    data: dict = Field(default_factory=dict)


class RunnerRead(BaseModel):
    id: str
    name: str
    host: str | None
    os: str | None
    capabilities: list[str]
    status: str
    allow_hardware_access: bool
    max_concurrent_tasks: int
    computer_node_id: str | None = None
    computer_node_label: str | None = None
    node_kind: str | None = None
    bound_project_count: int = 0
    computer_node_bindings: list[dict] = Field(default_factory=list)
    agent_count: int | None = None
    current_task: dict | None = None
    recent_errors: list[dict] = Field(default_factory=list)
    recent_events: list[dict] = Field(default_factory=list)
    last_heartbeat_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class RunnerWorkspaceBindingRead(BaseModel):
    project_id: str
    project_name: str
    project_default_branch: str | None = None
    project_develop_branch: str | None = None
    computer_node_id: str
    computer_node_label: str
    computer_node_status: str
    computer_node_host: str | None = None
    computer_node_os: str | None = None
    sort_order: int = 0
    workstation_count: int = 0


class RunnerWorkspaceWorkstationRead(BaseModel):
    project_id: str
    project_name: str
    workstation_id: str
    workstation_name: str
    workstation_status: str
    source: str | None = None
    computer_node_id: str | None = None
    computer_node_label: str | None = None
    ai_provider_id: str | None = None
    ai_provider_label: str | None = None
    agent_id: str | None = None
    description: str | None = None
    notes: str | None = None
    metadata: dict = Field(default_factory=dict)


class RunnerWorkspaceRead(BaseModel):
    runner: RunnerRead
    binding_count: int = 0
    project_count: int = 0
    computer_node_count: int = 0
    bindings: list[RunnerWorkspaceBindingRead] = Field(default_factory=list)
    workstations: list[RunnerWorkspaceWorkstationRead] = Field(default_factory=list)
    active_task_count: int = 0
    recent_errors: list[dict] = Field(default_factory=list)
    recent_events: list[dict] = Field(default_factory=list)


class RunnerTaskDispatchRead(BaseModel):
    runner_id: str
    task: TaskRead | None = None
    id: str | None = None
    title: str | None = None
    status: str | None = None
    commands: list[list[str]] = Field(default_factory=list)
    claimed: bool = False
    note: str | None = None
    workspace: RunnerWorkspaceRead | None = None


class RunnerBindingCreate(BaseModel):
    project_id: str
    computer_node_id: str


class RunnerBindingRead(BaseModel):
    runner_id: str
    project_id: str
    project_name: str
    project_default_branch: str | None = None
    project_develop_branch: str | None = None
    computer_node_id: str
    computer_node_label: str
    computer_node_status: str
    computer_node_host: str | None = None
    computer_node_os: str | None = None
    sort_order: int = 0
    workstation_count: int = 0


class RunnerBindingDeleteRead(BaseModel):
    runner_id: str
    project_id: str
    computer_node_id: str
    status: str = "unbound"


class RunnerThreadWorkstationSyncItem(BaseModel):
    workstation_id: str
    workstation_name: str
    workstation_status: str = "idle"
    agent_id: str | None = None
    ai_provider_id: str | None = None
    ai_provider_label: str | None = None
    description: str | None = None
    notes: str | None = None
    cwd: str | None = None
    model: str | None = None
    skill_loadout: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class RunnerThreadWorkstationSyncCreate(BaseModel):
    project_id: str
    computer_node_id: str
    workstations: list[RunnerThreadWorkstationSyncItem] = Field(default_factory=list)


class RunnerDeviceInterfaceRead(BaseModel):
    id: str
    kind: str
    name: str
    status: str = "unknown"
    transport: str | None = None
    details: dict = Field(default_factory=dict)
    read_capability: bool = True
    write_capability: str = "review_required"
    risk_level: str = "medium"


class RunnerDeviceInterfaceScanCreate(BaseModel):
    project_id: str
    computer_node_id: str
    platform: str | None = None
    host: str | None = None
    scanner_version: str | None = None
    scanned_at: datetime | None = None
    interfaces: list[RunnerDeviceInterfaceRead] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RunnerDeviceInterfaceScanRead(BaseModel):
    runner_id: str
    project_id: str
    computer_node_id: str
    status: str = "completed"
    platform: str | None = None
    host: str | None = None
    scanner_version: str | None = None
    scanned_at: datetime | str | None = None
    interface_count: int = 0
    interfaces: list[RunnerDeviceInterfaceRead] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
