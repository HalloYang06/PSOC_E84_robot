#!/usr/bin/env python
"""
Step 8 真端到端验收 — seat-mcp-server 自主求助全链路。

不是 mock，不是 import — 真启 server.py 作为 subprocess（就跟 Claude/Codex CLI 用的
方式一样），通过 stdio 喂 JSON-RPC，调三个工具，再去后端拉 inbox 验证真有消息。

链路：
  1. 登录平台拿 token，拉项目种子（确保 ≥2 同工位 + ≥1 跨工位 + lead）
  2. spawn server.py 子进程，注入 PLATFORM_* env（模拟 watcher 的注入）
  3. JSON-RPC initialize → tools/list → 调 request_help (同工位) → 拉 inbox 验 queued
  4. 调 request_help (跨工位) → 拉 inbox 验 pending_review
  5. /messages/{id}/review/approve → 验 status 变 queued
  6. 调 dispatch_to_peer → 验真创建
  7. 关闭子进程

用法：
  API_BASE=http://127.0.0.1:8010 PROJECT_ID=proj_ai_collab \
  python scripts/validate-seat-mcp-e2e.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SERVER_PY = REPO / "scripts" / "seat-mcp-server" / "server.py"

API = (os.environ.get("API_BASE") or "http://127.0.0.1:8010").rstrip("/")
PROJECT = os.environ.get("PROJECT_ID") or "proj_ai_collab"
EMAIL = os.environ.get("LOGIN_EMAIL") or "lead@example.com"
PASSWORD = os.environ.get("LOGIN_PASSWORD") or "password"


def _api(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        return {"_status": exc.code, "_raw": raw}


def login() -> str:
    r = _api("POST", "/api/auth/session", body={"email": EMAIL, "password": PASSWORD})
    return r["data"]["access_token"]


def get_project(token: str) -> dict:
    return _api("GET", f"/api/projects/{PROJECT}", token=token)["data"]


def patch_lead(token: str, node_id: str, lead_seat_id: str) -> None:
    _api(
        "PATCH",
        f"/api/collaboration/projects/{PROJECT}/workstation-profiles/{node_id}",
        token=token,
        body={"lead_seat_id": lead_seat_id},
    )


def list_inbox(token: str, recipient_seat_id: str, limit: int = 30) -> list[dict]:
    from urllib.parse import quote
    r = _api(
        "GET",
        f"/api/collaboration/messages?project_id={PROJECT}&recipient_type=thread_workstation"
        f"&recipient_id={quote(recipient_seat_id)}&limit={limit}",
        token=token,
    )
    return r.get("data") or []


def approve_message(token: str, message_id: str) -> dict:
    return _api("POST", f"/api/collaboration/messages/{message_id}/review/approve", token=token)


class McpClient:
    """Stdio JSON-RPC client over server.py subprocess."""

    def __init__(self, env: dict[str, str]):
        merged_env = {**os.environ, **env, "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(SERVER_PY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=merged_env,
        )
        self._req_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"server.py 没有返回，stderr={stderr!r}")
        return json.loads(line)

    def call_tool(self, name: str, args: dict) -> dict:
        resp = self.call("tools/call", {"name": name, "arguments": args})
        text = resp["result"]["content"][0]["text"]
        return json.loads(text)

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def _check(name: str, ok: bool, detail: str = "") -> dict:
    s = "PASS" if ok else "FAIL"
    print(f"  [{s}] {name}" + (f" — {detail}" if detail else ""))
    return {"name": name, "ok": ok, "detail": detail}


def main() -> int:
    print("=" * 60)
    print("Step 8 e2e — seat-mcp-server 真端到端")
    print("=" * 60)

    print("\n[准备] 登录 + 拉项目")
    token = login()
    project = get_project(token)
    seats = project["collaboration_config"]["thread_workstations"]
    by_node: dict[str, list[dict]] = {}
    for s in seats:
        by_node.setdefault(str(s.get("computer_node_id") or ""), []).append(s)
    same_node_seats = next((v for v in by_node.values() if len(v) >= 2), None)
    if not same_node_seats:
        print("FAIL — 项目里没 ≥2 个同工位 NPC")
        return 1
    cross_seat = next((s for s in seats if s["computer_node_id"] != same_node_seats[0]["computer_node_id"]), None)
    if cross_seat is None:
        print("FAIL — 项目里没跨工位 NPC")
        return 1
    npc_self, npc_peer = same_node_seats[0], same_node_seats[1]
    print(f"  本 NPC = {npc_self['name']} ({npc_self['id']})")
    print(f"  同工位伙伴 = {npc_peer['name']} ({npc_peer['id']})")
    print(f"  跨工位 = {cross_seat['name']} ({cross_seat['id']}) node={cross_seat['computer_node_id']}")

    print("\n[准备] 把跨工位的 lead 设到自己（保证 redirect 到具体 seat 而非空）")
    patch_lead(token, cross_seat["computer_node_id"], cross_seat["id"])

    env = {
        "PLATFORM_API_BASE": API,
        "PLATFORM_PROJECT_ID": PROJECT,
        "PLATFORM_SEAT_ID": str(npc_self["id"]),
        "PLATFORM_WORKSTATION_ID": str(npc_self["id"]),
        "PLATFORM_AUTH_TOKEN": token,
    }
    print(f"\n[启动] spawn server.py 子进程 (env: PLATFORM_SEAT_ID={env['PLATFORM_SEAT_ID']})")
    client = McpClient(env)

    results = []
    try:
        print("\n[A] MCP 协议握手")
        init = client.call("initialize")
        results.append(_check("initialize 协议版本", init["result"]["protocolVersion"] == "2024-11-05"))
        results.append(_check("serverInfo.name=seat-mcp", init["result"]["serverInfo"]["name"] == "seat-mcp"))

        print("\n[B] tools/list 三个工具齐全")
        tlist = client.call("tools/list")
        names = [t["name"] for t in tlist["result"]["tools"]]
        results.append(_check("list_peers 注册", "list_peers" in names))
        results.append(_check("request_help 注册", "request_help" in names))
        results.append(_check("dispatch_to_peer 注册", "dispatch_to_peer" in names))

        print("\n[C] list_peers — 真打后端，看到伙伴")
        peers = client.call_tool("list_peers", {})
        results.append(_check("ok=True", peers.get("ok") is True))
        same_ids = [p["seat_id"] for p in peers.get("same_workstation", [])]
        cross_ids = [p["seat_id"] for p in peers.get("cross_workstation", [])]
        results.append(_check(f"同工位伙伴含 {npc_peer['name']}", str(npc_peer["id"]) in same_ids,
                              f"got same={same_ids}"))
        results.append(_check(f"跨工位含 {cross_seat['name']}", str(cross_seat["id"]) in cross_ids,
                              f"got cross={cross_ids}"))

        print("\n[D] request_help (同工位) → 真创建消息 → 验 inbox queued")
        before = list_inbox(token, str(npc_peer["id"]))
        before_ids = {m["id"] for m in before}
        same_role = npc_peer["name"][:3]  # 用名字头几个字做关键字
        r = client.call_tool("request_help", {
            "role": same_role,
            "ask": "[e2e] 帮我看一下 SQL 是否会全表扫描",
        })
        results.append(_check("同工位 ok=True", r.get("ok") is True))
        results.append(_check("同工位 needs_review=False", r.get("needs_review") is False,
                              f"status={r.get('status')}"))
        time.sleep(1)
        after = list_inbox(token, str(npc_peer["id"]))
        new_msgs = [m for m in after if m["id"] not in before_ids]
        results.append(_check("inbox 真出现新消息", len(new_msgs) >= 1, f"new={len(new_msgs)}"))
        if new_msgs:
            results.append(_check("新消息 status=queued",
                                  new_msgs[0]["status"] == "queued",
                                  f"got {new_msgs[0]['status']}"))
            results.append(_check("新消息 sender=本 NPC",
                                  new_msgs[0]["sender_id"] == str(npc_self["id"]),
                                  f"got {new_msgs[0]['sender_id']}"))

        print("\n[E] request_help (跨工位) → pending_review")
        cross_role = cross_seat["name"][:3]
        before_cross = list_inbox(token, str(cross_seat["id"]))
        before_cross_ids = {m["id"] for m in before_cross}
        r = client.call_tool("request_help", {
            "role": cross_role,
            "ask": "[e2e] 后端 API 怎么改",
        })
        results.append(_check("跨工位 ok=True", r.get("ok") is True))
        results.append(_check("跨工位 needs_review=True", r.get("needs_review") is True,
                              f"status={r.get('status')}"))
        cross_msg_id = r.get("message_id")
        time.sleep(1)
        after_cross = list_inbox(token, str(cross_seat["id"]))
        new_cross = [m for m in after_cross if m["id"] not in before_cross_ids]
        results.append(_check("跨工位 inbox 真出现新消息", len(new_cross) >= 1,
                              f"new={len(new_cross)}"))
        if new_cross:
            results.append(_check("跨工位消息 status=pending_review",
                                  new_cross[0]["status"] == "pending_review",
                                  f"got {new_cross[0]['status']}"))
            results.append(_check("跨工位消息有 [路由] 元数据（跨工位/审核来源）",
                                  "[路由]" in (new_cross[0].get("body") or "") and
                                  "跨工位" in (new_cross[0].get("body") or ""),
                                  ""))

        print("\n[F] approve 待审消息 → status=queued")
        if cross_msg_id:
            approve_resp = approve_message(token, cross_msg_id)
            results.append(_check("approve API 返回 200",
                                  approve_resp.get("data") is not None or "_status" not in approve_resp,
                                  f"resp={list(approve_resp.keys())}"))
            time.sleep(0.5)
            after_approve = list_inbox(token, str(cross_seat["id"]))
            target = next((m for m in after_approve if m["id"] == cross_msg_id), None)
            if target:
                results.append(_check("approve 后 status=queued",
                                      target["status"] == "queued",
                                      f"got {target['status']}"))

        print("\n[G] dispatch_to_peer → 直接指名（仍走 review）")
        before2 = list_inbox(token, str(cross_seat["id"]))
        before2_ids = {m["id"] for m in before2}
        r = client.call_tool("dispatch_to_peer", {
            "seat_id": str(cross_seat["id"]),
            "title": "[e2e] 直接指名跨工位",
            "body": "需要你帮我联调 /api/foo",
        })
        results.append(_check("dispatch_to_peer ok=True", r.get("ok") is True))
        results.append(_check("dispatch_to_peer 跨工位 needs_review=True",
                              r.get("needs_review") is True))
        time.sleep(1)
        after2 = list_inbox(token, str(cross_seat["id"]))
        new2 = [m for m in after2 if m["id"] not in before2_ids]
        results.append(_check("dispatch 真创建消息", len(new2) >= 1))

    finally:
        client.close()

    print("\n" + "=" * 60)
    failed = [r for r in results if not r["ok"]]
    if failed:
        print(f"FAIL — {len(failed)}/{len(results)} 项不通过")
        for r in failed:
            print(f"  · {r['name']}{(' — ' + r['detail']) if r['detail'] else ''}")
        return 1
    print(f"PASS — {len(results)}/{len(results)} 项全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
