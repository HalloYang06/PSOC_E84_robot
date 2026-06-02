#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[1]
SCAN_SCRIPT = ROOT / "scripts" / "scan-device-interfaces.py"
AGENT_SCRIPT = ROOT / "scripts" / "nanopi-rehab-arm-readonly-agent.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect NanoPi read-only ROS/interface snapshots and upload them through nanopi-rehab-arm-readonly-agent.py."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--robot-id", default="medical-rehab-arm")
    parser.add_argument("--computer-node-id", default="", help="Platform computer node that owns this NanoPi/read-only uploader.")
    parser.add_argument("--runner-id", default="", help="Platform runner id bound to the computer node, if available.")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--joint-topic", default="/joint_states")
    parser.add_argument("--safety-topic", default="/rehab_arm/safety_state")
    parser.add_argument("--sensor-topic", default="/rehab_arm/sensor_state")
    parser.add_argument("--keyframe-file", default="")
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--dry-run", action="store_true", help="Collect and build payloads but do not POST to the platform.")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--skip-ros", action="store_true")
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{command[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def find_command(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if os.name == "nt":
        for suffix in (".exe", ".cmd", ".bat"):
            resolved = shutil.which(f"{name}{suffix}")
            if resolved:
                return resolved
    return None


def parse_scalar(value: str) -> Any:
    raw = value.strip().strip("'\"")
    if not raw:
        return ""
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if raw.lower() in {"null", "none"}:
        return None
    try:
        if any(ch in raw for ch in (".", "e", "E")):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def parse_list(value: str) -> list[Any]:
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    return []


def parse_topic_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    result: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---" or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            result[key] = parse_list(value)
        else:
            result[key] = parse_scalar(value)
    return result


def collect_scan(output_dir: Path, timeout: float) -> Path:
    path = output_dir / "scan.json"
    code, stdout, stderr = run_command([sys.executable, str(SCAN_SCRIPT), "--pretty"], timeout=max(timeout, 8.0))
    if code == 0 and stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"interfaces": [], "warnings": [f"scan output was not JSON: {stdout[:300]}"]}
    else:
        payload = {"interfaces": [], "warnings": [stderr or f"scan failed with code {code}"]}
    write_json(path, payload)
    return path


def collect_ros_topic(output_dir: Path, topic: str, filename: str, timeout: float) -> Path:
    path = output_dir / filename
    ros2 = find_command("ros2")
    if not ros2:
        code, stdout, stderr = 127, "", "ros2 not found"
    else:
        code, stdout, stderr = run_command([ros2, "topic", "echo", "--once", topic], timeout=timeout)
    if code == 0 and stdout:
        payload = parse_topic_payload(stdout)
    else:
        payload = {"_unavailable": True, "topic": topic, "error": stderr or f"ros2 topic echo failed with code {code}"}
    write_json(path, payload)
    return path


def build_agent_command(args: argparse.Namespace, files: dict[str, Path]) -> list[str]:
    command = [
        sys.executable,
        str(AGENT_SCRIPT),
        "--api-base",
        args.api_base,
        "--project-id",
        args.project_id,
        "--device-id",
        args.device_id,
        "--robot-id",
        args.robot_id,
    ]
    if args.computer_node_id:
        command.extend(["--computer-node-id", args.computer_node_id])
    if args.runner_id:
        command.extend(["--runner-id", args.runner_id])
    if "scan" in files:
        command.extend(["--board-scan-json", str(files["scan"])])
    if "joint" in files:
        command.extend(["--joint-state-json", str(files["joint"])])
    if "safety" in files:
        command.extend(["--safety-state-json", str(files["safety"])])
    if "sensor" in files:
        command.extend(["--sensor-state-json", str(files["sensor"])])
    if args.keyframe_file:
        command.extend(["--keyframe-file", args.keyframe_file])
    if args.dry_run:
        command.append("--dry-run")
    return command


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else Path.cwd() / "nanopi-readonly-snapshots" / f"{args.device_id}-{int(time.time())}"
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    if not args.skip_scan:
        files["scan"] = collect_scan(output_dir, args.timeout)
    if not args.skip_ros:
        files["joint"] = collect_ros_topic(output_dir, args.joint_topic, "joint-state.json", args.timeout)
        files["safety"] = collect_ros_topic(output_dir, args.safety_topic, "safety-state.json", args.timeout)
        files["sensor"] = collect_ros_topic(output_dir, args.sensor_topic, "sensor-state.json", args.timeout)
    command = build_agent_command(args, files)
    code, stdout, stderr = run_command(command, timeout=max(args.timeout, 30.0))
    report = {
        "ok": code == 0,
        "output_dir": str(output_dir),
        "collected": {key: str(value) for key, value in files.items()},
        "agent_result": json.loads(stdout) if stdout.strip().startswith("{") else {"raw": stdout},
        "agent_error": stderr,
        "safety_boundary": "read_only_collection_only_no_can_ros_serial_writes",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if code == 0 else code


if __name__ == "__main__":
    raise SystemExit(main())
