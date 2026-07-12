from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    task_id: str
    level: str = "H1"
    action: str
    notes: str | None = None


class ApprovalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = None


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = None


class ApprovalRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str
    level: str
    action: str
    status: str
    approver_user_id: str | None
    approved_at: datetime | None
    notes: str | None
    created_at: datetime | None

    class Config:
        from_attributes = True
