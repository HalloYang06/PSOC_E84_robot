from __future__ import annotations

import argparse
import base64
import json
import math
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_JOINTS = [
    "jian_hengxiang_joint",
    "jian_zongxiang_joint",
    "jian_xuanzhuan_joint",
    "zhou_zongxiang_joint",
    "wanbu_zongxiang_joint",
    "wanbu_hengxiang_joint",
]

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a safe read-only rehab-arm NanoPi sample telemetry batch.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--device-id", default="nanopi-readonly-sample")
    parser.add_argument("--robot-id", default="medical-rehab-arm")
    parser.add_argument("--urdf-zip", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


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


def request_multipart(api_base: str, path: str, fields: dict[str, str], file_name: str, file_bytes: bytes) -> dict[str, Any]:
    boundary = f"----rehab-readonly-{uuid.uuid4().hex}"
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
            b"Content-Type: image/png\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    url = f"{api_base.rstrip('/')}{path}"
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        method="POST",
        headers={"content-type": f"multipart/form-data; boundary={boundary}", "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: HTTP {exc.code} {detail[:600]}") from exc


def joints_from_urdf_zip(path_text: str) -> list[str]:
    if not path_text:
        return DEFAULT_JOINTS
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"URDF zip not found: {path}")
    with zipfile.ZipFile(path) as archive:
        urdf_names = [name for name in archive.namelist() if name.lower().endswith(".urdf")]
        if not urdf_names:
            raise RuntimeError(f"No .urdf file found in {path}")
        with archive.open(sorted(urdf_names)[0]) as handle:
            root = ElementTree.fromstring(handle.read())
    joints: list[str] = []
    for joint in root.findall("joint"):
        name = (joint.attrib.get("name") or "").strip()
        joint_type = (joint.attrib.get("type") or "").strip().lower()
        if name and joint_type != "fixed":
            joints.append(name)
    return joints or DEFAULT_JOINTS


def sample_payloads(args: argparse.Namespace) -> dict[str, Any]:
    now = time.time()
    joints = joints_from_urdf_zip(args.urdf_zip)
    positions = [round(math.sin(index + 1) * 0.35, 4) for index, _ in enumerate(joints)]
    velocities = [round(0.012 * (index + 1), 4) for index, _ in enumerate(joints)]
    efforts = [round(0.08 * (index + 1), 4) for index, _ in enumerate(joints)]
    motors = [
        {
            "motor_id": f"M{index + 1}",
            "joint_name": joint,
            "protocol": "readonly_status",
            "position": positions[index],
            "velocity": velocities[index],
            "torque": efforts[index],
            "current": round(0.45 + index * 0.07, 3),
            "temperature": round(31.5 + index * 0.8, 2),
            "voltage": 24.0,
            "error_code": 0,
            "enabled": False,
            "fault": False,
            "raw_can_id": hex(0x180 + index),
        }
        for index, joint in enumerate(joints)
    ]
    session_id = f"{args.device_id}-{int(now)}"
    common = {"project_id": args.project_id, "robot_id": args.robot_id, "device_id": args.device_id}
    return {
        "register": {
            **common,
            "device_type": "nanopi",
            "software_version": "readonly-sample-v1",
            "capabilities": ["linux_board_status", "can_readonly", "serial_readonly", "ros2_readonly", "camera_keyframe"],
        },
        "board_manifest": {
            **common,
            "manifest": {
                "schema_version": "linux_board_manifest_v1",
                "device_id": args.device_id,
                "robot_id": args.robot_id,
                "hostname": "NanoPi-readonly-sample",
                "platform": {"os": "Linux", "role": "NanoPi 只读数据节点"},
                "capabilities": {
                    "can_interfaces": [{"name": "can0", "kind": "socketcan", "operstate": "up", "mode": "listen-only"}],
                    "serial_devices": ["/dev/ttyUSB0"],
                    "camera_devices": ["/dev/video0"],
                    "usb_devices": [{"kind": "usb-camera", "description": "康复训练关键帧相机"}],
                    "ros2": {"available": True, "topics": ["/joint_states", "/tf", "/rehab_arm/safety_state"]},
                },
                "control_boundary": "readonly_discovery_only_not_motion_permission",
            },
        },
        "safety": {
            **common,
            "state": "limited",
            "motion_allowed": False,
            "emergency_stop": False,
            "m33_mode": "observe_only",
            "detail_code": "readonly_sample",
            "detail": "样例数据仅用于平台预览和数据闭环，不允许真实运动控制。",
            "heartbeat_age_ms": 36,
            "fault_code": "",
            "fault_message": "",
        },
        "motor": {
            **common,
            "ts_unix": now,
            "motors": motors,
            "joint_state": {"name": joints, "position": positions, "velocity": velocities, "effort": efforts},
            "source": "nanopi_readonly_sample",
        },
        "sensor": {
            **common,
            "ts_unix": now,
            "emg": {"left_biceps": 0.18, "left_triceps": 0.09},
            "heart_rate": 72,
            "imu": {"upper_arm_pitch": 8.4, "forearm_pitch": 17.2},
            "fatigue_score": 0.22,
            "intent_prediction": {"label": "reach_prepare", "confidence": 0.63},
            "model_outputs": [{"name": "spasm_risk", "value": 0.04}],
            "source": "nanopi_readonly_sample",
        },
        "manifest": {
            "manifest": {
                "schema_version": "rehab_arm_manifest_v1",
                "sessions": [
                    {
                        "schema_version": "rehab_arm_recording_session_v1",
                        "ok": True,
                        "session_id": session_id,
                        "project_id": args.project_id,
                        "device_id": args.device_id,
                        "robot_id": args.robot_id,
                        "file_name": f"{session_id}.jsonl",
                        "record_count": 240,
                        "summary": {
                            "schema_version": "rehab_arm_recording_summary_v1",
                            "topic_counts": {
                                "/joint_states": 80,
                                "/rehab_arm/motor_state": 80,
                                "/rehab_arm/safety_state": 4,
                                "/rehab_arm/sensor_state": 76,
                            },
                            "moving_joint_count": len(joints),
                            "motor_entry_count_min": len(motors),
                            "motor_entry_count_max": len(motors),
                            "motion_allowed_counts": {"true": 0, "false": 4, "missing": 0},
                        },
                        "quality_report": {
                            "schema_version": "rehab_arm_recording_quality_v1",
                            "ok": True,
                            "errors": [],
                            "warnings": ["样例数据用于 UI/数据闭环验证，不能替代真实硬件验收。"],
                            "criteria": {
                                "min_joint_messages": 2,
                                "min_moving_joints": min(1, len(joints)),
                                "require_motor_state": True,
                                "min_motor_entry_count": min(1, len(motors)),
                                "allow_motion_allowed_true": False,
                            },
                        },
                    }
                ],
            }
        },
        "sync_status": {
            "device_id": args.device_id,
            "project_id": args.project_id,
            "sync_status": "uploaded",
            "file_name": f"{session_id}.jsonl",
            "record_count": 240,
        },
        "simulation": {
            **common,
            "report": {
                "schema_version": "rehab_arm_sim_env_check_v1",
                "ok": True,
                "readiness": "ready_with_urdf_preview",
                "joint_contract": {"count": len(joints), "names": joints},
                "safety_note": "只读预览；真实运动控制必须由本地安全链路和人工强审决定。",
                "errors": [],
            },
        },
        "camera_fields": {
            **{key: str(value) for key, value in common.items()},
            "camera_id": "front",
            "frame_ts_unix": str(now),
            "image_format": "png",
            "width": "1",
            "height": "1",
            "detection_summary": "样例关键帧：训练桌面与上肢区域占位",
            "scene_summary": "只读视觉数据占位，用于总控台确认关键帧链路",
            "vla_context": "reach_prepare_observation_only",
        },
    }


def main() -> int:
    args = parse_args()
    payloads = sample_payloads(args)
    if args.dry_run:
        print(public_json({"ok": True, "dry_run": True, "payloads": payloads}))
        return 0

    api_base = args.api_base.rstrip("/")
    results = {
        "register": request_json(api_base, "POST", "/api/rehab-arm/v1/devices/register", payloads["register"]),
        "board_manifest": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{args.device_id}/board-manifest", payloads["board_manifest"]),
        "safety": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{args.device_id}/safety-state", payloads["safety"]),
        "motor": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{args.device_id}/motor-state", payloads["motor"]),
        "sensor": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{args.device_id}/sensor-state", payloads["sensor"]),
        "manifest": request_json(api_base, "POST", "/api/rehab-arm/v1/sessions/manifest", payloads["manifest"]),
        "sync_status": request_json(api_base, "POST", f"/api/rehab-arm/v1/sessions/{payloads['sync_status']['file_name'].removesuffix('.jsonl')}/sync-status", payloads["sync_status"]),
        "simulation": request_json(api_base, "POST", f"/api/rehab-arm/v1/devices/{args.device_id}/simulation-readiness", payloads["simulation"]),
        "camera": request_multipart(api_base, f"/api/rehab-arm/v1/devices/{args.device_id}/camera/keyframes", payloads["camera_fields"], "sample.png", PNG_1X1),
    }
    dashboard = request_json(api_base, "GET", "/api/rehab-arm/v1/devices/dashboard", {})
    matching_devices = [
        device
        for device in dashboard.get("data", {}).get("devices", [])
        if device.get("device_id") == args.device_id and device.get("project_id") == args.project_id
    ]
    print(
        public_json(
            {
                "ok": bool(matching_devices),
                "api_base": api_base,
                "project_id": args.project_id,
                "device_id": args.device_id,
                "joint_count": len(payloads["motor"]["joint_state"]["name"]),
                "uploaded": list(results.keys()),
                "dashboard_device_visible_for_project": bool(matching_devices),
            }
        )
    )
    return 0 if matching_devices else 1


if __name__ == "__main__":
    raise SystemExit(main())
