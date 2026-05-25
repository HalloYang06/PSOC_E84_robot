from __future__ import annotations

from fastapi import APIRouter, Request

from app.common.response import ok

from .schemas import RehabDeviceRegisterRequest, RehabManifestUploadRequest, RehabSyncStatusRequest
from .service import (
    record_device_registration,
    record_manifest_upload,
    record_session_file,
    record_sync_status,
)


router = APIRouter(prefix="/api/rehab-arm/v1", tags=["rehab-arm"])


@router.post("/devices/register")
def api_register_device(payload: RehabDeviceRegisterRequest):
    return ok(record_device_registration(payload.model_dump(mode="json")))


@router.post("/sessions/manifest")
def api_upload_manifest(payload: RehabManifestUploadRequest):
    return ok(record_manifest_upload(payload.model_dump(mode="json")))


@router.post("/sessions/{session_id}/files")
async def api_upload_session_file(session_id: str, request: Request):
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    return ok(record_session_file(session_id, content_type, body))


@router.post("/sessions/{session_id}/sync-status")
def api_report_sync_status(session_id: str, payload: RehabSyncStatusRequest):
    return ok(record_sync_status(session_id, payload.model_dump(mode="json")))
