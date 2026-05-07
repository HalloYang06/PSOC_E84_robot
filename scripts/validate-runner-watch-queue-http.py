from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit whether visible computers and threads can actually accept platform work.",
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--message-limit", type=int, default=200)
    parser.add_argument("--queued-warning-minutes", type=int, default=10)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when live collaboration blockers are found.")
    return parser.parse_args()


def request_json(url: str, *, method: str = "GET", token: str | None = None, payload: dict[str, object] | None = None) -> dict[str, object]:
    from urllib.request import Request, urlopen

    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    value_text = str(value).strip()
    return value_text or fallback


def parse_stamp(value: object) -> datetime | None:
    value_text = text(value)
    if not value_text:
        return None
    try:
        normalized = value_text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def queued_age_minutes(message: dict[str, object], *, now: datetime) -> int | None:
    created_at = parse_stamp(message.get("created_at") or message.get("updated_at"))
    if created_at is None:
        return None
    return max(0, int((now - created_at).total_seconds() // 60))


def is_queued_status(value: object) -> bool:
    return text(value).lower() in {"queued", "open", "waiting_response", "routed", "pending"}


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    now = datetime.now(timezone.utc)

    login_payload = request_json(
        f"{api_base}/api/auth/session",
        method="POST",
        payload={"email": args.login_email, "password": args.login_password},
    )
    token = text((login_payload.get("data") or {}).get("access_token") if isinstance(login_payload.get("data"), dict) else "")
    if not token:
        raise RuntimeError("Login response did not include access_token")

    config_payload = request_json(f"{api_base}/api/projects/{args.project_id}/config", token=token)
    config_data = config_payload.get("data") if isinstance(config_payload, dict) else {}
    collaboration_config = config_data.get("collaboration_config") if isinstance(config_data, dict) else {}
    nodes = collaboration_config.get("computer_nodes") if isinstance(collaboration_config, dict) else []
    threads = collaboration_config.get("thread_workstations") if isinstance(collaboration_config, dict) else []
    nodes = [item for item in nodes if isinstance(item, dict)] if isinstance(nodes, list) else []
    threads = [item for item in threads if isinstance(item, dict)] if isinstance(threads, list) else []

    messages_payload = request_json(
        f"{api_base}/api/collaboration/messages?project_id={args.project_id}&limit={args.message_limit}",
        token=token,
    )
    messages = messages_payload.get("data") if isinstance(messages_payload, dict) else []
    messages = [item for item in messages if isinstance(item, dict)] if isinstance(messages, list) else []

    queued_types = {"agent_command", "runner_command", "thread_scan_request", "requirement_dispatch"}
    queued_messages = [
        item
        for item in messages
        if text(item.get("message_type")).lower() in queued_types and is_queued_status(item.get("status"))
    ]
    stale_queued_messages = [
        item
        for item in queued_messages
        if (queued_age_minutes(item, now=now) or 0) >= args.queued_warning_minutes
    ]

    ready_nodes = [
        node
        for node in nodes
        if text(node.get("runner_watch_state")).lower() == "watching"
        or text(node.get("runner_effective_status")).lower() in {"watching", "ready"}
    ]
    blocked_nodes = [
        {
            "id": text(node.get("id")),
            "label": text(node.get("label") or node.get("name")),
            "runner_id": text(node.get("runner_id")),
            "runner_watch_state": text(node.get("runner_watch_state"), "missing"),
            "runner_effective_status": text(node.get("runner_effective_status"), "missing"),
            "runner_heartbeat_age_seconds": node.get("runner_heartbeat_age_seconds"),
            "runner_watch_detail": text(node.get("runner_watch_detail")),
        }
        for node in nodes
        if node not in ready_nodes
    ]

    missing_watch_fields = [
        text(node.get("id") or node.get("label"), f"node-{index + 1}")
        for index, node in enumerate(nodes)
        if "runner_watch_state" not in node or "runner_effective_status" not in node
    ]

    issues: list[str] = []
    if missing_watch_fields:
        issues.append(f"missing runner watch fields on nodes: {', '.join(missing_watch_fields)}")
    if nodes and queued_messages and not ready_nodes:
        issues.append("platform has queued commands but no computer is in runner watch/ready state")
    if stale_queued_messages:
        oldest = max(queued_age_minutes(item, now=now) or 0 for item in stale_queued_messages)
        issues.append(f"{len(stale_queued_messages)} queued command(s) older than {args.queued_warning_minutes} minutes; oldest {oldest} minutes")

    report = {
        "stamp": stamp,
        "project_id": args.project_id,
        "project_name": text(config_data.get("name")) if isinstance(config_data, dict) else "",
        "summary": {
            "computer_count": len(nodes),
            "thread_count": len(threads),
            "runner_watch_ready_count": len(ready_nodes),
            "runner_watch_blocked_count": len(blocked_nodes),
            "queued_command_count": len(queued_messages),
            "stale_queued_command_count": len(stale_queued_messages),
        },
        "blocked_nodes": blocked_nodes,
        "queued_messages": [
            {
                "id": text(item.get("id")),
                "type": text(item.get("message_type")),
                "status": text(item.get("status")),
                "recipient_id": text(item.get("recipient_id")),
                "title": text(item.get("title")),
                "age_minutes": queued_age_minutes(item, now=now),
            }
            for item in queued_messages[:50]
        ],
        "issues": issues,
    }
    report_path = output_dir / f"runner-watch-queue-http-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), **report["summary"], "issues": issues}, ensure_ascii=False))
    return 1 if args.strict and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
