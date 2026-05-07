from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_LOGIN_EMAIL = "codex-platform-npc@local.dev"
DEFAULT_LOGIN_PASSWORD = "password"
OPEN_STATUSES = {"waiting_response", "queued", "routed", "in_progress", "answered"}
FIXED_SEATS = ("NPC1", "NPC2", "NPC3")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync current unfinished live blockers into the project's automation requirement inbox.",
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--login-email", default=DEFAULT_LOGIN_EMAIL)
    parser.add_argument("--login-password", default=DEFAULT_LOGIN_PASSWORD)
    parser.add_argument("--db-path", default=str(repo_root() / "apps" / "api" / "ai_collab.db"))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_stamp(value: Any) -> datetime:
    cleaned = str(value or "").strip()
    if not cleaned:
        return datetime.min.replace(tzinfo=timezone.utc)
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
    return datetime.min.replace(tzinfo=timezone.utc)


@contextmanager
def single_instance_lock(root: Path):
    lock_dir = root / ".codex-runtime"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "automation-inbox-sync.lock"
    fd = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method.upper())
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def login(api_base: str, email: str, password: str) -> str:
    payload = http_json(
        "POST",
        f"{api_base}/api/auth/session",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") or {}
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Failed to obtain access token for automation inbox sync.")
    return token


def fetch_requirements(api_base: str, token: str, project_id: str) -> list[dict[str, Any]]:
    payload = http_json(
        "GET",
        f"{api_base}/api/requirements?project_id={project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def create_requirement(api_base: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = http_json(
        "POST",
        f"{api_base}/api/requirements",
        payload=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    data = result.get("data")
    return data if isinstance(data, dict) else result


def close_requirement(api_base: str, token: str, requirement_id: str, note: str) -> None:
    http_json(
        "POST",
        f"{api_base}/api/requirements/{requirement_id}/close",
        payload={"actor_type": "system", "actor_id": "automation-inbox-sync", "note": note},
        headers={"Authorization": f"Bearer {token}"},
    )


def load_bridge_audit(root: Path, project_id: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "verify-live-npc-bridges.py"), "--project-id", project_id, "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


def load_local_claude_sessions(root: Path) -> list[dict[str, Any]]:
    try:
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / "scan-claude-sessions.py"), "--cwd-filter", str(root), "--json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except subprocess.SubprocessError:
        return []
    payload = json.loads(completed.stdout)
    sessions = payload.get("sessions")
    return sessions if isinstance(sessions, list) else []


def load_fixed_seat_rows(db_path: Path, project_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select id, config_id, name, extra_data
            from project_thread_workstations
            where project_id = ?
            order by name asc
            """,
            (project_id,),
        ).fetchall()
    finally:
        conn.close()
    results: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["name"] or "").strip()
        if name not in FIXED_SEATS:
            continue
        extra_raw = row["extra_data"]
        extra: dict[str, Any] = {}
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
            except Exception:
                extra = {}
        results.append(
            {
                "id": str(row["id"] or "").strip(),
                "config_id": str(row["config_id"] or "").strip(),
                "name": name,
                "source_workstation_id": str(extra.get("source_workstation_id") or "").strip(),
            }
        )
    return results


def load_handoff_text(root: Path) -> str:
    handoff_path = root / "docs" / "ai-handoffs" / "codex-platform-autonomy-current.md"
    return handoff_path.read_text(encoding="utf-8", errors="replace")


def contains_placeholder_seat_rows(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        for field in ("id", "config_id", "name"):
            if "???" in str(row.get(field) or ""):
                return True
    return False


def build_open_requirement_index(requirements: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in requirements:
        status = str(item.get("status") or "").strip().lower()
        if status not in OPEN_STATUSES:
            continue
        title = str(item.get("title") or "").strip()
        to_agent = str(item.get("to_agent") or "").strip()
        if title:
            pairs.add((title, to_agent))
    return pairs


def dedupe_existing_automation_requirements(
    api_base: str,
    token: str,
    requirements: list[dict[str, Any]],
) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in requirements:
        status = str(item.get("status") or "").strip().lower()
        if status not in OPEN_STATUSES:
            continue
        title = str(item.get("title") or "").strip()
        if not title.startswith("自动化需求箱 /"):
            continue
        to_agent = str(item.get("to_agent") or "").strip()
        groups.setdefault((title, to_agent), []).append(item)

    closed: list[dict[str, str]] = []
    for (title, to_agent), items in groups.items():
        if len(items) <= 1:
            continue
        items.sort(key=lambda item: (parse_stamp(item.get("created_at")), str(item.get("id") or "")))
        keep = items[0]
        for duplicate in items[1:]:
            duplicate_id = str(duplicate.get("id") or "").strip()
            if not duplicate_id:
                continue
            close_requirement(
                api_base,
                token,
                duplicate_id,
                f"自动化需求箱去重：保留 {keep.get('id')}",
            )
            closed.append(
                {
                    "id": duplicate_id,
                    "title": title,
                    "to_agent": to_agent,
                    "kept_id": str(keep.get("id") or "").strip(),
                }
            )
    return closed


def build_bridge_map(bridges: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("seat") or "").strip(): item for item in bridges}


def bridge_needs_recovery_requirement(bridge: dict[str, Any]) -> bool:
    warnings = {str(item).strip() for item in bridge.get("warnings") or []}
    if bridge.get("live_final_done"):
        return False
    if bridge.get("heartbeat_missing") or "missing_heartbeat" in warnings:
        return True
    heartbeat_status = str(bridge.get("heartbeat_status") or "").strip().upper()
    if heartbeat_status and heartbeat_status != "ACTIVE":
        return True
    if not bridge.get("state_exists") or "missing_state" in warnings:
        return True
    if bridge.get("state_stale") or "stale_state" in warnings:
        return True
    if bridge.get("requirement_id") and not bridge.get("current_requirement_seen"):
        return True
    return False


def coordinator_workstation_id(bridge_map: dict[str, dict[str, Any]]) -> str:
    coordinator = bridge_map.get("NPC1") or {}
    return str(coordinator.get("live_workstation_id") or coordinator.get("wrapper_workstation_id") or "").strip()


def build_candidate_specs(
    root: Path,
    project_id: str,
    bridge_map: dict[str, dict[str, Any]],
    seat_rows: list[dict[str, Any]],
    handoff_text: str,
    claude_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    coordinator_id = coordinator_workstation_id(bridge_map)

    if contains_placeholder_seat_rows(seat_rows) and coordinator_id:
        specs.append(
            {
                "title": "自动化需求箱 / 收口主协作组席位 placeholder 视角",
                "to_agent": coordinator_id,
                "module": "npc-seat-identity",
                "priority": "high",
                "related_files": [
                    "apps/web/app/projects/[id]/project-playable-shell.tsx",
                    "apps/web/app/projects/[id]/page.tsx",
                    "scripts/run_ephemeral_live_acceptance.py",
                ],
                "context_summary": (
                    "当前首页 blocker 和 targeted recovery proof 已经对齐到 NPC2/NPC3，但已绑定 NPC 列表与 recovery DOM 里仍保留 "
                    "`NPC2 ??? / NPC1 ??? / NPC3 ???` 这类 placeholder 视角。请保留固定 NPC identity 和主协作组 blocker 真相，"
                    "同时把 seat route id、展示标题和恢复视图收成对用户干净的席位表达。"
                ),
                "expected_output": (
                    "seat 列表与 recovery proof 不再展示 placeholder 式席位标题；RECOVERY_DOM_NEXT_STEP_SEAT 应直接落到干净的 NPC2 席位表达；"
                    "首页 `NPC2 缺 heartbeat / NPC3 本地状态未更新` 的主协作组 blocker 不能被带歪。"
                ),
                "opening_message": (
                    "继续收 `NPC 创建 / 已绑定 NPC` 的 placeholder 残留。重点保持首页主协作组 blocker 真相不变，只清理 "
                    "seat list / recovery proof 的对外 route id 和标题展示，然后补 build、pytest 和 fresh recovery proof。"
                ),
            }
        )

    npc2 = bridge_map.get("NPC2") or {}
    npc2_agent = str(npc2.get("live_workstation_id") or npc2.get("wrapper_workstation_id") or "").strip()
    if npc2_agent and bridge_needs_recovery_requirement(npc2):
        specs.append(
            {
                "title": "自动化需求箱 / NPC2 恢复 heartbeat 与自治桥",
                "to_agent": npc2_agent,
                "module": "npc2-recovery",
                "priority": "high",
                "related_files": [
                    "scripts/npc2-thread-consumer.py",
                    "scripts/verify-live-npc-bridges.py",
                    "apps/web/app/projects/[id]/project-playable-shell.tsx",
                ],
                "context_summary": (
                    "当前 NPC2 的 live requirement 仍是 `2D Dev Mode / 协作界面收口`，状态 `in_progress`，已有 `progress_ack`，"
                    "但 bridge audit 仍显示 `heartbeat_missing`、`stale_state` 和 very late ack。首页第一层 blocker 也已明确指向 "
                    "`NPC2 缺 heartbeat`。"
                ),
                "expected_output": (
                    "补齐或恢复 NPC2 heartbeat，使自治桥重新稳定轮转；若 heartbeat 配置存在错绑或缺失，要直接修正到当前 live thread；"
                    "完成后至少补一次 fresh 最小回执/进展证明，并更新 live bridge proof。"
                ),
                "opening_message": (
                    "你现在处理的是 NPC2 的恢复链。先对齐当前 live thread 和 heartbeat 绑定，再确认 consumer 能继续拿到 requirement "
                    "`0f8130e9-64a3-45e8-9845-47538c3e948f` 的后续推进，不要只停在历史 minimal ack。"
                ),
            }
        )

    npc3 = bridge_map.get("NPC3") or {}
    npc3_agent = str(npc3.get("live_workstation_id") or npc3.get("wrapper_workstation_id") or "").strip()
    if npc3_agent and bridge_needs_recovery_requirement(npc3):
        specs.append(
            {
                "title": "自动化需求箱 / NPC3 刷新本地 state 与 consumer",
                "to_agent": npc3_agent,
                "module": "npc3-recovery",
                "priority": "high",
                "related_files": [
                    "scripts/npc3-thread-consumer.py",
                    "scripts/.npc3-thread-consumer-state.json",
                    "scripts/verify-live-npc-bridges.py",
                    "apps/web/public/harvest-moon-phaser3-game/index.html",
                ],
                "context_summary": (
                    "当前 NPC3 的 live requirement 仍是 `Map NPC / 地图 NPC 交互`，状态 `in_progress`，已有 `progress_ack`，"
                    "但 bridge audit 仍显示本地 state 过旧、selection/ack 延迟过大。首页第一层 blocker 已明确指向 `NPC3 本地状态未更新`。"
                ),
                "expected_output": (
                    "唤醒 NPC3 当前线程或重跑 consumer，让本地 state 与 live requirement 重新对齐；补最新进展或最终回复；"
                    "验证地图 NPC 交互链和相关 proof 不再停在旧 state。"
                ),
                "opening_message": (
                    "你现在处理的是 NPC3 的恢复链。先刷新当前 thread 的 local state / consumer，再继续推进 requirement "
                    "`0aae3eb2-7097-4e68-bc96-a38d5b90528b`，不要让 proof 长期停在旧 minimal ack。"
                ),
            }
        )

    if "screen-fallback" in handoff_text and coordinator_id:
        specs.append(
            {
                "title": "自动化需求箱 / 农场强截图链脱离 screen-fallback",
                "to_agent": coordinator_id,
                "module": "farm-proof",
                "priority": "high",
                "related_files": [
                    "scripts/run_ephemeral_live_acceptance.py",
                    "scripts/capture-auth-screenshot.mjs",
                    "apps/web/public/harvest-moon-phaser3-game/index.html",
                ],
                "context_summary": (
                    "当前农场底座首屏契约已经真实成立，但 farm strong capture 仍然长期落在 `CAPTURE_METHOD=screen-fallback`。"
                    "这已经成为当前 proof 链最主要的剩余限制。"
                ),
                "expected_output": (
                    "让 farm proof 尽量脱离 `screen-fallback`，至少要把当前强截图失败路径、可复现条件和可靠 fallback 明确收成可维护的验收链；"
                    "在不替换农场底座的前提下继续保住项目页第一屏主视图。"
                ),
                "opening_message": (
                    "继续收农场强截图链。目标不是换掉农场，而是让 current fresh acceptance 更稳定地拿到农场首屏证据，"
                    "同时诚实记录当前桌面壳限制。"
                ),
            }
        )

    if claude_sessions and coordinator_id:
        specs.append(
            {
                "title": "自动化需求箱 / Claude provider adapter 接入",
                "to_agent": coordinator_id,
                "module": "claude-adapter",
                "priority": "high",
                "related_files": [
                    "apps/web/lib/local-claude-sessions.ts",
                    "apps/web/lib/claude-seat-bridge.ts",
                    "apps/web/app/projects/[id]/page.tsx",
                    "apps/web/app/projects/[id]/project-playable-shell.tsx",
                    "scripts/start-claude-seat.ps1",
                    "scripts/scan-claude-sessions.py",
                ],
                "context_summary": (
                    f"本机当前已扫到 {len(claude_sessions)} 条 Claude Code 会话，平台已经能识别 Claude source thread，"
                    "但当前还没有和 Codex 同构的 Claude provider adapter 闭环。需要把会话登记、seat 状态、恢复提示和后续派单接入统一协议。"
                ),
                "expected_output": (
                    "至少让 Claude 进入和 Codex 同一套 seat adapter 状态链；创建/更新 Claude NPC 时自动登记会话；"
                    "项目页能诚实显示 Claude session 是否已登记、是否过旧，以及下一步该怎么恢复。"
                ),
                "opening_message": (
                    "继续把 Claude 接进平台。先收成最小可用 provider adapter：会话发现、seat 注册、adapter 健康状态、恢复动作都要进平台页面；"
                    "不要继续停留在“只能看到 Claude 线程，但还不能稳定协作”的阶段。"
                ),
            }
        )

    results: list[dict[str, Any]] = []
    for item in specs:
        results.append(
            {
                "project_id": project_id,
                "requirement_type": "thread_request",
                "status": "waiting_response",
                "from_agent": "automation-inbox",
                "max_response_tokens": 3000,
                **item,
            }
        )
    return results


def sync_candidates(
    api_base: str,
    token: str,
    existing_requirements: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    open_index = build_open_requirement_index(existing_requirements)
    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for payload in candidates:
        key = (str(payload.get("title") or "").strip(), str(payload.get("to_agent") or "").strip())
        if key in open_index:
            skipped.append({"title": key[0], "to_agent": key[1], "reason": "already_open"})
            continue
        created_requirement = create_requirement(api_base, token, payload)
        created.append(
            {
                "id": str(created_requirement.get("id") or ""),
                "title": str(created_requirement.get("title") or payload["title"]),
                "to_agent": str(created_requirement.get("to_agent") or payload["to_agent"]),
                "status": str(created_requirement.get("status") or payload["status"]),
            }
        )
        open_index.add(key)
    return {"created": created, "skipped": skipped}


def print_human(summary: dict[str, Any]) -> None:
    print(f"候选需求 {summary['candidate_count']} 条")
    if summary["closed_duplicates"]:
        print("已关闭重复 requirement：")
        for item in summary["closed_duplicates"]:
            print(f"- {item['title']} -> 关闭 {item['id']}，保留 {item['kept_id']}")
    if summary["created"]:
        print("已写入自动化需求箱：")
        for item in summary["created"]:
            print(f"- {item['title']} -> {item['to_agent']} ({item['id']})")
    if summary["skipped"]:
        print("已存在而跳过：")
        for item in summary["skipped"]:
            print(f"- {item['title']} -> {item['to_agent']} ({item['reason']})")


def main() -> int:
    args = parse_args()
    root = repo_root()
    with single_instance_lock(root):
        db_path = Path(args.db_path)
        token = login(args.api_base, args.login_email, args.login_password)
        requirements = fetch_requirements(args.api_base, token, args.project_id)
        closed_duplicates = dedupe_existing_automation_requirements(args.api_base, token, requirements)
        requirements = fetch_requirements(args.api_base, token, args.project_id)
        bridges = load_bridge_audit(root, args.project_id)
        claude_sessions = load_local_claude_sessions(root)
        seat_rows = load_fixed_seat_rows(db_path, args.project_id)
        handoff_text = load_handoff_text(root)
        candidates = build_candidate_specs(
            root,
            args.project_id,
            build_bridge_map(bridges),
            seat_rows,
            handoff_text,
            claude_sessions,
        )
        synced = sync_candidates(args.api_base, token, requirements, candidates)
        summary = {
            "project_id": args.project_id,
            "candidate_count": len(candidates),
            "closed_duplicates": closed_duplicates,
            "created": synced["created"],
            "skipped": synced["skipped"],
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
