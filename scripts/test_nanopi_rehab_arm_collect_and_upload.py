from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nanopi-rehab-arm-collect-and-upload.py"


def test_collect_and_upload_dry_run_reads_fake_ros_topics(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ros2 = fake_bin / ("ros2.bat" if os.name == "nt" else "ros2")
    if os.name == "nt":
        ros2.write_text(
            "@echo off\r\n"
            "set topic=\r\n"
            "for %%A in (%*) do set topic=%%~A\r\n"
            "if \"%topic%\"==\"/joint_states\" (\r\n"
            "  echo name: [jian_hengxiang_joint, zhou_zongxiang_joint]\r\n"
            "  echo position: [0.12, -0.34]\r\n"
            "  echo velocity: [0.01, 0.02]\r\n"
            "  echo effort: [0.1, 0.2]\r\n"
            ") else if \"%topic%\"==\"/rehab_arm/safety_state\" (\r\n"
            "  echo state: limited\r\n"
            "  echo motion_allowed: false\r\n"
            "  echo m33_mode: observe_only\r\n"
            "  echo heartbeat_age_ms: 28\r\n"
            ") else (\r\n"
            "  echo heart_rate: 72\r\n"
            "  echo fatigue_score: 0.2\r\n"
            ")\r\n",
            encoding="utf-8",
        )
    else:
        ros2.write_text(
            "#!/usr/bin/env sh\n"
            "topic=\"\"\n"
            "for arg in \"$@\"; do topic=\"$arg\"; done\n"
            "if [ \"$topic\" = \"/joint_states\" ]; then\n"
            "  printf 'name: [jian_hengxiang_joint, zhou_zongxiang_joint]\\nposition: [0.12, -0.34]\\nvelocity: [0.01, 0.02]\\neffort: [0.1, 0.2]\\n'\n"
            "elif [ \"$topic\" = \"/rehab_arm/safety_state\" ]; then\n"
            "  printf 'state: limited\\nmotion_allowed: false\\nm33_mode: observe_only\\nheartbeat_age_ms: 28\\n'\n"
            "else\n"
            "  printf 'heart_rate: 72\\nfatigue_score: 0.2\\n'\n"
            "fi\n",
            encoding="utf-8",
        )
        ros2.chmod(0o755)

    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        [
            "python",
            str(SCRIPT),
            "--project-id",
            "project-a",
            "--device-id",
            "nanopi-a",
            "--robot-id",
            "arm-a",
            "--output-dir",
            str(tmp_path / "out"),
            "--skip-scan",
            "--dry-run",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    report = json.loads(result.stdout)
    agent = report["agent_result"]

    assert report["ok"] is True
    assert report["safety_boundary"] == "read_only_collection_only_no_can_ros_serial_writes"
    assert set(report["collected"]) == {"joint", "safety", "sensor"}
    assert agent["payloads"]["motor"]["joint_state"]["name"] == ["jian_hengxiang_joint", "zhou_zongxiang_joint"]
    assert agent["payloads"]["safety"]["motion_allowed"] is False
    assert agent["payloads"]["sensor"]["heart_rate"] == 72
    assert agent["payloads"]["manifest"]["manifest"]["sessions"][0]["quality_report"]["ok"] is True


def test_collect_and_upload_handles_missing_ros_without_upload(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "python",
            str(SCRIPT),
            "--project-id",
            "project-a",
            "--device-id",
            "nanopi-no-ros",
            "--output-dir",
            str(tmp_path / "out"),
            "--skip-scan",
            "--dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    report = json.loads(result.stdout)
    session = report["agent_result"]["payloads"]["manifest"]["manifest"]["sessions"][0]

    assert report["ok"] is True
    assert session["quality_report"]["ok"] is False
    assert "需要关节状态" in session["quality_report"]["errors"][0]


def test_collect_and_upload_passes_existing_stereo_keyframes_to_agent(tmp_path: Path) -> None:
    left = tmp_path / "left.jpg"
    right = tmp_path / "right.jpg"
    left.write_bytes(b"fake-left")
    right.write_bytes(b"fake-right")
    result = subprocess.run(
        [
            "python",
            str(SCRIPT),
            "--project-id",
            "project-a",
            "--device-id",
            "nanopi-stereo",
            "--output-dir",
            str(tmp_path / "out"),
            "--skip-scan",
            "--skip-ros",
            "--left-keyframe-file",
            str(left),
            "--right-keyframe-file",
            str(right),
            "--left-camera-index",
            "0",
            "--right-camera-index",
            "1",
            "--left-flip",
            "hv",
            "--right-flip",
            "hv",
            "--flip-applied-before-detection",
            "--dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    report = json.loads(result.stdout)
    stereo = report["agent_result"]["payloads"]["stereo_context"]
    mapping = stereo["capture_loop"]["camera_mapping"]

    assert report["ok"] is True
    assert report["stereo_keyframes"] == {"left": str(left), "right": str(right)}
    assert stereo["left_camera_id"] == "stereo_left"
    assert stereo["right_camera_id"] == "stereo_right"
    assert mapping["logical_left"]["opencv_index"] == 0
    assert mapping["logical_right"]["opencv_index"] == 1
    assert mapping["logical_left"]["flip"] == "hv"
    assert mapping["logical_right"]["flip"] == "hv"
    assert mapping["logical_right"]["flip_applied_before_detection"] is True
    assert stereo["control_boundary"] == "stereo_vision_context_only_not_motion_permission"


def test_collect_and_upload_does_not_invent_camera_indices_for_forwarded_files(tmp_path: Path) -> None:
    left = tmp_path / "left.jpg"
    right = tmp_path / "right.jpg"
    left.write_bytes(b"fake-left")
    right.write_bytes(b"fake-right")
    result = subprocess.run(
        [
            "python",
            str(SCRIPT),
            "--project-id",
            "project-a",
            "--device-id",
            "nanopi-stereo",
            "--output-dir",
            str(tmp_path / "out"),
            "--skip-scan",
            "--skip-ros",
            "--left-keyframe-file",
            str(left),
            "--right-keyframe-file",
            str(right),
            "--dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    mapping = json.loads(result.stdout)["agent_result"]["payloads"]["stereo_context"]["capture_loop"]["camera_mapping"]

    assert mapping["logical_left"]["opencv_index"] is None
    assert mapping["logical_right"]["opencv_index"] is None
    assert mapping["mapping_state"] == "waiting_physical_index_confirmation"


def test_collect_and_upload_forwards_end_effector_detector_args(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script_copy = scripts_dir / "nanopi-rehab-arm-collect-and-upload.py"
    script_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    fake_agent = scripts_dir / "nanopi-rehab-arm-readonly-agent.py"
    fake_agent.write_text(
        "import json, sys\n"
        "print(json.dumps({'argv': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    fake_model = tmp_path / "best.onnx"
    fake_model.write_bytes(b"onnx")

    result = subprocess.run(
        [
            sys.executable,
            str(script_copy),
            "--project-id",
            "project-a",
            "--device-id",
            "nanopi-stereo",
            "--output-dir",
            str(tmp_path / "out"),
            "--skip-scan",
            "--skip-ros",
            "--end-effector-onnx",
            str(fake_model),
            "--end-effector-conf",
            "0.21",
            "--end-effector-nms",
            "0.37",
            "--end-effector-imgsz",
            "416",
            "--dry-run",
        ],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    argv = json.loads(result.stdout)["agent_result"]["argv"]

    assert "--end-effector-onnx" in argv
    assert argv[argv.index("--end-effector-onnx") + 1] == str(fake_model)
    assert argv[argv.index("--end-effector-conf") + 1] == "0.21"
    assert argv[argv.index("--end-effector-nms") + 1] == "0.37"
    assert argv[argv.index("--end-effector-imgsz") + 1] == "416"
