#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import math
import socket
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NanoPi read-only rehab-arm telemetry uploader. Reads local JSON snapshots and posts them to the platform; never writes CAN/ROS/serial."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--device-id", default="")
    parser.add_argument("--robot-id", default="medical-rehab-arm")
    parser.add_argument("--computer-node-id", default="", help="Platform computer node that owns this NanoPi/read-only uploader.")
    parser.add_argument("--runner-id", default="", help="Platform runner id bound to the computer node, if available.")
    parser.add_argument("--board-scan-json", default="", help="Output from scripts/scan-device-interfaces.py --pretty, optional.")
    parser.add_argument("--joint-state-json", default="", help="ROS sensor_msgs/JointState-like JSON, optional.")
    parser.add_argument("--motor-state-json", default="", help="Motor list or object with motors[], optional.")
    parser.add_argument("--safety-state-json", default="", help="Safety state JSON, optional.")
    parser.add_argument("--sensor-state-json", default="", help="EMG/IMU/heart/model summary JSON, optional.")
    parser.add_argument("--keyframe-file", default="", help="Optional png/jpg/webp low-rate camera keyframe.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_json_file(path_text: str, fallback: Any) -> Any:
    if not path_text:
        return fallback
    path = Path(path_text).expanduser()
    return json.loads(path.read_text(encoding="utf-8-sig"))


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any, fallback: str = "") -> str:
    raw = str(value if value is not None else "").strip()
    return raw or fallback


def public_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def request_json(api_base: str, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}{path}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if method.upper() != "GET" else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail[:600]}") from exc


def request_multipart(api_base: str, path: str, fields: dict[str, str], file_name: str, file_bytes: bytes, content_type: str) -> dict[str, Any]:
    boundary = f"----nanopi-readonly-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}{path}",
        data=b"".join(chunks),
        method="POST",
        headers={"content-type": f"multipart/form-data; boundary={boundary}", "accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def device_id_from_args(args: argparse.Namespace) -> str:
    return text(args.device_id, f"nanopi-{socket.gethostname()}")


def normalize_joint_state(raw: Any) -> dict[str, list[float] | list[str]]:
    record = as_record(raw)
    names = record.get("name") or record.get("names") or record.get("joint_names") or []
    if not isinstance(names, list):
        names = []
    names = [text(name) for name in names if text(name)]
    positions = record.get("position") or record.get("positions") or []
    velocities = record.get("velocity") or record.get("velocities") or []
    efforts = record.get("effort") or record.get("efforts") or []
    return {
        "name": names,
        "position": numeric_list(positions, len(names), 0.0),
        "velocity": numeric_list(velocities, len(names), 0.0),
        "effort": numeric_list(efforts, len(names), 0.0),
    }


def numeric_list(raw: Any, length: int, default: float) -> list[float]:
    values = raw if isinstance(raw, list) else []
    result: list[float] = []
    for index in range(length):
        try:
            value = float(values[index])
            result.append(value if math.isfinite(value) else default)
        except Exception:
            result.append(default)
    return result


def normalize_motors(raw: Any, joint_state: dict[str, Any]) -> list[dict[str, Any]]:
    container = as_record(raw)
    raw_motors = container.get("motors") if container else raw
    motors = [item for item in as_list(raw_motors) if isinstance(item, dict)]
    if motors:
        return [
            {
                "motor_id": text(item.get("motor_id") or item.get("id"), f"M{index + 1}"),
                "joint_name": text(item.get("joint_name") or item.get("joint") or item.get("name")),
                "protocol": text(item.get("protocol"), "readonly_status"),
                "position": optional_float(item.get("position")),
                "velocity": optional_float(item.get("velocity")),
                "torque": optional_float(item.get("torque") if item.get("torque") is not None else item.get("effort")),
                "current": optional_float(item.get("current")),
                "temperature": optional_float(item.get("temperature") if item.get("temperature") is not None else item.get("temperature_c")),
                "voltage": optional_float(item.get("voltage")),
                "error_code": item.get("error_code", 0),
                "enabled": bool(item.get("enabled", False)),
                "fault": bool(item.get("fault", False)),
                "raw_can_id": item.get("raw_can_id"),
            }
            for index, item in enumerate(motors)
        ]
    names = as_list(joint_state.get("name"))
    positions = as_list(joint_state.get("position"))
    velocities = as_list(joint_state.get("velocity"))
    efforts = as_list(joint_state.get("effort"))
    return [
        {
            "motor_id": f"M{index + 1}",
            "joint_name": text(name, f"joint_{index + 1}"),
            "protocol": "readonly_joint_state",
            "position": optional_float(positions[index] if index < len(positions) else None),
            "velocity": optional_float(velocities[index] if index < len(velocities) else None),
            "torque": optional_float(efforts[index] if index < len(efforts) else None),
            "current": None,
            "temperature": None,
            "voltage": None,
            "error_code": 0,
            "enabled": False,
            "fault": False,
            "raw_can_id": None,
        }
        for index, name in enumerate(names)
    ]


def optional_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def build_board_manifest(args: argparse.Namespace, scan: dict[str, Any]) -> dict[str, Any]:
    interfaces = [item for item in as_list(scan.get("interfaces")) if isinstance(item, dict)]
    can_interfaces = [item for item in interfaces if item.get("kind") == "can"]
    serial_devices = [text(item.get("name") or item.get("id")) for item in interfaces if item.get("kind") == "serial"]
    camera_devices = [
        text(item.get("name") or item.get("id"))
        for item in interfaces
        if item.get("kind") in {"camera"} or "camera" in text(item.get("name")).lower()
    ]
    usb_devices = [
        {"kind": text(item.get("kind"), "usb"), "description": text(item.get("name") or item.get("id"))}
        for item in interfaces
        if item.get("kind") == "usb"
    ][:24]
    ros_items = [item for item in interfaces if item.get("kind") == "ros"]
    topics: list[str] = []
    for item in ros_items:
        details = as_record(item.get("details"))
        topics.extend([text(topic) for topic in as_list(details.get("topics")) if text(topic)])
    return {
        "schema_version": "linux_board_manifest_v1",
        "device_id": device_id_from_args(args),
        "robot_id": args.robot_id,
        "computer_node_id": text(args.computer_node_id),
        "runner_id": text(args.runner_id),
        "hostname": text(scan.get("host"), socket.gethostname()),
        "platform": {"os": text(scan.get("platform"), "Linux"), "role": "NanoPi 只读数据节点"},
        "capabilities": {
            "can_interfaces": [
                {
                    "name": text(item.get("name") or item.get("id"), "can"),
                    "kind": "socketcan",
                    "operstate": text(as_record(item.get("details")).get("operstate"), text(item.get("status"), "unknown")),
                    "mode": "listen-only",
                }
                for item in can_interfaces
            ],
            "serial_devices": serial_devices,
            "camera_devices": camera_devices,
            "usb_devices": usb_devices,
            "ros2": {"available": bool(ros_items), "topics": topics[:80]},
        },
        "control_boundary": "readonly_discovery_only_not_motion_permission",
    }


def build_payloads(args: argparse.Namespace) -> dict[str, Any]:
    now = time.time()
    device_id = device_id_from_args(args)
    binding = {
        "computer_node_id": text(args.computer_node_id),
        "runner_id": text(args.runner_id),
    }
    common = {"project_id": args.project_id, "robot_id": args.robot_id, "device_id": device_id}
    scan = as_record(read_json_file(args.board_scan_json, {}))
    joint_state = normalize_joint_state(read_json_file(args.joint_state_json, {}))
    motors = normalize_motors(read_json_file(args.motor_state_json, {}), joint_state)
    safety_raw = as_record(read_json_file(args.safety_state_json, {}))
    sensor_raw = as_record(read_json_file(args.sensor_state_json, {}))
    session_id = f"{device_id}-{int(now)}"
    motion_allowed = bool(safety_raw.get("motion_allowed", False))
    return {
        "register": {
            **common,
            **binding,
            "device_type": "nanopi",
            "software_version": "nanopi-readonly-agent-v1",
            "capabilities": ["linux_board_status", "can_readonly", "serial_readonly", "ros2_readonly", "camera_keyframe"],
        },
        "board_manifest": {**common, **binding, "manifest": build_board_manifest(args, scan)},
        "safety": {
            **common,
            "state": text(safety_raw.get("state"), "limited"),
            "motion_allowed": motion_allowed,
            "emergency_stop": bool(safety_raw.get("emergency_stop", False)),
            "m33_mode": text(safety_raw.get("m33_mode"), "observe_only"),
            "detail_code": text(safety_raw.get("detail_code"), "readonly_upload"),
            "detail": text(safety_raw.get("detail"), "NanoPi 只读代理上报状态；平台不下发运动控制。"),
            "heartbeat_age_ms": int(safety_raw.get("heartbeat_age_ms") or 0),
            "fault_code": text(safety_raw.get("fault_code")),
            "fault_message": text(safety_raw.get("fault_message")),
        },
        "motor": {**common, "ts_unix": now, "motors": motors, "joint_state": joint_state, "source": "nanopi_readonly_agent"},
        "sensor": {**common, "ts_unix": now, **sensor_raw, "source": text(sensor_raw.get("source"), "nanopi_readonly_agent")},
        "manifest": {
            "manifest": {
                "schema_version": "rehab_arm_manifest_v1",
                "sessions": [
                    {
                        "schema_version": "rehab_arm_recording_session_v1",
                        "ok": True,
                        "session_id": session_id,
                        "project_id": args.project_id,
                        "device_id": device_id,
                        "robot_id": args.robot_id,
                        "file_name": f"{session_id}.jsonl",
                        "record_count": max(1, len(motors)),
                        "summary": {
                            "schema_version": "rehab_arm_recording_summary_v1",
                            "topic_counts": {
                                "/joint_states": 1 if joint_state["name"] else 0,
                                "/rehab_arm/motor_state": 1 if motors else 0,
                                "/rehab_arm/safety_state": 1,
                                "/rehab_arm/sensor_state": 1 if sensor_raw else 0,
                            },
                            "moving_joint_count": len(joint_state["name"]),
                            "motor_entry_count_min": len(motors),
                            "motor_entry_count_max": len(motors),
                            "motion_allowed_counts": {"true": 1 if motion_allowed else 0, "false": 0 if motion_allowed else 1, "missing": 0},
                        },
                        "quality_report": {
                            "schema_version": "rehab_arm_recording_quality_v1",
                            "ok": bool(joint_state["name"] and motors and not motion_allowed),
                            "errors": [] if joint_state["name"] and motors and not motion_allowed else ["需要关节状态、电机状态，且样例中不允许出现运动许可"],
                            "warnings": ["NanoPi 只读代理单次快照，真实训练数据仍需采集片段。"],
                            "criteria": {
                                "min_joint_messages": 1,
                                "min_moving_joints": 1,
                                "require_motor_state": True,
                                "min_motor_entry_count": 1,
                                "allow_motion_allowed_true": False,
                            },
                        },
                    }
                ],
            }
        },
        "sync_status": {"device_id": device_id, "project_id": args.project_id, "sync_status": "uploaded", "file_name": f"{session_id}.jsonl", "record_count": max(1, len(motors))},
        "simulation": {
            **common,
            "report": {
                "schema_version": "rehab_arm_sim_env_check_v1",
                "ok": bool(joint_state["name"]),
                "readiness": "ready_with_joint_snapshot" if joint_state["name"] else "waiting_for_joint_snapshot",
                "joint_contract": {"count": len(joint_state["name"]), "names": joint_state["name"]},
                "safety_note": "只读状态快照；真实运动仍由 M33/本地安全链路裁决。",
                "errors": [] if joint_state["name"] else ["未提供关节状态"],
            },
        },
        "camera_fields": {
            **{key: str(value) for key, value in common.items()},
            "camera_id": "front",
            "frame_ts_unix": str(now),
            "image_format": keyframe_format(args.keyframe_file),
            "width": "1",
            "height": "1",
            "detection_summary": "NanoPi 只读代理上传低频关键帧",
            "scene_summary": "现场关键帧仅作观察证据，不参与实时控制。",
            "vla_context": "observation_only",
        },
    }


def keyframe_format(path_text: str) -> str:
    suffix = Path(path_text).suffix.lower().lstrip(".") if path_text else "png"
    return "jpg" if suffix == "jpeg" else (suffix if suffix in {"jpg", "png", "webp"} else "png")


def keyframe_bytes(path_text: str) -> tuple[str, bytes, str]:
    if not path_text:
        return "placeholder.png", PNG_1X1, "image/png"
    path = Path(path_text).expanduser()
    image_format = keyframe_format(path_text)
    content_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[image_format]
    return path.name, path.read_bytes(), content_type


def upload_payloads(args: argparse.Namespace, payloads: dict[str, Any]) -> dict[str, Any]:
    api_base = args.api_base.rstrip("/")
    device_id = payloads["register"]["device_id"]
    session_id = str(payloads["sync_status"]["file_name"]).removesuffix(".jsonl")
    file_name, image_bytes, content_type = keyframe_bytes(args.keyframe_file)
    results = {
        "register": request_json(api_base, "POST", "/api/rehab-arm/v1/devices/register", payloads["register"]),
        "board_manifest": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/board-manifest", payloads["board_manifest"]),
        "safety": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/safety-state", payloads["safety"]),
        "motor": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/motor-state", payloads["motor"]),
        "sensor": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/sensor-state", payloads["sensor"]),
        "manifest": request_json(api_base, "POST", "/api/rehab-arm/v1/sessions/manifest", payloads["manifest"]),
        "sync_status": request_json(api_base, "POST", f"/api/rehab-arm/v1/sessions/{session_id}/sync-status", payloads["sync_status"]),
        "simulation": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/simulation-readiness", payloads["simulation"]),
        "camera": request_multipart(api_base, f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes", payloads["camera_fields"], file_name, image_bytes, content_type),
    }
    dashboard = request_json(api_base, "GET", "/api/rehab-arm/v1/devices/dashboard", {})
    visible = [
        device
        for device in dashboard.get("data", {}).get("devices", [])
        if device.get("device_id") == device_id and device.get("project_id") == args.project_id
    ]
    return {
        "ok": bool(visible),
        "project_id": args.project_id,
        "device_id": device_id,
        "uploaded": list(results.keys()),
        "joint_count": len(payloads["motor"]["joint_state"]["name"]),
        "motor_count": len(payloads["motor"]["motors"]),
        "dashboard_device_visible_for_project": bool(visible),
    }


def main() -> int:
    args = parse_args()
    payloads = build_payloads(args)
    if args.dry_run:
        print(public_json({"ok": True, "dry_run": True, "payloads": payloads}))
        return 0
    result = upload_payloads(args, payloads)
    print(public_json(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
