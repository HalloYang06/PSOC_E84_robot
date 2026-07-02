from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.session import get_db

from .app_schemas import (
    RehabAppDeviceBindRequest,
    RehabAppDeviceUnbindRequest,
    RehabAppAiTrainingDraftGenerateRequest,
    RehabAppBleAckCreate,
    RehabAppBleMessageCreate,
    RehabAppDiagnosticUploadRequest,
    RehabAppEmgSummaryCreate,
    RehabAppIntentSummaryCreate,
    RehabAppM33StatusUpdate,
    RehabAppOfflineQueueItemCreate,
    RehabAppOfflineQueueReplayRequest,
    RehabAppPlatformSyncRequest,
    RehabAppPreflightCheckCreate,
    RehabAppProfileUpdate,
    RehabAppTrainingReportReviewCreate,
    RehabAppTrainingSessionCancelRequest,
    RehabAppTrainingSessionFinishRequest,
    RehabAppTrainingSessionPauseRequest,
    RehabAppTrainingSessionProgressRequest,
    RehabAppTrainingSessionResumeRequest,
    RehabAppTrainingSessionStartRequest,
    RehabAppTrainingPlanCreate,
    RehabAppTrainingPlanSyncRequest,
    RehabAppTrainingPlanUpdate,
)
from .app_service import (
    accept_ai_training_draft,
    archive_training_plan,
    bind_device,
    cancel_training_session,
    create_ble_message,
    create_preflight_check,
    create_training_report_review,
    create_training_plan,
    draft_next_plan_from_report,
    emg_history,
    generate_ai_training_draft,
    generate_training_report,
    get_ai_training_draft,
    get_app_bootstrap,
    get_device_status,
    list_device_diagnostics,
    list_ble_messages,
    list_offline_queue,
    list_platform_sync_runs,
    list_safety_audit_logs,
    get_platform_sync_status,
    get_profile,
    get_session_training_report,
    get_training_plan,
    get_training_report,
    get_training_session,
    latest_emg_summary,
    list_ai_training_drafts,
    list_devices,
    list_training_reports,
    list_training_report_reviews,
    list_training_sessions,
    list_training_plans,
    finish_training_session,
    pause_training_session,
    record_emg_summary,
    record_intent_summary,
    replay_offline_queue,
    resume_training_session,
    start_training_session,
    sync_platform_records,
    sync_training_plan_to_device,
    unbind_device,
    update_ble_message_ack,
    update_m33_sync_status,
    update_training_plan,
    update_training_session_progress,
    enqueue_offline_item,
    upload_device_diagnostic,
    upsert_profile,
)


router = APIRouter(prefix="/api/rehab-arm/app/v1", tags=["rehab-arm-app"])


def _user_id(db: Session, request: Request) -> str:
    principal = resolve_human_principal(db, request, allow_bootstrap=False)
    if not principal.user_id:
        raise AppError("UNAUTHORIZED", "authentication required", status_code=401)
    return principal.user_id


@router.get("/me/profile")
def api_get_profile(request: Request, db: Session = Depends(get_db)):
    profile = get_profile(db, _user_id(db, request))
    return ok(profile)


@router.get("/me")
def api_get_me(request: Request, db: Session = Depends(get_db)):
    return ok(get_app_bootstrap(db, _user_id(db, request)))


@router.patch("/me/profile")
def api_update_profile(payload: RehabAppProfileUpdate, request: Request, db: Session = Depends(get_db)):
    return ok(upsert_profile(db, _user_id(db, request), payload))


@router.post("/devices/bind")
def api_bind_device(payload: RehabAppDeviceBindRequest, request: Request, db: Session = Depends(get_db)):
    user_id = _user_id(db, request)
    if payload.platform_project_id:
        resolve_project_write_principal(db, request, payload.platform_project_id, action="rehab_app.device.bind")
    return ok(bind_device(db, user_id, payload))


@router.get("/devices")
def api_list_devices(request: Request, db: Session = Depends(get_db)):
    return ok(list_devices(db, _user_id(db, request)))


@router.get("/devices/{device_id}/status")
def api_get_device_status(device_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_device_status(db, _user_id(db, request), device_id))


@router.post("/devices/{device_id}/unbind")
def api_unbind_device(device_id: str, payload: RehabAppDeviceUnbindRequest, request: Request, db: Session = Depends(get_db)):
    return ok(unbind_device(db, _user_id(db, request), device_id, payload.reason))


@router.post("/devices/{device_id}/m33-status")
def api_update_m33_status(device_id: str, payload: RehabAppM33StatusUpdate, request: Request, db: Session = Depends(get_db)):
    return ok(update_m33_sync_status(db, _user_id(db, request), device_id, payload.sync_id, payload.sync_status, payload.m33_reason, payload.firmware_version))


@router.post("/devices/{device_id}/diagnostic-upload")
def api_upload_device_diagnostic(device_id: str, payload: RehabAppDiagnosticUploadRequest, request: Request, db: Session = Depends(get_db)):
    return ok(upload_device_diagnostic(db, _user_id(db, request), device_id, payload))


@router.get("/devices/{device_id}/diagnostics")
def api_list_device_diagnostics(device_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(list_device_diagnostics(db, _user_id(db, request), device_id))


@router.post("/devices/{device_id}/ble/messages")
def api_create_ble_message(device_id: str, payload: RehabAppBleMessageCreate, request: Request, db: Session = Depends(get_db)):
    return ok(create_ble_message(db, _user_id(db, request), device_id, payload))


@router.get("/devices/{device_id}/ble/messages")
def api_list_ble_messages(device_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(list_ble_messages(db, _user_id(db, request), device_id))


@router.post("/devices/{device_id}/ble/messages/{message_id}/ack")
def api_ack_ble_message(device_id: str, message_id: str, payload: RehabAppBleAckCreate, request: Request, db: Session = Depends(get_db)):
    return ok(update_ble_message_ack(db, _user_id(db, request), device_id, message_id, payload.ack_status, payload.ack_payload))


@router.post("/training-plans")
def api_create_training_plan(payload: RehabAppTrainingPlanCreate, request: Request, db: Session = Depends(get_db)):
    return ok(create_training_plan(db, _user_id(db, request), payload))


@router.get("/training-plans")
def api_list_training_plans(request: Request, db: Session = Depends(get_db)):
    return ok(list_training_plans(db, _user_id(db, request)))


@router.get("/training-plans/{plan_id}")
def api_get_training_plan(plan_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_training_plan(db, _user_id(db, request), plan_id))


@router.patch("/training-plans/{plan_id}")
def api_update_training_plan(plan_id: str, payload: RehabAppTrainingPlanUpdate, request: Request, db: Session = Depends(get_db)):
    return ok(update_training_plan(db, _user_id(db, request), plan_id, payload))


@router.post("/training-plans/{plan_id}/archive")
def api_archive_training_plan(plan_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(archive_training_plan(db, _user_id(db, request), plan_id))


@router.post("/training-plans/{plan_id}/sync-to-device")
def api_sync_training_plan(plan_id: str, payload: RehabAppTrainingPlanSyncRequest, request: Request, db: Session = Depends(get_db)):
    return ok(sync_training_plan_to_device(db, _user_id(db, request), plan_id, payload.device_id))


@router.post("/training-preflight")
def api_create_training_preflight(payload: RehabAppPreflightCheckCreate, request: Request, db: Session = Depends(get_db)):
    return ok(create_preflight_check(db, _user_id(db, request), payload))


@router.post("/training-sessions/start")
def api_start_training_session(payload: RehabAppTrainingSessionStartRequest, request: Request, db: Session = Depends(get_db)):
    return ok(start_training_session(db, _user_id(db, request), payload.plan_id, payload.device_id))


@router.get("/training-sessions")
def api_list_training_sessions(request: Request, db: Session = Depends(get_db)):
    return ok(list_training_sessions(db, _user_id(db, request)))


@router.get("/training-sessions/{session_id}")
def api_get_training_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_training_session(db, _user_id(db, request), session_id))


@router.patch("/training-sessions/{session_id}/progress")
def api_update_training_session_progress(session_id: str, payload: RehabAppTrainingSessionProgressRequest, request: Request, db: Session = Depends(get_db)):
    return ok(update_training_session_progress(db, _user_id(db, request), session_id, payload.model_dump(exclude_unset=True)))


@router.post("/training-sessions/{session_id}/finish")
def api_finish_training_session(session_id: str, payload: RehabAppTrainingSessionFinishRequest, request: Request, db: Session = Depends(get_db)):
    return ok(finish_training_session(db, _user_id(db, request), session_id, payload.model_dump()))


@router.post("/training-sessions/{session_id}/pause")
def api_pause_training_session(session_id: str, payload: RehabAppTrainingSessionPauseRequest, request: Request, db: Session = Depends(get_db)):
    return ok(pause_training_session(db, _user_id(db, request), session_id, payload.reason))


@router.post("/training-sessions/{session_id}/resume")
def api_resume_training_session(session_id: str, payload: RehabAppTrainingSessionResumeRequest, request: Request, db: Session = Depends(get_db)):
    return ok(resume_training_session(db, _user_id(db, request), session_id, payload.note))


@router.post("/training-sessions/{session_id}/cancel")
def api_cancel_training_session(session_id: str, payload: RehabAppTrainingSessionCancelRequest, request: Request, db: Session = Depends(get_db)):
    return ok(cancel_training_session(db, _user_id(db, request), session_id, payload.reason))


@router.post("/training-sessions/{session_id}/report")
def api_generate_training_report(session_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(generate_training_report(db, _user_id(db, request), session_id))


@router.get("/training-sessions/{session_id}/report")
def api_get_session_training_report(session_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_session_training_report(db, _user_id(db, request), session_id))


@router.get("/training-reports")
def api_list_training_reports(request: Request, db: Session = Depends(get_db)):
    return ok(list_training_reports(db, _user_id(db, request)))


@router.get("/training-reports/{report_id}")
def api_get_training_report(report_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_training_report(db, _user_id(db, request), report_id))


@router.post("/training-reports/{report_id}/reviews")
def api_create_training_report_review(report_id: str, payload: RehabAppTrainingReportReviewCreate, request: Request, db: Session = Depends(get_db)):
    return ok(create_training_report_review(db, _user_id(db, request), report_id, payload))


@router.get("/training-reports/{report_id}/reviews")
def api_list_training_report_reviews(report_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(list_training_report_reviews(db, _user_id(db, request), report_id))


@router.post("/training-reports/{report_id}/draft-next-plan")
def api_draft_next_plan_from_report(report_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(draft_next_plan_from_report(db, _user_id(db, request), report_id))


@router.post("/emg/summary")
def api_record_emg_summary(payload: RehabAppEmgSummaryCreate, request: Request, db: Session = Depends(get_db)):
    return ok(record_emg_summary(db, _user_id(db, request), payload.model_dump()))


@router.get("/emg/latest")
def api_latest_emg_summary(request: Request, db: Session = Depends(get_db)):
    return ok(latest_emg_summary(db, _user_id(db, request)))


@router.get("/emg/history")
def api_emg_history(request: Request, db: Session = Depends(get_db)):
    return ok(emg_history(db, _user_id(db, request)))


@router.post("/intent/summary")
def api_record_intent_summary(payload: RehabAppIntentSummaryCreate, request: Request, db: Session = Depends(get_db)):
    return ok(record_intent_summary(db, _user_id(db, request), payload.model_dump()))


@router.post("/ai-training-drafts/generate")
def api_generate_ai_training_draft(payload: RehabAppAiTrainingDraftGenerateRequest, request: Request, db: Session = Depends(get_db)):
    return ok(generate_ai_training_draft(db, _user_id(db, request), payload.input_text, payload.context_snapshot))


@router.get("/ai-training-drafts")
def api_list_ai_training_drafts(request: Request, status: str = "all", db: Session = Depends(get_db)):
    return ok(list_ai_training_drafts(db, _user_id(db, request), status=status))


@router.get("/ai-training-drafts/{draft_id}")
def api_get_ai_training_draft(draft_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(get_ai_training_draft(db, _user_id(db, request), draft_id))


@router.post("/ai-training-drafts/{draft_id}/accept")
def api_accept_ai_training_draft(draft_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(accept_ai_training_draft(db, _user_id(db, request), draft_id))


@router.post("/platform/sync")
def api_platform_sync(payload: RehabAppPlatformSyncRequest, request: Request, db: Session = Depends(get_db)):
    return ok(sync_platform_records(db, _user_id(db, request), payload.resource_types))


@router.get("/platform/sync-status")
def api_platform_sync_status(request: Request, db: Session = Depends(get_db)):
    return ok(get_platform_sync_status(db, _user_id(db, request)))


@router.get("/platform/sync-runs")
def api_platform_sync_runs(request: Request, db: Session = Depends(get_db)):
    return ok(list_platform_sync_runs(db, _user_id(db, request)))


@router.post("/offline-queue")
def api_enqueue_offline_item(payload: RehabAppOfflineQueueItemCreate, request: Request, db: Session = Depends(get_db)):
    return ok(enqueue_offline_item(db, _user_id(db, request), payload))


@router.get("/offline-queue")
def api_list_offline_queue(request: Request, db: Session = Depends(get_db)):
    return ok(list_offline_queue(db, _user_id(db, request)))


@router.post("/offline-queue/replay")
def api_replay_offline_queue(payload: RehabAppOfflineQueueReplayRequest, request: Request, db: Session = Depends(get_db)):
    return ok(replay_offline_queue(db, _user_id(db, request), payload.item_ids))


@router.get("/safety-audit")
def api_safety_audit(request: Request, db: Session = Depends(get_db)):
    return ok(list_safety_audit_logs(db, _user_id(db, request)))
