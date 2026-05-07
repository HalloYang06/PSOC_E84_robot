"""C3 acceptance walk — drives runner._handle_runner_relay_message against the real claude CLI.

Runs end-to-end without an API server: a FakeClient stands in for the platform,
RunnerConfig(cli_provider="claude") triggers the cli_bridge path, and we let
the real claude.cmd execute the prompt. Captures evidence under artifacts/c3-walk/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.logs import LogCollector  # noqa: E402
import runner.main as runner_main  # noqa: E402


class FakeClient:
    def __init__(self) -> None:
        self.acks: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def ack_runner_message(self, runner_id: str, message_id: str, note: str | None = None) -> None:
        self.acks.append({"runner_id": runner_id, "message_id": message_id, "note": note})
        print(f"[FakeClient ack] {message_id} note={note!r}")

    def complete_runner_message(self, runner_id: str, message_id: str, *, result_status: str, note: str | None) -> None:
        self.completions.append(
            {"runner_id": runner_id, "message_id": message_id, "result_status": result_status, "note": note}
        )
        print(f"[FakeClient complete] {message_id} status={result_status} note_len={len(note or '')}")


def main() -> int:
    walk_dir = REPO_ROOT / "artifacts" / "c3-walk"
    workdir = walk_dir / "runner-workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    cfg = RunnerConfig(
        runner_id="runner-c3-walk",
        runner_name="C3 Walk Runner",
        platform_api_url="http://localhost:0",
        runner_token="walk",
        workdir=workdir,
        allow_hardware_access=False,
        max_concurrent_tasks=1,
        heartbeat_seconds=15,
        poll_seconds=10,
        cli_provider="claude",
        cli_executor_path=None,
        cli_timeout_seconds=180,
    )
    ensure_dirs(cfg)

    log_path = workdir / "logs" / "c3-walk.log"
    log = LogCollector(log_path)
    client = FakeClient()

    message = {
        "id": "msg-c3-walk-001",
        "title": "C3 端到端 ping",
        "body": "请只回复一行：最终回复：pong-c3-walk",
        "status": "pending",
        "project_id": "proj_c3_walk",
    }

    print(f"[walk] cfg.workdir={cfg.workdir}")
    print(f"[walk] cli_provider={cfg.cli_provider}")
    print(f"[walk] dispatching message id={message['id']!r} body={message['body']!r}")
    t0 = time.time()
    handled = runner_main._handle_runner_relay_message(message, client, cfg, log)
    dt = time.time() - t0
    print(f"[walk] handled={handled} elapsed={dt:.1f}s")

    inbox_files = list((workdir / "inbox").glob("*.json"))
    archived = list((workdir / "inbox" / "processed").glob("*.json"))
    print(f"[walk] inbox/*.json={[p.name for p in inbox_files]}")
    print(f"[walk] inbox/processed/*.json={[p.name for p in archived]}")

    summary = {
        "handled": handled,
        "elapsed_seconds": round(dt, 2),
        "acks": client.acks,
        "completions": client.completions,
        "inbox_remaining": [p.name for p in inbox_files],
        "inbox_processed": [p.name for p in archived],
        "log_path": str(log_path),
    }
    summary_path = walk_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[walk] summary written to {summary_path}")

    completion = client.completions[0] if client.completions else {}
    note = (completion.get("note") or "")
    print("\n=== completion.note (first 800 chars) ===")
    print(note[:800])
    print("=== end note ===")

    if completion.get("result_status") == "completed" and "pong-c3-walk" in note:
        print("\n[walk] PASS — claude returned pong-c3-walk via the runner relay path")
        return 0
    print("\n[walk] FAIL — see summary.json + log for diagnostics")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
