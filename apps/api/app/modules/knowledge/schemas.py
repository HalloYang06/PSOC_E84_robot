from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    repo_relative_path: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=700)
    scope: str = "project"
    owner_type: str | None = None
    owner_id: str | None = None
    exists_in_repo: bool | None = None
    version_ref: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    last_synced_at: datetime | None = None
    metadata: dict | None = Field(default=None, alias="extra_data")


class KnowledgeDocumentRead(KnowledgeDocumentCreate):
    id: str
    project_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
        populate_by_name = True


class ProjectSkillCreate(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    source: str = "custom"
    category: str | None = None
    repo_relative_path: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=700)
    description: str | None = None
    recommended_for: list[str] | None = None
    exists_in_repo: bool | None = None
    version_ref: str | None = None
    last_synced_at: datetime | None = None
    metadata: dict | None = Field(default=None, alias="extra_data")


class ProjectSkillRead(ProjectSkillCreate):
    id: str
    project_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
        populate_by_name = True


class SeatSkillAssignmentCreate(BaseModel):
    seat_id: str = Field(min_length=1, max_length=64)
    skill_id: str = Field(min_length=1, max_length=120)
    assignment_type: str = "direct"
    status: str = "active"
    notes: str | None = None
    metadata: dict | None = Field(default=None, alias="extra_data")


class SeatSkillAssignmentRead(SeatSkillAssignmentCreate):
    id: str
    project_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
        populate_by_name = True
