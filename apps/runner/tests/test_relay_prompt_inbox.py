"""Regression tests for the runner relay plain-text prompt fallback.

Background: a previous bug let the platform queue plain prompts but the runner
only handled `serial.*` and `git.preflight` bodies, so a user typing a free-form
instruction in the dispatch panel would see it stay "pending" forever and never
reach the local Claude/Codex CLI.

The fix in ``apps/runner/runner/main.py`` writes a JSON file under
``RUNNER_WORKDIR/inbox/`` for every unrecognised message and reports the
message as completed so the platform UI clears the "排队中" state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.logs import LogCollector  # noqa: E402
from runner.main import _handle_runner_relay_message  # noqa: E402


class _FakeClient:
    def __init__(self) -> None:
        self.acks: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def ack_runner_message(self, runner_id: str, message_id: str, note: str | None = None) -> None:
        self.acks.append({"runner_id": runner_id, "message_id": message_id, "note": note})

    def complete_runner_message(self, runner_id: str, message_id: str, *, result_status: str, note: str | None) -> None:
        self.completions.append(
            {"runner_id": runner_id, "message_id": message_id, "result_status": result_status, "note": note}
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
    assert len(client.completions) == 1
    assert client.completions[0]["result_status"] == "completed"
    assert "[测试派单]" in client.completions[0]["note"]
    assert str(inbox_files[0]) in client.completions[0]["note"]


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
