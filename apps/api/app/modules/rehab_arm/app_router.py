from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.session import get_db

from .app_schemas import (
    RehabAppDeviceBindRequest,
    RehabAppAiTrainingDraftGenerateRequest,
    RehabAppDiagnosticUploadRequest,
    RehabAppEmgSummaryCreate,
    RehabAppIntentSummaryCreate,
    RehabAppM33StatusUpdate,
    RehabAppOfflineQueueItemCreate,
    RehabAppOfflineQueueReplayRequest,
    RehabAppPlatformSyncRequest,
    RehabAppProfileUpdate,
    RehabAppTrainingSessionFinishRequest,
    RehabAppTrainingSessionProgressRequest,
    RehabAppTrainingSessionStartRequest,
    RehabAppTrainingPlanCreate,
    RehabAppTrainingPlanSyncRequest,
    RehabAppTrainingPlanUpdate,
)
from .app_service import (
    accept_ai_training_draft,
    archive_training_plan,
    bind_device,
    create_training_plan,
    emg_history,
    generate_ai_training_draft,
    get_ai_training_draft,
    get_app_bootstrap,
    get_device_status,
    list_device_diagnostics,
    list_offline_queue,
    list_platform_sync_runs,
    list_safety_audit_logs,
    get_platform_sync_status,
    get_profile,
    get_training_plan,
    get_training_session,
    latest_emg_summary,
    list_devices,
    list_training_sessions,
    list_training_plans,
    finish_training_session,
    record_emg_summary,
    record_intent_summary,
    replay_offline_queue,
    start_training_session,
    sync_platform_records,
    sync_training_plan_to_device,
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


@router.post("/devices/{device_id}/m33-status")
def api_update_m33_status(device_id: str, payload: RehabAppM33StatusUpdate, request: Request, db: Session = Depends(get_db)):
    return ok(update_m33_sync_status(db, _user_id(db, request), device_id, payload.sync_id, payload.sync_status, payload.m33_reason, payload.firmware_version))


@router.post("/devices/{device_id}/diagnostic-upload")
def api_upload_device_diagnostic(device_id: str, payload: RehabAppDiagnosticUploadRequest, request: Request, db: Session = Depends(get_db)):
    return ok(upload_device_diagnostic(db, _user_id(db, request), device_id, payload))


@router.get("/devices/{device_id}/diagnostics")
def api_list_device_diagnostics(device_id: str, request: Request, db: Session = Depends(get_db)):
    return ok(list_device_diagnostics(db, _user_id(db, request), device_id))


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
