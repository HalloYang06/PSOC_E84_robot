#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCANNER_VERSION = "2026-05-18.1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_text(command: list[str], timeout: float = 1.8) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{command[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:
        return 1, "", str(exc)


def read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None


def status_for_device(path: str) -> str:
    if not os.path.exists(path):
        return "offline"
    if os.access(path, os.R_OK):
        return "available"
    return "permission_needed"


def interface(item_id: str, kind: str, name: str, **kwargs: object) -> dict[str, object]:
    return {
        "id": item_id,
        "kind": kind,
        "name": name,
        "status": kwargs.pop("status", "unknown"),
        "transport": kwargs.pop("transport", None),
        "details": kwargs.pop("details", {}),
        "read_capability": kwargs.pop("read_capability", True),
        "write_capability": kwargs.pop("write_capability", "review_required"),
        "risk_level": kwargs.pop("risk_level", "medium"),
        **kwargs,
    }


def scan_serial() -> list[dict[str, object]]:
    paths: list[str] = []
    if os.name == "nt":
        # Windows COM ports are best scanned by pyserial when installed. Keep a
        # conservative placeholder so the runner command still succeeds.
        return [
            interface(
                "serial:windows-com",
                "serial",
                "Windows COM ports",
                status="scan_tool_needed",
                transport="win32",
                details={"hint": "Install pyserial on the runner for exact COM port enumeration."},
            )
        ]
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS*"):
        paths.extend(glob.glob(pattern))
    rows: list[dict[str, object]] = []
    for path in sorted(set(paths)):
        details: dict[str, object] = {"path": path}
        code, stdout, _ = run_text(["udevadm", "info", "-q", "property", "-n", path], timeout=1.2)
        if code == 0 and stdout:
            props: dict[str, str] = {}
            for line in stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key in {"ID_VENDOR", "ID_MODEL", "ID_SERIAL_SHORT", "ID_USB_DRIVER", "DEVLINKS"}:
                        props[key] = value
            details["udev"] = props
        busy = False
        for tool in ("fuser", "lsof"):
            code, stdout, _ = run_text([tool, path], timeout=0.8)
            if code == 0 and stdout:
                busy = True
                details["occupied_hint"] = tool
                break
        rows.append(
            interface(
                f"serial:{Path(path).name}",
                "serial",
                path,
                status="occupied" if busy else status_for_device(path),
                transport="tty",
                details=details,
                risk_level="medium",
            )
        )
    return rows


def scan_usb() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    code, stdout, stderr = run_text(["lsusb"], timeout=1.5)
    if code == 0 and stdout:
        for index, line in enumerate(stdout.splitlines()):
            name = line.strip()
            device_id = f"usb:{index + 1}"
            if " ID " in name:
                device_id = "usb:" + name.split(" ID ", 1)[1].split(" ", 1)[0]
            rows.append(
                interface(
                    device_id,
                    "usb",
                    name,
                    status="available",
                    transport="usb",
                    details={"lsusb": name},
                    risk_level="low",
                )
            )
    elif os.name != "nt":
        sysfs = sorted(Path("/sys/bus/usb/devices").glob("*")) if Path("/sys/bus/usb/devices").exists() else []
        for device in sysfs[:80]:
            vendor = read_text(device / "idVendor")
            product = read_text(device / "idProduct")
            name = read_text(device / "product") or device.name
            if vendor and product:
                rows.append(
                    interface(
                        f"usb:{vendor}:{product}:{device.name}",
                        "usb",
                        name,
                        status="available",
                        transport="usb-sysfs",
                        details={"vendor": vendor, "product": product, "sysfs_name": device.name},
                        risk_level="low",
                    )
                )
    else:
        rows.append(
            interface(
                "usb:windows",
                "usb",
                "Windows USB inventory",
                status="scan_tool_needed",
                transport="win32",
                details={"hint": "Use a runner helper with PowerShell PnPDevice support for full Windows USB inventory."},
                risk_level="low",
            )
        )
    if not rows and stderr:
        rows.append(
            interface(
                "usb:scan-unavailable",
                "usb",
                "USB scan unavailable",
                status="scan_tool_needed",
                transport="usb",
                details={"error": stderr},
                risk_level="low",
            )
        )
    return rows


def scan_can() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sys_class = Path("/sys/class/net")
    for netdev in sorted(sys_class.glob("can*")) if sys_class.exists() else []:
        details: dict[str, object] = {
            "ifindex": read_text(netdev / "ifindex"),
            "operstate": read_text(netdev / "operstate"),
            "mtu": read_text(netdev / "mtu"),
        }
        code, stdout, _ = run_text(["ip", "-details", "link", "show", netdev.name], timeout=1.2)
        if code == 0 and stdout:
            details["ip_details"] = stdout
        state = str(details.get("operstate") or "").lower()
        rows.append(
            interface(
                f"can:{netdev.name}",
                "can",
                netdev.name,
                status="available" if state in {"up", "unknown"} else "misconfigured",
                transport="socketcan",
                details=details,
                risk_level="medium",
            )
        )
    return rows


def scan_spi() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(glob.glob("/dev/spidev*")):
        details: dict[str, object] = {"path": path}
        rows.append(
            interface(
                f"spi:{Path(path).name}",
                "spi",
                path,
                status=status_for_device(path),
                transport="spidev",
                details=details,
                risk_level="high",
            )
        )
    code, stdout, _ = run_text(["lsmod"], timeout=1.2)
    if code == 0 and any(token in stdout.lower() for token in ("mcp251", "mcp25xx", "can_dev")):
        rows.append(
            interface(
                "spi-can:kernel-driver",
                "spi-can",
                "SPI-CAN driver clue",
                status="available",
                transport="socketcan-via-spi",
                details={"driver_hint": "mcp251x/can_dev module visible; confirm can0 after overlay and wiring."},
                risk_level="high",
            )
        )
    return rows


def scan_ros() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for command, kind in ((["ros2", "topic", "list"], "ros2"), (["rostopic", "list"], "ros1")):
        code, stdout, stderr = run_text(command, timeout=1.8)
        if code == 0:
            topics = [line.strip() for line in stdout.splitlines() if line.strip()]
            rows.append(
                interface(
                    f"ros:{kind}:topics",
                    "ros",
                    f"{kind.upper()} topics",
                    status="available",
                    transport=kind,
                    details={"topic_count": len(topics), "topics": topics[:60]},
                    risk_level="medium",
                )
            )
            return rows
        if stderr and "not found" not in stderr.lower():
            rows.append(
                interface(
                    f"ros:{kind}:unavailable",
                    "ros",
                    f"{kind.upper()} read-only probe",
                    status="misconfigured",
                    transport=kind,
                    details={"error": stderr[:400]},
                    risk_level="medium",
                )
            )
    return rows


def build_scan() -> dict[str, object]:
    interfaces = scan_serial() + scan_usb() + scan_can() + scan_spi() + scan_ros()
    summary: dict[str, object] = {"total": len(interfaces)}
    for kind in ("serial", "usb", "can", "spi", "spi-can", "ros"):
        summary[f"{kind}_count"] = len([item for item in interfaces if item.get("kind") == kind])
    return {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "scanner_version": SCANNER_VERSION,
        "scanned_at": now_iso(),
        "interfaces": interfaces,
        "summary": summary,
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only device interface scan for AI collaboration runner.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    scan = build_scan()
    print(json.dumps(scan, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
