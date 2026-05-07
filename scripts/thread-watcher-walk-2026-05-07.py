"""Thread-watcher acceptance walk (channel B · workstation = thread = terminal).

Mirrors scripts/cli-bridge-http-walk-2026-05-07.py for channel A. Verifies that
the platform-workstation-adapter --watch loop, started via
scripts/start-thread-watcher.ps1, can:

  1. discover a freshly-inserted workstation row in the DB
  2. pull a pending agent_command via real HTTP
  3. invoke the local claude.cmd through platform-provider-executor.py
  4. stream stdout/stderr to the terminal (watcher banner + claude output)
  5. write back agent_ack + agent_result rows and flip the original
     agent_command status to completed

Requires:
  - API server running on http://127.0.0.1:8000
  - claude CLI available (where claude works)
  - run from repo root (D:\\ai合作产品)

Outputs:
  - artifacts/thread-watcher-walk/run.log   (watcher stdout/stderr captured)
  - artifacts/thread-watcher-walk/summary.json
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "apps" / "api" / "ai_collab.db"
PROJECT_ID = "proj_ai_collab"
PROBE_TAG = uuid.uuid4().hex[:8]
WALK_PROVIDER = (os.environ.get("WALK_PROVIDER") or "claude").strip().lower()
if WALK_PROVIDER not in {"claude", "codex", "qwen"}:
    raise SystemExit(f"WALK_PROVIDER must be claude|codex|qwen (got {WALK_PROVIDER!r})")
WORKSTATION_CONFIG_ID = f"watcher-walk-{WALK_PROVIDER}-{PROBE_TAG}"
WORKSTATION_NAME = f"Thread Watcher Walk {WALK_PROVIDER} {PROBE_TAG}"
COMPUTER_NODE_ID = "runner-pc1"
MESSAGE_ID = f"msg-thread-watcher-{PROBE_TAG}"
PROBE_REPLY = f"pong-watcher-{PROBE_TAG}"
PROMPT_BODY = f"请只回复一行：最终回复：{PROBE_REPLY}"
PROMPT_TITLE = "Thread Watcher 端到端 ping"

WATCHER_RUNTIME_SECONDS = 240 if WALK_PROVIDER == "codex" else 90
SUMMARY_DIR = REPO_ROOT / "artifacts" / "thread-watcher-walk"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_workstation() -> str:
    """Create a temporary workstation row so the walk doesn't pollute real ones."""
    workstation_id = str(uuid.uuid4())
    now = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO project_thread_workstations
                (id, project_id, config_id, name, computer_node_id, ai_provider_id,
                 status, sort_order, extra_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', 0, '{}', ?, ?)
            """,
            (
                workstation_id,
                PROJECT_ID,
                WORKSTATION_CONFIG_ID,
                WORKSTATION_NAME,
                COMPUTER_NODE_ID,
                WALK_PROVIDER,
                now,
                now,
            ),
        )
        conn.commit()
    return workstation_id


def insert_agent_command() -> None:
    now = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO collaboration_messages
                (id, project_id, message_type, title, body, sender_type, sender_id,
                 recipient_type, recipient_id, status, created_at, updated_at)
            VALUES
                (?, ?, 'agent_command', ?, ?, 'human', 'thread-watcher-walk-tester',
                 'workstation', ?, 'pending', ?, ?)
            """,
            (
                MESSAGE_ID,
                PROJECT_ID,
                PROMPT_TITLE,
                PROMPT_BODY,
                WORKSTATION_CONFIG_ID,
                now,
                now,
            ),
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


def fetch_walk_messages() -> list[dict[str, Any]]:
    """Return everything tied to this walk: the agent_command + any ack/result rows."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, message_type, sender_type, sender_id, recipient_type, recipient_id,
                   status, body, created_at
            FROM collaboration_messages
            WHERE id = ?
               OR (project_id = ? AND recipient_id = ? AND created_at >= datetime('now', '-15 minutes'))
               OR (project_id = ? AND sender_id = ? AND created_at >= datetime('now', '-15 minutes'))
            ORDER BY created_at ASC
            """,
            (MESSAGE_ID, PROJECT_ID, WORKSTATION_CONFIG_ID, PROJECT_ID, WORKSTATION_CONFIG_ID),
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup(workstation_pk: str) -> None:
    """Remove the temp workstation. Leave the messages so they can be inspected."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM project_thread_workstations WHERE id = ?", (workstation_pk,))
        conn.commit()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    run_log = SUMMARY_DIR / "run.log"

    print(f"[walk] PROJECT_ID={PROJECT_ID}")
    print(f"[walk] WALK_PROVIDER={WALK_PROVIDER} WATCHER_RUNTIME_SECONDS={WATCHER_RUNTIME_SECONDS}")
    print(f"[walk] WORKSTATION_CONFIG_ID={WORKSTATION_CONFIG_ID}")
    print(f"[walk] MESSAGE_ID={MESSAGE_ID}")
    print(f"[walk] PROBE_REPLY={PROBE_REPLY}")
    print(f"[walk] DB_PATH={DB_PATH} exists={DB_PATH.is_file()}")

    if not DB_PATH.is_file():
        print(f"[walk] FAIL — database not found at {DB_PATH}")
        return 2

    print("\n[walk step 1] insert temporary workstation row")
    workstation_pk = insert_workstation()
    print(f"  -> workstation_pk={workstation_pk}")

    print("\n[walk step 2] insert pending agent_command into collaboration_messages")
    insert_agent_command()
    initial = fetch_message_status(MESSAGE_ID)
    print(f"  -> initial DB row: {initial}")

    print("\n[walk step 3] launch start-thread-watcher.ps1 via PowerShell")
    ps1 = REPO_ROOT / "scripts" / "start-thread-watcher.ps1"
    adapter = REPO_ROOT / "scripts" / "platform-workstation-adapter.py"
    use_direct = os.environ.get("WALK_DIRECT_ADAPTER", "0") == "1"
    if use_direct:
        cmd = [
            sys.executable,
            str(adapter),
            "--api-base",
            "http://127.0.0.1:8000",
            "--project-id",
            PROJECT_ID,
            "--workstation-id",
            WORKSTATION_CONFIG_ID,
            "--provider",
            WALK_PROVIDER,
            "--auto-ack",
            "--execute-provider-cli",
            "--executor-cwd",
            str(REPO_ROOT),
            "--watch",
            "--poll-seconds",
            "3",
        ]
    else:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "-ProjectId",
            PROJECT_ID,
            "-WorkstationId",
            WORKSTATION_CONFIG_ID,
            "-Provider",
            WALK_PROVIDER,
            "-PollSeconds",
            "3",
        ]
    print(f"  -> cmd: {' '.join(cmd)}")

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    log_lines: list[str] = []
    saw_banner = False
    saw_command = False
    saw_invoke = False
    saw_writeback = False
    saw_reply = False
    handler_dt = 0.0
    t_handler_start: float | None = None

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    deadline = time.time() + WATCHER_RUNTIME_SECONDS
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            stamped = f"[{time.strftime('%H:%M:%S')}] {line.rstrip()}"
            log_lines.append(stamped)
            print(stamped, flush=True)
            if "项目线程 watcher 启动准备" in line or "线程 watcher 已启动" in line:
                saw_banner = True
            if "收到" in line and "条平台指令" in line:
                saw_command = True
                t_handler_start = time.time()
            if "[正在调用" in line:
                saw_invoke = True
            if PROBE_REPLY in line:
                saw_reply = True
            if "[已回写平台]" in line:
                saw_writeback = True
                if t_handler_start is not None and handler_dt == 0.0:
                    handler_dt = time.time() - t_handler_start
                # writeback line is the terminal signal — adapter has already
                # flushed agent_result + flipped agent_command to completed.
                # Don't wait for the next readline (poll loop may starve us).
                print("\n[walk] saw [已回写平台] — terminating watcher", flush=True)
                break
            if time.time() > deadline:
                print("\n[walk] watcher runtime budget exhausted, terminating")
                break
    finally:
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass

    run_log.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\n[walk] watcher log -> {run_log}")

    final_msg = fetch_message_status(MESSAGE_ID)
    walk_msgs = fetch_walk_messages()
    print(f"\n[walk] final agent_command status: {final_msg.get('status')!r}")
    print(f"[walk] related rows ({len(walk_msgs)}):")
    for m in walk_msgs:
        body_preview = (m.get("body") or "")[:80].replace("\n", " ")
        print(f"  - id={m['id'][:18]}.. type={m['message_type']:18s} sender={m['sender_type']}/{(m.get('sender_id') or '')[:18]:18s} status={m['status']:10s} body={body_preview!r}")

    has_ack = any(m["message_type"] == "agent_ack" for m in walk_msgs)
    has_result = any(m["message_type"] == "agent_result" for m in walk_msgs)
    result_body_has_reply = any(
        m["message_type"] == "agent_result" and PROBE_REPLY in (m.get("body") or "")
        for m in walk_msgs
    )

    summary = {
        "probe_tag": PROBE_TAG,
        "walk_provider": WALK_PROVIDER,
        "project_id": PROJECT_ID,
        "workstation_config_id": WORKSTATION_CONFIG_ID,
        "message_id": MESSAGE_ID,
        "probe_reply": PROBE_REPLY,
        "watcher_runtime_seconds_budget": WATCHER_RUNTIME_SECONDS,
        "handler_elapsed_seconds": round(handler_dt, 2),
        "stdout_signals": {
            "saw_banner": saw_banner,
            "saw_command": saw_command,
            "saw_invoke": saw_invoke,
            "saw_reply": saw_reply,
            "saw_writeback": saw_writeback,
        },
        "db_initial_status": initial.get("status"),
        "db_final_status": final_msg.get("status"),
        "db_related_messages": walk_msgs,
        "db_has_agent_ack": has_ack,
        "db_has_agent_result": has_result,
        "db_result_body_has_reply": result_body_has_reply,
    }
    (SUMMARY_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"[walk] summary -> {SUMMARY_DIR / 'summary.json'}")

    print("\n[walk] cleaning up temp workstation row")
    try:
        cleanup(workstation_pk)
    except Exception as exc:
        print(f"  -> cleanup warning: {exc}")

    success = (
        saw_banner
        and saw_command
        and saw_reply
        and final_msg.get("status") == "completed"
        and has_result
        and result_body_has_reply
    )
    if success:
        print("\n[walk] PASS - thread watcher channel B verified end to end")
        return 0
    print("\n[walk] FAIL - see summary.json (signals + DB rows)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
