"""C3-HTTP acceptance walk — verifies the full HTTP pipeline platform↔runner↔CLI.

Unlike scripts/cli-bridge-walk-2026-05-07.py (which uses a FakeClient and skips
HTTP), this script:
  1. POST /api/runners/register via real PlatformClient
  2. INSERT a pending CollaborationMessage(message_type="runner_command",
     recipient_type="runner", recipient_id=runner_id) directly into SQLite to
     simulate the platform dispatching a prompt
  3. PlatformClient.fetch_runner_inbox (GET /api/runners/{id}/inbox) — proves
     the runner can see the message via real HTTP
  4. _handle_runner_relay_message → cli_bridge → real claude.cmd
  5. PlatformClient.complete_runner_message (POST .../complete) — proves the
     AI reply lands back on the platform's collaboration_messages row

Requires:
  - API server already running on http://127.0.0.1:8000 (verified via /api/health)
  - claude CLI on PATH (where claude works)
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "runner"))

from runner.client import PlatformClient  # noqa: E402
from runner.config import RunnerConfig, ensure_dirs  # noqa: E402
from runner.logs import LogCollector  # noqa: E402
import runner.main as runner_main  # noqa: E402


API_BASE = "http://127.0.0.1:8000"
DB_PATH = REPO_ROOT / "apps" / "api" / "ai_collab.db"
WALK_PROVIDER = (os.environ.get("WALK_PROVIDER") or "claude").strip().lower()
if WALK_PROVIDER not in {"claude", "codex", "qwen"}:
    raise SystemExit(f"WALK_PROVIDER must be claude|codex|qwen (got {WALK_PROVIDER!r})")
RUNNER_ID = f"runner-c3-http-{WALK_PROVIDER}-{uuid.uuid4().hex[:6]}"
RUNNER_NAME = f"C3 HTTP Walk {RUNNER_ID[-6:]}"
CLI_TIMEOUT_SECONDS = 600 if WALK_PROVIDER == "codex" else 180


def insert_pending_message(message_id: str, body: str, title: str, project_id: str) -> None:
    """Bypass the privileged create_runner_command endpoint by inserting directly.

    This simulates "platform UI dispatched a prompt" without needing a logged-in
    human user with project write permission. project_id must be a real row in
    the projects table — RunnerRelayMessageRead requires it as a non-null string.
    """
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO collaboration_messages
                (id, project_id, message_type, title, body, sender_type, sender_id,
                 recipient_type, recipient_id, status, created_at, updated_at)
            VALUES
                (?, ?, 'runner_command', ?, ?, 'human', 'c3-walk-tester',
                 'runner', ?, 'pending', ?, ?)
            """,
            (message_id, project_id, title, body, RUNNER_ID, now, now),
        )
        conn.commit()


def fetch_message_status(message_id: str) -> dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, status, body FROM collaboration_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
    return dict(row) if row else {}


def fetch_message_history(message_id: str) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%history%'"
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    print(f"[walk] API_BASE={API_BASE}")
    print(f"[walk] DB_PATH={DB_PATH} exists={DB_PATH.is_file()}")
    print(f"[walk] WALK_PROVIDER={WALK_PROVIDER} CLI_TIMEOUT={CLI_TIMEOUT_SECONDS}s")
    print(f"[walk] RUNNER_ID={RUNNER_ID}")

    if not DB_PATH.is_file():
        print(f"[walk] FAIL — database not found at {DB_PATH}")
        return 2

    walk_dir = REPO_ROOT / "artifacts" / "c3-http-walk"
    workdir = walk_dir / "runner-workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    cfg = RunnerConfig(
        runner_id=RUNNER_ID,
        runner_name=RUNNER_NAME,
        platform_api_url=API_BASE,
        runner_token="change-me",
        workdir=workdir,
        allow_hardware_access=False,
        max_concurrent_tasks=1,
        heartbeat_seconds=15,
        poll_seconds=10,
        cli_provider=WALK_PROVIDER,
        cli_executor_path=None,
        cli_timeout_seconds=CLI_TIMEOUT_SECONDS,
    )
    ensure_dirs(cfg)
    log = LogCollector(workdir / "logs" / "c3-http.log")
    client = PlatformClient(base_url=API_BASE, runner_id=RUNNER_ID, runner_token="change-me")

    print("\n[walk step 1] register runner via real HTTP")
    try:
        reg = client.register(
            runner_id=RUNNER_ID,
            runner_name=RUNNER_NAME,
            capabilities=["git", "runner.inbox", "runner.prompt.relay"],
            hardware_access=False,
        )
        print(f"  -> register response: {json.dumps(reg, ensure_ascii=False)[:200]}")
    except Exception as exc:
        print(f"  -> register FAILED: {exc}")
        return 3

    message_id = f"msg-c3-http-{uuid.uuid4().hex[:8]}"
    body = "请只回复一行：最终回复：pong-c3-http"
    title = "C3 HTTP 端到端 ping"
    project_id = "proj_ai_collab"

    print(f"\n[walk step 2] insert pending message id={message_id} project={project_id} into SQLite (sim platform dispatch)")
    insert_pending_message(message_id, body, title, project_id)
    snap = fetch_message_status(message_id)
    print(f"  -> initial DB row: {snap}")

    print("\n[walk step 3] PlatformClient.fetch_runner_inbox via real HTTP")
    inbox = client.fetch_runner_inbox(RUNNER_ID, limit=10)
    inbox_ids = [str(m.get("id")) for m in inbox]
    print(f"  -> inbox returned {len(inbox)} messages, ids={inbox_ids}")
    if message_id not in inbox_ids:
        print(f"  -> FAIL — our message {message_id} not in inbox response")
        return 4
    target = next(m for m in inbox if str(m.get("id")) == message_id)

    print("\n[walk step 4] _handle_runner_relay_message → cli_bridge → real claude.cmd")
    t0 = time.time()
    try:
        handled = runner_main._handle_runner_relay_message(target, client, cfg, log)
    except Exception as exc:
        print(f"  -> handler raised: {exc}")
        handled = False
    dt = time.time() - t0
    print(f"  -> handled={handled} elapsed={dt:.1f}s")

    print("\n[walk step 5] read DB to confirm complete_runner_message landed")
    final = fetch_message_status(message_id)
    print(f"  -> final DB row: status={final.get('status')!r}")

    inbox_after = client.fetch_runner_inbox(RUNNER_ID, limit=10)
    after_ids = [str(m.get("id")) for m in inbox_after]
    print(f"  -> inbox after handler: {len(inbox_after)} messages, ids={after_ids}")

    summary = {
        "api_base": API_BASE,
        "runner_id": RUNNER_ID,
        "message_id": message_id,
        "register_response": reg,
        "elapsed_seconds": round(dt, 2),
        "handled": handled,
        "inbox_before_ids": inbox_ids,
        "inbox_after_ids": after_ids,
        "db_initial_status": snap.get("status"),
        "db_final_status": final.get("status"),
        "inbox_dir_remaining": [p.name for p in (workdir / "inbox").glob("*.json")],
        "inbox_dir_processed": [p.name for p in (workdir / "inbox" / "processed").glob("*.json")],
    }
    summary_path = walk_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[walk] summary -> {summary_path}")

    success = (
        handled is True
        and final.get("status") == "completed"
        and message_id not in after_ids
    )
    if success:
        print("\n[walk] PASS - full HTTP pipeline platform<->runner<->CLI verified")
        return 0
    print("\n[walk] FAIL - see summary.json")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
