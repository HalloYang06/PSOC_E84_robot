from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test the collaboration workstation PATCH endpoint with a fresh auth token.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL. Default: http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--project-id",
        default="10f6a858-f3e4-467c-87f5-726caa3cc2be",
        help="Project id to verify.",
    )
    parser.add_argument(
        "--workstation-id",
        required=True,
        help="Workstation id to verify.",
    )
    parser.add_argument(
        "--auth-payload",
        default="artifacts/auth-cookie-payload-fresh-2026-04-22.json",
        help="Path to the auth payload JSON containing the token field.",
    )
    return parser.parse_args()


def load_token(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    token = str(payload.get("token") or "").strip()
    if not token:
        raise SystemExit(f"Missing token in auth payload: {path}")
    return token


def api_request(url: str, *, token: str, method: str = "GET", payload: dict | None = None) -> tuple[int, object]:
    request = urllib.request.Request(url, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        request.data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def main() -> int:
    args = parse_args()
    token = load_token(args.auth_payload)
    workstation_url = (
        f"{args.base_url}/api/collaboration/projects/{args.project_id}/thread-workstations/{args.workstation_id}"
    )

    get_status, get_body = api_request(workstation_url, token=token)
    if get_status != 200:
        print(
            json.dumps(
                {
                    "ok": False,
                    "step": "get",
                    "status": get_status,
                    "body": get_body,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    item = dict((get_body or {}).get("data") or {})
    patch_payload = {
        "status": item.get("status"),
    }
    patch_status, patch_body = api_request(workstation_url, token=token, method="PATCH", payload=patch_payload)
    if patch_status != 200:
        print(
            json.dumps(
                {
                    "ok": False,
                    "step": "patch",
                    "status": patch_status,
                    "body": patch_body,
                    "payload": patch_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    response_item = dict((patch_body or {}).get("data") or {})
    print(
        json.dumps(
            {
                "ok": True,
                "base_url": args.base_url,
                "project_id": args.project_id,
                "workstation_id": args.workstation_id,
                "status": patch_status,
                "name": response_item.get("name"),
                "returned_status": response_item.get("status"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
