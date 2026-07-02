from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.audit_log import AuditLog
from app.db.models.rehab_arm_app import (
    RehabAppAiTrainingDraft,
    RehabAppDiagnosticUpload,
    RehabAppDeviceBinding,
    RehabAppEmgSummary,
    RehabAppIntentInferenceSummary,
    RehabAppOfflineQueueItem,
    RehabAppPlatformSyncRun,
    RehabAppTrainingPlan,
    RehabAppTrainingPlanSync,
    RehabAppTrainingSession,
    RehabAppUserProfile,
)
from app.modules.audit.service import create_audit_log

from .app_schemas import (
    RehabAppDeviceBindRequest,
    RehabAppDiagnosticUploadRequest,
    RehabAppOfflineQueueItemCreate,
    RehabAppProfileUpdate,
    RehabAppTrainingPlanCreate,
    RehabAppTrainingPlanUpdate,
)


def _profile_dict(profile: RehabAppUserProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.name,
        "role": profile.role,
        "affected_side": profile.affected_side,
        "rehab_stage": profile.rehab_stage,
        "medical_constraints": profile.medical_constraints or [],
        "pain_baseline": profile.pain_baseline,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "control_boundary": "profile_data_only_not_medical_diagnosis",
    }


def _sync_dict(sync: RehabAppTrainingPlanSync) -> dict:
    return {
        "id": sync.id,
        "plan_id": sync.plan_id,
        "device_id": sync.device_id,
        "plan_version": sync.plan_version,
        "sync_status": sync.sync_status,
        "m33_reason": sync.m33_reason,
        "synced_at": sync.synced_at,
        "m33_authority": "required_before_motion",
        "control_boundary": "training_plan_sync_only_not_motion_permission",
    }


def _device_dict(device: RehabAppDeviceBinding, latest_sync: RehabAppTrainingPlanSync | None = None) -> dict:
    return {
        "id": device.id,
        "user_id": device.user_id,
        "m33_device_id": device.m33_device_id,
        "ble_name": device.ble_name,
        "firmware_version": device.firmware_version,
        "trust_status": device.trust_status,
        "platform_project_id": device.platform_project_id,
        "bound_at": device.bound_at,
        "last_seen_at": device.last_seen_at,
        "latest_sync": _sync_dict(latest_sync) if latest_sync else None,
        "control_boundary": "device_binding_only_not_motion_permission",
    }


def _plan_dict(plan: RehabAppTrainingPlan) -> dict:
    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "title": plan.title,
        "source": plan.source,
        "goal": plan.goal,
        "target_joints": plan.target_joints or [],
        "movement_type": plan.movement_type,
        "sets": plan.sets,
        "reps": plan.reps,
        "duration_sec": plan.duration_sec,
        "target_angle_range": plan.target_angle_range or {},
        "speed_level": plan.speed_level,
        "assist_level": plan.assist_level,
        "emg_policy": plan.emg_policy or {},
        "safety_constraints": plan.safety_constraints or {},
        "status": plan.status,
        "version": plan.version,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "control_boundary": "training_plan_only_not_motor_command",
    }


def _session_dict(session: RehabAppTrainingSession) -> dict:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "plan_id": session.plan_id,
        "device_id": session.device_id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "completion_rate": session.completion_rate,
        "interruption_count": session.interruption_count,
        "avg_assist_level": session.avg_assist_level,
        "max_assist_level": session.max_assist_level,
        "m33_reject_count": session.m33_reject_count,
        "pain_after": session.pain_after,
        "user_note": session.user_note,
        "control_boundary": "training_session_record_only_not_motion_permission",
    }


def _emg_dict(summary: RehabAppEmgSummary) -> dict:
    return {
        "id": summary.id,
        "user_id": summary.user_id,
        "session_id": summary.session_id,
        "channel": summary.channel,
        "muscle_name": summary.muscle_name,
        "rms_avg": summary.rms_avg,
        "peak": summary.peak,
        "activation_avg": summary.activation_avg,
        "fatigue_index": summary.fatigue_index,
        "contact_quality": summary.contact_quality,
        "created_at": summary.created_at,
        "control_boundary": "emg_summary_only_not_motion_permission",
    }


def _intent_dict(summary: RehabAppIntentInferenceSummary) -> dict:
    return {
        "id": summary.id,
        "user_id": summary.user_id,
        "session_id": summary.session_id,
        "source": summary.source,
        "predicted_action": summary.predicted_action,
        "confidence": summary.confidence,
        "topk": summary.topk or [],
        "stability_score": summary.stability_score,
        "created_at": summary.created_at,
        "control_boundary": "intent_summary_only_not_motion_permission",
    }


def _draft_dict(draft: RehabAppAiTrainingDraft) -> dict:
    return {
        "id": draft.id,
        "user_id": draft.user_id,
        "input_text": draft.input_text,
        "context_snapshot": draft.context_snapshot or {},
        "generated_plan": draft.generated_plan or {},
        "risk_notes": draft.risk_notes or [],
        "accepted_plan_id": draft.accepted_plan_id,
        "created_at": draft.created_at,
        "control_boundary": "ai_draft_only_not_execution_permission",
    }


def _diagnostic_dict(upload: RehabAppDiagnosticUpload) -> dict:
    return {
        "id": upload.id,
        "user_id": upload.user_id,
        "device_id": upload.device_id,
        "snapshot_type": upload.snapshot_type,
        "firmware_version": upload.firmware_version,
        "battery_level": upload.battery_level,
        "m33_state": upload.m33_state,
        "payload": upload.payload or {},
        "created_at": upload.created_at,
        "control_boundary": "diagnostic_snapshot_only_not_motion_permission",
    }


def _offline_item_dict(item: RehabAppOfflineQueueItem) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "client_item_id": item.client_item_id,
        "operation_type": item.operation_type,
        "resource_type": item.resource_type,
        "payload": item.payload or {},
        "replay_status": item.replay_status,
        "replay_result": item.replay_result or {},
        "created_at": item.created_at,
        "replayed_at": item.replayed_at,
        "control_boundary": "offline_queue_evidence_only_not_motion_permission",
    }


def _platform_sync_run_dict(run: RehabAppPlatformSyncRun) -> dict:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "resource_types": run.resource_types or [],
        "status": run.status,
        "summary": run.summary or {},
        "created_at": run.created_at,
        "control_boundary": "platform_sync_evidence_only_not_motion_permission",
    }


def _audit_dict(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "project_id": log.project_id,
        "actor_type": log.actor_type,
        "actor_id": log.actor_id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "success": log.success,
        "error_message": log.error_message,
        "created_at": log.created_at,
        "after": log.after or {},
        "control_boundary": "audit_log_only_not_motion_permission",
    }


def upsert_profile(db: Session, user_id: str, payload: RehabAppProfileUpdate) -> dict:
    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    data = payload.model_dump()
    if profile is None:
        profile = RehabAppUserProfile(user_id=user_id, **data)
        db.add(profile)
        action = "rehab_app.profile.created"
    else:
        for key, value in data.items():
            setattr(profile, key, value)
        db.add(profile)
        action = "rehab_app.profile.updated"
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action=action,
        resource_type="rehab_app_profile",
        resource_id=profile.id,
        after={"user_id": user_id, "control_boundary": "profile_data_only_not_medical_diagnosis"},
    )
    db.commit()
    db.refresh(profile)
    return _profile_dict(profile)


def get_profile(db: Session, user_id: str) -> dict | None:
    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    return _profile_dict(profile) if profile else None


def get_app_bootstrap(db: Session, user_id: str) -> dict:
    devices = list_devices(db, user_id)
    plans = list_training_plans(db, user_id)
    sessions = list_training_sessions(db, user_id, limit=1)
    return {
        "profile": get_profile(db, user_id),
        "devices": devices,
        "training_plans": plans,
        "active_session": sessions[0] if sessions and sessions[0]["status"] in {"started", "in_progress"} else None,
        "latest_emg": latest_emg_summary(db, user_id),
        "platform_sync": get_platform_sync_status(db, user_id),
        "offline_queue": list_offline_queue(db, user_id, status="queued", limit=20),
        "control_boundary": "app_bootstrap_evidence_only_not_motion_permission",
    }


def bind_device(db: Session, user_id: str, payload: RehabAppDeviceBindRequest) -> dict:
    device = db.scalar(
        select(RehabAppDeviceBinding).where(
            RehabAppDeviceBinding.user_id == user_id,
            RehabAppDeviceBinding.m33_device_id == payload.m33_device_id,
        )
    )
    data = payload.model_dump()
    if device is None:
        device = RehabAppDeviceBinding(user_id=user_id, **data)
        db.add(device)
    else:
        for key, value in data.items():
            setattr(device, key, value)
        db.add(device)
    db.flush()
    create_audit_log(
        db,
        project_id=payload.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.device.bound",
        resource_type="rehab_app_device_binding",
        resource_id=device.id,
        after={"m33_device_id": device.m33_device_id, "control_boundary": "device_binding_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(device)
    return _device_dict(device)


def _latest_device_sync(db: Session, device_id: str) -> RehabAppTrainingPlanSync | None:
    return db.scalar(
        select(RehabAppTrainingPlanSync)
        .where(RehabAppTrainingPlanSync.device_id == device_id)
        .order_by(RehabAppTrainingPlanSync.synced_at.desc())
        .limit(1)
    )


def list_devices(db: Session, user_id: str) -> list[dict]:
    devices = list(
        db.scalars(
            select(RehabAppDeviceBinding)
            .where(RehabAppDeviceBinding.user_id == user_id)
            .order_by(RehabAppDeviceBinding.bound_at.desc())
        )
    )
    return [_device_dict(device, _latest_device_sync(db, device.id)) for device in devices]


def get_device_status(db: Session, user_id: str, device_id: str) -> dict:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    latest_sync = _latest_device_sync(db, device.id)
    return {
        **_device_dict(device, latest_sync),
        "heartbeat_status": "unknown" if device.last_seen_at is None else "seen",
        "m33_state": latest_sync.sync_status if latest_sync else "waiting",
        "m33_reason": latest_sync.m33_reason if latest_sync else "",
        "m33_authority": "final_safety_authority",
        "control_boundary": "device_status_only_not_motion_permission",
    }


def upload_device_diagnostic(db: Session, user_id: str, device_id: str, payload: RehabAppDiagnosticUploadRequest) -> dict:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    upload = RehabAppDiagnosticUpload(user_id=user_id, device_id=device.id, **payload.model_dump())
    device.last_seen_at = datetime.now(timezone.utc)
    if payload.firmware_version:
        device.firmware_version = payload.firmware_version
    db.add(upload)
    db.add(device)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.device.diagnostic_uploaded",
        resource_type="rehab_app_diagnostic_upload",
        resource_id=upload.id,
        after={"m33_state": upload.m33_state, "control_boundary": "diagnostic_snapshot_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(upload)
    return _diagnostic_dict(upload)


def list_device_diagnostics(db: Session, user_id: str, device_id: str, limit: int = 50) -> list[dict]:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    uploads = list(
        db.scalars(
            select(RehabAppDiagnosticUpload)
            .where(RehabAppDiagnosticUpload.user_id == user_id, RehabAppDiagnosticUpload.device_id == device.id)
            .order_by(RehabAppDiagnosticUpload.created_at.desc())
            .limit(limit)
        )
    )
    return [_diagnostic_dict(upload) for upload in uploads]


def create_training_plan(db: Session, user_id: str, payload: RehabAppTrainingPlanCreate) -> dict:
    data = payload.model_dump()
    plan = RehabAppTrainingPlan(user_id=user_id, version=1, **data)
    db.add(plan)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_plan.created",
        resource_type="rehab_app_training_plan",
        resource_id=plan.id,
        after={"movement_type": plan.movement_type, "control_boundary": "training_plan_only_not_motor_command"},
    )
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


def list_training_plans(db: Session, user_id: str) -> list[dict]:
    plans = list(
        db.scalars(
            select(RehabAppTrainingPlan)
            .where(RehabAppTrainingPlan.user_id == user_id)
            .order_by(RehabAppTrainingPlan.updated_at.desc())
        )
    )
    return [_plan_dict(plan) for plan in plans]


def get_training_plan(db: Session, user_id: str, plan_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    return _plan_dict(plan)


def update_training_plan(db: Session, user_id: str, plan_id: str, payload: RehabAppTrainingPlanUpdate) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    changed = False
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)
        changed = True
    if changed:
        plan.version += 1
    db.add(plan)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_plan.updated",
        resource_type="rehab_app_training_plan",
        resource_id=plan.id,
        after={"version": plan.version, "control_boundary": "training_plan_only_not_motor_command"},
    )
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


def archive_training_plan(db: Session, user_id: str, plan_id: str) -> dict:
    return update_training_plan(db, user_id, plan_id, RehabAppTrainingPlanUpdate(status="archived"))


def sync_training_plan_to_device(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    sync = RehabAppTrainingPlanSync(plan_id=plan.id, device_id=device.id, plan_version=plan.version, sync_status="pending")
    db.add(sync)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_plan.sync_requested",
        resource_type="rehab_app_training_plan_sync",
        resource_id=sync.id,
        after={
            "plan_id": plan.id,
            "device_id": device.id,
            "m33_authority": "required_before_motion",
            "control_boundary": "training_plan_sync_only_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(sync)
    return _sync_dict(sync)


def update_m33_sync_status(db: Session, user_id: str, device_id: str, sync_id: str, sync_status: str, m33_reason: str = "", firmware_version: str = "") -> dict:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    sync = db.get(RehabAppTrainingPlanSync, sync_id)
    if sync is None or sync.device_id != device.id:
        raise AppError("TRAINING_PLAN_SYNC_NOT_FOUND", "training plan sync not found", status_code=404)
    sync.sync_status = sync_status
    sync.m33_reason = m33_reason
    sync.synced_at = datetime.now(timezone.utc)
    device.last_seen_at = datetime.now(timezone.utc)
    if firmware_version:
        device.firmware_version = firmware_version
    db.add(sync)
    db.add(device)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="m33",
        actor_id=device.m33_device_id,
        action=f"rehab_app.training_plan.{sync_status}",
        resource_type="rehab_app_training_plan_sync",
        resource_id=sync.id,
        after={
            "sync_status": sync.sync_status,
            "m33_reason": sync.m33_reason,
            "m33_authority": "final_safety_authority",
            "control_boundary": "m33_decision_only_not_motor_command",
        },
    )
    db.commit()
    db.refresh(sync)
    return _sync_dict(sync)


def _latest_plan_device_sync(db: Session, plan_id: str, device_id: str) -> RehabAppTrainingPlanSync | None:
    return db.scalar(
        select(RehabAppTrainingPlanSync)
        .where(RehabAppTrainingPlanSync.plan_id == plan_id, RehabAppTrainingPlanSync.device_id == device_id)
        .order_by(RehabAppTrainingPlanSync.synced_at.desc())
        .limit(1)
    )


def _require_user_session(db: Session, user_id: str, session_id: str) -> RehabAppTrainingSession:
    session = db.get(RehabAppTrainingSession, session_id)
    if session is None or session.user_id != user_id:
        raise AppError("TRAINING_SESSION_NOT_FOUND", "training session not found", status_code=404)
    return session


def start_training_session(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    sync = _latest_plan_device_sync(db, plan.id, device.id)
    if sync is None or sync.sync_status != "m33_accepted" or sync.plan_version != plan.version:
        raise AppError(
            "M33_ACCEPTANCE_REQUIRED",
            "M33 must accept the latest training plan sync before a session can start",
            status_code=409,
            details={
                "plan_id": plan.id,
                "device_id": device.id,
                "sync_status": sync.sync_status if sync else "missing",
                "accepted_plan_version": sync.plan_version if sync else None,
                "required_plan_version": plan.version,
                "m33_reason": sync.m33_reason if sync else "no plan sync found",
                "m33_authority": "final_safety_authority",
                "control_boundary": "training_session_blocked_not_motion_permission",
            },
        )
    session = RehabAppTrainingSession(user_id=user_id, plan_id=plan.id, device_id=device.id, status="started")
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.started",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"control_boundary": "training_session_record_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def finish_training_session(db: Session, user_id: str, session_id: str, payload: dict) -> dict:
    session = _require_user_session(db, user_id, session_id)
    for key, value in payload.items():
        setattr(session, key, value)
    session.status = "finished"
    session.ended_at = datetime.now(timezone.utc)
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.finished",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"control_boundary": "training_session_record_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def update_training_session_progress(db: Session, user_id: str, session_id: str, payload: dict) -> dict:
    session = _require_user_session(db, user_id, session_id)
    for key, value in payload.items():
        if value is not None:
            setattr(session, key, value)
    if session.status == "started":
        session.status = "in_progress"
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.progress_recorded",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"control_boundary": "training_session_record_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def list_training_sessions(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    sessions = list(
        db.scalars(
            select(RehabAppTrainingSession)
            .where(RehabAppTrainingSession.user_id == user_id)
            .order_by(RehabAppTrainingSession.started_at.desc())
            .limit(limit)
        )
    )
    return [_session_dict(session) for session in sessions]


def get_training_session(db: Session, user_id: str, session_id: str) -> dict:
    return _session_dict(_require_user_session(db, user_id, session_id))


def record_emg_summary(db: Session, user_id: str, payload: dict) -> dict:
    _require_user_session(db, user_id, str(payload.get("session_id") or ""))
    summary = RehabAppEmgSummary(user_id=user_id, **payload)
    db.add(summary)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.emg_summary.recorded",
        resource_type="rehab_app_emg_summary",
        resource_id=summary.id,
        after={"control_boundary": "emg_summary_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(summary)
    return _emg_dict(summary)


def latest_emg_summary(db: Session, user_id: str) -> dict | None:
    summary = db.scalar(
        select(RehabAppEmgSummary)
        .where(RehabAppEmgSummary.user_id == user_id)
        .order_by(RehabAppEmgSummary.created_at.desc())
        .limit(1)
    )
    return _emg_dict(summary) if summary else None


def emg_history(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    summaries = list(
        db.scalars(
            select(RehabAppEmgSummary)
            .where(RehabAppEmgSummary.user_id == user_id)
            .order_by(RehabAppEmgSummary.created_at.desc())
            .limit(limit)
        )
    )
    return [_emg_dict(summary) for summary in summaries]


def record_intent_summary(db: Session, user_id: str, payload: dict) -> dict:
    _require_user_session(db, user_id, str(payload.get("session_id") or ""))
    summary = RehabAppIntentInferenceSummary(user_id=user_id, **payload)
    db.add(summary)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.intent_summary.recorded",
        resource_type="rehab_app_intent_summary",
        resource_id=summary.id,
        after={"control_boundary": "intent_summary_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(summary)
    return _intent_dict(summary)


ALLOWED_OFFLINE_OPERATIONS = {
    "device_diagnostic_upload",
    "training_session_progress",
    "emg_summary",
    "intent_summary",
    "platform_sync",
}


def enqueue_offline_item(db: Session, user_id: str, payload: RehabAppOfflineQueueItemCreate) -> dict:
    if payload.operation_type not in ALLOWED_OFFLINE_OPERATIONS:
        raise AppError(
            "OFFLINE_OPERATION_NOT_ALLOWED",
            "offline queue only accepts evidence and review operations",
            status_code=422,
            details={"allowed_operations": sorted(ALLOWED_OFFLINE_OPERATIONS), "control_boundary": "offline_queue_evidence_only_not_motion_permission"},
        )
    existing = db.scalar(
        select(RehabAppOfflineQueueItem).where(
            RehabAppOfflineQueueItem.user_id == user_id,
            RehabAppOfflineQueueItem.client_item_id == payload.client_item_id,
        )
    )
    if existing:
        return _offline_item_dict(existing)
    item = RehabAppOfflineQueueItem(user_id=user_id, **payload.model_dump())
    db.add(item)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.offline_queue.enqueued",
        resource_type="rehab_app_offline_queue_item",
        resource_id=item.id,
        after={"operation_type": item.operation_type, "control_boundary": "offline_queue_evidence_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(item)
    return _offline_item_dict(item)


def list_offline_queue(db: Session, user_id: str, status: str | None = None, limit: int = 50) -> list[dict]:
    statement = select(RehabAppOfflineQueueItem).where(RehabAppOfflineQueueItem.user_id == user_id)
    if status:
        statement = statement.where(RehabAppOfflineQueueItem.replay_status == status)
    items = list(db.scalars(statement.order_by(RehabAppOfflineQueueItem.created_at.asc()).limit(limit)))
    return [_offline_item_dict(item) for item in items]


def _mark_offline_item(db: Session, item: RehabAppOfflineQueueItem, status: str, result: dict) -> None:
    item.replay_status = status
    item.replay_result = {**result, "control_boundary": "offline_queue_evidence_only_not_motion_permission"}
    item.replayed_at = datetime.now(timezone.utc)
    db.add(item)


def _offline_replay_result(result: dict) -> dict:
    return {
        "id": result.get("id") or "",
        "status": result.get("status") or result.get("sync_status") or "recorded",
        "resource_control_boundary": result.get("control_boundary") or "",
    }


def replay_offline_queue(db: Session, user_id: str, item_ids: list[str] | None = None) -> dict:
    statement = select(RehabAppOfflineQueueItem).where(
        RehabAppOfflineQueueItem.user_id == user_id,
        RehabAppOfflineQueueItem.replay_status == "queued",
    )
    if item_ids:
        statement = statement.where(RehabAppOfflineQueueItem.id.in_(item_ids))
    items = list(db.scalars(statement.order_by(RehabAppOfflineQueueItem.created_at.asc()).limit(50)))
    replayed: list[dict] = []
    for item in items:
        try:
            if item.operation_type == "device_diagnostic_upload":
                result = upload_device_diagnostic(
                    db,
                    user_id,
                    str((item.payload or {}).get("device_id") or ""),
                    RehabAppDiagnosticUploadRequest(**{k: v for k, v in (item.payload or {}).items() if k != "device_id"}),
                )
            elif item.operation_type == "training_session_progress":
                result = update_training_session_progress(
                    db,
                    user_id,
                    str((item.payload or {}).get("session_id") or ""),
                    {k: v for k, v in (item.payload or {}).items() if k != "session_id"},
                )
            elif item.operation_type == "emg_summary":
                result = record_emg_summary(db, user_id, item.payload or {})
            elif item.operation_type == "intent_summary":
                result = record_intent_summary(db, user_id, item.payload or {})
            elif item.operation_type == "platform_sync":
                result = sync_platform_records(db, user_id, list((item.payload or {}).get("resource_types") or []))
            else:
                raise AppError("OFFLINE_OPERATION_NOT_ALLOWED", "offline operation is not allowed", status_code=422)
            _mark_offline_item(db, item, "replayed", {"result": _offline_replay_result(result)})
        except Exception as exc:  # Keep the queue item inspectable for phone retry UX.
            _mark_offline_item(db, item, "failed", {"error": str(exc)})
        db.commit()
        db.refresh(item)
        replayed.append(_offline_item_dict(item))
    return {
        "items": replayed,
        "replayed_count": len([item for item in replayed if item["replay_status"] == "replayed"]),
        "failed_count": len([item for item in replayed if item["replay_status"] == "failed"]),
        "control_boundary": "offline_queue_evidence_only_not_motion_permission",
    }


def generate_ai_training_draft(db: Session, user_id: str, input_text: str, context_snapshot: dict) -> dict:
    generated_plan = {
        "title": "AI 建议低强度训练",
        "source": "ai_generated",
        "goal": input_text[:240],
        "movement_type": context_snapshot.get("movement_type") or "elbow_flexion",
        "sets": int(context_snapshot.get("sets") or 2),
        "reps": int(context_snapshot.get("reps") or 6),
        "duration_sec": int(context_snapshot.get("duration_sec") or 480),
        "target_joints": context_snapshot.get("target_joints") or ["elbow"],
        "assist_level": float(context_snapshot.get("assist_level") or 0.2),
        "speed_level": context_snapshot.get("speed_level") or "slow",
        "target_angle_range": context_snapshot.get("target_angle_range") or {"min_deg": 15, "max_deg": 60},
        "emg_policy": context_snapshot.get("emg_policy") or {"intent_source": "m55", "assist_when_confidence_above": 0.72},
        "safety_constraints": context_snapshot.get("safety_constraints") or {"require_fresh_m33_heartbeat": True, "stop_on_pain_report": True},
        "status": "draft",
        "control_boundary": "ai_draft_only_not_execution_permission",
    }
    risk_notes = ["AI 只生成草稿，不代表执行许可", "必须同步到 M33 并获得 m33_accepted 后才能开始训练记录"]
    draft = RehabAppAiTrainingDraft(
        user_id=user_id,
        input_text=input_text,
        context_snapshot=context_snapshot,
        generated_plan=generated_plan,
        risk_notes=risk_notes,
    )
    db.add(draft)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.ai_training_draft.generated",
        resource_type="rehab_app_ai_training_draft",
        resource_id=draft.id,
        after={"control_boundary": "ai_draft_only_not_execution_permission"},
    )
    db.commit()
    db.refresh(draft)
    return _draft_dict(draft)


def get_ai_training_draft(db: Session, user_id: str, draft_id: str) -> dict:
    draft = db.get(RehabAppAiTrainingDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        raise AppError("AI_TRAINING_DRAFT_NOT_FOUND", "AI training draft not found", status_code=404)
    return _draft_dict(draft)


def accept_ai_training_draft(db: Session, user_id: str, draft_id: str) -> dict:
    draft = db.get(RehabAppAiTrainingDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        raise AppError("AI_TRAINING_DRAFT_NOT_FOUND", "AI training draft not found", status_code=404)
    if draft.accepted_plan_id:
        return get_training_plan(db, user_id, draft.accepted_plan_id)
    plan_payload = RehabAppTrainingPlanCreate(**{k: v for k, v in (draft.generated_plan or {}).items() if k != "control_boundary"})
    plan = RehabAppTrainingPlan(user_id=user_id, version=1, **plan_payload.model_dump())
    db.add(plan)
    db.flush()
    draft.accepted_plan_id = plan.id
    db.add(draft)
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.ai_training_draft.accepted",
        resource_type="rehab_app_training_plan",
        resource_id=plan.id,
        after={"draft_id": draft.id, "control_boundary": "training_plan_only_not_motor_command"},
    )
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


def sync_platform_records(db: Session, user_id: str, resource_types: list[str]) -> dict:
    selected_types = resource_types or ["training_plans", "training_sessions", "emg_summaries", "m33_decisions"]
    summary = {
        "training_plans": len(list_training_plans(db, user_id)) if "training_plans" in selected_types else 0,
        "training_sessions": len(list_training_sessions(db, user_id)) if "training_sessions" in selected_types else 0,
        "emg_summaries": len(emg_history(db, user_id)) if "emg_summaries" in selected_types else 0,
        "m33_decisions": len(
            list(
                db.scalars(
                    select(RehabAppTrainingPlanSync)
                    .join(RehabAppTrainingPlan, RehabAppTrainingPlan.id == RehabAppTrainingPlanSync.plan_id)
                    .where(RehabAppTrainingPlan.user_id == user_id)
                )
            )
        )
        if "m33_decisions" in selected_types
        else 0,
    }
    run = RehabAppPlatformSyncRun(user_id=user_id, resource_types=selected_types, status="completed", summary=summary)
    db.add(run)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.platform_sync.requested",
        resource_type="rehab_app_platform_sync",
        resource_id=run.id,
        after={"resource_types": selected_types, "summary": summary, "control_boundary": "platform_sync_evidence_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(run)
    return _platform_sync_run_dict(run)


def get_platform_sync_status(db: Session, user_id: str) -> dict:
    latest_session = list_training_sessions(db, user_id, limit=1)
    latest_run = db.scalar(
        select(RehabAppPlatformSyncRun)
        .where(RehabAppPlatformSyncRun.user_id == user_id)
        .order_by(RehabAppPlatformSyncRun.created_at.desc())
        .limit(1)
    )
    return {
        "status": "ready",
        "latest_session_id": latest_session[0]["id"] if latest_session else "",
        "latest_sync_run": _platform_sync_run_dict(latest_run) if latest_run else None,
        "synced_resource_types": ["training_plans", "training_sessions", "emg_summaries", "m33_decisions"],
        "control_boundary": "platform_sync_evidence_only_not_motion_permission",
    }


def list_platform_sync_runs(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    runs = list(
        db.scalars(
            select(RehabAppPlatformSyncRun)
            .where(RehabAppPlatformSyncRun.user_id == user_id)
            .order_by(RehabAppPlatformSyncRun.created_at.desc())
            .limit(limit)
        )
    )
    return [_platform_sync_run_dict(run) for run in runs]


def list_safety_audit_logs(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    actor_ids = [user_id]
    actor_ids.extend(
        str(device.m33_device_id)
        for device in db.scalars(select(RehabAppDeviceBinding).where(RehabAppDeviceBinding.user_id == user_id))
        if device.m33_device_id
    )
    logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.actor_id.in_(actor_ids), AuditLog.action.startswith("rehab_app."))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    )
    return [_audit_dict(log) for log in logs]
