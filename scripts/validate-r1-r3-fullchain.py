"""End-to-end validation for R1+R2+R3 + GH-identity, against the running platform.

Runs against the platform's own GitHub repo project (proj_ai_collab) on
http://127.0.0.1:8010. Logs in as lead@example.com (legacy login, no password
check), exercises every new endpoint and code path, and writes a JSON report to
artifacts/validate-r1-r3-fullchain-<stamp>.json.

It also opens a "second user" session (chief@local) and polls the same NPC's
collaboration messages for ~20 seconds to demonstrate cross-session sync —
that's the multi-user "virtual runner" piece.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8010"
PROJECT = "proj_ai_collab"
ARTIFACTS = Path("D:/ai合作产品/artifacts")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def http(method, path, *, token=None, payload=None, query=None):
    url = f"{API}{path}"
    if query:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(query)}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def login(email):
    code, data = http("POST", "/api/auth/session", payload={"email": email, "password": "demo-pass"})
    assert code == 200, f"login failed for {email}: {code} {data}"
    return data["data"]["access_token"], data["data"]["user"]["id"]


def section(name):
    print(f"\n=== {name} ===")


def main():
    report = {"checks": [], "errors": []}

    def record(name, ok, detail=None):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" :: {detail}" if detail and not ok else ""))
        if not ok:
            report["errors"].append({"name": name, "detail": detail})

    section("LOGIN")
    tok_a, uid_a = login("lead@example.com")
    tok_b, uid_b = login("chief@local")
    record("login lead@example.com", bool(tok_a), {"user_id": uid_a})
    record("login chief@local (2nd user)", bool(tok_b), {"user_id": uid_b})

    section("PROJECT BASELINE")
    code, prj = http("GET", f"/api/projects/{PROJECT}", token=tok_a)
    p = prj.get("data", prj)
    cfg = p.get("collaboration_config") or {}
    seats = cfg.get("thread_workstations") or []
    record("GET project", code == 200, {"github_url": p.get("github_url"), "seats": len(seats)})

    if len(seats) < 2:
        print("Need >=2 seats for same-workstation peer test, abort.")
        return 2
    seat1, seat2 = seats[0], seats[1]
    seat1_id = seat1["row_id"]
    seat2_id = seat2["row_id"]
    from urllib.parse import quote
    seat1_handle = quote(str(seat1.get("config_id") or seat1["id"]), safe="")
    seat1_node = seat1.get("computer_node_id")
    seat2_node = seat2.get("computer_node_id")
    record(
        "two seats discovered",
        True,
        {"s1": seat1["name"], "s1_node": seat1_node, "s2": seat2["name"], "s2_node": seat2_node},
    )

    section("R2-CDE/GH/R3-GH: project review_policy + workstation profile + NPC identity")
    code, resp = http(
        "PATCH",
        f"/api/collaboration/projects/{PROJECT}/review-policy",
        token=tok_a,
        payload={
            "default": "cross_workstation_only",
            "workstations": {seat1_node or "runner_pc1": "skip"},
        },
    )
    record("PATCH project review-policy", code == 200, {"status": code, "resp_keys": sorted((resp.get("data") or resp).keys())[:6] if isinstance(resp.get("data") or resp, dict) else None})

    target_node = seat1_node or "runner_pc1"
    code, resp = http(
        "PATCH",
        f"/api/collaboration/projects/{PROJECT}/workstation-profiles/{target_node}",
        token=tok_a,
        payload={
            "local_repo_path": "D:/ai合作产品",
            "review_policy": "skip",
            "knowledge_path": f"docs/workstations/{target_node}.md",
            "skill_inheritance": ["claude-code-skill", "scorecard-poll"],
        },
    )
    record("PATCH workstation-profiles", code == 200, {"status": code})

    code, resp = http(
        "PATCH",
        f"/api/collaboration/projects/{PROJECT}/thread-workstations/{seat1_handle}",
        token=tok_a,
        payload={
            "metadata": {
                "git_user_name": "wenjunyong666",
                "git_user_email": "wenjunyong666@users.noreply.github.com",
                "review_policy": "inherit",
                "seat_type": "npc",
            }
        },
    )
    record("PATCH NPC identity (seat metadata)", code in (200, 204), {"status": code, "handle": seat1_handle})

    from urllib.parse import quote as _q
    seat2_handle = _q(str(seat2.get("config_id") or seat2["id"]), safe="")
    code2, _ = http(
        "PATCH",
        f"/api/collaboration/projects/{PROJECT}/thread-workstations/{seat2_handle}",
        token=tok_a,
        payload={"metadata": {"seat_type": "npc", "review_policy": "force"}},
    )
    record("PATCH NPC2 as npc seat_type", code2 in (200, 204), {"status": code2})

    section("R1: send command, then peer-impersonation send")
    code, resp = http(
        "POST",
        "/api/collaboration/messages",
        token=tok_a,
        payload={
            "project_id": PROJECT,
            "recipient_type": "thread_workstation",
            "recipient_id": seat1_id,
            "sender_type": "human",
            "sender_id": uid_a,
            "subject": "[validate] 用户直接派单",
            "body": "请在 D:/ai合作产品 上 git status，给我一个汇报。",
            "channel": "validate-fullchain",
        },
    )
    record("send human→NPC1", code == 200, {"status": code, "msg_id": (resp.get("data") or {}).get("id")})

    code, resp = http(
        "POST",
        "/api/collaboration/messages",
        token=tok_a,
        payload={
            "project_id": PROJECT,
            "recipient_type": "thread_workstation",
            "recipient_id": seat2_id,
            "sender_type": "agent",
            "sender_id": seat1_id,
            "subject": "[validate] NPC1 代发给 NPC2",
            "body": f"（代发自 {seat1['name']}）\n\n你帮我跑下前端 typecheck，然后回我状态。",
            "channel": "validate-fullchain",
        },
    )
    record("peer impersonation NPC1→NPC2", code == 200, {"status": code, "sender_type": "agent"})

    section("R2 broadcast preview review_decisions")
    code, resp = http(
        "POST",
        f"/api/collaboration/projects/{PROJECT}/broadcast/preview",
        token=tok_a,
        payload={"scope": "all", "subject": "[validate] preview", "body": "广播预演"},
    )
    data = resp.get("data") or resp
    decisions = data.get("review_decisions") if isinstance(data, dict) else None
    force_count = data.get("review_force_count") if isinstance(data, dict) else None
    record(
        "broadcast preview returns review_decisions",
        code == 200 and isinstance(decisions, list),
        {"status": code, "force_count": force_count, "decisions_sample": (decisions or [])[:3]},
    )

    section("R2-I cross-workstation handoffs list")
    code, resp = http("GET", "/api/handoffs", token=tok_a, query={"project_id": PROJECT, "limit": 20})
    items = (resp.get("data") or {}).get("items") if isinstance(resp.get("data"), dict) else (resp.get("data") or [])
    record(
        "GET /api/handoffs",
        code == 200,
        {"status": code, "count": len(items) if isinstance(items, list) else None},
    )

    section("R3-F trigger requirement chain (manual + after_requirement)")
    code, resp = http(
        "POST",
        "/api/requirements",
        token=tok_a,
        payload={
            "project_id": PROJECT,
            "title": "[validate] 触发链 · 母需求",
            "summary": "验证 trigger=manual 立即派",
            "to_agent": seat1.get("agent_id") or "agent_fe_game",
            "context_summary": "验证脚本生成",
        },
    )
    parent_req = (resp.get("data") or {}).get("id") if isinstance(resp.get("data"), dict) else None
    record("create parent requirement", code in (200, 201) and parent_req, {"status": code, "id": parent_req})

    if parent_req:
        code, resp = http(
            "POST",
            f"/api/requirements/{parent_req}/dispatch",
            token=tok_a,
            payload={"target_type": "agent", "target_id": seat1.get("agent_id") or "agent_fe_game"},
        )
        record("dispatch parent (manual)", code in (200, 201, 204), {"status": code})

    code, resp = http(
        "POST",
        "/api/requirements",
        token=tok_a,
        payload={
            "project_id": PROJECT,
            "title": "[validate] 触发链 · 子需求 (after_requirement)",
            "summary": "等待母需求完成才触发",
            "to_agent": seat2.get("agent_id") or seat1.get("agent_id") or "agent_fe_game",
            "follow_up_from_requirement_id": parent_req,
            "context_summary": "trigger=after_requirement",
        },
    )
    follow = (resp.get("data") or {}).get("id") if isinstance(resp.get("data"), dict) else None
    record("create follow-up requirement", code in (200, 201) and follow, {"status": code, "id": follow})

    section("Multi-user sync (虚拟 runner)")
    deadline = time.time() + 20
    sightings = []
    last_count_a = last_count_b = 0
    while time.time() < deadline:
        code_a, msgs_a = http(
            "GET",
            "/api/collaboration/messages",
            token=tok_a,
            query={"project_id": PROJECT, "recipient_id": seat1_id, "limit": 30},
        )
        code_b, msgs_b = http(
            "GET",
            "/api/collaboration/messages",
            token=tok_b,
            query={"project_id": PROJECT, "recipient_id": seat1_id, "limit": 30},
        )
        items_a = (msgs_a.get("data") or {}).get("items") if isinstance(msgs_a.get("data"), dict) else (msgs_a.get("data") or [])
        items_b = (msgs_b.get("data") or {}).get("items") if isinstance(msgs_b.get("data"), dict) else (msgs_b.get("data") or [])
        last_count_a = len(items_a) if isinstance(items_a, list) else 0
        last_count_b = len(items_b) if isinstance(items_b, list) else 0
        sightings.append({"t": round(time.time() % 1000, 1), "a": last_count_a, "b": last_count_b})
        if last_count_a > 0 and last_count_b > 0 and last_count_a == last_count_b:
            break
        time.sleep(2)

    same = last_count_a == last_count_b
    record(
        "two sessions see same NPC1 message count",
        same and last_count_a > 0,
        {"a": last_count_a, "b": last_count_b, "samples": sightings[-5:]},
    )

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ARTIFACTS / f"validate-r1-r3-fullchain-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {out}")
    fail = sum(1 for c in report["checks"] if not c["ok"])
    print(f"PASS={len(report['checks']) - fail} FAIL={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
