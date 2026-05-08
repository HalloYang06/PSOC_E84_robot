#!/usr/bin/env python
"""
Step 8 验收：seat-mcp-server 的协议 + 三个工具是否齐备。

策略：
- 直接 import server 模块，喂 JSON-RPC 请求，断言响应。
- HTTP 调用用 monkey-patch 的 _http_json 拦截，不依赖真 API（CI 友好；本地真跑请用 e2e）。
- 关键断言：协议握手、工具列表、list_peers/request_help/dispatch_to_peer 三个工具
  都能在 monkey-patch 注入的"假后端"里走通，且能正确反映 review gate（pending_review vs queued）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "scripts" / "seat-mcp-server" / "server.py"

spec = importlib.util.spec_from_file_location("seat_mcp_server", SERVER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return {"name": name, "ok": ok, "detail": detail}


# ---- fake backend ---------------------------------------------------------
SEATS = [
    {"id": "seat_alice", "config_id": "seat_alice_cfg", "name": "Alice (frontend)", "computer_node_id": "pc1", "provider_id": "claude", "responsibility": "前端页面"},
    {"id": "seat_bob",   "config_id": "seat_bob_cfg",   "name": "Bob (reviewer)",   "computer_node_id": "pc1", "provider_id": "claude", "responsibility": "代码审核 reviewer"},
    {"id": "seat_carol", "config_id": "seat_carol_cfg", "name": "Carol (backend)",  "computer_node_id": "pc2", "provider_id": "codex",  "responsibility": "后端 API"},
]

CFG = {
    "collaboration_config": {
        "workstation_profiles": {"pc2": {"lead_seat_id": "seat_carol"}},
        "review_policy": {"default": "cross_workstation_only"},
    }
}

CREATED: list[dict] = []


def fake_http_json(method, url, body=None):
    if url.endswith("/thread-workstations") and method == "GET":
        return {"data": SEATS}
    if url.endswith("/config") and method == "GET":
        return {"data": CFG}
    if url.endswith("/api/collaboration/messages") and method == "POST":
        is_cross = False
        sender = next((s for s in SEATS if s["id"] == body.get("sender_id")), None)
        recipient = next((s for s in SEATS if s["id"] == body.get("recipient_id")), None)
        if sender and recipient:
            is_cross = sender["computer_node_id"] != recipient["computer_node_id"]
        msg = {
            "id": f"msg_{len(CREATED)+1}",
            "status": "pending_review" if is_cross else "queued",
            "sender_id": body.get("sender_id"),
            "recipient_id": body.get("recipient_id"),
            "title": body.get("title"),
            "body": body.get("body"),
        }
        CREATED.append(msg)
        return {"data": msg}
    if "/messages/" in url and url.endswith("/complete") and method == "POST":
        # 长开模式 mark_done 工具走这里
        msg = {
            "id": f"receipt_{len(CREATED)+1}",
            "status": "completed",
            "metadata": {"receipt_kind": "done", "parent_message_id": url.split("/messages/", 1)[1].split("/", 1)[0]},
            "body": (body or {}).get("note"),
            "result_status": (body or {}).get("result_status"),
        }
        CREATED.append(msg)
        return {"data": msg}
    return {"_status": 404, "_error": f"unmatched url={url} method={method}"}


# ---- env + patch ----------------------------------------------------------
import os
os.environ["PLATFORM_API_BASE"] = "http://127.0.0.1:8010"
os.environ["PLATFORM_PROJECT_ID"] = "proj_demo"
os.environ["PLATFORM_SEAT_ID"] = "seat_alice"
os.environ["PLATFORM_WORKSTATION_ID"] = "pc1"
os.environ["PLATFORM_AUTH_TOKEN"] = "dev-token"

mod._http_json = fake_http_json


def call(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    return mod.handle({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})


def call_tool(name: str, args: dict, req_id: int = 1) -> dict:
    resp = call("tools/call", {"name": name, "arguments": args}, req_id)
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def main() -> int:
    print("=" * 60)
    print("Step 8 验收：seat-mcp-server")
    print("=" * 60)

    results = []

    print("\n[A] MCP 协议握手")
    init = call("initialize")
    results.append(_check("initialize 返回 protocolVersion", init.get("result", {}).get("protocolVersion") == mod.PROTOCOL_VERSION))
    results.append(_check("serverInfo.name == seat-mcp", init.get("result", {}).get("serverInfo", {}).get("name") == mod.SERVER_NAME))
    results.append(_check("声明 tools capability", "tools" in init.get("result", {}).get("capabilities", {})))

    print("\n[B] tools/list")
    tlist = call("tools/list")
    tools = [t["name"] for t in tlist.get("result", {}).get("tools", [])]
    results.append(_check("有 list_peers", "list_peers" in tools))
    results.append(_check("有 request_help", "request_help" in tools))
    results.append(_check("有 dispatch_to_peer", "dispatch_to_peer" in tools))
    results.append(_check("有 read_my_inbox", "read_my_inbox" in tools))
    results.append(_check("有 mark_done（长开模式专用）", "mark_done" in tools))
    rh = next((t for t in tlist["result"]["tools"] if t["name"] == "request_help"), {})
    results.append(_check("request_help inputSchema 有 role", "role" in (rh.get("inputSchema", {}).get("properties", {}))))
    results.append(_check("request_help inputSchema 有 ask", "ask" in (rh.get("inputSchema", {}).get("properties", {}))))
    md = next((t for t in tlist["result"]["tools"] if t["name"] == "mark_done"), {})
    results.append(_check("mark_done inputSchema 有 message_id", "message_id" in (md.get("inputSchema", {}).get("properties", {}))))
    results.append(_check("mark_done inputSchema 有 body", "body" in (md.get("inputSchema", {}).get("properties", {}))))

    print("\n[C] list_peers — 区分同/跨工位")
    peers = call_tool("list_peers", {})
    results.append(_check("ok=True", peers.get("ok") is True))
    same_ids = [p["seat_id"] for p in peers.get("same_workstation", [])]
    cross_ids = [p["seat_id"] for p in peers.get("cross_workstation", [])]
    results.append(_check("Bob 在同工位 (pc1)", "seat_bob" in same_ids))
    results.append(_check("Carol 在跨工位 (pc2)", "seat_carol" in cross_ids))
    results.append(_check("自己 (Alice) 不在结果里", "seat_alice" not in same_ids and "seat_alice" not in cross_ids))
    carol = next((p for p in peers["cross_workstation"] if p["seat_id"] == "seat_carol"), {})
    results.append(_check("Carol is_lead=True（pc2 工位长）", carol.get("is_lead") is True))

    print("\n[D] request_help — 同工位伙伴 → queued（免审）")
    CREATED.clear()
    r = call_tool("request_help", {"role": "reviewer", "ask": "帮我看 PR #42"})
    results.append(_check("ok=True", r.get("ok") is True))
    results.append(_check("匹配到 Bob", r.get("matched_peer", {}).get("seat_id") == "seat_bob"))
    results.append(_check("status=queued（同工位免审）", r.get("status") == "queued"))
    results.append(_check("needs_review=False", r.get("needs_review") is False))
    results.append(_check("后端真创建了一条消息", len(CREATED) == 1))
    results.append(_check("消息 sender=Alice/recipient=Bob", CREATED[0]["sender_id"] == "seat_alice" and CREATED[0]["recipient_id"] == "seat_bob"))

    print("\n[E] request_help — 跨工位 → pending_review")
    CREATED.clear()
    r = call_tool("request_help", {"role": "后端", "ask": "API 怎么改"})
    results.append(_check("匹配到 Carol", r.get("matched_peer", {}).get("seat_id") == "seat_carol"))
    results.append(_check("status=pending_review（跨工位强审）", r.get("status") == "pending_review"))
    results.append(_check("needs_review=True", r.get("needs_review") is True))
    results.append(_check("hint 提示等用户审", "审" in (r.get("hint") or "")))

    print("\n[F] dispatch_to_peer — 直接指名跨工位")
    CREATED.clear()
    r = call_tool("dispatch_to_peer", {"seat_id": "seat_carol", "title": "请联调 /api/foo", "body": "需要支持 paginate"})
    results.append(_check("ok=True", r.get("ok") is True))
    results.append(_check("status=pending_review", r.get("status") == "pending_review"))
    results.append(_check("recipient=Carol", CREATED and CREATED[0]["recipient_id"] == "seat_carol"))
    results.append(_check("body 含工具来源标记", "dispatch_to_peer" in (CREATED[0]["body"] if CREATED else "")))

    print("\n[G] mark_done — 长开模式写 done 回执")
    CREATED.clear()
    md = call_tool("mark_done", {"message_id": "msg_incoming_xyz", "body": "已修复，PR https://github.com/owner/repo/pull/42"})
    results.append(_check("ok=True", md.get("ok") is True))
    results.append(_check("parent_message_id 回带", md.get("parent_message_id") == "msg_incoming_xyz"))
    results.append(_check("receipt_kind=done", md.get("receipt_kind") == "done"))
    results.append(_check("后端真创建了一条回执消息", len(CREATED) == 1))
    results.append(_check("回执 status=completed", CREATED and CREATED[0].get("status") == "completed"))
    bad_md = call_tool("mark_done", {"message_id": "", "body": ""})
    results.append(_check("缺参数返回 ok=False", bad_md.get("ok") is False))

    print("\n[H] 错误路径")
    bad = call_tool("request_help", {"role": "", "ask": ""})
    results.append(_check("缺参数返回 ok=False", bad.get("ok") is False))
    bad2 = call_tool("request_help", {"role": "DBA", "ask": "help"})  # 没人匹配
    results.append(_check("没人匹配返回 ok=False", bad2.get("ok") is False))

    print("\n[I] 未知方法 / 未知工具")
    nope = call("unknown/method")
    results.append(_check("未知方法返回 -32601", nope.get("error", {}).get("code") == -32601))
    nope2 = call("tools/call", {"name": "no_such_tool", "arguments": {}})
    results.append(_check("未知工具返回 -32601", nope2.get("error", {}).get("code") == -32601))

    print("\n" + "=" * 60)
    failed = [r for r in results if not r["ok"]]
    if failed:
        print(f"FAIL — {len(failed)}/{len(results)} 项不通过")
        for r in failed:
            print(f"  · {r['name']}")
        return 1
    print(f"PASS — {len(results)}/{len(results)} 项全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
