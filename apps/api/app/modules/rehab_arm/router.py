from __future__ import annotations

from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.common.response import ok

from .schemas import (
    RehabBoardManifestRequest,
    RehabDeviceRegisterRequest,
    RehabManifestUploadRequest,
    RehabMotorStateRequest,
    RehabSafetyStateRequest,
    RehabSensorStateRequest,
    RehabSimulationReadinessRequest,
    RehabSyncStatusRequest,
)
from .service import (
    build_dashboard,
    latest_keyframe_path,
    record_camera_keyframe,
    record_board_manifest,
    record_device_registration,
    record_manifest_upload,
    record_motor_state,
    record_safety_state,
    record_sensor_state,
    record_simulation_readiness,
    record_session_file,
    record_sync_status,
    sha256_bytes,
)


router = APIRouter(prefix="/api/rehab-arm/v1", tags=["rehab-arm"])


def _parse_multipart_body(content_type: str, body: bytes) -> tuple[dict[str, str], bytes]:
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise HTTPException(status_code=415, detail="multipart/form-data boundary is required")
    boundary = match.group(1).strip().strip('"').encode()
    delimiter = b"--" + boundary
    fields: dict[str, str] = {}
    file_bytes = b""
    for part in body.split(delimiter):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_blob, separator, payload = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        payload = payload.removesuffix(b"\r\n").removesuffix(b"--")
        headers = header_blob.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        if name == "file":
            file_bytes = payload
        else:
            fields[name] = payload.decode("utf-8", errors="replace")
    if not file_bytes:
        raise HTTPException(status_code=422, detail="file field is required")
    return fields, file_bytes


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


@router.get("/devices/dashboard")
def api_rehab_arm_dashboard():
    return ok(build_dashboard())


@router.post("/devices/{device_id}/simulation-readiness")
def api_upload_simulation_readiness(device_id: str, payload: RehabSimulationReadinessRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_simulation_readiness(payload.model_dump(mode="json")))


@router.post("/devices/{device_id}/board-manifest")
def api_upload_board_manifest(device_id: str, payload: RehabBoardManifestRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    manifest = payload.manifest
    if manifest.get("schema_version") != "linux_board_manifest_v1":
        raise HTTPException(status_code=422, detail="manifest.schema_version must be linux_board_manifest_v1")
    return ok(record_board_manifest(payload.model_dump(mode="json")))


@router.post("/devices/{device_id}/camera/keyframes")
async def api_upload_camera_keyframe(device_id: str, request: Request):
    """Accept low-frequency camera keyframes as non-realtime data assets."""
    fields, body = _parse_multipart_body(request.headers.get("content-type", ""), await request.body())
    robot_id = fields.get("robot_id", "")
    camera_id = fields.get("camera_id", "")
    image_format = fields.get("image_format", "")
    try:
        frame_ts_unix = float(fields.get("frame_ts_unix") or 0)
        width = int(fields.get("width") or 0)
        height = int(fields.get("height") or 0)
    except ValueError:
        raise HTTPException(status_code=422, detail="frame_ts_unix, width, and height must be numeric") from None
    sha256 = fields.get("sha256", "")
    detection_summary = fields.get("detection_summary", "")
    scene_summary = fields.get("scene_summary", "")
    vla_context = fields.get("vla_context", "")
    if not robot_id or not camera_id or not frame_ts_unix or width <= 0 or height <= 0:
        raise HTTPException(status_code=422, detail="robot_id, camera_id, frame_ts_unix, width, and height are required")
    normalized_format = image_format.strip().lower()
    if normalized_format not in {"jpg", "jpeg", "png", "webp"}:
        raise HTTPException(status_code=422, detail="image_format must be jpg, png, or webp")
    digest = sha256_bytes(body)
    if sha256 and digest.lower() != sha256.strip().lower():
        raise HTTPException(status_code=422, detail="sha256 does not match uploaded keyframe")
    return ok(
        record_camera_keyframe(
            {
                "robot_id": robot_id,
                "device_id": device_id,
                "camera_id": camera_id,
                "frame_ts_unix": frame_ts_unix,
                "image_format": "jpg" if normalized_format == "jpeg" else normalized_format,
                "width": width,
                "height": height,
                "sha256": digest,
                "detection_summary": detection_summary,
                "scene_summary": scene_summary,
                "vla_context": vla_context,
            },
            body,
        )
    )


@router.get("/devices/{device_id}/camera/keyframes/latest/file")
def api_latest_camera_keyframe_file(device_id: str):
    path = latest_keyframe_path(device_id)
    if path is None:
        raise HTTPException(status_code=404, detail="latest keyframe not found")
    suffix = Path(path).suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/devices/{device_id}/motor-state")
def api_upload_motor_state(device_id: str, payload: RehabMotorStateRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_motor_state(payload.model_dump(mode="json")))


@router.post("/devices/{device_id}/sensor-state")
def api_upload_sensor_state(device_id: str, payload: RehabSensorStateRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_sensor_state(payload.model_dump(mode="json")))


@router.post("/devices/{device_id}/safety-state")
def api_upload_safety_state(device_id: str, payload: RehabSafetyStateRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_safety_state(payload.model_dump(mode="json")))
