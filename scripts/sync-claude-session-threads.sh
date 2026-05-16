#!/usr/bin/env bash
set -euo pipefail

SERVER=""
RUNNER_ID=""
PROJECT_ID=""
COMPUTER_NODE_ID=""
CLAUDE_HOME_VALUE=""
WORKSPACE_ROOT=""
TAKE="12"
MAX_AGE_HOURS="24"
MODEL="sonnet"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2 ;;
    --runner-id) RUNNER_ID="${2:-}"; shift 2 ;;
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --computer-node-id) COMPUTER_NODE_ID="${2:-}"; shift 2 ;;
    --claude-home) CLAUDE_HOME_VALUE="${2:-}"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="${2:-}"; shift 2 ;;
    --take) TAKE="${2:-}"; shift 2 ;;
    --max-age-hours) MAX_AGE_HOURS="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SERVER" || -z "$RUNNER_ID" || -z "$PROJECT_ID" || -z "$COMPUTER_NODE_ID" ]]; then
  echo "Required: --server --runner-id --project-id --computer-node-id" >&2
  exit 2
fi

BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

export BODY_FILE PROJECT_ID COMPUTER_NODE_ID CLAUDE_HOME_VALUE WORKSPACE_ROOT TAKE MAX_AGE_HOURS MODEL
python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


def clean(value: object, max_len: int = 240) -> str:
    return " ".join(str(value or "").split())[:max_len].strip()


def parse_dt(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def text_from_message(message: object) -> str:
    if isinstance(message, str):
        return clean(message, 120)
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return clean(content, 120)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return clean(" ".join(parts), 120)
    return ""


def claude_homes() -> list[Path]:
    explicit = clean(os.environ.get("CLAUDE_HOME_VALUE"), 1000)
    if explicit:
        return [Path(explicit).expanduser()]
    homes = []
    if os.environ.get("CLAUDE_HOME"):
        homes.append(Path(os.environ["CLAUDE_HOME"]).expanduser())
    homes.append(Path.home() / ".claude")
    for raw in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
        if raw:
            homes.append(Path(raw) / "Claude")
    deduped = []
    seen = set()
    for path in homes:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def add_or_merge(sessions: dict[str, dict], item: dict) -> None:
    sid = clean(item.get("session_id"), 120)
    if not sid:
        return
    prev = sessions.get(sid)
    if not prev:
        sessions[sid] = item
        return
    prev_dt = parse_dt(prev.get("last_activity_at"))
    next_dt = parse_dt(item.get("last_activity_at"))
    if next_dt and (not prev_dt or next_dt > prev_dt):
        sessions[sid] = {**prev, **{k: v for k, v in item.items() if v}}


take = max(1, int(os.environ.get("TAKE") or "12"))
max_age_hours = abs(int(os.environ.get("MAX_AGE_HOURS") or "24"))
cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
workspace_root = clean(os.environ.get("WORKSPACE_ROOT")) or None
workspace_norm = str(Path(workspace_root).expanduser()).replace("\\", "/").lower() if workspace_root else ""
checked = [str(path) for path in claude_homes()]
sessions: dict[str, dict] = {}

for root in claude_homes():
    live_root = root / "sessions"
    if live_root.exists():
        for path in live_root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            sid = clean(payload.get("sessionId"), 120)
            cwd = clean(payload.get("cwd"), 1000)
            if not sid or not cwd:
                continue
            if workspace_norm and workspace_norm not in cwd.replace("\\", "/").lower():
                continue
            started = payload.get("startedAt")
            last_dt = None
            if isinstance(started, (int, float)) and started > 0:
                last_dt = datetime.fromtimestamp(started / 1000, timezone.utc)
            if last_dt and last_dt < cutoff:
                continue
            add_or_merge(sessions, {
                "session_id": sid,
                "cwd": cwd,
                "last_activity_at": (last_dt or datetime.now(timezone.utc)).isoformat(),
                "source_kind": "live_session_file",
                "source_file": str(path),
                "project_slug": "(live-session)",
            })
    projects_root = root / "projects"
    if projects_root.exists():
        files = sorted(projects_root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:160]
        for path in files:
            sid = cwd = branch = latest_user = ""
            latest_dt = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
            except Exception:
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                sid = clean(item.get("sessionId"), 120) or sid
                cwd = clean(item.get("cwd"), 1000) or cwd
                branch = clean(item.get("gitBranch"), 120) or branch
                parsed = parse_dt(item.get("timestamp"))
                if parsed and parsed > latest_dt:
                    latest_dt = parsed
                if item.get("type") == "user":
                    latest_user = text_from_message(item.get("message")) or latest_user
            if not sid or not cwd:
                continue
            if workspace_norm and workspace_norm not in cwd.replace("\\", "/").lower():
                continue
            if latest_dt < cutoff:
                continue
            add_or_merge(sessions, {
                "session_id": sid,
                "cwd": cwd,
                "git_branch": branch,
                "last_activity_at": latest_dt.isoformat(),
                "source_kind": "project_jsonl",
                "source_file": str(path),
                "project_slug": path.parent.name,
                "latest_user_message": latest_user,
            })

skills = ["github-repo-bootstrap", "ai-collab-productizer", "continuous-orchestrator", "handoff-path-output", "verify-before-claim", "thread-bridge-writeback"]
rows = sorted(sessions.values(), key=lambda item: item.get("last_activity_at") or "", reverse=True)[:take]
workstations = []
for item in rows:
    sid = clean(item.get("session_id"), 120)
    slug = clean(item.get("project_slug")) or sid[:8]
    stamp = ""
    dt = parse_dt(item.get("last_activity_at"))
    if dt:
        stamp = " @ " + dt.strftime("%m-%d %H:%M")
    workstations.append({
        "workstation_id": f"claude-session-{sid}",
        "workstation_name": f"Claude / {slug} [{sid[:8]}]{stamp}",
        "workstation_status": "active" if item.get("source_kind") == "live_session_file" else "open",
        "cwd": clean(item.get("cwd"), 1000),
        "model": clean(os.environ.get("MODEL")),
        "description": "Synced from local Claude Code session files",
        "notes": clean(f"last_activity_at={item.get('last_activity_at')}; source={item.get('source_kind')}"),
        "ai_provider_id": "claude",
        "ai_provider_label": "Claude",
        "skill_loadout": skills,
        "metadata": {
            "connection_kind": "local",
            "provider_family": "claude",
            "workspace_root": workspace_root,
            "scan_status": "active_session_found",
        },
    })

if not workstations:
    slug = re.sub(r"[^a-z0-9]+", "-", os.environ["COMPUTER_NODE_ID"].lower()).strip("-") or "computer"
    workstations.append({
        "workstation_id": f"claude-manual-{slug}",
        "workstation_name": f"Claude / manual bind on {os.environ['COMPUTER_NODE_ID']}",
        "workstation_status": "needs_binding",
        "cwd": workspace_root,
        "model": clean(os.environ.get("MODEL")),
        "description": "Claude session files were not found yet; open Claude Code on this computer and scan again.",
        "notes": clean(f"Checked: {'; '.join(checked)}"),
        "ai_provider_id": "claude",
        "ai_provider_label": "Claude",
        "skill_loadout": skills,
        "metadata": {
            "connection_kind": "local",
            "provider_family": "claude",
            "workspace_root": workspace_root,
            "scan_status": "needs_manual_bind",
        },
    })

payload = {
    "project_id": clean(os.environ["PROJECT_ID"]),
    "computer_node_id": clean(os.environ["COMPUTER_NODE_ID"]),
    "workstations": workstations,
}
with open(os.environ["BODY_FILE"], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
PY

API_BASE="${SERVER%/}"
API_BASE="${API_BASE/:3000/:8010}"
API_BASE="${API_BASE/:3001/:8011}"
URL="${API_BASE%/}/api/runners/$RUNNER_ID/thread-workstations/sync"
echo "Syncing Claude thread slots to $URL ..."
curl -fsSL \
  -X POST "$URL" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-runner-id: $RUNNER_ID" \
  --data-binary "@$BODY_FILE"
echo
echo "Claude thread slots synced."
