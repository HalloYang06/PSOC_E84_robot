"""Regression test for the main-loop wiring of cli_bridge into the relay fallback.

When ``cfg.cli_provider`` is set, ``_handle_runner_relay_message`` must:
  1. Still write the inbox JSON file.
  2. Invoke ``cli_bridge.dispatch_prompt_to_cli`` (we patch it to skip subprocess).
  3. Use the cli_bridge result for ``complete_runner_message``.
  4. Move the inbox file under ``inbox/processed/`` so the next poll skips it.

When ``cfg.cli_provider == "disabled"`` (default), behaviour must match the
original inbox-only path used in ``test_relay_prompt_inbox.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.logs import LogCollector  # noqa: E402
import runner.main as runner_main  # noqa: E402


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


def _make_cfg(tmp_path: Path, **overrides: Any) -> RunnerConfig:
    defaults: dict[str, Any] = dict(
        runner_id="runner-test",
        runner_name="Runner Test",
        platform_api_url="http://localhost:8000",
        runner_token="change-me",
        workdir=tmp_path,
        allow_hardware_access=False,
        max_concurrent_tasks=1,
        heartbeat_seconds=15,
        poll_seconds=10,
        cli_provider="disabled",
    )
    defaults.update(overrides)
    cfg = RunnerConfig(**defaults)
    ensure_dirs(cfg)
    return cfg


def test_provider_claude_invokes_cli_bridge_and_archives_inbox(tmp_path, monkeypatch) -> None:
    cfg = _make_cfg(tmp_path, cli_provider="claude")
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()
    captured: dict[str, Any] = {}

    def fake_dispatch(message, inbox_path, cfg_arg, log_arg):
        captured["inbox_path"] = inbox_path
        captured["message_id"] = message.get("id")
        captured["cli_provider"] = cfg_arg.cli_provider
        return {
            "ok": True,
            "result_status": "completed",
            "note": "AI 回复:已完成只读 git status 检查",
            "stdout": "AI 回复:已完成只读 git status 检查",
            "provider": "claude",
        }

    monkeypatch.setattr(runner_main, "dispatch_prompt_to_cli", fake_dispatch)

    handled = runner_main._handle_runner_relay_message(
        {
            "id": "msg-claude-wired",
            "title": "git 只读检查",
            "body": "请帮我跑一下 git status",
            "status": "pending",
            "project_id": "proj_x",
        },
        client,
        cfg,
        log,
    )

    assert handled is True
    assert captured["message_id"] == "msg-claude-wired"
    assert captured["cli_provider"] == "claude"
    assert isinstance(captured["inbox_path"], Path)

    assert len(client.completions) == 1
    completion = client.completions[0]
    assert completion["result_status"] == "completed"
    assert "AI 回复" in (completion["note"] or "")

    assert list((cfg.workdir / "inbox").glob("*.json")) == []
    archived = list((cfg.workdir / "inbox" / "processed").glob("*.json"))
    assert len(archived) == 1
    assert archived[0].name == "msg-claude-wired.json"


def test_provider_disabled_keeps_legacy_inbox_only_behaviour(tmp_path, monkeypatch) -> None:
    cfg = _make_cfg(tmp_path, cli_provider="disabled")
    log = LogCollector(cfg.workdir / "logs" / "test.log")
    client = _FakeClient()

    def fake_dispatch(*_args, **_kwargs):
        raise AssertionError("dispatch_prompt_to_cli must not be called when provider=disabled")

    monkeypatch.setattr(runner_main, "dispatch_prompt_to_cli", fake_dispatch)

    handled = runner_main._handle_runner_relay_message(
        {
            "id": "msg-disabled",
            "title": "随便发",
            "body": "hi",
            "status": "pending",
        },
        client,
        cfg,
        log,
    )

    assert handled is True
    assert len(client.acks) == 1
    assert len(client.completions) == 0

    inbox_files = list((cfg.workdir / "inbox").glob("*.json"))
    assert len(inbox_files) == 1
    archived = list((cfg.workdir / "inbox" / "processed").glob("*.json"))
    assert archived == []
