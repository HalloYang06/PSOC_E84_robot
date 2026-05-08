#!/usr/bin/env python
"""
Seat MCP server — runs alongside the Claude/Codex CLI session of an NPC seat
and lets that NPC self-initiate cross-NPC collaboration without going through
the human UI.

Three tools, all stdio + line-delimited JSON-RPC (Claude Code / Codex CLIs both
accept this transport):

- list_peers()                          → 同工位 / 跨工位伙伴名单（seat_id + 姓名 + 是否工位长）
- request_help(role, ask, expected="")  → 平台按 role 在同工位匹配一个 NPC，发派单
                                          （有审 → pending_review；免审 → queued）
- dispatch_to_peer(seat_id, title, body)→ 直接指名派单（同上 review 行为）

每个工具内部都只做一件事：调现成的后端 `POST /api/collaboration/messages`，
让后端 `_resolve_review_for_dispatch` 自动决定 pending_review / queued。这就是
"NPC 主动发起 → 走审 / 可免审"的真自主协作链路。

环境变量（由 watcher 注入，见 platform-workstation-adapter.py）：
- PLATFORM_API_BASE       e.g. http://127.0.0.1:8010
- PLATFORM_PROJECT_ID
- PLATFORM_SEAT_ID        本 NPC 的 seat row id（thread_workstation 收件人 = 这个）
- PLATFORM_WORKSTATION_ID 本 NPC 所在 workstation 的 config_id（兜底）
- PLATFORM_ADAPTER_TOKEN  workstation adapter token（优先）
- PLATFORM_AUTH_TOKEN     human session bearer（兜底）

退出码：本 server 永远不主动 exit；让父 CLI 关闭 stdin 时自然结束。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "seat-mcp"
SERVER_VERSION = "0.1.0"


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def _api_base() -> str:
    return _env("PLATFORM_API_BASE", "http://127.0.0.1:8010").rstrip("/")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    adapter_token = _env("PLATFORM_ADAPTER_TOKEN")
    auth_token = _env("PLATFORM_AUTH_TOKEN")
    workstation_id = _env("PLATFORM_WORKSTATION_ID")
    if adapter_token and workstation_id:
        h["X-Workstation-Id"] = workstation_id
        h["X-Workstation-Token"] = adapter_token
    elif auth_token:
        h["Authorization"] = f"Bearer {auth_token}"
    return h


def _http_json(method: str, url: str, body: dict | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
        return {"_status": exc.code, "_raw": raw}
    except Exception as exc:
        return {"_status": 0, "_error": str(exc)}
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"_raw": raw}


def _list_seats(project_id: str) -> list[dict[str, Any]]:
    payload = _http_json("GET", f"{_api_base()}/api/collaboration/projects/{project_id}/thread-workstations")
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, list) else []


def _project_config(project_id: str) -> dict[str, Any]:
    payload = _http_json("GET", f"{_api_base()}/api/collaboration/projects/{project_id}/config")
    if isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            return data
    return {}


def _self_seat(project_id: str, seat_id: str) -> dict[str, Any] | None:
    seats = _list_seats(project_id)
    for s in seats:
        if str(s.get("id") or "") == seat_id or str(s.get("config_id") or "") == seat_id:
            return s
    return None


def _peers(project_id: str, seat_id: str) -> dict[str, list[dict[str, Any]]]:
    seats = _list_seats(project_id)
    cfg = _project_config(project_id)
    inner = cfg.get("collaboration_config") if isinstance(cfg, dict) else None
    profiles = (inner or {}).get("workstation_profiles") if isinstance(inner, dict) else None
    profiles = profiles if isinstance(profiles, dict) else {}
    me = _self_seat(project_id, seat_id) or {}
    my_node = str(me.get("computer_node_id") or "").strip()
    same: list[dict[str, Any]] = []
    cross: list[dict[str, Any]] = []
    for s in seats:
        sid = str(s.get("id") or "")
        if not sid or sid == str(me.get("id") or ""):
            continue
        node = str(s.get("computer_node_id") or "").strip()
        node_profile = profiles.get(node) if isinstance(profiles, dict) else None
        is_lead = bool(node_profile and (node_profile.get("lead_seat_id") or node_profile.get("leadSeatId")) in {sid, s.get("config_id"), s.get("name")})
        info = {
            "seat_id": sid,
            "name": s.get("name") or s.get("config_id") or sid,
            "provider": s.get("provider_id") or s.get("provider_label") or "",
            "computer_node_id": node,
            "is_lead": is_lead,
            "responsibility": s.get("responsibility") or "",
        }
        (same if node == my_node else cross).append(info)
    return {"same_workstation": same, "cross_workstation": cross}


def _create_message(*, project_id: str, sender_seat_id: str, recipient_seat_id: str, title: str, body: str, message_type: str = "agent_command") -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "sender_type": "agent",
        "sender_id": sender_seat_id,
        "recipient_type": "thread_workstation",
        "recipient_id": recipient_seat_id,
        "message_type": message_type,
        "title": title[:200] or "NPC 自主发起",
        "body": body or "",
        "status": "queued",
    }
    return _http_json("POST", f"{_api_base()}/api/collaboration/messages", payload)


def _match_role(peers_same: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    role_l = role.strip().lower()
    if not role_l:
        return None
    for p in peers_same:
        haystack = " ".join([
            str(p.get("name") or ""),
            str(p.get("responsibility") or ""),
            str(p.get("provider") or ""),
        ]).lower()
        if role_l in haystack:
            return p
    return None


def _tool_list_peers() -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    peers = _peers(project_id, seat_id)
    return {"ok": True, **peers}


def _tool_request_help(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    role = str(args.get("role") or "").strip()
    ask = str(args.get("ask") or "").strip()
    expected = str(args.get("expected") or "").strip()
    if not role or not ask:
        return {"ok": False, "error": "role and ask are required"}
    peers = _peers(project_id, seat_id)
    target = _match_role(peers["same_workstation"], role) or _match_role(peers["cross_workstation"], role)
    if target is None:
        return {"ok": False, "error": f"no peer matched role {role!r}", "peers": peers}
    title = f"[自主求助] {role}"
    body = f"## 我（NPC `{seat_id}`）的求助\n\n**找谁**：{role}\n\n**问题**：\n{ask}"
    if expected:
        body += f"\n\n**期望产物**：\n{expected}"
    body += "\n\n（本消息由 NPC 通过 seat-mcp `request_help` 工具自主发起。后端 review 策略会决定 pending_review / queued。）"
    resp = _create_message(
        project_id=project_id,
        sender_seat_id=seat_id,
        recipient_seat_id=str(target.get("seat_id") or ""),
        title=title,
        body=body,
    )
    msg = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(msg, dict):
        return {"ok": False, "error": "platform rejected the dispatch", "raw": resp}
    return {
        "ok": True,
        "matched_peer": target,
        "message_id": msg.get("id"),
        "status": msg.get("status"),
        "needs_review": (msg.get("status") == "pending_review"),
        "hint": (
            "等待用户在驾驶舱/瓷砖待审区点通过；通过后才会真发送给目标 NPC。"
            if msg.get("status") == "pending_review"
            else "已直接进入目标 NPC 的队列（免审模式或同工位策略为 skip）。"
        ),
    }


def _tool_dispatch_to_peer(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    target_seat_id = str(args.get("seat_id") or "").strip()
    title = str(args.get("title") or "").strip()
    body = str(args.get("body") or "").strip()
    if not target_seat_id or not title or not body:
        return {"ok": False, "error": "seat_id, title and body are required"}
    body_full = body + f"\n\n（NPC `{seat_id}` 通过 seat-mcp `dispatch_to_peer` 主动发起，后端 review 策略接管。）"
    resp = _create_message(
        project_id=project_id,
        sender_seat_id=seat_id,
        recipient_seat_id=target_seat_id,
        title=title,
        body=body_full,
    )
    msg = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(msg, dict):
        return {"ok": False, "error": "platform rejected the dispatch", "raw": resp}
    return {
        "ok": True,
        "message_id": msg.get("id"),
        "status": msg.get("status"),
        "needs_review": (msg.get("status") == "pending_review"),
    }


TOOLS = [
    {
        "name": "list_peers",
        "description": "列出我（当前 NPC seat）能接触到的伙伴：分组为同工位（same_workstation）和跨工位（cross_workstation），每个伙伴含 seat_id / name / provider / is_lead。同工位的伙伴默认不需要审核；跨工位会被强制走工位长 + 审核。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "request_help",
        "description": "我（当前 NPC）需要找一位伙伴帮我做事时调用。平台按 role 关键字（匹配 name / responsibility / provider）在同工位优先匹配；找不到再到跨工位。匹配成功 → 自动发起一条派单 → 后端 review 策略决定 pending_review（要审）或 queued（免审）。返回 message_id、status、needs_review。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "要找的伙伴角色关键字，例如 'reviewer' / '前端' / 'codex'。"},
                "ask": {"type": "string", "description": "我要请对方做什么 / 我卡在哪里（中文/英文都行，会作为消息正文）。"},
                "expected": {"type": "string", "description": "期望对方产出什么（可选）。"},
            },
            "required": ["role", "ask"],
            "additionalProperties": False,
        },
    },
    {
        "name": "dispatch_to_peer",
        "description": "我已经知道要找哪位伙伴（有 seat_id），直接指名派单。仍走 review gate（同工位免审 / 跨工位强审，除非项目/工位/NPC 上覆盖了 skip）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seat_id": {"type": "string", "description": "目标 NPC 的 seat_id（list_peers 返回的同名字段）。"},
                "title": {"type": "string", "description": "派单标题。"},
                "body": {"type": "string", "description": "派单正文。"},
            },
            "required": ["seat_id", "title", "body"],
            "additionalProperties": False,
        },
    },
]


def _ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _content(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method") or ""
    req_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method in {"notifications/initialized", "initialized"}:
        return None
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        if name == "list_peers":
            return _ok(req_id, _content(_tool_list_peers()))
        if name == "request_help":
            return _ok(req_id, _content(_tool_request_help(args if isinstance(args, dict) else {})))
        if name == "dispatch_to_peer":
            return _ok(req_id, _content(_tool_dispatch_to_peer(args if isinstance(args, dict) else {})))
        return _err(req_id, -32601, f"unknown tool {name!r}")
    if method in {"ping"}:
        return _ok(req_id, {})
    if req_id is None:
        return None
    return _err(req_id, -32601, f"method {method!r} not implemented")


def main() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        if resp is None:
            continue
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
