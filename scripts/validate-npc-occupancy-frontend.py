"""验证占用锁前端 hooks 走的端点对 web 端逻辑可用：
1) GET 当前占用 → 应有 Demo（前轮 release 后）None
2) 模拟「打开瓷砖」触发的 soft-claim（force=false）
3) 30s 心跳：再发 force=false（已是 holder），acquired_at 不变、heartbeat_at 更新
4) 释放
"""
from __future__ import annotations
import json, sys, time, urllib.request
from urllib.parse import quote

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
    return data["data"]["access_token"], data["data"]["user"]["id"], data["data"]["user"].get("name", email)


def main():
    tok, uid, uname = login("lead@example.com")

    code, prj = http("GET", f"/api/projects/{PROJECT}", token=tok)
    seats = ((prj.get("data") or prj).get("collaboration_config") or {}).get("thread_workstations") or []
    seat = seats[0]
    handle = quote(str(seat.get("config_id") or seat["id"]), safe="")
    print(f"seat={seat['name']} handle={handle} user={uname}({uid})")

    base = f"/api/collaboration/projects/{PROJECT}/thread-workstations/{handle}"

    # 1) 查
    code, j = http("GET", f"{base}/occupancy", token=tok)
    print(f"[GET] init occupancy = {(j.get('data') or {}).get('occupancy')}")

    # 2) soft-claim
    code, j = http("POST", f"{base}/occupy", token=tok, payload={"force": False, "user_name": uname})
    occ1 = (j.get("data") or {}).get("occupancy") or (j.get("data") or {}).get("occupied_by")
    print(f"[POST occupy force=false] ok={(j.get('data') or {}).get('ok')} holder={occ1.get('user_id') if occ1 else None}")
    assert (j.get("data") or {}).get("ok") is True, "前端打开瓷砖应当能拿到占用"
    acquired_at = occ1["acquired_at"]
    heartbeat_1 = occ1["heartbeat_at"]

    # 3) 心跳重发（force=false，自己是 holder）
    time.sleep(1.2)
    code, j = http("POST", f"{base}/occupy", token=tok, payload={"force": False, "user_name": uname})
    occ2 = (j.get("data") or {}).get("occupancy")
    print(f"[heartbeat] acquired_at unchanged? {occ2['acquired_at'] == acquired_at} heartbeat advanced? {occ2['heartbeat_at'] > heartbeat_1}")
    assert occ2["acquired_at"] == acquired_at, "持锁人重申 force=false 不应重置 acquired_at"
    assert occ2["heartbeat_at"] > heartbeat_1, "心跳应推进 heartbeat_at"

    # 4) 释放（模拟关瓷砖）
    code, j = http("POST", f"{base}/release", token=tok)
    print(f"[release] ok={(j.get('data') or {}).get('ok')}")
    assert (j.get("data") or {}).get("ok") is True

    code, j = http("GET", f"{base}/occupancy", token=tok)
    final = (j.get("data") or {}).get("occupancy")
    print(f"[GET] final occupancy = {final}")
    assert final is None, "release 后应空"

    print("\nALL FRONTEND-LIFECYCLE CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
