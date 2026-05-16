#!/usr/bin/env bash
set -euo pipefail

SERVER=""
RUNNER_ID=""
PROJECT_ID=""
COMPUTER_NODE_ID=""
SESSION_INDEX_PATH=""
TAKE="12"
MAX_AGE_DAYS="14"
WORKSPACE_ROOT=""
AI_PROVIDER_ID="codex"
AI_PROVIDER_LABEL="Codex"
MODEL="gpt-5.4"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2 ;;
    --runner-id) RUNNER_ID="${2:-}"; shift 2 ;;
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --computer-node-id) COMPUTER_NODE_ID="${2:-}"; shift 2 ;;
    --session-index-path) SESSION_INDEX_PATH="${2:-}"; shift 2 ;;
    --take) TAKE="${2:-}"; shift 2 ;;
    --max-age-days) MAX_AGE_DAYS="${2:-}"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="${2:-}"; shift 2 ;;
    --ai-provider-id) AI_PROVIDER_ID="${2:-}"; shift 2 ;;
    --ai-provider-label) AI_PROVIDER_LABEL="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SERVER" || -z "$RUNNER_ID" || -z "$PROJECT_ID" || -z "$COMPUTER_NODE_ID" ]]; then
  echo "Required: --server --runner-id --project-id --computer-node-id" >&2
  exit 2
fi

BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

export BODY_FILE PROJECT_ID COMPUTER_NODE_ID SESSION_INDEX_PATH TAKE MAX_AGE_DAYS WORKSPACE_ROOT AI_PROVIDER_ID AI_PROVIDER_LABEL MODEL
python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


def clean(value: object, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_len].strip()


def parse_dt(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def session_id_from_file(path: Path) -> str:
    match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$", path.stem)
    if match:
        return match.group(1).lower()
    return hashlib.sha256(str(path).lower().encode("utf-8")).hexdigest()[:32]


def short_title(value: object, fallback: str) -> str:
    title = clean(value, 64)
    title = re.sub(r"^\s*#+\s*", "", title)
    return title or fallback


def codex_homes() -> list[Path]:
    homes: list[Path] = []
    for env_name in ("CODEX_HOME",):
        raw = os.environ.get(env_name)
        if raw:
            homes.append(Path(raw).expanduser())
    homes.append(Path.home() / ".codex")
    for raw in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
        if raw:
            homes.extend([Path(raw) / "Codex", Path(raw) / "OpenAI" / "Codex"])
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in homes:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


take = max(1, int(os.environ.get("TAKE") or "12"))
max_age_days = abs(int(os.environ.get("MAX_AGE_DAYS") or "14"))
cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
workspace_root = clean(os.environ.get("WORKSPACE_ROOT")) or None
workspace_norm = str(Path(workspace_root).expanduser()).replace("\\", "/").lower() if workspace_root else ""
explicit_index = clean(os.environ.get("SESSION_INDEX_PATH"), 1000)
index_candidates = [Path(explicit_index).expanduser()] if explicit_index else [home / "session_index.jsonl" for home in codex_homes()]
session_dirs = []
for candidate in index_candidates:
    if candidate.parent:
        session_dirs.append(candidate.parent / "sessions")
for home in codex_homes():
    session_dirs.extend([home / "sessions", home / "Sessions"])

rows: dict[str, dict] = {}
checked = [str(path) for path in index_candidates]
for index_path in index_candidates:
    if not index_path.exists():
        continue
    try:
        lines = index_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        session_id = clean(item.get("id"), 120)
        updated_at = parse_dt(item.get("updated_at"))
        if not session_id or (updated_at and updated_at < cutoff):
            continue
        rows[session_id] = {
            "id": session_id,
            "name": short_title(item.get("thread_name"), f"Codex / {session_id[:8]}"),
            "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
            "source_kind": "session_index",
        }

for directory in session_dirs:
    if not directory.exists():
        continue
    for path in sorted(directory.rglob("*.json*"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if updated_at < cutoff:
            continue
        session_id = session_id_from_file(path)
        if session_id in rows:
            continue
        title = ""
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:260]:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                payload = item.get("payload") if isinstance(item, dict) else None
                if isinstance(payload, dict):
                    title = payload.get("thread_name") or title
                    if not title and item.get("type") == "event_msg" and payload.get("type") == "user_message":
                        title = payload.get("message") or title
                if title:
                    break
        except Exception:
            pass
        rows[session_id] = {
            "id": session_id,
            "name": short_title(title, f"Codex / {updated_at.strftime('%m-%d %H:%M')} / {session_id[:8]}"),
            "updated_at": updated_at.isoformat(),
            "source_kind": "session_file",
            "source_file": str(path),
        }

items = sorted(rows.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:take]
skills = ["github-repo-bootstrap", "ai-collab-productizer", "continuous-orchestrator", "handoff-path-output", "verify-before-claim"]
workstations = []
for item in items:
    sid = clean(item["id"], 120)
    workstations.append({
        "workstation_id": f"codex-session-{sid}",
        "workstation_name": clean(item["name"], 120),
        "workstation_status": "active",
        "cwd": workspace_root,
        "model": clean(os.environ.get("MODEL")),
        "description": "Synced from local Codex session files",
        "notes": clean(f"updated_at={item.get('updated_at')}"),
        "ai_provider_id": clean(os.environ.get("AI_PROVIDER_ID")),
        "ai_provider_label": clean(os.environ.get("AI_PROVIDER_LABEL")),
        "skill_loadout": skills,
        "metadata": {
            "connection_kind": "local",
            "provider_family": clean(os.environ.get("AI_PROVIDER_ID")),
            "workspace_root": workspace_root,
            "scan_status": "active_session_found",
            "source_kind": clean(item.get("source_kind")),
        },
    })

if not workstations:
    slug = re.sub(r"[^a-z0-9]+", "-", os.environ["COMPUTER_NODE_ID"].lower()).strip("-") or "computer"
    workstations.append({
        "workstation_id": f"codex-manual-{slug}",
        "workstation_name": f"Codex / manual bind on {os.environ['COMPUTER_NODE_ID']}",
        "workstation_status": "needs_binding",
        "cwd": workspace_root,
        "model": clean(os.environ.get("MODEL")),
        "description": "Codex session files were not found yet; open Codex on this computer and scan again.",
        "notes": clean(f"Checked: {'; '.join(checked)}"),
        "ai_provider_id": clean(os.environ.get("AI_PROVIDER_ID")),
        "ai_provider_label": clean(os.environ.get("AI_PROVIDER_LABEL")),
        "skill_loadout": skills,
        "metadata": {
            "connection_kind": "local",
            "provider_family": clean(os.environ.get("AI_PROVIDER_ID")),
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
echo "Syncing Codex thread slots to $URL ..."
if [[ "$DRY_RUN" == "true" ]]; then
  cat "$BODY_FILE"
  echo
  exit 0
fi
curl -fsSL \
  -X POST "$URL" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-runner-id: $RUNNER_ID" \
  --data-binary "@$BODY_FILE"
echo
echo "Codex thread slots synced."
