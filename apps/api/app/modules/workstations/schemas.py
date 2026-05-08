from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkstationCreate(BaseModel):
    config_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    lead_seat_id: str | None = Field(default=None, max_length=64)
    review_policy: str | None = Field(default=None, pattern="^(force|skip|inherit)$")
    sort_order: int = 0
    extra_data: dict[str, Any] | None = None


class WorkstationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    lead_seat_id: str | None = Field(default=None, max_length=64)
    review_policy: str | None = Field(default=None, pattern="^(force|skip|inherit)$")
    sort_order: int | None = None
    extra_data: dict[str, Any] | None = None


class WorkstationLeadSet(BaseModel):
    seat_id: str | None = Field(default=None, max_length=64)


class WorkstationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    config_id: str
    name: str
    description: str | None = None
    lead_seat_id: str | None = None
    review_policy: str | None = None
    sort_order: int = 0
    seat_count: int = 0
    extra_data: dict[str, Any] | None = None


class WorkstationSeatAssignRequest(BaseModel):
    seat_ids: list[str] = Field(default_factory=list)
