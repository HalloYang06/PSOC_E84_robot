from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize legacy in-progress final replies into progress ack messages.")
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).resolve().parent.parent / "apps" / "api" / "ai_collab.db"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def replacement_dedupe_key(requirement_id: str, current: str | None) -> str:
    cleaned = str(current or "").strip()
    legacy = f"auto_final_reply:{requirement_id}:in_progress"
    if not cleaned or cleaned == legacy:
        return f"auto_progress_ack:{requirement_id}"
    return cleaned


def load_candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        select id, requirement_id, title, status, message_type, dedupe_key, created_at, updated_at
        from collaboration_messages
        where message_type = 'requirement_final_reply'
          and status = 'in_progress'
        order by updated_at desc, created_at desc
        """
    ).fetchall()


def existing_progress_ack(conn: sqlite3.Connection, requirement_id: str, dedupe_key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        select id, requirement_id, dedupe_key, created_at, updated_at
        from collaboration_messages
        where requirement_id = ?
          and message_type = 'requirement_progress_ack'
          and status = 'in_progress'
          and dedupe_key = ?
        order by updated_at desc, created_at desc
        limit 1
        """,
        (requirement_id, dedupe_key),
    ).fetchone()


def normalize(conn: sqlite3.Connection, *, apply_changes: bool) -> list[dict[str, str]]:
    candidates = load_candidates(conn)
    changes: list[dict[str, str]] = []
    for row in candidates:
        requirement_id = str(row["requirement_id"] or "").strip()
        next_dedupe_key = replacement_dedupe_key(requirement_id, row["dedupe_key"])
        duplicate_progress_ack = existing_progress_ack(conn, requirement_id, next_dedupe_key)
        action = "delete_legacy_duplicate" if duplicate_progress_ack is not None else "rewrite_message_type"
        change = {
            "id": str(row["id"]),
            "requirement_id": requirement_id,
            "title": str(row["title"] or ""),
            "action": action,
            "from_message_type": str(row["message_type"] or ""),
            "to_message_type": "requirement_progress_ack" if duplicate_progress_ack is None else "",
            "from_dedupe_key": str(row["dedupe_key"] or ""),
            "to_dedupe_key": next_dedupe_key,
            "duplicate_progress_ack_id": str(duplicate_progress_ack["id"]) if duplicate_progress_ack is not None else "",
        }
        changes.append(change)
        if apply_changes:
            if duplicate_progress_ack is not None:
                conn.execute(
                    """
                    delete from collaboration_messages
                    where id = ?
                    """,
                    (str(row["id"]),),
                )
            else:
                conn.execute(
                    """
                    update collaboration_messages
                    set message_type = 'requirement_progress_ack',
                        dedupe_key = ?
                    where id = ?
                    """,
                    (next_dedupe_key, str(row["id"])),
                )
    if apply_changes:
        conn.commit()
    return changes


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        changes = normalize(conn, apply_changes=args.apply)
    finally:
        conn.close()
    payload = {
        "mode": "apply" if args.apply else "dry_run",
        "count": len(changes),
        "changes": changes,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode={payload['mode']}")
        print(f"count={payload['count']}")
        for item in changes:
            print(
                f"{item['id']} | {item['requirement_id']} | "
                f"{item['from_message_type']} -> {item['to_message_type']} | "
                f"{item['from_dedupe_key'] or '-'} -> {item['to_dedupe_key']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
