from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    bio: str | None = None
    is_active: bool = True


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    bio: str | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    id: str
    name: str
    email: str | None
    display_name: str | None
    bio: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectInviteCreate(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    role: str = "member"
    invited_by_user_id: str | None = None
    message: str | None = None
    expires_at: datetime | None = None


class ProjectInviteUpdate(BaseModel):
    status: str | None = None
    message: str | None = None
    accepted_by_user_id: str | None = None
    expires_at: datetime | None = None


class ProjectInviteAcceptRequest(BaseModel):
    user_id: str
    actor_type: str = "human"
    actor_id: str | None = None
    note: str | None = None


class ProjectInviteRead(BaseModel):
    id: str
    project_id: str
    email: str | None
    role: str
    token: str | None = None
    status: str
    invited_by_user_id: str | None
    accepted_by_user_id: str | None
    message: str | None
    expires_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectMemberCreate(BaseModel):
    user_id: str
    role: str = "member"
    is_owner: bool = False
    status: str = "active"


class ProjectMemberUpdate(BaseModel):
    role: str | None = None
    is_owner: bool | None = None
    status: str | None = None


class ProjectMemberRead(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: str
    status: str
    is_owner: bool
    joined_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    user: UserRead | None = None

    class Config:
        from_attributes = True


class CollaborationSummaryRead(BaseModel):
    users: int
    pending_invites: int
    members: int


class CollaborationMessageCreate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    approval_id: str | None = None
    handoff_id: str | None = None
    requirement_id: str | None = None
    agent_id: str | None = None
    message_type: str = "comment_message"
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)
    sender_type: str = "human"
    sender_id: str | None = None
    recipient_type: str | None = None
    recipient_id: str | None = None
    status: str = "open"
    metadata: dict | None = Field(default=None, alias="extra_data")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _accept_metadata_alias(cls, value):
        if isinstance(value, dict) and "metadata" in value and "extra_data" not in value:
            data = dict(value)
            data["extra_data"] = data.pop("metadata")
            return data
        return value


class CollaborationMessageUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = None
    status: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_has_update(self):
        if self.title is None and self.body is None and self.status is None:
            raise ValueError("At least one collaboration message field must be updated")
        return self


class CollaborationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    project_id: str | None
    task_id: str | None
    approval_id: str | None
    handoff_id: str | None
    requirement_id: str | None
    agent_id: str | None
    dispatch_id: str | None
    message_type: str
    title: str | None
    body: str
    sender_type: str
    sender_id: str | None
    recipient_type: str | None
    recipient_id: str | None
    status: str
    metadata: dict | None = Field(default=None, alias="extra_data")
    created_at: datetime | None
    updated_at: datetime | None


class CollaborationMessagePreviewRead(BaseModel):
    project_id: str
    task_id: str | None = None
    approval_id: str | None = None
    handoff_id: str | None = None
    requirement_id: str | None = None
    agent_id: str | None = None
    message_type: str
    title: str | None = None
    body: str
    sender_type: str
    sender_id: str | None = None
    recipient_type: str | None = None
    recipient_id: str | None = None
    recipient_label: str | None = None
    status: str
    ready: bool = False
    preview_signature: str
    pending_target_message_count: int = 0
    recent_same_type_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preview_notes: list[str] = Field(default_factory=list)
    next_step: str | None = None


class RunnerRelayCommandCreate(BaseModel):
    task_id: str | None = None
    dispatch_id: str | None = None
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)
    runner_id: str | None = None
    computer_node_id: str | None = None
    workstation_id: str | None = None

    @model_validator(mode="after")
    def validate_single_target(self):
        targets = [self.dispatch_id, self.runner_id, self.computer_node_id, self.workstation_id]
        count = sum(1 for value in targets if value)
        if count != 1:
            raise ValueError("Exactly one of dispatch_id, runner_id, computer_node_id, workstation_id must be provided")
        return self


class RunnerRelayMessageRead(BaseModel):
    id: str
    project_id: str
    task_id: str | None = None
    dispatch_id: str | None = None
    title: str | None = None
    body: str
    status: str
    message_type: str
    sender_type: str
    sender_id: str | None = None
    recipient_type: str | None = None
    recipient_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class RunnerRelayAckCreate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class RunnerRelayCompleteCreate(BaseModel):
    result_status: str = Field(default="completed", pattern="^(completed|failed)$")
    note: str | None = Field(default=None, max_length=4000)


class WorkstationInboxAckCreate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class WorkstationInboxCompleteCreate(BaseModel):
    result_status: str = Field(default="completed", pattern="^(completed|failed)$")
    note: str | None = Field(default=None, max_length=4000)


class WorkstationAdapterConfigRead(BaseModel):
    project_id: str
    workstation_id: str
    workstation_name: str
    computer_node_id: str | None = None
    provider_id: str | None = None
    provider_label: str | None = None
    model: str | None = None
    executor_command: str | None = None
    executor_cwd: str | None = None
    executor_timeout_seconds: int | None = None
    settings_source: dict[str, str] = Field(default_factory=dict)


class CollaborationProviderCreate(BaseModel):
    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    kind: str | None = None
    enabled: bool = True
    endpoint: str | None = None
    model: str | None = None
    sort_order: int = 0
    metadata: dict | None = None


class CollaborationProviderUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = None
    enabled: bool | None = None
    endpoint: str | None = None
    model: str | None = None
    sort_order: int | None = None
    metadata: dict | None = None


def _normalize_path_list(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[\n,]+", value) if part.strip()]
        return items or None
    if isinstance(value, (list, tuple, set)):
        items = [str(part).strip() for part in value if str(part).strip()]
        return items or None
    text = str(value).strip()
    return [text] if text else None


def _normalize_workstation_aliases(value: object | None) -> object | None:
    if not isinstance(value, dict):
        return value
    data = dict(value)
    if not data.get("responsibility") and data.get("responsibility_text"):
        data["responsibility"] = data["responsibility_text"]
    if not data.get("responsibility") and data.get("role"):
        data["responsibility"] = data["role"]
    if not data.get("model") and data.get("default_model"):
        data["model"] = data["default_model"]
    if not data.get("model") and data.get("model_name"):
        data["model"] = data["model_name"]
    if not data.get("permission_level") and data.get("permissionLevel"):
        data["permission_level"] = data["permissionLevel"]
    if not data.get("permission_level") and data.get("permission"):
        data["permission_level"] = data["permission"]
    if not data.get("permission_level") and data.get("access_level"):
        data["permission_level"] = data["access_level"]
    if data.get("read_paths") is None and data.get("read_dirs") is not None:
        data["read_paths"] = data["read_dirs"]
    if data.get("read_paths") is None and data.get("readable_paths") is not None:
        data["read_paths"] = data["readable_paths"]
    if data.get("write_paths") is None and data.get("write_dirs") is not None:
        data["write_paths"] = data["write_dirs"]
    if data.get("write_paths") is None and data.get("writable_paths") is not None:
        data["write_paths"] = data["writable_paths"]
    data["read_paths"] = _normalize_path_list(data.get("read_paths"))
    data["write_paths"] = _normalize_path_list(data.get("write_paths"))
    return data


class CollaborationComputerNodeCreate(BaseModel):
    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    status: str = "offline"
    runner_id: str | None = None
    connection_kind: str | None = None
    workspace_root: str | None = None
    git_root: str | None = None
    read_paths: list[str] | None = None
    write_paths: list[str] | None = None
    host: str | None = None
    os: str | None = None
    sort_order: int = 0
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_path_aliases(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            for field_name in ("read_paths", "write_paths"):
                raw = data.get(field_name)
                if isinstance(raw, str):
                    items = [part.strip() for part in re.split(r"[,\n]+", raw) if part.strip()]
                    data[field_name] = items or None
            return data
        return value


class CollaborationComputerNodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None
    runner_id: str | None = None
    connection_kind: str | None = None
    workspace_root: str | None = None
    git_root: str | None = None
    read_paths: list[str] | None = None
    write_paths: list[str] | None = None
    host: str | None = None
    os: str | None = None
    sort_order: int | None = None
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_path_aliases(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            for field_name in ("read_paths", "write_paths"):
                raw = data.get(field_name)
                if isinstance(raw, str):
                    items = [part.strip() for part in re.split(r"[,\n]+", raw) if part.strip()]
                    data[field_name] = items or None
            return data
        return value


class CollaborationWorkstationCreate(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    agent_id: str | None = None
    computer_node: str | None = None
    computer_node_id: str | None = None
    ai_provider: str | None = None
    ai_provider_id: str | None = None
    responsibility: str | None = None
    model: str | None = None
    permission_level: str | None = None
    read_paths: list[str] | None = None
    write_paths: list[str] | None = None
    status: str = "idle"
    description: str | None = None
    notes: str | None = None
    sort_order: int = 0
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_workstation_aliases(cls, value):
        return _normalize_workstation_aliases(value)


class CollaborationWorkstationUpdate(BaseModel):
    id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    agent_id: str | None = None
    computer_node: str | None = None
    computer_node_id: str | None = None
    ai_provider: str | None = None
    ai_provider_id: str | None = None
    responsibility: str | None = None
    model: str | None = None
    permission_level: str | None = None
    read_paths: list[str] | None = None
    write_paths: list[str] | None = None
    status: str | None = None
    description: str | None = None
    notes: str | None = None
    sort_order: int | None = None
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_workstation_aliases(cls, value):
        return _normalize_workstation_aliases(value)


class CollaborationConfigUpdate(BaseModel):
    thread_workstations: list[CollaborationWorkstationCreate] | None = None
    ai_providers: list[CollaborationProviderCreate] | None = None
    computer_nodes: list[CollaborationComputerNodeCreate] | None = None
    review_policy: dict | None = None
    workstation_profiles: dict | None = None


class ComputerNodePairingTokenRead(BaseModel):
    project_id: str
    computer_node_id: str
    computer_node_label: str
    token: str | None = None
    token_available: bool = False
    issued_at: datetime | None = None
    last_used_at: datetime | None = None


class WorkstationAdapterTokenRead(BaseModel):
    project_id: str
    workstation_id: str
    workstation_name: str
    token: str | None = None
    token_available: bool = False
    issued_at: datetime | None = None
    last_used_at: datetime | None = None
