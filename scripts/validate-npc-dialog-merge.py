"""Smoke test merged NPC dialog: incoming + outgoing + role classification."""
from __future__ import annotations
import json, sys, urllib.request
from urllib.parse import quote, urlencode

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8010"
PROJECT = "proj_ai_collab"


def http(method, path, *, token=None, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    import urllib.error
    req = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def login(email):
    code, data = http("POST", "/api/auth/session", payload={"email": email, "password": "demo-pass"})
    return data["data"]["access_token"], data["data"]["user"]["id"]


def main():
    tok, uid = login("lead@example.com")

    code, prj = http("GET", f"/api/projects/{PROJECT}", token=tok)
    seats = ((prj.get("data") or prj).get("collaboration_config") or {}).get("thread_workstations") or []
    seat1 = seats[0]
    seat2 = seats[1]
    s1, s2 = seat1["id"], seat2["id"]
    print(f"NPC1={seat1['name']} ({s1}) NPC2={seat2['name']} ({s2})")

    # 1. user → NPC1（human）
    http("POST", "/api/collaboration/messages", token=tok, payload={
        "project_id": PROJECT, "recipient_type": "thread_workstation", "recipient_id": s1,
        "sender_type": "human", "sender_id": uid, "title": "[merge-test] 用户派单", "body": "请汇报状态",
    })
    # 2. NPC2 → NPC1（agent）
    http("POST", "/api/collaboration/messages", token=tok, payload={
        "project_id": PROJECT, "recipient_type": "thread_workstation", "recipient_id": s1,
        "sender_type": "agent", "sender_id": s2, "title": "[merge-test] NPC2 → NPC1", "body": "（代发自 NPC2）一起跑下 typecheck",
    })
    # 3. NPC1 → NPC2（self → peer）
    http("POST", "/api/collaboration/messages", token=tok, payload={
        "project_id": PROJECT, "recipient_type": "thread_workstation", "recipient_id": s2,
        "sender_type": "agent", "sender_id": s1, "title": "[merge-test] NPC1 → NPC2", "body": "好的我来补一段单元测试",
    })

    # 现在站在 NPC1 视角拉两路
    base = f"/api/collaboration/messages?project_id={PROJECT}&limit=50"
    c1, j1 = http("GET", f"{base}&recipient_type=thread_workstation&recipient_id={quote(s1, safe='')}", token=tok)
    c2, j2 = http("GET", f"{base}&sender_id={quote(s1, safe='')}", token=tok)
    incoming = j1.get("data") or []
    outgoing = j2.get("data") or []
    print(f"NPC1 视角 → incoming={len(incoming)} outgoing={len(outgoing)}")

    titles_in = [m.get("title") for m in incoming if (m.get("title") or "").startswith("[merge-test]")]
    titles_out = [m.get("title") for m in outgoing if (m.get("title") or "").startswith("[merge-test]")]
    print("incoming merge-test:", titles_in)
    print("outgoing merge-test:", titles_out)

    assert any("用户派单" in (t or "") for t in titles_in), "应当看到用户派单（incoming）"
    assert any("NPC2 → NPC1" in (t or "") for t in titles_in), "应当看到 NPC2 → NPC1（incoming）"
    assert any("NPC1 → NPC2" in (t or "") for t in titles_out), "应当看到 NPC1 → NPC2（outgoing，sender_id 过滤）"

    # 合并 + 去重 + 按时间排序
    seen = set()
    merged = []
    for m in incoming + outgoing:
        if m.get("id") in seen:
            continue
        seen.add(m.get("id"))
        merged.append(m)
    merged.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    print(f"合并后 = {len(merged)} 条（去重）")

    # 模拟前端 classifyRole
    peer_ids = {s2}
    print("\n=== 前端 role 分轨预演（最近 5 条） ===")
    for m in merged[:5]:
        st = (m.get("sender_type") or "").lower()
        sid = m.get("sender_id")
        if st == "human":
            role = "human"
        elif st == "agent" and sid == s1:
            role = "self"
        elif st == "agent" and sid in peer_ids:
            role = "peer"
        elif st == "agent":
            role = "external"
        else:
            role = "system"
        print(f"  [{role:8s}] {m.get('title') or m.get('body','')[:40]}")

    print("\nALL CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
