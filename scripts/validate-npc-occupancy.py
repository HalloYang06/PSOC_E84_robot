"""Smoke test for NPC occupancy lock endpoints."""
from __future__ import annotations
import json, sys, urllib.error, urllib.request
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
    req = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def login(email):
    code, data = http("POST", "/api/auth/session", payload={"email": email, "password": "demo-pass"})
    assert code == 200, f"login failed: {code} {data}"
    return data["data"]["access_token"], data["data"]["user"]["id"], data["data"]["user"].get("name")


def main():
    print("=== two-user occupancy lock smoke ===")
    tok_a, uid_a, name_a = login("lead@example.com")
    tok_b, uid_b, name_b = login("chief@local")
    print(f"user A = {name_a} ({uid_a})")
    print(f"user B = {name_b} ({uid_b})")

    code, prj = http("GET", f"/api/projects/{PROJECT}", token=tok_a)
    seats = ((prj.get("data") or prj).get("collaboration_config") or {}).get("thread_workstations") or []
    seat = seats[0]
    handle = quote(str(seat.get("config_id") or seat["id"]), safe="")
    print(f"seat = {seat['name']} (handle={handle})")

    base = f"/api/collaboration/projects/{PROJECT}/thread-workstations/{handle}"

    # 1. A occupies
    code, r = http("POST", f"{base}/occupy", token=tok_a, payload={"user_name": name_a or "A"})
    print(f"A occupy → {code} ok={r.get('data',{}).get('ok')} holder={(r.get('data') or {}).get('occupancy', {}).get('user_id')}")
    assert code == 200 and (r.get('data') or {}).get('ok'), "A should own the seat"

    # 2. B tries (without force) → should fail with occupied_by
    code, r = http("POST", f"{base}/occupy", token=tok_b, payload={"user_name": name_b or "B"})
    occ_data = r.get('data') or {}
    print(f"B occupy(no force) → {code} ok={occ_data.get('ok')} occupied_by={occ_data.get('occupied_by',{}).get('user_id')}")
    assert occ_data.get('ok') is False, "B should be denied (no force)"
    assert occ_data.get('occupied_by',{}).get('user_id') == uid_a, "should report A as holder"

    # 3. A reads occupancy
    code, r = http("GET", f"{base}/occupancy", token=tok_a)
    holder = (r.get('data') or {}).get('occupancy') or {}
    print(f"GET occupancy → {code} holder={holder.get('user_id')} acquired_at={holder.get('acquired_at')}")
    assert holder.get('user_id') == uid_a

    # 4. B forces
    code, r = http("POST", f"{base}/occupy", token=tok_b, payload={"user_name": name_b or "B", "force": True})
    occ = (r.get('data') or {}).get('occupancy') or {}
    print(f"B occupy(force) → {code} ok={(r.get('data') or {}).get('ok')} new_holder={occ.get('user_id')} preempted_user={occ.get('preempted_user')}")
    assert (r.get('data') or {}).get('ok'), "B force should succeed"
    assert occ.get('user_id') == uid_b
    assert occ.get('preempted_user') == uid_a

    # 5. A tries to release (no longer holder) → should refuse
    code, r = http("POST", f"{base}/release", token=tok_a)
    rd = r.get('data') or {}
    print(f"A release(not holder) → {code} ok={rd.get('ok')} reason={rd.get('reason')}")
    assert rd.get('ok') is False, "A should not be allowed to release B's seat"

    # 6. B releases
    code, r = http("POST", f"{base}/release", token=tok_b)
    print(f"B release → {code} ok={(r.get('data') or {}).get('ok')}")
    assert (r.get('data') or {}).get('ok')

    # 7. After release, occupancy is None
    code, r = http("GET", f"{base}/occupancy", token=tok_a)
    holder_after = (r.get('data') or {}).get('occupancy')
    print(f"GET occupancy after release → {code} occupancy={holder_after}")
    assert holder_after is None

    print("\nALL 7 OCCUPANCY CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
