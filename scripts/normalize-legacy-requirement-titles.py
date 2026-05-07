from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from collab_title_normalizer import (
    looks_dirty_text,
    normalized_message_title,
    normalized_requirement_title,
    related_file_list,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize legacy dirty requirement and message titles.")
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).resolve().parent.parent / "apps" / "api" / "ai_collab.db"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--requirement-id", dest="requirement_ids", action="append", default=[])
    return parser.parse_args()


def load_requirement_candidates(conn: sqlite3.Connection, requirement_ids: list[str]) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    if requirement_ids:
        placeholders = ",".join("?" for _ in requirement_ids)
        return conn.execute(
            f"""
        select id, title, context_summary, expected_output, related_files
        from requirements
        where id in ({placeholders})
        order by updated_at desc, created_at desc
        """,
            tuple(requirement_ids),
        ).fetchall()
    return conn.execute(
        """
        select id, title, context_summary, expected_output, related_files
        from requirements
        order by updated_at desc, created_at desc
        """
    ).fetchall()


def load_requirement_messages(conn: sqlite3.Connection, requirement_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select id, title, message_type, status
        from collaboration_messages
        where requirement_id = ?
        order by created_at asc
        """,
        (requirement_id,),
    ).fetchall()


def normalize(conn: sqlite3.Connection, *, apply_changes: bool, requirement_ids: list[str]) -> dict[str, object]:
    requirement_changes: list[dict[str, str]] = []
    message_changes: list[dict[str, str]] = []
    candidates = load_requirement_candidates(conn, requirement_ids)
    for row in candidates:
        requirement_id = str(row["id"])
        raw_title = str(row["title"] or "")
        related_files = related_file_list(row["related_files"])
        next_title = normalized_requirement_title(
            raw_title,
            related_files,
            row["context_summary"],
            row["expected_output"],
        )
        if looks_dirty_text(raw_title) and next_title and next_title != raw_title:
            requirement_changes.append(
                {
                    "id": requirement_id,
                    "from_title": raw_title,
                    "to_title": next_title,
                }
            )
            if apply_changes:
                conn.execute(
                    "update requirements set title = ? where id = ?",
                    (next_title, requirement_id),
                )
        else:
            next_title = raw_title

        for message in load_requirement_messages(conn, requirement_id):
            raw_message_title = str(message["title"] or "")
            if not looks_dirty_text(raw_message_title):
                continue
            normalized_title = normalized_message_title(
                raw_message_title,
                requirement_title=next_title,
                message_type=message["message_type"],
                status=message["status"],
            )
            if not normalized_title or normalized_title == raw_message_title:
                continue
            message_changes.append(
                {
                    "id": str(message["id"]),
                    "requirement_id": requirement_id,
                    "message_type": str(message["message_type"] or ""),
                    "status": str(message["status"] or ""),
                    "from_title": raw_message_title,
                    "to_title": normalized_title,
                }
            )
            if apply_changes:
                conn.execute(
                    "update collaboration_messages set title = ? where id = ?",
                    (normalized_title, str(message["id"])),
                )
    if apply_changes:
        conn.commit()
    return {
        "mode": "apply" if apply_changes else "dry_run",
        "requirement_count": len(requirement_changes),
        "message_count": len(message_changes),
        "requirements": requirement_changes,
        "messages": message_changes,
    }


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        payload = normalize(conn, apply_changes=args.apply, requirement_ids=args.requirement_ids)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode={payload['mode']}")
        print(f"requirements={payload['requirement_count']}")
        print(f"messages={payload['message_count']}")
        for item in payload["requirements"]:
            print(f"REQ {item['id']} | {item['from_title']} -> {item['to_title']}")
        for item in payload["messages"]:
            print(
                f"MSG {item['id']} | {item['message_type']}:{item['status']} | "
                f"{item['from_title']} -> {item['to_title']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
