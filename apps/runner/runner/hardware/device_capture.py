from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEVICE_CAPTURE_KINDS = {"robotics.capture.start", "robotics.capture.stop"}
MAX_CAPTURE_SECONDS = 3.0
MAX_CAPTURE_BYTES = 64_000
MAX_COMPLETION_NOTE_CHARS = 3800


def is_device_capture_command(payload: dict[str, Any] | None) -> bool:
    return str((payload or {}).get("kind") or "").strip() in DEVICE_CAPTURE_KINDS


def execute_device_capture_command(
    payload: dict[str, Any],
    *,
    allow_hardware_access: bool,
    workdir: Path,
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

    if kind == "robotics.capture.start":
        capture_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema": "runner_device_capture_session_v1",
            "capture_id": capture_id,
            "project_id": project_id,
            "computer_node_id": computer_node_id,
            "interface_id": interface_id,
            "interface_name": interface_name,
            "interface_kind": interface_kind,
            "sample_hz": sample_hz,
            "channels": channels,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "preview_file": _relative_to_workdir(preview_path, workdir),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return _result(
            True,
            "completed",
            "采集会话已在目标电脑准备好",
            {
                "ok": True,
                "kind": kind,
                "capture_id": capture_id,
                "status": "running",
                "manifest": _relative_to_workdir(manifest_path, workdir),
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

    capture_dir.mkdir(parents=True, exist_ok=True)
    serial_port = _serial_port_from_interface(payload.get("interface_id"), payload.get("port"))
    samples: list[dict[str, Any]] = []
    capture_error = ""
    byte_count = 0
    if _looks_like_serial(interface_kind, str(payload.get("interface_id") or "")) and serial_port:
        serial_result = _capture_serial_preview(serial_port, sample_hz=sample_hz)
        samples = serial_result["samples"]
        capture_error = serial_result["error"]
        byte_count = serial_result["byte_count"]
    else:
        capture_error = "当前最小采集器只支持串口只读采样；CAN/USB/SPI-CAN 会在后续通道补齐。"

    with preview_path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")

    stopped_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema": "runner_device_capture_result_v1",
        "capture_id": capture_id,
        "project_id": project_id,
        "computer_node_id": computer_node_id,
        "interface_id": interface_id,
        "interface_name": interface_name,
        "interface_kind": interface_kind,
        "sample_hz": sample_hz,
        "channels": channels,
        "stopped_at": stopped_at,
        "status": "captured" if samples else "empty",
        "sample_count": len(samples),
        "byte_count": byte_count,
        "preview_file": _relative_to_workdir(preview_path, workdir),
        "error": capture_error,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            "manifest": _relative_to_workdir(manifest_path, workdir),
            "preview": _relative_to_workdir(preview_path, workdir),
            "error": capture_error,
        },
    )


def _capture_serial_preview(port: str, *, sample_hz: int) -> dict[str, Any]:
    try:
        import serial  # type: ignore
    except Exception as exc:
        return {"samples": [], "byte_count": 0, "error": f"pyserial is not installed: {exc}"}

    timeout = max(0.02, min(0.2, 1 / max(sample_hz, 1)))
    deadline = time.time() + MAX_CAPTURE_SECONDS
    samples: list[dict[str, Any]] = []
    byte_count = 0
    try:
        with serial.Serial(port=port, baudrate=115200, timeout=timeout) as ser:
            while time.time() < deadline and byte_count < MAX_CAPTURE_BYTES:
                chunk = ser.readline() or ser.read(256)
                if not chunk:
                    continue
                byte_count += len(chunk)
                text = chunk.decode("utf-8", errors="replace").strip()
                samples.append(
                    {
                        "t": datetime.now(timezone.utc).isoformat(),
                        "port": port,
                        "bytes": len(chunk),
                        "text": text,
                        "hex": chunk[:64].hex(" "),
                    }
                )
                if len(samples) >= max(8, min(200, sample_hz)):
                    break
    except Exception as exc:
        return {"samples": samples, "byte_count": byte_count, "error": str(exc)}
    return {"samples": samples, "byte_count": byte_count, "error": "" if samples else "serial port returned no data in the short capture window"}


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
        return raw.split(":", 1)[1].strip()
    return ""


def _looks_like_serial(interface_kind: str, interface_id: str) -> bool:
    lowered = f"{interface_kind} {interface_id}".lower()
    return "serial" in lowered or "串口" in lowered or interface_id.lower().startswith("serial:")


def _relative_to_workdir(path: Path, workdir: Path) -> str:
    try:
        return path.relative_to(workdir).as_posix()
    except ValueError:
        return path.name


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
