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


class ProfessionalViewArtifactRead(BaseModel):
    class PreviewContextRead(BaseModel):
        task_id: str
        path: str
        source_message_id: str | None = None
        dispatch_id: str | None = None
        workstation_id: str | None = None

    label: str
    path: str
    source_message_id: str | None = None
    source_message_type: str | None = None
    task_id: str | None = None
    dispatch_id: str | None = None
    sender_id: str | None = None
    authoritative_seat_id: str | None = None
    authoritative_seat_ref: str | None = None
    authoritative_target_seat_id: str | None = None
    historical_alias_non_authoritative: bool = False
    exception_tags: list[str] = Field(default_factory=list)
    blocked_reason_code: str | None = None
    evidence_complete: bool | None = None
    preview_context: PreviewContextRead | None = None


class ProfessionalViewExceptionStateRead(BaseModel):
    failed: bool = False
    timed_out: bool = False
    auto_closed: bool = False
    retryable: bool = False
    log_available: bool = False
    split_suggested: bool = False
    exception_kind: str | None = None
    blocked_reason_code: str | None = None
    blocked_reason_label: str | None = None
    evidence_complete: bool | None = None
    platform_defect: bool = False
    nudge_required: bool = False
    wait_extension_available: bool = False
    manual_close_required: bool = False
    desktop_closeout_waiting: bool = False
    desktop_sync_retry_requested: bool = False
    desktop_sync_retry_count: int = 0
    tags: list[str] = Field(default_factory=list)


class ProfessionalViewMessageRead(BaseModel):
    id: str
    message_type: str
    status: str
    title: str | None = None
    body: str
    sender_type: str
    sender_id: str | None = None
    recipient_type: str | None = None
    recipient_id: str | None = None
    dispatch_id: str | None = None
    authoritative_seat_id: str | None = None
    authoritative_seat_ref: str | None = None
    authoritative_target_seat_id: str | None = None
    historical_alias_non_authoritative: bool = False
    metadata: dict = Field(default_factory=dict)
    payload_json: dict | None = None
    artifact_refs: list[ProfessionalViewArtifactRead] = Field(default_factory=list)
    exception_state: ProfessionalViewExceptionStateRead = Field(default_factory=ProfessionalViewExceptionStateRead)
    created_at: datetime | None = None


class ProfessionalViewAuditRead(BaseModel):
    id: str
    action: str
    actor_type: str
    actor_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    success: bool
    created_at: datetime | None = None


class ProfessionalViewTimelineEntryRead(BaseModel):
    kind: str
    status: str | None = None
    label: str
    source_id: str | None = None
    source_type: str | None = None
    dispatch_id: str | None = None
    created_at: datetime | None = None


class ProfessionalViewApprovalLinkRead(BaseModel):
    approval_id: str
    level: str | None = None
    action: str | None = None
    status: str
    task_id: str | None = None
    receipt_message_id: str | None = None


class ProfessionalViewReceiptLinkRead(BaseModel):
    message_id: str
    message_type: str
    status: str
    source_message_id: str | None = None
    dispatch_id: str | None = None
    authoritative_seat_id: str | None = None
    authoritative_seat_ref: str | None = None
    authoritative_target_seat_id: str | None = None
    historical_alias_non_authoritative: bool = False
    created_at: datetime | None = None


class ProfessionalViewCapabilitySummaryRead(BaseModel):
    workstation_id: str | None = None
    workstation_name: str | None = None
    runner_id: str | None = None
    provider_id: str | None = None
    capability_labels: list[str] = Field(default_factory=list)
    adapter: dict = Field(default_factory=dict)
    runner: dict = Field(default_factory=dict)


class ProfessionalViewSummaryRead(BaseModel):
    task_id: str
    project_id: str
    task_status: str
    dispatch_count: int
    message_count: int
    audit_count: int
    artifact_count: int
    latest_result_status: str | None = None
    latest_result_message_id: str | None = None
    pending_approval_count: int = 0
    blocked: bool = False
    exception_summary: dict = Field(default_factory=dict)
    evidence_chain_status: str | None = None
    stale_sync_requires_attention: bool = False
    receipt_count: int = 0
    capability_count: int = 0
    runner_count: int = 0
    auto_retry_active: bool = False
    pending_closeout_count: int = 0
    experiment_run_status: str = "waiting"
    metrics_summary: dict = Field(default_factory=dict)
    dataset_manifest_artifact_path: str | None = None
    manifest_version: str | None = None
    sample_count: int | None = None
    low_confidence_count: int | None = None
    qa_status: str = "waiting"
    export_status: str = "waiting"
    training_receipt_status: str = "waiting"
    release_gate_status: str = "can_continue"
    replay_ready: bool = False


class ProfessionalTaskViewRead(BaseModel):
    task: TaskRead
    gate: dict
    summary: ProfessionalViewSummaryRead
    dispatches: list[TaskDispatchRead] = Field(default_factory=list)
    messages: list[ProfessionalViewMessageRead] = Field(default_factory=list)
    timeline: list[ProfessionalViewTimelineEntryRead] = Field(default_factory=list)
    approvals: list[ProfessionalViewApprovalLinkRead] = Field(default_factory=list)
    receipts: list[ProfessionalViewReceiptLinkRead] = Field(default_factory=list)
    capability_summary: list[ProfessionalViewCapabilitySummaryRead] = Field(default_factory=list)
    audit: list[ProfessionalViewAuditRead] = Field(default_factory=list)


class ArtifactIndexEntryRead(BaseModel):
    label: str
    path: str
    task_id: str
    source_message_id: str | None = None
    source_message_type: str | None = None
    dispatch_id: str | None = None
    sender_id: str | None = None
    authoritative_seat_id: str | None = None
    authoritative_seat_ref: str | None = None
    authoritative_target_seat_id: str | None = None
    historical_alias_non_authoritative: bool = False
    created_at: datetime | None = None
    exception_tags: list[str] = Field(default_factory=list)
    blocked_reason_code: str | None = None
    evidence_complete: bool | None = None
    runner_id: str | None = None
    workstation_id: str | None = None
    preview_context: ProfessionalViewArtifactRead.PreviewContextRead | None = None
