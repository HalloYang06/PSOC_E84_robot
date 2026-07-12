from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LabStatusRead(BaseModel):
    pending_human_approvals: int
    high_risk_approvals: int
    online_runners: int
    blocked_tasks: int
    active_tasks: int
    recent_audit_count: int


class LabChecklistItemRead(BaseModel):
    key: str
    title: str
    status: str
    detail: str | None = None


class LabCheckRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str | None = None
    item: str = Field(min_length=1, max_length=200)
    passed: bool = False
    notes: str | None = None


class LabApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    action: str = Field(min_length=1, max_length=200)
    level: str = "H3"
    notes: str | None = None


class LabAuditRead(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    success: bool
    created_at: datetime | None

    class Config:
        from_attributes = True


class LabChainStepRead(BaseModel):
    step: str
    status: str
    note: str


class LabChainRead(BaseModel):
    status: LabStatusRead
    checklist: list[LabChecklistItemRead]
    pending_hardware_approvals: list[dict]
    runner_summary: dict
    git_status: dict
    suggested_chain: list[LabChainStepRead]
