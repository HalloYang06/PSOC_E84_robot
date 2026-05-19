from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEVICE_CAPTURE_KINDS = {"robotics.capture.start", "robotics.capture.stop"}
MAX_CAPTURE_SECONDS = 3.0
MAX_CAPTURE_BYTES = 64_000
MAX_COMPLETION_NOTE_CHARS = 3800
MAX_SESSION_JOIN_SECONDS = 5.0
MAX_PREVIEW_POINTS = 160


@dataclass
class _CaptureSession:
    capture_id: str
    manifest_path: Path
    preview_path: Path
    workdir: Path
    payload: dict[str, Any]
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None
    status: str = "starting"
    error: str = ""
    sample_count: int = 0
    byte_count: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stopped_at: str = ""
    last_sample_at: str = ""


_SESSIONS: dict[str, _CaptureSession] = {}
_SESSIONS_LOCK = threading.Lock()


def is_device_capture_command(payload: dict[str, Any] | None) -> bool:
    return str((payload or {}).get("kind") or "").strip() in DEVICE_CAPTURE_KINDS


def execute_device_capture_command(
    payload: dict[str, Any],
    *,
    allow_hardware_access: bool,
    workdir: Path,
    repo_root: Path | None = None,
    git_push: bool = False,
) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip()
    if kind not in DEVICE_CAPTURE_KINDS:
        return _result(False, "failed", "不支持的采集请求", {"ok": False, "error": f"unsupported capture kind: {kind}"})

    capture_id = _safe_token(payload.get("capture_id"), "capture")
    project_id = _safe_token(payload.get("project_id"), "project")
    computer_node_id = _safe_token(payload.get("computer_node_id"), "computer")
    interface_id = _safe_token(payload.get("interface_id"), "interface")
    interface_kind = str(payload.get("interface_kind") or "").strip().lower()
    interface_name = str(payload.get("interface_name") or interface_id).strip()
    sample_hz = _safe_sample_hz(payload.get("sample_hz"))
    channels = _safe_channels(payload.get("channels"))
    capture_dir = workdir / "device-captures" / project_id / computer_node_id / interface_id / capture_id
    manifest_path = capture_dir / "manifest.json"
    preview_path = capture_dir / "preview.jsonl"

    session_key = _session_key(project_id, computer_node_id, interface_id, capture_id)

    if kind == "robotics.capture.start":
        capture_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema": "runner_device_capture_session_v2",
            "capture_id": capture_id,
            "project_id": project_id,
            "computer_node_id": computer_node_id,
            "interface_id": interface_id,
            "interface_name": interface_name,
            "interface_kind": interface_kind,
            "sample_hz": sample_hz,
            "channels": channels,
            "started_at": started_at,
            "status": "running" if allow_hardware_access else "prepared",
            "preview_file": _relative_to_workdir(preview_path, workdir),
            "capture_mode": "background_session",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        session = _CaptureSession(
            capture_id=capture_id,
            manifest_path=manifest_path,
            preview_path=preview_path,
            workdir=workdir,
            payload={**payload, "capture_id": capture_id, "sample_hz": sample_hz, "channels": channels},
            status="running" if allow_hardware_access else "prepared",
            started_at=started_at,
        )
        if allow_hardware_access:
            session.thread = threading.Thread(
                target=_run_capture_session,
                args=(session,),
                name=f"robotics-capture-{capture_id[:24]}",
                daemon=True,
            )
            session.thread.start()
        with _SESSIONS_LOCK:
            previous = _SESSIONS.get(session_key)
            if previous and previous.thread and previous.thread.is_alive():
                previous.stop_event.set()
            _SESSIONS[session_key] = session
        return _result(
            True,
            "completed",
            "采集会话已在目标电脑后台运行" if allow_hardware_access else "采集会话已登记，等待目标电脑开启硬件访问",
            {
                "ok": True,
                "kind": kind,
                "capture_id": capture_id,
                "status": session.status,
                "manifest": _relative_to_workdir(manifest_path, workdir),
                "preview": _relative_to_workdir(preview_path, workdir),
                "capture_mode": "background_session",
            },
        )

    if not allow_hardware_access:
        return _result(
            True,
            "failed",
            "目标电脑未开启硬件访问权限",
            {
                "ok": False,
                "kind": kind,
                "capture_id": capture_id,
                "error": "hardware access is disabled for this runner",
                "hint": "Start the runner with hardware access enabled on the target computer.",
            },
        )

    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_key, None)

    samples: list[dict[str, Any]] = _read_preview_samples(preview_path)
    if session:
        session.stop_event.set()
        if session.thread and session.thread.is_alive():
            session.thread.join(timeout=MAX_SESSION_JOIN_SECONDS)
        with session.lock:
            samples = _read_preview_samples(preview_path)
            capture_error = session.error
            byte_count = session.byte_count
            session_status = "captured" if session.sample_count else session.status
            started_at = session.started_at
    else:
        capture_dir.mkdir(parents=True, exist_ok=True)
        serial_port = _serial_port_from_interface(payload.get("interface_id"), payload.get("port"))
        capture_error = ""
        byte_count = 0
        started_at = ""
        session_status = "captured" if samples else "empty"
        if not samples:
            if _looks_like_can(interface_kind, str(payload.get("interface_id") or "")):
                can_result = _capture_can_preview(str(payload.get("interface_id") or ""), sample_hz=sample_hz)
                samples = can_result["samples"]
                capture_error = can_result["error"]
                byte_count = can_result["byte_count"]
                with preview_path.open("w", encoding="utf-8") as handle:
                    for sample in samples:
                        handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
            elif _looks_like_serial(interface_kind, str(payload.get("interface_id") or "")) and serial_port:
                serial_result = _capture_serial_preview(serial_port, sample_hz=sample_hz, baud_rate=_safe_baud_rate(payload.get("baud_rate")))
                samples = serial_result["samples"]
                capture_error = serial_result["error"]
                byte_count = serial_result["byte_count"]
                with preview_path.open("w", encoding="utf-8") as handle:
                    for sample in samples:
                        handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
            else:
                capture_error = "当前采集器支持串口和 SocketCAN 只读采样；USB/SPI-CAN/ROS 会按独立通道继续补齐。"

    stopped_at = datetime.now(timezone.utc).isoformat()
    preview_summary = _build_preview_summary(samples)
    preview_points = _build_preview_points(samples)
    manifest = {
        "schema": "runner_device_capture_result_v2",
        "capture_id": capture_id,
        "project_id": project_id,
        "computer_node_id": computer_node_id,
        "interface_id": interface_id,
        "interface_name": interface_name,
        "interface_kind": interface_kind,
        "sample_hz": sample_hz,
        "channels": channels,
        "started_at": started_at or payload.get("started_at") or "",
        "stopped_at": stopped_at,
        "status": "captured" if samples else session_status,
        "sample_count": len(samples),
        "byte_count": byte_count,
        "preview_summary": preview_summary,
        "preview_points": preview_points,
        "preview_file": _relative_to_workdir(preview_path, workdir),
        "error": capture_error,
        "capture_mode": "background_session" if session else "short_window_fallback",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sync_result = _sync_capture_to_repo(
        manifest_path=manifest_path,
        preview_path=preview_path,
        repo_root=repo_root,
        project_id=project_id,
        computer_node_id=computer_node_id,
        interface_id=interface_id,
        capture_id=capture_id,
        git_push=git_push,
    )
    local_cache = _cleanup_capture_cache_after_sync(capture_dir, sync_result)
    ok = bool(samples)
    return _result(
        True,
        "completed" if ok else "failed",
        "采集完成" if ok else "采集未读到样本",
        {
            "ok": ok,
            "kind": kind,
            "capture_id": capture_id,
            "sample_count": len(samples),
            "byte_count": byte_count,
            "preview_summary": preview_summary,
            "preview_points": preview_points,
            "manifest": _relative_to_workdir(manifest_path, workdir),
            "preview": _relative_to_workdir(preview_path, workdir),
            "error": capture_error,
            "capture_mode": manifest["capture_mode"],
            "repo_sync": sync_result,
            "local_cache": local_cache,
        },
    )


def _run_capture_session(session: _CaptureSession) -> None:
    payload = session.payload
    interface_kind = str(payload.get("interface_kind") or "").strip().lower()
    interface_id = str(payload.get("interface_id") or "").strip()
    serial_port = _serial_port_from_interface(interface_id, payload.get("port"))
    if _looks_like_can(interface_kind, interface_id):
        _run_can_capture_session(session)
        return
    if not (_looks_like_serial(interface_kind, interface_id) and serial_port):
        with session.lock:
            session.status = "unsupported"
            session.error = "当前后台采集器支持串口和 SocketCAN 只读采样；USB/SPI-CAN/ROS 会按独立通道继续补齐。"
            _update_session_manifest(session)
        return

    try:
        import serial  # type: ignore
    except Exception as exc:
        with session.lock:
            session.status = "failed"
            session.error = f"pyserial is not installed: {exc}"
            _update_session_manifest(session)
        return

    sample_hz = _safe_sample_hz(payload.get("sample_hz"))
    baud_rate = _safe_baud_rate(payload.get("baud_rate"))
    timeout = max(0.02, min(0.2, 1 / max(sample_hz, 1)))
    session.preview_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with serial.Serial(port=serial_port, baudrate=baud_rate, timeout=timeout) as ser:
            with session.preview_path.open("a", encoding="utf-8") as handle:
                while not session.stop_event.is_set() and session.byte_count < MAX_CAPTURE_BYTES:
                    chunk = ser.readline() or ser.read(256)
                    if not chunk:
                        continue
                    chunk_samples = _serial_chunk_samples(chunk, serial_port)
                    for sample in chunk_samples:
                        now = str(sample.get("t") or datetime.now(timezone.utc).isoformat())
                        handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                        with session.lock:
                            session.sample_count += 1
                            session.byte_count += int(sample.get("bytes") or 0)
                            session.last_sample_at = now
                            session.status = "capturing"
                    handle.flush()
                    if session.sample_count % max(8, min(100, sample_hz)) == 0:
                        with session.lock:
                            _update_session_manifest(session)
    except Exception as exc:
        with session.lock:
            session.status = "failed" if not session.sample_count else "captured_with_error"
            session.error = str(exc)
            _update_session_manifest(session)
        return

    with session.lock:
        session.stopped_at = datetime.now(timezone.utc).isoformat()
        if session.sample_count:
            session.status = "captured"
        elif not session.error:
            session.status = "empty"
            session.error = "serial port returned no data while the capture session was running"
        _update_session_manifest(session)


def _update_session_manifest(session: _CaptureSession) -> None:
    payload = session.payload
    manifest = {
        "schema": "runner_device_capture_session_v2",
        "capture_id": session.capture_id,
        "project_id": _safe_token(payload.get("project_id"), "project"),
        "computer_node_id": _safe_token(payload.get("computer_node_id"), "computer"),
        "interface_id": _safe_token(payload.get("interface_id"), "interface"),
        "interface_name": str(payload.get("interface_name") or payload.get("interface_id") or "").strip(),
        "interface_kind": str(payload.get("interface_kind") or "").strip().lower(),
        "sample_hz": _safe_sample_hz(payload.get("sample_hz")),
        "channels": _safe_channels(payload.get("channels")),
        "started_at": session.started_at,
        "stopped_at": session.stopped_at,
        "status": session.status,
        "sample_count": session.sample_count,
        "byte_count": session.byte_count,
        "last_sample_at": session.last_sample_at,
        "preview_file": _relative_to_workdir(session.preview_path, session.workdir),
        "error": session.error,
        "capture_mode": "background_session",
    }
    session.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _capture_serial_preview(port: str, *, sample_hz: int, baud_rate: int = 115200) -> dict[str, Any]:
    try:
        import serial  # type: ignore
    except Exception as exc:
        return {"samples": [], "byte_count": 0, "error": f"pyserial is not installed: {exc}"}

    timeout = max(0.02, min(0.2, 1 / max(sample_hz, 1)))
    deadline = time.time() + MAX_CAPTURE_SECONDS
    samples: list[dict[str, Any]] = []
    byte_count = 0
    try:
        with serial.Serial(port=port, baudrate=baud_rate, timeout=timeout) as ser:
            while time.time() < deadline and byte_count < MAX_CAPTURE_BYTES:
                chunk = ser.readline() or ser.read(256)
                if not chunk:
                    continue
                byte_count += len(chunk)
                samples.extend(_serial_chunk_samples(chunk, port))
                if len(samples) >= max(8, min(200, sample_hz)):
                    break
    except Exception as exc:
        return {"samples": samples, "byte_count": byte_count, "error": str(exc)}
    return {"samples": samples, "byte_count": byte_count, "error": "" if samples else "serial port returned no data in the short capture window"}


def _serial_chunk_samples(chunk: bytes, port: str) -> list[dict[str, Any]]:
    decoded = chunk.decode("utf-8", errors="replace")
    parts = [part.strip() for part in decoded.splitlines() if part.strip()]
    if not parts and decoded.strip():
        parts = [decoded.strip()]
    samples: list[dict[str, Any]] = []
    for part in parts:
        encoded = part.encode("utf-8", errors="replace")
        samples.append(
            {
                "t": datetime.now(timezone.utc).isoformat(),
                "port": port,
                "bytes": len(encoded),
                "text": part,
                "hex": encoded[:64].hex(" "),
            }
        )
    return samples


def _run_can_capture_session(session: _CaptureSession) -> None:
    payload = session.payload
    can_iface = _can_interface_from_interface(payload.get("interface_id"), payload.get("channel"))
    candump = shutil.which("candump")
    if not can_iface:
        with session.lock:
            session.status = "failed"
            session.error = "CAN interface is missing. Select a scanned SocketCAN interface such as can:can0."
            _update_session_manifest(session)
        return
    if not candump:
        with session.lock:
            session.status = "failed"
            session.error = "candump is not installed on this Linux runner. Install can-utils to enable SocketCAN capture."
            _update_session_manifest(session)
        return
    session.preview_path.parent.mkdir(parents=True, exist_ok=True)
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen([candump, "-L", can_iface], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        with session.preview_path.open("a", encoding="utf-8") as handle:
            while not session.stop_event.is_set() and session.byte_count < MAX_CAPTURE_BYTES:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.02)
                    continue
                raw = line.strip()
                sample_bytes = len(raw.encode("utf-8"))
                now = datetime.now(timezone.utc).isoformat()
                sample = {"t": now, "interface": can_iface, "text": raw, "bytes": sample_bytes, **_parse_candump_line(raw)}
                handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                handle.flush()
                with session.lock:
                    session.sample_count += 1
                    session.byte_count += sample_bytes
                    session.last_sample_at = now
                    session.status = "capturing"
                if session.sample_count % 50 == 0:
                    with session.lock:
                        _update_session_manifest(session)
    except Exception as exc:
        with session.lock:
            session.status = "failed" if not session.sample_count else "captured_with_error"
            session.error = str(exc)
            _update_session_manifest(session)
        return
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                proc.kill()

    with session.lock:
        session.stopped_at = datetime.now(timezone.utc).isoformat()
        if session.sample_count:
            session.status = "captured"
        elif not session.error:
            session.status = "empty"
            stderr = ""
            if proc and proc.stderr is not None:
                try:
                    stderr = proc.stderr.read().strip()
                except Exception:
                    stderr = ""
            session.error = stderr or "SocketCAN returned no frames while the capture session was running"
        _update_session_manifest(session)


def _capture_can_preview(interface_id: str, *, sample_hz: int) -> dict[str, Any]:
    can_iface = _can_interface_from_interface(interface_id, None)
    candump = shutil.which("candump")
    if not can_iface:
        return {"samples": [], "byte_count": 0, "error": "CAN interface is missing. Select a scanned SocketCAN interface such as can:can0."}
    if not candump:
        return {"samples": [], "byte_count": 0, "error": "candump is not installed on this Linux runner. Install can-utils to enable SocketCAN capture."}
    deadline = time.time() + MAX_CAPTURE_SECONDS
    samples: list[dict[str, Any]] = []
    byte_count = 0
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen([candump, "-L", can_iface], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        while time.time() < deadline and byte_count < MAX_CAPTURE_BYTES and len(samples) < max(8, min(200, sample_hz)):
            if proc.stdout is None:
                break
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
                continue
            raw = line.strip()
            sample_bytes = len(raw.encode("utf-8"))
            byte_count += sample_bytes
            samples.append({"t": datetime.now(timezone.utc).isoformat(), "interface": can_iface, "text": raw, "bytes": sample_bytes, **_parse_candump_line(raw)})
    except Exception as exc:
        return {"samples": samples, "byte_count": byte_count, "error": str(exc)}
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                proc.kill()
    return {"samples": samples, "byte_count": byte_count, "error": "" if samples else "SocketCAN returned no frames in the short capture window"}


def _build_preview_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    numeric: dict[str, list[float]] = {}
    for sample in samples:
        flattened = _flatten_numeric_sample(sample)
        for key, value in flattened.items():
            numeric.setdefault(key, []).append(value)
        text = str(sample.get("text") or "").strip()
        for key, value in _parse_numeric_text(text).items():
            numeric.setdefault(key, []).append(value)
    fields: dict[str, dict[str, float | int]] = {}
    for key, values in numeric.items():
        if not values:
            continue
        fields[key] = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "first": values[0],
            "last": values[-1],
        }
    return {
        "schema": "runner_device_capture_preview_summary_v1",
        "sample_count": len(samples),
        "numeric_field_count": len(fields),
        "numeric_fields": fields,
    }


def _build_preview_points(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"schema": "runner_device_capture_preview_points_v1", "sample_count": 0, "series": {}}
    step = max(1, len(samples) // MAX_PREVIEW_POINTS)
    selected = samples[::step][:MAX_PREVIEW_POINTS]
    series: dict[str, list[dict[str, float]]] = {}
    for index, sample in enumerate(selected):
        flattened = _flatten_numeric_sample(sample)
        text = str(sample.get("text") or "").strip()
        for key, value in _parse_numeric_text(text).items():
            flattened.setdefault(key, value)
        x = _sample_x_value(sample, index)
        for key, value in flattened.items():
            if key in {"bytes"}:
                continue
            series.setdefault(key, []).append({"x": x, "y": value})
    return {
        "schema": "runner_device_capture_preview_points_v1",
        "sample_count": len(samples),
        "point_count": sum(len(points) for points in series.values()),
        "series": series,
    }


def _sample_x_value(sample: dict[str, Any], fallback: int) -> float:
    for key in ("time", "t", "timestamp"):
        raw = sample.get(key)
        parsed = _parse_float(raw)
        if parsed is not None:
            return parsed
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
    return float(fallback)


def _flatten_numeric_sample(sample: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, raw in sample.items():
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int | float):
            values[str(key)] = float(raw)
        elif isinstance(raw, str) and key not in {"text", "hex", "data_hex", "can_id", "port", "interface"}:
            parsed = _parse_float(raw)
            if parsed is not None:
                values[str(key)] = parsed
    return values


def _parse_numeric_text(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    if not text:
        return values
    normalized = text.strip()
    if normalized.startswith("@sample,"):
        parts = normalized.split(",")[1:]
        for index, part in enumerate(parts):
            parsed = _parse_float(part)
            if parsed is not None:
                values[f"sample.{index}"] = parsed
        return values
    for token in normalized.replace(";", ",").split(","):
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        safe_key = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in key.strip()).strip("_")
        parsed = _parse_float(raw)
        if safe_key and parsed is not None:
            values[safe_key] = parsed
    return values


def _parse_float(value: Any) -> float | None:
    try:
        text_value = str(value).strip()
        if not text_value:
            return None
        return float(text_value)
    except Exception:
        return None


def _safe_token(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw).strip("-")
    return safe[:96] or fallback


def _safe_sample_hz(value: Any) -> int:
    try:
        sample_hz = int(float(str(value)))
    except Exception:
        sample_hz = 100
    return max(1, min(sample_hz, 2000))


def _safe_baud_rate(value: Any) -> int:
    try:
        baud_rate = int(float(str(value)))
    except Exception:
        baud_rate = 115200
    return max(300, min(baud_rate, 4_000_000))


def _safe_channels(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("，", ",").split(",")
    channels = [str(item).strip() for item in raw if str(item).strip()]
    return channels[:64] or ["time", "raw.text", "raw.hex"]


def _serial_port_from_interface(interface_id: Any, port: Any) -> str:
    explicit = str(port or "").strip()
    if explicit:
        return explicit
    raw = str(interface_id or "").strip()
    if raw.lower().startswith("serial:"):
        value = raw.split(":", 1)[1].strip()
        if value and "/" not in value and value.lower().startswith(("tty", "cu.")):
            return f"/dev/{value}"
        return value
    return ""


def _looks_like_serial(interface_kind: str, interface_id: str) -> bool:
    lowered = f"{interface_kind} {interface_id}".lower()
    return "serial" in lowered or "串口" in lowered or interface_id.lower().startswith("serial:")


def _looks_like_can(interface_kind: str, interface_id: str) -> bool:
    lowered = f"{interface_kind} {interface_id}".lower()
    return "socketcan" in lowered or interface_kind == "can" or interface_id.lower().startswith("can:")


def _can_interface_from_interface(interface_id: Any, channel: Any) -> str:
    explicit = str(channel or "").strip()
    if explicit:
        return explicit
    raw = str(interface_id or "").strip()
    if raw.lower().startswith("can:"):
        return raw.split(":", 1)[1].strip()
    return raw if raw.lower().startswith("can") else ""


def _parse_candump_line(line: str) -> dict[str, Any]:
    parts = line.split()
    frame = parts[-1] if parts else ""
    can_id = ""
    data = ""
    if "#" in frame:
        can_id, data = frame.split("#", 1)
    return {"can_id": can_id, "data_hex": data}


def _relative_to_workdir(path: Path, workdir: Path) -> str:
    try:
        return path.relative_to(workdir).as_posix()
    except ValueError:
        return path.name


def _session_key(project_id: str, computer_node_id: str, interface_id: str, capture_id: str) -> str:
    return "\n".join([project_id, computer_node_id, interface_id, capture_id])


def _read_preview_samples(preview_path: Path) -> list[dict[str, Any]]:
    if not preview_path.exists():
        return []
    samples: list[dict[str, Any]] = []
    try:
        with preview_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    samples.append(parsed)
    except OSError:
        return samples
    return samples


def _sync_capture_to_repo(
    *,
    manifest_path: Path,
    preview_path: Path,
    repo_root: Path | None,
    project_id: str,
    computer_node_id: str,
    interface_id: str,
    capture_id: str,
    git_push: bool,
) -> dict[str, Any]:
    repo_relative_dir = Path("data") / "device-captures" / project_id / computer_node_id / interface_id / capture_id
    repo_relative_manifest = (repo_relative_dir / "manifest.json").as_posix()
    repo_relative_preview = (repo_relative_dir / "preview.jsonl").as_posix()
    if repo_root is None:
        return {
            "ok": False,
            "status": "waiting_for_repo",
            "repo_relative_dir": repo_relative_dir.as_posix(),
            "message": "目标电脑未配置设备数据仓库工作副本，采集数据暂存在本机待同步缓存。",
        }
    root = repo_root.resolve()
    if not root.exists():
        return {
            "ok": False,
            "status": "repo_missing",
            "repo_relative_dir": repo_relative_dir.as_posix(),
            "message": "目标电脑配置的仓库工作副本不存在，采集数据暂存在本机待同步缓存。",
        }
    if not (root / ".git").exists():
        return {
            "ok": False,
            "status": "not_git_repo",
            "repo_relative_dir": repo_relative_dir.as_posix(),
            "message": "目标电脑配置的目录不是 Git 工作副本，采集数据暂存在本机待同步缓存。",
        }
    target_dir = root / repo_relative_dir
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest_path, root / repo_relative_manifest)
        if preview_path.exists() and preview_path.stat().st_size > 0:
            shutil.copy2(preview_path, root / repo_relative_preview)
        checksum = {
            "schema": "runner_device_capture_checksum_v1",
            "capture_id": capture_id,
            "files": [
                {"path": repo_relative_manifest, "bytes": (root / repo_relative_manifest).stat().st_size},
                {"path": repo_relative_preview, "bytes": (root / repo_relative_preview).stat().st_size if (root / repo_relative_preview).exists() else 0},
            ],
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        checksum_path = target_dir / "checksum-summary.json"
        checksum_path.write_text(json.dumps(checksum, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "ok": False,
            "status": "copy_failed",
            "repo_relative_dir": repo_relative_dir.as_posix(),
            "message": f"写入仓库工作副本失败：{exc}",
        }

    git_paths = [repo_relative_manifest, (repo_relative_dir / "checksum-summary.json").as_posix()]
    if (root / repo_relative_preview).exists() and (root / repo_relative_preview).stat().st_size > 0:
        git_paths.insert(1, repo_relative_preview)
    add = _run_git(root, ["add", "--", *git_paths])
    if not add["ok"]:
        return {
            "ok": False,
            "status": "git_add_failed",
            "repo_relative_dir": repo_relative_dir.as_posix(),
            "message": "采集文件已写入仓库工作副本，但登记到 Git 暂存区失败。",
            "git": add,
        }
    diff = _run_git(root, ["diff", "--cached", "--quiet", "--", *git_paths])
    committed = False
    commit_hash = ""
    if diff["returncode"] != 0:
        commit = _run_git(root, ["commit", "-m", f"Add device capture {capture_id}"])
        if not commit["ok"]:
            return {
                "ok": False,
                "status": "git_commit_failed",
                "repo_relative_dir": repo_relative_dir.as_posix(),
                "message": "采集文件已写入仓库工作副本，但提交失败，等待人工处理。",
                "git": commit,
            }
        committed = True
        rev = _run_git(root, ["rev-parse", "--short=12", "HEAD"])
        commit_hash = str(rev.get("stdout") or "").strip()
    push_result: dict[str, Any] | None = None
    if git_push and committed:
        push_result = _run_git(root, ["push"])
    status = "pushed" if push_result and push_result.get("ok") else "committed" if committed else "unchanged"
    if push_result and not push_result.get("ok"):
        status = "push_failed"
    return {
        "ok": status in {"pushed", "committed", "unchanged"},
        "status": status,
        "repo_relative_dir": repo_relative_dir.as_posix(),
        "manifest": repo_relative_manifest,
        "preview": repo_relative_preview if (root / repo_relative_preview).exists() and (root / repo_relative_preview).stat().st_size > 0 else "",
        "commit": commit_hash or None,
        "push_enabled": git_push,
        "message": "采集数据已写入仓库证据目录" if status != "push_failed" else "采集数据已提交本地仓库，但推送失败，等待重试或人工处理。",
        "push": push_result,
    }


def _cleanup_capture_cache_after_sync(capture_dir: Path, sync_result: dict[str, Any]) -> dict[str, Any]:
    status = str(sync_result.get("status") or "").strip()
    if status not in {"pushed", "committed", "unchanged"}:
        return {
            "status": "kept_for_retry",
            "message": "采集缓存保留在目标电脑，等待仓库同步或人工处理。",
        }
    try:
        shutil.rmtree(capture_dir)
    except FileNotFoundError:
        return {
            "status": "already_clean",
            "message": "采集缓存已清理。",
        }
    except Exception as exc:
        return {
            "status": "cleanup_failed",
            "message": f"采集数据已写入仓库证据目录，但本机缓存清理失败：{exc}",
        }
    return {
        "status": "cleaned",
        "message": "采集数据已写入仓库证据目录，本机临时缓存已清理。",
    }


def _run_git(cwd: Path, args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except Exception as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[:1200],
        "stderr": completed.stderr.strip()[:1200],
    }


def _result(handled: bool, result_status: str, title: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "handled": handled,
        "result_status": result_status,
        "note": _format_completion_note(title, result),
        "result": result,
    }


def _format_completion_note(title: str, result: dict[str, Any]) -> str:
    raw = json.dumps(result, ensure_ascii=False, indent=2)
    note = f"{title}\n\n```json\n{raw}\n```"
    if len(note) <= MAX_COMPLETION_NOTE_CHARS:
        return note
    trimmed = note[: MAX_COMPLETION_NOTE_CHARS - 80].rstrip()
    return f"{trimmed}\n...\n```"
