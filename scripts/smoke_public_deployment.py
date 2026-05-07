from __future__ import annotations

import argparse
import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch(url: str) -> tuple[int, dict[str, str], str]:
    request = Request(url, headers={"User-Agent": "ai-collab-smoke/1.0"})
    context = ssl.create_default_context()
    with urlopen(request, context=context, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status, headers, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the public AI collaboration deployment.")
    parser.add_argument("--base-url", required=True, help="Public browser base URL, for example https://coop.example.com")
    parser.add_argument(
        "--api-base-url",
        default="",
        help="Optional API base URL override. Defaults to the same base URL as the browser.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    api_base_url = (args.api_base_url or args.base_url).rstrip("/")

    report: dict[str, object] = {
        "base_url": base_url,
        "api_base_url": api_base_url,
        "checks": {},
        "ready": False,
    }

    try:
        login_status, login_headers, login_body = fetch(f"{base_url}/login")
        report["checks"] = {
            "login_status": login_status,
            "login_contains_html": "<html" in login_body.lower(),
            "login_contains_form": "<form" in login_body.lower() or "登录" in login_body or "login" in login_body.lower(),
            "hsts_header": login_headers.get("strict-transport-security", ""),
        }
    except (HTTPError, URLError, TimeoutError) as exc:
        report["checks"] = {"login_error": str(exc)}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    try:
        api_status, _, api_body = fetch(f"{api_base_url}/api/health")
        report["checks"] |= {
            "api_health_status": api_status,
            "api_health_contains_ok": '"status"' in api_body and '"ok"' in api_body,
        }
    except (HTTPError, URLError, TimeoutError) as exc:
        report["checks"] |= {"api_health_error": str(exc)}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    checks = report["checks"]
    report["ready"] = bool(
        checks.get("login_status") == 200
        and checks.get("login_contains_html")
        and checks.get("login_contains_form")
        and checks.get("api_health_status") == 200
        and checks.get("api_health_contains_ok")
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
