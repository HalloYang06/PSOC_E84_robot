#!/usr/bin/env python
"""
Step 8 验收：seat-mcp-server 的协议 + 结构化 Need 工具是否齐备。

策略：
- 直接 import server 模块，喂 JSON-RPC 请求，断言响应。
- HTTP 调用用 monkey-patch 的 _http_json 拦截，不依赖真 API（CI 友好；本地真跑请用 e2e）。
- 关键断言：协议握手、工具列表、list_peers/create_need/check_my_needs/check_my_tasks
  都能在 monkey-patch 注入的"假后端"里走通。
- request_help 只作为兼容旧工具，必须转成结构化 Need；不能再按关键词直接派单。
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
NEEDS: list[dict] = []
TASKS: list[dict] = []


def fake_http_json(method, url, body=None):
    if url.endswith("/thread-workstations") and method == "GET":
        return {"data": SEATS}
    if url.endswith("/workstations") and method == "GET":
        return {"data": [
            {"id": "pc1", "name": "前端工位", "lead_seat_id": "seat_bob"},
            {"id": "pc2", "name": "后端工位", "lead_seat_id": "seat_carol"},
        ]}
    if url.endswith("/config") and method == "GET":
        return {"data": CFG}
    if "/structured-need" in url and method == "POST":
        need = {
            "id": f"need_{len(NEEDS)+1}",
            "status": "ready_to_route",
            "from_agent": body.get("requester_seat_id"),
            "target_seat_id": body.get("suggested_assignee") or "seat_bob",
            "title": body.get("title"),
        }
        preview = {
            "recommended_assignee_id": need["target_seat_id"],
            "recommended_assignee_name": "Bob (reviewer)" if need["target_seat_id"] == "seat_bob" else "Carol (backend)",
            "requires_review": False,
            "review_reason": "同工位/可信策略允许自动路由",
            "blocked_reason": None,
            "will_create_tasks": [{"source_need_id": need["id"], "assignee_seat_id": need["target_seat_id"]}],
        }
        NEEDS.append(need)
        if body.get("auto_route"):
            task = {"id": f"task_{len(TASKS)+1}", "title": need["title"], "status": "queued", "source_need_id": need["id"]}
            TASKS.append(task)
            return {"data": {"requirement": need, "route_preview": preview, "route_result": {"task": task, "dispatch": None}}}
        return {"data": {"requirement": need, "route_preview": preview, "route_result": None}}
    if "/queues?" in url and method == "GET":
        return {"data": {
            "my_needs": {"count": len(NEEDS), "items": NEEDS},
            "my_tasks": {"count": len(TASKS), "items": TASKS},
        }}
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
    results.append(_check("有 create_need", "create_need" in tools))
    results.append(_check("有 check_my_needs", "check_my_needs" in tools))
    results.append(_check("有 check_my_tasks", "check_my_tasks" in tools))
    results.append(_check("有 request_help", "request_help" in tools))
    results.append(_check("有 dispatch_to_peer", "dispatch_to_peer" in tools))
    results.append(_check("有 read_my_inbox", "read_my_inbox" in tools))
    results.append(_check("有 mark_done（长开模式专用）", "mark_done" in tools))
    cn = next((t for t in tlist["result"]["tools"] if t["name"] == "create_need"), {})
    cn_props = cn.get("inputSchema", {}).get("properties", {})
    results.append(_check("create_need inputSchema 有 required_capability", "required_capability" in cn_props))
    results.append(_check("create_need inputSchema 有 expected_output", "expected_output" in cn_props))
    results.append(_check("create_need inputSchema 有 acceptance_criteria", "acceptance_criteria" in cn_props))
    rh = next((t for t in tlist["result"]["tools"] if t["name"] == "request_help"), {})
    results.append(_check("request_help inputSchema 有 role", "role" in (rh.get("inputSchema", {}).get("properties", {}))))
    results.append(_check("request_help inputSchema 有 ask", "ask" in (rh.get("inputSchema", {}).get("properties", {}))))
    results.append(_check("request_help 描述标记为兼容旧工具", "兼容旧工具" in (rh.get("description") or "")))
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

    print("\n[D] create_need — 结构化 Need 写入我的需求")
    NEEDS.clear()
    TASKS.clear()
    r = call_tool("create_need", {
        "title": "需要 reviewer 检查 PR",
        "why_needed": "我需要同事帮我确认 PR 是否满足验收。",
        "required_capability": "reviewer",
        "expected_output": "给出可执行审查结论。",
        "input_context": "PR #42 修改了任务派发状态。",
        "risk_level": "low",
        "priority": "P2",
        "acceptance_criteria": ["说明是否通过", "指出阻塞点"],
    })
    results.append(_check("ok=True", r.get("ok") is True))
    results.append(_check("返回 need_id", bool(r.get("need_id"))))
    results.append(_check("返回推荐承接 NPC", r.get("recommended_assignee_id") == "seat_bob"))
    results.append(_check("后端真创建了一条 Need", len(NEEDS) == 1))
    needs = call_tool("check_my_needs", {"limit": 5})
    results.append(_check("check_my_needs 能看到 Need", needs.get("ok") is True and (needs.get("my_needs") or {}).get("count") == 1))

    print("\n[E] request_help — 兼容旧工具，只转成结构化 Need")
    NEEDS.clear()
    r = call_tool("request_help", {"role": "reviewer", "ask": "帮我看 PR #42"})
    results.append(_check("ok=True", r.get("ok") is True))
    results.append(_check("request_help 返回 need_id 而不是直接派单 message_id", bool(r.get("need_id")) and not r.get("message_id")))
    results.append(_check("request_help 创建 Need", len(NEEDS) == 1))

    print("\n[F] create_need auto_route — 允许时生成目标任务")
    NEEDS.clear()
    TASKS.clear()
    r = call_tool("create_need", {
        "title": "需要生成目标任务",
        "why_needed": "验证低风险结构化 Need 可以自动转任务。",
        "required_capability": "reviewer",
        "expected_output": "给出最小回执。",
        "input_context": "自动路由验收。",
        "risk_level": "low",
        "priority": "P2",
        "acceptance_criteria": ["目标任务出现"],
        "auto_route": True,
    })
    tasks = call_tool("check_my_tasks", {"limit": 5})
    results.append(_check("auto_route ok=True", r.get("ok") is True))
    results.append(_check("check_my_tasks 能读任务队列", tasks.get("ok") is True))
    results.append(_check("后端真创建目标 Task", len(TASKS) == 1))

    print("\n[G] dispatch_to_peer — 旧直派仍可用，但不是新主路径")
    CREATED.clear()
    r = call_tool("dispatch_to_peer", {"seat_id": "seat_carol", "title": "请联调 /api/foo", "body": "需要支持 paginate"})
    results.append(_check("ok=True", r.get("ok") is True))
    results.append(_check("status=pending_review", r.get("status") == "pending_review"))
    results.append(_check("recipient=Carol", CREATED and CREATED[0]["recipient_id"] == "seat_carol"))
    results.append(_check("body 含工具来源标记", "dispatch_to_peer" in (CREATED[0]["body"] if CREATED else "")))

    print("\n[H] mark_done — 长开模式写 done 回执")
    CREATED.clear()
    md = call_tool("mark_done", {"message_id": "msg_incoming_xyz", "body": "已修复，PR https://github.com/owner/repo/pull/42"})
    results.append(_check("ok=True", md.get("ok") is True))
    results.append(_check("parent_message_id 回带", md.get("parent_message_id") == "msg_incoming_xyz"))
    results.append(_check("receipt_kind=done", md.get("receipt_kind") == "done"))
    results.append(_check("后端真创建了一条回执消息", len(CREATED) == 1))
    results.append(_check("回执 status=completed", CREATED and CREATED[0].get("status") == "completed"))
    bad_md = call_tool("mark_done", {"message_id": "", "body": ""})
    results.append(_check("缺参数返回 ok=False", bad_md.get("ok") is False))

    print("\n[I] 错误路径")
    bad = call_tool("request_help", {"role": "", "ask": ""})
    results.append(_check("缺参数返回 ok=False", bad.get("ok") is False))
    bad2 = call_tool("create_need", {"title": "缺字段"})
    results.append(_check("结构化 Need 缺字段返回 ok=False", bad2.get("ok") is False))

    print("\n[J] 未知方法 / 未知工具")
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
