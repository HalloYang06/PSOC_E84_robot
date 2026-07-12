from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BossPlanItemCreate(BaseModel):
    role: str = Field(min_length=1, max_length=160)
    target_seat_id: str | None = Field(default=None, max_length=64)
    target_name: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    status: str = Field(default="planned", max_length=32)
    dispatch_message_id: str | None = Field(default=None, max_length=64)
    receipt_message_id: str | None = Field(default=None, max_length=64)
    sort_order: int = 0
    skills: list[str] | None = None
    knowledge_paths: list[str] | None = None
    acceptance: str | None = None
    metadata: dict | None = Field(default=None, alias="extra_data")

    model_config = ConfigDict(populate_by_name=True)


class BossPlanCreate(BaseModel):
    boss_seat_id: str | None = Field(default=None, max_length=64)
    goal: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=240)
    status: str = Field(default="draft", max_length=32)
    source_message_id: str | None = Field(default=None, max_length=64)
    summary: str | None = None
    contract_path: str | None = Field(default=None, max_length=500)
    items: list[BossPlanItemCreate] = Field(default_factory=list)
    metadata: dict | None = Field(default=None, alias="extra_data")

    model_config = ConfigDict(populate_by_name=True)


class BossPlanItemUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=32)
    dispatch_message_id: str | None = Field(default=None, max_length=64)
    receipt_message_id: str | None = Field(default=None, max_length=64)
    metadata: dict | None = Field(default=None, alias="extra_data")

    model_config = ConfigDict(populate_by_name=True)


class BossPlanItemRead(BossPlanItemCreate):
    id: str
    plan_id: str
    project_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BossPlanRead(BaseModel):
    id: str
    project_id: str
    boss_seat_id: str | None
    goal: str
    title: str | None
    status: str
    source_message_id: str | None
    summary: str | None
    contract_path: str | None
    metadata: dict | None = Field(default=None, alias="extra_data")
    created_at: datetime | None = None
    updated_at: datetime | None = None
    items: list[BossPlanItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
