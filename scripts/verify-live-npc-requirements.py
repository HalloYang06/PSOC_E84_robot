from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collab_title_normalizer import looks_dirty_text, normalized_requirement_title, related_file_list


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OPEN_STATUSES = {"waiting_response", "queued", "routed", "in_progress", "answered"}
LATE_PROGRESS_ACK_SECONDS = 60 * 60
STALE_OPEN_REQUIREMENT_SECONDS = 4 * 60 * 60


@dataclass
class SeatIdentity:
    name: str
    aliases: set[str]


def parse_stamp(value: str | None) -> datetime | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    candidate = cleaned.replace("Z", "+00:00")
    for parser in (
        lambda item: datetime.fromisoformat(item),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
        lambda item: datetime.strptime(item, "%Y-%m-%dT%H:%M:%S"),
    ):
        try:
            parsed = parser(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def seconds_between(later: str | None, earlier: str | None) -> int | None:
    later_dt = parse_stamp(later)
    earlier_dt = parse_stamp(earlier)
    if later_dt is None or earlier_dt is None:
        return None
    return max(0, int((later_dt - earlier_dt).total_seconds()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the latest live requirement state for NPC seats.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).resolve().parent.parent / "apps" / "api" / "ai_collab.db"),
    )
    parser.add_argument("--seats", nargs="+", default=["NPC1", "NPC2", "NPC3"])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_seat_identities(conn: sqlite3.Connection, project_id: str, seats: list[str]) -> list[SeatIdentity]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select id, config_id, name, extra_data
        from project_thread_workstations
        where project_id = ?
        order by name asc
        """,
        (project_id,),
    ).fetchall()
    requested = {item.strip().lower(): item.strip() for item in seats if item.strip()}
    identities: dict[str, SeatIdentity] = {}
    for row in rows:
        name = str(row["name"] or "").strip()
        lowered = name.lower()
        if lowered not in requested:
            continue
        aliases = {name, str(row["config_id"] or "").strip(), str(row["id"] or "").strip()}
        extra_raw = row["extra_data"]
        extra: dict[str, Any] = {}
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
            except Exception:
                extra = {}
        for key in ("source_workstation_id", "workstation_id"):
            value = str(extra.get(key) or "").strip()
            if value:
                aliases.add(value)
        identities[requested[lowered]] = SeatIdentity(
            name=requested[lowered],
            aliases={item for item in aliases if item},
        )
    return [identities.get(seat, SeatIdentity(name=seat, aliases={seat})) for seat in seats]


def select_latest_requirement(conn: sqlite3.Connection, project_id: str, aliases: set[str]) -> sqlite3.Row | None:
    if not aliases:
        return None
    placeholders = ",".join("?" for _ in aliases)
    params = [project_id, *sorted(aliases)]
    open_rows = conn.execute(
        f"""
        select id, title, status, to_agent, from_agent, updated_at, created_at,
               context_summary, expected_output, related_files
        from requirements
        where project_id = ?
          and to_agent in ({placeholders})
          and status in ({",".join("?" for _ in OPEN_STATUSES)})
        order by updated_at desc, created_at desc
        limit 1
        """,
        (*params, *sorted(OPEN_STATUSES)),
    ).fetchall()
    if open_rows:
        return open_rows[0]
    any_rows = conn.execute(
        f"""
        select id, title, status, to_agent, from_agent, updated_at, created_at,
               context_summary, expected_output, related_files
        from requirements
        where project_id = ?
          and to_agent in ({placeholders})
        order by updated_at desc, created_at desc
        limit 1
        """,
        params,
    ).fetchall()
    return any_rows[0] if any_rows else None


def load_requirement_messages(conn: sqlite3.Connection, requirement_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select id, message_type, status, title, sender_id, recipient_id, created_at, updated_at
        from collaboration_messages
        where requirement_id = ?
        order by created_at desc, updated_at desc
        """,
        (requirement_id,),
    ).fetchall()


def first_message(messages: list[sqlite3.Row], *, message_type: str, status: str | None = None) -> sqlite3.Row | None:
    for item in messages:
        if str(item["message_type"] or "").strip() != message_type:
            continue
        if status is not None and str(item["status"] or "").strip() != status:
            continue
        return item
    return None


def summarize_requirement(conn: sqlite3.Connection, project_id: str, seat: SeatIdentity) -> dict[str, Any]:
    row = select_latest_requirement(conn, project_id, seat.aliases)
    if row is None:
        return {
            "seat": seat.name,
            "aliases": sorted(seat.aliases),
            "state": "missing",
        }

    messages = load_requirement_messages(conn, str(row["id"]))
    latest_dispatch = first_message(messages, message_type="requirement_dispatch")
    latest_progress_ack = first_message(messages, message_type="requirement_progress_ack")
    latest_legacy_progress = first_message(messages, message_type="requirement_final_reply", status="in_progress")
    latest_done_final = first_message(messages, message_type="requirement_final_reply", status="done")
    latest_agent_report = first_message(messages, message_type="agent_report")

    progress_signal = "missing"
    if latest_progress_ack is not None:
        progress_signal = "progress_ack"
    elif latest_legacy_progress is not None:
        progress_signal = "legacy_final_reply_in_progress"
    elif latest_agent_report is not None and str(latest_agent_report["status"] or "").strip() == "in_progress":
        progress_signal = "agent_report_only"

    progress_origin = latest_progress_ack or latest_legacy_progress or latest_agent_report
    dispatch_to_progress_seconds = seconds_between(
        str(progress_origin["created_at"]) if progress_origin is not None else None,
        str(latest_dispatch["created_at"]) if latest_dispatch is not None else None,
    )
    updated_age_seconds = seconds_between(
        datetime.now(timezone.utc).isoformat(),
        str(row["updated_at"] or ""),
    )
    related_files = related_file_list(row["related_files"])
    title_dirty = looks_dirty_text(row["title"])
    display_title = normalized_requirement_title(
        row["title"],
        related_files,
        row["context_summary"],
        row["expected_output"],
    )
    warnings: list[str] = []
    if title_dirty:
        warnings.append("dirty_title")
    if dispatch_to_progress_seconds is not None and dispatch_to_progress_seconds >= LATE_PROGRESS_ACK_SECONDS:
        warnings.append("late_progress_ack")
    if (
        str(row["status"] or "").strip() in OPEN_STATUSES
        and updated_age_seconds is not None
        and updated_age_seconds >= STALE_OPEN_REQUIREMENT_SECONDS
    ):
        warnings.append("stale_open_requirement")

    if str(row["status"] or "").strip() in OPEN_STATUSES:
        if progress_signal == "missing":
            health = "waiting_for_ack"
        elif "stale_open_requirement" in warnings:
            health = "stalled_after_ack"
        elif "late_progress_ack" in warnings:
            health = "working_after_late_ack"
        elif latest_done_final is not None:
            health = "done_but_not_closed"
        else:
            health = "working"
    else:
        health = "done" if latest_done_final is not None else "recent"

    return {
        "seat": seat.name,
        "aliases": sorted(seat.aliases),
        "state": "open" if str(row["status"] or "").strip() in OPEN_STATUSES else "recent",
        "requirement": {
            "id": str(row["id"]),
            "title": str(row["title"] or ""),
            "display_title": display_title,
            "status": str(row["status"] or ""),
            "to_agent": str(row["to_agent"] or ""),
            "from_agent": str(row["from_agent"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "created_at": str(row["created_at"] or ""),
            "title_dirty": title_dirty,
            "related_files": related_files,
        },
        "signals": {
            "dispatch": latest_dispatch is not None,
            "progress_signal": progress_signal,
            "agent_report": latest_agent_report is not None,
            "final_done": latest_done_final is not None,
            "dispatch_to_progress_seconds": dispatch_to_progress_seconds,
            "updated_age_seconds": updated_age_seconds,
            "health": health,
            "warnings": warnings,
        },
        "latest_messages": {
            "dispatch": dict(latest_dispatch) if latest_dispatch is not None else None,
            "progress_ack": dict(latest_progress_ack) if latest_progress_ack is not None else None,
            "legacy_progress": dict(latest_legacy_progress) if latest_legacy_progress is not None else None,
            "agent_report": dict(latest_agent_report) if latest_agent_report is not None else None,
            "final_done": dict(latest_done_final) if latest_done_final is not None else None,
        },
    }


def print_human(results: list[dict[str, Any]]) -> None:
    print("Live NPC requirement audit")
    print("")
    for item in results:
        print(f"[{item['seat']}] state={item['state']}")
        if item["state"] == "missing":
            aliases = ", ".join(item["aliases"])
            print(f"  aliases: {aliases or '-'}")
            print("  requirement: missing")
            print("")
            continue
        requirement = item["requirement"]
        signals = item["signals"]
        print(
            f"  requirement: {requirement['id']} | {requirement['status']} | "
            f"{requirement['display_title']}"
        )
        print(f"  route: {requirement['from_agent']} -> {requirement['to_agent']}")
        print(
            "  signals: "
            f"dispatch={'yes' if signals['dispatch'] else 'no'}, "
            f"progress={signals['progress_signal']}, "
            f"agent_report={'yes' if signals['agent_report'] else 'no'}, "
            f"final_done={'yes' if signals['final_done'] else 'no'}"
        )
        print(
            "  health: "
            f"{signals['health']}, "
            f"title_dirty={'yes' if requirement['title_dirty'] else 'no'}, "
            f"dispatch_to_progress_s={signals['dispatch_to_progress_seconds'] if signals['dispatch_to_progress_seconds'] is not None else '-'}, "
            f"updated_age_s={signals['updated_age_seconds'] if signals['updated_age_seconds'] is not None else '-'}"
        )
        print(f"  warnings: {', '.join(signals['warnings']) if signals['warnings'] else '-'}")
        print(f"  updated_at: {requirement['updated_at']}")
        print("")


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        seats = load_seat_identities(conn, args.project_id, args.seats)
        results = [summarize_requirement(conn, args.project_id, seat) for seat in seats]
    finally:
        conn.close()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_human(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
