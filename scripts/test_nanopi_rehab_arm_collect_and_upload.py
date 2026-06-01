from __future__ import annotations

import json
import os
import subprocess
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
