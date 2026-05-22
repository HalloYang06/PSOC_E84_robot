#!/usr/bin/env python
from __future__ import annotations

import importlib.util
import os
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

        def fake_app_server_turn(**kwargs):
            return {
                "ok": False,
                "returncode": 1,
                "stdout": "",
                "stderr": "app-server unavailable",
                "note": "Codex app-server delivery failed: app-server unavailable",
                "delivery_mode": "codex_app_server",
                "thread_id": kwargs.get("session_id"),
            }

        def fake_automation_turn(**kwargs):
            return {
                "ok": False,
                "recoverable": True,
                "returncode": None,
                "stdout": "",
                "stderr": "automation unavailable",
                "note": "桌面自动化不可用",
                "delivery_mode": "codex_desktop_ui",
                "desktop_visible": False,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_method": "codex_desktop_automation",
            }

        original_app_server = adapter._run_codex_app_server_turn
        original_env = os.environ.get("AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK")
        adapter._run_codex_desktop_ui_turn = fake_desktop_turn
        adapter._run_codex_app_server_turn = fake_app_server_turn
        original_automation = adapter._run_codex_desktop_automation_turn
        adapter._run_codex_desktop_automation_turn = fake_automation_turn
        os.environ["AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK"] = "1"
        try:
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
        finally:
            adapter._run_codex_app_server_turn = original_app_server
            adapter._run_codex_desktop_automation_turn = original_automation
            if original_env is None:
                os.environ.pop("AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK", None)
            else:
                os.environ["AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK"] = original_env

    assert result["ok"] is False
    assert result["recoverable"] is True
    assert result["delivery_mode"] == "codex_desktop_ui_required_failed"
    assert result["desktop_visible"] is True
    assert result["desktop_delivery_confirmed"] is False
    assert result["desktop_delivery_unconfirmed"] is True
    assert result["desktop_delivery_method"] == "codex_desktop_interrupt"
    assert "required_failed" in str(result)
    assert "session JSONL" not in str(result.get("note") or "")


def test_desktop_executor_interrupts_desktop_by_default_without_app_server() -> None:
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
                    "- message_id: `msg-app-server`",
                ]
            ),
            encoding="utf-8",
        )
        calls = {"app_server": 0, "desktop_ui": 0, "automation": 0}
        codex_home = Path(tmp) / ".codex"

        def fake_app_server_turn(**kwargs):
            calls["app_server"] += 1
            raise AssertionError("desktop-visible interrupt delivery should not use app-server")

        def fake_desktop_turn(**kwargs):
            calls["desktop_ui"] += 1
            return {
                "ok": True,
                "returncode": 0,
                "stdout": "sent",
                "stderr": "",
                "note": "已把这条平台派单发送到绑定的 Codex Desktop 线程。",
                "delivery_mode": "codex_desktop_ui",
                "desktop_visible": True,
                "desktop_delivery_confirmed": True,
                "thread_id": kwargs.get("session_id"),
                "desktop_thread_url": "codex://threads/00000000-0000-0000-0000-000000000000",
            }

        def fake_automation_turn(**kwargs):
            calls["automation"] += 1
            raise AssertionError("interrupt delivery should not use heartbeat automation first")

        original_app_server = adapter._run_codex_app_server_turn
        original_desktop = adapter._run_codex_desktop_ui_turn
        original_automation = adapter._run_codex_desktop_automation_turn
        original_home = os.environ.get("CODEX_HOME")
        try:
            os.environ["CODEX_HOME"] = str(codex_home)
            adapter._run_codex_app_server_turn = fake_app_server_turn
            adapter._run_codex_desktop_ui_turn = fake_desktop_turn
            adapter._run_codex_desktop_automation_turn = fake_automation_turn
            result = adapter.run_executor(
                template=adapter.CODEX_DESKTOP_UI_EXECUTOR,
                command_path=command_path,
                project_id="proj_ai_collab",
                workstation_id="platform-npc-2",
                provider="codex",
                message_id="msg-app-server",
                model=None,
                session_id="codex-session-00000000-0000-0000-0000-000000000000",
                cwd=str(ROOT),
                timeout_seconds=5,
            )
        finally:
            adapter._run_codex_app_server_turn = original_app_server
            adapter._run_codex_desktop_ui_turn = original_desktop
            adapter._run_codex_desktop_automation_turn = original_automation
            if original_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = original_home

    assert result["ok"] is True
    assert result["delivery_mode"] == "codex_desktop_ui"
    assert result["desktop_visible"] is True
    assert result["desktop_delivery_confirmed"] is True
    assert result["desktop_delivery_method"] == "codex_desktop_interrupt"
    assert calls == {"app_server": 0, "desktop_ui": 1, "automation": 0}


def test_desktop_automation_turn_writes_heartbeat_file() -> None:
    adapter = load_adapter()
    with TemporaryDirectory() as tmp:
        codex_home = Path(tmp) / ".codex"
        original_home = os.environ.get("CODEX_HOME")
        try:
            os.environ["CODEX_HOME"] = str(codex_home)
            result = adapter._run_codex_desktop_automation_turn(
                prompt_text="# 平台派单\n\n- message_id: `msg-app-server`\n",
                session_id="codex-session-00000000-0000-0000-0000-000000000000",
                message_id="msg-app-server",
                project_id="proj_ai_collab",
                workstation_id="platform-npc-2",
            )
            automation_path = Path(result["desktop_automation_path"])
            assert automation_path.exists()
            automation_contents = automation_path.read_text(encoding="utf-8")
        finally:
            if original_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = original_home

    assert result["ok"] is True
    assert result["desktop_delivery_method"] == "codex_desktop_automation"
    assert 'kind = "heartbeat"' in automation_contents
    assert 'status = "ACTIVE"' in automation_contents
    assert 'target_thread_id = "00000000-0000-0000-0000-000000000000"' in automation_contents
    assert "message_id: `msg-app-server`" in automation_contents


def test_desktop_executor_can_use_non_interrupting_automation_policy() -> None:
    adapter = load_adapter()
    with TemporaryDirectory() as tmp:
        command_path = Path(tmp) / "command.md"
        command_path.write_text("# 平台派单\n\n- message_id: `msg-no-sendkeys`\n", encoding="utf-8")
        calls = {"desktop_ui": 0}

        def fake_app_server_turn(**kwargs):
            return {
                "ok": False,
                "returncode": 1,
                "stdout": "",
                "stderr": "thread resume failed",
                "note": "Codex app-server delivery failed: thread resume failed",
                "delivery_mode": "codex_app_server",
                "thread_id": kwargs.get("session_id"),
            }

        def fake_desktop_turn(**kwargs):
            calls["desktop_ui"] += 1
            raise AssertionError("foreground desktop delivery should be opt-in")

        def fake_automation_turn(**kwargs):
            return {
                "ok": False,
                "recoverable": True,
                "returncode": None,
                "stdout": "",
                "stderr": "automation unavailable",
                "note": "桌面自动化不可用",
                "delivery_mode": "codex_desktop_ui",
                "desktop_visible": False,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_method": "codex_desktop_automation",
            }

        original_app_server = adapter._run_codex_app_server_turn
        original_desktop = adapter._run_codex_desktop_ui_turn
        original_automation = adapter._run_codex_desktop_automation_turn
        original_env = os.environ.get("AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK")
        original_policy = os.environ.get("AI_COLLAB_CODEX_DESKTOP_DELIVERY_POLICY")
        os.environ.pop("AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK", None)
        os.environ["AI_COLLAB_CODEX_DESKTOP_DELIVERY_POLICY"] = "automation"
        try:
            adapter._run_codex_app_server_turn = fake_app_server_turn
            adapter._run_codex_desktop_ui_turn = fake_desktop_turn
            adapter._run_codex_desktop_automation_turn = fake_automation_turn
            result = adapter.run_executor(
                template=adapter.CODEX_DESKTOP_UI_EXECUTOR,
                command_path=command_path,
                project_id="proj_ai_collab",
                workstation_id="platform-npc-2",
                provider="codex",
                message_id="msg-no-sendkeys",
                model=None,
                session_id="codex-session-00000000-0000-0000-0000-000000000000",
                cwd=str(ROOT),
                timeout_seconds=5,
            )
        finally:
            adapter._run_codex_app_server_turn = original_app_server
            adapter._run_codex_desktop_ui_turn = original_desktop
            adapter._run_codex_desktop_automation_turn = original_automation
            if original_env is not None:
                os.environ["AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK"] = original_env
            if original_policy is None:
                os.environ.pop("AI_COLLAB_CODEX_DESKTOP_DELIVERY_POLICY", None)
            else:
                os.environ["AI_COLLAB_CODEX_DESKTOP_DELIVERY_POLICY"] = original_policy

    assert result["ok"] is False
    assert result["recoverable"] is True
    assert result["desktop_delivery_confirmed"] is False
    assert result["delivery_mode"] == "codex_desktop_ui"
    assert result["desktop_visible"] is False
    assert result["desktop_delivery_method"] == "codex_desktop_automation"
    assert calls == {"desktop_ui": 0}


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


def test_desktop_dispatch_automation_can_be_paused_after_prompt_seen() -> None:
    adapter = load_adapter()
    with TemporaryDirectory() as tmp:
        original_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(Path(tmp) / ".codex")
        try:
            result = adapter._run_codex_desktop_automation_turn(
                prompt_text="message_id: `msg-pause`\n请只回复 ok。",
                session_id="codex-session-00000000-0000-0000-0000-000000000000",
                message_id="msg-pause",
                project_id="proj_ai_collab",
                workstation_id="platform-npc-5",
            )
            assert result["ok"] is True
            assert adapter._pause_codex_desktop_dispatch_automation(
                "msg-pause",
                automation_id=result["desktop_automation_id"],
            )
            contents = Path(result["desktop_automation_path"]).read_text(encoding="utf-8")
            assert 'status = "PAUSED"' in contents
            assert 'status = "ACTIVE"' not in contents
        finally:
            if original_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = original_home


if __name__ == "__main__":
    test_desktop_ui_unconfirmed_stays_recoverable()
    test_desktop_executor_interrupts_desktop_by_default_without_app_server()
    test_desktop_executor_can_use_non_interrupting_automation_policy()
    test_desktop_ui_delivery_exception_stays_recoverable()
    test_desktop_ui_auto_retries_until_prompt_is_confirmed()
    test_desktop_ui_focus_loss_auto_retries_until_prompt_is_confirmed()
    test_desktop_retry_dedupe_key_changes_with_retry_count()
    test_desktop_dispatch_automation_can_be_paused_after_prompt_seen()
    print("desktop delivery unconfirmed recoverable: ok")
