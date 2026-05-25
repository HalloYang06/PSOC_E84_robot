from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from app.settings import get_settings


_SAFE_PART_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_part(value: str | None, fallback: str = "unknown") -> str:
    cleaned = _SAFE_PART_RE.sub("_", (value or "").strip()).strip("._")
    return cleaned or fallback


def storage_root() -> Path:
    root = Path(get_settings().rehab_arm_sync_storage_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
    return None


def read_recent_events(limit: int = 24) -> list[dict[str, Any]]:
    path = storage_root() / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return list(reversed(events))


def device_dir(device_id: str) -> Path:
    return storage_root() / "device_state" / safe_part(device_id)


def write_device_latest(device_id: str, name: str, record: dict[str, Any]) -> None:
    write_json(device_dir(device_id) / f"{name}_latest.json", record)


def append_device_event(device_id: str, record: dict[str, Any]) -> None:
    append_jsonl(device_dir(device_id) / "events.jsonl", record)


def telemetry_record(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    robot_id = safe_part(str(payload.get("robot_id") or "unknown"))
    record = {
        "ts_unix": time.time(),
        "record_type": record_type,
        "device_id": device_id,
        "robot_id": robot_id,
        "sync_role": "non_realtime_telemetry_data_asset_only",
        "safety_boundary": "server_never_sends_can_or_motor_setpoints_m33_final_authority",
        "payload": payload,
    }
    append_jsonl(storage_root() / "events.jsonl", record)
    append_device_event(device_id, record)
    return record


def record_device_registration(payload: dict[str, Any]) -> dict[str, Any]:
    root = storage_root()
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    robot_id = safe_part(str(payload.get("robot_id") or "unknown"))
    record = {
        "ts_unix": time.time(),
        "record_type": "device_registration",
        "device_id": device_id,
        "robot_id": robot_id,
        "payload": payload,
    }
    write_json(root / "devices" / f"{robot_id}__{device_id}.json", record)
    write_device_latest(device_id, "registration", record)
    append_jsonl(root / "events.jsonl", record)
    append_device_event(device_id, record)
    return {
        "ok": True,
        "device_id": device_id,
        "robot_id": robot_id,
        "sync_role": "non_realtime_data_only",
    }


def record_manifest_upload(payload: dict[str, Any]) -> dict[str, Any]:
    root = storage_root()
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    sessions = manifest.get("sessions") if isinstance(manifest, dict) else []
    accepted_sessions = [
        str(item.get("session_id"))
        for item in sessions
        if isinstance(item, dict) and item.get("ok") is True and item.get("session_id")
    ]
    record = {
        "ts_unix": time.time(),
        "record_type": "manifest",
        "session_count": len(sessions) if isinstance(sessions, list) else 0,
        "accepted_sessions": accepted_sessions,
        "payload": payload,
    }
    write_json(root / "manifests" / f"{int(record['ts_unix'] * 1000)}.json", record)
    append_jsonl(root / "events.jsonl", record)
    device_ids = {
        safe_part(str(item.get("device_id")))
        for item in sessions
        if isinstance(sessions, list) and isinstance(item, dict) and item.get("device_id")
    }
    for device_id in device_ids:
        write_device_latest(device_id, "manifest", record)
        append_device_event(device_id, record)
    return {
        "ok": True,
        "accepted_sessions": accepted_sessions,
        "missing_files": [],
        "upload_urls": [],
    }


def _manifest_sessions(manifest_record: dict[str, Any]) -> list[dict[str, Any]]:
    payload = manifest_record.get("payload")
    manifest = payload.get("manifest") if isinstance(payload, dict) else None
    sessions = manifest.get("sessions") if isinstance(manifest, dict) else None
    return [item for item in sessions if isinstance(item, dict)] if isinstance(sessions, list) else []


def _session_quality(session: dict[str, Any]) -> dict[str, Any]:
    quality_report = session.get("quality_report") if isinstance(session.get("quality_report"), dict) else {}
    summary = session.get("summary") if isinstance(session.get("summary"), dict) else {}
    if not summary and isinstance(quality_report.get("summary"), dict):
        summary = quality_report["summary"]
    topic_counts = summary.get("topic_counts") if isinstance(summary.get("topic_counts"), dict) else {}
    motion_allowed_counts = summary.get("motion_allowed_counts") if isinstance(summary.get("motion_allowed_counts"), dict) else {}
    moving_joint_count = int(summary.get("moving_joint_count") or 0)
    motor_entry_count_min = int(summary.get("motor_entry_count_min") or 0)
    motor_entry_count_max = int(summary.get("motor_entry_count_max") or 0)
    motion_allowed_true = int(motion_allowed_counts.get("true") or 0)
    errors: list[str] = []
    warnings: list[str] = []
    quality_report_ok = quality_report.get("ok")
    if session.get("ok") is not True:
        errors.extend([str(item) for item in session.get("errors", []) if item])
        if not errors:
            errors.append("session manifest marked not ok")
    if quality_report and quality_report_ok is not True:
        errors.extend([str(item) for item in quality_report.get("errors", []) if item])
        if not errors:
            errors.append("quality report marked not ok")
    if not summary:
        warnings.append("session has no summary; label/export can start after data quality summary is uploaded")
    if summary and not topic_counts:
        warnings.append("summary has no topic_counts; UI can still index the session but cannot preview streams")
    if summary and moving_joint_count <= 0:
        warnings.append("no joint motion detected; this may be normal for non-robot logs, images, audio, or static checks")
    if summary and motor_entry_count_min <= 0:
        warnings.append("no motor_state entries detected; this may be normal for non-motor devices")
    if motion_allowed_true > 0:
        warnings.append("motion_allowed true appears in data; keep annotation/export separate from motion permission")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "session_id": session.get("session_id") or "",
        "file_name": session.get("file_name") or "",
        "record_count": session.get("record_count") or 0,
        "moving_joint_count": moving_joint_count,
        "motor_entry_count_min": motor_entry_count_min,
        "motor_entry_count_max": motor_entry_count_max,
        "topic_counts": topic_counts,
        "motion_allowed_true_count": motion_allowed_true,
        "summary_schema": summary.get("schema_version") or "",
        "quality_report_schema": quality_report.get("schema_version") or "",
        "quality_report_ok": quality_report_ok,
        "quality_criteria": quality_report.get("criteria") if isinstance(quality_report.get("criteria"), dict) else {},
        "source_schema": session.get("schema_version") or "",
    }


def build_data_quality_index(manifest_record: dict[str, Any]) -> dict[str, Any]:
    sessions = _manifest_sessions(manifest_record)
    quality_sessions = [_session_quality(session) for session in sessions]
    annotatable = [session for session in quality_sessions if session["ok"]]
    latest = annotatable[0] if annotatable else (quality_sessions[0] if quality_sessions else {})
    blocking_reasons: list[str] = []
    if not sessions:
        blocking_reasons.append("waiting for manifest_with_summary upload")
    elif not annotatable:
        blocking_reasons.extend(latest.get("errors", []) if isinstance(latest, dict) else [])
    return {
        "schema_version": "device_recording_quality_index_v1",
        "session_count": len(sessions),
        "annotatable_session_count": len(annotatable),
        "latest_session": latest,
        "sessions": quality_sessions[:8],
        "annotation_ready": bool(annotatable),
        "blocking_reasons": blocking_reasons,
        "handoff_target": "device_data_workbench_dataset_tab",
        "control_boundary": "data_quality_only_not_motion_permission",
        "adapter": "rehab_arm_sync_v1",
    }


def record_session_file(session_id: str, content_type: str, body: bytes) -> dict[str, Any]:
    root = storage_root()
    safe_session_id = safe_part(session_id, "unknown_session")
    timestamp_ms = int(time.time() * 1000)
    body_path = root / "sessions" / safe_session_id / f"{timestamp_ms}_multipart_body.bin"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(body)
    record = {
        "ts_unix": time.time(),
        "record_type": "session_file",
        "session_id": safe_session_id,
        "content_type": content_type,
        "size_bytes": len(body),
        "sha256": sha256_bytes(body),
        "body_path": str(body_path),
    }
    append_jsonl(root / "events.jsonl", record)
    append_jsonl(root / "sessions" / safe_session_id / "events.jsonl", record)
    return {
        "ok": True,
        "session_id": safe_session_id,
        "sync_status": "uploaded",
        "size_bytes": len(body),
        "sha256": record["sha256"],
        "stored_body_path": str(body_path),
    }


def record_sync_status(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    root = storage_root()
    safe_session_id = safe_part(session_id, "unknown_session")
    record = {
        "ts_unix": time.time(),
        "record_type": "sync_status",
        "session_id": safe_session_id,
        "payload": payload,
    }
    append_jsonl(root / "events.jsonl", record)
    append_jsonl(root / "sessions" / safe_session_id / "events.jsonl", record)
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    write_device_latest(device_id, "sync_status", record)
    append_device_event(device_id, record)
    return {
        "ok": True,
        "session_id": safe_session_id,
        "sync_status": payload.get("sync_status", "received"),
        "file_name": payload.get("file_name", ""),
    }


def record_motor_state(payload: dict[str, Any]) -> dict[str, Any]:
    record = telemetry_record("motor_state", payload)
    write_device_latest(record["device_id"], "motor_state", record)
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "motor_count": len(payload.get("motors") or []),
        "sync_role": record["sync_role"],
    }


def record_sensor_state(payload: dict[str, Any]) -> dict[str, Any]:
    record = telemetry_record("sensor_state", payload)
    write_device_latest(record["device_id"], "sensor_state", record)
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "sync_role": record["sync_role"],
    }


def record_safety_state(payload: dict[str, Any]) -> dict[str, Any]:
    record = telemetry_record("safety_state", payload)
    write_device_latest(record["device_id"], "safety_state", record)
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "state": payload.get("state"),
        "motion_allowed": payload.get("motion_allowed", False),
        "sync_role": record["sync_role"],
    }


def record_camera_keyframe(payload: dict[str, Any], image_bytes: bytes) -> dict[str, Any]:
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    robot_id = safe_part(str(payload.get("robot_id") or "unknown"))
    camera_id = safe_part(str(payload.get("camera_id") or "camera"))
    image_format = safe_part(str(payload.get("image_format") or "jpg")).lower()
    timestamp_ms = int(float(payload.get("frame_ts_unix") or time.time()) * 1000)
    digest = sha256_bytes(image_bytes)
    image_path = storage_root() / "keyframes" / device_id / f"{timestamp_ms}_{camera_id}.{image_format}"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    record = telemetry_record(
        "camera_keyframe",
        {
            **payload,
            "device_id": device_id,
            "robot_id": robot_id,
            "camera_id": camera_id,
            "image_format": image_format,
            "sha256": digest,
            "size_bytes": len(image_bytes),
        },
    )
    record["image_path"] = str(image_path)
    record["image_url"] = f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes/latest/file"
    write_device_latest(device_id, "camera_keyframe", record)
    return {
        "ok": True,
        "device_id": device_id,
        "robot_id": robot_id,
        "camera_id": camera_id,
        "sha256": digest,
        "size_bytes": len(image_bytes),
        "image_url": record["image_url"],
        "sync_role": record["sync_role"],
    }


def latest_keyframe_path(device_id: str) -> Path | None:
    latest = read_json(device_dir(device_id) / "camera_keyframe_latest.json")
    path = Path(str(latest.get("image_path") or "")) if latest else None
    if path and path.is_file():
        return path
    return None


def _device_latest(device_id: str, name: str) -> dict[str, Any] | None:
    return read_json(device_dir(device_id) / f"{name}_latest.json")


def build_dashboard() -> dict[str, Any]:
    root = storage_root()
    device_ids: set[str] = set()
    for path in (root / "device_state").glob("*"):
        if path.is_dir():
            device_ids.add(path.name)
    for path in (root / "devices").glob("*.json"):
        record = read_json(path)
        if record and record.get("device_id"):
            device_ids.add(safe_part(str(record.get("device_id"))))

    devices: list[dict[str, Any]] = []
    now = time.time()
    for device_id in sorted(device_ids):
        registration = _device_latest(device_id, "registration") or {}
        motor_state = _device_latest(device_id, "motor_state") or {}
        sensor_state = _device_latest(device_id, "sensor_state") or {}
        safety_state = _device_latest(device_id, "safety_state") or {}
        camera_keyframe = _device_latest(device_id, "camera_keyframe") or {}
        sync_status = _device_latest(device_id, "sync_status") or {}
        manifest = _device_latest(device_id, "manifest") or {}
        data_quality = build_data_quality_index(manifest)
        latest_records = [registration, motor_state, sensor_state, safety_state, camera_keyframe, sync_status, manifest]
        last_upload = max([float(item.get("ts_unix") or 0) for item in latest_records if item] or [0])
        safety_payload = safety_state.get("payload") if isinstance(safety_state.get("payload"), dict) else {}
        register_payload = registration.get("payload") if isinstance(registration.get("payload"), dict) else {}
        sync_payload = sync_status.get("payload") if isinstance(sync_status.get("payload"), dict) else {}
        devices.append(
            {
                "device_id": device_id,
                "robot_id": safe_part(str(register_payload.get("robot_id") or safety_state.get("robot_id") or motor_state.get("robot_id") or "unknown")),
                "online_state": "online" if last_upload and now - last_upload <= 180 else "offline",
                "last_upload_ts_unix": last_upload or None,
                "safety_state": safety_payload.get("state", "ok" if not safety_state else "fault"),
                "motion_allowed": bool(safety_payload.get("motion_allowed", False)),
                "current_session": sync_status.get("session_id") or "",
                "latest_upload_status": sync_payload.get("sync_status") or ("received" if last_upload else "none"),
                "latest_error": safety_payload.get("fault_message") or safety_payload.get("detail") or "",
                "data_quality": data_quality,
                "registration": registration,
                "camera_keyframe": camera_keyframe,
                "motor_state": motor_state,
                "sensor_state": sensor_state,
                "safety": safety_state,
                "sync_status": sync_status,
                "manifest": manifest,
            }
        )
    return {
        "sync_role": "non_realtime_telemetry_data_asset_only",
        "safety_boundary": {
            "server_may_send": ["high_level_task", "data_request", "configuration_suggestion", "annotation_task", "vla_task_draft"],
            "server_must_not_send": ["can_frame", "motor_current", "motor_torque", "motor_raw_position", "motor_velocity", "m33_override", "emergency_stop_dependency"],
            "m33_final_authority": True,
        },
        "devices": devices,
        "recent_events": read_recent_events(32),
    }
