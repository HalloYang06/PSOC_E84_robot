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
    append_jsonl(root / "events.jsonl", record)
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
    return {
        "ok": True,
        "accepted_sessions": accepted_sessions,
        "missing_files": [],
        "upload_urls": [],
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
    return {
        "ok": True,
        "session_id": safe_session_id,
        "sync_status": payload.get("sync_status", "received"),
        "file_name": payload.get("file_name", ""),
    }
