from __future__ import annotations

import json
import subprocess
from pathlib import Path


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
