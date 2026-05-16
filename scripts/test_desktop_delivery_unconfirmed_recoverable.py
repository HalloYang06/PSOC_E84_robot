#!/usr/bin/env python
from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "scripts" / "platform-workstation-adapter.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("platform_workstation_adapter_under_test", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load adapter from {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_desktop_ui_unconfirmed_stays_recoverable() -> None:
    adapter = load_adapter()
    with TemporaryDirectory() as tmp:
        command_path = Path(tmp) / "command.md"
        command_path.write_text(
            "\n".join(
                [
                    "# 平台派单",
                    "",
                    "请继续推进平台自开发。",
                    "",
                    "- message_id: `msg-unconfirmed`",
                ]
            ),
            encoding="utf-8",
        )

        def fake_desktop_turn(**kwargs):
            return {
                "ok": False,
                "recoverable": True,
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "note": "桌面线程暂未确认收到这条派单。",
                "delivery_mode": "codex_desktop_ui",
                "desktop_visible": True,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_unconfirmed": True,
                "thread_id": kwargs.get("session_id"),
                "desktop_thread_url": "codex://threads/00000000-0000-0000-0000-000000000000",
            }

        adapter._run_codex_desktop_ui_turn = fake_desktop_turn
        result = adapter.run_executor(
            template=adapter.CODEX_DESKTOP_UI_EXECUTOR,
            command_path=command_path,
            project_id="proj_ai_collab",
            workstation_id="platform-npc-2",
            provider="codex",
            message_id="msg-unconfirmed",
            model=None,
            session_id="00000000-0000-0000-0000-000000000000",
            cwd=str(ROOT),
            timeout_seconds=5,
        )

    assert result["ok"] is False
    assert result["recoverable"] is True
    assert result["delivery_mode"] == "codex_desktop_ui"
    assert result["desktop_visible"] is True
    assert result["desktop_delivery_confirmed"] is False
    assert result["desktop_delivery_unconfirmed"] is True
    assert "required_failed" not in str(result)
    assert "session JSONL" not in str(result.get("note") or "")


def test_desktop_ui_delivery_exception_stays_recoverable() -> None:
    adapter = load_adapter()
    result = None

    original_run = adapter.subprocess.run

    def fake_run(*args, **kwargs):
        raise RuntimeError("clipboard focus was interrupted")

    try:
        adapter.subprocess.run = fake_run
        result = adapter._run_codex_desktop_ui_turn(
            prompt_text="message_id: `msg-interrupted`\n请继续。",
            session_id="codex-session-00000000-0000-0000-0000-000000000000",
            message_id="msg-interrupted",
            timeout_seconds=5,
        )
    finally:
        adapter.subprocess.run = original_run

    assert result["ok"] is False
    assert result["recoverable"] is True
    assert result["desktop_visible"] is True
    assert result["desktop_delivery_confirmed"] is False
    assert result["desktop_delivery_unconfirmed"] is True
    assert "待收口" in result["note"]
    assert "Codex Desktop UI delivery failed" not in result["note"]


def test_desktop_ui_auto_retries_until_prompt_is_confirmed() -> None:
    adapter = load_adapter()
    attempts = {"run": 0, "seen": 0}

    class FakeCompleted:
        def __init__(self):
            self.args = ["powershell"]
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    original_run = adapter.subprocess.run
    original_seen = adapter._wait_for_codex_desktop_prompt_seen
    original_attempts = adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS

    def fake_run(*args, **kwargs):
        attempts["run"] += 1
        return FakeCompleted()

    def fake_seen(**kwargs):
        attempts["seen"] += 1
        if attempts["seen"] >= 2:
            return {"session_file": "session.jsonl"}
        return None

    try:
        adapter.subprocess.run = fake_run
        adapter._wait_for_codex_desktop_prompt_seen = fake_seen
        adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS = 3
        result = adapter._run_codex_desktop_ui_turn(
            prompt_text="message_id: `msg-retry`\n请继续。",
            session_id="codex-session-00000000-0000-0000-0000-000000000000",
            message_id="msg-retry",
            timeout_seconds=5,
        )
    finally:
        adapter.subprocess.run = original_run
        adapter._wait_for_codex_desktop_prompt_seen = original_seen
        adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS = original_attempts

    assert result["ok"] is True
    assert result["desktop_delivery_confirmed"] is True
    assert result["desktop_delivery_attempts"] == 2
    assert result["desktop_delivery_auto_retried"] is True
    assert attempts["run"] == 2


def test_desktop_ui_focus_loss_auto_retries_until_prompt_is_confirmed() -> None:
    adapter = load_adapter()
    attempts = {"run": 0, "seen": 0}

    class FakeCompleted:
        def __init__(self, returncode: int, stderr: str = ""):
            self.args = ["powershell"]
            self.returncode = returncode
            self.stdout = ""
            self.stderr = stderr

    original_run = adapter.subprocess.run
    original_seen = adapter._wait_for_codex_desktop_prompt_seen
    original_attempts = adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS

    def fake_run(*args, **kwargs):
        attempts["run"] += 1
        if attempts["run"] == 1:
            return FakeCompleted(1, "desktop_focus_lost stage=before_submit; foreground=Browser")
        return FakeCompleted(0)

    def fake_seen(**kwargs):
        attempts["seen"] += 1
        return {"session_file": "session.jsonl"}

    try:
        adapter.subprocess.run = fake_run
        adapter._wait_for_codex_desktop_prompt_seen = fake_seen
        adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS = 3
        result = adapter._run_codex_desktop_ui_turn(
            prompt_text="message_id: `msg-focus-retry`\n请继续。",
            session_id="codex-session-00000000-0000-0000-0000-000000000000",
            message_id="msg-focus-retry",
            timeout_seconds=5,
        )
    finally:
        adapter.subprocess.run = original_run
        adapter._wait_for_codex_desktop_prompt_seen = original_seen
        adapter.CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS = original_attempts

    assert result["ok"] is True
    assert result["desktop_delivery_confirmed"] is True
    assert result["desktop_delivery_attempts"] == 2
    assert result["desktop_delivery_auto_retried"] is True
    assert attempts["run"] == 2


def test_desktop_retry_dedupe_key_changes_with_retry_count() -> None:
    adapter = load_adapter()
    command = {
        "id": "msg-retryable",
        "metadata": {
            "desktop_sync_retry_requested": True,
            "desktop_sync_retry_count": 2,
        },
    }
    assert adapter._desktop_retry_dedupe_key({"id": "msg-retryable"}) == "msg-retryable"
    assert adapter._desktop_retry_dedupe_key(command) == "msg-retryable:desktop-retry:2"


if __name__ == "__main__":
    test_desktop_ui_unconfirmed_stays_recoverable()
    test_desktop_ui_delivery_exception_stays_recoverable()
    test_desktop_ui_auto_retries_until_prompt_is_confirmed()
    test_desktop_ui_focus_loss_auto_retries_until_prompt_is_confirmed()
    test_desktop_retry_dedupe_key_changes_with_retry_count()
    print("desktop delivery unconfirmed recoverable: ok")
