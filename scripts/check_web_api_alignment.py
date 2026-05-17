from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpResult:
    url: str
    status: int
    body: str
    error: str | None = None

    def json(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self.body or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def request_json(url: str, *, timeout: float = 8.0) -> HttpResult:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return HttpResult(url=url, status=int(res.status), body=res.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(url=url, status=int(exc.code), body=body, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - command-line diagnostic should report the real failure.
        return HttpResult(url=url, status=0, body="", error=str(exc))


def data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def error_code(payload: dict[str, Any]) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("code") or "")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the Web BFF proxy is aligned with the intended API instance."
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3001", help="Web origin, for example http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011", help="Direct API origin expected behind the Web proxy")
    parser.add_argument("--project-id", default="proj_ai_collab", help="Project id used for route-shape probes")
    args = parser.parse_args()

    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    project_id = args.project_id.strip()

    direct_health = request_json(f"{api_base}/api/health")
    proxy_health = request_json(f"{web_base}/api/proxy/health")

    route_query = urllib.parse.urlencode(
        {
            "project_id": project_id,
            "path": "artifacts/__web_api_alignment_probe__.log",
        }
    )
    direct_artifact = request_json(f"{api_base}/api/collaboration/artifacts/preview?{route_query}")
    proxy_artifact = request_json(f"{web_base}/api/proxy/collaboration/artifacts/preview?{route_query}")

    direct_health_data = data(direct_health.json())
    proxy_health_data = data(proxy_health.json())
    direct_artifact_code = error_code(direct_artifact.json())
    proxy_artifact_code = error_code(proxy_artifact.json())

    issues: list[str] = []
    if direct_health.status != 200:
        issues.append(f"direct API health failed: {direct_health.status} {direct_health.error or direct_health.body[:120]}")
    if proxy_health.status != 200:
        issues.append(f"web proxy health failed: {proxy_health.status} {proxy_health.error or proxy_health.body[:120]}")

    direct_port = direct_health_data.get("port")
    proxy_port = proxy_health_data.get("port")
    if direct_health.status == 200 and proxy_health.status == 200 and str(direct_port) != str(proxy_port):
        issues.append(f"web proxy points to API port {proxy_port}, expected {direct_port}")

    direct_deployment = direct_health_data.get("deployment")
    proxy_deployment = proxy_health_data.get("deployment")
    if isinstance(direct_deployment, dict) and isinstance(proxy_deployment, dict):
        direct_sha = str(direct_deployment.get("build_sha") or "")
        proxy_sha = str(proxy_deployment.get("build_sha") or "")
        if direct_sha and proxy_sha and direct_sha != proxy_sha:
            issues.append(f"web proxy points to API build {proxy_sha}, expected direct API build {direct_sha}")

    artifact_route_loaded = proxy_artifact_code in {"ARTIFACT_NOT_FOUND", "PROJECT_NOT_FOUND", "UNAUTHORIZED"}
    if proxy_artifact.status == 404 and proxy_artifact_code in {"", "HTTP_ERROR"}:
        issues.append("web proxy reached an API instance that does not know /api/collaboration/artifacts/preview")
    elif proxy_artifact.status == 500:
        issues.append("web proxy returned 500; check apps/web/app/api/proxy/[...path]/route.ts and Web process env")
    elif not artifact_route_loaded and proxy_artifact.status not in {200, 400}:
        issues.append(
            f"artifact preview route probe unexpected: status={proxy_artifact.status} code={proxy_artifact_code or '-'}"
        )

    report = {
        "ok": not issues,
        "web_base": web_base,
        "api_base": api_base,
        "direct_health": {
            "status": direct_health.status,
            "pid": direct_health_data.get("pid"),
            "port": direct_health_data.get("port"),
            "base_url": direct_health_data.get("base_url"),
            "deployment": direct_health_data.get("deployment"),
        },
        "proxy_health": {
            "status": proxy_health.status,
            "pid": proxy_health_data.get("pid"),
            "port": proxy_health_data.get("port"),
            "base_url": proxy_health_data.get("base_url"),
            "deployment": proxy_health_data.get("deployment"),
        },
        "artifact_preview_route": {
            "direct_status": direct_artifact.status,
            "direct_error_code": direct_artifact_code,
            "proxy_status": proxy_artifact.status,
            "proxy_error_code": proxy_artifact_code,
            "loaded_through_proxy": artifact_route_loaded,
        },
        "warnings": [
            "deployment fingerprint missing; cloud API has not been updated to a build that reports deployment metadata"
        ]
        if direct_health.status == 200 and not isinstance(direct_health_data.get("deployment"), dict)
        else [],
        "issues": issues,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
