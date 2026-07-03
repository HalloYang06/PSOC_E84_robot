from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.audit_log import AuditLog
from app.db.models.rehab_arm_app import (
    RehabAppAiTrainingDraft,
    RehabAppBleMessage,
    RehabAppDiagnosticUpload,
    RehabAppDeviceBinding,
    RehabAppEmgSummary,
    RehabAppIntentInferenceSummary,
    RehabAppOfflineQueueItem,
    RehabAppPlanConstraintReview,
    RehabAppPlatformSyncRun,
    RehabAppPreflightCheck,
    RehabAppSessionSafetyEvent,
    RehabAppTrainingPlan,
    RehabAppTrainingPlanSync,
    RehabAppTrainingReport,
    RehabAppTrainingReportReview,
    RehabAppTrainingSession,
    RehabAppUserProfile,
)
from app.modules.audit.service import create_audit_log

from .app_schemas import (
    RehabAppDeviceBindRequest,
    RehabAppDiagnosticUploadRequest,
    RehabAppBleMessageCreate,
    RehabAppOfflineQueueItemCreate,
    RehabAppOfflineQueueReviewRequest,
    RehabAppPlanConstraintReviewCreate,
    RehabAppPreflightCheckCreate,
    RehabAppProfileUpdate,
    RehabAppSessionSafetyEventCreate,
    RehabAppTrainingReportReviewCreate,
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


def _ble_message_dict(message: RehabAppBleMessage) -> dict:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "device_id": message.device_id,
        "message_type": message.message_type,
        "related_plan_id": message.related_plan_id,
        "related_session_id": message.related_session_id,
        "payload": message.payload or {},
        "ack_status": message.ack_status,
        "ack_payload": message.ack_payload or {},
        "created_at": message.created_at,
        "acked_at": message.acked_at,
        "control_boundary": "ble_message_contract_only_not_motor_command",
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


def _preflight_dict(check: RehabAppPreflightCheck) -> dict:
    return {
        "id": check.id,
        "user_id": check.user_id,
        "plan_id": check.plan_id,
        "device_id": check.device_id,
        "sync_id": check.sync_id,
        "plan_version": check.plan_version,
        "status": check.status,
        "checked_by_role": check.checked_by_role,
        "checklist": check.checklist or {},
        "pain_before": check.pain_before,
        "notes": check.notes,
        "created_at": check.created_at,
        "control_boundary": "preflight_check_evidence_only_not_motion_permission",
    }


def _safety_event_dict(event: RehabAppSessionSafetyEvent) -> dict:
    return {
        "id": event.id,
        "user_id": event.user_id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "severity": event.severity,
        "source": event.source,
        "pain_score": event.pain_score,
        "payload": event.payload or {},
        "note": event.note,
        "created_at": event.created_at,
        "control_boundary": "session_safety_event_evidence_only_not_motion_permission",
    }


def _report_dict(report: RehabAppTrainingReport) -> dict:
    return {
        "id": report.id,
        "user_id": report.user_id,
        "session_id": report.session_id,
        "plan_id": report.plan_id,
        "device_id": report.device_id,
        "summary": report.summary or {},
        "emg_overview": report.emg_overview or {},
        "intent_overview": report.intent_overview or {},
        "safety_overview": report.safety_overview or {},
        "recommendations": report.recommendations or [],
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "control_boundary": "training_report_review_only_not_medical_diagnosis_or_motion_permission",
    }


def _report_review_dict(review: RehabAppTrainingReportReview) -> dict:
    return {
        "id": review.id,
        "user_id": review.user_id,
        "report_id": review.report_id,
        "reviewer_role": review.reviewer_role,
        "review_status": review.review_status,
        "reviewer_note": review.reviewer_note,
        "next_step": review.next_step,
        "request_new_plan": review.request_new_plan,
        "follow_up_payload": review.follow_up_payload or {},
        "created_at": review.created_at,
        "control_boundary": "training_report_review_only_not_medical_diagnosis_or_motion_permission",
    }


def _constraint_review_dict(review: RehabAppPlanConstraintReview) -> dict:
    return {
        "id": review.id,
        "user_id": review.user_id,
        "plan_id": review.plan_id,
        "plan_version": review.plan_version,
        "reviewer_role": review.reviewer_role,
        "review_status": review.review_status,
        "reviewed_constraints": review.reviewed_constraints or [],
        "review_note": review.review_note,
        "created_at": review.created_at,
        "control_boundary": "constraint_review_evidence_only_not_motion_permission",
    }


def _report_with_review_dict(db: Session, report: RehabAppTrainingReport) -> dict:
    latest_review = db.scalar(
        select(RehabAppTrainingReportReview)
        .where(RehabAppTrainingReportReview.report_id == report.id)
        .order_by(RehabAppTrainingReportReview.created_at.desc())
        .limit(1)
    )
    return {**_report_dict(report), "latest_review": _report_review_dict(latest_review) if latest_review else None}


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


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


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


def _onboarding_step(code: str, status: str, title: str, description: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "status": status,
        "title": title,
        "description": description,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _app_onboarding_guide(profile: dict | None, devices: list[dict], plans: list[dict]) -> dict:
    has_profile = profile is not None
    has_trusted_device = any(device["trust_status"] != "revoked" for device in devices)
    has_usable_plan = any(plan["status"] not in {"archived", "rejected"} for plan in plans)
    steps = [
        _onboarding_step(
            "PROFILE_REQUIRED",
            "done" if has_profile else "todo",
            "完善康复档案",
            "记录患侧、康复阶段、疼痛基线和禁忌项，后续计划约束和疼痛门禁会引用这些信息。",
            "/api/rehab-arm/app/v1/me/profile",
            "PATCH",
            {"affected_side": "left_or_right", "rehab_stage": "required", "pain_baseline": "0_to_10", "medical_constraints": []},
        ),
        _onboarding_step(
            "TRUSTED_DEVICE_REQUIRED",
            "done" if has_trusted_device else "todo",
            "绑定可信 M33 设备",
            "绑定 M33 BLE 身份用于计划同步、M33 接受证据和诊断读取；解绑冻结的设备不能训练。",
            "/api/rehab-arm/app/v1/devices/bind",
            "POST",
            {"m33_device_id": "required", "ble_name": "optional", "trust_status": "trusted"},
        ),
        _onboarding_step(
            "TRAINING_PLAN_REQUIRED",
            "done" if has_usable_plan else "todo",
            "创建或接受训练计划",
            "创建治疗师计划，或从 AI 草稿接受为普通训练计划。计划仍需同步并由 M33 接受后才能进入 preflight。",
            "/api/rehab-arm/app/v1/training-plans",
            "POST",
            {"title": "required", "movement_type": "required", "sets": "required", "reps": "required", "status": "active"},
        ),
    ]
    next_step = next((step for step in steps if step["status"] == "todo"), None)
    return {
        "status": "complete" if next_step is None else "incomplete",
        "next_step": next_step,
        "steps": steps,
        "actions": [step for step in steps if step["status"] == "todo"],
        "control_boundary": "app_onboarding_guide_evidence_only_not_motion_permission",
    }


def _daily_action(
    code: str,
    priority: int,
    title: str,
    description: str,
    endpoint: str,
    method: str,
    payload_hint: dict | None = None,
    source: dict | None = None,
) -> dict:
    return {
        "code": code,
        "priority": priority,
        "title": title,
        "description": description,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
        "source": source or {},
    }


def _app_daily_action_guide(
    onboarding_guide: dict,
    active_session: dict | None,
    finished_session_report_guide: dict | None,
    primary_start_guide: dict | None,
    latest_report: dict | None,
    latest_open_ai_draft: dict | None,
    offline_sync_guide: dict | None = None,
    safety_review_guide: dict | None = None,
    accepted_plan_guide: dict | None = None,
) -> dict:
    if active_session:
        return {
            "status": "action_required",
            "next_action": _daily_action(
                "RECOVER_ACTIVE_SESSION",
                10,
                "继续处理当前训练",
                "设备已有未关闭训练，请先恢复、完成或取消当前训练，再开始新的训练。",
                f"/api/rehab-arm/app/v1/training-sessions/{active_session['id']}",
                "GET",
                source={"session_id": active_session["id"], "session_status": active_session["status"], "guide": "session_recovery_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if safety_review_guide and safety_review_guide.get("status") == "review_required":
        blocking_event = safety_review_guide.get("blocking_event") or {}
        return {
            "status": "action_required",
            "next_action": _daily_action(
                "REVIEW_BLOCKING_SAFETY_EVENT",
                15,
                "复核阻塞安全事件",
                "最近训练存在未复核 critical 安全事件。请先记录 approved/conditional safety_review，再继续下一次训练。",
                f"/api/rehab-arm/app/v1/training-sessions/{blocking_event.get('session_id', '{session_id}')}/safety-events",
                "POST",
                {"event_type": "safety_review", "severity": "info", "payload": {"review_status": "approved_or_conditional"}},
                source={
                    "session_id": blocking_event.get("session_id", ""),
                    "event_id": blocking_event.get("event_id", ""),
                    "guide": "safety_review_guide",
                },
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if finished_session_report_guide and finished_session_report_guide.get("status") == "report_required":
        session = finished_session_report_guide.get("session") or {}
        next_action = finished_session_report_guide.get("next_action") or {}
        return {
            "status": "action_required",
            "next_action": _daily_action(
                next_action.get("code") or "GENERATE_TRAINING_REPORT",
                18,
                next_action.get("label") or "生成训练报告",
                "最近训练已经结束但还没有生成训练报告。先生成报告，再进行人工复盘和下一计划闭环。",
                next_action.get("endpoint") or f"/api/rehab-arm/app/v1/training-sessions/{session.get('id', '{session_id}')}/report",
                next_action.get("method") or "POST",
                next_action.get("payload_hint") or {},
                source={"session_id": session.get("id", ""), "guide": "finished_session_report_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if offline_sync_guide and offline_sync_guide.get("status") in {"review_failed_items", "ready_to_replay"}:
        actions = offline_sync_guide.get("actions") or []
        next_action = actions[0] if actions else {}
        is_failed = offline_sync_guide.get("status") == "review_failed_items"
        return {
            "status": "action_required",
            "next_action": _daily_action(
                next_action.get("code") or ("VIEW_OFFLINE_QUEUE" if is_failed else "REPLAY_OFFLINE_EVIDENCE"),
                19,
                next_action.get("label") or ("查看离线失败证据" if is_failed else "同步离线证据"),
                "手机端存在未处理的离线证据。请先重放 queued 证据或查看 failed 失败项，再继续后续训练闭环。",
                next_action.get("endpoint") or "/api/rehab-arm/app/v1/offline-queue",
                next_action.get("method") or "GET",
                next_action.get("payload_hint") or {},
                source={"guide": "offline_sync_guide", "offline_status": offline_sync_guide.get("status", "")},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if latest_open_ai_draft:
        return {
            "status": "action_required",
            "next_action": _daily_action(
                "REVIEW_AI_DRAFT",
                20,
                "审核 AI 训练草稿",
                "有未接受的 AI 训练草稿。接受后会成为普通训练计划，仍需 M33 同步和接受。",
                f"/api/rehab-arm/app/v1/ai-training-drafts/{latest_open_ai_draft['id']}",
                "GET",
                source={"draft_id": latest_open_ai_draft["id"], "guide": "ai_draft_review_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if accepted_plan_guide and accepted_plan_guide.get("status") in {"device_required", "sync_required", "m33_decision_pending", "m33_rejected_review_required", "preflight_required"}:
        plan = accepted_plan_guide.get("plan") or {}
        next_action = accepted_plan_guide.get("next_action") or {}
        return {
            "status": "action_required",
            "next_action": _daily_action(
                next_action.get("code") or "COMPLETE_ACCEPTED_AI_PLAN",
                25,
                next_action.get("label") or "完成已接受 AI 计划闭环",
                "AI 草稿已接受为训练计划，但仍需完成设备绑定、M33 同步/接受、preflight 或开始条件检查。",
                next_action.get("endpoint") or f"/api/rehab-arm/app/v1/training-plans/{plan.get('id', '{plan_id}')}",
                next_action.get("method") or "GET",
                next_action.get("payload_hint") or {},
                source={"plan_id": plan.get("id", ""), "guide": "accepted_plan_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if latest_report and latest_report.get("latest_review") is None:
        return {
            "status": "action_required",
            "next_action": _daily_action(
                "REVIEW_LATEST_REPORT",
                30,
                "复盘最近训练报告",
                "最近训练报告还没有人工复核。请记录患者或治疗师复盘，再决定继续、调整或生成下一计划。",
                f"/api/rehab-arm/app/v1/training-reports/{latest_report['id']}/reviews",
                "POST",
                {"reviewer_role": "patient_or_therapist", "review_status": "reviewed", "next_step": "continue_or_adjust"},
                source={"report_id": latest_report["id"], "guide": "report_followup_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    latest_review = latest_report.get("latest_review") if latest_report else None
    if latest_report and latest_review and latest_review.get("request_new_plan"):
        return {
            "status": "action_required",
            "next_action": _daily_action(
                "DRAFT_NEXT_PLAN_FROM_REPORT",
                40,
                "根据复盘生成下一计划草稿",
                "最近复盘要求调整计划。先生成 AI 草稿，再由用户或治疗师接受为普通训练计划。",
                f"/api/rehab-arm/app/v1/training-reports/{latest_report['id']}/draft-next-plan",
                "POST",
                source={"report_id": latest_report["id"], "review_id": latest_review["id"], "guide": "report_followup_guide"},
            ),
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    if primary_start_guide:
        return {
            "status": "ready" if primary_start_guide["can_start"] else "action_required",
            "next_action": primary_start_guide["next_action"],
            "source": {"guide": "primary_start_guide"},
            "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
        }
    return {
        "status": onboarding_guide["status"],
        "next_action": onboarding_guide["next_step"],
        "source": {"guide": "onboarding_guide"},
        "control_boundary": "app_daily_action_guide_evidence_only_not_motion_permission",
    }


def _timeline_item(kind: str, event_at: object, title: str, status: str, source_id: str, detail: dict | None = None) -> dict:
    return {
        "kind": kind,
        "event_at": event_at,
        "title": title,
        "status": status,
        "source_id": source_id,
        "detail": detail or {},
    }


def _timeline_sort_value(item: dict) -> str:
    value = item.get("event_at")
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _app_care_timeline(sessions: list[dict], reports: list[dict], drafts: list[dict], offline_items: list[dict], limit: int = 8) -> dict:
    items: list[dict] = []
    for session in sessions:
        items.append(
            _timeline_item(
                "training_session",
                session.get("ended_at") or session.get("started_at"),
                "训练会话",
                session["status"],
                session["id"],
                {
                    "plan_id": session["plan_id"],
                    "device_id": session["device_id"],
                    "completion_rate": session["completion_rate"],
                    "pain_after": session["pain_after"],
                },
            )
        )
    for report in reports:
        latest_review = report.get("latest_review") or {}
        items.append(
            _timeline_item(
                "training_report",
                report.get("created_at"),
                "训练报告",
                "reviewed" if latest_review else "review_required",
                report["id"],
                {
                    "session_id": report["session_id"],
                    "plan_id": report["plan_id"],
                    "latest_review_id": latest_review.get("id", ""),
                    "recommendations": report.get("recommendations", []),
                },
            )
        )
    for draft in drafts:
        items.append(
            _timeline_item(
                "ai_training_draft",
                draft.get("created_at"),
                "AI 训练草稿",
                "accepted" if draft.get("accepted_plan_id") else "open",
                draft["id"],
                {"accepted_plan_id": draft.get("accepted_plan_id") or "", "risk_notes": draft.get("risk_notes", [])},
            )
        )
    for item in offline_items:
        items.append(
            _timeline_item(
                "offline_queue_item",
                item.get("replayed_at") or item.get("created_at"),
                "离线证据",
                item["replay_status"],
                item["id"],
                {"operation_type": item["operation_type"], "resource_type": item["resource_type"]},
            )
        )
    items = sorted(items, key=_timeline_sort_value, reverse=True)[:limit]
    return {
        "items": items,
        "control_boundary": "app_care_timeline_evidence_only_not_motion_permission",
    }


def _app_care_summary(
    onboarding_guide: dict,
    primary_start_guide: dict | None,
    sessions: list[dict],
    reports: list[dict],
    drafts: list[dict],
    offline_items: list[dict],
) -> dict:
    active_count = sum(1 for session in sessions if session["status"] in {"started", "in_progress", "paused"})
    finished_count = sum(1 for session in sessions if session["status"] == "finished")
    cancelled_count = sum(1 for session in sessions if session["status"] == "cancelled")
    review_required_count = sum(1 for report in reports if report.get("latest_review") is None)
    open_draft_count = sum(1 for draft in drafts if not draft.get("accepted_plan_id"))
    queued_offline_count = sum(1 for item in offline_items if item["replay_status"] == "queued")
    failed_offline_count = sum(1 for item in offline_items if item["replay_status"] == "failed")
    can_start = bool(primary_start_guide and primary_start_guide.get("can_start"))
    blockers = []
    if onboarding_guide["status"] != "complete":
        blockers.append("onboarding_incomplete")
    if active_count:
        blockers.append("active_session")
    if review_required_count:
        blockers.append("report_review_required")
    if open_draft_count:
        blockers.append("ai_draft_open")
    if failed_offline_count:
        blockers.append("offline_queue_failed")
    if queued_offline_count:
        blockers.append("offline_queue_pending")
    status = "attention_required" if blockers else ("ready" if can_start else "setup_required")
    return {
        "status": status,
        "can_start": can_start,
        "counts": {
            "active_sessions": active_count,
            "finished_sessions": finished_count,
            "cancelled_sessions": cancelled_count,
            "reports": len(reports),
            "reports_pending_review": review_required_count,
            "ai_drafts_open": open_draft_count,
            "offline_items_queued": queued_offline_count,
            "offline_items_failed": failed_offline_count,
        },
        "blockers": blockers,
        "control_boundary": "app_care_summary_evidence_only_not_motion_permission",
    }


def _app_home_status_guide(daily_action_guide: dict, care_summary: dict, related_actions: list[dict] | None = None) -> dict:
    next_action = daily_action_guide.get("next_action") or {}
    action_code = str(next_action.get("code") or "")
    action_endpoint = str(next_action.get("endpoint") or "")
    action_method = str(next_action.get("method") or "").upper()
    body = next_action.get("description") or next_action.get("detail") or next_action.get("message") or ""
    critical_actions = {"RECOVER_ACTIVE_SESSION", "REVIEW_BLOCKING_SAFETY_EVENT", "VIEW_OFFLINE_QUEUE"}
    warning_actions = {"GENERATE_TRAINING_REPORT", "REPLAY_OFFLINE_EVIDENCE", "REVIEW_LATEST_REPORT", "DRAFT_NEXT_PLAN_FROM_REPORT"}
    if daily_action_guide.get("status") == "ready":
        tone = "success"
        headline = "可以进入下一步"
    elif action_code in critical_actions:
        tone = "critical"
        headline = next_action.get("title") or next_action.get("label") or "需要先处理阻塞事项"
    elif action_code in warning_actions:
        tone = "warning"
        headline = next_action.get("title") or next_action.get("label") or "需要先完成当前事项"
    else:
        tone = "info"
        headline = next_action.get("title") or next_action.get("label") or "继续完成设置"
    secondary_actions: list[dict] = []
    seen_action_codes = {action_code} if action_code else set()
    seen_action_targets = {(action_method, action_endpoint)} if action_method and action_endpoint else set()
    for action in related_actions or []:
        code = str(action.get("code") or "")
        endpoint = str(action.get("endpoint") or "")
        method = str(action.get("method") or "").upper()
        target = (method, endpoint)
        if not code or code in seen_action_codes or (method and endpoint and target in seen_action_targets):
            continue
        seen_action_codes.add(code)
        if method and endpoint:
            seen_action_targets.add(target)
        secondary_actions.append(action)
    return {
        "status": daily_action_guide.get("status") or care_summary.get("status"),
        "tone": tone,
        "headline": headline,
        "body": body or "按照下一步操作完成当前康复记录闭环。",
        "primary_action": next_action,
        "secondary_actions": secondary_actions,
        "blockers": care_summary.get("blockers") or [],
        "counts": care_summary.get("counts") or {},
        "safety_note": "本卡片只提供手机端证据和流程引导，不授予硬件运动权限；真实运动仍由 M33 最终裁决。",
        "control_boundary": "app_home_status_guide_evidence_only_not_motion_permission",
    }


def _app_home_related_actions(daily_action_guide: dict, guides_by_name: dict[str, dict | None]) -> list[dict]:
    next_action = daily_action_guide.get("next_action") or {}
    source = next_action.get("source") or daily_action_guide.get("source") or {}
    source_guide = source.get("guide")
    guide = guides_by_name.get(source_guide) if source_guide else None
    if not guide:
        return []
    return guide.get("actions") or []


def _app_offline_sync_guide(offline_items: list[dict]) -> dict:
    queued = [item for item in offline_items if item["replay_status"] == "queued"]
    replayed = [item for item in offline_items if item["replay_status"] == "replayed"]
    failed = [item for item in offline_items if item["replay_status"] == "failed"]
    actions = []
    if failed:
        status = "review_failed_items"
        next_action = "inspect_failed_replay_results"
        first_failed_id = failed[0]["id"] if len(failed) == 1 else "{item_id}"
        actions.append(
            {
                "code": "VIEW_OFFLINE_QUEUE",
                "label": "查看离线队列",
                "endpoint": "/api/rehab-arm/app/v1/offline-queue?status=failed",
                "method": "GET",
                "payload_hint": {"status": "failed"},
            }
        )
        actions.append(
            {
                "code": "REVIEW_FAILED_OFFLINE_ITEM",
                "label": "标记失败证据已处理",
                "endpoint": f"/api/rehab-arm/app/v1/offline-queue/{first_failed_id}/review",
                "method": "POST",
                "payload_hint": {"reviewer_role": "patient_or_therapist", "review_status": "reviewed", "note": "required"},
            }
        )
    elif queued:
        status = "ready_to_replay"
        next_action = "replay_queued_evidence"
    else:
        status = "synced"
        next_action = "none"
    if queued:
        actions.append(
            {
                "code": "REPLAY_OFFLINE_EVIDENCE",
                "label": "重放离线证据",
                "endpoint": "/api/rehab-arm/app/v1/offline-queue/replay",
                "method": "POST",
                "payload_hint": {"item_ids": [item["id"] for item in queued]},
            }
        )
    return {
        "status": status,
        "next_action": next_action,
        "counts": {
            "queued": len(queued),
            "replayed": len(replayed),
            "failed": len(failed),
        },
        "queued_item_ids": [item["id"] for item in queued],
        "failed_item_ids": [item["id"] for item in failed],
        "replay_endpoint": "/api/rehab-arm/app/v1/offline-queue/replay",
        "replay_method": "POST",
        "payload_hint": {"item_ids": [item["id"] for item in queued]},
        "actions": actions,
        "control_boundary": "offline_sync_guide_evidence_only_not_motion_permission",
    }


def _app_offline_queue_items(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    items = list(
        db.scalars(
            select(RehabAppOfflineQueueItem)
            .where(
                RehabAppOfflineQueueItem.user_id == user_id,
                RehabAppOfflineQueueItem.replay_status.in_(["queued", "failed"]),
            )
            .order_by(RehabAppOfflineQueueItem.created_at.asc())
            .limit(limit)
        )
    )
    return [_offline_item_dict(item) for item in items]


def _session_recovery_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _app_session_recovery_guide(db: Session, user_id: str, active_session: dict | None) -> dict | None:
    if active_session is None:
        return None
    session_id = active_session["id"]
    status = active_session["status"]
    actions = [
        _session_recovery_action("VIEW_SESSION", "查看训练详情", f"/api/rehab-arm/app/v1/training-sessions/{session_id}", "GET"),
        _session_recovery_action(
            "CANCEL_SESSION",
            "取消当前训练",
            f"/api/rehab-arm/app/v1/training-sessions/{session_id}/cancel",
            "POST",
            {"reason": "required"},
        ),
    ]
    recovery_status = "active"
    blocking_event = None
    if status == "paused":
        session = _require_user_session(db, user_id, session_id)
        event = _latest_unreviewed_critical_safety_event(db, user_id, session.id)
        if event is not None:
            recovery_status = "safety_review_required"
            blocking_event = {"event_id": event.id, "event_type": event.event_type, "severity": event.severity}
            actions.insert(
                1,
                _session_recovery_action(
                    "RECORD_SAFETY_REVIEW",
                    "记录安全复核",
                    f"/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
                    "POST",
                    {"event_type": "safety_review", "severity": "info", "payload": {"review_status": "approved_or_conditional"}},
                ),
            )
        else:
            recovery_status = "paused_can_resume"
            actions.insert(
                1,
                _session_recovery_action("RESUME_SESSION", "恢复训练记录", f"/api/rehab-arm/app/v1/training-sessions/{session_id}/resume", "POST"),
            )
    else:
        actions.insert(
            1,
            _session_recovery_action(
                "RECORD_PROGRESS",
                "记录训练进度",
                f"/api/rehab-arm/app/v1/training-sessions/{session_id}/progress",
                "PATCH",
                {"completion_rate": "0_to_1"},
            ),
        )
        actions.insert(
            2,
            _session_recovery_action(
                "FINISH_SESSION",
                "完成训练记录",
                f"/api/rehab-arm/app/v1/training-sessions/{session_id}/finish",
                "POST",
                {"completion_rate": "0_to_1", "pain_after": "optional_0_to_10"},
            ),
        )
    return {
        "status": recovery_status,
        "session": active_session,
        "blocking_event": blocking_event,
        "actions": actions,
        "control_boundary": "session_recovery_guide_evidence_only_not_motion_permission",
    }


def _report_followup_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _ai_draft_review_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _app_ai_draft_review_guide(latest_open_ai_draft: dict | None) -> dict | None:
    if latest_open_ai_draft is None:
        return None
    draft_id = latest_open_ai_draft["id"]
    return {
        "status": "review_required",
        "draft": latest_open_ai_draft,
        "next_action": _ai_draft_review_action(
            "VIEW_AI_DRAFT",
            "查看 AI 训练草稿",
            f"/api/rehab-arm/app/v1/ai-training-drafts/{draft_id}",
            "GET",
            {"draft_id": draft_id},
        ),
        "actions": [
            _ai_draft_review_action(
                "VIEW_AI_DRAFT",
                "查看 AI 训练草稿",
                f"/api/rehab-arm/app/v1/ai-training-drafts/{draft_id}",
                "GET",
                {"draft_id": draft_id},
            ),
            _ai_draft_review_action(
                "ACCEPT_AI_DRAFT",
                "接受为训练计划",
                f"/api/rehab-arm/app/v1/ai-training-drafts/{draft_id}/accept",
                "POST",
                {"draft_id": draft_id},
            ),
        ],
        "control_boundary": "ai_draft_review_guide_draft_only_not_motion_permission",
    }


def _app_report_followup_guide(latest_report: dict | None, drafts: list[dict]) -> dict | None:
    if latest_report is None:
        return None
    report_id = latest_report["id"]
    latest_review = latest_report.get("latest_review")
    report_drafts = [
        draft
        for draft in drafts
        if (draft.get("context_snapshot") or {}).get("source") == "training_report_review"
        and (draft.get("context_snapshot") or {}).get("report_id") == report_id
    ]
    open_report_draft = next((draft for draft in report_drafts if not draft.get("accepted_plan_id")), None)
    accepted_report_draft = next((draft for draft in report_drafts if draft.get("accepted_plan_id")), None)
    actions = [
        _report_followup_action("VIEW_REPORT", "查看训练报告", f"/api/rehab-arm/app/v1/training-reports/{report_id}", "GET"),
    ]
    if latest_review is None:
        status = "review_required"
        actions.append(
            _report_followup_action(
                "RECORD_REPORT_REVIEW",
                "记录报告复盘",
                f"/api/rehab-arm/app/v1/training-reports/{report_id}/reviews",
                "POST",
                {"reviewer_role": "patient_or_therapist", "review_status": "reviewed", "next_step": "continue_or_adjust"},
            )
        )
    elif open_report_draft:
        status = "ai_draft_review_required"
        actions.extend(
            [
                _report_followup_action(
                    "VIEW_AI_DRAFT",
                    "查看下一计划草稿",
                    f"/api/rehab-arm/app/v1/ai-training-drafts/{open_report_draft['id']}",
                    "GET",
                    {"draft_id": open_report_draft["id"]},
                ),
                _report_followup_action(
                    "ACCEPT_AI_DRAFT",
                    "接受为训练计划",
                    f"/api/rehab-arm/app/v1/ai-training-drafts/{open_report_draft['id']}/accept",
                    "POST",
                    {"draft_id": open_report_draft["id"]},
                ),
            ]
        )
    elif accepted_report_draft:
        status = "accepted_plan_sync_required"
        accepted_plan_id = accepted_report_draft["accepted_plan_id"]
        actions.extend(
            [
                _report_followup_action("VIEW_ACCEPTED_PLAN", "查看已接受计划", f"/api/rehab-arm/app/v1/training-plans/{accepted_plan_id}", "GET"),
                _report_followup_action(
                    "SYNC_ACCEPTED_PLAN_TO_M33",
                    "同步计划到 M33",
                    f"/api/rehab-arm/app/v1/training-plans/{accepted_plan_id}/sync-to-device",
                    "POST",
                    {"device_id": "required"},
                ),
            ]
        )
    elif latest_review.get("request_new_plan"):
        status = "next_plan_draft_required"
        actions.append(
            _report_followup_action(
                "DRAFT_NEXT_PLAN_FROM_REPORT",
                "生成下一计划草稿",
                f"/api/rehab-arm/app/v1/training-reports/{report_id}/draft-next-plan",
                "POST",
                {"report_id": report_id, "review_id": latest_review["id"]},
            )
        )
    else:
        status = "review_complete"
    return {
        "status": status,
        "report": latest_report,
        "report_draft": open_report_draft or accepted_report_draft,
        "latest_review": latest_review,
        "actions": actions,
        "control_boundary": "report_followup_guide_evidence_only_not_motion_permission",
    }


def _app_finished_session_report_guide(db: Session, user_id: str, sessions: list[dict]) -> dict | None:
    for session in sessions:
        if session.get("status") != "finished":
            continue
        existing_report = _session_report(db, user_id, session["id"])
        if existing_report is not None:
            continue
        session_id = session["id"]
        return {
            "status": "report_required",
            "session": session,
            "next_action": _report_followup_action(
                "GENERATE_TRAINING_REPORT",
                "生成训练报告",
                f"/api/rehab-arm/app/v1/training-sessions/{session_id}/report",
                "POST",
                {"session_id": session_id},
            ),
            "actions": [
                _report_followup_action("VIEW_SESSION", "查看训练记录", f"/api/rehab-arm/app/v1/training-sessions/{session_id}", "GET"),
                _report_followup_action(
                    "GENERATE_TRAINING_REPORT",
                    "生成训练报告",
                    f"/api/rehab-arm/app/v1/training-sessions/{session_id}/report",
                    "POST",
                    {"session_id": session_id},
                ),
            ],
            "control_boundary": "finished_session_report_guide_evidence_only_not_motion_permission",
        }
    return None


def _device_operational_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _latest_device_diagnostic(db: Session, user_id: str, device_id: str) -> dict | None:
    upload = db.scalar(
        select(RehabAppDiagnosticUpload)
        .where(RehabAppDiagnosticUpload.user_id == user_id, RehabAppDiagnosticUpload.device_id == device_id)
        .order_by(RehabAppDiagnosticUpload.created_at.desc(), RehabAppDiagnosticUpload.id.desc())
        .limit(1)
    )
    return _diagnostic_dict(upload) if upload else None


def _app_device_operational_guide(db: Session, user_id: str, devices: list[dict], primary_plan: dict | None) -> dict:
    if not devices:
        return {
            "status": "device_required",
            "device": None,
            "latest_diagnostic": None,
            "actions": [
                _device_operational_action(
                    "BIND_TRUSTED_DEVICE",
                    "绑定可信 M33 设备",
                    "/api/rehab-arm/app/v1/devices/bind",
                    "POST",
                    {"m33_device_id": "required", "ble_name": "optional", "trust_status": "trusted"},
                )
            ],
            "control_boundary": "device_operational_guide_evidence_only_not_motion_permission",
        }
    device = next((item for item in devices if item["trust_status"] != "revoked"), devices[0])
    latest_sync = device.get("latest_sync")
    latest_diagnostic = _latest_device_diagnostic(db, user_id, device["id"])
    actions = [
        _device_operational_action("VIEW_DEVICE_STATUS", "查看设备状态", f"/api/rehab-arm/app/v1/devices/{device['id']}/status", "GET"),
        _device_operational_action("VIEW_DIAGNOSTICS", "查看诊断记录", f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostics", "GET"),
    ]
    if device["trust_status"] == "revoked":
        status = "device_revoked"
        actions.append(
            _device_operational_action(
                "BIND_REPLACEMENT_DEVICE",
                "绑定替换设备",
                "/api/rehab-arm/app/v1/devices/bind",
                "POST",
                {"m33_device_id": "required", "ble_name": "optional", "trust_status": "trusted"},
            )
        )
    elif latest_sync is None:
        status = "plan_sync_required" if primary_plan else "diagnostic_or_plan_required"
        actions.append(
            _device_operational_action(
                "UPLOAD_DIAGNOSTIC",
                "上传设备诊断",
                f"/api/rehab-arm/app/v1/devices/{device['id']}/diagnostic-upload",
                "POST",
                {"snapshot_type": "m33_status", "m33_state": "required"},
            )
        )
        if primary_plan:
            actions.append(
                _device_operational_action(
                    "SYNC_PLAN_TO_M33",
                    "同步计划到 M33",
                    f"/api/rehab-arm/app/v1/training-plans/{primary_plan['id']}/sync-to-device",
                    "POST",
                    {"device_id": device["id"]},
                )
            )
    elif latest_sync["sync_status"] in {"pending", "sent"}:
        status = "m33_decision_pending"
        actions.extend(
            [
                _device_operational_action(
                    "REQUEST_DEVICE_STATUS",
                    "请求设备状态",
                    f"/api/rehab-arm/app/v1/devices/{device['id']}/ble/messages",
                    "POST",
                    {"message_type": "device_status_request"},
                ),
                _device_operational_action(
                    "RECORD_M33_DECISION",
                    "记录 M33 决策",
                    f"/api/rehab-arm/app/v1/devices/{device['id']}/m33-status",
                    "POST",
                    {"sync_id": latest_sync["id"], "sync_status": "m33_accepted_or_m33_rejected"},
                ),
            ]
        )
    elif latest_sync["sync_status"] == "m33_rejected":
        status = "m33_rejected_review_required"
        actions.append(
            _device_operational_action(
                "RESYNC_PLAN_AFTER_REVIEW",
                "复核后重新同步计划",
                f"/api/rehab-arm/app/v1/training-plans/{latest_sync['plan_id']}/sync-to-device",
                "POST",
                {"device_id": device["id"]},
            )
        )
    elif latest_sync["sync_status"] == "m33_accepted":
        status = "m33_acceptance_ready"
        actions.append(
            _device_operational_action(
                "CHECK_START_READINESS",
                "检查训练开始条件",
                f"/api/rehab-arm/app/v1/training-plans/{latest_sync['plan_id']}/readiness",
                "GET",
                {"device_id": device["id"]},
            )
        )
    else:
        status = "device_attention_required"
    return {
        "status": status,
        "device": device,
        "latest_sync": latest_sync,
        "latest_diagnostic": latest_diagnostic,
        "heartbeat_status": "unknown" if device.get("last_seen_at") is None else "seen",
        "actions": actions,
        "control_boundary": "device_operational_guide_evidence_only_not_motion_permission",
    }


def _safety_review_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _app_safety_review_guide(db: Session, user_id: str, sessions: list[dict]) -> dict | None:
    for session_item in sessions:
        session_id = session_item["id"]
        event = _latest_unreviewed_critical_safety_event(db, user_id, session_id)
        if event is None:
            continue
        blocking_event = {
            "session_id": session_id,
            "event_id": event.id,
            "event_type": event.event_type,
            "severity": event.severity,
            "source": event.source,
            "pain_score": event.pain_score,
        }
        return {
            "status": "review_required",
            "blocking_event": blocking_event,
            "session": session_item,
            "actions": [
                _safety_review_action("VIEW_SESSION", "查看训练记录", f"/api/rehab-arm/app/v1/training-sessions/{session_id}", "GET"),
                _safety_review_action(
                    "VIEW_SAFETY_EVENTS",
                    "查看安全事件",
                    f"/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
                    "GET",
                ),
                _safety_review_action(
                    "RECORD_SAFETY_REVIEW",
                    "记录安全复核",
                    f"/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
                    "POST",
                    {"event_type": "safety_review", "severity": "info", "payload": {"review_status": "approved_or_conditional"}},
                ),
            ],
            "control_boundary": "safety_review_guide_evidence_only_not_motion_permission",
        }
    return {
        "status": "clear",
        "blocking_event": None,
        "session": None,
        "actions": [],
        "control_boundary": "safety_review_guide_evidence_only_not_motion_permission",
    }


def _accepted_plan_action(code: str, label: str, endpoint: str, method: str, payload_hint: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "endpoint": endpoint,
        "method": method,
        "payload_hint": payload_hint or {},
    }


def _app_accepted_plan_guide(db: Session, user_id: str, drafts: list[dict], devices: list[dict]) -> dict | None:
    accepted_draft = next((draft for draft in drafts if draft.get("accepted_plan_id")), None)
    if accepted_draft is None:
        return None
    plan_id = accepted_draft["accepted_plan_id"]
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        return None
    plan_data = _plan_dict(plan)
    trusted_device = next((device for device in devices if device["trust_status"] != "revoked"), None)
    actions = [
        _accepted_plan_action("VIEW_ACCEPTED_PLAN", "查看已接受计划", f"/api/rehab-arm/app/v1/training-plans/{plan.id}", "GET"),
    ]
    latest_sync = None
    if plan.status in {"archived", "rejected"}:
        status = "plan_closed"
        next_action = actions[0]
    elif trusted_device is None:
        status = "device_required"
        actions.append(
            _accepted_plan_action(
                "BIND_TRUSTED_DEVICE",
                "绑定可信 M33 设备",
                "/api/rehab-arm/app/v1/devices/bind",
                "POST",
                {"m33_device_id": "required", "ble_name": "optional", "trust_status": "trusted"},
            )
        )
        next_action = actions[-1]
    else:
        latest_sync_model = _latest_plan_device_sync(db, plan.id, trusted_device["id"])
        latest_sync = _sync_dict(latest_sync_model) if latest_sync_model else None
        if latest_sync_model is None or latest_sync_model.plan_version != plan.version:
            status = "sync_required"
            actions.append(
                _accepted_plan_action(
                    "SYNC_ACCEPTED_PLAN_TO_M33",
                    "同步已接受计划到 M33",
                    f"/api/rehab-arm/app/v1/training-plans/{plan.id}/sync-to-device",
                    "POST",
                    {"device_id": trusted_device["id"]},
                )
            )
            next_action = actions[-1]
        elif latest_sync_model.sync_status in {"pending", "sent"}:
            status = "m33_decision_pending"
            actions.append(
                _accepted_plan_action(
                    "RECORD_M33_DECISION",
                    "记录 M33 决策",
                    f"/api/rehab-arm/app/v1/devices/{trusted_device['id']}/m33-status",
                    "POST",
                    {"sync_id": latest_sync_model.id, "sync_status": "m33_accepted_or_m33_rejected"},
                )
            )
            next_action = actions[-1]
        elif latest_sync_model.sync_status == "m33_rejected":
            status = "m33_rejected_review_required"
            actions.append(
                _accepted_plan_action(
                    "RESYNC_ACCEPTED_PLAN_AFTER_REVIEW",
                    "复核后重新同步计划",
                    f"/api/rehab-arm/app/v1/training-plans/{plan.id}/sync-to-device",
                    "POST",
                    {"device_id": trusted_device["id"]},
                )
            )
            next_action = actions[-1]
        else:
            readiness = get_training_readiness(db, user_id, plan.id, trusted_device["id"])
            if readiness["can_start"]:
                status = "ready_to_start"
                actions.append(
                    _accepted_plan_action(
                        "START_TRAINING_RECORD",
                        "开始训练记录",
                        "/api/rehab-arm/app/v1/training-sessions/start",
                        "POST",
                        {"plan_id": plan.id, "device_id": trusted_device["id"]},
                    )
                )
            else:
                status = "preflight_required"
                actions.append(
                    _accepted_plan_action(
                        "CHECK_START_READINESS",
                        "检查训练开始条件",
                        f"/api/rehab-arm/app/v1/training-plans/{plan.id}/readiness",
                        "GET",
                        {"device_id": trusted_device["id"]},
                    )
                )
            next_action = actions[-1]
    return {
        "status": status,
        "draft": accepted_draft,
        "plan": plan_data,
        "device": trusted_device,
        "latest_sync": latest_sync,
        "next_action": next_action,
        "actions": actions,
        "control_boundary": "accepted_plan_guide_evidence_only_not_motion_permission",
    }


def get_app_bootstrap(db: Session, user_id: str) -> dict:
    devices = list_devices(db, user_id)
    plans = list_training_plans(db, user_id)
    sessions = list_training_sessions(db, user_id, limit=5)
    reports = list_training_reports(db, user_id, limit=5)
    drafts = list_ai_training_drafts(db, user_id, status="open", limit=1)
    all_drafts = list_ai_training_drafts(db, user_id, status="all", limit=5)
    preflights = list_preflight_checks(db, user_id, limit=1)
    offline_queue = _app_offline_queue_items(db, user_id, limit=20)
    profile = get_profile(db, user_id)
    active_session = sessions[0] if sessions and sessions[0]["status"] in {"started", "in_progress", "paused"} else None
    latest_report = latest_training_report(db, user_id)
    latest_open_ai_draft = drafts[0] if drafts else None
    onboarding_guide = _app_onboarding_guide(profile, devices, plans)
    primary_plan = next((plan for plan in plans if plan["status"] not in {"archived", "rejected"}), None)
    primary_device = next((device for device in devices if device["trust_status"] != "revoked"), None)
    primary_start_guide = None
    if primary_plan and primary_device:
        primary_start_guide = get_training_start_guide(db, user_id, primary_plan["id"], primary_device["id"])
    safety_review_guide = _app_safety_review_guide(db, user_id, sessions)
    accepted_plan_guide = _app_accepted_plan_guide(db, user_id, all_drafts, devices)
    finished_session_report_guide = _app_finished_session_report_guide(db, user_id, sessions)
    offline_sync_guide = _app_offline_sync_guide(offline_queue)
    session_recovery_guide = _app_session_recovery_guide(db, user_id, active_session)
    ai_draft_review_guide = _app_ai_draft_review_guide(latest_open_ai_draft)
    report_followup_guide = _app_report_followup_guide(latest_report, all_drafts)
    daily_action_guide = _app_daily_action_guide(
        onboarding_guide,
        active_session,
        finished_session_report_guide,
        primary_start_guide,
        latest_report,
        latest_open_ai_draft,
        offline_sync_guide,
        safety_review_guide,
        accepted_plan_guide,
    )
    care_summary = _app_care_summary(onboarding_guide, primary_start_guide, sessions, reports, all_drafts, offline_queue)
    home_related_actions = _app_home_related_actions(
        daily_action_guide,
        {
            "onboarding_guide": onboarding_guide,
            "primary_start_guide": primary_start_guide,
            "session_recovery_guide": session_recovery_guide,
            "finished_session_report_guide": finished_session_report_guide,
            "ai_draft_review_guide": ai_draft_review_guide,
            "report_followup_guide": report_followup_guide,
            "offline_sync_guide": offline_sync_guide,
            "safety_review_guide": safety_review_guide,
            "accepted_plan_guide": accepted_plan_guide,
        },
    )
    return {
        "profile": profile,
        "devices": devices,
        "training_plans": plans,
        "onboarding_guide": onboarding_guide,
        "active_session": active_session,
        "primary_start_guide": primary_start_guide,
        "daily_action_guide": daily_action_guide,
        "home_status_guide": _app_home_status_guide(daily_action_guide, care_summary, home_related_actions),
        "care_summary": care_summary,
        "care_timeline": _app_care_timeline(sessions, reports, all_drafts, offline_queue),
        "offline_sync_guide": offline_sync_guide,
        "session_recovery_guide": session_recovery_guide,
        "finished_session_report_guide": finished_session_report_guide,
        "ai_draft_review_guide": ai_draft_review_guide,
        "report_followup_guide": report_followup_guide,
        "device_operational_guide": _app_device_operational_guide(db, user_id, devices, primary_plan),
        "safety_review_guide": safety_review_guide,
        "accepted_plan_guide": accepted_plan_guide,
        "latest_preflight": preflights[0] if preflights else None,
        "latest_emg": latest_emg_summary(db, user_id),
        "latest_report": latest_report,
        "latest_open_ai_draft": latest_open_ai_draft,
        "platform_sync": get_platform_sync_status(db, user_id),
        "offline_queue": offline_queue,
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


def unbind_device(db: Session, user_id: str, device_id: str, reason: str = "") -> dict:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    device.trust_status = "revoked"
    db.add(device)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.device.unbound",
        resource_type="rehab_app_device_binding",
        resource_id=device.id,
        after={
            "m33_device_id": device.m33_device_id,
            "reason": reason,
            "control_boundary": "device_unbound_history_retained_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(device)
    return {
        **_device_dict(device),
        "unbind_reason": reason,
        "control_boundary": "device_unbound_history_retained_not_motion_permission",
    }


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


def _require_device_not_revoked(device: RehabAppDeviceBinding) -> None:
    if device.trust_status == "revoked":
        raise AppError(
            "DEVICE_REVOKED",
            "device binding is revoked and cannot be used for training, BLE, or M33 decisions",
            status_code=409,
            details={
                "device_id": device.id,
                "m33_device_id": device.m33_device_id,
                "control_boundary": "device_revoked_not_motion_permission",
            },
        )


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


def _require_training_plan_usable(plan: RehabAppTrainingPlan) -> None:
    if plan.status in {"archived", "rejected"}:
        raise AppError(
            "TRAINING_PLAN_NOT_USABLE",
            "archived or rejected training plans cannot be synced or started",
            status_code=409,
            details={
                "plan_id": plan.id,
                "plan_status": plan.status,
                "control_boundary": "training_plan_closed_not_motion_permission",
            },
        )


def _normalized_plan_terms(plan: RehabAppTrainingPlan) -> set[str]:
    terms = {str(plan.movement_type or "").lower().replace("-", "_").replace(" ", "_")}
    terms.update(str(joint).lower().replace("-", "_").replace(" ", "_") for joint in (plan.target_joints or []))
    return {term for term in terms if term}


def _plan_constraint_violations(profile: RehabAppUserProfile | None, plan: RehabAppTrainingPlan) -> list[dict]:
    if profile is None:
        return []
    constraints = [str(item).strip().lower() for item in (profile.medical_constraints or []) if str(item).strip()]
    if not constraints:
        return []
    terms = _normalized_plan_terms(plan)
    max_deg = None
    if isinstance(plan.target_angle_range, dict):
        max_deg = plan.target_angle_range.get("max_deg")
    violations: list[dict] = []
    for constraint in constraints:
        compact = constraint.replace("-", " ").replace("_", " ")
        if any(token in compact for token in ["no overhead", "avoid overhead", "no over shoulder", "禁止过头", "避免过肩"]):
            if "overhead" in terms or "shoulder" in terms or any(term.startswith("shoulder_") for term in terms) or (isinstance(max_deg, (int, float)) and max_deg > 90):
                violations.append({"constraint": constraint, "reason": "overhead_or_shoulder_motion"})
            continue
        if compact.startswith("no ") or compact.startswith("avoid "):
            blocked = compact.split(" ", 1)[1].strip().replace(" ", "_")
            if blocked and any(blocked in term or term in blocked for term in terms):
                violations.append({"constraint": constraint, "reason": "blocked_plan_term", "matched": blocked})
    return violations


def _latest_plan_constraint_review(db: Session, user_id: str, plan_id: str, plan_version: int) -> RehabAppPlanConstraintReview | None:
    return db.scalar(
        select(RehabAppPlanConstraintReview)
        .where(
            RehabAppPlanConstraintReview.user_id == user_id,
            RehabAppPlanConstraintReview.plan_id == plan_id,
            RehabAppPlanConstraintReview.plan_version == plan_version,
            RehabAppPlanConstraintReview.review_status.in_(["approved", "conditional"]),
        )
        .order_by(RehabAppPlanConstraintReview.created_at.desc(), RehabAppPlanConstraintReview.id.desc())
        .limit(1)
    )


def _require_plan_matches_profile_constraints(db: Session, user_id: str, plan: RehabAppTrainingPlan) -> None:
    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    violations = _plan_constraint_violations(profile, plan)
    if violations:
        review = _latest_plan_constraint_review(db, user_id, plan.id, plan.version)
        if review is not None:
            return
        raise AppError(
            "TRAINING_PLAN_CONTRAINDICATED",
            "training plan conflicts with the user's recorded medical constraints and needs therapist review",
            status_code=409,
            details={
                "plan_id": plan.id,
                "plan_version": plan.version,
                "violations": violations,
                "required_review_endpoint": f"/api/rehab-arm/app/v1/training-plans/{plan.id}/constraint-reviews",
                "control_boundary": "training_plan_blocked_not_medical_diagnosis_or_motion_permission",
            },
        )


def create_plan_constraint_review(db: Session, user_id: str, plan_id: str, payload: RehabAppPlanConstraintReviewCreate) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    violations = _plan_constraint_violations(profile, plan)
    if not violations and payload.review_status != "rejected":
        raise AppError(
            "CONSTRAINT_REVIEW_NOT_REQUIRED",
            "this plan has no detected profile-constraint conflict that requires review",
            status_code=409,
            details={"plan_id": plan.id, "plan_version": plan.version, "control_boundary": "constraint_review_evidence_only_not_motion_permission"},
        )
    review = RehabAppPlanConstraintReview(
        user_id=user_id,
        plan_id=plan.id,
        plan_version=plan.version,
        reviewer_role=payload.reviewer_role,
        review_status=payload.review_status,
        reviewed_constraints=payload.reviewed_constraints or [item["constraint"] for item in violations],
        review_note=payload.review_note,
    )
    db.add(review)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action=f"rehab_app.training_plan.constraint_review.{review.review_status}",
        resource_type="rehab_app_plan_constraint_review",
        resource_id=review.id,
        after={
            "plan_id": plan.id,
            "plan_version": plan.version,
            "review_status": review.review_status,
            "control_boundary": "constraint_review_evidence_only_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(review)
    return _constraint_review_dict(review)


def list_plan_constraint_reviews(db: Session, user_id: str, plan_id: str) -> list[dict]:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    reviews = list(
        db.scalars(
            select(RehabAppPlanConstraintReview)
            .where(RehabAppPlanConstraintReview.user_id == user_id, RehabAppPlanConstraintReview.plan_id == plan.id)
            .order_by(RehabAppPlanConstraintReview.created_at.desc(), RehabAppPlanConstraintReview.id.desc())
        )
    )
    return [_constraint_review_dict(review) for review in reviews]


def get_training_readiness(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    checks: list[dict] = []
    plan = db.get(RehabAppTrainingPlan, plan_id)
    device = db.get(RehabAppDeviceBinding, device_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)

    def add_check(name: str, status: str, code: str = "", detail: dict | None = None) -> None:
        checks.append({"name": name, "status": status, "code": code, "detail": detail or {}})

    if plan.status in {"archived", "rejected"}:
        add_check("plan_usable", "blocked", "TRAINING_PLAN_NOT_USABLE", {"plan_status": plan.status})
    else:
        add_check("plan_usable", "passed", detail={"plan_status": plan.status})

    if device.trust_status == "revoked":
        add_check("device_trusted", "blocked", "DEVICE_REVOKED", {"trust_status": device.trust_status})
    else:
        add_check("device_trusted", "passed", detail={"trust_status": device.trust_status})

    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    violations = _plan_constraint_violations(profile, plan)
    constraint_review = _latest_plan_constraint_review(db, user_id, plan.id, plan.version)
    if violations and constraint_review is None:
        add_check("profile_constraints", "blocked", "TRAINING_PLAN_CONTRAINDICATED", {"violations": violations, "plan_version": plan.version})
    else:
        add_check("profile_constraints", "passed", detail={"review_id": constraint_review.id if constraint_review else ""})

    active_session = db.scalar(
        select(RehabAppTrainingSession)
        .where(
            RehabAppTrainingSession.user_id == user_id,
            RehabAppTrainingSession.device_id == device.id,
            RehabAppTrainingSession.status.in_(["started", "in_progress", "paused"]),
        )
        .order_by(RehabAppTrainingSession.started_at.desc(), RehabAppTrainingSession.id.desc())
        .limit(1)
    )
    if active_session is not None:
        add_check(
            "device_session_available",
            "blocked",
            "ACTIVE_TRAINING_SESSION_EXISTS",
            {"active_session_id": active_session.id, "active_session_status": active_session.status},
        )
    else:
        add_check("device_session_available", "passed")

    sync = _latest_plan_device_sync(db, plan.id, device.id)
    if sync is None or sync.sync_status != "m33_accepted" or sync.plan_version != plan.version:
        add_check(
            "m33_acceptance",
            "blocked",
            "M33_ACCEPTANCE_REQUIRED",
            {
                "sync_id": sync.id if sync else "",
                "sync_status": sync.sync_status if sync else "missing",
                "accepted_plan_version": sync.plan_version if sync else None,
                "required_plan_version": plan.version,
            },
        )
    else:
        add_check("m33_acceptance", "passed", detail={"sync_id": sync.id, "plan_version": sync.plan_version})

    if sync and sync.sync_status == "m33_accepted" and sync.plan_version == plan.version:
        preflight = _latest_passed_preflight(db, user_id, plan.id, device.id)
        if preflight is None or preflight.sync_id != sync.id or preflight.plan_version != plan.version:
            add_check("preflight", "blocked", "PREFLIGHT_CHECK_REQUIRED", {"sync_id": sync.id, "required_plan_version": plan.version})
        else:
            add_check("preflight", "passed", detail={"preflight_id": preflight.id, "sync_id": preflight.sync_id})
    else:
        add_check("preflight", "waiting", "M33_ACCEPTANCE_REQUIRED")

    safety_block: dict | None = None
    recent_sessions = list(
        db.scalars(
            select(RehabAppTrainingSession)
            .where(
                RehabAppTrainingSession.user_id == user_id,
                RehabAppTrainingSession.device_id == device.id,
                RehabAppTrainingSession.status.in_(["finished", "cancelled"]),
            )
            .order_by(RehabAppTrainingSession.started_at.desc(), RehabAppTrainingSession.id.desc())
            .limit(5)
        )
    )
    for session in recent_sessions:
        event = _latest_unreviewed_critical_safety_event(db, user_id, session.id)
        if event is not None:
            safety_block = {"session_id": session.id, "event_id": event.id, "event_type": event.event_type}
            break
    if safety_block:
        add_check("safety_review", "blocked", "SAFETY_REVIEW_REQUIRED", safety_block)
    else:
        add_check("safety_review", "passed")

    status = "ready" if all(check["status"] == "passed" for check in checks) else "blocked"
    return {
        "plan_id": plan.id,
        "device_id": device.id,
        "status": status,
        "can_start": status == "ready",
        "checks": checks,
        "control_boundary": "training_readiness_evidence_only_not_motion_permission",
    }


def get_training_start_guide(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    readiness = get_training_readiness(db, user_id, plan_id, device_id)
    check_by_name = {check["name"]: check for check in readiness["checks"]}

    def action(
        code: str,
        actor: str,
        title: str,
        description: str,
        endpoint: str = "",
        method: str = "",
        payload_hint: dict | None = None,
    ) -> dict:
        return {
            "code": code,
            "actor": actor,
            "title": title,
            "description": description,
            "endpoint": endpoint,
            "method": method,
            "payload_hint": payload_hint or {},
        }

    action_map = {
        "TRAINING_PLAN_NOT_USABLE": action(
            "TRAINING_PLAN_NOT_USABLE",
            "patient_or_therapist",
            "选择可用训练计划",
            "当前计划已归档或被拒绝，不能继续训练。请回到训练计划列表选择 active/draft 计划，或从复盘记录生成新计划。",
            "/api/rehab-arm/app/v1/training-plans",
            "GET",
        ),
        "DEVICE_REVOKED": action(
            "DEVICE_REVOKED",
            "patient_or_therapist",
            "重新绑定可信设备",
            "当前设备已解绑冻结，只能查看历史和诊断。请绑定可信 M33 设备后再同步训练计划。",
            "/api/rehab-arm/app/v1/devices/bind",
            "POST",
            {"m33_device_id": "required", "ble_name": "optional", "trust_status": "trusted"},
        ),
        "TRAINING_PLAN_CONTRAINDICATED": action(
            "TRAINING_PLAN_CONTRAINDICATED",
            "therapist",
            "完成禁忌项复核",
            "计划与康复档案约束冲突，需要治疗师记录当前版本的复核证据，再重新同步给 M33。",
            f"/api/rehab-arm/app/v1/training-plans/{plan_id}/constraint-reviews",
            "POST",
            {"reviewer_role": "therapist", "review_status": "approved_or_conditional", "review_note": "required"},
        ),
        "ACTIVE_TRAINING_SESSION_EXISTS": action(
            "ACTIVE_TRAINING_SESSION_EXISTS",
            "patient_or_therapist",
            "恢复或结束当前训练",
            "该设备已有 started/in_progress/paused 训练会话。请先恢复、完成或取消当前会话，再开始新的训练。",
            "/api/rehab-arm/app/v1/me",
            "GET",
        ),
        "M33_ACCEPTANCE_REQUIRED": action(
            "M33_ACCEPTANCE_REQUIRED",
            "m33_or_patient",
            "同步计划并等待 M33 接受",
            "当前计划版本还没有 M33 accepted 证据。请同步当前版本，等待 M33 固件侧审核并回传接受状态。",
            f"/api/rehab-arm/app/v1/training-plans/{plan_id}/sync-to-device",
            "POST",
            {"device_id": device_id},
        ),
        "PREFLIGHT_CHECK_REQUIRED": action(
            "PREFLIGHT_CHECK_REQUIRED",
            "patient_or_therapist",
            "完成训练前检查",
            "M33 已接受当前计划后，还需要提交与当前 sync_id/plan_version 匹配的 preflight 检查。",
            "/api/rehab-arm/app/v1/training-preflight",
            "POST",
            {
                "plan_id": plan_id,
                "device_id": device_id,
                "sync_id": check_by_name.get("preflight", {}).get("detail", {}).get("sync_id", "required"),
                "checklist": {
                    "device_worn_correctly": True,
                    "pain_within_limit": True,
                    "stop_explained": True,
                    "m33_plan_accepted": True,
                },
            },
        ),
        "SAFETY_REVIEW_REQUIRED": action(
            "SAFETY_REVIEW_REQUIRED",
            "therapist",
            "复核上一轮安全事件",
            "同一设备最近训练存在未复核 critical 安全事件，需要记录 approved/conditional safety_review 后才能继续。",
            "/api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events",
            "POST",
            {"event_type": "safety_review", "severity": "info", "payload": {"review_status": "approved_or_conditional"}},
        ),
    }

    ordered_steps: list[dict] = []
    for check in readiness["checks"]:
        code = check.get("code") or ""
        if check["status"] == "passed":
            ordered_steps.append({"check": check["name"], "status": "done", "code": code, "action": {}})
        elif check["status"] == "waiting":
            ordered_steps.append({"check": check["name"], "status": "waiting", "code": code, "action": action_map.get(code, {})})
        else:
            ordered_steps.append({"check": check["name"], "status": "todo", "code": code, "action": action_map.get(code, {})})

    next_action = {}
    for step in ordered_steps:
        if step["status"] == "todo":
            next_action = step["action"]
            break
    if not next_action and readiness["can_start"]:
        next_action = action(
            "READY_TO_START",
            "patient_or_therapist",
            "可以创建训练会话",
            "后端启动前置条件已满足。点击开始只会创建 App 训练记录，真实运动仍由 M33/机器人侧决定。",
            "/api/rehab-arm/app/v1/training-sessions/start",
            "POST",
            {"plan_id": plan_id, "device_id": device_id},
        )

    return {
        "plan_id": plan_id,
        "device_id": device_id,
        "can_start": readiness["can_start"],
        "readiness": readiness,
        "next_action": next_action,
        "steps": ordered_steps,
        "actions": [
            action(
                "VIEW_START_GUIDE",
                "patient_or_therapist",
                "查看训练开始指引",
                "查看当前计划、设备、M33、preflight 和安全复核的完整开始条件。",
                f"/api/rehab-arm/app/v1/training-plans/{plan_id}/start-guide",
                "GET",
                {"device_id": device_id},
            ),
            action(
                "CHECK_START_READINESS",
                "patient_or_therapist",
                "检查训练开始条件",
                "读取当前计划和设备是否满足 App 记录开始条件。结果仍然不是硬件运动许可。",
                f"/api/rehab-arm/app/v1/training-plans/{plan_id}/readiness",
                "GET",
                {"device_id": device_id},
            ),
            *([next_action] if next_action else []),
        ],
        "control_boundary": "training_start_guide_evidence_only_not_motion_permission",
    }


def sync_training_plan_to_device(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    _require_training_plan_usable(plan)
    _require_plan_matches_profile_constraints(db, user_id, plan)
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    _require_device_not_revoked(device)
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
    _require_device_not_revoked(device)
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


REQUIRED_PREFLIGHT_CHECKS = {
    "device_worn_correctly",
    "pain_within_limit",
    "stop_explained",
    "m33_plan_accepted",
}


def _require_pain_preflight_safe(db: Session, user_id: str, payload: RehabAppPreflightCheckCreate) -> None:
    if payload.pain_before is None or payload.checked_by_role == "therapist":
        return
    profile = db.scalar(select(RehabAppUserProfile).where(RehabAppUserProfile.user_id == user_id))
    baseline = profile.pain_baseline if profile and profile.pain_baseline is not None else None
    review_threshold = min(7.0, baseline + 2.0) if baseline is not None else 7.0
    if payload.pain_before >= review_threshold:
        raise AppError(
            "PREFLIGHT_PAIN_REVIEW_REQUIRED",
            "preflight pain score requires therapist review before a training session can start",
            status_code=409,
            details={
                "pain_before": payload.pain_before,
                "pain_baseline": baseline,
                "review_threshold": review_threshold,
                "allowed_override_role": "therapist",
                "control_boundary": "preflight_blocked_not_medical_diagnosis_or_motion_permission",
            },
        )


def create_preflight_check(db: Session, user_id: str, payload: RehabAppPreflightCheckCreate) -> dict:
    plan = db.get(RehabAppTrainingPlan, payload.plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    _require_training_plan_usable(plan)
    device = db.get(RehabAppDeviceBinding, payload.device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    _require_device_not_revoked(device)
    sync = db.get(RehabAppTrainingPlanSync, payload.sync_id)
    if sync is None or sync.plan_id != plan.id or sync.device_id != device.id:
        raise AppError("TRAINING_PLAN_SYNC_NOT_FOUND", "training plan sync not found for this plan/device", status_code=404)
    if sync.sync_status != "m33_accepted" or sync.plan_version != plan.version:
        raise AppError(
            "M33_ACCEPTANCE_REQUIRED",
            "preflight requires the latest plan version to be accepted by M33",
            status_code=409,
            details={
                "plan_id": plan.id,
                "device_id": device.id,
                "sync_id": sync.id,
                "sync_status": sync.sync_status,
                "accepted_plan_version": sync.plan_version,
                "required_plan_version": plan.version,
                "control_boundary": "preflight_blocked_not_motion_permission",
            },
        )
    checklist = payload.checklist or {}
    missing = sorted(item for item in REQUIRED_PREFLIGHT_CHECKS if checklist.get(item) is not True)
    if missing:
        raise AppError(
            "PREFLIGHT_CHECK_INCOMPLETE",
            "required preflight checklist items are missing or false",
            status_code=409,
            details={
                "missing": missing,
                "required": sorted(REQUIRED_PREFLIGHT_CHECKS),
                "control_boundary": "preflight_blocked_not_motion_permission",
            },
        )
    _require_pain_preflight_safe(db, user_id, payload)
    check = RehabAppPreflightCheck(
        user_id=user_id,
        plan_id=plan.id,
        device_id=device.id,
        sync_id=sync.id,
        plan_version=plan.version,
        status="passed",
        checked_by_role=payload.checked_by_role,
        checklist=checklist,
        pain_before=payload.pain_before,
        notes=payload.notes,
    )
    db.add(check)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.preflight_check.passed",
        resource_type="rehab_app_preflight_check",
        resource_id=check.id,
        after={
            "plan_id": plan.id,
            "device_id": device.id,
            "sync_id": sync.id,
            "plan_version": plan.version,
            "control_boundary": "preflight_check_evidence_only_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(check)
    return _preflight_dict(check)


def list_preflight_checks(
    db: Session,
    user_id: str,
    plan_id: str | None = None,
    device_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    conditions = [RehabAppPreflightCheck.user_id == user_id]
    if plan_id:
        conditions.append(RehabAppPreflightCheck.plan_id == plan_id)
    if device_id:
        conditions.append(RehabAppPreflightCheck.device_id == device_id)
    checks = list(
        db.scalars(
            select(RehabAppPreflightCheck)
            .where(*conditions)
            .order_by(RehabAppPreflightCheck.created_at.desc(), RehabAppPreflightCheck.id.desc())
            .limit(limit)
        )
    )
    return [_preflight_dict(check) for check in checks]


BLE_MESSAGE_TYPES = {
    "app_hello",
    "device_status_request",
    "training_plan_push",
    "training_session_start_request",
    "training_progress_notify",
    "training_pause_request",
    "training_stop_request",
    "diagnostic_snapshot_request",
}

FORBIDDEN_BLE_KEYS = {
    "can",
    "can_frame",
    "current",
    "torque",
    "motor",
    "motor_command",
    "raw_position",
    "raw_velocity",
    "position_setpoint",
    "velocity_setpoint",
    "m33_override",
    "estop_release",
    "emergency_stop_release",
}


def _contains_forbidden_ble_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(term in key_text for term in FORBIDDEN_BLE_KEYS):
                return True
            if _contains_forbidden_ble_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_ble_key(item) for item in value)
    return False


def _require_user_device(db: Session, user_id: str, device_id: str) -> RehabAppDeviceBinding:
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    _require_device_not_revoked(device)
    return device


def _ble_base_payload(device: RehabAppDeviceBinding, message_type: str, message_id: str) -> dict:
    return {
        "schema_version": "rehab_app_ble_v1",
        "message_type": message_type,
        "message_id": message_id,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "device_id": device.m33_device_id,
        "control_boundary": "ble_message_contract_only_not_motor_command",
    }


def create_ble_message(db: Session, user_id: str, device_id: str, payload: RehabAppBleMessageCreate) -> dict:
    if payload.message_type not in BLE_MESSAGE_TYPES:
        raise AppError("BLE_MESSAGE_TYPE_NOT_ALLOWED", "BLE message type is not allowed", status_code=422)
    if _contains_forbidden_ble_key(payload.extra_payload):
        raise AppError(
            "BLE_PAYLOAD_NOT_ALLOWED",
            "BLE payload must not contain motor, CAN, raw motion, M33 override, or emergency-stop release fields",
            status_code=422,
            details={"control_boundary": "ble_message_contract_only_not_motor_command"},
        )
    device = _require_user_device(db, user_id, device_id)
    message_id = payload.client_message_id or str(uuid.uuid4())
    ble_payload = _ble_base_payload(device, payload.message_type, message_id)
    related_plan_id = ""
    related_session_id = ""
    if payload.message_type == "training_plan_push":
        plan = db.get(RehabAppTrainingPlan, payload.plan_id)
        if plan is None or plan.user_id != user_id:
            raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
        related_plan_id = plan.id
        ble_payload.update(
            {
                "user_id": user_id,
                "plan_id": plan.id,
                "plan_version": plan.version,
                "movement_type": plan.movement_type,
                "sets": plan.sets,
                "reps": plan.reps,
                "duration_sec": plan.duration_sec,
                "target_angle_range": plan.target_angle_range or {},
                "speed_level": plan.speed_level,
                "assist_level": plan.assist_level,
                "emg_policy": plan.emg_policy or {},
                "safety_constraints": {
                    "require_fresh_m33_heartbeat": True,
                    "stop_on_pain_report": True,
                    **(plan.safety_constraints or {}),
                },
            }
        )
    elif payload.message_type in {"training_session_start_request", "training_progress_notify", "training_pause_request", "training_stop_request"}:
        session = _require_user_session(db, user_id, payload.session_id)
        if session.device_id != device.id:
            raise AppError("TRAINING_SESSION_DEVICE_MISMATCH", "training session does not belong to this device", status_code=409)
        related_session_id = session.id
        related_plan_id = session.plan_id
        ble_payload.update(
            {
                "session_id": session.id,
                "plan_id": session.plan_id,
                "session_status": session.status,
                "completion_rate": session.completion_rate,
                "interruption_count": session.interruption_count,
                "m33_reject_count": session.m33_reject_count,
            }
        )
        if payload.message_type == "training_session_start_request":
            plan = db.get(RehabAppTrainingPlan, session.plan_id)
            sync = _latest_plan_device_sync(db, session.plan_id, device.id)
            if plan is None or sync is None or sync.sync_status != "m33_accepted" or sync.plan_version != plan.version:
                raise AppError(
                    "M33_ACCEPTANCE_REQUIRED",
                    "M33 must accept the latest plan version before a BLE session start request can be prepared",
                    status_code=409,
                    details={"control_boundary": "ble_message_contract_only_not_motor_command"},
                )
    ble_payload.update(payload.extra_payload)
    message = RehabAppBleMessage(
        user_id=user_id,
        device_id=device.id,
        message_type=payload.message_type,
        related_plan_id=related_plan_id,
        related_session_id=related_session_id,
        payload=ble_payload,
    )
    db.add(message)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.ble_message.created",
        resource_type="rehab_app_ble_message",
        resource_id=message.id,
        after={"message_type": message.message_type, "control_boundary": "ble_message_contract_only_not_motor_command"},
    )
    db.commit()
    db.refresh(message)
    return _ble_message_dict(message)


def update_ble_message_ack(db: Session, user_id: str, device_id: str, message_id: str, ack_status: str, ack_payload: dict) -> dict:
    if _contains_forbidden_ble_key(ack_payload):
        raise AppError(
            "BLE_ACK_PAYLOAD_NOT_ALLOWED",
            "BLE ACK payload must not contain motor, CAN, raw motion, M33 override, or emergency-stop release fields",
            status_code=422,
            details={"control_boundary": "ble_ack_evidence_only_not_motion_permission"},
        )
    device = _require_user_device(db, user_id, device_id)
    message = db.get(RehabAppBleMessage, message_id)
    if message is None or message.user_id != user_id or message.device_id != device.id:
        raise AppError("BLE_MESSAGE_NOT_FOUND", "BLE message not found", status_code=404)
    message.ack_status = ack_status
    message.ack_payload = {
        **ack_payload,
        "m33_authority": "final_safety_authority",
        "control_boundary": "ble_ack_evidence_only_not_motion_permission",
    }
    message.acked_at = datetime.now(timezone.utc)
    device.last_seen_at = datetime.now(timezone.utc)
    db.add(message)
    db.add(device)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id or None,
        actor_type="m33",
        actor_id=device.m33_device_id,
        action=f"rehab_app.ble_message.{ack_status}",
        resource_type="rehab_app_ble_message",
        resource_id=message.id,
        after={"ack_status": ack_status, "control_boundary": "ble_ack_evidence_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(message)
    return _ble_message_dict(message)


def list_ble_messages(db: Session, user_id: str, device_id: str, limit: int = 50) -> list[dict]:
    device = _require_user_device(db, user_id, device_id)
    messages = list(
        db.scalars(
            select(RehabAppBleMessage)
            .where(RehabAppBleMessage.user_id == user_id, RehabAppBleMessage.device_id == device.id)
            .order_by(RehabAppBleMessage.created_at.desc())
            .limit(limit)
        )
    )
    return [_ble_message_dict(message) for message in messages]


def _latest_plan_device_sync(db: Session, plan_id: str, device_id: str) -> RehabAppTrainingPlanSync | None:
    return db.scalar(
        select(RehabAppTrainingPlanSync)
        .where(RehabAppTrainingPlanSync.plan_id == plan_id, RehabAppTrainingPlanSync.device_id == device_id)
        .order_by(RehabAppTrainingPlanSync.synced_at.desc())
        .limit(1)
    )


def _latest_passed_preflight(db: Session, user_id: str, plan_id: str, device_id: str) -> RehabAppPreflightCheck | None:
    return db.scalar(
        select(RehabAppPreflightCheck)
        .where(
            RehabAppPreflightCheck.user_id == user_id,
            RehabAppPreflightCheck.plan_id == plan_id,
            RehabAppPreflightCheck.device_id == device_id,
            RehabAppPreflightCheck.status == "passed",
        )
        .order_by(RehabAppPreflightCheck.created_at.desc(), RehabAppPreflightCheck.id.desc())
        .limit(1)
    )


def _require_user_session(db: Session, user_id: str, session_id: str) -> RehabAppTrainingSession:
    session = db.get(RehabAppTrainingSession, session_id)
    if session is None or session.user_id != user_id:
        raise AppError("TRAINING_SESSION_NOT_FOUND", "training session not found", status_code=404)
    return session


def _require_active_training_session(session: RehabAppTrainingSession) -> None:
    if session.status not in {"started", "in_progress"}:
        raise AppError(
            "TRAINING_SESSION_NOT_ACTIVE",
            "training session is not active and cannot be changed",
            status_code=409,
            details={
                "session_id": session.id,
                "status": session.status,
                "control_boundary": "training_session_locked_not_motion_permission",
            },
        )


def _require_paused_training_session(session: RehabAppTrainingSession) -> None:
    if session.status != "paused":
        raise AppError(
            "TRAINING_SESSION_NOT_PAUSED",
            "training session is not paused and cannot be resumed",
            status_code=409,
            details={
                "session_id": session.id,
                "status": session.status,
                "control_boundary": "training_session_state_change_only_not_motion_permission",
            },
        )


def _session_report(db: Session, user_id: str, session_id: str) -> RehabAppTrainingReport | None:
    return db.scalar(select(RehabAppTrainingReport).where(RehabAppTrainingReport.user_id == user_id, RehabAppTrainingReport.session_id == session_id))


def _require_session_report_open(db: Session, user_id: str, session: RehabAppTrainingSession) -> None:
    report = _session_report(db, user_id, session.id)
    if report is not None:
        raise AppError(
            "TRAINING_REPORT_ALREADY_GENERATED",
            "session evidence is locked after a training report is generated",
            status_code=409,
            details={
                "session_id": session.id,
                "report_id": report.id,
                "control_boundary": "training_report_locked_not_motion_permission",
            },
        )


def _latest_safety_review_after(db: Session, user_id: str, session_id: str, created_at: object) -> RehabAppSessionSafetyEvent | None:
    return db.scalar(
        select(RehabAppSessionSafetyEvent)
        .where(
            RehabAppSessionSafetyEvent.user_id == user_id,
            RehabAppSessionSafetyEvent.session_id == session_id,
            RehabAppSessionSafetyEvent.event_type == "safety_review",
            RehabAppSessionSafetyEvent.severity.in_(["info", "warning"]),
            RehabAppSessionSafetyEvent.created_at >= created_at,
        )
        .order_by(RehabAppSessionSafetyEvent.created_at.desc(), RehabAppSessionSafetyEvent.id.desc())
        .limit(1)
    )


def _latest_unreviewed_critical_safety_event(db: Session, user_id: str, session_id: str) -> RehabAppSessionSafetyEvent | None:
    critical_events = list(
        db.scalars(
            select(RehabAppSessionSafetyEvent)
            .where(
                RehabAppSessionSafetyEvent.user_id == user_id,
                RehabAppSessionSafetyEvent.session_id == session_id,
                RehabAppSessionSafetyEvent.severity == "critical",
                RehabAppSessionSafetyEvent.event_type != "safety_review",
            )
            .order_by(RehabAppSessionSafetyEvent.created_at.desc(), RehabAppSessionSafetyEvent.id.desc())
        )
    )
    for event in critical_events:
        review = _latest_safety_review_after(db, user_id, session_id, event.created_at)
        if review is None:
            return event
    return None


def _require_no_unreviewed_session_safety_event(db: Session, user_id: str, session: RehabAppTrainingSession, action: str) -> None:
    event = _latest_unreviewed_critical_safety_event(db, user_id, session.id)
    if event is not None:
        raise AppError(
            "SAFETY_REVIEW_REQUIRED",
            "a critical safety event requires therapist or engineer review before this workflow can continue",
            status_code=409,
            details={
                "session_id": session.id,
                "event_id": event.id,
                "event_type": event.event_type,
                "action": action,
                "required_event_type": "safety_review",
                "control_boundary": "session_safety_event_review_required_not_motion_permission",
            },
        )


def _require_no_unreviewed_device_safety_event(db: Session, user_id: str, device_id: str) -> None:
    recent_sessions = list(
        db.scalars(
            select(RehabAppTrainingSession)
            .where(
                RehabAppTrainingSession.user_id == user_id,
                RehabAppTrainingSession.device_id == device_id,
                RehabAppTrainingSession.status.in_(["finished", "cancelled"]),
            )
            .order_by(RehabAppTrainingSession.started_at.desc(), RehabAppTrainingSession.id.desc())
            .limit(5)
        )
    )
    for session in recent_sessions:
        _require_no_unreviewed_session_safety_event(db, user_id, session, "start_training_session")


def start_training_session(db: Session, user_id: str, plan_id: str, device_id: str) -> dict:
    plan = db.get(RehabAppTrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError("TRAINING_PLAN_NOT_FOUND", "training plan not found", status_code=404)
    _require_training_plan_usable(plan)
    _require_plan_matches_profile_constraints(db, user_id, plan)
    device = db.get(RehabAppDeviceBinding, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("DEVICE_NOT_FOUND", "device binding not found", status_code=404)
    _require_device_not_revoked(device)
    _require_no_unreviewed_device_safety_event(db, user_id, device.id)
    active_session = db.scalar(
        select(RehabAppTrainingSession)
        .where(
            RehabAppTrainingSession.user_id == user_id,
            RehabAppTrainingSession.device_id == device.id,
            RehabAppTrainingSession.status.in_(["started", "in_progress", "paused"]),
        )
        .order_by(RehabAppTrainingSession.started_at.desc())
        .limit(1)
    )
    if active_session is not None:
        raise AppError(
            "ACTIVE_TRAINING_SESSION_EXISTS",
            "finish or recover the active training session before starting another one on this device",
            status_code=409,
            details={
                "active_session_id": active_session.id,
                "active_session_status": active_session.status,
                "device_id": device.id,
                "control_boundary": "training_session_blocked_not_motion_permission",
            },
        )
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
    preflight = _latest_passed_preflight(db, user_id, plan.id, device.id)
    if preflight is None or preflight.sync_id != sync.id or preflight.plan_version != plan.version:
        raise AppError(
            "PREFLIGHT_CHECK_REQUIRED",
            "a current passed preflight check is required before starting a training session",
            status_code=409,
            details={
                "plan_id": plan.id,
                "device_id": device.id,
                "sync_id": sync.id,
                "required_plan_version": plan.version,
                "latest_preflight_id": preflight.id if preflight else None,
                "latest_preflight_sync_id": preflight.sync_id if preflight else None,
                "latest_preflight_plan_version": preflight.plan_version if preflight else None,
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
    _require_active_training_session(session)
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


def pause_training_session(db: Session, user_id: str, session_id: str, reason: str = "") -> dict:
    session = _require_user_session(db, user_id, session_id)
    _require_active_training_session(session)
    _require_session_report_open(db, user_id, session)
    session.status = "paused"
    if reason:
        session.user_note = f"{session.user_note}\nPause: {reason}".strip()
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.paused",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"reason": reason, "control_boundary": "training_session_pause_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def resume_training_session(db: Session, user_id: str, session_id: str, note: str = "") -> dict:
    session = _require_user_session(db, user_id, session_id)
    _require_paused_training_session(session)
    _require_session_report_open(db, user_id, session)
    _require_no_unreviewed_session_safety_event(db, user_id, session, "resume_training_session")
    session.status = "in_progress"
    if note:
        session.user_note = f"{session.user_note}\nResume: {note}".strip()
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.resumed",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"note": note, "control_boundary": "training_session_resume_only_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def cancel_training_session(db: Session, user_id: str, session_id: str, reason: str = "") -> dict:
    session = _require_user_session(db, user_id, session_id)
    if session.status not in {"started", "in_progress", "paused"}:
        raise AppError(
            "TRAINING_SESSION_NOT_ACTIVE",
            "training session is already closed and cannot be cancelled",
            status_code=409,
            details={
                "session_id": session.id,
                "status": session.status,
                "control_boundary": "training_session_locked_not_motion_permission",
            },
        )
    _require_session_report_open(db, user_id, session)
    session.status = "cancelled"
    session.ended_at = datetime.now(timezone.utc)
    if reason:
        session.user_note = f"{session.user_note}\nCancel: {reason}".strip()
    db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_session.cancelled",
        resource_type="rehab_app_training_session",
        resource_id=session.id,
        after={"reason": reason, "control_boundary": "training_session_cancelled_not_motion_permission"},
    )
    db.commit()
    db.refresh(session)
    return _session_dict(session)


def update_training_session_progress(db: Session, user_id: str, session_id: str, payload: dict) -> dict:
    session = _require_user_session(db, user_id, session_id)
    _require_active_training_session(session)
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


def record_session_safety_event(db: Session, user_id: str, session_id: str, payload: RehabAppSessionSafetyEventCreate) -> dict:
    session = _require_user_session(db, user_id, session_id)
    allowed_statuses = {"started", "in_progress", "paused"}
    if payload.event_type == "safety_review":
        allowed_statuses = allowed_statuses | {"finished", "cancelled"}
    if session.status not in allowed_statuses:
        raise AppError(
            "TRAINING_SESSION_NOT_ACTIVE",
            "safety events can only be recorded while the session is active or paused",
            status_code=409,
            details={"session_id": session.id, "status": session.status, "control_boundary": "session_safety_event_evidence_only_not_motion_permission"},
        )
    if payload.event_type == "safety_review":
        review_status = str((payload.payload or {}).get("review_status") or "")
        if payload.source not in {"therapist", "app"} or review_status not in {"approved", "conditional"}:
            raise AppError(
                "SAFETY_REVIEW_INVALID",
                "safety review events require therapist/app source and approved or conditional review_status",
                status_code=409,
                details={
                    "session_id": session.id,
                    "allowed_sources": ["therapist", "app"],
                    "allowed_review_status": ["approved", "conditional"],
                    "control_boundary": "session_safety_event_review_required_not_motion_permission",
                },
            )
    event = RehabAppSessionSafetyEvent(
        user_id=user_id,
        session_id=session.id,
        event_type=payload.event_type,
        severity=payload.severity,
        source=payload.source,
        pain_score=payload.pain_score,
        payload=payload.payload,
        note=payload.note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    should_pause = payload.severity == "critical" or (payload.event_type == "pain_report" and payload.pain_score is not None and payload.pain_score >= 7)
    if should_pause and session.status in {"started", "in_progress"}:
        session.status = "paused"
        session.interruption_count += 1
        session.user_note = f"{session.user_note}\nSafety event pause: {payload.event_type} {payload.note}".strip()
        db.add(session)
    db.flush()
    create_audit_log(
        db,
        actor_type="human" if payload.source in {"patient", "therapist", "app"} else payload.source,
        actor_id=user_id,
        action=f"rehab_app.training_session.safety_event.{payload.event_type}",
        resource_type="rehab_app_session_safety_event",
        resource_id=event.id,
        after={
            "session_id": session.id,
            "event_type": payload.event_type,
            "severity": payload.severity,
            "session_status": session.status,
            "control_boundary": "session_safety_event_evidence_only_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(event)
    return _safety_event_dict(event)


def list_session_safety_events(db: Session, user_id: str, session_id: str) -> list[dict]:
    _require_user_session(db, user_id, session_id)
    events = list(
        db.scalars(
            select(RehabAppSessionSafetyEvent)
            .where(RehabAppSessionSafetyEvent.user_id == user_id, RehabAppSessionSafetyEvent.session_id == session_id)
            .order_by(RehabAppSessionSafetyEvent.created_at.asc(), RehabAppSessionSafetyEvent.id.asc())
        )
    )
    return [_safety_event_dict(event) for event in events]


def _session_safety_events(db: Session, user_id: str, session_id: str) -> list[RehabAppSessionSafetyEvent]:
    return list(
        db.scalars(
            select(RehabAppSessionSafetyEvent)
            .where(RehabAppSessionSafetyEvent.user_id == user_id, RehabAppSessionSafetyEvent.session_id == session_id)
            .order_by(RehabAppSessionSafetyEvent.created_at.asc(), RehabAppSessionSafetyEvent.id.asc())
        )
    )


def _session_emg_summaries(db: Session, user_id: str, session_id: str) -> list[RehabAppEmgSummary]:
    return list(
        db.scalars(
            select(RehabAppEmgSummary)
            .where(RehabAppEmgSummary.user_id == user_id, RehabAppEmgSummary.session_id == session_id)
            .order_by(RehabAppEmgSummary.created_at.asc())
        )
    )


def _session_intent_summaries(db: Session, user_id: str, session_id: str) -> list[RehabAppIntentInferenceSummary]:
    return list(
        db.scalars(
            select(RehabAppIntentInferenceSummary)
            .where(RehabAppIntentInferenceSummary.user_id == user_id, RehabAppIntentInferenceSummary.session_id == session_id)
            .order_by(RehabAppIntentInferenceSummary.created_at.asc())
        )
    )


def generate_training_report(db: Session, user_id: str, session_id: str) -> dict:
    session = _require_user_session(db, user_id, session_id)
    if session.status != "finished":
        raise AppError(
            "TRAINING_SESSION_NOT_FINISHED",
            "training report can only be generated after the session is finished",
            status_code=409,
            details={"control_boundary": "training_report_review_only_not_medical_diagnosis_or_motion_permission"},
        )
    existing_report = _session_report(db, user_id, session.id)
    if existing_report is not None:
        return _report_with_review_dict(db, existing_report)
    plan = db.get(RehabAppTrainingPlan, session.plan_id)
    device = db.get(RehabAppDeviceBinding, session.device_id)
    emg_items = _session_emg_summaries(db, user_id, session.id)
    intent_items = _session_intent_summaries(db, user_id, session.id)
    safety_events = _session_safety_events(db, user_id, session.id)
    avg_activation = sum(item.activation_avg for item in emg_items) / len(emg_items) if emg_items else 0.0
    avg_fatigue = sum(item.fatigue_index for item in emg_items) / len(emg_items) if emg_items else 0.0
    avg_confidence = sum(item.confidence for item in intent_items) / len(intent_items) if intent_items else 0.0
    summary = {
        "plan_title": plan.title if plan else "",
        "movement_type": plan.movement_type if plan else "",
        "device_ble_name": device.ble_name if device else "",
        "completion_rate": session.completion_rate,
        "pain_after": session.pain_after,
        "interruption_count": session.interruption_count,
        "user_note": session.user_note,
    }
    emg_overview = {
        "sample_count": len(emg_items),
        "avg_activation": round(avg_activation, 4),
        "avg_fatigue_index": round(avg_fatigue, 4),
        "muscles": sorted({item.muscle_name for item in emg_items}),
        "contact_quality": sorted({item.contact_quality for item in emg_items}),
    }
    intent_overview = {
        "sample_count": len(intent_items),
        "avg_confidence": round(avg_confidence, 4),
        "predicted_actions": sorted({item.predicted_action for item in intent_items if item.predicted_action}),
        "avg_stability_score": round(sum(item.stability_score for item in intent_items) / len(intent_items), 4) if intent_items else 0.0,
    }
    safety_overview = {
        "m33_reject_count": session.m33_reject_count,
        "max_assist_level": session.max_assist_level,
        "event_count": len(safety_events),
        "critical_event_count": sum(1 for event in safety_events if event.severity == "critical"),
        "event_types": sorted({event.event_type for event in safety_events}),
        "max_pain_score": max((event.pain_score for event in safety_events if event.pain_score is not None), default=None),
        "control_boundary": "m33_final_safety_authority",
    }
    recommendations = []
    if safety_overview["critical_event_count"]:
        recommendations.append("critical_safety_event_review_required_before_next_session")
    if session.pain_after is not None and session.pain_after >= 5:
        recommendations.append("pain_after_high_review_with_therapist_before_next_plan")
    if safety_overview["max_pain_score"] is not None and safety_overview["max_pain_score"] >= 7:
        recommendations.append("high_in_session_pain_review_with_therapist")
    if avg_fatigue >= 0.5:
        recommendations.append("fatigue_elevated_reduce_intensity_or_extend_rest")
    if avg_confidence and avg_confidence < 0.7:
        recommendations.append("intent_confidence_low_check_emg_contact_and_calibration")
    if not recommendations:
        recommendations.append("continue_current_plan_with_m33_review_required")
    report = RehabAppTrainingReport(user_id=user_id, session_id=session.id, plan_id=session.plan_id, device_id=session.device_id)
    report.summary = summary
    report.emg_overview = emg_overview
    report.intent_overview = intent_overview
    report.safety_overview = safety_overview
    report.recommendations = recommendations
    db.add(report)
    db.flush()
    create_audit_log(
        db,
        project_id=device.platform_project_id if device else None,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_report.generated",
        resource_type="rehab_app_training_report",
        resource_id=report.id,
        after={"session_id": session.id, "control_boundary": "training_report_review_only_not_medical_diagnosis_or_motion_permission"},
    )
    db.commit()
    db.refresh(report)
    return _report_with_review_dict(db, report)


def get_training_report(db: Session, user_id: str, report_id: str) -> dict:
    report = db.get(RehabAppTrainingReport, report_id)
    if report is None or report.user_id != user_id:
        raise AppError("TRAINING_REPORT_NOT_FOUND", "training report not found", status_code=404)
    return _report_with_review_dict(db, report)


def get_session_training_report(db: Session, user_id: str, session_id: str) -> dict:
    _require_user_session(db, user_id, session_id)
    report = _session_report(db, user_id, session_id)
    if report is None:
        raise AppError("TRAINING_REPORT_NOT_FOUND", "training report not found", status_code=404)
    return _report_with_review_dict(db, report)


def list_training_reports(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    reports = list(
        db.scalars(
            select(RehabAppTrainingReport)
            .where(RehabAppTrainingReport.user_id == user_id)
            .order_by(RehabAppTrainingReport.created_at.desc())
            .limit(limit)
        )
    )
    return [_report_with_review_dict(db, report) for report in reports]


def latest_training_report(db: Session, user_id: str) -> dict | None:
    report = db.scalar(
        select(RehabAppTrainingReport)
        .where(RehabAppTrainingReport.user_id == user_id)
        .order_by(RehabAppTrainingReport.created_at.desc())
        .limit(1)
    )
    return _report_with_review_dict(db, report) if report else None


def create_training_report_review(db: Session, user_id: str, report_id: str, payload: RehabAppTrainingReportReviewCreate) -> dict:
    report = db.get(RehabAppTrainingReport, report_id)
    if report is None or report.user_id != user_id:
        raise AppError("TRAINING_REPORT_NOT_FOUND", "training report not found", status_code=404)
    data = payload.model_dump()
    review = RehabAppTrainingReportReview(user_id=user_id, report_id=report.id, **data)
    db.add(review)
    db.flush()
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.training_report.reviewed",
        resource_type="rehab_app_training_report_review",
        resource_id=review.id,
        after={
            "report_id": report.id,
            "review_status": review.review_status,
            "next_step": review.next_step,
            "request_new_plan": review.request_new_plan,
            "control_boundary": "training_report_review_only_not_medical_diagnosis_or_motion_permission",
        },
    )
    db.commit()
    db.refresh(review)
    return _report_review_dict(review)


def list_training_report_reviews(db: Session, user_id: str, report_id: str, limit: int = 50) -> list[dict]:
    report = db.get(RehabAppTrainingReport, report_id)
    if report is None or report.user_id != user_id:
        raise AppError("TRAINING_REPORT_NOT_FOUND", "training report not found", status_code=404)
    reviews = list(
        db.scalars(
            select(RehabAppTrainingReportReview)
            .where(RehabAppTrainingReportReview.user_id == user_id, RehabAppTrainingReportReview.report_id == report.id)
            .order_by(RehabAppTrainingReportReview.created_at.desc())
            .limit(limit)
        )
    )
    return [_report_review_dict(review) for review in reviews]


def record_emg_summary(db: Session, user_id: str, payload: dict) -> dict:
    session = _require_user_session(db, user_id, str(payload.get("session_id") or ""))
    _require_session_report_open(db, user_id, session)
    summary = RehabAppEmgSummary(user_id=user_id, created_at=datetime.now(timezone.utc), **payload)
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
    session = _require_user_session(db, user_id, str(payload.get("session_id") or ""))
    _require_session_report_open(db, user_id, session)
    summary = RehabAppIntentInferenceSummary(user_id=user_id, created_at=datetime.now(timezone.utc), **payload)
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
    "session_safety_event",
    "plan_constraint_review",
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


def review_failed_offline_item(db: Session, user_id: str, item_id: str, payload: RehabAppOfflineQueueReviewRequest) -> dict:
    item = db.get(RehabAppOfflineQueueItem, item_id)
    if item is None or item.user_id != user_id:
        raise AppError("OFFLINE_QUEUE_ITEM_NOT_FOUND", "offline queue item not found", status_code=404)
    if item.replay_status != "failed":
        raise AppError(
            "OFFLINE_QUEUE_ITEM_NOT_FAILED",
            "only failed offline queue items can be marked reviewed",
            status_code=409,
            details={
                "item_id": item.id,
                "replay_status": item.replay_status,
                "control_boundary": "offline_queue_evidence_only_not_motion_permission",
            },
        )
    previous_result = item.replay_result or {}
    item.replay_status = "reviewed"
    item.replay_result = {
        **previous_result,
        "review": {
            "reviewer_role": payload.reviewer_role,
            "review_status": payload.review_status,
            "note": payload.note,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
        "control_boundary": "offline_queue_evidence_only_not_motion_permission",
    }
    item.replayed_at = datetime.now(timezone.utc)
    db.add(item)
    create_audit_log(
        db,
        actor_type="human",
        actor_id=user_id,
        action="rehab_app.offline_queue.reviewed",
        resource_type="rehab_app_offline_queue_item",
        resource_id=item.id,
        after={
            "operation_type": item.operation_type,
            "review_status": payload.review_status,
            "control_boundary": "offline_queue_evidence_only_not_motion_permission",
        },
    )
    db.commit()
    db.refresh(item)
    return _offline_item_dict(item)


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
            elif item.operation_type == "session_safety_event":
                result = record_session_safety_event(
                    db,
                    user_id,
                    str((item.payload or {}).get("session_id") or ""),
                    RehabAppSessionSafetyEventCreate(**{k: v for k, v in (item.payload or {}).items() if k != "session_id"}),
                )
            elif item.operation_type == "plan_constraint_review":
                result = create_plan_constraint_review(
                    db,
                    user_id,
                    str((item.payload or {}).get("plan_id") or ""),
                    RehabAppPlanConstraintReviewCreate(**{k: v for k, v in (item.payload or {}).items() if k != "plan_id"}),
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


def _draft_plan_from_context(input_text: str, context_snapshot: dict) -> dict:
    return {
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


def _persist_ai_training_draft(db: Session, user_id: str, input_text: str, context_snapshot: dict, generated_plan: dict, risk_notes: list[str]) -> dict:
    draft = RehabAppAiTrainingDraft(
        user_id=user_id,
        input_text=input_text,
        context_snapshot=_json_safe(context_snapshot),
        generated_plan=_json_safe(generated_plan),
        risk_notes=risk_notes,
        created_at=datetime.now(timezone.utc),
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


def generate_ai_training_draft(db: Session, user_id: str, input_text: str, context_snapshot: dict) -> dict:
    generated_plan = _draft_plan_from_context(input_text, context_snapshot)
    risk_notes = ["AI 只生成草稿，不代表执行许可", "必须同步到 M33 并获得 m33_accepted 后才能开始训练记录"]
    return _persist_ai_training_draft(db, user_id, input_text, context_snapshot, generated_plan, risk_notes)


def list_ai_training_drafts(db: Session, user_id: str, status: str = "all", limit: int = 50) -> list[dict]:
    stmt = select(RehabAppAiTrainingDraft).where(RehabAppAiTrainingDraft.user_id == user_id)
    if status == "open":
        stmt = stmt.where(RehabAppAiTrainingDraft.accepted_plan_id == "")
    elif status == "accepted":
        stmt = stmt.where(RehabAppAiTrainingDraft.accepted_plan_id != "")
    elif status != "all":
        raise AppError("AI_TRAINING_DRAFT_STATUS_INVALID", "AI training draft status must be all, open, or accepted", status_code=422)
    drafts = list(db.scalars(stmt.order_by(RehabAppAiTrainingDraft.created_at.desc(), RehabAppAiTrainingDraft.id.desc()).limit(limit)))
    return [_draft_dict(draft) for draft in drafts]


def draft_next_plan_from_report(db: Session, user_id: str, report_id: str) -> dict:
    report = db.get(RehabAppTrainingReport, report_id)
    if report is None or report.user_id != user_id:
        raise AppError("TRAINING_REPORT_NOT_FOUND", "training report not found", status_code=404)
    latest_review = db.scalar(
        select(RehabAppTrainingReportReview)
        .where(RehabAppTrainingReportReview.user_id == user_id, RehabAppTrainingReportReview.report_id == report.id)
        .order_by(RehabAppTrainingReportReview.created_at.desc())
        .limit(1)
    )
    plan = db.get(RehabAppTrainingPlan, report.plan_id)
    summary = report.summary or {}
    emg_overview = report.emg_overview or {}
    intent_overview = report.intent_overview or {}
    review_payload = _report_review_dict(latest_review) if latest_review else {}
    next_step = str(review_payload.get("next_step") or "")
    request_new_plan = bool(review_payload.get("request_new_plan") or False)
    base_sets = int(plan.sets if plan else 2)
    base_reps = int(plan.reps if plan else 6)
    base_assist = float(plan.assist_level if plan else 0.2)
    avg_fatigue = float(emg_overview.get("avg_fatigue_index") or 0)
    pain_after = summary.get("pain_after")
    should_reduce = next_step in {"adjust_plan", "pause_and_consult", "calibration_check"} or request_new_plan
    if pain_after is not None and float(pain_after) >= 5:
        should_reduce = True
    if avg_fatigue >= 0.5:
        should_reduce = True
    generated_plan = {
        "title": "复核后下一次训练草稿",
        "source": "ai_generated",
        "goal": f"Based on report {report.id}: {next_step or 'continue_current_plan'}",
        "movement_type": summary.get("movement_type") or (plan.movement_type if plan else "elbow_flexion"),
        "sets": max(1, base_sets - 1) if should_reduce else base_sets,
        "reps": max(1, base_reps - 1) if should_reduce else base_reps,
        "duration_sec": int(plan.duration_sec if plan else 480),
        "target_joints": plan.target_joints if plan else ["elbow"],
        "assist_level": min(1.0, round(base_assist + 0.05, 3)) if should_reduce else base_assist,
        "speed_level": "slow",
        "target_angle_range": plan.target_angle_range if plan else {"min_deg": 15, "max_deg": 60},
        "emg_policy": plan.emg_policy if plan else {"intent_source": "m55", "assist_when_confidence_above": 0.72},
        "safety_constraints": {
            "require_fresh_m33_heartbeat": True,
            "stop_on_pain_report": True,
            "requires_report_review": True,
            "source_report_id": report.id,
        },
        "status": "draft",
        "control_boundary": "ai_draft_only_not_execution_permission",
    }
    context_snapshot = {
        "source": "training_report_review",
        "report_id": report.id,
        "session_id": report.session_id,
        "summary": summary,
        "emg_overview": emg_overview,
        "intent_overview": intent_overview,
        "latest_review": review_payload,
        "control_boundary": "report_to_ai_draft_only_not_execution_permission",
    }
    input_text = f"Draft next plan from training report {report.id} and latest review. This must remain a draft only."
    risk_notes = [
        "复核后计划仍然只是草稿，不代表执行许可",
        "接受草稿后仍需同步到 M33 并获得当前版本 m33_accepted",
        "如疼痛或疲劳升高，应先由治疗师复核再进入下一次训练",
    ]
    return _persist_ai_training_draft(db, user_id, input_text, context_snapshot, generated_plan, risk_notes)


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
    selected_types = resource_types or [
        "training_plans",
        "training_sessions",
        "training_reports",
        "training_report_reviews",
        "plan_constraint_reviews",
        "session_safety_events",
        "ai_training_drafts",
        "emg_summaries",
        "m33_decisions",
    ]
    summary = {
        "training_plans": len(list_training_plans(db, user_id)) if "training_plans" in selected_types else 0,
        "training_sessions": len(list_training_sessions(db, user_id)) if "training_sessions" in selected_types else 0,
        "training_reports": len(list_training_reports(db, user_id)) if "training_reports" in selected_types else 0,
        "training_report_reviews": len(
            list(db.scalars(select(RehabAppTrainingReportReview).where(RehabAppTrainingReportReview.user_id == user_id)))
        )
        if "training_report_reviews" in selected_types
        else 0,
        "plan_constraint_reviews": len(
            list(db.scalars(select(RehabAppPlanConstraintReview).where(RehabAppPlanConstraintReview.user_id == user_id)))
        )
        if "plan_constraint_reviews" in selected_types
        else 0,
        "session_safety_events": len(
            list(db.scalars(select(RehabAppSessionSafetyEvent).where(RehabAppSessionSafetyEvent.user_id == user_id)))
        )
        if "session_safety_events" in selected_types
        else 0,
        "ai_training_drafts": len(list(db.scalars(select(RehabAppAiTrainingDraft).where(RehabAppAiTrainingDraft.user_id == user_id))))
        if "ai_training_drafts" in selected_types
        else 0,
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
        "synced_resource_types": [
            "training_plans",
            "training_sessions",
            "training_reports",
            "training_report_reviews",
            "plan_constraint_reviews",
            "session_safety_events",
            "ai_training_drafts",
            "emg_summaries",
            "m33_decisions",
        ],
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
