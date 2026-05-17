#!/usr/bin/env python
"""
Seat MCP server — runs alongside the Claude/Codex CLI session of an NPC seat
and lets that NPC self-initiate cross-NPC collaboration without going through
the human UI.

Three tools, all stdio + line-delimited JSON-RPC (Claude Code / Codex CLIs both
accept this transport):

- list_peers()                          → 同工位 / 跨工位伙伴名单。【判定按逻辑工位 workstation_id】
                                          （workstation_id 为空时退回 computer_node_id），与后端
                                          `_seat_workstation_key` 对齐。
- create_need(...)                      → 当前 NPC 写入结构化 Need，由平台 NeedRouter 预览/路由成目标 NPC Task
- request_help(role, ask, expected="")  → 兼容旧工具：只转成结构化 Need，不再按关键词直接派单
- dispatch_to_peer(seat_id, title, body, force_direct=False)
                                        → 直接指名派单。跨工位时默认改投到目标工位长转手；
                                          force_direct=True 才直送（不推荐）。

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


def _list_workstations(project_id: str) -> list[dict[str, Any]]:
    """新逻辑工位表（项目内自定义"软件/硬件/嵌入式…"）。"""
    payload = _http_json("GET", f"{_api_base()}/api/projects/{project_id}/workstations")
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


def _seat_workstation_key(seat: dict[str, Any]) -> str:
    """与后端 `_seat_workstation_key` 对齐：workstation_id 优先，否则退回 computer_node_id。"""
    ws = str(seat.get("workstation_id") or "").strip()
    if ws:
        return ws
    return str(seat.get("computer_node_id") or "").strip()


def _peers(project_id: str, seat_id: str) -> dict[str, Any]:
    seats = _list_seats(project_id)
    workstations = _list_workstations(project_id)
    cfg = _project_config(project_id)
    inner = cfg.get("collaboration_config") if isinstance(cfg, dict) else None
    profiles = (inner or {}).get("workstation_profiles") if isinstance(inner, dict) else None
    profiles = profiles if isinstance(profiles, dict) else {}

    ws_name_by_id: dict[str, str] = {}
    lead_by_ws: dict[str, str] = {}
    for ws in workstations:
        wid = str(ws.get("id") or "").strip()
        if not wid:
            continue
        ws_name_by_id[wid] = str(ws.get("name") or wid)
        lead = str(ws.get("lead_seat_id") or "").strip()
        if lead:
            lead_by_ws[wid] = lead

    me = _self_seat(project_id, seat_id) or {}
    my_key = _seat_workstation_key(me)
    my_ws_id = str(me.get("workstation_id") or "").strip()
    my_ws_name = ws_name_by_id.get(my_ws_id) if my_ws_id else ""

    same: list[dict[str, Any]] = []
    cross: list[dict[str, Any]] = []
    for s in seats:
        sid = str(s.get("id") or "")
        if not sid or sid == str(me.get("id") or ""):
            continue
        peer_key = _seat_workstation_key(s)
        peer_ws_id = str(s.get("workstation_id") or "").strip()
        peer_node = str(s.get("computer_node_id") or "").strip()
        peer_ws_name = ws_name_by_id.get(peer_ws_id) if peer_ws_id else ""
        is_lead = False
        if peer_ws_id and lead_by_ws.get(peer_ws_id) == sid:
            is_lead = True
        else:
            node_profile = profiles.get(peer_node) if peer_node else None
            if isinstance(node_profile, dict):
                cand = node_profile.get("lead_seat_id") or node_profile.get("leadSeatId")
                if cand in {sid, s.get("config_id"), s.get("name")}:
                    is_lead = True
        info = {
            "seat_id": sid,
            "name": s.get("name") or s.get("config_id") or sid,
            "provider": s.get("provider_id") or s.get("provider_label") or "",
            "workstation_id": peer_ws_id or "",
            "workstation_name": peer_ws_name or "",
            "computer_node_id": peer_node,
            "is_lead": is_lead,
            "responsibility": s.get("responsibility") or "",
        }
        (same if peer_key and peer_key == my_key else cross).append(info)
    return {
        "my_workstation_id": my_ws_id,
        "my_workstation_name": my_ws_name or "",
        "my_workstation_key": my_key,
        "same_workstation": same,
        "cross_workstation": cross,
    }


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
    role = str(args.get("role") or "").strip()
    ask = str(args.get("ask") or "").strip()
    expected = str(args.get("expected") or "").strip()
    if not role or not ask:
        return {"ok": False, "error": "role and ask are required"}
    return _tool_create_need(
        {
            "title": f"需要 {role} 协助",
            "why_needed": ask,
            "required_capability": role,
            "expected_output": expected or "给出可执行的协作结果和最小回执。",
            "input_context": ask,
            "risk_level": "low",
            "priority": "P2",
            "acceptance_criteria": [expected or "对方给出清晰结论或可执行产物"],
            "auto_route": False,
        }
    )


def _tool_create_need(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    title = str(args.get("title") or "").strip()
    why_needed = str(args.get("why_needed") or "").strip()
    required_capability = str(args.get("required_capability") or "").strip()
    expected_output = str(args.get("expected_output") or "").strip()
    input_context = str(args.get("input_context") or "").strip()
    acceptance_criteria = args.get("acceptance_criteria") or []
    if isinstance(acceptance_criteria, str):
        acceptance_criteria = [acceptance_criteria]
    acceptance_criteria = [str(item).strip() for item in acceptance_criteria if str(item).strip()]
    if not title or not why_needed or not required_capability or not expected_output or not input_context:
        return {
            "ok": False,
            "error": "title, why_needed, required_capability, expected_output and input_context are required",
        }
    if not acceptance_criteria:
        return {"ok": False, "error": "acceptance_criteria is required; draft Needs cannot route to tasks"}
    payload = {
        "project_id": project_id,
        "requester_seat_id": seat_id,
        "title": title,
        "why_needed": why_needed,
        "required_capability": required_capability,
        "expected_output": expected_output,
        "input_context": input_context,
        "risk_level": str(args.get("risk_level") or "low").strip().lower(),
        "priority": str(args.get("priority") or "P2").strip().upper(),
        "suggested_assignee": str(args.get("suggested_assignee") or "").strip() or None,
        "acceptance_criteria": acceptance_criteria,
        "blocking_current_task": bool(args.get("blocking_current_task") or False),
        "module": str(args.get("module") or "").strip() or None,
        "auto_route": bool(args.get("auto_route") or False),
    }
    resp = _http_json(
        "POST",
        f"{_api_base()}/api/collaboration/projects/{project_id}/thread-workstations/{seat_id}/structured-need",
        payload,
    )
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "error": "platform rejected structured Need", "raw": resp}
    preview = data.get("route_preview") if isinstance(data.get("route_preview"), dict) else {}
    requirement = data.get("requirement") if isinstance(data.get("requirement"), dict) else {}
    return {
        "ok": True,
        "need_id": requirement.get("id"),
        "need_status": requirement.get("status"),
        "recommended_assignee_id": preview.get("recommended_assignee_id"),
        "recommended_assignee_name": preview.get("recommended_assignee_name"),
        "requires_review": preview.get("requires_review"),
        "review_reason": preview.get("review_reason"),
        "blocked_reason": preview.get("blocked_reason"),
        "route_result": data.get("route_result"),
        "hint": "Need 已进入我的需求；若策略允许自动路由，目标 NPC 的任务池会出现 Task。",
    }


def _tool_check_my_needs(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    payload = _http_json(
        "GET",
        f"{_api_base()}/api/collaboration/projects/{project_id}/thread-workstations/{seat_id}/queues?limit={int(args.get('limit') or 20)}",
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "error": "platform rejected queue read", "raw": payload}
    return {"ok": True, "my_needs": data.get("my_needs")}


def _tool_check_my_tasks(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    payload = _http_json(
        "GET",
        f"{_api_base()}/api/collaboration/projects/{project_id}/thread-workstations/{seat_id}/queues?limit={int(args.get('limit') or 20)}",
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "error": "platform rejected queue read", "raw": payload}
    return {"ok": True, "my_tasks": data.get("my_tasks")}


def _tool_dispatch_to_peer(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    target_seat_id = str(args.get("seat_id") or "").strip()
    title = str(args.get("title") or "").strip()
    body = str(args.get("body") or "").strip()
    force_direct = bool(args.get("force_direct") or False)
    if not target_seat_id or not title or not body:
        return {"ok": False, "error": "seat_id, title and body are required"}

    peers = _peers(project_id, seat_id)
    me_key = peers.get("my_workstation_key") or ""
    target_seat: dict[str, Any] | None = None
    for p in (peers.get("same_workstation") or []) + (peers.get("cross_workstation") or []):
        if str(p.get("seat_id") or "") == target_seat_id:
            target_seat = p
            break

    routed_to_lead = False
    original_target_id = target_seat_id
    original_target_name = ""
    if target_seat is not None:
        original_target_name = str(target_seat.get("name") or "")
        peer_key = str(target_seat.get("workstation_id") or target_seat.get("computer_node_id") or "")
        is_cross = bool(me_key) and bool(peer_key) and peer_key != me_key
        if is_cross and not force_direct and not target_seat.get("is_lead"):
            target_ws_id = str(target_seat.get("workstation_id") or "")
            if target_ws_id:
                lead_id = ""
                for ws in _list_workstations(project_id):
                    if str(ws.get("id") or "") == target_ws_id:
                        lead_id = str(ws.get("lead_seat_id") or "").strip()
                        break
                if lead_id and lead_id != target_seat_id:
                    target_seat_id = lead_id
                    routed_to_lead = True

    routing_note = (
        f"\n\n[路由] 跨工位默认转交工位长：原指定 `{original_target_id}`（{original_target_name}）→ 经工位长 `{target_seat_id}` 转手"
        if routed_to_lead
        else ""
    )
    body_full = (
        body
        + routing_note
        + f"\n\n（NPC `{seat_id}` 通过 seat-mcp `dispatch_to_peer` 主动发起，后端 review 策略接管。）"
    )
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
        "routed_via_lead": routed_to_lead,
        "delivered_to_seat_id": target_seat_id,
        "originally_addressed_seat_id": original_target_id,
    }


def _tool_mark_done(args: dict[str, Any]) -> dict[str, Any]:
    """长开窗口模式下，NPC 处理完一条派单后显式声明完成。
    通过平台 /messages/{id}/complete 端点写 done 回执。"""
    project_id = _env("PLATFORM_PROJECT_ID")
    workstation_id = _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not workstation_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_WORKSTATION_ID env"}
    message_id = str(args.get("message_id") or "").strip()
    body = str(args.get("body") or "").strip()
    failed = bool(args.get("failed") or False)
    if not message_id or not body:
        return {"ok": False, "error": "message_id and body are required"}
    from urllib.parse import quote as _q
    url = (
        f"{_api_base()}/api/collaboration/projects/{_q(project_id, safe='')}"
        f"/thread-workstations/{_q(workstation_id, safe='')}"
        f"/messages/{_q(message_id, safe='')}/complete"
    )
    resp = _http_json("POST", url, {
        "result_status": "failed" if failed else "completed",
        "note": body,
    })
    msg = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(msg, dict):
        return {"ok": False, "error": "platform rejected the completion", "raw": resp}
    return {
        "ok": True,
        "message_id": msg.get("id"),
        "parent_message_id": message_id,
        "status": msg.get("status"),
        "receipt_kind": ((msg.get("metadata") or {}).get("receipt_kind") if isinstance(msg.get("metadata"), dict) else None),
        "hint": "已写入 done 回执；对方 NPC 的 inbox 会看到这条结果。",
    }


def _tool_read_my_inbox(args: dict[str, Any]) -> dict[str, Any]:
    """让 NPC 在 CLI 线程内自查：我收到的派单 + 别人给我的回执 + 我发出的派单的当前状态。"""
    project_id = _env("PLATFORM_PROJECT_ID")
    seat_id = _env("PLATFORM_SEAT_ID") or _env("PLATFORM_WORKSTATION_ID")
    if not project_id or not seat_id:
        return {"ok": False, "error": "missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env"}
    limit = int(args.get("limit") or 15)
    # 同名异 id 兜底（JSON 中文 id vs DB UUID）
    me = _self_seat(project_id, seat_id) or {}
    candidates = {seat_id, str(me.get("id") or ""), str(me.get("config_id") or ""), str(me.get("name") or "")}
    candidates.discard("")

    incoming_dispatches: list[dict[str, Any]] = []  # 别人派给我的（thread_workstation 收件）
    incoming_receipts: list[dict[str, Any]] = []     # 别人对我派单的回执（agent 收件 + receipt_kind）
    outgoing_status: list[dict[str, Any]] = []       # 我发出的、对方还没回执的
    outgoing_done: list[dict[str, Any]] = []         # 我发出的、已收到回执的

    seen = set()
    for sid in candidates:
        for params in (
            f"?project_id={project_id}&recipient_type=thread_workstation&recipient_id={sid}&limit={limit * 2}",
            f"?project_id={project_id}&recipient_type=agent&recipient_id={sid}&limit={limit * 2}",
            f"?project_id={project_id}&sender_id={sid}&limit={limit * 2}",
        ):
            payload = _http_json("GET", f"{_api_base()}/api/collaboration/messages{params}")
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                continue
            for m in data:
                mid = str(m.get("id") or "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                receipt_kind = str((meta or {}).get("receipt_kind") or "")
                sender = str(m.get("sender_id") or "")
                recv = str(m.get("recipient_id") or "")
                rtype = str(m.get("recipient_type") or "")
                title = str(m.get("title") or "")
                body = str(m.get("body") or "")
                status = str(m.get("status") or "")
                short = {
                    "id": mid,
                    "title": title[:120],
                    "status": status,
                    "sender_id": sender,
                    "recipient_id": recv,
                    "receipt_kind": receipt_kind,
                    "parent_message_id": str((meta or {}).get("parent_message_id") or ""),
                    "created_at": str(m.get("created_at") or ""),
                    "body_preview": body[:300] + ("…" if len(body) > 300 else ""),
                }
                if recv in candidates and rtype == "thread_workstation":
                    incoming_dispatches.append(short)
                elif recv in candidates and rtype == "agent" and receipt_kind:
                    incoming_receipts.append(short)
                elif sender in candidates:
                    if str(m.get("message_type") or "") == "agent_command":
                        outgoing_status.append(short)
                    else:
                        outgoing_done.append(short)

    incoming_dispatches.sort(key=lambda x: x["created_at"], reverse=True)
    incoming_receipts.sort(key=lambda x: x["created_at"], reverse=True)
    outgoing_status.sort(key=lambda x: x["created_at"], reverse=True)
    outgoing_done.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "ok": True,
        "self_seat_id": seat_id,
        "self_name": str(me.get("name") or ""),
        "incoming_dispatches": incoming_dispatches[:limit],
        "incoming_receipts": incoming_receipts[:limit],
        "outgoing_dispatches": outgoing_status[:limit],
        "outgoing_results": outgoing_done[:limit],
        "hint": (
            f"incoming_dispatches: 别人派给我、待我处理的任务（共 {len(incoming_dispatches)} 条）；"
            f"incoming_receipts: 我之前派出去的任务，对方已经发回的 ack/done/reject/progress 回执（共 {len(incoming_receipts)} 条）；"
            f"outgoing_dispatches: 我发出去的派单（共 {len(outgoing_status)} 条）；"
            f"如果一条 outgoing 还没出现在 incoming_receipts，说明对方还没回。"
        ),
    }


TOOLS = [
    {
        "name": "create_need",
        "description": "我（当前 NPC）明确缺少输入、能力或协作产物时调用。该工具写入结构化 Need：Need 属于我；平台 NeedRouter 会根据员工表、skill、知识库、在线状态和审核策略推荐目标 NPC，并在允许时转成目标 NPC 的 Task。不要用关键词猜派单。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "需求标题。"},
                "why_needed": {"type": "string", "description": "为什么我需要别人帮，说明当前阻塞。"},
                "required_capability": {"type": "string", "description": "需要的能力，不是目标名字，例如 frontend-review / runner-debug / data-qa。"},
                "expected_output": {"type": "string", "description": "对方交付什么才算满足。"},
                "input_context": {"type": "string", "description": "给承接方的必要上下文。"},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                "suggested_assignee": {"type": "string", "description": "可选，明确知道目标 NPC seat_id 时填写。"},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "description": "验收标准。"},
                "blocking_current_task": {"type": "boolean"},
                "module": {"type": "string"},
                "auto_route": {"type": "boolean", "description": "低风险且策略允许时是否自动转成目标 NPC 任务。默认 false。"},
            },
            "required": ["title", "why_needed", "required_capability", "expected_output", "input_context", "acceptance_criteria"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_peers",
        "description": "列出我（当前 NPC seat）能接触到的伙伴：分组为同工位（same_workstation）和跨工位（cross_workstation）。判定按【逻辑工位】（workstation_id）：相同 workstation_id 视为同工位；workstation_id 为空时退回 computer_node_id 比较。返回还含 my_workstation_id / my_workstation_name 让我能引用自己。每个伙伴含 seat_id / name / workstation_id / workstation_name / computer_node_id / is_lead / responsibility。同工位默认免审核；跨工位会被强制走工位长 + 审核。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "request_help",
        "description": "兼容旧工具：我需要找伙伴帮忙时调用会被转换为结构化 Need。新工作流请优先使用 create_need，因为平台不再靠 role 关键词直接派单。",
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
        "description": "我已经知道要找哪位伙伴（有 seat_id），直接指名派单。同工位 → 直送目标。跨工位 → 默认改投到目标工位的【工位长】转手（除非 force_direct=True 或目标本身就是 lead）。仍走 review gate（同工位免审 / 跨工位强审，除非项目/工位/NPC 上覆盖了 skip）。返回额外字段 routed_via_lead / delivered_to_seat_id / originally_addressed_seat_id。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seat_id": {"type": "string", "description": "目标 NPC 的 seat_id（list_peers 返回的同名字段）。"},
                "title": {"type": "string", "description": "派单标题。"},
                "body": {"type": "string", "description": "派单正文。"},
                "force_direct": {"type": "boolean", "description": "跨工位时是否绕过工位长，直送指定 seat（不推荐，仅在你确认对方工位长不在或已授权时使用）。默认 false。"},
            },
            "required": ["seat_id", "title", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_my_needs",
        "description": "查看我（当前 NPC）自己提出、等待别人满足的 Need 队列。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "check_my_tasks",
        "description": "查看分配给我（当前 NPC）承接和完成的 Task 队列。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "read_my_inbox",
        "description": "在 CLI 线程内自查我（当前 NPC）的协作流：（1）incoming_dispatches：别人派给我的、还未我处理的派单。（2）incoming_receipts：我之前派出去的任务，对方已发回的 ack/done/reject/progress 回执。（3）outgoing_dispatches：我自己发出的派单（含 pending_review/queued/completed 状态）。（4）outgoing_results：我发出的回执。每条带 title/sender_id/recipient_id/status/receipt_kind/parent_message_id/created_at/body_preview。在 work 卡住、要确认对方有没有回、要复述上下文时调用一次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "每类返回多少条，默认 15。"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mark_done",
        "description": "长开窗口（PersistentWindow）模式下声明一条派单已处理完。message_id 来自 read_my_inbox 的 incoming_dispatches[].id；body 是你给对方的最终回复（GitHub-flavored Markdown，链接用真实 GitHub 仓库地址）。失败时把 failed 设 true。**仅在长开模式使用**——一次性弹窗模式由 watcher 自动写回，不要重复调。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "要标记完成的派单 id（来自 read_my_inbox 的 incoming_dispatches[].id）。"},
                "body": {"type": "string", "description": "给对方的最终回复 Markdown 正文。"},
                "failed": {"type": "boolean", "description": "如果是失败回执则设 true（默认 false）。"},
            },
            "required": ["message_id", "body"],
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
        if name == "create_need":
            return _ok(req_id, _content(_tool_create_need(args if isinstance(args, dict) else {})))
        if name == "list_peers":
            return _ok(req_id, _content(_tool_list_peers()))
        if name == "request_help":
            return _ok(req_id, _content(_tool_request_help(args if isinstance(args, dict) else {})))
        if name == "dispatch_to_peer":
            return _ok(req_id, _content(_tool_dispatch_to_peer(args if isinstance(args, dict) else {})))
        if name == "read_my_inbox":
            return _ok(req_id, _content(_tool_read_my_inbox(args if isinstance(args, dict) else {})))
        if name == "check_my_needs":
            return _ok(req_id, _content(_tool_check_my_needs(args if isinstance(args, dict) else {})))
        if name == "check_my_tasks":
            return _ok(req_id, _content(_tool_check_my_tasks(args if isinstance(args, dict) else {})))
        if name == "mark_done":
            return _ok(req_id, _content(_tool_mark_done(args if isinstance(args, dict) else {})))
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
