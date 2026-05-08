from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollaborationProviderRead(BaseModel):
    id: str
    project_id: str | None = None
    label: str
    kind: str | None = None
    enabled: bool = True
    endpoint: str | None = None
    model: str | None = None
    sort_order: int = 0
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_aliases(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            if not data.get("label") and data.get("name"):
                data["label"] = data["name"]
            if not data.get("endpoint") and data.get("url"):
                data["endpoint"] = data["url"]
            if not data.get("model") and data.get("default_model"):
                data["model"] = data["default_model"]
            if not data.get("kind") and data.get("type"):
                data["kind"] = data["type"]
            return data
        return value


class CollaborationComputerNodeRead(BaseModel):
    id: str
    project_id: str | None = None
    label: str
    status: str = "offline"
    runner_id: str | None = None
    runner_name: str | None = None
    runner_status: str | None = None
    runner_last_heartbeat_at: datetime | None = None
    runner_heartbeat_age_seconds: int | None = None
    runner_watch_state: str | None = None
    runner_effective_status: str | None = None
    runner_watch_fresh_seconds: int | None = None
    runner_watch_detail: str | None = None
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
    def normalize_node_aliases(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            if not data.get("label") and data.get("name"):
                data["label"] = data["name"]
            if not data.get("os") and data.get("platform"):
                data["os"] = data["platform"]
            if not data.get("connection_kind") and data.get("connection_type"):
                data["connection_kind"] = data["connection_type"]
            if not data.get("connection_kind") and data.get("kind"):
                data["connection_kind"] = data["kind"]
            if not data.get("workspace_root") and data.get("workspace"):
                data["workspace_root"] = data["workspace"]
            if not data.get("workspace_root") and data.get("workspace_path"):
                data["workspace_root"] = data["workspace_path"]
            if not data.get("git_root") and data.get("repo_root"):
                data["git_root"] = data["repo_root"]
            if not data.get("git_root") and data.get("repository_root"):
                data["git_root"] = data["repository_root"]
            if data.get("read_paths") is None and data.get("read_dirs") is not None:
                data["read_paths"] = data["read_dirs"]
            if data.get("read_paths") is None and data.get("readable_paths") is not None:
                data["read_paths"] = data["readable_paths"]
            if data.get("write_paths") is None and data.get("write_dirs") is not None:
                data["write_paths"] = data["write_dirs"]
            if data.get("write_paths") is None and data.get("writable_paths") is not None:
                data["write_paths"] = data["writable_paths"]
            for field_name in ("read_paths", "write_paths"):
                raw = data.get(field_name)
                if isinstance(raw, str):
                    items = [part.strip() for part in raw.replace("\r", "\n").split("\n") if part.strip()]
                    if len(items) == 1 and "," in items[0]:
                        items = [part.strip() for part in items[0].split(",") if part.strip()]
                    data[field_name] = items or None
            return data
        return value


class CollaborationWorkstationRead(BaseModel):
    id: str | None = None
    config_id: str | None = None
    row_id: str | None = None
    project_id: str | None = None
    name: str
    agent_id: str | None = None
    workstation_id: str | None = None
    source_workstation_id: str | None = None
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
        if isinstance(value, dict):
            data = dict(value)
            if not data.get("config_id") and data.get("id"):
                data["config_id"] = data["id"]
            if not data.get("responsibility") and data.get("responsibility_text"):
                data["responsibility"] = data["responsibility_text"]
            if not data.get("responsibility") and data.get("role"):
                data["responsibility"] = data["role"]
            if not data.get("source_workstation_id") and isinstance(data.get("metadata"), dict):
                data["source_workstation_id"] = data["metadata"].get("source_workstation_id")
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
            for field_name in ("read_paths", "write_paths"):
                raw = data.get(field_name)
                if isinstance(raw, str):
                    items = [part.strip() for part in re.split(r"[\n,]+", raw) if part.strip()]
                    data[field_name] = items or None
            if not data.get("description") and data.get("notes"):
                data["description"] = data["notes"]
            if not data.get("notes") and data.get("description"):
                data["notes"] = data["description"]
            return data
        return value


class CollaborationConfigRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    thread_workstations: list[CollaborationWorkstationRead] = Field(default_factory=list)
    ai_providers: list[CollaborationProviderRead] = Field(default_factory=list)
    computer_nodes: list[CollaborationComputerNodeRead] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_topology_aliases(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            if "thread_workstations" not in data and "workstations" in data:
                data["thread_workstations"] = data["workstations"]
            if "ai_providers" not in data and "providers" in data:
                data["ai_providers"] = data["providers"]
            if "computer_nodes" not in data and "nodes" in data:
                data["computer_nodes"] = data["nodes"]
            return data
        return value


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    project_type: str | None = None
    requirement_policy: dict | None = None
    collaboration_config: CollaborationConfigRead | dict | None = None
    github_url: str | None = None
    local_git_url: str | None = None
    default_branch: str = "main"
    develop_branch: str = "develop"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    project_type: str | None = None
    requirement_policy: dict | None = None
    collaboration_config: CollaborationConfigRead | dict | None = None
    github_url: str | None = None
    local_git_url: str | None = None
    default_branch: str | None = None
    develop_branch: str | None = None


class ProjectConfigRead(BaseModel):
    id: str
    name: str
    description: str | None
    project_type: str | None
    requirement_policy: dict | None
    collaboration_config: CollaborationConfigRead | dict | None
    github_url: str | None
    local_git_url: str | None
    default_branch: str
    develop_branch: str
    member_count: int = 0
    invitation_count: int = 0
    pending_invitation_count: int = 0
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    project_type: str | None = None
    requirement_policy: dict | None = None
    collaboration_config: CollaborationConfigRead | dict | None = None
    github_url: str | None = None
    local_git_url: str | None = None
    default_branch: str | None = None
    develop_branch: str | None = None


class ProjectSyncRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    provider: str = "github"
    notes: str | None = None


class ProjectRollbackRequest(BaseModel):
    actor_type: str = "human"
    actor_id: str | None = None
    target_ref: str
    notes: str | None = None


class ProjectPresencePing(BaseModel):
    path: str | None = Field(default=None, max_length=500)


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    project_type: str | None
    requirement_policy: dict | None
    collaboration_config: CollaborationConfigRead | dict | None
    github_url: str | None
    local_git_url: str | None
    default_branch: str
    develop_branch: str
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True
