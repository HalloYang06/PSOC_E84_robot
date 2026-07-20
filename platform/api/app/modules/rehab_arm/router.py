from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access
from app.settings import get_settings

from .schemas import (
    RehabCameraStreamOfferRequest,
    RehabCommandCenterSnapshotRequest,
    RehabBoardManifestRequest,
    RehabDeviceRegisterRequest,
    RehabEstopRequest,
    RehabIkCandidateRequest,
    RehabModelRelayConfigRequest,
    RehabManifestUploadRequest,
    RehabModelRelayRequest,
    RehabModelRelayTokenRequest,
    RehabMotorStateRequest,
    RehabSafetyStateRequest,
    RehabSensorStateRequest,
    RehabSimulationReadinessRequest,
    RehabStereoVisionContextRequest,
    RehabSyncStatusRequest,
    RehabVlaTaskRequest,
)
from .service import (
    build_dashboard,
    build_camera_stream_offer,
    build_command_center_snapshot,
    build_safety_status,
    build_wiring_health,
    latest_keyframe_path,
    latest_ik_candidate,
    latest_model_package_path,
    issue_model_relay_token,
    model_relay_config_status,
    record_command_center_snapshot,
    record_camera_keyframe,
    record_camera_stream_offer,
    record_board_manifest,
    record_device_model_package,
    record_device_registration,
    record_estop_request,
    record_ik_candidate_request,
    record_manifest_upload,
    record_model_relay_request,
    record_motor_state,
    record_safety_state,
    record_sensor_state,
    record_simulation_readiness,
    record_session_file,
    record_stereo_vision_context,
    record_sync_status,
    record_vla_task_request,
    record_voice_capture,
    record_xiaozhi_ws_event,
    parse_xiaozhi_audio_frame,
    pcm_duration_ms,
    require_device_project_match,
    sha256_bytes,
    synthesize_xiaozhi_tts,
    transcribe_xiaozhi_audio,
    update_model_relay_config,
    verify_model_relay_token,
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


def _int_field(fields: dict[str, str], name: str) -> int:
    try:
        return int(fields.get(name) or 0)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be numeric") from None


async def _model_relay_payload_from_request(request: Request, device_id: str, project_id: str = "") -> RehabModelRelayRequest:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        fields, audio_bytes = _parse_multipart_body(request.headers.get("content-type", ""), await request.body())
        metadata_raw = fields.get("metadata") or "{}"
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="metadata must be valid JSON") from exc
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=422, detail="metadata must be a JSON object")
        audio_ref = {
            "schema_version": "voice_audio_ref_v1",
            "sha256": sha256_bytes(audio_bytes),
            "byte_length": len(audio_bytes),
            "content_type": request.headers.get("content-type", ""),
            "audio_format": metadata.get("audio_format") or metadata.get("format") or "",
            "control_boundary": "voice_audio_asset_only_not_motion_permission",
        }
        context_refs = metadata.get("context_refs") if isinstance(metadata.get("context_refs"), dict) else {}
        payload = {
            **metadata,
            "schema_version": "model_relay_request_v1",
            "robot_id": metadata.get("robot_id") or fields.get("robot_id") or "",
            "device_id": metadata.get("device_id") or device_id,
            "project_id": project_id or metadata.get("project_id") or fields.get("project_id") or "",
            "input_type": metadata.get("input_type") or "vla_language_from_voice",
            "prompt": metadata.get("prompt") or metadata.get("transcript") or fields.get("prompt") or fields.get("transcript") or "[voice audio uploaded]",
            "context_refs": {**context_refs, "audio_ref": audio_ref},
            "control_boundary": "model_relay_request_only_not_motion_permission",
        }
        try:
            return RehabModelRelayRequest.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="request body must be JSON or multipart/form-data") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="request body must be a JSON object")
    try:
        return RehabModelRelayRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _event_payload(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, default=str)


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _require_project_or_relay_token(
    db: Session,
    request: Request,
    project_id: str,
    device_id: str,
    required_scope: str = "rehab_arm.model_relay.invoke",
) -> None:
    try:
        require_project_read_access(db, request, project_id, action="rehab_arm.model_relay")
        return
    except AppError as human_error:
        token = _bearer_token(request)
        if token and verify_model_relay_token(token, project_id, device_id, required_scope=required_scope):
            return
        raise human_error


def _websocket_bearer_token(websocket: WebSocket) -> str:
    auth = websocket.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = websocket.query_params.get("token") or ""
    return str(token).strip()


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
def api_rehab_arm_dashboard(project_id: str | None = Query(default=None)):
    return ok(build_dashboard(project_id=project_id))


@router.get("/devices/{device_id}/command-center/snapshot")
def api_get_command_center_snapshot(device_id: str, project_id: str | None = Query(default=None)):
    return ok(build_command_center_snapshot(device_id, project_id=project_id))


@router.websocket("/devices/{device_id}/events")
async def api_device_events(websocket: WebSocket, device_id: str, project_id: str | None = Query(default=None)):
    """Stream readonly command-center events for UI display.

    The protocol explicitly keeps WebSocket display separate from M33-local
    safety. This endpoint sends telemetry snapshots and ignores all control
    payloads from clients.
    """
    await websocket.accept()
    await websocket.send_text(
        _event_payload(
            {
                "type": "hello",
                "schema_version": "rehab_arm_device_events_v1",
                "device_id": device_id,
                "project_id": project_id or "",
                "control_boundary": "telemetry_stream_only_not_motion_permission",
            }
        )
    )
    await websocket.send_text(
        _event_payload(
            {
                "type": "command_center_snapshot_v1",
                "device_id": device_id,
                "data": build_command_center_snapshot(device_id, project_id=project_id),
                "control_boundary": "telemetry_snapshot_only_not_motion_permission",
            }
        )
    )

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_text(_event_payload({"type": "ping", "control_boundary": "telemetry_stream_only_not_motion_permission"}))
        except Exception:
            return

    heartbeat = asyncio.create_task(_heartbeat())
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_text(
                _event_payload(
                    {
                        "type": "ignored_client_payload",
                        "device_id": device_id,
                        "detail": "rehab-arm device events websocket is readonly",
                        "control_boundary": "telemetry_stream_only_not_motion_permission",
                    }
                )
            )
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()


@router.post("/devices/{device_id}/command-center/snapshot")
def api_upload_command_center_snapshot(device_id: str, payload: RehabCommandCenterSnapshotRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    try:
        return ok(record_command_center_snapshot(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    project_id = fields.get("project_id", "") or fields.get("projectId", "")
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
                "project_id": project_id,
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


@router.get("/devices/{device_id}/camera/keyframes/{camera_id}/latest/file")
def api_latest_camera_keyframe_file_by_camera(device_id: str, camera_id: str):
    path = latest_keyframe_path(device_id, camera_id)
    if path is None:
        raise HTTPException(status_code=404, detail="latest keyframe not found for camera")
    suffix = Path(path).suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.get("/devices/{device_id}/camera/stream-offer")
def api_get_camera_stream_offer(device_id: str):
    return ok(build_camera_stream_offer(device_id))


@router.post("/devices/{device_id}/camera/stream-offer")
def api_upload_camera_stream_offer(device_id: str, payload: RehabCameraStreamOfferRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_camera_stream_offer(payload.model_dump(mode="json")))


@router.post("/devices/{device_id}/vision/stereo-context")
def api_upload_stereo_vision_context(device_id: str, payload: RehabStereoVisionContextRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    try:
        return ok(record_stereo_vision_context(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/devices/{device_id}/ik-candidate")
def api_create_ik_candidate(device_id: str, payload: RehabIkCandidateRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    try:
        return ok(record_ik_candidate_request(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/devices/{device_id}/ik-candidate/latest")
def api_latest_ik_candidate(device_id: str):
    return ok(latest_ik_candidate(device_id))


@router.post("/devices/{device_id}/model-package")
async def api_upload_device_model_package(device_id: str, request: Request):
    """Accept a URDF zip/package as a project device model profile for readonly preview."""
    fields, body = _parse_multipart_body(request.headers.get("content-type", ""), await request.body())
    robot_id = fields.get("robot_id", "")
    project_id = fields.get("project_id", "") or fields.get("projectId", "")
    file_name = fields.get("file_name", "robot_model.zip")
    if not robot_id or not project_id:
        raise HTTPException(status_code=422, detail="robot_id and project_id are required")
    normalized_name = Path(file_name).name
    if not normalized_name.lower().endswith((".zip", ".urdf", ".xml")):
        raise HTTPException(status_code=422, detail="model package must be zip, urdf, or xml")
    if len(body) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="model package must be 12MB or smaller")
    return ok(
        record_device_model_package(
            {
                "robot_id": robot_id,
                "device_id": device_id,
                "project_id": project_id,
                "file_name": normalized_name,
                "package_name": fields.get("package_name", ""),
                "urdf_path": fields.get("urdf_path", ""),
                "joint_count": _int_field(fields, "joint_count"),
                "mesh_count": _int_field(fields, "mesh_count"),
                "mapping_json": fields.get("mapping_json", "[]"),
            },
            normalized_name,
            body,
        )
    )


@router.get("/devices/{device_id}/model-package/latest/file")
def api_latest_device_model_package_file(device_id: str):
    path = latest_model_package_path(device_id)
    if path is None:
        raise HTTPException(status_code=404, detail="latest model package not found")
    suffix = Path(path).suffix.lower()
    media_type = "application/zip" if suffix == ".zip" else "application/xml"
    return FileResponse(path, media_type=media_type, filename=Path(path).name)


@router.post("/devices/{device_id}/voice/captures")
async def api_upload_voice_capture(device_id: str, request: Request):
    """Accept voice_capture_v1 and relay it as model-state-compatible suggestion only."""
    fields, body = _parse_multipart_body(request.headers.get("content-type", ""), await request.body())
    robot_id = fields.get("robot_id", "")
    if not robot_id:
        raise HTTPException(status_code=422, detail="robot_id is required")
    return ok(record_voice_capture(device_id, fields, body))


@router.post("/devices/{device_id}/vla/task-requests")
def api_vla_task_request(device_id: str, payload: RehabVlaTaskRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    try:
        return ok(record_vla_task_request(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/projects/{project_id}/devices/{device_id}/vla/task-requests")
def api_project_vla_task_request(
    project_id: str,
    device_id: str,
    payload: RehabVlaTaskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_project_or_relay_token(db, request, project_id, device_id, required_scope="rehab_arm.vla_task.invoke")
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    request_payload = payload.model_dump(mode="json")
    if request_payload.get("project_id") and request_payload["project_id"] != project_id:
        raise HTTPException(status_code=422, detail="payload.project_id must match path project_id")
    request_payload["project_id"] = project_id
    try:
        require_device_project_match(device_id, project_id)
        return ok(record_vla_task_request(request_payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/devices/{device_id}/model/relay")
async def api_model_relay(device_id: str, request: Request):
    payload = await _model_relay_payload_from_request(request, device_id)
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    try:
        return ok(record_model_relay_request(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/projects/{project_id}/devices/{device_id}/model/relay")
async def api_project_model_relay(
    project_id: str,
    device_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_project_or_relay_token(db, request, project_id, device_id)
    payload = await _model_relay_payload_from_request(request, device_id, project_id=project_id)
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    request_payload = payload.model_dump(mode="json")
    if request_payload.get("project_id") and request_payload["project_id"] != project_id:
        raise HTTPException(status_code=422, detail="payload.project_id must match path project_id")
    request_payload["project_id"] = project_id
    try:
        require_device_project_match(device_id, project_id)
        return ok(record_model_relay_request(request_payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.websocket("/projects/{project_id}/devices/{device_id}/xiaozhi/ws")
async def api_project_xiaozhi_websocket(websocket: WebSocket, project_id: str, device_id: str):
    """XiaoZhi-compatible voice WebSocket for M55.

    This endpoint is intentionally scoped to the existing rehab-arm model relay
    token. It accepts voice frames and returns language/VLA suggestions only.
    """
    token = _websocket_bearer_token(websocket)
    if not token or not verify_model_relay_token(token, project_id, device_id, required_scope="rehab_arm.xiaozhi.websocket"):
        await websocket.close(code=1008)
        return
    try:
        require_device_project_match(device_id, project_id)
    except ValueError:
        await websocket.close(code=1008)
        return

    robot_id = websocket.query_params.get("robot_id") or "rehab-arm-alpha"
    await websocket.accept()
    settings = get_settings()
    session_id = ""
    protocol_header = websocket.headers.get("protocol-version", "").strip()
    try:
        protocol_version = int(protocol_header or settings.rehab_arm_xiaozhi_default_protocol_version or 1)
    except ValueError:
        protocol_version = 1
    device_header = websocket.headers.get("device-id", "").strip()
    client_header = websocket.headers.get("client-id", "").strip()
    default_audio_format = (settings.rehab_arm_xiaozhi_default_audio_format or "pcm_s16le").strip().lower()
    if default_audio_format not in {"pcm_s16le", "opus"}:
        default_audio_format = "pcm_s16le"
    audio_params: dict = {"format": default_audio_format, "sample_rate": 16000, "channels": 1, "frame_duration": 60}
    if default_audio_format == "pcm_s16le":
        audio_params["bits_per_sample"] = 16
    audio_chunks: list[bytes] = []
    audio_frame_count = 0
    transcript_hint = ""

    def base_payload(record_type: str, payload: dict) -> dict:
        return {
            "record_type": record_type,
            "schema_version": "xiaozhi_session_v1",
            "robot_id": robot_id,
            "device_id": device_id,
            "project_id": project_id,
            "session_id": session_id,
            **payload,
            "control_boundary": "xiaozhi_voice_relay_only_not_motion_permission",
        }

    async def finish_xiaozhi_turn(stop_event: dict, disconnected: bool = False) -> None:
        nonlocal session_id, audio_chunks, audio_frame_count, transcript_hint

        session_id = str(stop_event.get("session_id") or session_id or f"xiaozhi_{device_id}")
        transcript = str(stop_event.get("text") or stop_event.get("transcript") or transcript_hint or "")
        audio_bytes = sum(len(item) for item in audio_chunks)
        audio_blob = b"".join(audio_chunks)
        duration_ms = pcm_duration_ms(audio_bytes, audio_params)
        asr_result: dict = {"ok": bool(transcript), "called": False, "text": transcript, "error": ""}
        if not transcript and audio_blob:
            asr_result = transcribe_xiaozhi_audio(audio_blob, audio_params, audio_chunks)
            transcript = str(asr_result.get("text") or "")
        record_xiaozhi_ws_event(
            base_payload(
                "xiaozhi_ws_input",
                {
                    "event": "listen_stop",
                    "protocol_version": protocol_version,
                    "audio_params": audio_params,
                    "audio_frame_count": audio_frame_count,
                    "audio_bytes": audio_bytes,
                    "audio_duration_ms": duration_ms,
                    "asr_called": bool(asr_result.get("called")),
                    "asr_ok": bool(asr_result.get("ok")),
                    "asr_text": transcript,
                    "asr_error": str(asr_result.get("error") or ""),
                    "asr_audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                    "asr_audio_prep": asr_result.get("asr_audio_prep") or {},
                    "prepared_audio_bytes": int(asr_result.get("prepared_audio_bytes") or 0),
                    "official_audio_path": bool(asr_result.get("official_audio_path") or str(audio_params.get("format") or "").lower() == "opus"),
                    "compatibility_mode": asr_result.get("compatibility_mode") or "",
                    "disconnected": disconnected,
                },
            )
        )
        if disconnected:
            audio_chunks = []
            audio_frame_count = 0
            transcript_hint = ""
            return
        await websocket.send_text(
            _event_payload(
                {
                    "session_id": session_id,
                    "type": "stt",
                    "text": transcript,
                    "ok": bool(asr_result.get("ok") or transcript),
                    "error": "" if transcript else str(asr_result.get("error") or "asr_empty_text"),
                    "audio_duration_ms": duration_ms,
                    "audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                    "official_audio_path": bool(asr_result.get("official_audio_path") or str(audio_params.get("format") or "").lower() == "opus"),
                    "compatibility_mode": asr_result.get("compatibility_mode") or "",
                    "control_boundary": "speech_to_text_only_not_motion_permission",
                }
            )
        )

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                if audio_chunks:
                    await finish_xiaozhi_turn({}, disconnected=True)
                break
            if "bytes" in message and message["bytes"] is not None:
                chunk = bytes(message["bytes"])
                parsed_frame = parse_xiaozhi_audio_frame(chunk, audio_params, protocol_version=protocol_version)
                payload = bytes(parsed_frame.get("payload") or b"")
                audio_format = str(audio_params.get("format") or "opus").lower()
                expected_pcm_frame_bytes = (
                    int(audio_params.get("sample_rate") or 16000)
                    * int(audio_params.get("channels") or 1)
                    * 2
                    * int(audio_params.get("frame_duration") or 60)
                    // 1000
                )
                if (
                    protocol_version == 3
                    and audio_format == "opus"
                    and parsed_frame.get("binary_protocol") == "xiaozhi_v3"
                    and parsed_frame.get("frame_type") == 0
                    and parsed_frame.get("reserved") == 0
                    and len(payload) == expected_pcm_frame_bytes
                ):
                    audio_params = {**audio_params, "format": "pcm_s16le", "bits_per_sample": 16}
                    audio_format = "pcm_s16le"
                audio_chunks.append(payload)
                audio_frame_count += 1
                audio_bytes = sum(len(item) for item in audio_chunks)
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_input",
                        {
                            "event": "audio_frame",
                            "protocol_version": protocol_version,
                            "protocol_version_header": protocol_header,
                            "device_id_header": device_header,
                            "client_id_header": client_header,
                            "audio_format": audio_format,
                            "official_audio_path": audio_format == "opus",
                            "compatibility_mode": "debug_pcm_s16le_not_official_xiaozhi_audio" if audio_format == "pcm_s16le" else "",
                            "binary_protocol": parsed_frame.get("binary_protocol"),
                            "frame_type": parsed_frame.get("frame_type"),
                            "reserved": parsed_frame.get("reserved"),
                            "payload_size": parsed_frame.get("payload_size"),
                            "payload_bytes": len(payload),
                            "raw_frame_bytes": len(chunk),
                            "audio_frame_count": audio_frame_count,
                            "audio_frame_bytes": len(payload),
                            "audio_bytes": audio_bytes,
                            "audio_duration_ms": pcm_duration_ms(audio_bytes, audio_params),
                            "parse_error": parsed_frame.get("parse_error") or "",
                            "audio_params": audio_params,
                        },
                    )
                )
                continue

            text = message.get("text")
            if text is None:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_text(_event_payload({"type": "error", "message": "invalid_json"}))
                continue
            if not isinstance(event, dict):
                await websocket.send_text(_event_payload({"type": "error", "message": "json_object_required"}))
                continue

            event_type = str(event.get("type") or "")
            if event_type == "hello":
                hello_version = event.get("version")
                try:
                    hello_version_int = int(hello_version or protocol_version)
                except (TypeError, ValueError):
                    hello_version_int = protocol_version
                if protocol_header and hello_version_int != protocol_version:
                    await websocket.send_text(
                        _event_payload(
                            {
                                "type": "error",
                                "message": "hello_version_must_match_protocol_version_header",
                                "version": protocol_version,
                            }
                        )
                    )
                    continue
                protocol_version = hello_version_int
                incoming_audio_params = event.get("audio_params") if isinstance(event.get("audio_params"), dict) else {}
                audio_params = {
                    "format": str(incoming_audio_params.get("format") or audio_params.get("format") or "pcm_s16le"),
                    "sample_rate": int(incoming_audio_params.get("sample_rate") or audio_params.get("sample_rate") or 16000),
                    "channels": int(incoming_audio_params.get("channels") or audio_params.get("channels") or 1),
                    "frame_duration": int(incoming_audio_params.get("frame_duration") or audio_params.get("frame_duration") or 60),
                }
                if str(audio_params.get("format") or "").lower() == "pcm_s16le":
                    audio_params["bits_per_sample"] = int(incoming_audio_params.get("bits_per_sample") or 16)
                audio_format = str(audio_params.get("format") or "opus").lower()
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_input",
                        {
                            "event": "hello",
                            "hello": event,
                            "protocol_version": protocol_version,
                            "protocol_version_header": protocol_header,
                            "device_id_header": device_header,
                            "client_id_header": client_header,
                            "audio_params": audio_params,
                            "official_audio_path": audio_format == "opus",
                            "compatibility_mode": "debug_pcm_s16le_not_official_xiaozhi_audio" if audio_format == "pcm_s16le" else "",
                            "audio_bytes": 0,
                        },
                    )
                )
                hello_ack = {"type": "hello", "version": protocol_version}
                if client_header != "rehab-arm-alpha":
                    hello_ack.update(
                        {
                            "transport": "websocket",
                            "features": {"mcp": True},
                            "audio_params": audio_params,
                            "control_boundary": "xiaozhi_handshake_only_not_motion_permission",
                        }
                    )
                await websocket.send_text(_event_payload(hello_ack))
                continue

            if event_type == "listen" and event.get("state") == "start":
                session_id = str(event.get("session_id") or session_id or f"xiaozhi_{device_id}")
                audio_chunks = []
                audio_frame_count = 0
                transcript_hint = str(event.get("text") or event.get("transcript") or "")
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_input",
                        {
                            "event": "listen_start",
                            "mode": event.get("mode") or "auto_stop",
                            "protocol_version": protocol_version,
                            "audio_params": audio_params,
                            "audio_bytes": 0,
                            "audio_duration_ms": 0,
                        },
                    )
                )
                await websocket.send_text(_event_payload({"session_id": session_id, "type": "listen", "state": "start"}))
                continue

            if event_type == "listen" and event.get("state") == "detect":
                session_id = str(event.get("session_id") or session_id or f"xiaozhi_{device_id}")
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_input",
                        {
                            "event": "listen_detect",
                            "text": event.get("text") or event.get("wake_word") or "",
                            "protocol_version": protocol_version,
                            "audio_params": audio_params,
                        },
                    )
                )
                await websocket.send_text(
                    _event_payload({"session_id": session_id, "type": "listen", "state": "detect", "text": event.get("text") or event.get("wake_word") or ""})
                )
                continue

            if event_type == "listen" and event.get("state") == "stop":
                session_id = str(event.get("session_id") or session_id or f"xiaozhi_{device_id}")
                transcript = str(event.get("text") or event.get("transcript") or transcript_hint or "")
                audio_bytes = sum(len(item) for item in audio_chunks)
                audio_blob = b"".join(audio_chunks)
                duration_ms = pcm_duration_ms(audio_bytes, audio_params)
                asr_result: dict = {"ok": bool(transcript), "called": False, "text": transcript, "error": ""}
                if not transcript and audio_blob:
                    asr_result = transcribe_xiaozhi_audio(audio_blob, audio_params, audio_chunks)
                    transcript = str(asr_result.get("text") or "")
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_input",
                        {
                            "event": "listen_stop",
                            "protocol_version": protocol_version,
                            "audio_params": audio_params,
                            "audio_frame_count": audio_frame_count,
                            "audio_bytes": audio_bytes,
                            "audio_duration_ms": duration_ms,
                            "asr_called": bool(asr_result.get("called")),
                            "asr_ok": bool(asr_result.get("ok")),
                            "asr_text": transcript,
                            "asr_error": str(asr_result.get("error") or ""),
                            "asr_audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                            "asr_audio_prep": asr_result.get("asr_audio_prep") or {},
                            "prepared_audio_bytes": int(asr_result.get("prepared_audio_bytes") or 0),
                            "official_audio_path": bool(asr_result.get("official_audio_path") or str(audio_params.get("format") or "").lower() == "opus"),
                            "compatibility_mode": asr_result.get("compatibility_mode") or "",
                        },
                    )
                )
                await websocket.send_text(
                    _event_payload(
                        {
                            "session_id": session_id,
                            "type": "stt",
                            "text": transcript,
                            "ok": bool(asr_result.get("ok") or transcript),
                            "error": "" if transcript else str(asr_result.get("error") or "asr_empty_text"),
                            "audio_duration_ms": duration_ms,
                            "audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                            "official_audio_path": bool(asr_result.get("official_audio_path") or str(audio_params.get("format") or "").lower() == "opus"),
                            "compatibility_mode": asr_result.get("compatibility_mode") or "",
                            "control_boundary": "speech_to_text_only_not_motion_permission",
                        }
                    )
                )
                relay_payload = {
                    "schema_version": "model_relay_request_v1",
                    "robot_id": robot_id,
                    "device_id": device_id,
                    "project_id": project_id,
                    "session_id": session_id,
                    "input_type": "vla_language_from_voice",
                    "prompt": transcript,
                    "context_refs": {
                        "audio_ref": {
                            "schema_version": "voice_audio_ref_v1",
                            "sha256": sha256_bytes(audio_blob),
                            "byte_length": audio_bytes,
                            "duration_ms": duration_ms,
                            "audio_params": audio_params,
                            "asr": {
                                "called": bool(asr_result.get("called")),
                                "ok": bool(asr_result.get("ok")),
                                "error": str(asr_result.get("error") or ""),
                                "audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                                "compatibility_mode": asr_result.get("compatibility_mode") or "",
                            },
                            "control_boundary": "voice_audio_asset_only_not_motion_permission",
                        }
                    },
                    "control_boundary": "model_relay_request_only_not_motion_permission",
                }
                relay_response = None
                if transcript:
                    try:
                        relay_response = record_model_relay_request(relay_payload)
                    except ValueError as exc:
                        await websocket.send_text(_event_payload({"type": "error", "message": str(exc)}))
                        continue
                else:
                    relay_response = {
                        "classification": {"type": "none", "confidence": 0, "control_boundary": "classification_only_not_motion_permission"},
                        "vla_language_context": {},
                        "vla_language_gate": {
                            "schema_version": "vla_language_gate_v1",
                            "classification_type": "none",
                            "participates_in_vla_l": False,
                            "route": "no_vla_input",
                            "detail": "asr_text_empty_no_llm_call",
                            "control_boundary": "language_gate_only_not_motion_permission",
                        },
                        "operator_facing_reply": "没有识别到有效语音文本，模型未进入动作建议。",
                        "summary": "ASR 未返回文本，未进入 LLM/VLA。",
                    }
                classification = relay_response.get("classification") if isinstance(relay_response.get("classification"), dict) else {}
                language_context = relay_response.get("vla_language_context") if isinstance(relay_response.get("vla_language_context"), dict) else {}
                language_gate = relay_response.get("vla_language_gate") if isinstance(relay_response.get("vla_language_gate"), dict) else {}
                kind = str(classification.get("type") or "none")
                reply = str(relay_response.get("operator_facing_reply") or relay_response.get("summary") or "请再说一遍。")
                await websocket.send_text(
                    _event_payload(
                        {
                            "type": "llm",
                            "kind": kind,
                            "text": reply,
                            "entered_llm": bool(transcript),
                            "vla_language_gate": language_gate,
                            "control_boundary": "llm_reply_only_not_motion_permission",
                        }
                    )
                )
                if kind == "vla_command":
                    chat = {
                        "type": "chat",
                        "kind": "vla_command",
                        "transcript": transcript,
                        "language_context": json.dumps(language_context, ensure_ascii=False),
                        "vla_language_gate": language_gate,
                        "reply": reply,
                        "control_boundary": "vla_language_only_not_motion_permission",
                    }
                elif kind == "daily_chat":
                    chat = {
                        "type": "chat",
                        "kind": "daily_chat",
                        "vla_language_gate": language_gate,
                        "reply": reply,
                        "control_boundary": "daily_chat_only_not_motion_permission",
                    }
                else:
                    chat = {
                        "type": "chat",
                        "kind": "none",
                        "vla_language_gate": language_gate,
                        "reply": reply or "没有听清，请再说一遍。",
                        "control_boundary": "no_command_detected_not_motion_permission",
                    }
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_reply",
                        {
                            "event": "reply",
                            "kind": chat["kind"],
                            "transcript": transcript,
                            "protocol_version": protocol_version,
                            "audio_params": audio_params,
                            "audio_frame_count": audio_frame_count,
                            "audio_bytes": audio_bytes,
                            "audio_duration_ms": duration_ms,
                            "asr_called": bool(asr_result.get("called")),
                            "asr_ok": bool(asr_result.get("ok")),
                            "asr_error": str(asr_result.get("error") or ""),
                            "asr_audio_format": asr_result.get("audio_format") or audio_params.get("format") or "",
                            "asr_audio_prep": asr_result.get("asr_audio_prep") or {},
                            "prepared_audio_bytes": int(asr_result.get("prepared_audio_bytes") or 0),
                            "official_audio_path": bool(asr_result.get("official_audio_path") or str(audio_params.get("format") or "").lower() == "opus"),
                            "compatibility_mode": asr_result.get("compatibility_mode") or "",
                            "entered_llm": bool(transcript),
                            "entered_tts": True,
                            "classification": classification,
                            "vla_language_gate": language_gate,
                            "reply": reply,
                        },
                    )
                )
                await websocket.send_text(_event_payload(chat))
                await websocket.send_text(_event_payload({"session_id": session_id, "type": "tts", "state": "start"}))
                tts_result = synthesize_xiaozhi_tts(reply, audio_params)
                tts_audio = bytes(tts_result.get("audio") or b"")
                tts_audio_packets = [bytes(packet) for packet in (tts_result.get("audio_packets") or [])]
                tts_audio_format = str(tts_result.get("audio_format") or "").lower()
                tts_sent_frames = 0
                tts_sent_bytes = 0
                tts_send_error = ""
                tts_frame_delay_s = max(0.01, min(0.12, float(audio_params.get("frame_duration") or 60) / 1000.0))
                if tts_audio_packets:
                    for payload in tts_audio_packets:
                        frame_payload = bytes([0, 0]) + len(payload).to_bytes(2, "big") + payload if protocol_version == 3 else payload
                        try:
                            await asyncio.wait_for(websocket.send_bytes(frame_payload), timeout=2.0)
                        except TimeoutError:
                            tts_send_error = f"tts_send_timeout:frame={tts_sent_frames}"
                            break
                        tts_sent_frames += 1
                        tts_sent_bytes += len(payload)
                        await asyncio.sleep(tts_frame_delay_s)
                elif tts_audio:
                    frame_bytes = max(
                        2,
                        len(tts_audio)
                        if tts_audio_format == "opus"
                        else int(audio_params.get("sample_rate") or 16000)
                        * int(audio_params.get("channels") or 1)
                        * 2
                        * int(audio_params.get("frame_duration") or 60)
                        // 1000,
                    )
                    for offset in range(0, len(tts_audio), frame_bytes):
                        payload = tts_audio[offset : offset + frame_bytes]
                        frame_payload = bytes([0, 0]) + len(payload).to_bytes(2, "big") + payload if protocol_version == 3 else payload
                        try:
                            await asyncio.wait_for(websocket.send_bytes(frame_payload), timeout=2.0)
                        except TimeoutError:
                            tts_send_error = f"tts_send_timeout:frame={tts_sent_frames}"
                            break
                        tts_sent_frames += 1
                        tts_sent_bytes += len(payload)
                        await asyncio.sleep(tts_frame_delay_s)
                record_xiaozhi_ws_event(
                    base_payload(
                        "xiaozhi_ws_tts",
                        {
                            "event": "tts",
                            "called": bool(tts_result.get("called")),
                            "ok": bool(tts_result.get("ok")) and not tts_send_error,
                            "error": tts_send_error or str(tts_result.get("error") or ""),
                            "provider_configured": bool(tts_result.get("provider_configured")),
                            "audio_format": tts_result.get("audio_format") or "",
                            "source_audio_format": tts_result.get("source_audio_format") or "",
                            "pcm_bytes": int(tts_result.get("pcm_bytes") or 0),
                            "opus_packet_count": int(tts_result.get("opus_packet_count") or len(tts_audio_packets)),
                            "audio_bytes": len(tts_audio),
                            "sent_frames": tts_sent_frames,
                            "sent_bytes": tts_sent_bytes,
                            "control_boundary": "tts_feedback_only_not_motion_permission",
                        },
                    )
                )
                await websocket.send_text(_event_payload({"session_id": session_id, "type": "tts", "state": "stop"}))
                await websocket.send_text(_event_payload({"session_id": session_id, "type": "listen", "state": "stop"}))
                audio_chunks = []
                audio_frame_count = 0
                continue

            await websocket.send_text(_event_payload({"type": "error", "message": "unsupported_xiaozhi_event"}))
    except WebSocketDisconnect:
        if audio_chunks:
            await finish_xiaozhi_turn({}, disconnected=True)


@router.post("/projects/{project_id}/devices/{device_id}/model/relay-token")
def api_issue_model_relay_token(
    project_id: str,
    device_id: str,
    payload: RehabModelRelayTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(
        db,
        request,
        project_id,
        require_privileged=True,
        action="rehab_arm.model_relay_token.create",
    )
    try:
        require_device_project_match(device_id, project_id)
        return ok(issue_model_relay_token(project_id, device_id, payload.ttl_seconds, payload.label))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/projects/{project_id}/model-relay/config")
def api_get_model_relay_config(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="rehab_arm.model_relay_config.read")
    return ok(model_relay_config_status())


@router.put("/projects/{project_id}/model-relay/config")
def api_update_model_relay_config(
    project_id: str,
    payload: RehabModelRelayConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(
        db,
        request,
        project_id,
        require_privileged=True,
        action="rehab_arm.model_relay_config.update",
    )
    try:
        return ok(update_model_relay_config(payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/devices/{device_id}/wiring-health")
def api_get_wiring_health(device_id: str):
    return ok(build_wiring_health(device_id))


@router.get("/devices/{device_id}/safety")
def api_get_safety(device_id: str):
    return ok(build_safety_status(device_id))


@router.post("/devices/{device_id}/estop")
def api_estop(device_id: str, payload: RehabEstopRequest):
    if payload.device_id != device_id:
        raise HTTPException(status_code=422, detail="payload.device_id must match path device_id")
    return ok(record_estop_request(payload.model_dump(mode="json")))


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
