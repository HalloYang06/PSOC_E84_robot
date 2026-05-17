from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate cloud user flow for scanned threads -> NPC seats -> dispatch. "
            "This does not fake a live desktop Runner; it reports offline targets honestly."
        ),
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "cloud-npc-thread-dispatch"))
    parser.add_argument("--dispatch-seat", default="6", help="Seat number to send the smoke task to after binding.")
    parser.add_argument(
        "--allow-offline-dispatch",
        action="store_true",
        help="Create a queued smoke task even when the target computer is not in continuous pickup mode.",
    )
    parser.add_argument(
        "--cleanup-dispatch",
        action="store_true",
        help="Close the smoke task before exiting so validation does not leave user-visible queue items.",
    )
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, object] | None = None,
    timeout: int = 30,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def login(api_base: str, email: str, password: str) -> tuple[str, str]:
    payload = request_json(
        api_url(api_base, "/api/auth/session"),
        method="POST",
        payload={"email": email, "password": password},
    )
    data = data_of(payload)
    if not isinstance(data, dict):
        raise RuntimeError("login response missing data")
    token = text(data.get("access_token"))
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    user_id = text(user.get("id") if isinstance(user, dict) else "")
    if not token:
        raise RuntimeError("login did not return access_token")
    return token, user_id


def get_config(api_base: str, project_id: str, token: str) -> dict[str, object]:
    payload = request_json(api_url(api_base, f"/api/projects/{quote(project_id)}/config"), token=token)
    data = data_of(payload)
    if not isinstance(data, dict):
        raise RuntimeError("project config response missing data")
    return data


def list_messages(api_base: str, project_id: str, token: str, *, limit: int = 200) -> list[dict[str, object]]:
    payload = request_json(
        api_url(api_base, "/api/collaboration/messages", {"project_id": project_id, "limit": limit}),
        token=token,
    )
    data = data_of(payload)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def collaboration_config(config: dict[str, object]) -> dict[str, object]:
    value = config.get("collaboration_config")
    return value if isinstance(value, dict) else {}


def metadata(item: dict[str, object]) -> dict[str, object]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def scanned_threads(config: dict[str, object]) -> list[dict[str, object]]:
    collab = collaboration_config(config)
    rows = collab.get("thread_workstations")
    result: list[dict[str, object]] = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        md = metadata(row)
        provider = text(row.get("ai_provider_id") or row.get("ai_provider") or md.get("provider_id")).lower()
        source = text(md.get("source") or row.get("source")).lower()
        seat_type = text(md.get("seat_type") or row.get("seat_type")).lower()
        row_id = text(row.get("id") or row.get("workstation_id"))
        if provider != "codex":
            continue
        if seat_type in {"npc", "codex"}:
            continue
        if source != "runner_thread_scan":
            continue
        if not row_id:
            continue
        result.append(row)
    return result


def existing_npc_by_number(config: dict[str, object]) -> dict[str, dict[str, object]]:
    collab = collaboration_config(config)
    rows = collab.get("thread_workstations")
    result: dict[str, dict[str, object]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        md = metadata(row)
        seat_type = text(md.get("seat_type") or row.get("seat_type")).lower()
        name = text(row.get("name"))
        row_id = text(row.get("id") or row.get("workstation_id"))
        number = text(md.get("npc_number"))
        match = re.search(r"([1-6])\s*号", name)
        if not number and match:
            number = match.group(1)
        if number in {"1", "2", "3", "4", "5", "6"} and (seat_type in {"npc", "codex"} or row_id.startswith("platform-npc-")):
            result[number] = row
    return result


def find_numbered_threads(threads: list[dict[str, object]]) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    matched: dict[str, dict[str, object]] = {}
    candidates: dict[str, list[dict[str, object]]] = {str(i): [] for i in range(1, 7)}
    for thread in threads:
        haystack = " ".join(
            [
                text(thread.get("name")),
                text(thread.get("id")),
                text(metadata(thread).get("source_workstation_id")),
                text(thread.get("description")),
            ]
        )
        for number in range(1, 7):
            key = str(number)
            if re.search(rf"(^|[^0-9]){number}\s*号", haystack) or f"设为{number}号" in haystack:
                candidates[key].append(thread)
    for key, items in candidates.items():
        if items:
            matched[key] = items[-1]
    return matched, candidates


def create_or_update_npc(
    api_base: str,
    project_id: str,
    token: str,
    *,
    number: str,
    thread: dict[str, object],
    existing: dict[str, object] | None,
) -> dict[str, object]:
    thread_id = text(thread.get("id") or thread.get("workstation_id"))
    node_id = text(thread.get("computer_node_id") or thread.get("computer_node"))
    thread_name = text(thread.get("name"), thread_id)
    npc_id = text(existing.get("id") if isinstance(existing, dict) else "", f"platform-npc-{number}")
    payload = {
        "id": npc_id,
        "name": f"{number}号 NPC",
        "agent_id": f"codex-npc-{number}",
        "computer_node": text(thread.get("computer_node"), node_id),
        "computer_node_id": node_id,
        "ai_provider": "Codex",
        "ai_provider_id": "codex",
        "source_workstation_id": thread_id,
        "source_thread_id": thread_id,
        "bound_thread_id": thread_id,
        "target_thread_id": thread_id,
        "responsibility": f"AI 协作平台 {number} 号线程，绑定扫描到的线程：{thread_name}",
        "model": "gpt-5.4",
        "permission_level": "L2",
        "status": "active",
        "description": f"由平台扫描线程绑定，不手填线程 ID。来源线程名：{thread_name}",
        "metadata": {
            "seat_type": "codex",
            "provider_id": "codex",
            "provider_label": "Codex",
            "npc_number": number,
            "source_workstation_id": thread_id,
            "source_thread_id": thread_id,
            "bound_thread_id": thread_id,
            "source_thread_name": thread_name,
            "automation_enabled": True,
            "automation_heartbeat_seconds": 60,
            "validated_by": "cloud-npc-thread-dispatch-flow",
        },
    }
    if existing:
        target = text(existing.get("id") or existing.get("config_id") or existing.get("name"))
        payload.pop("id", None)
        response = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(project_id)}/thread-workstations/{quote(target)}"),
            method="PATCH",
            token=token,
            payload=payload,
        )
    else:
        response = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(project_id)}/thread-workstations"),
            method="POST",
            token=token,
            payload=payload,
        )
    data = data_of(response)
    if not isinstance(data, dict):
        raise RuntimeError(f"NPC bind response missing data for {number}: {response}")
    return data


def dispatch_to_workstation(
    api_base: str,
    project_id: str,
    token: str,
    user_id: str,
    *,
    workstation: dict[str, object],
    title: str,
    body: str,
) -> dict[str, object]:
    workstation_id = text(workstation.get("id") or workstation.get("config_id") or workstation.get("name"))
    payload = {
        "project_id": project_id,
        "agent_id": workstation_id,
        "message_type": "agent_command",
        "title": title,
        "body": body,
        "sender_type": "human",
        "sender_id": user_id,
        "recipient_type": "thread_workstation",
        "recipient_id": workstation_id,
        "status": "queued",
        "metadata": {
            "user_visible_goal": "云端体验派活到已绑定 NPC",
            "target_npc": text(workstation.get("name"), workstation_id),
        },
    }
    response = request_json(api_url(api_base, "/api/collaboration/messages"), method="POST", token=token, payload=payload)
    data = data_of(response)
    if not isinstance(data, dict):
        raise RuntimeError(f"dispatch response missing data: {response}")
    return data


def update_message_status(
    api_base: str,
    token: str,
    *,
    message_id: str,
    status: str,
    body: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"status": status}
    if body is not None:
        payload["body"] = body
    response = request_json(
        api_url(api_base, f"/api/collaboration/messages/{quote(message_id)}"),
        method="PATCH",
        token=token,
        payload=payload,
    )
    data = data_of(response)
    if not isinstance(data, dict):
        raise RuntimeError(f"message update response missing data: {response}")
    return data


def node_status_map(config: dict[str, object]) -> dict[str, dict[str, object]]:
    collab = collaboration_config(config)
    nodes = collab.get("computer_nodes")
    result: dict[str, dict[str, object]] = {}
    if not isinstance(nodes, list):
        return result
    for node in nodes:
        if isinstance(node, dict):
            result[text(node.get("id"))] = node
    return result


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "ok": False,
        "stamp": stamp,
        "api_base": api_base,
        "project_id": args.project_id,
        "steps": [],
        "missing_thread_numbers": [],
        "bound_npcs": {},
        "dispatch": None,
        "issues": [],
        "warnings": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    try:
        token, user_id = login(api_base, args.login_email, args.login_password)
        step("login", "ok", user_id=user_id)

        config = get_config(api_base, args.project_id, token)
        threads = scanned_threads(config)
        nodes = node_status_map(config)
        numbered, candidates = find_numbered_threads(threads)
        report["scanned_thread_count"] = len(threads)
        report["numbered_thread_candidates"] = {
            key: [
                {
                    "id": text(item.get("id") or item.get("workstation_id")),
                    "name": text(item.get("name")),
                    "computer_node_id": text(item.get("computer_node_id") or item.get("computer_node")),
                }
                for item in value
            ]
            for key, value in candidates.items()
        }
        step("scan_inventory", "ok", scanned_thread_count=len(threads), matched_numbers=sorted(numbered.keys()))

        existing = existing_npc_by_number(config)
        bound: dict[str, dict[str, object]] = {}
        for number in [str(i) for i in range(1, 7)]:
            thread = numbered.get(number)
            if not thread:
                report["missing_thread_numbers"].append(number)
                continue
            bound[number] = create_or_update_npc(
                api_base,
                args.project_id,
                token,
                number=number,
                thread=thread,
                existing=existing.get(number),
            )
        report["bound_npcs"] = {
            number: {
                "id": text(item.get("id") or item.get("config_id")),
                "name": text(item.get("name")),
                "computer_node_id": text(item.get("computer_node_id") or item.get("computer_node")),
                "source_workstation_id": text(metadata(item).get("source_workstation_id") or item.get("source_workstation_id")),
            }
            for number, item in bound.items()
        }
        step("bind_npc_seats", "ok" if bound else "warning", bound_numbers=sorted(bound.keys()))

        refreshed = get_config(api_base, args.project_id, token)
        nodes = node_status_map(refreshed)
        offline_bound_targets: list[dict[str, object]] = []
        for number, item in bound.items():
            node_id = text(item.get("computer_node_id") or item.get("computer_node"))
            node = nodes.get(node_id, {})
            watch_state = text(node.get("runner_watch_state"))
            effective = text(node.get("runner_effective_status"))
            if effective != "online" or watch_state != "watching":
                offline_bound_targets.append(
                    {
                        "number": number,
                        "node_id": node_id,
                        "runner_id": text(node.get("runner_id")),
                        "runner_watch_state": watch_state,
                        "runner_effective_status": effective,
                    }
                )
        report["offline_bound_targets"] = offline_bound_targets
        if offline_bound_targets and args.allow_offline_dispatch:
            report["warnings"].append(
                "绑定完成，但目标电脑当前没有常驻接单；本次按参数允许离线派活，测试消息会进入队列并按清理参数处理。"
            )
        elif offline_bound_targets:
            report["warnings"].append(
                "绑定完成，但目标电脑当前没有常驻接单；本次只验证绑定和状态，不创建会滞留的测试派单。"
            )
        step("check_runner_readiness", "ok" if not offline_bound_targets else "warning", offline_bound_targets=offline_bound_targets)

        dispatch_number = text(args.dispatch_seat, "6")
        target = bound.get(dispatch_number) or next(iter(bound.values()), None)
        if target:
            target_node_id = text(target.get("computer_node_id") or target.get("computer_node"))
            target_node = nodes.get(target_node_id, {})
            target_ready = (
                text(target_node.get("runner_effective_status")) == "online"
                and text(target_node.get("runner_watch_state")) == "watching"
            )
            if not target_ready and not args.allow_offline_dispatch:
                report["dispatch"] = {
                    "status": "skipped",
                    "reason": "target_computer_not_in_continuous_pickup",
                    "target_name": text(target.get("name")),
                    "target_node_id": target_node_id,
                }
                step("dispatch_smoke_task", "skipped", dispatch=report["dispatch"])
            else:
                title = f"1-6号线程派活体验 {stamp}"
                body = (
                    "请做最小回执即可：确认你已经收到平台从云端派到绑定线程的任务。"
                    "不要执行真实硬件、部署、ROS 写操作或电机动作。"
                )
                command = dispatch_to_workstation(
                    api_base,
                    args.project_id,
                    token,
                    user_id,
                    workstation=target,
                    title=title,
                    body=body,
                )
                command_id = text(command.get("id"))
                report["dispatch"] = {
                    "command_id": command_id,
                    "title": text(command.get("title")),
                    "status": text(command.get("status")),
                    "recipient_type": text(command.get("recipient_type")),
                    "recipient_id": text(command.get("recipient_id")),
                    "target_name": text(target.get("name")),
                    "target_ready": target_ready,
                }
                step("dispatch_smoke_task", "ok", dispatch=report["dispatch"])
                messages = list_messages(api_base, args.project_id, token)
                visible = next((item for item in messages if text(item.get("id")) == command_id), None)
                if not visible:
                    report["issues"].append("dispatch command was not visible in collaboration messages")
                else:
                    report["dispatch_visible_message"] = {
                        "id": text(visible.get("id")),
                        "title": text(visible.get("title")),
                        "status": text(visible.get("status")),
                        "recipient_id": text(visible.get("recipient_id")),
                    }
                step("verify_dispatch_visible", "ok" if visible else "failed")
                if command_id and args.cleanup_dispatch:
                    updated = update_message_status(
                        api_base,
                        token,
                        message_id=command_id,
                        status="cancelled",
                        body="云端 NPC 派工验收清理：测试消息已关闭，避免留在用户队列。",
                    )
                    report["dispatch_cleanup"] = {
                        "command_id": command_id,
                        "status": text(updated.get("status")),
                    }
                    step("cleanup_dispatch", "ok", dispatch_cleanup=report["dispatch_cleanup"])
        else:
            report["issues"].append("no numbered NPC could be bound, so dispatch was skipped")
            step("dispatch_smoke_task", "skipped")

        if report["missing_thread_numbers"]:
            report["warnings"].append(
                f"没有在当前云端扫描结果中找到这些编号线程：{', '.join(report['missing_thread_numbers'])}。需要目标电脑在线后重新扫描。"
            )
        report["ok"] = not report["issues"]
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        report_path = output_dir / f"cloud-npc-thread-dispatch-flow-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "warnings": report["warnings"], "issues": report["issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
