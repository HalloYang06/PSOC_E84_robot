from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_human_principal, resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.session import get_db

from .app_schemas import (
    RehabAppDeviceBindRequest,
    RehabAppEmgSummaryCreate,
    RehabAppIntentSummaryCreate,
    RehabAppProfileUpdate,
    RehabAppTrainingSessionFinishRequest,
    RehabAppTrainingSessionStartRequest,
    RehabAppTrainingPlanCreate,
    RehabAppTrainingPlanSyncRequest,
)
from .app_service import (
    bind_device,
    create_training_plan,
    get_profile,
    latest_emg_summary,
    list_devices,
    list_training_plans,
    finish_training_session,
    record_emg_summary,
    record_intent_summary,
    start_training_session,
    sync_training_plan_to_device,
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


@router.post("/training-plans")
def api_create_training_plan(payload: RehabAppTrainingPlanCreate, request: Request, db: Session = Depends(get_db)):
    return ok(create_training_plan(db, _user_id(db, request), payload))


@router.get("/training-plans")
def api_list_training_plans(request: Request, db: Session = Depends(get_db)):
    return ok(list_training_plans(db, _user_id(db, request)))


@router.post("/training-plans/{plan_id}/sync-to-device")
def api_sync_training_plan(plan_id: str, payload: RehabAppTrainingPlanSyncRequest, request: Request, db: Session = Depends(get_db)):
    return ok(sync_training_plan_to_device(db, _user_id(db, request), plan_id, payload.device_id))


@router.post("/training-sessions/start")
def api_start_training_session(payload: RehabAppTrainingSessionStartRequest, request: Request, db: Session = Depends(get_db)):
    return ok(start_training_session(db, _user_id(db, request), payload.plan_id, payload.device_id))


@router.post("/training-sessions/{session_id}/finish")
def api_finish_training_session(session_id: str, payload: RehabAppTrainingSessionFinishRequest, request: Request, db: Session = Depends(get_db)):
    return ok(finish_training_session(db, _user_id(db, request), session_id, payload.model_dump()))


@router.post("/emg/summary")
def api_record_emg_summary(payload: RehabAppEmgSummaryCreate, request: Request, db: Session = Depends(get_db)):
    return ok(record_emg_summary(db, _user_id(db, request), payload.model_dump()))


@router.get("/emg/latest")
def api_latest_emg_summary(request: Request, db: Session = Depends(get_db)):
    return ok(latest_emg_summary(db, _user_id(db, request)))


@router.post("/intent/summary")
def api_record_intent_summary(payload: RehabAppIntentSummaryCreate, request: Request, db: Session = Depends(get_db)):
    return ok(record_intent_summary(db, _user_id(db, request), payload.model_dump()))
