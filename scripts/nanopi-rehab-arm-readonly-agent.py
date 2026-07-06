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

CAN_ID_F103_EMG_ADC = 0x7C2
CAN_ID_M33_M55_MODEL_STATUS = 0x323
M55_MODEL_STATUS_MARKER = 0xB5
M55_MODEL_FLAG_FRESH = 0x01
M55_MODEL_FLAG_DETECTED = 0x02
M55_MODEL_FLAG_SUGGESTION_ONLY = 0x80
ADC_REFERENCE_V = 3.3
ADC_MAX_COUNT = 4095.0
EMG_CHANNELS = [
    {"channel": "ch1", "muscle": "biceps", "role": "model_input"},
    {"channel": "ch2", "muscle": "triceps", "role": "model_input"},
    {"channel": "ch3", "muscle": "forearm_flexors", "role": "model_input"},
    {"channel": "ch4", "muscle": "reserved", "role": "reserved_physical_input"},
]
M55_EMG_INTENT_LABELS = {
    0: "elbow_extend",
    1: "elbow_flex",
    2: "rest",
    3: "shoulder_flex",
}


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
    parser.add_argument("--left-keyframe-file", default="", help="Optional left RGB camera keyframe for stereo V evidence.")
    parser.add_argument("--right-keyframe-file", default="", help="Optional right RGB camera keyframe for stereo V evidence.")
    parser.add_argument("--left-camera-index", type=int, default=None, help="OpenCV camera index used for the logical stereo_left frame, if known.")
    parser.add_argument("--right-camera-index", type=int, default=None, help="OpenCV camera index used for the logical stereo_right frame, if known.")
    parser.add_argument("--left-flip", choices=["none", "h", "v", "hv", "unknown"], default="unknown", help="Frame flip applied to logical stereo_left before upload/detection.")
    parser.add_argument("--right-flip", choices=["none", "h", "v", "hv", "unknown"], default="unknown", help="Frame flip applied to logical stereo_right before upload/detection.")
    parser.add_argument("--flip-applied-before-detection", action="store_true", help="Record that any configured stereo flip was applied before detector/depth processing.")
    parser.add_argument("--end-effector-onnx", default="", help="Optional YOLOv8 ONNX model for end_effector/gripper_tip evidence.")
    parser.add_argument("--end-effector-conf", type=float, default=0.15, help="Confidence threshold for the optional end-effector ONNX detector.")
    parser.add_argument("--end-effector-nms", type=float, default=0.45, help="NMS threshold for the optional end-effector ONNX detector.")
    parser.add_argument("--end-effector-imgsz", type=int, default=416, help="Input size used by the optional end-effector ONNX detector.")
    parser.add_argument("--stereo-baseline-m", type=float, default=0.06, help="Distance between left/right RGB cameras in meters.")
    parser.add_argument("--stereo-calibration-id", default="bench_uncalibrated_rgb_pair", help="Calibration id attached to stereo context evidence.")
    parser.add_argument("--stereo-width", type=int, default=640)
    parser.add_argument("--stereo-height", type=int, default=480)
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


def parse_can_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw.startswith("0x"):
                return int(raw, 16)
            return int(raw, 10)
        return int(value)
    except Exception:
        return None


def parse_can_data(value: Any) -> list[int]:
    if isinstance(value, list):
        result: list[int] = []
        for item in value:
            try:
                result.append(int(item) & 0xFF)
            except Exception:
                return []
        return result
    if isinstance(value, str):
        raw = value.strip().replace(",", " ").replace("-", " ").replace(":", " ")
        parts = [part for part in raw.split() if part]
        if len(parts) == 1 and len(parts[0]) % 2 == 0:
            parts = [parts[0][index:index + 2] for index in range(0, len(parts[0]), 2)]
        result = []
        for part in parts:
            try:
                result.append(int(part, 16) & 0xFF)
            except Exception:
                return []
        return result
    return []


def can_frame_id(frame: dict[str, Any]) -> int | None:
    return parse_can_id(frame.get("id") or frame.get("can_id") or frame.get("arbitration_id"))


def latest_can_frame(frames: list[Any], can_id: int) -> dict[str, Any] | None:
    matched = [
        frame
        for frame in frames
        if isinstance(frame, dict) and can_frame_id(frame) == can_id
    ]
    return matched[-1] if matched else None


def u16_le(data: list[int], offset: int) -> int:
    return int(data[offset]) | (int(data[offset + 1]) << 8)


def adc_to_voltage(raw_adc: int) -> float:
    return round(max(0.0, min(ADC_MAX_COUNT, float(raw_adc))) * ADC_REFERENCE_V / ADC_MAX_COUNT, 3)


def decode_emg_adc_frame(frame: dict[str, Any] | None, sample_rate_hz: Any, now: float) -> dict[str, Any] | None:
    if not frame:
        return None
    data = parse_can_data(frame.get("data") or frame.get("payload") or frame.get("bytes"))
    if len(data) < 8:
        return None
    raw_values = [u16_le(data, offset) for offset in range(0, 8, 2)]
    channels = []
    for index, spec in enumerate(EMG_CHANNELS):
        raw_adc = raw_values[index]
        channels.append(
            {
                **spec,
                "index": index,
                "raw_adc": raw_adc,
                "adc_count": raw_adc,
                "unit": "adc_count",
                "voltage_v": adc_to_voltage(raw_adc),
                "normalized": round(raw_adc / ADC_MAX_COUNT, 4) if raw_adc else 0.0,
                "adc_reference_v": ADC_REFERENCE_V,
                "adc_resolution_bits": 12,
                "connected": raw_adc > 0,
                "quality": {"status": "no_electrode_or_unverified"},
            }
        )
    return {
        "schema_version": "rehab_arm_emg4_adc_v1",
        "source": "m33_can_0x7c2_via_nanopi",
        "can_id": "0x7C2",
        "channel_count": 4,
        "model_input_channel_count": 3,
        "sample_rate_hz": optional_float(sample_rate_hz) or 50.0,
        "unit": "adc_count",
        "voltage_reference_v": ADC_REFERENCE_V,
        "adc_resolution_bits": 12,
        "channels": channels,
        "quality": {
            "status": "no_electrode_or_unverified",
            "reason": "electrodes_not_attached_or_contact_not_calibrated",
            "motion_permission": False,
        },
        "timestamp_source": "nanopi_receive_time",
        "ts_unix": optional_float(frame.get("ts_unix") or frame.get("timestamp")) or now,
        "control_boundary": "readonly_emg_sensor_evidence_only_not_motion_permission",
    }


def m55_intent_label(model_code: int, result_code: int) -> str:
    if model_code == 2:
        return M55_EMG_INTENT_LABELS.get(result_code, f"unknown_{result_code}")
    return f"model_{model_code}_result_{result_code}"


def decode_m55_model_status_frame(frame: dict[str, Any] | None, now: float) -> dict[str, Any] | None:
    if not frame:
        return None
    data = parse_can_data(frame.get("data") or frame.get("payload") or frame.get("bytes"))
    if len(data) < 8 or data[0] != M55_MODEL_STATUS_MARKER:
        return None
    model_code = int(data[2])
    result_code = int(data[3])
    confidence_permille = int(data[4]) * 10
    flags = int(data[5])
    window_ms = int(data[6]) * 10
    label = m55_intent_label(model_code, result_code)
    return {
        "schema_version": "rehab_arm_m55_intent_prediction_v1",
        "source": "m55_inference_can_0x323",
        "can_id": "0x323",
        "marker": "0xB5",
        "seq": int(data[1]),
        "model_code": model_code,
        "model": "emg_intent" if model_code == 2 else f"model_{model_code}",
        "result_code": result_code,
        "label": label,
        "value": label,
        "confidence_permille": min(1000, max(0, confidence_permille)),
        "confidence": round(min(1000, max(0, confidence_permille)) / 1000.0, 3),
        "fresh": bool(flags & M55_MODEL_FLAG_FRESH),
        "detected": bool(flags & M55_MODEL_FLAG_DETECTED),
        "suggestion_only": bool(flags & M55_MODEL_FLAG_SUGGESTION_ONLY),
        "window_ms": window_ms,
        "timestamp_source": "nanopi_receive_time",
        "ts_unix": optional_float(frame.get("ts_unix") or frame.get("timestamp")) or now,
        "control_boundary": "m55_inference_suggestion_only_not_motion_permission",
    }


def model_outputs_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    candidate = {
        "label": intent.get("label"),
        "value": intent.get("value") or intent.get("label"),
        "confidence": intent.get("confidence"),
        "confidence_permille": intent.get("confidence_permille"),
        "detected": intent.get("detected"),
        "fresh": intent.get("fresh"),
        "source": intent.get("source"),
        "detail": f"model_code={intent.get('model_code')} result_code={intent.get('result_code')} window_ms={intent.get('window_ms')}",
        "control_boundary": intent.get("control_boundary"),
    }
    return {
        "schema_version": "rehab_arm_m55_model_outputs_v1",
        "source": "m55_inference_can_0x323",
        "latest": intent,
        "candidates": [candidate],
        "results": [intent],
        "control_boundary": "model_outputs_display_only_not_motion_permission",
    }


def normalize_sensor_state(sensor_raw: dict[str, Any], now: float) -> dict[str, Any]:
    if not sensor_raw:
        return {}
    normalized = dict(sensor_raw)
    frames = as_list(sensor_raw.get("can_frames") or sensor_raw.get("frames") or sensor_raw.get("can"))
    emg = decode_emg_adc_frame(
        latest_can_frame(frames, CAN_ID_F103_EMG_ADC),
        sensor_raw.get("sample_rate_hz") or sensor_raw.get("sample_rate"),
        now,
    )
    intent = decode_m55_model_status_frame(latest_can_frame(frames, CAN_ID_M33_M55_MODEL_STATUS), now)
    if emg:
        normalized["emg"] = emg
        normalized.setdefault("emg_channels", emg["channels"])
    if intent:
        model_outputs = model_outputs_from_intent(intent)
        normalized["intent_prediction"] = intent
        normalized["model_outputs"] = model_outputs
        if isinstance(normalized.get("emg"), dict):
            normalized["emg"]["intent_prediction"] = intent
            normalized["emg"]["model_outputs"] = model_outputs
    return normalized


def build_rehab_arm_hardware_manifest(args: argparse.Namespace, can_interfaces: list[dict[str, Any]]) -> dict[str, Any]:
    can_name = text((can_interfaces[0] if can_interfaces else {}).get("name"), "can0")
    return {
        "schema_version": "rehab_arm_hardware_manifest_v1",
        "device_id": device_id_from_args(args),
        "robot_id": args.robot_id,
        "timebase": {
            "nanopi_upload": "unix_seconds",
            "m33_m55_ipc": "rt_tick_ms",
            "sensor_node": "f103_local_sequence",
        },
        "can": {
            "interface": can_name,
            "mode": "listen-only",
            "emg_adc_can_id": "0x7C2",
            "m55_model_status_can_id": "0x323",
        },
        "emg": {
            "schema_version": "rehab_arm_emg4_adc_v1",
            "sensor_node": "stm32_sensor_node_on_can",
            "channel_count_reserved": 4,
            "model_input_channels": ["ch1", "ch2", "ch3"],
            "reserved_channels": ["ch4"],
            "adc_reference_v": ADC_REFERENCE_V,
            "adc_resolution_bits": 12,
            "unit": "adc_count",
            "voltage_unit": "V",
            "sample_rate_hz_nominal": 50,
            "quality_default": "no_electrode_or_unverified",
            "channels": EMG_CHANNELS,
        },
        "inference": {
            "m55_model_status_can_id": "0x323",
            "model_code_emg_intent": 2,
            "labels": M55_EMG_INTENT_LABELS,
            "authority": "suggestion_only_m33_keeps_motion_authority",
        },
        "control_boundary": "readonly_hardware_manifest_not_motion_permission",
    }


def build_board_manifest(args: argparse.Namespace, scan: dict[str, Any]) -> dict[str, Any]:
    interfaces = [item for item in as_list(scan.get("interfaces")) if isinstance(item, dict)]
    can_interfaces = [item for item in interfaces if item.get("kind") == "can"]
    serial_devices = [text(item.get("name") or item.get("id")) for item in interfaces if item.get("kind") == "serial"]
    camera_devices = [
        text(item.get("name") or item.get("id"))
        for item in interfaces
        if item.get("kind") in {"camera"} or "camera" in text(item.get("name")).lower()
    ]
    camera_device_details = [
        {
            "name": text(item.get("name") or item.get("id")),
            "kind": text(item.get("kind"), "camera"),
            "status": text(item.get("status"), "unknown"),
            "transport": text(item.get("transport")),
            "details": as_record(item.get("details")),
        }
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
            "camera_device_details": camera_device_details,
            "usb_devices": usb_devices,
            "ros2": {"available": bool(ros_items), "topics": topics[:80]},
        },
        "hardware_manifest": build_rehab_arm_hardware_manifest(args, can_interfaces),
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
    sensor_raw = normalize_sensor_state(as_record(read_json_file(args.sensor_state_json, {})), now)
    session_id = f"{device_id}-{int(now)}"
    motion_allowed = bool(safety_raw.get("motion_allowed", False))
    return {
        "register": {
            **common,
            **binding,
            "device_type": "nanopi",
            "software_version": "nanopi-readonly-agent-v1",
            "capabilities": ["linux_board_status", "can_readonly", "can_frame_decode_readonly", "emg4_adc_readonly", "m55_intent_status_readonly", "serial_readonly", "ros2_readonly", "camera_keyframe"],
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
        "stereo_context": build_stereo_context(args, common, now),
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


def stereo_image_pair_ref(device_id: str) -> dict[str, str]:
    return {
        "left_image_url": f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes/stereo_left/latest/file",
        "right_image_url": f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes/stereo_right/latest/file",
    }


def stereo_camera_mapping(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "logical_left": {
            "camera_id": "stereo_left",
            "opencv_index": args.left_camera_index,
            "flip": args.left_flip,
            "flip_applied_before_detection": bool(args.flip_applied_before_detection),
        },
        "logical_right": {
            "camera_id": "stereo_right",
            "opencv_index": args.right_camera_index,
            "flip": args.right_flip,
            "flip_applied_before_detection": bool(args.flip_applied_before_detection),
        },
        "mapping_state": "provided_by_capture_args" if args.left_camera_index is not None and args.right_camera_index is not None else "waiting_physical_index_confirmation",
    }


def _load_cv2() -> Any | None:
    try:
        import cv2  # type: ignore

        return cv2
    except Exception:
        return None


def _letterbox(frame: Any, image_size: int, cv2: Any) -> tuple[Any, float, int, int]:
    height, width = frame.shape[:2]
    ratio = min(image_size / max(1, height), image_size / max(1, width))
    resized_width = max(1, int(round(width * ratio)))
    resized_height = max(1, int(round(height * ratio)))
    resized = cv2.resize(frame, (resized_width, resized_height))
    pad_x = (image_size - resized_width) // 2
    pad_y = (image_size - resized_height) // 2
    canvas = __import__("numpy").full((image_size, image_size, 3), 114, dtype=__import__("numpy").uint8)
    canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
    return canvas, ratio, pad_x, pad_y


def _nms_detections(detections: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    def area(item: dict[str, Any]) -> float:
        x, y, w, h = item["bbox_xywh"]
        return max(0.0, float(w)) * max(0.0, float(h))

    def iou(left: dict[str, Any], right: dict[str, Any]) -> float:
        lx, ly, lw, lh = left["bbox_xywh"]
        rx, ry, rw, rh = right["bbox_xywh"]
        lx2, ly2 = lx + lw, ly + lh
        rx2, ry2 = rx + rw, ry + rh
        ix1, iy1 = max(lx, rx), max(ly, ry)
        ix2, iy2 = min(lx2, rx2), min(ly2, ry2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        return inter / max(1e-6, area(left) + area(right) - inter)

    kept: list[dict[str, Any]] = []
    for candidate in sorted(detections, key=lambda item: float(item["confidence"]), reverse=True):
        if all(candidate["label"] != item["label"] or iou(candidate, item) < threshold for item in kept):
            kept.append(candidate)
    return kept


def run_end_effector_onnx(args: argparse.Namespace, image_path_text: str, camera_id: str) -> list[dict[str, Any]]:
    if not args.end_effector_onnx or not image_path_text:
        return []
    cv2 = _load_cv2()
    if cv2 is None:
        return []
    model_path = Path(args.end_effector_onnx).expanduser()
    image_path = Path(image_path_text).expanduser()
    if not model_path.exists() or not image_path.exists():
        return []
    frame = cv2.imread(str(image_path))
    if frame is None:
        return []
    image_size = max(32, int(args.end_effector_imgsz))
    blob_frame, ratio, pad_x, pad_y = _letterbox(frame, image_size, cv2)
    net = cv2.dnn.readNetFromONNX(str(model_path))
    blob = cv2.dnn.blobFromImage(blob_frame, 1 / 255.0, (image_size, image_size), swapRB=True, crop=False)
    net.setInput(blob)
    output = __import__("numpy").squeeze(net.forward())
    if len(output.shape) == 2 and output.shape[0] < output.shape[1]:
        output = output.T
    names = ["end_effector", "gripper_tip"]
    height, width = frame.shape[:2]
    detections: list[dict[str, Any]] = []
    for row in output:
        if len(row) < 6:
            continue
        scores = row[4:6]
        class_id = int(__import__("numpy").argmax(scores))
        confidence = float(scores[class_id])
        if confidence < args.end_effector_conf:
            continue
        center_x, center_y, box_w, box_h = [float(value) for value in row[:4]]
        x1 = (center_x - box_w / 2 - pad_x) / ratio
        y1 = (center_y - box_h / 2 - pad_y) / ratio
        x2 = (center_x + box_w / 2 - pad_x) / ratio
        y2 = (center_y + box_h / 2 - pad_y) / ratio
        x1 = max(0.0, min(float(width - 1), x1))
        y1 = max(0.0, min(float(height - 1), y1))
        x2 = max(0.0, min(float(width - 1), x2))
        y2 = max(0.0, min(float(height - 1), y2))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append({
            "label": names[class_id],
            "confidence": round(confidence, 4),
            "bbox_xywh": [round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)],
            "center_xy": [round((x1 + x2) / 2, 2), round((y1 + y2) / 2, 2)],
            "camera_id": camera_id,
            "detector": "end_effector_yolov8_onnx",
            "control_boundary": "detector_output_only_not_motion_permission",
        })
    return _nms_detections(detections, float(args.end_effector_nms))


def select_best_detection(detections: list[dict[str, Any]], label: str) -> dict[str, Any]:
    candidates = [item for item in detections if item.get("label") == label]
    if not candidates:
        return {"label": "waiting", "confidence": 0.0}
    return dict(sorted(candidates, key=lambda item: float(item.get("confidence", 0.0)), reverse=True)[0])


def build_stereo_context(args: argparse.Namespace, common: dict[str, Any], now: float) -> dict[str, Any] | None:
    if not args.left_keyframe_file or not args.right_keyframe_file:
        return None
    left_detections = run_end_effector_onnx(args, args.left_keyframe_file, "stereo_left")
    right_detections = run_end_effector_onnx(args, args.right_keyframe_file, "stereo_right")
    detections = {"left": left_detections, "right": right_detections}
    end_effector = select_best_detection(left_detections + right_detections, "end_effector")
    gripper_tip = select_best_detection(left_detections + right_detections, "gripper_tip")
    detector_state = "end_effector_detector_ready" if args.end_effector_onnx else "waiting_detector"
    if args.end_effector_onnx and not (left_detections or right_detections):
        detector_state = "end_effector_not_detected"
    return {
        "schema_version": "stereo_rgb_yolo_context_v1",
        **common,
        "frame_ts_unix": now,
        "capture_loop": {
            "implementation": "nanopi_python_stereo_keyframe_upload",
            "mode": "two_usb_rgb_keyframes",
            "camera_mapping": stereo_camera_mapping(args),
            "control_boundary": "capture_loop_readonly_not_motion_permission",
        },
        "left_camera_id": "stereo_left",
        "right_camera_id": "stereo_right",
        "stereo_calibration_id": text(args.stereo_calibration_id, "bench_uncalibrated_rgb_pair"),
        "baseline_m": args.stereo_baseline_m if args.stereo_baseline_m > 0 else None,
        "image_pair_ref": stereo_image_pair_ref(str(common["device_id"])),
        "detections": detections,
        "target_object": {"label": "waiting", "confidence": 0.0},
        "end_effector_object": end_effector,
        "gripper_tip_object": gripper_tip,
        "pixel_servo_hint": {
            "next_step": "observe_only_wait_for_target" if end_effector.get("confidence", 0.0) else "observe_only_wait_for_detector",
            "metric_depth_available": False,
            "control_boundary": "pixel_servo_hint_only_not_motion_permission",
        },
        "visual_lock_stability": {
            "state": "single_frame_end_effector_evidence" if end_effector.get("confidence", 0.0) else detector_state,
            "stable_for_dry_run": False,
            "control_boundary": "visual_lock_only_not_motion_permission",
        },
        "target_quality_gate": {
            "state": "waiting_target_detector",
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        },
        "estimated_depth_m": None,
        "target_3d_camera_frame": None,
        "scene_summary": "stereo RGB keyframes uploaded; optional end-effector detector evidence attached",
        "vla_context": "two USB RGB cameras provide V evidence only; end-effector detection is not motion permission",
        "confidence": max(float(end_effector.get("confidence", 0.0)), float(gripper_tip.get("confidence", 0.0))),
        "control_boundary": "stereo_vision_context_only_not_motion_permission",
    }


def stereo_camera_fields(args: argparse.Namespace, common: dict[str, Any], camera_id: str, now: float) -> dict[str, str]:
    return {
        **{key: str(value) for key, value in common.items()},
        "camera_id": camera_id,
        "frame_ts_unix": str(now),
        "image_format": keyframe_format(args.left_keyframe_file if camera_id == "stereo_left" else args.right_keyframe_file),
        "width": str(max(1, int(args.stereo_width))),
        "height": str(max(1, int(args.stereo_height))),
        "detection_summary": f"{camera_id} raw keyframe; detector pending",
        "scene_summary": "Stereo RGB raw keyframe uploaded from NanoPi read-only path.",
        "vla_context": "stereo RGB frame evidence only; not motion permission",
    }


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
    if payloads.get("stereo_context"):
        now = float(payloads["stereo_context"]["frame_ts_unix"])
        left_name, left_bytes, left_type = keyframe_bytes(args.left_keyframe_file)
        right_name, right_bytes, right_type = keyframe_bytes(args.right_keyframe_file)
        results["stereo_left_camera"] = request_multipart(
            api_base,
            f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes",
            stereo_camera_fields(args, {"project_id": args.project_id, "robot_id": args.robot_id, "device_id": device_id}, "stereo_left", now),
            left_name,
            left_bytes,
            left_type,
        )
        results["stereo_right_camera"] = request_multipart(
            api_base,
            f"/api/rehab-arm/v1/devices/{device_id}/camera/keyframes",
            stereo_camera_fields(args, {"project_id": args.project_id, "robot_id": args.robot_id, "device_id": device_id}, "stereo_right", now),
            right_name,
            right_bytes,
            right_type,
        )
        results["stereo_context"] = request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{device_id}/vision/stereo-context", payloads["stereo_context"])
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
