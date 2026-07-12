"""Tests for ``runner.cli_bridge``.

Covers:
  - provider="disabled" / unknown -> short-circuit failed, no subprocess call
  - provider="claude" success -> subprocess called with expected argv,
    completion uses stdout in note, prompt file written
  - subprocess.TimeoutExpired -> failed result_status with timeout note
  - executor script missing -> failed result_status with discoverable error
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.cli_bridge import dispatch_prompt_to_cli, locate_provider_executor  # noqa: E402
from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.logs import LogCollector  # noqa: E402


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
        cli_executor_path=None,
        cli_timeout_seconds=30,
    )
    defaults.update(overrides)
    cfg = RunnerConfig(**defaults)
    ensure_dirs(cfg)
    return cfg


def _make_log(tmp_path: Path) -> LogCollector:
    return LogCollector(tmp_path / "logs" / "test.log")


def _stub_executor(tmp_path: Path) -> Path:
    executor = tmp_path / "scripts" / "platform-provider-executor.py"
    executor.parent.mkdir(parents=True, exist_ok=True)
    executor.write_text("# stub\n", encoding="utf-8")
    return executor


def test_disabled_provider_returns_failed_without_subprocess(tmp_path, monkeypatch) -> None:
    cfg = _make_cfg(tmp_path, cli_provider="disabled")
    log = _make_log(tmp_path)
    inbox_path = cfg.workdir / "inbox" / "msg-disabled.json"
    inbox_path.write_text("{}", encoding="utf-8")

    called = []

    def fake_run(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("subprocess.run should not be called when provider=disabled")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch_prompt_to_cli(
        {"id": "msg-disabled", "body": "hello"},
        inbox_path,
        cfg,
        log,
    )

    assert called == []
    assert result["ok"] is False
    assert result["result_status"] == "failed"
    assert "claude or codex" in result["note"]


def test_claude_success_invokes_executor_with_expected_argv(tmp_path, monkeypatch) -> None:
    executor = _stub_executor(tmp_path)
    cfg = _make_cfg(tmp_path, cli_provider="claude", cli_executor_path=executor)
    log = _make_log(tmp_path)
    inbox_path = cfg.workdir / "inbox" / "msg-claude.json"
    inbox_path.write_text("{}", encoding="utf-8")

    captured: dict[str, Any] = {}

    class _CompletedProcess:
        returncode = 0
        stdout = "Sure — running the read-only Git status check now.\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _CompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch_prompt_to_cli(
        {
            "id": "msg-claude",
            "title": "只读检查 git",
            "body": "请跑 git status，告诉我哪些文件没提交。",
            "project_id": "proj_x",
        },
        inbox_path,
        cfg,
        log,
    )

    assert result["ok"] is True
    assert result["result_status"] == "completed"
    assert "running the read-only Git status check" in result["note"]
    assert "[只读检查 git]" in result["note"]

    argv = captured["argv"]
    assert argv[0] == sys.executable
    assert argv[1] == str(executor)
    prompt_file = Path(argv[2])
    assert prompt_file.read_text(encoding="utf-8") == "请跑 git status，告诉我哪些文件没提交。"
    assert "--provider" in argv and argv[argv.index("--provider") + 1] == "claude"
    assert "--message-id" in argv and argv[argv.index("--message-id") + 1] == "msg-claude"
    assert "--project-id" in argv and argv[argv.index("--project-id") + 1] == "proj_x"
    assert captured["kwargs"]["timeout"] == cfg.cli_timeout_seconds
    assert captured["kwargs"]["shell"] is False


def test_subprocess_timeout_marks_failed(tmp_path, monkeypatch) -> None:
    executor = _stub_executor(tmp_path)
    cfg = _make_cfg(tmp_path, cli_provider="codex", cli_executor_path=executor, cli_timeout_seconds=7)
    log = _make_log(tmp_path)
    inbox_path = cfg.workdir / "inbox" / "msg-timeout.json"
    inbox_path.write_text("{}", encoding="utf-8")

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch_prompt_to_cli(
        {"id": "msg-timeout", "body": "tell me a story"},
        inbox_path,
        cfg,
        log,
    )

    assert result["ok"] is False
    assert result["result_status"] == "failed"
    assert "timed out" in result["note"]
    assert "7s" in result["note"]


def test_missing_executor_returns_failed_with_path_hint(tmp_path, monkeypatch) -> None:
    bogus = tmp_path / "scripts" / "does-not-exist.py"
    cfg = _make_cfg(tmp_path, cli_provider="claude", cli_executor_path=bogus)
    log = _make_log(tmp_path)
    inbox_path = cfg.workdir / "inbox" / "msg-missing.json"
    inbox_path.write_text("{}", encoding="utf-8")

    called = []

    def fake_run(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("subprocess.run should not be called when executor missing")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch_prompt_to_cli(
        {"id": "msg-missing", "body": "hi"},
        inbox_path,
        cfg,
        log,
    )

    assert called == []
    assert result["ok"] is False
    assert result["result_status"] == "failed"
    assert "platform-provider-executor.py" in result["note"]
    assert locate_provider_executor(cfg) is None
