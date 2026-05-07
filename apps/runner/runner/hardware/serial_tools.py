from __future__ import annotations

import glob
import json
import os
import platform
import re
import shutil
import subprocess
import time
from typing import Any


SERIAL_COMMAND_KINDS = {"serial.usb.scan", "serial.write"}
MAX_SERIAL_PAYLOAD_BYTES = 4096
MAX_COMPLETION_NOTE_CHARS = 3800


def parse_runner_command_body(body: str | None) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def is_serial_command(payload: dict[str, Any] | None) -> bool:
    return str((payload or {}).get("kind") or "").strip() in SERIAL_COMMAND_KINDS


def execute_serial_command(payload: dict[str, Any], *, allow_hardware_access: bool) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip()
    if kind not in SERIAL_COMMAND_KINDS:
        return {
            "handled": False,
            "result_status": "failed",
            "note": "",
            "result": {"ok": False, "error": f"unsupported serial command kind: {kind or '<empty>'}"},
        }

    if not allow_hardware_access:
        result = {
            "ok": False,
            "kind": kind,
            "error": "hardware access is disabled for this runner",
            "hint": "Set ALLOW_HARDWARE_ACCESS=true on the computer that should scan USB/serial devices.",
        }
        return {
            "handled": True,
            "result_status": "failed",
            "note": _format_completion_note("硬件权限未开启", result),
            "result": result,
        }

    if kind == "serial.usb.scan":
        result = scan_usb_and_serial_devices()
        return {
            "handled": True,
            "result_status": "completed" if result.get("ok") else "failed",
            "note": _format_completion_note("串口电视扫描结果", result),
            "result": result,
        }

    result = write_serial_payload(payload)
    return {
        "handled": True,
        "result_status": "completed" if result.get("ok") else "failed",
        "note": _format_completion_note("串口电视写入结果", result),
        "result": result,
    }


def scan_usb_and_serial_devices() -> dict[str, Any]:
    serial_devices = _scan_serial_ports()
    usb_devices = _scan_usb_devices()
    return {
        "ok": True,
        "kind": "serial.usb.scan",
        "host_os": platform.platform(),
        "serial_devices": serial_devices,
        "serial_device_count": len(serial_devices),
        "usb_devices": usb_devices,
        "usb_device_count": len(usb_devices),
        "protocol_hint": "AICSV/1: @xy,<x>,<y> or @sample,<t>,<ch1>,<ch2>...",
    }


def write_serial_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        port = _safe_port_name(str(payload.get("port") or ""))
        baud_rate = _safe_baud_rate(payload.get("baud_rate"))
    except ValueError as exc:
        return {
            "ok": False,
            "kind": "serial.write",
            "error": str(exc),
        }
    payload_format = str(payload.get("payload_format") or "text-lf").strip().lower()
    payload_text = str(payload.get("payload") or "")
    try:
        payload_bytes = _encode_payload(payload_text, payload_format)
    except ValueError as exc:
        return {
            "ok": False,
            "kind": "serial.write",
            "port": port,
            "baud_rate": baud_rate,
            "payload_format": payload_format,
            "error": str(exc),
        }

    try:
        import serial  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "kind": "serial.write",
            "port": port,
            "baud_rate": baud_rate,
            "payload_format": payload_format,
            "bytes_prepared": len(payload_bytes),
            "error": "pyserial is not installed on this runner",
            "hint": "Install pyserial on the target computer to enable serial.write.",
            "import_error": str(exc),
        }

    try:
        with serial.Serial(port=port, baudrate=baud_rate, timeout=0.2, write_timeout=2) as ser:
            written = ser.write(payload_bytes)
            ser.flush()
            time.sleep(0.05)
            incoming = ser.read(512)
    except Exception as exc:
        return {
            "ok": False,
            "kind": "serial.write",
            "port": port,
            "baud_rate": baud_rate,
            "payload_format": payload_format,
            "bytes_prepared": len(payload_bytes),
            "error": str(exc),
        }

    return {
        "ok": True,
        "kind": "serial.write",
        "port": port,
        "baud_rate": baud_rate,
        "payload_format": payload_format,
        "bytes_written": written,
        "readback_bytes": len(incoming),
        "readback_hex": incoming.hex(" ") if incoming else "",
        "readback_text": incoming.decode("utf-8", errors="replace") if incoming else "",
    }


def _scan_serial_ports() -> list[dict[str, Any]]:
    devices = _scan_serial_ports_pyserial()
    if devices:
        return devices
    if os.name == "nt":
        return _scan_serial_ports_windows_cim()
    return _scan_serial_ports_glob()


def _scan_serial_ports_pyserial() -> list[dict[str, Any]]:
    try:
        from serial.tools import list_ports  # type: ignore
    except Exception:
        return []
    devices: list[dict[str, Any]] = []
    for item in list_ports.comports():
        devices.append(
            {
                "port": item.device,
                "label": item.description or item.device,
                "hwid": item.hwid,
                "vendor_id": f"{item.vid:04X}" if item.vid is not None else None,
                "product_id": f"{item.pid:04X}" if item.pid is not None else None,
                "serial_number": item.serial_number,
                "manufacturer": item.manufacturer,
                "product": item.product,
                "source": "pyserial",
            }
        )
    return devices


def _scan_serial_ports_windows_cim() -> list[dict[str, Any]]:
    script = (
        "Get-CimInstance Win32_SerialPort | "
        "Select-Object DeviceID,Name,Description,PNPDeviceID,Manufacturer | "
        "ConvertTo-Json -Compress"
    )
    data = _run_powershell_json(script)
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    devices: list[dict[str, Any]] = []
    for row in rows:
        port = str(row.get("DeviceID") or "").strip()
        if not port:
            continue
        devices.append(
            {
                "port": port,
                "label": row.get("Name") or row.get("Description") or port,
                "hwid": row.get("PNPDeviceID"),
                "manufacturer": row.get("Manufacturer"),
                "source": "windows-cim",
            }
        )
    return devices


def _scan_serial_ports_glob() -> list[dict[str, Any]]:
    patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"]
    if platform.system().lower() == "darwin":
        patterns = ["/dev/cu.*", "/dev/tty.*"]
    seen: set[str] = set()
    devices: list[dict[str, Any]] = []
    for pattern in patterns:
        for port in sorted(glob.glob(pattern)):
            if port in seen:
                continue
            seen.add(port)
            devices.append({"port": port, "label": port, "source": "device-glob"})
    return devices


def _scan_usb_devices() -> list[dict[str, Any]]:
    if os.name == "nt":
        return _scan_usb_devices_windows_cim()
    if shutil.which("lsusb"):
        completed = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5, shell=False)
        if completed.returncode == 0:
            return [
                {"label": line.strip(), "source": "lsusb"}
                for line in completed.stdout.splitlines()
                if line.strip()
            ]
    return []


def _scan_usb_devices_windows_cim() -> list[dict[str, Any]]:
    script = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPDeviceID -like 'USB*' } | "
        "Select-Object Name,DeviceID,Manufacturer,Status | "
        "ConvertTo-Json -Compress"
    )
    data = _run_powershell_json(script)
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    devices: list[dict[str, Any]] = []
    for row in rows[:80]:
        label = str(row.get("Name") or row.get("DeviceID") or "").strip()
        if not label:
            continue
        devices.append(
            {
                "label": label,
                "device_id": row.get("DeviceID"),
                "manufacturer": row.get("Manufacturer"),
                "status": row.get("Status"),
                "source": "windows-cim",
            }
        )
    return devices


def _run_powershell_json(script: str) -> Any:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    completed = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=8,
        shell=False,
    )
    raw = completed.stdout.strip()
    if completed.returncode != 0 or not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _safe_port_name(value: str) -> str:
    port = value.strip()
    if not port:
        raise ValueError("serial port is required")
    if len(port) > 120 or any(ord(ch) < 32 for ch in port):
        raise ValueError("serial port name is invalid")
    return port


def _safe_baud_rate(value: Any) -> int:
    try:
        baud_rate = int(value)
    except Exception:
        baud_rate = 115200
    if baud_rate < 300 or baud_rate > 2_000_000:
        raise ValueError("baud_rate must be between 300 and 2000000")
    return baud_rate


def _encode_payload(payload_text: str, payload_format: str) -> bytes:
    if payload_format in {"text-lf", "line"}:
        text = payload_text if payload_text.endswith("\n") else f"{payload_text}\n"
        data = text.encode("utf-8")
    elif payload_format in {"text", "raw"}:
        data = payload_text.encode("utf-8")
    elif payload_format == "hex":
        cleaned = re.sub(r"[^0-9A-Fa-f]", "", payload_text)
        if not cleaned:
            raise ValueError("hex payload is empty")
        if len(cleaned) % 2:
            raise ValueError("hex payload must contain an even number of digits")
        data = bytes.fromhex(cleaned)
    else:
        raise ValueError(f"unsupported payload_format: {payload_format}")
    if not data:
        raise ValueError("payload is empty")
    if len(data) > MAX_SERIAL_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_SERIAL_PAYLOAD_BYTES} bytes")
    return data


def _format_completion_note(title: str, result: dict[str, Any]) -> str:
    raw = json.dumps(result, ensure_ascii=False, indent=2)
    note = f"{title}\n\n```json\n{raw}\n```"
    if len(note) <= MAX_COMPLETION_NOTE_CHARS:
        return note
    trimmed = note[: MAX_COMPLETION_NOTE_CHARS - 80].rstrip()
    return f"{trimmed}\n...\n```"
