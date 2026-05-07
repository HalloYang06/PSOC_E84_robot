#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def text(value: Any, fallback: str = "") -> str:
    next_value = str(value or "").strip()
    return next_value or fallback


def short_text(value: str, limit: int = 96) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)]}..."


def parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_message_text(message: Any) -> str:
    if isinstance(message, str):
        return short_text(message)
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return short_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(text(item.get("text")))
            elif isinstance(item, str):
                parts.append(item)
        return short_text(" ".join(part for part in parts if part))
    return ""


@dataclass
class ClaudeSessionSummary:
    session_id: str
    seat_name: str
    project_slug: str
    cwd: str
    git_branch: str
    last_activity_at: str
    started_at: str
    pid: int | None
    user_turns: int
    assistant_turns: int
    latest_user_message: str
    latest_assistant_message: str
    source_file: str
    source_kind: str
    live_process_seen: bool
    cwd_matches_filter: bool


def scan_session_file(path: Path, home: Path, registry: dict[str, dict[str, str]]) -> ClaudeSessionSummary | None:
    session_id = ""
    cwd = ""
    git_branch = ""
    latest_at = datetime.min.replace(tzinfo=timezone.utc)
    latest_user_message = ""
    latest_assistant_message = ""
    user_turns = 0
    assistant_turns = 0

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        session_id = text(item.get("sessionId"), session_id)
        cwd = text(item.get("cwd"), cwd)
        git_branch = text(item.get("gitBranch"), git_branch)
        timestamp = parse_iso(text(item.get("timestamp")))
        if timestamp > latest_at:
            latest_at = timestamp
        item_type = text(item.get("type")).lower()
        if item_type == "user":
            user_turns += 1
            latest_user_message = extract_message_text(item.get("message")) or latest_user_message
        elif item_type == "assistant":
            assistant_turns += 1
            latest_assistant_message = extract_message_text(item.get("message")) or latest_assistant_message

    if not session_id:
        session_id = path.stem

    project_slug = path.parent.name
    relative_parts = path.relative_to(home).parts
    if len(relative_parts) >= 3 and relative_parts[0] == "projects":
        project_slug = relative_parts[1]

    return ClaudeSessionSummary(
        session_id=session_id,
        seat_name=text(registry.get(session_id, {}).get("seat_name")),
        project_slug=project_slug,
        cwd=cwd,
        git_branch=git_branch,
        last_activity_at=latest_at.isoformat().replace("+00:00", "Z") if latest_at.year > 1971 else "",
        started_at=latest_at.isoformat().replace("+00:00", "Z") if latest_at.year > 1971 else "",
        pid=None,
        user_turns=user_turns,
        assistant_turns=assistant_turns,
        latest_user_message=latest_user_message,
        latest_assistant_message=latest_assistant_message,
        source_file=str(path),
        source_kind="project_jsonl",
        live_process_seen=False,
        cwd_matches_filter=True,
    )


def parse_epoch_millis(value: Any) -> datetime:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed <= 0:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromtimestamp(parsed / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def process_exists(pid: Any) -> bool:
    try:
        parsed = int(pid)
    except (TypeError, ValueError):
        return False
    if parsed <= 0:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {parsed}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    output = (result.stdout or "").strip().lower()
    if not output or "no tasks are running" in output:
        return False
    return f'"{parsed}"' in output or f",{parsed}," in output


def cwd_matches_filter(cwd: str, cwd_filter: str) -> bool:
    if not cwd_filter:
        return True
    return cwd_filter in cwd.lower()


def session_status(last_activity_at: str) -> str:
    parsed = parse_iso(last_activity_at)
    if parsed.year <= 1971:
        return "idle"
    diff_minutes = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 60))
    if diff_minutes <= 15:
        return "active"
    if diff_minutes <= 180:
        return "open"
    if diff_minutes <= 1440:
        return "idle"
    return "stale"


def scan_live_session_file(path: Path, registry: dict[str, dict[str, str]]) -> ClaudeSessionSummary | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    session_id = text(payload.get("sessionId"))
    cwd = text(payload.get("cwd"))
    if not session_id or not cwd:
        return None
    started_at = parse_epoch_millis(payload.get("startedAt"))
    live_process_seen = process_exists(payload.get("pid"))
    recently_exited = (
        started_at.year > 1971 and (datetime.now(timezone.utc) - started_at).total_seconds() <= 30 * 60
    )
    if not live_process_seen and not recently_exited:
        return None
    return ClaudeSessionSummary(
        session_id=session_id,
        seat_name=text(registry.get(session_id, {}).get("seat_name")),
        project_slug="(live-session)",
        cwd=cwd,
        git_branch="",
        last_activity_at=started_at.isoformat().replace("+00:00", "Z") if started_at.year > 1971 else "",
        started_at=started_at.isoformat().replace("+00:00", "Z") if started_at.year > 1971 else "",
        pid=int(payload.get("pid")) if str(payload.get("pid", "")).isdigit() else None,
        user_turns=0,
        assistant_turns=0,
        latest_user_message="",
        latest_assistant_message="",
        source_file=str(path),
        source_kind="live_session_file",
        live_process_seen=live_process_seen,
        cwd_matches_filter=True,
    )


def find_claude_home() -> Path:
    env_home = os.environ.get("CLAUDE_HOME", "").strip()
    if env_home:
        return Path(env_home)
    return Path.home() / ".claude"


def find_workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_registry_map(path: Path) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    items = payload.get("seats")
    if not isinstance(items, list):
        return {}

    result: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        session_id = text(item.get("session_id"))
        if not session_id:
            continue
        result[session_id] = {
            "seat_name": text(item.get("seat_name")),
            "provider": text(item.get("provider")),
        }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan local Claude Code session files and summarize distinguishable session/thread identities.",
    )
    parser.add_argument("--claude-home", default="", help="Override Claude home directory (defaults to ~/.claude)")
    parser.add_argument(
        "--registry",
        default="",
        help="Optional JSON registry produced by start-claude-seat.ps1 for stable seat-to-session mapping",
    )
    parser.add_argument("--cwd-filter", default="", help="Only include sessions whose cwd contains this text")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of sessions to print")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    claude_home = Path(args.claude_home).expanduser() if args.claude_home else find_claude_home()
    registry_path = (
        Path(args.registry).expanduser()
        if args.registry
        else find_workspace_root() / "artifacts" / "claude-seat-registry.json"
    )
    registry = load_registry_map(registry_path)
    projects_root = claude_home / "projects"
    sessions_root = claude_home / "sessions"
    if not projects_root.exists():
        payload = {
            "claude_home": str(claude_home),
            "registry_path": str(registry_path),
            "sessions": [],
            "warning": "projects directory not found",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    cwd_filter = text(args.cwd_filter).lower()
    sessions_by_id: dict[str, ClaudeSessionSummary] = {}
    for path in projects_root.rglob("*.jsonl"):
        summary = scan_session_file(path, claude_home, registry)
        if not summary:
            continue
        summary.cwd_matches_filter = cwd_matches_filter(summary.cwd, cwd_filter)
        if not summary.cwd_matches_filter or session_status(summary.last_activity_at) not in {"active", "open"}:
            continue
        sessions_by_id[summary.session_id] = summary

    if sessions_root.exists():
        for path in sessions_root.glob("*.json"):
            summary = scan_live_session_file(path, registry)
            if not summary:
                continue
            summary.cwd_matches_filter = cwd_matches_filter(summary.cwd, cwd_filter)
            registry_entry = registry.get(summary.session_id, {})
            if not (summary.cwd_matches_filter or summary.live_process_seen or registry_entry or summary.source_kind == "live_session_file"):
                continue
            existing = sessions_by_id.get(summary.session_id)
            if existing is None or parse_iso(summary.last_activity_at) > parse_iso(existing.last_activity_at):
                if existing:
                    summary.latest_user_message = existing.latest_user_message
                    summary.latest_assistant_message = existing.latest_assistant_message
                    summary.user_turns = existing.user_turns
                    summary.assistant_turns = existing.assistant_turns
                    summary.git_branch = existing.git_branch
                    summary.project_slug = existing.project_slug or summary.project_slug
                    if not summary.started_at:
                        summary.started_at = existing.started_at
                    if summary.pid is None:
                        summary.pid = existing.pid
                sessions_by_id[summary.session_id] = summary
            else:
                existing.live_process_seen = summary.live_process_seen or existing.live_process_seen
                existing.cwd_matches_filter = summary.cwd_matches_filter
                existing.source_kind = existing.source_kind or summary.source_kind
                if existing.source_kind != "project_jsonl":
                    existing.source_file = summary.source_file
                    existing.source_kind = summary.source_kind
                if not existing.started_at:
                    existing.started_at = summary.started_at
                if existing.pid is None:
                    existing.pid = summary.pid

    sessions = list(sessions_by_id.values())
    sessions.sort(key=lambda item: parse_iso(item.last_activity_at), reverse=True)
    sessions = sessions[: max(1, args.limit)]

    if args.json:
        print(
            json.dumps(
                {
                    "claude_home": str(claude_home),
                    "registry_path": str(registry_path),
                    "count": len(sessions),
                    "sessions": [asdict(item) for item in sessions],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Claude home: {claude_home}")
    print(f"Registry: {registry_path}")
    print(f"Sessions: {len(sessions)}")
    print("")
    for index, session in enumerate(sessions, start=1):
        print(f"[{index}] {session.session_id}")
        if session.seat_name:
            print(f"  seat: {session.seat_name}")
        print(f"  cwd: {session.cwd or '(unknown)'}")
        print(f"  project: {session.project_slug}")
        print(f"  branch: {session.git_branch or '(unknown)'}")
        print(f"  last_activity_at: {session.last_activity_at or '(unknown)'}")
        print(f"  started_at: {session.started_at or '(unknown)'}")
        print(f"  pid: {session.pid or '(unknown)'}")
        print(f"  turns: user {session.user_turns} / assistant {session.assistant_turns}")
        if session.latest_user_message:
            print(f"  latest_user: {session.latest_user_message}")
        if session.latest_assistant_message:
            print(f"  latest_assistant: {session.latest_assistant_message}")
        print(f"  source_file: {session.source_file}")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
