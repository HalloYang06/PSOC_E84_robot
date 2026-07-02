from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.rehab_arm_app import (
    RehabAppDeviceBinding,
    RehabAppEmgSummary,
    RehabAppIntentInferenceSummary,
    RehabAppTrainingPlan,
    RehabAppTrainingPlanSync,
    RehabAppTrainingSession,
    RehabAppUserProfile,
)
from app.modules.audit.service import create_audit_log

from .app_schemas import RehabAppDeviceBindRequest, RehabAppProfileUpdate, RehabAppTrainingPlanCreate


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


def sync_training_plan_to_device(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    sync = RehabAppTrainingPlanSync(plan_id=plan.id, device_id=device.id, sync_status="pending")
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
    from datetime import datetime, timezone

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
