#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
DEFAULT_WORKSTATION_ID = "codex-session-user-flow-researcher-20260423-181944"
DEFAULT_WORKSTATION_NAME = "NPC1"
OPEN_REQUIREMENT_STATUSES = {"waiting_response", "queued", "routed", "in_progress", "answered"}
TERMINAL_REQUIREMENT_STATUSES = {"done", "closed", "completed", "resolved"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_db_path() -> Path:
    return repo_root() / "apps" / "api" / "ai_collab.db"


def default_inbox_path(project_id: str) -> Path:
    return repo_root() / "docs" / "ai-handoffs" / "inbox" / f"project-{project_id}-codex.json"


def default_state_path() -> Path:
    return Path(__file__).with_name(".npc1-thread-consumer-state.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh a local Codex NPC bridge state from the platform DB. "
            "This lightweight base intentionally does not fake platform write-back."
        )
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--db-path", default=str(default_db_path()))
    parser.add_argument("--inbox-path", default="")
    parser.add_argument("--state-path", default=str(default_state_path()))
    parser.add_argument("--workstation-id", default=DEFAULT_WORKSTATION_ID)
    parser.add_argument("--workstation-name", default=DEFAULT_WORKSTATION_NAME)
    parser.add_argument("--platform-fetch", action="store_true")
    parser.add_argument("--requirement-id", default="")
    parser.add_argument("--source-message-id", default="")
    parser.add_argument("--report-status", default="")
    parser.add_argument("--report-title", default="")
    parser.add_argument("--report-body", default="")
    parser.add_argument("--handoff-path", default="")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--autonomy-sweep", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def select_requirements(conn: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    params: list[Any] = [args.project_id, args.workstation_id]
    requirement_filter = ""
    if args.requirement_id.strip():
        requirement_filter = "and id = ?"
        params.append(args.requirement_id.strip())
    placeholders = ",".join("?" for _ in OPEN_REQUIREMENT_STATUSES)
    params.extend(sorted(OPEN_REQUIREMENT_STATUSES))
    return conn.execute(
        f"""
        select id, title, status, to_agent, from_agent, updated_at, created_at,
               context_summary, expected_output, related_files
        from requirements
        where project_id = ?
          and to_agent = ?
          {requirement_filter}
          and status in ({placeholders})
        order by updated_at desc, created_at desc
        """,
        params,
    ).fetchall()


def messages_for_requirement(conn: sqlite3.Connection, requirement_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select id, message_type, status, title, body, sender_id, recipient_id, created_at, updated_at
        from collaboration_messages
        where requirement_id = ?
        order by created_at desc, updated_at desc
        """,
        (requirement_id,),
    ).fetchall()


def first_message(messages: list[sqlite3.Row], message_type: str) -> sqlite3.Row | None:
    for item in messages:
        if str(item["message_type"] or "").strip() == message_type:
            return item
    return None


def posted_status_names(workstation_state: dict[str, Any], dedupe_id: str) -> list[str]:
    posted = workstation_state.get("posted") or {}
    if not isinstance(posted, dict):
        return []
    statuses = posted.get(dedupe_id) or {}
    if not isinstance(statuses, dict):
        return []
    return sorted(str(key) for key in statuses.keys())


def mirror_platform_progress(
    workstation_state: dict[str, Any],
    *,
    dedupe_id: str,
    requirement_id: str,
    source_message_id: str,
    messages: list[sqlite3.Row],
) -> None:
    posted = workstation_state.setdefault("posted", {})
    if not isinstance(posted, dict):
        workstation_state["posted"] = {}
        posted = workstation_state["posted"]
    bucket = posted.setdefault(dedupe_id, {})
    if not isinstance(bucket, dict):
        posted[dedupe_id] = {}
        bucket = posted[dedupe_id]

    for message in messages:
        status = str(message["status"] or "").strip()
        message_type = str(message["message_type"] or "").strip()
        if message_type not in {"agent_report", "requirement_progress_ack", "requirement_final_reply"}:
            continue
        if status not in {"in_progress", "done"}:
            continue
        bucket.setdefault(
            status,
            {
                "at": str(message["created_at"] or ""),
                "requirement_id": requirement_id,
                "source_message_id": source_message_id,
                "mirrored_from_platform": {
                    "id": str(message["id"] or ""),
                    "message_type": message_type,
                    "status": status,
                    "title": str(message["title"] or ""),
                    "created_at": str(message["created_at"] or ""),
                },
            },
        )


def build_selected(requirement: sqlite3.Row, dispatch: sqlite3.Row | None, already_posted: list[str]) -> dict[str, Any]:
    dispatch_dict = row_dict(dispatch) or {}
    requirement_id = str(requirement["id"])
    source_message_id = str(dispatch_dict.get("id") or requirement_id)
    source_status = str(dispatch_dict.get("status") or requirement["status"] or "")
    return {
        "id": source_message_id,
        "title": str(dispatch_dict.get("title") or requirement["title"] or ""),
        "status": source_status,
        "route": "platform_dispatch" if dispatch is not None else "platform_requirement",
        "created_at": str(dispatch_dict.get("created_at") or requirement["created_at"] or ""),
        "project_id": DEFAULT_PROJECT_ID,
        "source_message_id": source_message_id,
        "source_requirement_id": requirement_id,
        "source_status": source_status,
        "already_posted": already_posted,
        "draft": {
            "report_status": None,
            "title": None,
            "body": None,
        },
    }


def main() -> int:
    args = parse_args()
    if args.post:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "post_not_supported_by_recovered_base_consumer",
                    "message": "State refresh is supported; platform write-back must use a real API bridge.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    now = utc_now()
    state_path = Path(args.state_path)
    inbox_path = Path(args.inbox_path) if args.inbox_path else default_inbox_path(args.project_id)
    state = read_json(state_path)
    state.setdefault("version", 1)
    workstations = state.setdefault("workstations", {})
    if not isinstance(workstations, dict):
        state["workstations"] = {}
        workstations = state["workstations"]
    workstation_state = workstations.setdefault(args.workstation_id, {})
    if not isinstance(workstation_state, dict):
        workstations[args.workstation_id] = {}
        workstation_state = workstations[args.workstation_id]

    with connect(Path(args.db_path)) as conn:
        requirements = select_requirements(conn, args)
        if args.source_message_id.strip():
            wanted = args.source_message_id.strip()
            requirements = [
                row
                for row in requirements
                if any(str(message["id"] or "") == wanted for message in messages_for_requirement(conn, str(row["id"])))
            ]

        selected_requirement = requirements[0] if requirements else None
        if selected_requirement is None:
            output = {
                "now": now,
                "inbox_path": str(inbox_path),
                "state_path": str(state_path),
                "workstation_id": args.workstation_id,
                "workstation_name": args.workstation_name,
                "matched_commands": 0,
                "fetched_from_platform": bool(args.platform_fetch),
                "selected": None,
                "pending_ids": [],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 1

        messages = messages_for_requirement(conn, str(selected_requirement["id"]))
        dispatch = first_message(messages, "requirement_dispatch")
        source_message_id = str(dispatch["id"] if dispatch is not None else selected_requirement["id"])
        dedupe_id = source_message_id
        mirror_platform_progress(
            workstation_state,
            dedupe_id=dedupe_id,
            requirement_id=str(selected_requirement["id"]),
            source_message_id=source_message_id,
            messages=messages,
        )
        already_posted = posted_status_names(workstation_state, dedupe_id)
        selected = build_selected(selected_requirement, dispatch, already_posted)
        workstation_state["last_selected"] = {
            "at": now,
            "dedupe_id": dedupe_id,
            "requirement_id": str(selected_requirement["id"]),
        }
        workstation_state["last_platform_fetch"] = {
            "at": now,
            "reason": "platform_fetch_selection_refresh",
            "route": selected["route"],
            "source_message_id": source_message_id,
            "requirement_id": str(selected_requirement["id"]),
            "requirement_status": str(selected_requirement["status"] or ""),
        }
        write_json(state_path, state)

    output = {
        "now": now,
        "inbox_path": str(inbox_path),
        "state_path": str(state_path),
        "workstation_id": args.workstation_id,
        "workstation_name": args.workstation_name,
        "matched_commands": len(requirements),
        "fetched_from_platform": bool(args.platform_fetch),
        "selected": selected,
        "pending_ids": [
            str(row["id"])
            for row in requirements
            if str(row["status"] or "").strip().lower() not in TERMINAL_REQUIREMENT_STATUSES
        ],
        "state_refreshed": {
            "last_selected": workstation_state.get("last_selected"),
            "last_platform_fetch": workstation_state.get("last_platform_fetch"),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
