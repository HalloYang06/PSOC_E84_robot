#!/usr/bin/env python
"""
CLI 端可见的协作过程监控器（不调 AI CLI，只做"看"）。

作用：
  - 登录平台，指定一个 seat（NPC）
  - 每 3 秒轮询 inbox 和 sender=自己 的回执，彩色打印新消息
  - 让用户在 CLI 端能实时看到："我（或平台）派给谁、谁回了什么、走了什么审"

用法：
  python scripts/cli-see-collab.py \
    --project proj_ai_collab \
    --seat 前端工位 \
    [--api http://127.0.0.1:8010] \
    [--email lead@example.com --password password] \
    [--poll 3]

无登录凭据时从环境变量读 PLATFORM_AUTH_TOKEN / FARM_ACCESS_TOKEN。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import quote

COLOR = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "orange": "\033[38;5;208m",
}


def c(text: str, color: str) -> str:
    return f"{COLOR.get(color, '')}{text}{COLOR['reset']}"


def _api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_status": e.code, "_raw": e.read().decode("utf-8", errors="replace") if e.fp else ""}
    except Exception as e:
        return {"_status": 0, "_error": str(e)}


def login(api: str, email: str, password: str) -> str:
    r = _api("POST", f"{api}/api/auth/session", "", {"email": email, "password": password})
    return r.get("data", {}).get("access_token", "") if isinstance(r.get("data"), dict) else ""


def _msg_role(msg: dict, my_seat_id: str) -> str:
    sender = str(msg.get("sender_id") or "")
    sender_type = str(msg.get("sender_type") or "")
    recipient = str(msg.get("recipient_id") or "")
    if sender_type == "human":
        return "human"
    if sender == my_seat_id:
        return "self"
    if recipient == my_seat_id:
        return "to_me"
    return "observed"


def _color_for(msg: dict, my_seat_id: str) -> str:
    mtype = str(msg.get("message_type") or "").lower()
    status = str(msg.get("status") or "").lower()
    meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
    receipt_kind = str((meta or {}).get("receipt_kind") or "").lower()
    if status == "pending_review":
        return "orange"
    if "result" in mtype or receipt_kind in {"ack", "progress", "done", "reject"}:
        if receipt_kind == "reject":
            return "red"
        if receipt_kind == "done":
            return "green"
        if receipt_kind == "ack":
            return "cyan"
        return "blue"
    role = _msg_role(msg, my_seat_id)
    if role == "human":
        return "white"
    if role == "self":
        return "dim"
    if role == "to_me":
        return "magenta"
    return "dim"


def _short(s: str, n: int = 8) -> str:
    return s[:n] if len(s) > n else s


def _strip_platform_chatter(body: str) -> str:
    lines = body.split("\n")
    out = []
    for ln in lines:
        t = ln.strip()
        if t.startswith("[路由]"):
            continue
        if t.startswith("（NPC ") and "seat-mcp" in t:
            continue
        if t.startswith("（本消息由 NPC"):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def print_message(msg: dict, my_seat_id: str, name_map: dict[str, str]) -> None:
    color = _color_for(msg, my_seat_id)
    status = str(msg.get("status") or "").lower()
    mtype = str(msg.get("message_type") or "")
    title = str(msg.get("title") or "(无标题)")
    sender = str(msg.get("sender_id") or "")
    recipient = str(msg.get("recipient_id") or "")
    meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
    receipt_kind = str((meta or {}).get("receipt_kind") or "")
    parent = str((meta or {}).get("parent_message_id") or "")
    ts = str(msg.get("created_at") or "")[:19].replace("T", " ")
    sender_name = name_map.get(sender, sender[:12] if sender else "?")
    recv_name = name_map.get(recipient, recipient[:12] if recipient else "?")
    tag = f"[{mtype}]"
    if receipt_kind:
        tag += f"[{receipt_kind}]"
    if status == "pending_review":
        tag += "[待审]"
    elif status == "queued":
        tag += "[队列]"
    elif status == "completed":
        tag += "[完成]"
    head = f"{ts}  {tag}  {sender_name} → {recv_name}"
    print(c(head, color))
    print(c(f"  {title}", color))
    body = _strip_platform_chatter(str(msg.get("body") or ""))
    if body:
        for ln in body.splitlines()[:12]:
            print(c(f"  │ {ln}", "dim"))
        if len(body.splitlines()) > 12:
            print(c(f"  │ ... (省略 {len(body.splitlines()) - 12} 行)", "dim"))
    if parent:
        print(c(f"  ↳ 对应派单: {_short(parent, 12)}", "dim"))
    print()


def load_seats(api: str, project: str, token: str) -> dict[str, str]:
    r = _api("GET", f"{api}/api/collaboration/projects/{project}/thread-workstations", token)
    data = r.get("data") if isinstance(r, dict) else None
    if not isinstance(data, list):
        return {}
    # id -> name 映射（JSON alias id 是中文 name；我们也接 UUID 主键）
    m = {}
    for s in data:
        sid = str(s.get("id") or "")
        name = str(s.get("name") or sid)
        if sid:
            m[sid] = name
    # 补 DB 主键 UUID 也指向同 name：从 workstations/{}/seats 拉
    for row in data:
        ws = str(row.get("workstation_id") or "")
        if not ws:
            continue
        r2 = _api("GET", f"{api}/api/projects/{project}/workstations/{quote(ws)}/seats", token)
        inner = r2.get("data") if isinstance(r2, dict) else None
        if isinstance(inner, list):
            for s in inner:
                m[str(s.get("id") or "")] = str(s.get("name") or "")
    return {k: v for k, v in m.items() if k}


def resolve_seat_id(api: str, project: str, token: str, name_or_id: str) -> str | None:
    name_map = load_seats(api, project, token)
    if name_or_id in name_map:
        return name_or_id
    for sid, name in name_map.items():
        if name == name_or_id:
            return sid
    # fallback：按 config_id 搜
    r = _api("GET", f"{api}/api/collaboration/projects/{project}/thread-workstations", token)
    for s in (r.get("data") or []):
        if str(s.get("config_id") or "") == name_or_id:
            return str(s.get("id") or None)
    return None


def fetch_messages(api: str, project: str, token: str, seat_id: str, limit: int) -> list[dict]:
    # 取给我的 thread_workstation 消息 + 给我的 agent 消息（回执） + 我发出的
    # 注意：sender/recipient 既可能用 JSON 中文 id，也可能用 DB UUID 主键 — 都查一遍
    out = []
    candidates = [seat_id]
    name_map = load_seats(api, project, token)
    if seat_id in name_map:
        # 反查：拿到所有同 name 的 id（JSON id + DB UUID）
        n = name_map[seat_id]
        for k, v in name_map.items():
            if v == n and k not in candidates:
                candidates.append(k)
    # 也接 name 反查（脚本传入 UUID 时反推 name 加进去）
    for cid in list(candidates):
        nm = name_map.get(cid)
        if nm and nm not in candidates:
            candidates.append(nm)
    for sid in candidates:
        for params in (
            f"?project_id={project}&recipient_type=thread_workstation&recipient_id={quote(sid)}&limit={limit}",
            f"?project_id={project}&recipient_type=agent&recipient_id={quote(sid)}&limit={limit}",
            f"?project_id={project}&sender_id={quote(sid)}&limit={limit}",
        ):
            r = _api("GET", f"{api}/api/collaboration/messages{params}", token)
            data = r.get("data") if isinstance(r, dict) else None
            if isinstance(data, list):
                out.extend(data)
    # 去重（按 id）+ 按 created_at 升序
    seen = set()
    uniq = []
    for m in out:
        mid = str(m.get("id") or "")
        if mid and mid not in seen:
            seen.add(mid)
            uniq.append(m)
    uniq.sort(key=lambda x: str(x.get("created_at") or ""))
    return uniq


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.environ.get("API_BASE", "http://127.0.0.1:8010"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--seat", required=True, help="NPC 名字 / seat id / config_id")
    parser.add_argument("--email", default=os.environ.get("LOGIN_EMAIL", "lead@example.com"))
    parser.add_argument("--password", default=os.environ.get("LOGIN_PASSWORD", "password"))
    parser.add_argument("--poll", type=float, default=3.0)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--once", action="store_true", help="只拉一次，不轮询")
    args = parser.parse_args()

    api = args.api.rstrip("/")
    token = os.environ.get("PLATFORM_AUTH_TOKEN") or os.environ.get("FARM_ACCESS_TOKEN") or ""
    if not token:
        token = login(api, args.email, args.password)
    if not token:
        print(c("登录失败，无 token", "red"))
        return 2

    seat_id = resolve_seat_id(api, args.project, token, args.seat)
    if not seat_id:
        print(c(f"找不到 seat: {args.seat}", "red"))
        return 3

    name_map = load_seats(api, args.project, token)
    my_name = name_map.get(seat_id, args.seat)
    print(c(f"=== CLI 端可见：{my_name} ({_short(seat_id, 10)})  project={args.project}  poll={args.poll}s ===", "bold"))
    print(c("颜色图例：绿=done 蓝=其他回执 青=ack 紫=发给我 橙=待审 红=拒/失败 白=人 灰=观察/自发", "dim"))
    print()

    seen_ids: set[str] = set()
    first = True
    try:
        while True:
            msgs = fetch_messages(api, args.project, token, seat_id, args.limit)
            new_msgs = [m for m in msgs if str(m.get("id")) not in seen_ids]
            if first and new_msgs:
                # 首次进入：只打印最近 8 条历史，其余设为已看过
                head = new_msgs[-8:]
                tail = new_msgs[:-8] if len(new_msgs) > 8 else []
                for m in tail:
                    seen_ids.add(str(m.get("id")))
                if tail:
                    print(c(f"[历史] 已跳过 {len(tail)} 条旧消息，只显示最近 8 条", "dim"))
                for m in head:
                    seen_ids.add(str(m.get("id")))
                    print_message(m, seat_id, name_map)
                first = False
            else:
                for m in new_msgs:
                    seen_ids.add(str(m.get("id")))
                    print_message(m, seat_id, name_map)
                if new_msgs:
                    print(c(f"[{datetime.now().strftime('%H:%M:%S')}] {len(new_msgs)} 条新消息", "dim"))
            if args.once:
                return 0
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print(c("\n退出。", "dim"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
