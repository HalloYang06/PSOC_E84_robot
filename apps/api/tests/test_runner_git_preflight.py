from __future__ import annotations

import os
import sys
import json
from types import SimpleNamespace
from pathlib import Path


RUNNER_APP = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_APP) not in sys.path:
    sys.path.insert(0, str(RUNNER_APP))

from runner import git_tools  # noqa: E402
from runner import main as runner_main  # noqa: E402


def test_git_preflight_checks_env_credential_without_exposing_value(monkeypatch) -> None:
    monkeypatch.setattr(
        git_tools,
        "_probe_git_version",
        lambda: {"ok": True, "returncode": 0, "stdout": "git version test", "stderr": ""},
    )
    monkeypatch.setitem(os.environ, "GITHUB_TOKEN_FOR_TEST", "secret-value")

    result = git_tools.build_git_preflight_result(
        {
            "kind": "git.preflight",
            "action": "sync",
            "dry_run": True,
            "repository_url": "https://github.com/example/repo.git",
            "branch": "develop",
            "credential_source": "runner_env",
            "credential_ref": "runner-local:GITHUB_TOKEN_FOR_TEST",
        }
    )

    assert result["ok"] is True
    assert result["credential_check"]["env_name"] == "GITHUB_TOKEN_FOR_TEST"
    assert result["credential_check"]["env_present"] is True
    assert "secret-value" not in str(result)


def test_git_preflight_rejects_raw_github_token_reference(monkeypatch) -> None:
    monkeypatch.setattr(
        git_tools,
        "_probe_git_version",
        lambda: {"ok": True, "returncode": 0, "stdout": "git version test", "stderr": ""},
    )

    result = git_tools.build_git_preflight_result(
        {
            "kind": "git.preflight",
            "action": "sync",
            "dry_run": True,
            "repository_url": "https://github.com/example/repo.git",
            "credential_source": "runner_env",
            "credential_ref": "github_pat_" + "A" * 44,
        }
    )

    assert result["ok"] is False
    assert result["credential_ref"] == "<hidden-secret-like-ref>"
    assert any("raw GitHub token" in blocker for blocker in result["blockers"])


def test_git_preflight_stays_read_only_even_if_payload_requests_execution(monkeypatch) -> None:
    monkeypatch.setattr(
        git_tools,
        "_probe_git_version",
        lambda: {"ok": True, "returncode": 0, "stdout": "git version test", "stderr": ""},
    )

    result = git_tools.build_git_preflight_result(
        {
            "kind": "git.preflight",
            "action": "rollback",
            "dry_run": False,
            "repository_url": "https://github.com/example/repo.git",
            "target_ref": "HEAD~1",
            "credential_source": "manual_review",
        }
    )

    assert result["ok"] is False
    assert any("read-only" in blocker for blocker in result["blockers"])
    assert "reset" in result["blocked_now"]


def test_runner_relay_handler_acknowledges_and_completes_git_preflight(monkeypatch) -> None:
    monkeypatch.setattr(
        git_tools,
        "_probe_git_version",
        lambda: {"ok": True, "returncode": 0, "stdout": "git version test", "stderr": ""},
    )

    class FakeClient:
        def __init__(self) -> None:
            self.acks: list[dict[str, str | None]] = []
            self.completions: list[dict[str, str | None]] = []

        def ack_runner_message(self, runner_id: str, message_id: str, note: str | None = None) -> None:
            self.acks.append({"runner_id": runner_id, "message_id": message_id, "note": note})

        def complete_runner_message(
            self,
            runner_id: str,
            message_id: str,
            *,
            result_status: str,
            note: str | None = None,
        ) -> None:
            self.completions.append(
                {
                    "runner_id": runner_id,
                    "message_id": message_id,
                    "result_status": result_status,
                    "note": note,
                }
            )

    class FakeLog:
        def __init__(self) -> None:
            self.items: list[tuple[str, str]] = []

        def write(self, level: str, message: str) -> None:
            self.items.append((level, message))

    client = FakeClient()
    log = FakeLog()
    cfg = SimpleNamespace(runner_id="runner-git-preflight", runner_name="Git Preflight Runner", allow_hardware_access=False)
    handled = runner_main._handle_runner_relay_message(
        {
            "id": "message-git-preflight",
            "status": "pending",
            "body": json.dumps(
                {
                    "kind": "git.preflight",
                    "action": "sync",
                    "dry_run": True,
                    "repository_url": "https://github.com/example/repo.git",
                    "credential_source": "manual_review",
                }
            ),
        },
        client,  # type: ignore[arg-type]
        cfg,  # type: ignore[arg-type]
        log,  # type: ignore[arg-type]
    )

    assert handled is True
    assert client.acks and "read-only Git capability checks" in str(client.acks[0]["note"])
    assert client.completions[0]["result_status"] == "completed"
    assert "Git 协作预检结果" in str(client.completions[0]["note"])
