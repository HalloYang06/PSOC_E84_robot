from __future__ import annotations

import base64
import io
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

from app.settings import DEFAULT_DEV_SECRET_KEY, get_settings


_SAFE_PART_RE = re.compile(r"[^A-Za-z0-9_.-]+")
WIRING_STATUSES = {"ok", "stale", "missing", "fault", "not_wired", "unknown"}
DANGEROUS_VLA_OUTPUTS = {
    "can_frame",
    "can_frames",
    "motor_current",
    "motor_torque",
    "motor_velocity",
    "raw_motor_position",
    "raw_motor_velocity",
    "joint_trajectory",
    "trajectory_points",
    "m33_safety_override",
    "motion_allowed_override",
    "motion_permission_granted",
    "direct_motor_command",
}
MODEL_RELAY_SAFE_OUTPUTS = {
    "high_level_task",
    "dry_run_joint_trajectory_candidate",
    "model_state_suggestion",
    "voice_intent",
    "vla_language_context",
    "vla_vision_context",
    "server_to_nanopi_high_level_command",
    "camera_scene_summary",
    "sensor_summary",
}
MODEL_RELAY_CONFIG_KEYS = {
    "REHAB_ARM_MODEL_RELAY_PROVIDER",
    "REHAB_ARM_MODEL_RELAY_BASE_URL",
    "REHAB_ARM_MODEL_RELAY_MODEL",
    "REHAB_ARM_MODEL_RELAY_API_KEY",
    "REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED",
}
MODEL_RELAY_PROVIDER_PRESETS = [
    {"id": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1", "model_hint": "gpt-4o-mini / gpt-4.1-mini"},
    {"id": "azure_openai", "label": "Azure OpenAI", "base_url": "https://YOUR-RESOURCE.openai.azure.com/openai/v1", "model_hint": "deployment name"},
    {"id": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model_hint": "deepseek-chat"},
    {"id": "qwen", "label": "通义千问 / DashScope compatible", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model_hint": "qwen-plus"},
    {"id": "moonshot", "label": "Moonshot / Kimi", "base_url": "https://api.moonshot.cn/v1", "model_hint": "moonshot-v1-8k"},
    {"id": "zhipu", "label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model_hint": "glm-4-flash"},
    {"id": "siliconflow", "label": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model_hint": "Qwen/Qwen2.5-7B-Instruct"},
    {"id": "custom", "label": "自定义 OpenAI-compatible", "base_url": "", "model_hint": "model id"},
]
MODEL_RELAY_TOKEN_PREFIX = "rehab-relay.v1"
MODEL_RELAY_TOKEN_SCOPES = ["rehab_arm.model_relay.invoke", "rehab_arm.xiaozhi.websocket", "rehab_arm.vla_task.invoke"]
XIAOZHI_V3_AUDIO_FRAME_TYPE_PCM = 0
XIAOZHI_MIN_AUDIBLE_TTS_PCM_BYTES = 1600
ARM_JOINT_MAP = [
    {
        "motor_id": "3",
        "motor": "Sitaiwei CANSimple",
        "logical_joint": "shoulder_lift_joint",
        "urdf_joint": "jian_hengxiang_joint",
        "wired": True,
    },
    {"motor_id": "4", "motor": "RS00", "logical_joint": "elbow_lift_joint", "urdf_joint": "jian_zongxiang_joint", "wired": True},
    {
        "motor_id": "5",
        "motor": "RS00",
        "logical_joint": "shoulder_abduction_joint",
        "urdf_joint": "zhou_zongxiang_joint",
        "wired": True,
    },
    {
        "motor_id": "6",
        "motor": "EL05",
        "logical_joint": "upper_arm_rotation_joint",
        "urdf_joint": "jian_xuanzhuan_joint",
        "wired": True,
    },
    {"motor_id": "1", "motor": "4015", "logical_joint": "wrist_pending_1", "urdf_joint": "wanbu_zongxiang_joint", "wired": False},
    {"motor_id": "2", "motor": "4015", "logical_joint": "wrist_pending_2", "urdf_joint": "wanbu_hengxiang_joint", "wired": False},
]


def safe_part(value: str | None, fallback: str = "unknown") -> str:
    cleaned = _SAFE_PART_RE.sub("_", (value or "").strip()).strip("._")
    return cleaned or fallback


def storage_root() -> Path:
    root = Path(get_settings().rehab_arm_sync_storage_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def repo_root() -> Path:
    configured = os.environ.get("AI_COLLAB_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[5]


def _shell_quote_env(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _read_env_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _write_relay_env(updates: dict[str, str]) -> None:
    path = repo_root() / ".env"
    lines = _read_env_lines(path)
    remaining = [line for line in lines if line.split("=", 1)[0].strip() not in MODEL_RELAY_CONFIG_KEYS]
    if remaining and remaining[-1].strip():
        remaining.append("")
    for key in [
        "REHAB_ARM_MODEL_RELAY_PROVIDER",
        "REHAB_ARM_MODEL_RELAY_BASE_URL",
        "REHAB_ARM_MODEL_RELAY_MODEL",
        "REHAB_ARM_MODEL_RELAY_API_KEY",
        "REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED",
    ]:
        if key not in updates:
            continue
        remaining.append(f"{key}={_shell_quote_env(updates[key])}")
        os.environ[key] = updates[key]
    path.write_text("\n".join(remaining).rstrip() + "\n", encoding="utf-8")
    get_settings.cache_clear()


def _relay_token_secret() -> str:
    settings = get_settings()
    secret = settings.secret_key.strip()
    if secret:
        return secret
    return DEFAULT_DEV_SECRET_KEY


def _encode_token_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_token_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    value = json.loads(raw.decode("utf-8"))
    return value if isinstance(value, dict) else {}


def issue_model_relay_token(project_id: str, device_id: str, ttl_seconds: int, label: str = "") -> dict[str, Any]:
    now = int(time.time())
    exp = now + max(60, min(int(ttl_seconds or 0), 30 * 24 * 60 * 60))
    payload = {
        "v": 1,
        "kind": "rehab_model_relay",
        "project_id": str(project_id or "").strip(),
        "device_id": safe_part(device_id),
        "scope": MODEL_RELAY_TOKEN_SCOPES,
        "label": str(label or "rehab-arm-model-relay-token").strip()[:120],
        "iat": now,
        "exp": exp,
    }
    encoded = _encode_token_payload(payload)
    signature = hmac.new(_relay_token_secret().encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{MODEL_RELAY_TOKEN_PREFIX}.{encoded}.{signature}"
    return {
        "schema_version": "model_relay_token_v1",
        "token": token,
        "token_type": "bearer",
        "project_id": payload["project_id"],
        "device_id": payload["device_id"],
        "scope": payload["scope"],
        "expires_at_unix": exp,
        "control_boundary": "model_relay_invocation_only_not_motion_permission",
    }


def verify_model_relay_token(
    token: str,
    project_id: str,
    device_id: str,
    required_scope: str = "rehab_arm.model_relay.invoke",
) -> bool:
    parts = str(token or "").strip().split(".")
    if len(parts) != 4 or ".".join(parts[:2]) != MODEL_RELAY_TOKEN_PREFIX:
        return False
    encoded = parts[2]
    signature = parts[3]
    expected = hmac.new(_relay_token_secret().encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = _decode_token_payload(encoded)
    except Exception:
        return False
    if payload.get("v") != 1 or payload.get("kind") != "rehab_model_relay":
        return False
    if int(payload.get("exp") or 0) < int(time.time()):
        return False
    if str(payload.get("project_id") or "").strip() != str(project_id or "").strip():
        return False
    if safe_part(str(payload.get("device_id") or "")) != safe_part(device_id):
        return False
    return required_scope in set(payload.get("scope") or [])


def model_relay_config_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "schema_version": "model_relay_config_status_v1",
        "provider": settings.rehab_arm_model_relay_provider.strip() or "openai_compatible",
        "base_url": settings.rehab_arm_model_relay_base_url.strip(),
        "model": settings.rehab_arm_model_relay_model.strip(),
        "external_enabled": bool(settings.rehab_arm_model_relay_external_enabled),
        "api_key_configured": bool(settings.rehab_arm_model_relay_api_key.strip()),
        "api_key_exposed_to_browser": False,
        "presets": MODEL_RELAY_PROVIDER_PRESETS,
        "control_boundary": "server_secret_config_only_not_motion_permission",
    }


def update_model_relay_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "openai_compatible").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    model = str(payload.get("model") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    external_enabled = bool(payload.get("external_enabled", True))
    if not provider or not base_url or not model:
        raise ValueError("provider, base_url, and model are required")
    updates = {
        "REHAB_ARM_MODEL_RELAY_PROVIDER": provider,
        "REHAB_ARM_MODEL_RELAY_BASE_URL": base_url,
        "REHAB_ARM_MODEL_RELAY_MODEL": model,
        "REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED": "true" if external_enabled else "false",
    }
    if api_key:
        updates["REHAB_ARM_MODEL_RELAY_API_KEY"] = api_key
    elif not get_settings().rehab_arm_model_relay_api_key.strip():
        raise ValueError("api_key is required for first-time model relay provider setup")
    _write_relay_env(updates)
    return model_relay_config_status()


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


def read_recent_events(limit: int = 24, project_id: str | None = None) -> list[dict[str, Any]]:
    path = storage_root() / "events.jsonl"
    project_filter = (project_id or "").strip()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if not project_filter:
        events: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return list(reversed(events))
    events = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or _record_project_id(value) != project_filter:
            continue
        events.append(value)
        if len(events) >= max(1, limit):
            break
    return events


def device_dir(device_id: str) -> Path:
    return storage_root() / "device_state" / safe_part(device_id)


def write_device_latest(device_id: str, name: str, record: dict[str, Any]) -> None:
    write_json(device_dir(device_id) / f"{name}_latest.json", record)


def append_device_event(device_id: str, record: dict[str, Any]) -> None:
    append_jsonl(device_dir(device_id) / "events.jsonl", record)


def telemetry_record(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    robot_id = safe_part(str(payload.get("robot_id") or "unknown"))
    project_id = str(payload.get("project_id") or payload.get("projectId") or "").strip()
    record = {
        "ts_unix": time.time(),
        "record_type": record_type,
        "device_id": device_id,
        "robot_id": robot_id,
        "project_id": project_id,
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
    project_id = str(payload.get("project_id") or payload.get("projectId") or "").strip()
    record = {
        "ts_unix": time.time(),
        "record_type": "device_registration",
        "device_id": device_id,
        "robot_id": robot_id,
        "project_id": project_id,
        "payload": payload,
    }
    write_json(root / "devices" / f"{robot_id}__{device_id}.json", record)
    write_device_latest(device_id, "registration", record)
    append_jsonl(root / "events.jsonl", record)
    append_device_event(device_id, record)
    return {
        "ok": True,
        "schema_version": "rehab_arm_device_register_v1",
        "device_id": device_id,
        "robot_id": robot_id,
        "sync_role": "non_realtime_data_only",
        "control_boundary": "gateway_registration_only_not_motion_permission",
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
    session_device_ids = [
        safe_part(str(item.get("device_id")))
        for item in sessions
        if isinstance(sessions, list) and isinstance(item, dict) and item.get("device_id")
    ]
    session_project_ids = [
        str(item.get("project_id") or item.get("projectId") or "").strip()
        for item in sessions
        if isinstance(sessions, list) and isinstance(item, dict) and (item.get("project_id") or item.get("projectId"))
    ]
    record = {
        "ts_unix": time.time(),
        "record_type": "manifest",
        "session_count": len(sessions) if isinstance(sessions, list) else 0,
        "accepted_sessions": accepted_sessions,
        "device_id": session_device_ids[0] if len(set(session_device_ids)) == 1 else "",
        "project_id": session_project_ids[0] if len(set(session_project_ids)) == 1 else "",
        "payload": payload,
    }
    write_json(root / "manifests" / f"{int(record['ts_unix'] * 1000)}.json", record)
    append_jsonl(root / "events.jsonl", record)
    device_ids = set(session_device_ids)
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


def record_simulation_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    record = telemetry_record("simulation_readiness", payload)
    write_device_latest(record["device_id"], "simulation_readiness", record)
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "readiness": report.get("readiness", "unknown"),
        "report_ok": report.get("ok"),
        "sync_role": record["sync_role"],
        "control_boundary": "simulation_readiness_only_not_motion_permission",
    }


def record_board_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    record = telemetry_record("board_manifest", payload)
    write_device_latest(record["device_id"], "board_manifest", record)
    capabilities = manifest.get("capabilities") if isinstance(manifest, dict) else {}
    if not isinstance(capabilities, dict):
        capabilities = {}
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "schema_version": manifest.get("schema_version", "unknown"),
        "can_interface_count": len(capabilities.get("can_interfaces") or []),
        "serial_device_count": len(capabilities.get("serial_devices") or []),
        "camera_device_count": len(capabilities.get("camera_devices") or []),
        "ros2_available": bool((capabilities.get("ros2") or {}).get("available")) if isinstance(capabilities.get("ros2"), dict) else False,
        "sync_role": record["sync_role"],
        "control_boundary": "board_manifest_only_not_motion_permission",
    }


def record_device_model_package(payload: dict[str, Any], file_name: str, file_bytes: bytes) -> dict[str, Any]:
    device_id = safe_part(str(payload.get("device_id") or "unknown"))
    robot_id = safe_part(str(payload.get("robot_id") or "unknown"))
    project_id = str(payload.get("project_id") or payload.get("projectId") or "").strip()
    package_name = safe_part(str(payload.get("package_name") or file_name or "robot_model"))
    timestamp_ms = int(time.time() * 1000)
    digest = sha256_bytes(file_bytes)
    suffix = Path(file_name).suffix.lower() or ".zip"
    package_path = storage_root() / "model_packages" / device_id / f"{timestamp_ms}_{package_name}{suffix}"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_bytes(file_bytes)
    record = telemetry_record(
        "device_model",
        {
            **payload,
            "device_id": device_id,
            "robot_id": robot_id,
            "project_id": project_id,
            "file_name": file_name,
            "package_name": payload.get("package_name") or package_name,
            "sha256": digest,
            "size_bytes": len(file_bytes),
            "model_url": f"/api/rehab-arm/v1/devices/{device_id}/model-package/latest/file",
            "control_boundary": "model_preview_only_not_motion_permission",
        },
    )
    record["package_path"] = str(package_path)
    record["model_url"] = f"/api/rehab-arm/v1/devices/{device_id}/model-package/latest/file"
    write_device_latest(device_id, "device_model", record)
    return {
        "ok": True,
        "device_id": device_id,
        "robot_id": robot_id,
        "project_id": project_id,
        "file_name": file_name,
        "sha256": digest,
        "size_bytes": len(file_bytes),
        "model_url": record["model_url"],
        "sync_role": record["sync_role"],
        "control_boundary": "model_preview_only_not_motion_permission",
    }


def latest_model_package_path(device_id: str) -> Path | None:
    latest = read_json(device_dir(device_id) / "device_model_latest.json")
    path = Path(str(latest.get("package_path") or "")) if latest else None
    if path and path.is_file():
        return path
    return None


def record_motor_state(payload: dict[str, Any]) -> dict[str, Any]:
    record = telemetry_record("motor_state", payload)
    write_device_latest(record["device_id"], "motor_state", record)
    joint_state = payload.get("joint_state") or payload.get("joint_states") or {}
    joint_names: list[Any] = []
    if isinstance(joint_state, dict):
        names = joint_state.get("name") or joint_state.get("names") or []
        joint_names = names if isinstance(names, list) else []
    elif isinstance(joint_state, list):
        joint_names = [item.get("name") or item.get("joint_name") for item in joint_state if isinstance(item, dict)]
    return {
        "ok": True,
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "motor_count": len(payload.get("motors") or []),
        "joint_state_count": len([name for name in joint_names if name]),
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
        "control_boundary": "safety_status_only_not_motion_permission",
    }


def _motor_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.removeprefix("motor_").removeprefix("m")
    return raw


def _latest_payload(device_id: str, name: str) -> dict[str, Any]:
    record = _device_latest(device_id, name) or {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return payload if isinstance(payload, dict) else {}


def _joint_state_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    joint_state = payload.get("joint_state") or payload.get("joint_states") or {}
    ts_unix = payload.get("ts_unix") or payload.get("timestamp_unix")
    result: dict[str, dict[str, Any]] = {}
    if isinstance(joint_state, dict):
        names = joint_state.get("name") or joint_state.get("names") or []
        positions = joint_state.get("position") or joint_state.get("positions") or []
        velocities = joint_state.get("velocity") or joint_state.get("velocities") or []
        if isinstance(names, list):
            for index, name in enumerate(names):
                joint_name = str(name or "").strip()
                if not joint_name:
                    continue
                result[joint_name] = {
                    "position": positions[index] if isinstance(positions, list) and index < len(positions) else None,
                    "velocity": velocities[index] if isinstance(velocities, list) and index < len(velocities) else None,
                    "ts_unix": ts_unix,
                }
    if isinstance(joint_state, list):
        for item in joint_state:
            if not isinstance(item, dict):
                continue
            joint_name = str(item.get("name") or item.get("joint_name") or "").strip()
            if joint_name:
                position = item.get("position")
                if position is None:
                    position = item.get("position_rad")
                velocity = item.get("velocity")
                if velocity is None:
                    velocity = item.get("velocity_rad_s")
                result[joint_name] = {
                    "position": position,
                    "velocity": velocity,
                    "ts_unix": item.get("ts_unix") or ts_unix,
                }
    return result


def _number_if_fresh(values: list[Any], index: int, is_fresh: bool) -> float | None:
    if not is_fresh or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_render_state(render_state: dict[str, Any]) -> dict[str, Any]:
    names = list(render_state.get("joint_names") or [])
    raw_positions = list(render_state.get("positions") or [])
    raw_velocities = list(render_state.get("velocities") or [])
    raw_fresh = list(render_state.get("fresh") or [])
    raw_clamped = list(render_state.get("limit_clamped") or [])
    fresh = [raw_fresh[index] is True for index, _name in enumerate(names)]
    return {
        "schema_version": "robot_render_state_v1",
        "urdf_asset_id": render_state.get("urdf_asset_id", "rehab_arm_urdf_current"),
        "joint_names": names,
        "positions": [_number_if_fresh(raw_positions, index, fresh[index]) for index, _name in enumerate(names)],
        "velocities": [_number_if_fresh(raw_velocities, index, fresh[index]) for index, _name in enumerate(names)],
        "fresh": fresh,
        "limit_clamped": [raw_clamped[index] is True if index < len(raw_clamped) else False for index, _name in enumerate(names)],
    }


def build_robot_render_state(device_id: str) -> dict[str, Any]:
    snapshot = _latest_payload(device_id, "command_center_snapshot")
    render_state = snapshot.get("robot_render_state") if isinstance(snapshot.get("robot_render_state"), dict) else {}
    if render_state:
        return _normalized_render_state(render_state)

    motor_payload = _latest_payload(device_id, "motor_state")
    by_joint = _joint_state_map(motor_payload)
    motor_by_id: dict[str, dict[str, Any]] = {}
    for motor in motor_payload.get("motors") or []:
        if isinstance(motor, dict):
            motor_by_id[_motor_key(motor.get("motor_id"))] = motor

    joint_names: list[str] = []
    positions: list[float | None] = []
    velocities: list[float | None] = []
    fresh: list[bool] = []
    limit_clamped: list[bool] = []
    now = time.time()
    for row in ARM_JOINT_MAP:
        joint_names.append(row["urdf_joint"])
        source = by_joint.get(row["logical_joint"]) or by_joint.get(row["urdf_joint"]) or motor_by_id.get(row["motor_id"]) or {}
        ts_unix = float(source.get("ts_unix") or motor_payload.get("ts_unix") or 0)
        has_position = source.get("position") is not None
        is_fresh = bool(row["wired"] and has_position and ts_unix and now - ts_unix <= 2.0)
        positions.append(float(source.get("position")) if has_position and is_fresh else None)
        velocity = source.get("velocity")
        velocities.append(float(velocity) if velocity is not None and is_fresh else None)
        fresh.append(is_fresh)
        limit_clamped.append(bool(source.get("limit_clamped") or source.get("clamped") or False))

    return {
        "schema_version": "robot_render_state_v1",
        "urdf_asset_id": "rehab_arm_urdf_current",
        "joint_names": joint_names,
        "positions": positions,
        "velocities": velocities,
        "fresh": fresh,
        "limit_clamped": limit_clamped,
    }


def build_wiring_health(device_id: str) -> dict[str, Any]:
    snapshot = _latest_payload(device_id, "command_center_snapshot")
    wiring = snapshot.get("wiring_health") if isinstance(snapshot.get("wiring_health"), dict) else {}
    if wiring:
        checks = [item for item in wiring.get("checks", []) if isinstance(item, dict)]
        for item in checks:
            if item.get("status") not in WIRING_STATUSES:
                item["status"] = "unknown"
        return {
            "schema_version": "wiring_health_v1",
            "robot_id": snapshot.get("robot_id", "rehab-arm-alpha"),
            "device_id": device_id,
            "overall": wiring.get("overall", "unknown"),
            "checks": checks,
            "control_boundary": "diagnostic_only_not_motion_permission",
        }

    motor_payload = _latest_payload(device_id, "motor_state")
    safety_payload = _latest_payload(device_id, "safety_state")
    camera_record = _device_latest(device_id, "camera_keyframe") or {}
    sensor_payload = _latest_payload(device_id, "sensor_state")
    now = time.time()
    motor_by_id = {_motor_key(motor.get("motor_id")): motor for motor in motor_payload.get("motors") or [] if isinstance(motor, dict)}
    checks: list[dict[str, Any]] = []
    for row in ARM_JOINT_MAP:
        motor = motor_by_id.get(row["motor_id"], {})
        if not row["wired"]:
            status = "not_wired"
            evidence = "wrist motor not installed or mapping pending"
            fresh_ms = None
        elif not motor:
            status = "missing"
            evidence = f"no motor {row['motor_id']} feedback in latest state"
            fresh_ms = None
        elif motor.get("fault"):
            status = "fault"
            evidence = str(motor.get("error_code") or "motor fault flag")
            fresh_ms = None
        else:
            ts_unix = float(motor.get("ts_unix") or motor_payload.get("ts_unix") or 0)
            fresh_ms = int(max(0, (now - ts_unix) * 1000)) if ts_unix else None
            status = "ok" if fresh_ms is not None and fresh_ms <= 1000 else "stale"
            evidence = f"motor {row['motor_id']} feedback"
        checks.append({"channel": f"motor_{row['motor_id']}_{row['urdf_joint']}", "status": status, "fresh_ms": fresh_ms, "evidence": evidence})

    heartbeat_age = safety_payload.get("heartbeat_age_ms")
    checks.append({
        "channel": "m33_heartbeat",
        "status": "ok" if isinstance(heartbeat_age, int) and heartbeat_age <= 500 else "stale" if heartbeat_age is not None else "unknown",
        "fresh_ms": heartbeat_age,
        "evidence": "M33 safety_state_v1 heartbeat_age_ms",
    })
    checks.append({
        "channel": "c8t6_emg_can",
        "status": "ok" if sensor_payload.get("emg") else "missing",
        "fresh_ms": None,
        "evidence": "C8T6 0x7C2/0x7C3 EMG summary",
    })
    checks.append({
        "channel": "camera_keyframe",
        "status": "ok" if camera_record else "missing",
        "fresh_ms": int(max(0, (now - float(camera_record.get("ts_unix") or 0)) * 1000)) if camera_record.get("ts_unix") else None,
        "evidence": "camera_keyframe_v1 latest upload",
    })
    checks.append({"channel": "voice_input", "status": "unknown", "fresh_ms": None, "evidence": "voice_capture_v1 optional input"})
    bad = [item for item in checks if item["status"] in {"stale", "missing", "fault"}]
    return {
        "schema_version": "wiring_health_v1",
        "robot_id": safety_payload.get("robot_id") or motor_payload.get("robot_id") or "rehab-arm-alpha",
        "device_id": device_id,
        "overall": "degraded" if bad else "ok",
        "checks": checks,
        "control_boundary": "diagnostic_only_not_motion_permission",
    }


def build_safety_status(device_id: str) -> dict[str, Any]:
    payload = _latest_payload(device_id, "safety_state")
    snapshot = _latest_payload(device_id, "command_center_snapshot")
    snap_safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}
    source = payload or snap_safety
    return {
        "schema_version": "safety_state_v1",
        "robot_id": source.get("robot_id") or snapshot.get("robot_id") or "rehab-arm-alpha",
        "device_id": device_id,
        "state": source.get("state", "unknown"),
        "motion_allowed": bool(source.get("motion_allowed", False)),
        "control_mode": source.get("control_mode") or source.get("m33_mode") or "logging_only",
        "detail": source.get("detail") or source.get("fault_message") or "",
        "last_m33_status_seq": source.get("last_m33_status_seq"),
        "heartbeat_age_ms": source.get("heartbeat_age_ms"),
        "source": source.get("source") or "m33_can_0x322",
        "control_boundary": "safety_status_only_not_motion_permission",
    }


def build_command_center_snapshot(device_id: str, project_id: str | None = None) -> dict[str, Any]:
    latest = _device_latest(device_id, "command_center_snapshot") or {}
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
    if payload:
        return {
            **payload,
            "robot_render_state": build_robot_render_state(device_id),
            "safety": build_safety_status(device_id),
            "wiring_health": build_wiring_health(device_id),
            "control_boundary": "telemetry_snapshot_only_not_motion_permission",
        }
    safety = build_safety_status(device_id)
    return {
        "schema_version": "command_center_snapshot_v1",
        "ts_unix": time.time(),
        "robot_id": safety.get("robot_id", "rehab-arm-alpha"),
        "device_id": device_id,
        "project_id": project_id or "",
        "source": "server_mock_from_latest_telemetry",
        "profile": {"profile_id": "mock_readonly_profile", "mapping_version": "medical_arm_6dof_2026_06_08"},
        "robot_render_state": build_robot_render_state(device_id),
        "safety": safety,
        "wiring_health": build_wiring_health(device_id),
        "model_state": {
            "schema_version": "rehab_arm_model_state_v1",
            "model_results": [],
            "control_boundary": "model_suggestion_only_not_motion_permission",
        },
        "control_boundary": "telemetry_snapshot_only_not_motion_permission",
    }


def record_command_center_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    render = payload.get("robot_render_state") if isinstance(payload.get("robot_render_state"), dict) else {}
    names = render.get("joint_names") if isinstance(render.get("joint_names"), list) else []
    positions = render.get("positions") if isinstance(render.get("positions"), list) else []
    if names and positions and len(names) != len(positions):
        raise ValueError("robot_render_state.joint_names and positions must have equal length")
    record = telemetry_record("command_center_snapshot", payload)
    write_device_latest(record["device_id"], "command_center_snapshot", record)
    return {
        "ok": True,
        "schema_version": "command_center_snapshot_v1",
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "snapshot_id": f"ccs_{int(record['ts_unix'] * 1000)}",
        "joint_count": len(names),
        "control_boundary": "telemetry_snapshot_only_not_motion_permission",
    }


def record_camera_stream_offer(payload: dict[str, Any]) -> dict[str, Any]:
    payload = {
        **payload,
        "control_boundary": "camera_preview_only_not_motion_permission",
    }
    record = telemetry_record("camera_stream_offer", payload)
    write_device_latest(record["device_id"], "camera_stream_offer", record)
    return {
        "ok": True,
        "schema_version": "camera_stream_offer_v1",
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "camera_id": payload.get("camera_id"),
        "transport": payload.get("transport"),
        "control_boundary": "camera_preview_only_not_motion_permission",
    }


def _target_label(target: Any) -> str:
    if isinstance(target, dict):
        return _safe_text(target.get("label") or target.get("class_name") or target.get("name"), 120)
    return _safe_text(target, 120)


def _detection_count(detections: Any) -> int:
    if isinstance(detections, list):
        return len(detections)
    if isinstance(detections, dict):
        items = detections.get("items") or detections.get("detections") or detections.get("objects")
        return len(items) if isinstance(items, list) else len(detections)
    return 0


def record_stereo_vision_context(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("control_boundary") != "stereo_vision_context_only_not_motion_permission":
        raise ValueError("stereo vision context must stay perception-only")
    confidence = payload.get("confidence")
    if confidence is not None:
        try:
            payload["confidence"] = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            raise ValueError("confidence must be numeric") from None
    record = telemetry_record("stereo_vision_context", payload)
    write_device_latest(record["device_id"], "stereo_vision_context", record)
    return {
        "ok": True,
        "schema_version": "stereo_rgb_yolo_context_v1",
        "device_id": record["device_id"],
        "robot_id": record["robot_id"],
        "project_id": record.get("project_id") or "",
        "left_camera_id": payload.get("left_camera_id"),
        "right_camera_id": payload.get("right_camera_id"),
        "target_label": _target_label(payload.get("target_object")),
        "detection_count": _detection_count(payload.get("detections")),
        "estimated_depth_m": payload.get("estimated_depth_m"),
        "control_boundary": "stereo_vision_context_only_not_motion_permission",
    }


def build_camera_stream_offer(device_id: str) -> dict[str, Any]:
    record = _device_latest(device_id, "camera_stream_offer") or {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if payload:
        return {
            "schema_version": "camera_stream_offer_v1",
            "robot_id": payload.get("robot_id") or "rehab-arm-alpha",
            "device_id": device_id,
            "camera_id": payload.get("camera_id") or "front_rgb",
            "transport": payload.get("transport") or "webrtc_or_mjpeg",
            "max_fps": payload.get("max_fps") or 15,
            "max_width": payload.get("max_width") or 1280,
            "max_height": payload.get("max_height") or 720,
            "control_boundary": "camera_preview_only_not_motion_permission",
        }
    return {
        "schema_version": "camera_stream_offer_v1",
        "robot_id": "rehab-arm-alpha",
        "device_id": device_id,
        "camera_id": "front_rgb",
        "transport": "webrtc_or_mjpeg",
        "max_fps": 15,
        "max_width": 1280,
        "max_height": 720,
        "control_boundary": "camera_preview_only_not_motion_permission",
    }


def record_voice_capture(device_id: str, fields: dict[str, str], audio_bytes: bytes) -> dict[str, Any]:
    transcript = fields.get("transcript") or "语音已接收，等待 ASR 服务接入"
    intent_label = fields.get("intent_label") or "voice_intent_pending"
    confidence = float(fields.get("confidence") or 0)
    payload = {
        "schema_version": "voice_capture_v1",
        "robot_id": fields.get("robot_id") or "rehab-arm-alpha",
        "device_id": device_id,
        "project_id": fields.get("project_id") or fields.get("projectId") or "",
        "source": fields.get("source") or "command_center_microphone",
        "audio_format": fields.get("audio_format") or "wav_pcm16",
        "sample_rate": int(fields.get("sample_rate") or 16000),
        "duration_ms": int(fields.get("duration_ms") or 0),
        "language": fields.get("language") or "zh-CN",
        "session_id": fields.get("session_id") or "",
        "sha256": sha256_bytes(audio_bytes),
        "size_bytes": len(audio_bytes),
        "control_boundary": "voice_input_only_not_motion_permission",
    }
    record = telemetry_record("voice_capture", payload)
    relay = {
        "schema_version": "voice_relay_v1",
        "transcript": transcript,
        "intent": {"label": intent_label, "confidence": confidence},
        "as_model_state": {
            "schema_version": "rehab_arm_model_state_v1",
            "model_results": [
                {
                    "model_id": "server_voice_asr_v1",
                    "model_version": "0.1.0",
                    "result_code": 1 if confidence > 0 else 0,
                    "label": intent_label,
                    "confidence": confidence,
                    "fresh": True,
                }
            ],
            "control_boundary": "model_suggestion_only_not_motion_permission",
        },
        "control_boundary": "voice_relay_only_not_motion_permission",
    }
    write_device_latest(device_id, "voice_capture", record)
    write_device_latest(device_id, "voice_relay", {**record, "record_type": "voice_relay", "payload": relay})
    return relay


def record_vla_task_request(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = set(payload.get("allowed_outputs") or [])
    forbidden = set(payload.get("forbidden_outputs") or [])
    if allowed & DANGEROUS_VLA_OUTPUTS:
        raise ValueError("VLA allowed_outputs contains forbidden low-level control output")
    if not DANGEROUS_VLA_OUTPUTS.issubset(forbidden):
        payload["forbidden_outputs"] = sorted(forbidden | DANGEROUS_VLA_OUTPUTS)
    request_record = telemetry_record("vla_task_request", payload)
    render = build_robot_render_state(request_record["device_id"])
    candidate_joint = next((name for name, is_fresh in zip(render.get("joint_names", []), render.get("fresh", [])) if is_fresh), "zhou_zongxiang_joint")
    response = {
        "schema_version": "vla_plan_candidate_v1",
        "plan_id": f"vla_plan_{int(time.time() * 1000)}",
        "summary": f"已生成 dry-run 候选：{payload.get('language_goal')}。该候选不是运动许可。",
        "candidate": {
            "type": "dry_run_joint_trajectory",
            "joint_names": [candidate_joint],
            "points": [{"positions": [0.1], "time_from_start_sec": 2.0}],
        },
        "requires": ["mujoco_dry_run_passed", "m33_motion_allowed_true", "human_confirmation"],
        "control_boundary": "vla_candidate_only_not_motion_permission",
    }
    record = telemetry_record("vla_plan_candidate", {**payload, "candidate_response": response})
    write_device_latest(record["device_id"], "vla_plan_candidate", record)
    return response


def record_xiaozhi_ws_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Record XiaoZhi-compatible voice WebSocket input/output for the command center."""
    record_type = str(payload.get("record_type") or "xiaozhi_ws_event")
    public_payload = {key: value for key, value in payload.items() if key != "record_type"}
    record = telemetry_record(record_type, public_payload)
    if record_type in {"xiaozhi_ws_input", "xiaozhi_ws_reply", "xiaozhi_ws_tts"}:
        session_record = _device_latest(record["device_id"], "xiaozhi_session") or {}
        session_payload = dict(session_record.get("payload") or {}) if isinstance(session_record, dict) else {}
        current_payload = dict(public_payload)

        event = str(current_payload.get("event") or "").strip()
        if record_type == "xiaozhi_ws_input" and event == "audio_frame":
            session_payload.update(
                {
                    "schema_version": "xiaozhi_session_v1",
                    "event": "audio_frame",
                    "ui_state": "listening",
                    "last_error": "",
                    "audio_bytes": int(current_payload.get("audio_bytes") or 0),
                    "audio_duration_ms": int(current_payload.get("audio_duration_ms") or 0),
                    "audio_format": current_payload.get("audio_format") or "",
                    "official_audio_path": bool(current_payload.get("official_audio_path") or False),
                    "compatibility_mode": current_payload.get("compatibility_mode") or "",
                    "control_boundary": "xiaozhi_voice_relay_only_not_motion_permission",
                }
            )
        elif record_type == "xiaozhi_ws_input" and event in {"listen_start", "listen_detect", "listen_stop", "disconnect"}:
            current_asr_text = str(current_payload.get("asr_text") or "")
            if event == "listen_start":
                ui_state = "listening"
            elif event == "listen_detect":
                ui_state = "wake_detected"
            elif event == "listen_stop":
                ui_state = "thinking" if current_asr_text else "idle"
            else:
                ui_state = "offline"
            asr_error = current_payload.get("asr_error") if "asr_error" in current_payload else session_payload.get("asr_error")
            asr_error = asr_error or ""
            session_payload.update(
                {
                    "schema_version": "xiaozhi_session_v1",
                    "event": event,
                    "ui_state": ui_state,
                    "last_error": asr_error if event == "listen_stop" and asr_error and not current_payload.get("asr_text") else "",
                    "audio_bytes": int(current_payload.get("audio_bytes") or session_payload.get("audio_bytes") or 0),
                    "audio_duration_ms": int(current_payload.get("audio_duration_ms") or session_payload.get("audio_duration_ms") or 0),
                    "audio_format": current_payload.get("audio_format") or session_payload.get("audio_format") or "",
                    "asr_audio_format": current_payload.get("asr_audio_format") or session_payload.get("asr_audio_format") or current_payload.get("audio_format") or session_payload.get("audio_format") or "",
                    "official_audio_path": bool(current_payload.get("official_audio_path") or session_payload.get("official_audio_path") or False),
                    "compatibility_mode": current_payload.get("compatibility_mode") or session_payload.get("compatibility_mode") or "",
                    "asr_called": bool(current_payload.get("asr_called")) if "asr_called" in current_payload else bool(session_payload.get("asr_called") or False),
                    "asr_ok": bool(current_payload.get("asr_ok")) if "asr_ok" in current_payload else bool(session_payload.get("asr_ok") or False),
                    "asr_text": current_asr_text,
                    "asr_error": asr_error,
                    "transcript": current_asr_text,
                    "reply": "",
                    "kind": "",
                    "ok": False,
                    "entered_llm": bool(current_payload.get("entered_llm") or False),
                    "entered_tts": bool(current_payload.get("entered_tts") or False),
                    "control_boundary": "xiaozhi_voice_relay_only_not_motion_permission",
                }
            )
        elif record_type == "xiaozhi_ws_reply":
            session_payload.update(
                {
                    "schema_version": "xiaozhi_session_v1",
                    "event": "reply",
                    "ui_state": "thinking",
                    "last_error": "",
                    "kind": current_payload.get("kind") or session_payload.get("kind") or "none",
                    "reply": current_payload.get("reply") or session_payload.get("reply") or "",
                    "transcript": current_payload.get("transcript") or session_payload.get("transcript") or "",
                    "audio_bytes": int(current_payload.get("audio_bytes") or session_payload.get("audio_bytes") or 0),
                    "audio_duration_ms": int(current_payload.get("audio_duration_ms") or session_payload.get("audio_duration_ms") or 0),
                    "audio_format": current_payload.get("audio_format") or session_payload.get("audio_format") or "",
                    "asr_audio_format": current_payload.get("asr_audio_format") or session_payload.get("asr_audio_format") or current_payload.get("audio_format") or session_payload.get("audio_format") or "",
                    "official_audio_path": bool(current_payload.get("official_audio_path") or session_payload.get("official_audio_path") or False),
                    "compatibility_mode": current_payload.get("compatibility_mode") or session_payload.get("compatibility_mode") or "",
                    "asr_called": bool(current_payload.get("asr_called") or session_payload.get("asr_called") or False),
                    "asr_ok": bool(current_payload.get("asr_ok") or session_payload.get("asr_ok") or False),
                    "asr_text": current_payload.get("asr_text") or session_payload.get("asr_text") or "",
                    "asr_error": current_payload.get("asr_error") or session_payload.get("asr_error") or "",
                    "entered_llm": bool(current_payload.get("entered_llm") or session_payload.get("entered_llm") or False),
                    "entered_tts": bool(current_payload.get("entered_tts") or session_payload.get("entered_tts") or False),
                    "control_boundary": "xiaozhi_voice_relay_only_not_motion_permission",
                }
            )
        elif record_type == "xiaozhi_ws_tts":
            has_recognized_text = bool(str(session_payload.get("transcript") or session_payload.get("asr_text") or "").strip())
            event_name = "tts" if has_recognized_text else str(session_payload.get("event") or "reply")
            tts_error = current_payload.get("error") or session_payload.get("error") or ""
            tts_ok = bool(current_payload.get("ok") or session_payload.get("ok") or False)
            if tts_ok and int(current_payload.get("audio_bytes") or session_payload.get("audio_bytes") or 0) > 0:
                ui_state = "speaking"
                last_error = ""
            elif tts_error:
                ui_state = "error"
                last_error = tts_error
            else:
                ui_state = "idle"
                last_error = ""
            session_payload.update(
                {
                    "schema_version": "xiaozhi_session_v1",
                    "event": event_name,
                    "ui_state": ui_state,
                    "ok": tts_ok,
                    "provider_configured": bool(current_payload.get("provider_configured") or session_payload.get("provider_configured") or False),
                    "audio_bytes": int(current_payload.get("audio_bytes") or session_payload.get("audio_bytes") or 0),
                    "sent_frames": int(current_payload.get("sent_frames") or session_payload.get("sent_frames") or 0),
                    "sent_bytes": int(current_payload.get("sent_bytes") or session_payload.get("sent_bytes") or 0),
                    "audio_format": current_payload.get("audio_format") or session_payload.get("audio_format") or "",
                    "error": tts_error,
                    "last_error": last_error,
                    "control_boundary": "xiaozhi_voice_relay_only_not_motion_permission",
                }
            )
        else:
            session_payload.update(current_payload)
        write_device_latest(record["device_id"], "xiaozhi_session", {"payload": session_payload, "record_type": "xiaozhi_session", "device_id": record["device_id"], "robot_id": record.get("robot_id"), "project_id": record.get("project_id"), "ts_unix": record.get("ts_unix")})
    return record


def _audio_param_int(audio_params: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(audio_params.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def _env_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def pcm_duration_ms(byte_length: int, audio_params: dict[str, Any]) -> int:
    """Return PCM duration from XiaoZhi audio params without trusting frame_duration."""
    sample_rate = _audio_param_int(audio_params, "sample_rate", 16000)
    channels = _audio_param_int(audio_params, "channels", 1)
    bits_per_sample = _audio_param_int(audio_params, "bits_per_sample", 16)
    bytes_per_second = sample_rate * channels * max(1, bits_per_sample // 8)
    if bytes_per_second <= 0:
        return 0
    return int((byte_length * 1000) / bytes_per_second)


def parse_xiaozhi_audio_frame(chunk: bytes, audio_params: dict[str, Any], protocol_version: int = 3) -> dict[str, Any]:
    """Parse official XiaoZhi binary audio frames.

    Official Protocol-Version 3 uses:
    [type uint8, reserved uint8, payload_size uint16 BE, payload].
    The payload is normally Opus. pcm_s16le is a temporary debug compatibility
    branch for the current M55 board and must not be treated as the official path.
    """
    if protocol_version != 3:
        return {
            "binary_protocol": f"xiaozhi_v{protocol_version}_raw_audio",
            "frame_type": None,
            "reserved": None,
            "payload_size": len(chunk),
            "payload": chunk,
            "header_bytes": 0,
            "parse_error": "",
        }
    if len(chunk) < 4:
        return {
            "binary_protocol": "xiaozhi_v3",
            "frame_type": None,
            "reserved": None,
            "payload_size": 0,
            "payload": chunk,
            "header_bytes": 0,
            "parse_error": "v3_frame_too_short",
        }
    frame_type = int(chunk[0])
    reserved = int(chunk[1])
    payload_size = int.from_bytes(chunk[2:4], "big")
    available = max(0, len(chunk) - 4)
    audio_format = _env_text(audio_params.get("format")).lower()
    if audio_format == "pcm_s16le" and (frame_type != 0 or reserved != 0 or payload_size > available):
        return {
            "binary_protocol": "xiaozhi_v3_compat_raw_pcm",
            "frame_type": None,
            "reserved": None,
            "payload_size": len(chunk),
            "payload": chunk,
            "header_bytes": 0,
            "parse_error": "compat_raw_pcm_without_v3_header",
        }
    if payload_size > available:
        payload = chunk[4:]
        parse_error = f"payload_size_exceeds_available:{payload_size}>{available}"
    else:
        payload = chunk[4 : 4 + payload_size]
        parse_error = ""
    return {
        "binary_protocol": "xiaozhi_v3",
        "frame_type": frame_type,
        "reserved": reserved,
        "payload_size": payload_size,
        "payload": payload,
        "header_bytes": 4,
        "parse_error": parse_error,
    }


def _pcm_s16le_to_wav_bytes(pcm_bytes: bytes, audio_params: dict[str, Any]) -> bytes:
    sample_rate = _audio_param_int(audio_params, "sample_rate", 16000)
    channels = _audio_param_int(audio_params, "channels", 1)
    bits_per_sample = _audio_param_int(audio_params, "bits_per_sample", 16)
    sample_width = max(1, bits_per_sample // 8)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buffer.getvalue()


def _prepare_pcm_s16le_for_asr(pcm_bytes: bytes, audio_params: dict[str, Any]) -> tuple[bytes, dict[str, int | bool]]:
    sample_rate = _audio_param_int(audio_params, "sample_rate", 16000)
    channels = _audio_param_int(audio_params, "channels", 1)
    frame_samples = max(1, sample_rate * 20 // 1000 * channels)
    frame_bytes = frame_samples * 2
    threshold_avg = 90
    threshold_peak = 600
    speech_start: int | None = None
    speech_end = 0
    peak = 0

    if len(pcm_bytes) < frame_bytes or (len(pcm_bytes) & 1):
        return pcm_bytes, {"trimmed": False, "gain_applied": False, "peak": 0}

    for offset in range(0, len(pcm_bytes) - 1, frame_bytes):
        frame = pcm_bytes[offset : min(len(pcm_bytes), offset + frame_bytes)]
        sample_count = len(frame) // 2
        if sample_count <= 0:
            continue
        frame_peak = 0
        frame_sum = 0
        for index in range(sample_count):
            sample = int.from_bytes(frame[index * 2 : index * 2 + 2], "little", signed=True)
            mag = abs(sample)
            frame_sum += mag
            if mag > frame_peak:
                frame_peak = mag
        peak = max(peak, frame_peak)
        if (frame_sum // sample_count) >= threshold_avg or frame_peak >= threshold_peak:
            if speech_start is None:
                speech_start = offset
            speech_end = offset + len(frame)

    if speech_start is None:
        return pcm_bytes, {"trimmed": False, "gain_applied": False, "peak": peak}

    pad_bytes = sample_rate * channels * 2 * 200 // 1000
    start = max(0, speech_start - pad_bytes)
    end = min(len(pcm_bytes), speech_end + pad_bytes)
    prepared = pcm_bytes[start:end]
    trimmed = (start != 0) or (end != len(pcm_bytes))

    if 0 < peak < 5000:
        gain = min(8.0, 12000.0 / float(peak))
        output = bytearray()
        for index in range(len(prepared) // 2):
            sample = int.from_bytes(prepared[index * 2 : index * 2 + 2], "little", signed=True)
            scaled = int(sample * gain)
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            output.extend(scaled.to_bytes(2, "little", signed=True))
        prepared = bytes(output)
        return prepared, {"trimmed": trimmed, "gain_applied": True, "peak": peak}

    return prepared, {"trimmed": trimmed, "gain_applied": False, "peak": peak}


def _asr_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/audio/transcriptions"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/audio/transcriptions"
    return f"{cleaned}/v1/audio/transcriptions"


def _tts_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/audio/speech"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/audio/speech"
    return f"{cleaned}/v1/audio/speech"


def _qwen_tts_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    if "dashscope.aliyuncs.com/compatible-mode" in cleaned:
        cleaned = cleaned.replace("/compatible-mode/v1", "").replace("/compatible-mode", "")
    if cleaned.endswith("/api/v1/services/aigc/multimodal-generation/generation"):
        return cleaned
    return f"{cleaned}/api/v1/services/aigc/multimodal-generation/generation"


def _wav_bytes_to_pcm_s16le(wav_bytes: bytes) -> tuple[bytes, dict[str, int]]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        sample_rate = int(wav.getframerate())
        channels = int(wav.getnchannels())
        sample_width = int(wav.getsampwidth())
        frames = wav.readframes(wav.getnframes())
    if sample_width == 2:
        return frames, {"sample_rate": sample_rate, "channels": channels, "bits_per_sample": 16}
    if sample_width == 1:
        pcm = bytearray()
        for value in frames:
            sample = (int(value) - 128) << 8
            pcm.extend(int(sample).to_bytes(2, "little", signed=True))
        return bytes(pcm), {"sample_rate": sample_rate, "channels": channels, "bits_per_sample": 16}
    return b"", {"sample_rate": sample_rate, "channels": channels, "bits_per_sample": sample_width * 8}


def _pcm_s16le_mono_resample(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate:
        return pcm
    sample_count = len(pcm) // 2
    if sample_count <= 1:
        return pcm
    samples = [int.from_bytes(pcm[index * 2 : index * 2 + 2], "little", signed=True) for index in range(sample_count)]
    target_count = max(1, int(sample_count * target_rate / source_rate))
    output = bytearray()
    for index in range(target_count):
        source_pos = index * source_rate / target_rate
        left = min(sample_count - 1, int(source_pos))
        right = min(sample_count - 1, left + 1)
        ratio = source_pos - left
        value = int(samples[left] * (1.0 - ratio) + samples[right] * ratio)
        output.extend(value.to_bytes(2, "little", signed=True))
    return bytes(output)


def _qwen_tts_audio_url(payload: dict[str, Any]) -> str:
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    audio = output.get("audio") if isinstance(output.get("audio"), dict) else {}
    return _env_text(audio.get("url") or output.get("audio_url") or payload.get("audio_url"))


def _download_audio_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def _post_qwen_asr_flash(settings: Any, api_key: str, base_url: str, model: str, wav_bytes: bytes) -> dict[str, Any]:
    url = _relay_chat_url(base_url)
    if not url:
        return {"ok": False, "called": False, "text": "", "error": "asr_base_url_not_configured"}
    data_uri = "data:audio/wav;base64," + base64.b64encode(wav_bytes).decode("ascii")
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_uri},
                    }
                ],
            }
        ],
        "asr_options": {"enable_itn": False},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        return {"ok": False, "called": True, "text": "", "error": f"asr_http_error:{exc.code}:{detail}"}
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "called": True, "text": "", "error": f"asr_call_failed:{type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "called": True, "text": "", "error": "asr_response_not_json"}
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    text = _safe_text(content, 600)
    meaningful = _is_meaningful_asr_text(text)
    return {
        "ok": meaningful,
        "called": True,
        "text": text if meaningful else "",
        "raw_text": text,
        "error": "" if meaningful else "asr_empty_or_punctuation",
        "provider": settings.rehab_arm_xiaozhi_asr_provider.strip() or "qwen",
        "model": model,
    }


def transcribe_xiaozhi_pcm(audio_bytes: bytes, audio_params: dict[str, Any]) -> dict[str, Any]:
    """Transcribe XiaoZhi PCM through a server-side ASR provider if configured.

    The device never receives provider credentials. When ASR is not configured,
    the caller still gets a visible diagnostic object so the WebSocket does not
    silently end at listen stop.
    """
    settings = get_settings()
    if not audio_bytes:
        return {"ok": False, "called": False, "text": "", "error": "no_audio"}
    api_key = _env_text(settings.rehab_arm_xiaozhi_asr_api_key) or _env_text(settings.rehab_arm_model_relay_api_key)
    base_url = _env_text(settings.rehab_arm_xiaozhi_asr_base_url) or _env_text(settings.rehab_arm_model_relay_base_url)
    model = _env_text(settings.rehab_arm_xiaozhi_asr_model)
    external_enabled = bool(settings.rehab_arm_xiaozhi_asr_external_enabled and api_key and base_url and model)
    if not external_enabled:
        return {
            "ok": False,
            "called": False,
            "text": "",
            "error": "asr_not_configured",
            "provider_configured": bool(api_key and base_url and model),
        }
    url = _asr_url(base_url)
    if not url:
        return {"ok": False, "called": False, "text": "", "error": "asr_base_url_not_configured"}
    prepared_audio, asr_audio_prep = _prepare_pcm_s16le_for_asr(audio_bytes, audio_params)
    wav_bytes = _pcm_s16le_to_wav_bytes(prepared_audio, audio_params)
    if model.lower().startswith("qwen3-asr-flash"):
        result = _post_qwen_asr_flash(settings, api_key, base_url, model, wav_bytes)
        result["asr_audio_prep"] = asr_audio_prep
        result["prepared_audio_bytes"] = len(prepared_audio)
        return result
    boundary = f"----rehab-xiaozhi-asr-{int(time.time() * 1000)}"
    parts = [
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="model"\r\n\r\n'
            f"{model}\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="xiaozhi.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8"),
        wav_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "called": True, "text": "", "error": f"asr_call_failed:{type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "called": True, "text": "", "error": "asr_response_not_json"}
    text = _safe_text(data.get("text") or data.get("transcript") or data.get("result") or "", 600)
    meaningful = _is_meaningful_asr_text(text)
    return {
        "ok": meaningful,
        "called": True,
        "text": text if meaningful else "",
        "raw_text": text,
        "error": "" if meaningful else "asr_empty_or_punctuation",
        "provider": settings.rehab_arm_xiaozhi_asr_provider.strip() or settings.rehab_arm_model_relay_provider.strip() or "openai_compatible_asr",
        "model": model,
        "asr_audio_prep": asr_audio_prep,
        "prepared_audio_bytes": len(prepared_audio),
    }


def _decode_xiaozhi_opus_packets(audio_packets: list[bytes], audio_params: dict[str, Any]) -> dict[str, Any]:
    if not audio_packets:
        return {"ok": False, "pcm": b"", "error": "no_opus_packets", "packet_count": 0}
    sample_rate = _audio_param_int(audio_params, "sample_rate", 16000)
    channels = _audio_param_int(audio_params, "channels", 1)
    frame_duration = _audio_param_int(audio_params, "frame_duration", 60)
    frame_size = max(1, sample_rate * frame_duration // 1000)
    try:
        import opuslib  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 - optional runtime dependency diagnostic.
        return {
            "ok": False,
            "pcm": b"",
            "error": f"opus_decoder_unavailable:{type(exc).__name__}",
            "packet_count": len(audio_packets),
        }
    try:
        decoder = opuslib.Decoder(sample_rate, channels)
        pcm = bytearray()
        for packet in audio_packets:
            if not packet:
                continue
            pcm.extend(decoder.decode(packet, frame_size, decode_fec=False))
    except Exception as exc:  # noqa: BLE001 - expose decode failures without crashing the WebSocket.
        return {
            "ok": False,
            "pcm": b"",
            "error": f"opus_decode_failed:{type(exc).__name__}",
            "packet_count": len(audio_packets),
        }
    return {
        "ok": bool(pcm),
        "pcm": bytes(pcm),
        "error": "" if pcm else "opus_decode_empty_pcm",
        "packet_count": len(audio_packets),
        "sample_rate": sample_rate,
        "channels": channels,
        "frame_duration": frame_duration,
    }


def transcribe_xiaozhi_audio(audio_bytes: bytes, audio_params: dict[str, Any], audio_packets: list[bytes] | None = None) -> dict[str, Any]:
    audio_format = _env_text(audio_params.get("format")).lower()
    if audio_format == "pcm_s16le":
        result = transcribe_xiaozhi_pcm(audio_bytes, audio_params)
        result["audio_format"] = "pcm_s16le"
        result["compatibility_mode"] = "debug_pcm_s16le_not_official_xiaozhi_audio"
        return result
    if audio_format == "opus":
        packets = audio_packets if audio_packets is not None else ([audio_bytes] if audio_bytes else [])
        decode_result = _decode_xiaozhi_opus_packets(packets, audio_params)
        if not decode_result.get("ok"):
            return {
                "ok": False,
                "called": False,
                "text": "",
                "error": str(decode_result.get("error") or "opus_decode_failed"),
                "audio_format": "opus",
                "official_audio_path": True,
                "opus_packet_count": int(decode_result.get("packet_count") or 0),
                "detail": "official XiaoZhi audio payload is Opus; install python opuslib plus system libopus on the server to decode before ASR",
            }
        pcm_params = {
            "format": "pcm_s16le",
            "sample_rate": int(decode_result.get("sample_rate") or _audio_param_int(audio_params, "sample_rate", 16000)),
            "channels": int(decode_result.get("channels") or _audio_param_int(audio_params, "channels", 1)),
            "bits_per_sample": 16,
            "frame_duration": int(decode_result.get("frame_duration") or _audio_param_int(audio_params, "frame_duration", 60)),
        }
        result = transcribe_xiaozhi_pcm(bytes(decode_result.get("pcm") or b""), pcm_params)
        result["audio_format"] = "opus"
        result["decoded_audio_format"] = "pcm_s16le"
        result["official_audio_path"] = True
        result["opus_packet_count"] = int(decode_result.get("packet_count") or len(packets))
        result["decoded_pcm_bytes"] = len(bytes(decode_result.get("pcm") or b""))
        return result
    return {
        "ok": False,
        "called": False,
        "text": "",
        "error": f"unsupported_audio_format:{audio_format or 'unknown'}",
        "audio_format": audio_format,
    }


def synthesize_xiaozhi_tts(text: str, audio_params: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    reply = _safe_text(text, 600)
    api_key = _env_text(settings.rehab_arm_xiaozhi_tts_api_key) or _env_text(settings.rehab_arm_model_relay_api_key)
    base_url = _env_text(settings.rehab_arm_xiaozhi_tts_base_url) or _env_text(settings.rehab_arm_model_relay_base_url)
    model = _env_text(settings.rehab_arm_xiaozhi_tts_model)
    voice = _env_text(settings.rehab_arm_xiaozhi_tts_voice) or "alloy"
    external_enabled = bool(settings.rehab_arm_xiaozhi_tts_external_enabled and api_key and base_url and model and reply)
    if not reply:
        return {"ok": False, "called": False, "error": "tts_empty_text", "audio": b""}
    if not external_enabled:
        return {
            "ok": False,
            "called": False,
            "error": "tts_not_configured",
            "provider_configured": bool(api_key and base_url and model),
            "audio": b"",
        }
    is_qwen_tts = "qwen" in model.lower() or _env_text(settings.rehab_arm_xiaozhi_tts_provider).lower() == "qwen"
    url = _qwen_tts_url(base_url) if is_qwen_tts else _tts_url(base_url)
    if not url:
        return {"ok": False, "called": False, "error": "tts_base_url_not_configured", "audio": b""}
    try:
        if is_qwen_tts:
            request = urllib.request.Request(
                url,
                data=json.dumps(
                    {
                        "model": model,
                        "input": {
                            "text": reply,
                            "voice": voice,
                        },
                        "parameters": {
                            "sample_rate": _audio_param_int(audio_params, "sample_rate", 16000),
                            "format": "wav",
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_json = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                return {"ok": False, "called": True, "error": "tts_response_not_json", "audio": b""}
            audio_url = _qwen_tts_audio_url(payload)
            if not audio_url:
                return {"ok": False, "called": True, "error": "tts_audio_url_missing", "audio": b""}
            raw_audio = _download_audio_bytes(audio_url)
        else:
            request = urllib.request.Request(
                url,
                data=json.dumps(
                    {"model": model, "voice": voice, "input": reply, "response_format": "wav"},
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "called": True, "error": f"tts_http_error:{exc.code}:{detail}", "audio": b""}
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "called": True, "error": f"tts_call_failed:{type(exc).__name__}", "audio": b""}
    if not raw_audio.startswith(b"RIFF"):
        return {"ok": False, "called": True, "error": "tts_response_not_wav", "audio": b""}
    try:
        pcm, params = _wav_bytes_to_pcm_s16le(raw_audio)
    except wave.Error:
        return {"ok": False, "called": True, "error": "tts_wav_decode_failed", "audio": b""}
    expected_rate = _audio_param_int(audio_params, "sample_rate", 16000)
    expected_channels = _audio_param_int(audio_params, "channels", 1)
    if params.get("channels") != expected_channels:
        return {
            "ok": False,
            "called": True,
            "error": f"tts_audio_channels_mismatch:{params.get('channels')}ch",
            "audio": b"",
            "audio_params": params,
        }
    resampled = False
    if params.get("sample_rate") != expected_rate and expected_channels == 1:
        pcm = _pcm_s16le_mono_resample(pcm, int(params.get("sample_rate") or 0), expected_rate)
        params = {**params, "sample_rate": expected_rate}
        resampled = True
    if len(pcm) < XIAOZHI_MIN_AUDIBLE_TTS_PCM_BYTES:
        return {
            "ok": False,
            "called": True,
            "error": f"tts_audio_too_short:{len(pcm)}<{XIAOZHI_MIN_AUDIBLE_TTS_PCM_BYTES}",
            "audio": b"",
            "audio_format": "pcm_s16le",
            "audio_params": params,
            "provider_configured": True,
            "provider": settings.rehab_arm_xiaozhi_tts_provider.strip() or settings.rehab_arm_model_relay_provider.strip() or "openai_compatible_tts",
            "model": model,
            "voice": voice,
            "control_boundary": "tts_feedback_only_not_motion_permission",
        }
    return {
        "ok": bool(pcm),
        "called": True,
        "error": "" if pcm else "tts_empty_audio",
        "audio": pcm,
        "audio_format": "pcm_s16le",
        "resampled": resampled,
        "provider_configured": True,
        "provider": settings.rehab_arm_xiaozhi_tts_provider.strip() or settings.rehab_arm_model_relay_provider.strip() or "openai_compatible_tts",
        "model": model,
        "voice": voice,
        "control_boundary": "tts_feedback_only_not_motion_permission",
    }


def _contains_dangerous_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in DANGEROUS_VLA_OUTPUTS:
                return True
            if _contains_dangerous_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_dangerous_key(item) for item in value)
    return False


def _safe_text(value: Any, limit: int = 800) -> str:
    text = str(value or "").strip()
    for token in DANGEROUS_VLA_OUTPUTS:
        text = re.sub(re.escape(token), "[blocked_low_level_field]", text, flags=re.IGNORECASE)
    return text[:limit]


def _is_meaningful_asr_text(text: str) -> bool:
    normalized = _safe_text(text, 80)
    if not normalized:
        return False
    return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in normalized)


def _relay_classification(payload: dict[str, Any], external_payload: dict[str, Any], external_ok: bool) -> dict[str, Any]:
    raw_type = str(external_payload.get("classification") or external_payload.get("type") or "").strip().lower()
    prompt = str(payload.get("prompt") or "").strip()
    input_type = str(payload.get("input_type") or "").strip()
    if raw_type not in {"daily_chat", "vla_command", "none"}:
        if input_type == "vla_language_from_voice" and re.search(r"抬|训练|康复|开始|暂停|停止|辅助|手臂|肩|肘|腕", prompt):
            raw_type = "vla_command"
        elif not prompt or len(prompt) <= 1:
            raw_type = "none"
        elif re.search(r"你好|天气|聊天|谢谢|介绍", prompt):
            raw_type = "daily_chat"
        else:
            raw_type = "vla_command" if input_type in {"vla_context", "high_level_task"} else "none"
    try:
        confidence = float(external_payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if not external_ok and raw_type == "vla_command":
        confidence = max(confidence, 0.55)
    return {
        "schema_version": "model_relay_classification_v1",
        "type": raw_type,
        "confidence": min(1.0, max(0.0, confidence)),
        "reason": _safe_text(external_payload.get("reason") or external_payload.get("summary") or prompt, 240),
        "control_boundary": "classification_only_not_motion_permission",
    }


def _external_operator_reply(external_payload: dict[str, Any], fallback: str = "") -> str:
    return _safe_text(
        external_payload.get("operator_facing_reply")
        or external_payload.get("reply")
        or external_payload.get("answer")
        or external_payload.get("message")
        or external_payload.get("summary")
        or external_payload.get("high_level_task")
        or external_payload.get("detail")
        or fallback,
        800,
    )


def _vla_language_gate(classification: dict[str, Any], payload: dict[str, Any], relay_id: str) -> dict[str, Any]:
    kind = str(classification.get("type") or "none").strip()
    participates = kind == "vla_command"
    if participates:
        route = "vla_l_input"
        detail = "classified_as_vla_command_use_as_language_input_only"
    elif kind == "daily_chat":
        route = "daily_chat_only"
        detail = "daily_chat_not_part_of_vla_language_input"
    else:
        route = "no_vla_input"
        detail = "no_rehab_vla_command_detected"
    return {
        "schema_version": "vla_language_gate_v1",
        "gate_id": f"vla_l_gate_{relay_id}",
        "input_type": payload.get("input_type"),
        "classification_type": kind,
        "participates_in_vla_l": participates,
        "route": route,
        "detail": detail,
        "control_boundary": "language_gate_only_not_motion_permission",
    }


def _latest_camera_payload(device_id: str) -> dict[str, Any]:
    stereo_record = _device_latest(device_id, "stereo_vision_context") or {}
    stereo_payload = stereo_record.get("payload") if isinstance(stereo_record.get("payload"), dict) else {}
    if isinstance(stereo_payload, dict) and stereo_payload:
        return stereo_payload
    record = _device_latest(device_id, "camera_keyframe") or {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return payload if isinstance(payload, dict) else {}


def _build_vla_language_context(relay_id: str, payload: dict[str, Any], classification: dict[str, Any], external_payload: dict[str, Any]) -> dict[str, Any]:
    context_refs = payload.get("context_refs") if isinstance(payload.get("context_refs"), dict) else {}
    audio_ref = context_refs.get("audio_ref") if isinstance(context_refs.get("audio_ref"), dict) else {}
    return {
        "schema_version": "vla_language_context_v1",
        "context_id": f"lang_ctx_{relay_id}",
        "source": "m55_voice_http" if payload.get("input_type") == "vla_language_from_voice" else "server_model_relay",
        "input_type": payload.get("input_type"),
        "transcript": _safe_text(payload.get("prompt"), 600),
        "intent_label": _safe_text(external_payload.get("label") or classification.get("type"), 120),
        "operator_facing_reply": _external_operator_reply(
            external_payload,
            "请再说一遍。" if classification.get("type") == "none" else "已理解，我会按高层建议处理，不会下发真实运动控制。",
        ),
        "classification": classification,
        "participates_in_vla_l": classification.get("type") == "vla_command",
        "audio_ref": audio_ref,
        "control_boundary": "vla_language_context_only_not_motion_permission",
    }


def _build_vla_vision_context(relay_id: str, device_id: str, camera_payload: dict[str, Any]) -> dict[str, Any]:
    if camera_payload.get("schema_version") == "stereo_rgb_yolo_context_v1":
        target_label = _target_label(camera_payload.get("target_object")) or "unknown"
        return {
            "schema_version": "vla_vision_context_v1",
            "context_id": f"vision_ctx_{relay_id}",
            "source": "stereo_rgb_yolo_context_v1",
            "scene_summary": _safe_text(camera_payload.get("scene_summary") or f"stereo RGB YOLO target: {target_label}", 500),
            "patient_visibility": _safe_text(camera_payload.get("vla_context") or "unknown", 240),
            "environment_constraints": "two RGB stereo depth is approximate; operator must verify target pose before motion",
            "camera_id": f"{camera_payload.get('left_camera_id') or 'left_rgb'}+{camera_payload.get('right_camera_id') or 'right_rgb'}",
            "target_label": target_label,
            "estimated_depth_m": camera_payload.get("estimated_depth_m"),
            "target_3d_camera_frame": camera_payload.get("target_3d_camera_frame"),
            "detection_count": _detection_count(camera_payload.get("detections")),
            "confidence": camera_payload.get("confidence"),
            "image_pair_ref": camera_payload.get("image_pair_ref") or {},
            "control_boundary": "vla_vision_context_only_not_motion_permission",
        }
    return {
        "schema_version": "vla_vision_context_v1",
        "context_id": f"vision_ctx_{relay_id}",
        "source": "camera_keyframe_v1",
        "scene_summary": _safe_text(camera_payload.get("scene_summary") or camera_payload.get("detection_summary") or "no fresh camera summary", 500),
        "patient_visibility": _safe_text(camera_payload.get("detection_summary") or "unknown", 240),
        "environment_constraints": _safe_text(camera_payload.get("vla_context") or "operator must verify patient posture and workspace before motion", 300),
        "camera_id": camera_payload.get("camera_id") or "front_rgb",
        "image_url": camera_payload.get("image_url") or f"/api/rehab-arm/v1/devices/{safe_part(device_id)}/camera/keyframes/latest/file",
        "control_boundary": "vla_vision_context_only_not_motion_permission",
    }


def _build_server_action_command(
    relay_id: str,
    payload: dict[str, Any],
    classification: dict[str, Any],
    language_context: dict[str, Any],
    vision_context: dict[str, Any],
    render: dict[str, Any],
    external_payload: dict[str, Any],
) -> dict[str, Any] | None:
    if classification.get("type") != "vla_command":
        return None
    label = _safe_text(external_payload.get("label") or "assist_slow_arm_raise", 80)
    natural_language = _safe_text(external_payload.get("summary") or payload.get("prompt"), 300)
    return {
        "schema_version": "server_to_nanopi_high_level_command_v1",
        "robot_id": payload.get("robot_id") or render.get("robot_id") or "rehab-arm-alpha",
        "device_id": payload.get("device_id"),
        "command_id": f"srv_action_{relay_id}",
        "source": "server_vla_action",
        "source_refs": {
            "vla_language_context_id": language_context["context_id"],
            "vla_vision_context_id": vision_context["context_id"],
            "robot_context_snapshot_id": f"robot_ctx_{relay_id}",
        },
        "action": {
            "kind": "rehab_training_request",
            "label": label,
            "natural_language": natural_language,
            "priority": "normal",
        },
        "requires_before_motion": [
            "active_profile_loaded",
            "wiring_state_checked",
            "safety_state_fresh",
            "mujoco_dry_run_required",
            "operator_confirmation_required",
            "m33_final_gate_required",
        ],
        "allowed_next_steps": [
            "vla_candidate_gate",
            "mujoco_dry_run_review",
            "operator_review",
        ],
        "control_boundary": "server_action_high_level_only_not_motion_permission",
    }


def _relay_chat_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/chat/completions"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


def _post_openai_compatible_chat(settings: Any, payload: dict[str, Any], render: dict[str, Any]) -> dict[str, Any]:
    url = _relay_chat_url(settings.rehab_arm_model_relay_base_url)
    if not url:
        return {"ok": False, "error": "base_url_not_configured"}
    model = settings.rehab_arm_model_relay_model.strip()
    if not model:
        return {"ok": False, "error": "model_not_configured"}
    system = (
        "You are a medical rehabilitation arm command-center relay. "
        "Return JSON only. Required keys: classification (daily_chat, vla_command, or none), "
        "operator_facing_reply, summary, label, confidence. "
        "For daily chat, answer naturally in operator_facing_reply. "
        "For rehab commands, summarize the safe high-level intent and optional dry_run_joint_trajectory_candidate. "
        "Never output CAN frames, motor current, motor torque, raw motor position/velocity, direct motor commands, "
        "or any safety override. All outputs are suggestions only and never motion permission."
    )
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema_version": payload.get("schema_version"),
                        "input_type": payload.get("input_type"),
                        "prompt": payload.get("prompt"),
                        "context_refs": payload.get("context_refs") or {},
                        "requested_outputs": payload.get("requested_outputs") or [],
                        "forbidden_outputs": sorted(DANGEROUS_VLA_OUTPUTS),
                        "robot_render_state": render,
                        "control_boundary": "model_relay_only_not_motion_permission",
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "authorization": f"Bearer {settings.rehab_arm_model_relay_api_key.strip()}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": f"external_call_failed:{type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "external_response_not_json"}
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    try:
        parsed = json.loads(content) if content else {}
    except json.JSONDecodeError:
        parsed = {"summary": content}
    if _contains_dangerous_key(parsed):
        return {"ok": False, "error": "external_response_blocked_low_level_output"}
    return {"ok": True, "payload": parsed}


def record_model_relay_request(payload: dict[str, Any]) -> dict[str, Any]:
    requested = set(payload.get("requested_outputs") or [])
    forbidden = set(payload.get("forbidden_outputs") or [])
    if requested & DANGEROUS_VLA_OUTPUTS:
        raise ValueError("model relay requested_outputs contains forbidden low-level control output")
    if not requested <= MODEL_RELAY_SAFE_OUTPUTS:
        unsupported = sorted(requested - MODEL_RELAY_SAFE_OUTPUTS)
        raise ValueError(f"model relay requested_outputs contains unsupported output: {', '.join(unsupported)}")
    if not DANGEROUS_VLA_OUTPUTS.issubset(forbidden):
        payload["forbidden_outputs"] = sorted(forbidden | DANGEROUS_VLA_OUTPUTS)

    settings = get_settings()
    request_record = telemetry_record("model_relay_request", payload)
    render = build_robot_render_state(request_record["device_id"])
    fresh_joints = [name for name, fresh in zip(render.get("joint_names", []), render.get("fresh", [])) if fresh]
    provider_configured = bool(settings.rehab_arm_model_relay_api_key.strip())
    external_enabled = bool(settings.rehab_arm_model_relay_external_enabled and provider_configured)
    provider_label = settings.rehab_arm_model_relay_provider.strip() or "server_model_relay"
    model_label = settings.rehab_arm_model_relay_model.strip() or "not_configured"
    prompt = str(payload.get("prompt") or "").strip()
    input_type = str(payload.get("input_type") or "high_level_task").strip()
    external_result = (
        _post_openai_compatible_chat(settings, payload, render)
        if external_enabled
        else {"ok": False, "error": "external_disabled_or_unconfigured"}
    )
    relay_id = f"model_relay_{int(time.time() * 1000)}"
    external_payload = external_result.get("payload") if external_result.get("ok") and isinstance(external_result.get("payload"), dict) else {}
    external_summary = _safe_text(external_payload.get("summary") or external_payload.get("high_level_task"), 800)
    external_reply = _external_operator_reply(external_payload, external_summary)
    external_label = _safe_text(external_payload.get("label") or input_type, 120)
    try:
        external_confidence = float(external_payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        external_confidence = 0.0
    external_confidence = min(1.0, max(0.0, external_confidence))
    summary = (
        "服务端模型中转已接收请求；当前返回安全建议外壳，不是运动许可。"
        if not external_enabled
        else external_summary or external_reply or "服务端模型中转已接收请求；外部模型调用已经过服务端安全输出过滤。"
    )
    classification = _relay_classification(payload, external_payload, bool(external_result.get("ok")))
    language_gate = _vla_language_gate(classification, payload, relay_id)
    camera_payload = _latest_camera_payload(request_record["device_id"])
    language_context = _build_vla_language_context(relay_id, payload, classification, external_payload)
    vision_context = _build_vla_vision_context(relay_id, request_record["device_id"], camera_payload)
    server_action_command = _build_server_action_command(
        relay_id,
        payload,
        classification,
        language_context,
        vision_context,
        render,
        external_payload,
    )
    response = {
        "schema_version": "model_relay_response_v1",
        "relay_id": relay_id,
        "provider": {
            "provider_id": provider_label,
            "model": model_label,
            "configured": provider_configured,
            "external_call_enabled": external_enabled,
            "external_call_ok": bool(external_result.get("ok")),
            "external_call_error": "" if external_result.get("ok") else str(external_result.get("error") or ""),
            "api_key_exposed_to_device": False,
        },
        "input_type": input_type,
        "classification": classification,
        "vla_language_gate": language_gate,
        "operator_facing_reply": language_context["operator_facing_reply"],
        "vla_language_context": language_context,
        "vla_vision_context": vision_context,
        "server_action_command": server_action_command,
        "summary": summary,
        "suggestion": {
            "schema_version": "rehab_arm_model_state_v1",
            "model_results": [
                {
                    "model_id": "server_model_relay_guard",
                    "model_version": "0.1.0",
                    "result_code": 1 if external_result.get("ok") else 0,
                    "label": external_label,
                    "confidence": external_confidence,
                    "fresh": True,
                    "detail": external_summary or external_reply or prompt[:240],
                }
            ],
            "control_boundary": "model_suggestion_only_not_motion_permission",
        },
        "vla_plan_candidate": {
            "schema_version": "vla_plan_candidate_v1",
            "candidate": {
                "type": "dry_run_joint_trajectory_candidate",
                "joint_names": fresh_joints[:6],
                "points": [],
                "candidate_only_not_motion_permission": True,
            },
            "requires": ["mujoco_dry_run_passed", "m33_motion_allowed_true", "human_confirmation"],
            "control_boundary": "vla_candidate_only_not_motion_permission",
        },
        "blocked_outputs": sorted(DANGEROUS_VLA_OUTPUTS),
        "control_boundary": "model_relay_only_not_motion_permission",
    }
    record = telemetry_record("model_relay_response", {**payload, "relay_response": response})
    write_device_latest(record["device_id"], "model_relay_response", record)
    return response


def record_estop_request(payload: dict[str, Any]) -> dict[str, Any]:
    record = telemetry_record("estop_request", payload)
    ack = {
        "schema_version": "estop_ack_v1",
        "request_id": payload.get("request_id"),
        "accepted_by_gateway": True,
        "m33_ack": False,
        "state": "pending_m33_ack",
        "detail": "request queued to local safety path; emergency stop is not confirmed until M33 ack",
        "control_boundary": "not_safe_until_m33_ack",
    }
    write_device_latest(record["device_id"], "estop_request", record)
    write_device_latest(record["device_id"], "estop_ack", {**record, "record_type": "estop_ack", "payload": ack})
    return ack


def _record_project_id(record: dict[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return str(record.get("project_id") or payload.get("project_id") or payload.get("projectId") or "").strip()


def _record_field(record: dict[str, Any], *names: str) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    for source in (record, payload, manifest):
        for name in names:
            value = str(source.get(name) or "").strip()
            if value:
                return value
    return ""


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


def device_project_id(device_id: str) -> str:
    """Return the latest known project binding for a rehab-arm device."""
    latest_records = [
        _device_latest(device_id, "registration") or {},
        _device_latest(device_id, "command_center_snapshot") or {},
        _device_latest(device_id, "motor_state") or {},
        _device_latest(device_id, "sensor_state") or {},
        _device_latest(device_id, "safety_state") or {},
        _device_latest(device_id, "board_manifest") or {},
        _device_latest(device_id, "device_model") or {},
        _device_latest(device_id, "model_relay_response") or {},
        _device_latest(device_id, "stereo_vision_context") or {},
    ]
    return next(
        (
            record_project_id
            for record in latest_records
            for record_project_id in [_record_project_id(record)]
            if record and record_project_id
        ),
        "",
    )


def require_device_project_match(device_id: str, project_id: str) -> None:
    expected = str(project_id or "").strip()
    actual = device_project_id(device_id)
    if not expected:
        raise ValueError("project_id is required for model relay")
    if not actual:
        raise ValueError("device has no project binding; register the device before model relay")
    if actual != expected:
        raise ValueError("device does not belong to requested project")


def build_dashboard(project_id: str | None = None) -> dict[str, Any]:
    root = storage_root()
    project_filter = (project_id or "").strip()
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
        simulation_readiness = _device_latest(device_id, "simulation_readiness") or {}
        board_manifest = _device_latest(device_id, "board_manifest") or {}
        device_model = _device_latest(device_id, "device_model") or {}
        command_center_snapshot = _device_latest(device_id, "command_center_snapshot") or {}
        camera_stream_offer = _device_latest(device_id, "camera_stream_offer") or {}
        stereo_vision_context = _device_latest(device_id, "stereo_vision_context") or {}
        voice_relay = _device_latest(device_id, "voice_relay") or {}
        vla_plan_candidate = _device_latest(device_id, "vla_plan_candidate") or {}
        model_relay_response = _device_latest(device_id, "model_relay_response") or {}
        xiaozhi_session = _device_latest(device_id, "xiaozhi_session") or {}
        estop_ack = _device_latest(device_id, "estop_ack") or {}
        camera_keyframe = _device_latest(device_id, "camera_keyframe") or {}
        sync_status = _device_latest(device_id, "sync_status") or {}
        manifest = _device_latest(device_id, "manifest") or {}
        data_quality = build_data_quality_index(manifest)
        latest_records = [
            registration,
            motor_state,
            sensor_state,
            safety_state,
            simulation_readiness,
            board_manifest,
            camera_keyframe,
            sync_status,
            manifest,
            device_model,
            command_center_snapshot,
            camera_stream_offer,
            stereo_vision_context,
            voice_relay,
            vla_plan_candidate,
            model_relay_response,
            xiaozhi_session,
            estop_ack,
        ]
        device_project_id = next(
            (
                record_project_id
                for record in latest_records
                for record_project_id in [_record_project_id(record)]
                if record and record_project_id
            ),
            "",
        )
        if project_filter and device_project_id != project_filter:
            continue
        last_upload = max([float(item.get("ts_unix") or 0) for item in latest_records if item] or [0])
        safety_payload = safety_state.get("payload") if isinstance(safety_state.get("payload"), dict) else {}
        command_center_payload = command_center_snapshot.get("payload") if isinstance(command_center_snapshot.get("payload"), dict) else {}
        register_payload = registration.get("payload") if isinstance(registration.get("payload"), dict) else {}
        sync_payload = sync_status.get("payload") if isinstance(sync_status.get("payload"), dict) else {}
        computer_node_id = next(
            (
                value
                for record in latest_records
                for value in [_record_field(record, "computer_node_id", "computerNodeId", "runner_computer_node_id", "runnerComputerNodeId")]
                if record and value
            ),
            "",
        )
        runner_id = next(
            (
                value
                for record in latest_records
                for value in [_record_field(record, "runner_id", "runnerId")]
                if record and value
            ),
            "",
        )
        safety_status = build_safety_status(device_id)
        devices.append(
            {
                "device_id": device_id,
                "project_id": device_project_id,
                "robot_id": safe_part(
                    str(
                        register_payload.get("robot_id")
                        or command_center_payload.get("robot_id")
                        or safety_payload.get("robot_id")
                        or safety_state.get("robot_id")
                        or motor_state.get("robot_id")
                        or "unknown"
                    )
                ),
                "computer_node_id": computer_node_id,
                "runner_id": runner_id,
                "online_state": "online" if last_upload and now - last_upload <= 180 else "offline",
                "last_upload_ts_unix": last_upload or None,
                "safety_state": safety_status.get("state") or safety_payload.get("state", "ok" if not safety_state else "fault"),
                "motion_allowed": bool(safety_status.get("motion_allowed", False)),
                "current_session": sync_status.get("session_id") or "",
                "latest_upload_status": sync_payload.get("sync_status") or ("received" if last_upload else "none"),
                "latest_error": safety_payload.get("fault_message") or safety_payload.get("detail") or safety_status.get("detail") or "",
                "data_quality": data_quality,
                "command_center_snapshot": command_center_snapshot,
                "robot_render_state": build_robot_render_state(device_id),
                "camera_stream_offer": camera_stream_offer,
                "stereo_vision_context": stereo_vision_context,
                "wiring_health": build_wiring_health(device_id),
                "safety_status": safety_status,
                "voice_relay": voice_relay,
                "vla_plan_candidate": vla_plan_candidate,
                "model_relay_response": model_relay_response,
                "xiaozhi_session": xiaozhi_session,
                "estop_ack": estop_ack,
                "registration": registration,
                "camera_keyframe": camera_keyframe,
                "motor_state": motor_state,
                "sensor_state": sensor_state,
                "safety": safety_state,
                "simulation_readiness": simulation_readiness,
                "board_manifest": board_manifest,
                "device_model": device_model,
                "sync_status": sync_status,
                "manifest": manifest,
            }
        )
    return {
        "sync_role": "non_realtime_telemetry_data_asset_only",
        "safety_boundary": {
            "server_may_send": ["high_level_task", "data_request", "configuration_suggestion", "annotation_task", "vla_task_draft"],
            "server_must_not_send": ["can_frame", "motor_current", "motor_torque", "raw_motor_position", "raw_motor_velocity", "m33_safety_override"],
            "m33_final_authority": True,
        },
        "devices": devices,
        "recent_events": read_recent_events(32, project_id=project_filter or None),
    }
