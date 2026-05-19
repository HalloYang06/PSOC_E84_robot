"""Regression tests for the runner relay plain-text prompt fallback.

Background: a previous bug let the platform queue plain prompts but the runner
only handled `serial.*` and `git.preflight` bodies, so a user typing a free-form
instruction in the dispatch panel would see it stay "pending" forever and never
reach the local Claude/Codex CLI.

The fix in ``apps/runner/runner/main.py`` writes a JSON file under
``RUNNER_WORKDIR/inbox/`` for every unrecognised message and acknowledges the
message as delivered. It must not mark the message completed until a CLI,
Desktop bridge, or adapter reports a real final result.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.hardware.device_capture import _build_preview_points, _build_preview_summary, _can_interface_from_interface, _parse_candump_line, _serial_port_from_interface, execute_device_capture_command  # noqa: E402
from runner.logs import LogCollector  # noqa: E402
from runner.main import _handle_runner_relay_message  # noqa: E402


class _FakeClient:
    def __init__(self) -> None:
        self.acks: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def ack_runner_message(self, runner_id: str, message_id: str, note: str | None = None) -> None:
        self.acks.append({"runner_id": runner_id, "message_id": message_id, "note": note})

    def complete_runner_message(
        self,
        runner_id: str,
        message_id: str,
        *,
        result_status: str,
        note: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.completions.append(
            {"runner_id": runner_id, "message_id": message_id, "result_status": result_status, "note": note, "metadata": metadata}
        )


def _make_cfg(tmp_path: Path) -> RunnerConfig:
    cfg = RunnerConfig(
        runner_id="runner-test",
        runner_name="Runner Test",
        platform_api_url="http://localhost:8000",
        runner_token="change-me",
        workdir=tmp_path,
        allow_hardware_access=False,
        max_concurrent_tasks=1,
        heartbeat_seconds=15,
        poll_seconds=10,
    )
    ensure_dirs(cfg)
    return cfg


def test_plain_prompt_persisted_to_inbox(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()
    message = {
        "id": "msg-001",
        "title": "测试派单",
        "body": "请把康复机械臂的串口扫一下",  # plain text, not JSON / not serial / not git.preflight
        "status": "pending",
        "project_id": "proj_rehab_arm",
        "task_id": "task_42",
    }

    handled = _handle_runner_relay_message(message, client, cfg, log)

    assert handled is True
    inbox_files = list((cfg.workdir / "inbox").glob("*.json"))
    assert len(inbox_files) == 1
    record = json.loads(inbox_files[0].read_text(encoding="utf-8"))
    assert record["id"] == "msg-001"
    assert record["body"] == "请把康复机械臂的串口扫一下"
    assert record["project_id"] == "proj_rehab_arm"
    assert record["received_at"]

    assert client.acks == [
        {
            "runner_id": "runner-test",
            "message_id": "msg-001",
            "note": "Runner Test accepted the prompt and wrote it to "
            f"{inbox_files[0]}.",
        }
    ]
    assert client.completions == []


def test_serial_command_still_short_circuits_before_inbox(tmp_path: Path) -> None:
    """Make sure adding the fallback didn't break the existing serial branch."""
    cfg = _make_cfg(tmp_path)
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()
    serial_body = json.dumps({"kind": "serial.usb.scan"})
    message = {
        "id": "msg-serial",
        "body": serial_body,
        "status": "pending",
    }

    handled = _handle_runner_relay_message(message, client, cfg, log)

    assert handled is True
    assert list((cfg.workdir / "inbox").glob("*.json")) == []
    assert len(client.completions) == 1
    # serial.usb.scan with hardware disabled returns "failed", not "completed"
    assert client.completions[0]["result_status"] == "failed"


def test_robotics_capture_command_short_circuits_before_inbox(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()
    body = json.dumps(
        {
            "kind": "robotics.capture.start",
            "project_id": "proj_x",
            "capture_id": "capture-test",
            "computer_node_id": "windows-desktop-main",
            "interface_id": "serial:COM1",
            "interface_kind": "serial",
            "sample_hz": 100,
            "channels": ["time", "raw.text"],
        }
    )

    handled = _handle_runner_relay_message({"id": "msg-capture", "body": body, "status": "pending"}, client, cfg, log)

    assert handled is True
    assert list((cfg.workdir / "inbox").glob("*.json")) == []
    assert len(client.acks) == 1
    assert len(client.completions) == 1
    assert client.completions[0]["result_status"] == "completed"
    assert client.completions[0]["metadata"]["runner_capability"] == "robotics.capture"
    assert client.completions[0]["metadata"]["runner_result"]["capture_id"] == "capture-test"
    manifest = cfg.workdir / "device-captures" / "proj_x" / "windows-desktop-main" / "serial-COM1" / "capture-test" / "manifest.json"
    assert manifest.exists()


def test_robotics_capture_start_runs_background_session_until_stop(tmp_path: Path, monkeypatch: Any) -> None:
    class _FakeSerial:
        def __init__(self, **_: Any) -> None:
            self.closed = False

        def __enter__(self) -> "_FakeSerial":
            return self

        def __exit__(self, *_: Any) -> None:
            self.closed = True

        def readline(self) -> bytes:
            time.sleep(0.01)
            return b"t=1,current=0.4\n"

        def read(self, _: int) -> bytes:
            return b""

    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=_FakeSerial))
    base_payload = {
        "project_id": "proj_bg",
        "capture_id": "capture-bg",
        "computer_node_id": "windows-desktop-main",
        "interface_id": "serial:COM9",
        "interface_kind": "serial",
        "sample_hz": 100,
        "channels": ["time", "motor.current"],
    }

    start = execute_device_capture_command(
        {"kind": "robotics.capture.start", **base_payload},
        allow_hardware_access=True,
        workdir=tmp_path,
    )
    assert start["result_status"] == "completed"
    assert start["result"]["capture_mode"] == "background_session"

    preview = tmp_path / "device-captures" / "proj_bg" / "windows-desktop-main" / "serial-COM9" / "capture-bg" / "preview.jsonl"
    deadline = time.time() + 2
    while time.time() < deadline and (not preview.exists() or not preview.read_text(encoding="utf-8").strip()):
        time.sleep(0.02)

    stop = execute_device_capture_command(
        {"kind": "robotics.capture.stop", **base_payload},
        allow_hardware_access=True,
        workdir=tmp_path,
    )

    assert stop["result_status"] == "completed"
    assert stop["result"]["sample_count"] > 0
    assert stop["result"]["byte_count"] > 0
    assert stop["result"]["capture_mode"] == "background_session"
    manifest = tmp_path / stop["result"]["manifest"]
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema"] == "runner_device_capture_result_v2"
    assert data["status"] == "captured"


def test_robotics_capture_stop_reports_waiting_repo_when_not_configured(tmp_path: Path) -> None:
    payload = {
        "kind": "robotics.capture.stop",
        "project_id": "proj_repo_wait",
        "capture_id": "capture-wait",
        "computer_node_id": "linux-board",
        "interface_id": "serial:ttyUSB0",
        "interface_kind": "serial",
        "sample_hz": 100,
        "channels": ["time", "raw.text"],
    }

    result = execute_device_capture_command(payload, allow_hardware_access=True, workdir=tmp_path)

    assert result["result_status"] == "failed"
    assert result["result"]["repo_sync"]["status"] == "waiting_for_repo"
    assert result["result"]["repo_sync"]["repo_relative_dir"] == "data/device-captures/proj_repo_wait/linux-board/serial-ttyUSB0/capture-wait"


def test_robotics_capture_stop_syncs_manifest_preview_to_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "runner@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runner"], cwd=repo, check=True)

    capture_dir = tmp_path / "device-captures" / "proj_repo" / "linux-board" / "serial-ttyUSB0" / "capture-sync"
    capture_dir.mkdir(parents=True)
    (capture_dir / "preview.jsonl").write_text('{"t":"2026-05-19T00:00:00Z","text":"ok"}\n', encoding="utf-8")
    payload = {
        "kind": "robotics.capture.stop",
        "project_id": "proj_repo",
        "capture_id": "capture-sync",
        "computer_node_id": "linux-board",
        "interface_id": "serial:ttyUSB0",
        "interface_kind": "serial",
        "sample_hz": 100,
        "channels": ["time", "raw.text"],
    }

    result = execute_device_capture_command(payload, allow_hardware_access=True, workdir=tmp_path, repo_root=repo)

    sync = result["result"]["repo_sync"]
    assert sync["status"] == "committed"
    assert sync["manifest"] == "data/device-captures/proj_repo/linux-board/serial-ttyUSB0/capture-sync/manifest.json"
    assert (repo / sync["manifest"]).exists()
    assert (repo / sync["preview"]).exists()
    assert (repo / "data/device-captures/proj_repo/linux-board/serial-ttyUSB0/capture-sync/checksum-summary.json").exists()
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=repo, check=True, capture_output=True, text=True)
    assert "Add device capture capture-sync" in log.stdout


def test_robotics_capture_stop_syncs_manifest_without_preview_to_git_repo(tmp_path: Path, monkeypatch: Any) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "runner@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runner"], cwd=repo, check=True)
    monkeypatch.setattr("runner.hardware.device_capture._capture_serial_preview", lambda *_args, **_kwargs: {"samples": [], "byte_count": 0, "error": "no data"})
    payload = {
        "kind": "robotics.capture.stop",
        "project_id": "proj_empty_repo",
        "capture_id": "capture-empty",
        "computer_node_id": "windows-pc",
        "interface_id": "serial:COM30",
        "interface_kind": "serial",
        "sample_hz": 100,
        "channels": ["time", "raw.text"],
    }

    result = execute_device_capture_command(payload, allow_hardware_access=True, workdir=tmp_path, repo_root=repo)

    sync = result["result"]["repo_sync"]
    assert result["result_status"] == "failed"
    assert sync["status"] == "committed"
    assert sync["manifest"] == "data/device-captures/proj_empty_repo/windows-pc/serial-COM30/capture-empty/manifest.json"
    assert sync["preview"] == ""
    assert (repo / sync["manifest"]).exists()
    assert not (repo / "data/device-captures/proj_empty_repo/windows-pc/serial-COM30/capture-empty/preview.jsonl").exists()


def test_linux_scanned_serial_interface_id_resolves_to_dev_path() -> None:
    assert _serial_port_from_interface("serial:ttyUSB0", None) == "/dev/ttyUSB0"
    assert _serial_port_from_interface("serial:ttyACM1", None) == "/dev/ttyACM1"
    assert _serial_port_from_interface("serial:/dev/ttyAMA0", None) == "/dev/ttyAMA0"
    assert _serial_port_from_interface("serial:COM7", None) == "COM7"
    assert _serial_port_from_interface("serial:ttyUSB0", "COM9") == "COM9"


def test_can_interface_and_candump_line_helpers() -> None:
    assert _can_interface_from_interface("can:can0", None) == "can0"
    assert _can_interface_from_interface("can0", None) == "can0"
    assert _can_interface_from_interface("can:can0", "can1") == "can1"
    assert _parse_candump_line("(1716100000.1) can0 123#DEADBEEF") == {"can_id": "123", "data_hex": "DEADBEEF"}


def test_preview_summary_extracts_numeric_fields_for_charting() -> None:
    summary = _build_preview_summary(
        [
            {"t": "2026-05-19T00:00:00Z", "bytes": 12, "text": "current=0.4,velocity=100"},
            {"t": "2026-05-19T00:00:01Z", "bytes": 16, "text": "current=0.8,velocity=120"},
            {"t": "2026-05-19T00:00:02Z", "bytes": 10, "text": "@sample,0,1.5,3"},
        ]
    )

    assert summary["sample_count"] == 3
    fields = summary["numeric_fields"]
    assert fields["current"]["min"] == 0.4
    assert fields["current"]["max"] == 0.8
    assert fields["velocity"]["last"] == 120
    assert fields["sample.1"]["mean"] == 1.5


def test_preview_points_extract_series_for_waveform_chart() -> None:
    points = _build_preview_points(
        [
            {"t": "2026-05-19T00:00:00Z", "text": "current=0.4,velocity=100"},
            {"t": "2026-05-19T00:00:01Z", "text": "current=0.8,velocity=120"},
            {"t": "2026-05-19T00:00:02Z", "text": "@sample,0,1.5,3"},
        ]
    )

    assert points["sample_count"] == 3
    assert points["series"]["current"][0]["y"] == 0.4
    assert points["series"]["velocity"][1]["y"] == 120
    assert points["series"]["sample.2"][0]["y"] == 3


def test_robotics_can_capture_start_returns_clear_missing_candump(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("runner.hardware.device_capture.shutil.which", lambda name: None if name == "candump" else name)
    payload = {
        "project_id": "proj_can",
        "capture_id": "capture-can",
        "computer_node_id": "linux-board",
        "interface_id": "can:can0",
        "interface_kind": "can",
        "sample_hz": 100,
        "channels": ["time", "can_id", "data_hex"],
    }

    start = execute_device_capture_command({"kind": "robotics.capture.start", **payload}, allow_hardware_access=True, workdir=tmp_path)
    stop = execute_device_capture_command({"kind": "robotics.capture.stop", **payload}, allow_hardware_access=True, workdir=tmp_path)

    assert start["result_status"] == "completed"
    assert stop["result_status"] == "failed"
    assert "candump is not installed" in stop["result"]["error"]


def test_message_without_id_returns_false(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()
    message = {"id": "", "body": "hello"}

    handled = _handle_runner_relay_message(message, client, cfg, log)

    assert handled is False
    assert client.acks == []
    assert client.completions == []
    assert list((cfg.workdir / "inbox").glob("*.json")) == []
