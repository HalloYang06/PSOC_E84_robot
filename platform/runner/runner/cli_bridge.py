"""Bridge runner inbox prompts to a local Claude / Codex CLI.

Reuses `scripts/platform-provider-executor.py` (the same script the workstation
adapter uses) instead of reimplementing Windows .cmd quoting / stdin piping.

The executor script writes the prompt to stdin of `claude` / `codex` and prints
the model output to stdout. We capture that and return it so the caller can
forward it to `complete_runner_message`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import RunnerConfig
from .git_tools import MAX_COMPLETION_NOTE_CHARS
from .logs import LogCollector


def locate_provider_executor(cfg: RunnerConfig) -> Path | None:
    """Find platform-provider-executor.py in three places, in priority order.

    1. cfg.cli_executor_path (explicit override)
    2. <workdir>/scripts/platform-provider-executor.py (where
       connect-ai-collab-runner.ps1 drops it for end users)
    3. monorepo dev path (when running from a checkout of the repo)
    """
    if cfg.cli_executor_path is not None:
        candidate = Path(cfg.cli_executor_path)
        return candidate if candidate.is_file() else None

    workdir_candidate = cfg.workdir / "scripts" / "platform-provider-executor.py"
    if workdir_candidate.is_file():
        return workdir_candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "scripts" / "platform-provider-executor.py"
        if candidate.is_file():
            return candidate

    return None


def _truncate_note(note: str) -> str:
    if len(note) <= MAX_COMPLETION_NOTE_CHARS:
        return note
    head = note[: MAX_COMPLETION_NOTE_CHARS - 80]
    return f"{head}\n…(truncated, original {len(note)} chars)"


def dispatch_prompt_to_cli(
    message: dict[str, Any],
    inbox_path: Path,
    cfg: RunnerConfig,
    log: LogCollector,
) -> dict[str, Any]:
    """Run the local provider CLI for one inbox prompt.

    Returns a dict with keys:
      - ok (bool)
      - result_status ("completed" | "failed")
      - note (str, already truncated to MAX_COMPLETION_NOTE_CHARS)
      - stdout (str, full)
      - provider (str)
    """
    provider = (cfg.cli_provider or "disabled").strip().lower()
    message_id = str(message.get("id") or "").strip()
    project_id = str(message.get("project_id") or "").strip()
    title = str(message.get("title") or "").strip()
    body = str(message.get("body") or "").strip()

    if provider not in {"claude", "codex"}:
        return {
            "ok": False,
            "result_status": "failed",
            "note": f"cli_provider={provider!r}, expected claude or codex",
            "stdout": "",
            "provider": provider,
        }

    executor = locate_provider_executor(cfg)
    if executor is None:
        note = (
            "Could not find scripts/platform-provider-executor.py. "
            f"Set RUNNER_CLI_EXECUTOR or drop the script under {cfg.workdir / 'scripts'}."
        )
        log.write("error", note)
        return {
            "ok": False,
            "result_status": "failed",
            "note": note,
            "stdout": "",
            "provider": provider,
        }

    prompt_file = inbox_path.with_suffix(".prompt.md")
    prompt_text = body or title or "(empty prompt)"
    try:
        prompt_file.write_text(prompt_text, encoding="utf-8")
    except OSError as exc:
        note = f"Failed to write prompt file {prompt_file}: {exc}"
        log.write("error", note)
        return {
            "ok": False,
            "result_status": "failed",
            "note": note,
            "stdout": "",
            "provider": provider,
        }

    argv = [
        sys.executable,
        str(executor),
        str(prompt_file),
        "--provider",
        provider,
        "--message-id",
        message_id or "ad-hoc",
        "--project-id",
        project_id,
        "--workstation-id",
        "",
    ]
    log.write("info", f"cli_bridge invoking provider={provider} message={message_id} executor={executor}")

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=cfg.cli_timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        note = (
            f"Provider {provider} CLI timed out after {cfg.cli_timeout_seconds}s. "
            "Adjust RUNNER_CLI_TIMEOUT_SECONDS or check whether the CLI is hanging on auth."
        )
        log.write("error", note)
        return {
            "ok": False,
            "result_status": "failed",
            "note": note,
            "stdout": "",
            "provider": provider,
        }
    except FileNotFoundError as exc:
        note = f"Failed to invoke {executor} via {sys.executable}: {exc}"
        log.write("error", note)
        return {
            "ok": False,
            "result_status": "failed",
            "note": note,
            "stdout": "",
            "provider": provider,
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    rc = completed.returncode

    if rc == 0 and stdout:
        body_note = stdout if not title else f"[{title}] {stdout}"
        return {
            "ok": True,
            "result_status": "completed",
            "note": _truncate_note(body_note),
            "stdout": stdout,
            "provider": provider,
        }

    failure_lines = [f"Provider {provider} CLI exited with rc={rc}."]
    if stdout:
        failure_lines.append(f"--- stdout ---\n{stdout}")
    if stderr:
        failure_lines.append(f"--- stderr ---\n{stderr}")
    if not stdout and not stderr:
        failure_lines.append("No output captured. Check whether the CLI is on PATH.")
    note = "\n".join(failure_lines)
    log.write("error", f"cli_bridge provider={provider} message={message_id} rc={rc}")
    return {
        "ok": False,
        "result_status": "failed",
        "note": _truncate_note(note),
        "stdout": stdout,
        "provider": provider,
    }
