from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RehabAppProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, pattern="^(patient|therapist|family|engineer)$")
    affected_side: str | None = None
    rehab_stage: str | None = None
    medical_constraints: list[str] | None = None
    pain_baseline: float | None = Field(default=None, ge=0, le=10)


class RehabAppProfileRead(RehabAppProfileUpdate):
    id: str
    user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    control_boundary: str = "profile_data_only_not_medical_diagnosis"


class RehabAppDeviceBindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    m33_device_id: str = Field(min_length=1, max_length=120)
    ble_name: str = ""
    firmware_version: str = ""
    trust_status: str = Field(default="unverified", pattern="^(unverified|trusted|revoked)$")
    platform_project_id: str = ""


class RehabAppDeviceUnbindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=300)


class RehabAppDiagnosticUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_type: str = Field(default="diagnostic_snapshot", max_length=80)
    firmware_version: str = ""
    battery_level: float | None = Field(default=None, ge=0, le=1)
    m33_state: str = Field(default="unknown", max_length=80)
    payload: dict = Field(default_factory=dict)


class RehabAppTrainingPlanSyncRead(BaseModel):
    id: str
    plan_id: str
    device_id: str
    sync_status: str
    m33_reason: str = ""
    synced_at: datetime | None = None
    m33_authority: str = "required_before_motion"
    control_boundary: str = "training_plan_sync_only_not_motion_permission"


class RehabAppDeviceRead(BaseModel):
    id: str
    user_id: str
    m33_device_id: str
    ble_name: str
    firmware_version: str
    trust_status: str
    platform_project_id: str
    bound_at: datetime | None = None
    last_seen_at: datetime | None = None
    latest_sync: RehabAppTrainingPlanSyncRead | None = None
    control_boundary: str = "device_binding_only_not_motion_permission"


class RehabAppTrainingPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    source: str = Field(default="manual", pattern="^(manual|ai_generated|therapist|imported)$")
    goal: str = ""
    target_joints: list[str] = Field(default_factory=list)
    movement_type: str = Field(min_length=1, max_length=80)
    sets: int = Field(default=1, ge=1, le=20)
    reps: int = Field(default=1, ge=1, le=200)
    duration_sec: int = Field(default=0, ge=0, le=7200)
    target_angle_range: dict = Field(default_factory=dict)
    speed_level: str = "slow"
    assist_level: float = Field(default=0.0, ge=0, le=1)
    emg_policy: dict = Field(default_factory=dict)
    safety_constraints: dict = Field(default_factory=dict)
    status: str = Field(default="draft", pattern="^(draft|active|archived|rejected)$")


class RehabAppTrainingPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    source: str | None = Field(default=None, pattern="^(manual|ai_generated|therapist|imported)$")
    goal: str | None = None
    target_joints: list[str] | None = None
    movement_type: str | None = Field(default=None, min_length=1, max_length=80)
    sets: int | None = Field(default=None, ge=1, le=20)
    reps: int | None = Field(default=None, ge=1, le=200)
    duration_sec: int | None = Field(default=None, ge=0, le=7200)
    target_angle_range: dict | None = None
    speed_level: str | None = None
    assist_level: float | None = Field(default=None, ge=0, le=1)
    emg_policy: dict | None = None
    safety_constraints: dict | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|archived|rejected)$")


class RehabAppTrainingPlanRead(RehabAppTrainingPlanCreate):
    id: str
    user_id: str
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    control_boundary: str = "training_plan_only_not_motor_command"


class RehabAppTrainingPlanSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)


class RehabAppPlanConstraintReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_role: str = Field(default="therapist", pattern="^(therapist|engineer)$")
    review_status: str = Field(default="approved", pattern="^(approved|conditional|rejected)$")
    reviewed_constraints: list[str] = Field(default_factory=list)
    review_note: str = Field(default="", max_length=4000)


class RehabAppPlanConstraintReviewRead(RehabAppPlanConstraintReviewCreate):
    id: str
    user_id: str
    plan_id: str
    plan_version: int
    created_at: datetime | None = None
    control_boundary: str = "constraint_review_evidence_only_not_motion_permission"


class RehabAppM33StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_id: str = Field(min_length=1)
    sync_status: str = Field(pattern="^(sent|m33_accepted|m33_rejected|failed)$")
    m33_reason: str = ""
    firmware_version: str = ""


class RehabAppBleMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_type: str = Field(
        pattern="^(app_hello|device_status_request|training_plan_push|training_session_start_request|training_progress_notify|training_pause_request|training_stop_request|diagnostic_snapshot_request)$"
    )
    plan_id: str = ""
    session_id: str = ""
    client_message_id: str = ""
    extra_payload: dict = Field(default_factory=dict)


class RehabAppBleAckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ack_status: str = Field(pattern="^(acknowledged|rejected|failed)$")
    ack_payload: dict = Field(default_factory=dict)


class RehabAppTrainingReportReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_role: str = Field(default="patient", pattern="^(patient|therapist|family|engineer)$")
    review_status: str = Field(default="reviewed", pattern="^(needs_review|reviewed|needs_therapist_review|accepted|rejected)$")
    reviewer_note: str = Field(default="", max_length=4000)
    next_step: str = Field(default="continue_current_plan", pattern="^(continue_current_plan|adjust_plan|pause_and_consult|request_new_plan|calibration_check)$")
    request_new_plan: bool = False
    follow_up_payload: dict = Field(default_factory=dict)


class RehabAppTrainingSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)


class RehabAppPreflightCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    sync_id: str = Field(min_length=1)
    checked_by_role: str = Field(default="patient", pattern="^(patient|therapist|family|engineer)$")
    checklist: dict = Field(default_factory=dict)
    pain_before: float | None = Field(default=None, ge=0, le=10)
    notes: str = Field(default="", max_length=2000)


class RehabAppPreflightCheckRead(RehabAppPreflightCheckCreate):
    id: str
    user_id: str
    plan_version: int
    status: str
    created_at: datetime | None = None
    control_boundary: str = "preflight_check_evidence_only_not_motion_permission"


class RehabAppTrainingSessionFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion_rate: float = Field(default=0.0, ge=0, le=1)
    interruption_count: int = Field(default=0, ge=0)
    avg_assist_level: float = Field(default=0.0, ge=0, le=1)
    max_assist_level: float = Field(default=0.0, ge=0, le=1)
    m33_reject_count: int = Field(default=0, ge=0)
    pain_after: float | None = Field(default=None, ge=0, le=10)
    user_note: str = ""


class RehabAppTrainingSessionPauseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=1000)


class RehabAppTrainingSessionResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=1000)


class RehabAppTrainingSessionCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=1000)


class RehabAppTrainingSessionProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion_rate: float | None = Field(default=None, ge=0, le=1)
    interruption_count: int | None = Field(default=None, ge=0)
    avg_assist_level: float | None = Field(default=None, ge=0, le=1)
    max_assist_level: float | None = Field(default=None, ge=0, le=1)
    m33_reject_count: int | None = Field(default=None, ge=0)
    user_note: str | None = None


class RehabAppSessionSafetyEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(pattern="^(pain_report|device_fit_issue|m33_reject|fatigue_report|manual_stop_request|safety_review|other)$")
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")
    source: str = Field(default="patient", pattern="^(patient|therapist|m33|m55|app)$")
    pain_score: float | None = Field(default=None, ge=0, le=10)
    payload: dict = Field(default_factory=dict)
    note: str = Field(default="", max_length=2000)


class RehabAppSessionSafetyEventRead(RehabAppSessionSafetyEventCreate):
    id: str
    user_id: str
    session_id: str
    created_at: datetime | None = None
    control_boundary: str = "session_safety_event_evidence_only_not_motion_permission"


class RehabAppTrainingSessionRead(BaseModel):
    id: str
    user_id: str
    plan_id: str
    device_id: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str
    completion_rate: float
    interruption_count: int
    avg_assist_level: float
    max_assist_level: float
    m33_reject_count: int
    pain_after: float | None = None
    user_note: str = ""
    control_boundary: str = "training_session_record_only_not_motion_permission"


class RehabAppEmgSummaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    channel: str = Field(min_length=1, max_length=40)
    muscle_name: str = Field(min_length=1, max_length=120)
    rms_avg: float = 0.0
    peak: float = 0.0
    activation_avg: float = 0.0
    fatigue_index: float = 0.0
    contact_quality: str = "unknown"


class RehabAppEmgSummaryRead(RehabAppEmgSummaryCreate):
    id: str
    user_id: str
    created_at: datetime | None = None
    control_boundary: str = "emg_summary_only_not_motion_permission"


class RehabAppIntentSummaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    source: str = "m55"
    predicted_action: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)
    topk: list[dict] = Field(default_factory=list)
    stability_score: float = Field(default=0.0, ge=0, le=1)


class RehabAppIntentSummaryRead(RehabAppIntentSummaryCreate):
    id: str
    user_id: str
    created_at: datetime | None = None
    control_boundary: str = "intent_summary_only_not_motion_permission"


class RehabAppAiTrainingDraftGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(min_length=1, max_length=4000)
    context_snapshot: dict = Field(default_factory=dict)


class RehabAppPlatformSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_types: list[str] = Field(default_factory=list)


class RehabAppOfflineQueueItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_item_id: str = Field(min_length=1, max_length=120)
    operation_type: str = Field(min_length=1, max_length=80)
    resource_type: str = Field(default="", max_length=80)
    payload: dict = Field(default_factory=dict)


class RehabAppOfflineQueueReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[str] = Field(default_factory=list)


class RehabAppOfflineQueueReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_role: str = Field(default="patient", max_length=40)
    review_status: str = Field(default="reviewed", pattern="^(reviewed|ignored|duplicate|replaced)$", max_length=40)
    note: str = Field(min_length=1, max_length=1000)


class RehabAppWorkflowActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)
