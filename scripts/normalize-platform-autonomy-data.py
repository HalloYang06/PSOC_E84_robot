from __future__ import annotations

import json
import sqlite3
from pathlib import Path


PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"

MAINTENANCE_REQUIREMENT_COPY = {
    "平台主链夜间自检": {
        "context_summary": "复查登录、项目管理、线程扫描、NPC 背包和最小回执链在当前项目里是否仍然正常。",
        "expected_output": "给一条最小回执，说明当前链路是否正常，必要时补修复。",
        "to_agent_hint": "主负责 NPC",
    },
    "平台主链自检并推进下一步": {
        "context_summary": "复查平台主线、最终回复池、当前负责人和推荐操作是否还能正常运作。",
        "expected_output": "给一条最小回执，并继续推进下一步。",
        "to_agent_hint": "主负责 NPC",
    },
    "复查电脑与线程扫描": {
        "context_summary": "复查在线电脑、真实线程数量、线程扫描请求与页面显示是否一致。",
        "expected_output": "确认线程扫描链状态，必要时修复后回一条最小回执。",
        "to_agent_hint": "线程联络员",
    },
    "复查电脑与线程扫描状态": {
        "context_summary": "检查电脑接入、线程扫描和回执跟进是否仍然对齐。",
        "expected_output": "给一条最小回执，说明当前线程扫描状态。",
        "to_agent_hint": "线程联络员",
    },
    "整理 Git 协作结果视图": {
        "context_summary": "整理 Git 合作页、需求分流和最终回复池的结果视图，让平台只看最终结果。",
        "expected_output": "给一条最小回执，并补齐结果视图或状态摘要。",
        "to_agent_hint": "Git 维护员",
    },
    "整理 Git 协作需求并回流结果": {
        "context_summary": "整理 Git 协作需求、需求分流和结果回流，让平台里只看最终回复。",
        "expected_output": "给一条最小回执，并回流最新结果。",
        "to_agent_hint": "Git 维护员",
    },
    "整理 Skill 库与 NPC 装配": {
        "context_summary": "整理 Skill 库、NPC 装备和 Git 边界，让 NPC 属性更稳定可读。",
        "expected_output": "给一条最小回执，并说明 Skill 库和 NPC 装配是否已更新。",
        "to_agent_hint": "技能库维护员",
    },
}


def load_db() -> sqlite3.Connection:
    db_path = Path(__file__).resolve().parents[1] / "apps" / "api" / "ai_collab.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_codex_seats(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    seats: dict[str, dict[str, str]] = {}
    rows = conn.execute(
        """
        SELECT id, name, agent_id, extra_data
        FROM project_thread_workstations
        WHERE project_id = ?
        """,
        (PROJECT_ID,),
    ).fetchall()
    for row in rows:
        extra = json.loads(row["extra_data"]) if row["extra_data"] else {}
        if str(extra.get("seat_type", "")).lower() != "codex":
            continue
        seats[row["name"]] = {
            "id": row["id"],
            "agent_id": row["agent_id"] or "",
            }
    return seats


def canonical_ai_target(raw: str | None, hinted_name: str | None, seats: dict[str, dict[str, str]]) -> str | None:
    value = (raw or "").strip()
    if hinted_name and hinted_name in seats:
        agent_id = seats[hinted_name].get("agent_id") or seats[hinted_name]["id"]
        return f"ai:{agent_id}"
    if not value:
        return value or None
    if value.startswith("ai:") or value.startswith("human:"):
        raw_ai = value[3:] if value.startswith("ai:") else value
        if value.startswith("ai:"):
          for info in seats.values():
              if raw_ai in {info["id"], info.get("agent_id", "")}:
                  agent_id = info.get("agent_id") or info["id"]
                  return f"ai:{agent_id}"
        return value
    for info in seats.values():
        if value in {info["id"], info["agent_id"]}:
            agent_id = info.get("agent_id") or info["id"]
            return f"ai:{agent_id}"
    return value


def main() -> None:
    conn = load_db()
    seats = load_codex_seats(conn)
    updated = 0
    rows = conn.execute(
        """
        SELECT id, title, to_agent, context_summary, expected_output
        FROM requirements
        WHERE project_id = ?
        """,
        (PROJECT_ID,),
    ).fetchall()
    for row in rows:
        patch = MAINTENANCE_REQUIREMENT_COPY.get(row["title"])
        if not patch:
            continue
        next_target = canonical_ai_target(row["to_agent"], patch.get("to_agent_hint"), seats)
        if (
            row["context_summary"] == patch["context_summary"]
            and row["expected_output"] == patch["expected_output"]
            and row["to_agent"] == next_target
        ):
            continue
        conn.execute(
            """
            UPDATE requirements
            SET context_summary = ?, expected_output = ?, to_agent = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                patch["context_summary"],
                patch["expected_output"],
                next_target,
                row["id"],
            ),
        )
        updated += 1
    conn.commit()
    print(json.dumps({"updated_requirements": updated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
