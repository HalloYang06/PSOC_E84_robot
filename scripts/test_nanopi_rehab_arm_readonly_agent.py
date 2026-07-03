from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nanopi-rehab-arm-readonly-agent.py"


def run_agent(*args: str) -> dict:
    result = subprocess.run(
        ["python", str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)


def test_nanopi_readonly_agent_dry_run_maps_scan_and_joint_state(tmp_path: Path) -> None:
    scan_path = tmp_path / "scan.json"
    joint_path = tmp_path / "joint.json"
    safety_path = tmp_path / "safety.json"
    sensor_path = tmp_path / "sensor.json"
    scan_path.write_text(
        json.dumps(
            {
                "host": "nanopi-m5",
                "platform": "Linux-6.1",
                "interfaces": [
                    {"kind": "can", "name": "can0", "status": "available", "details": {"operstate": "up"}},
                    {"kind": "serial", "name": "/dev/ttyUSB0"},
                    {"kind": "camera", "name": "/dev/video0", "status": "available", "transport": "v4l2", "details": {"opencv_index_guess": 0, "sysfs_name": "USB Camera"}},
                    {"kind": "usb", "name": "USB camera"},
                    {"kind": "ros", "name": "ROS2 topics", "details": {"topics": ["/joint_states", "/tf"]}},
                ],
            }
        ),
        encoding="utf-8",
    )
    joint_path.write_text(
        json.dumps({"name": ["jian_hengxiang_joint", "zhou_zongxiang_joint"], "position": [0.12, -0.34], "velocity": [0.01, 0.02], "effort": [0.1, 0.2]}),
        encoding="utf-8",
    )
    safety_path.write_text(json.dumps({"state": "limited", "motion_allowed": False, "m33_mode": "observe_only", "heartbeat_age_ms": 25}), encoding="utf-8")
    sensor_path.write_text(json.dumps({"heart_rate": 73, "imu": {"forearm_pitch": 12.5}}), encoding="utf-8")

    output = run_agent(
        "--project-id",
        "project-a",
        "--device-id",
        "nanopi-a",
        "--robot-id",
        "arm-a",
        "--computer-node-id",
        "nanopi-computer-a",
        "--runner-id",
        "runner-nanopi-a",
        "--board-scan-json",
        str(scan_path),
        "--joint-state-json",
        str(joint_path),
        "--safety-state-json",
        str(safety_path),
        "--sensor-state-json",
        str(sensor_path),
        "--dry-run",
    )

    payloads = output["payloads"]
    assert output["ok"] is True
    assert payloads["register"]["computer_node_id"] == "nanopi-computer-a"
    assert payloads["register"]["runner_id"] == "runner-nanopi-a"
    assert payloads["board_manifest"]["computer_node_id"] == "nanopi-computer-a"
    assert payloads["board_manifest"]["runner_id"] == "runner-nanopi-a"
    assert payloads["board_manifest"]["manifest"]["computer_node_id"] == "nanopi-computer-a"
    assert payloads["board_manifest"]["manifest"]["runner_id"] == "runner-nanopi-a"
    assert payloads["board_manifest"]["manifest"]["hostname"] == "nanopi-m5"
    assert payloads["board_manifest"]["manifest"]["capabilities"]["can_interfaces"][0]["name"] == "can0"
    assert payloads["board_manifest"]["manifest"]["capabilities"]["serial_devices"] == ["/dev/ttyUSB0"]
    assert "/dev/video0" in payloads["board_manifest"]["manifest"]["capabilities"]["camera_devices"]
    camera_detail = payloads["board_manifest"]["manifest"]["capabilities"]["camera_device_details"][0]
    assert camera_detail["name"] == "/dev/video0"
    assert camera_detail["details"]["opencv_index_guess"] == 0
    assert payloads["board_manifest"]["manifest"]["capabilities"]["ros2"]["topics"] == ["/joint_states", "/tf"]
    assert payloads["motor"]["joint_state"]["name"] == ["jian_hengxiang_joint", "zhou_zongxiang_joint"]
    assert len(payloads["motor"]["motors"]) == 2
    assert payloads["motor"]["motors"][0]["protocol"] == "readonly_joint_state"
    assert payloads["safety"]["motion_allowed"] is False
    assert payloads["manifest"]["manifest"]["sessions"][0]["quality_report"]["ok"] is True


def test_nanopi_readonly_agent_marks_motion_allowed_snapshot_not_annotation_ready(tmp_path: Path) -> None:
    joint_path = tmp_path / "joint.json"
    safety_path = tmp_path / "safety.json"
    joint_path.write_text(json.dumps({"name": ["joint_1"], "position": [0.1]}), encoding="utf-8")
    safety_path.write_text(json.dumps({"state": "ok", "motion_allowed": True}), encoding="utf-8")

    output = run_agent(
        "--project-id",
        "project-a",
        "--device-id",
        "nanopi-a",
        "--joint-state-json",
        str(joint_path),
        "--safety-state-json",
        str(safety_path),
        "--dry-run",
    )

    session = output["payloads"]["manifest"]["manifest"]["sessions"][0]
    assert session["summary"]["motion_allowed_counts"]["true"] == 1
    assert session["quality_report"]["ok"] is False
    assert "不允许出现运动许可" in session["quality_report"]["errors"][0]


def test_nanopi_readonly_agent_dry_run_builds_stereo_context(tmp_path: Path) -> None:
    left = tmp_path / "left.jpg"
    right = tmp_path / "right.jpg"
    left.write_bytes(b"fake-left-jpeg")
    right.write_bytes(b"fake-right-jpeg")

    output = run_agent(
        "--project-id",
        "project-a",
        "--device-id",
        "nanopi-a",
        "--robot-id",
        "arm-a",
        "--left-keyframe-file",
        str(left),
        "--right-keyframe-file",
        str(right),
        "--stereo-baseline-m",
        "0.06",
        "--left-camera-index",
        "2",
        "--right-camera-index",
        "4",
        "--left-flip",
        "hv",
        "--right-flip",
        "none",
        "--flip-applied-before-detection",
        "--dry-run",
    )

    stereo = output["payloads"]["stereo_context"]
    mapping = stereo["capture_loop"]["camera_mapping"]
    assert stereo["schema_version"] == "stereo_rgb_yolo_context_v1"
    assert stereo["left_camera_id"] == "stereo_left"
    assert stereo["right_camera_id"] == "stereo_right"
    assert stereo["baseline_m"] == 0.06
    assert mapping["logical_left"]["opencv_index"] == 2
    assert mapping["logical_left"]["flip"] == "hv"
    assert mapping["logical_right"]["opencv_index"] == 4
    assert mapping["logical_right"]["flip"] == "none"
    assert mapping["logical_left"]["flip_applied_before_detection"] is True
    assert mapping["mapping_state"] == "provided_by_capture_args"
    assert stereo["image_pair_ref"]["left_image_url"].endswith("/camera/keyframes/stereo_left/latest/file")
    assert stereo["control_boundary"] == "stereo_vision_context_only_not_motion_permission"
    assert stereo["pixel_servo_hint"]["metric_depth_available"] is False


def test_nanopi_readonly_agent_can_attach_end_effector_onnx_detection() -> None:
    dataset_root = Path("D:/vla_dataset/20260627_213112")
    model = dataset_root / "runs/end_effector_v1_cpu_416_e10/weights/best.onnx"
    left = dataset_root / "yolo_end_effector_v1_with_negatives/images/val/mono_000035.jpg"
    if not model.exists() or not left.exists():
        pytest.skip("local end-effector ONNX fixture is not available")

    output = run_agent(
        "--project-id",
        "project-a",
        "--device-id",
        "nanopi-a",
        "--robot-id",
        "arm-a",
        "--left-keyframe-file",
        str(left),
        "--right-keyframe-file",
        str(left),
        "--end-effector-onnx",
        str(model),
        "--end-effector-conf",
        "0.1",
        "--dry-run",
    )

    stereo = output["payloads"]["stereo_context"]
    assert stereo["schema_version"] == "stereo_rgb_yolo_context_v1"
    assert stereo["detections"]["left"]
    assert stereo["end_effector_object"]["label"] == "end_effector"
    assert stereo["end_effector_object"]["confidence"] > 0
    assert stereo["end_effector_object"]["control_boundary"] == "detector_output_only_not_motion_permission"
