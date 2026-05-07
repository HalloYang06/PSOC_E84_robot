from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate human login/project presence through the public API.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    return parser.parse_args()


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session_status, session_payload = request_json(
        "POST",
        f"{api_base}/api/auth/session",
        payload={"email": args.login_email, "password": args.login_password},
    )
    if session_status != 200:
        raise RuntimeError(f"login failed: HTTP {session_status} {session_payload}")
    session_data = session_payload["data"]  # type: ignore[index]
    token = str(session_data["access_token"])  # type: ignore[index]
    user_id = str(session_data["user"]["id"])  # type: ignore[index]

    path = f"/projects/{args.project_id}?tab=human-party"
    presence_status, presence_payload = request_json(
        "POST",
        f"{api_base}/api/projects/{args.project_id}/presence",
        token=token,
        payload={"path": path},
    )
    if presence_status != 200:
        raise RuntimeError(f"presence failed: HTTP {presence_status} {presence_payload}")

    members_status, members_payload = request_json(
        "GET",
        f"{api_base}/api/projects/{args.project_id}/members",
        token=token,
    )
    if members_status != 200:
        raise RuntimeError(f"members failed: HTTP {members_status} {members_payload}")

    members = members_payload.get("data")
    if not isinstance(members, list):
        raise RuntimeError(f"members payload is not a list: {members_payload}")
    owner = next((item for item in members if isinstance(item, dict) and str(item.get("user_id")) == user_id), None)
    if not isinstance(owner, dict):
        raise RuntimeError(f"current user {user_id} is not in project members")
    if owner.get("project_presence_state") != "online":
        raise RuntimeError(f"current user is not project-online: {owner}")
    user = owner.get("user")
    if not isinstance(user, dict) or user.get("online_state") != "online":
        raise RuntimeError(f"current account is not login-online: {owner}")

    report = {
        "stamp": stamp,
        "api_base": api_base,
        "project_id": args.project_id,
        "user_id": user_id,
        "presence": presence_payload.get("data"),
        "current_member": owner,
        "member_count": len(members),
        "project_online_count": sum(1 for item in members if isinstance(item, dict) and item.get("project_presence_state") == "online"),
        "account_online_count": sum(
            1
            for item in members
            if isinstance(item, dict)
            and isinstance(item.get("user"), dict)
            and item["user"].get("online_state") == "online"
        ),
    }
    report_path = output_dir / f"project-presence-http-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "issues": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
