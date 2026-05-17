from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate structured NPC Need routing into target NPC Task on cloud API.")
    parser.add_argument("--api-base", default="http://106.55.62.122:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--requester-seat", default="platform-npc-1")
    parser.add_argument("--target-seat", default="platform-npc-2")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "structured-need-task-routing"))
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def request_json(url: str, *, method: str = "GET", token: str | None = None, payload: dict[str, object] | None = None, timeout: int = 30) -> tuple[int, dict[str, object]]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def login(api_base: str, email: str, password: str) -> tuple[str, str]:
    status, payload = request_json(
        api_url(api_base, "/api/auth/session"),
        method="POST",
        payload={"email": email, "password": password},
    )
    data = data_of(payload)
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"login failed: HTTP {status}: {payload}")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    token = text(data.get("access_token"))
    if not token:
        raise RuntimeError("login did not return access token")
    return token, text(user.get("id") if isinstance(user, dict) else "")


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "ok": False,
        "api_base": api_base,
        "project_id": args.project_id,
        "requester_seat": args.requester_seat,
        "target_seat": args.target_seat,
        "steps": [],
        "issues": [],
        "warnings": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    try:
        token, user_id = login(api_base, args.login_email, args.login_password)
        step("login", "ok", user_id=user_id)

        need_payload = {
            "project_id": args.project_id,
            "requester_seat_id": args.requester_seat,
            "title": f"结构化 Need 转任务验收 {stamp}",
            "why_needed": "我需要另一个 NPC 检查 P0.5 Need/Task 链路，确认不是关键词猜派单。",
            "required_capability": "platform need task routing validation",
            "expected_output": "目标 NPC 给出最小回执，说明已收到由 Need 路由生成的 Task。",
            "input_context": "这是云端 API 验证：NPC A 创建 Need，平台路由到 NPC B 的 Task。",
            "risk_level": "low",
            "priority": "P2",
            "suggested_assignee": args.target_seat,
            "acceptance_criteria": [
                "Need 出现在发起 NPC 的我的需求",
                "Task 出现在目标 NPC 的我的任务",
                "Task 记录 source_need_id 语义事件",
            ],
            "blocking_current_task": False,
            "module": "平台验收",
            "auto_route": False,
        }
        status, created_payload = request_json(
            api_url(api_base, "/api/requirements/structured-need"),
            method="POST",
            token=token,
            payload=need_payload,
        )
        created = data_of(created_payload)
        if status != 200 or not isinstance(created, dict):
            raise RuntimeError(f"structured need create failed: HTTP {status}: {created_payload}")
        requirement = created.get("requirement") if isinstance(created.get("requirement"), dict) else {}
        preview = created.get("route_preview") if isinstance(created.get("route_preview"), dict) else {}
        need_id = text(requirement.get("id") if isinstance(requirement, dict) else "")
        if not need_id:
            raise RuntimeError("structured need create did not return need id")
        report["need"] = {
            "id": need_id,
            "status": requirement.get("status"),
            "from_agent": requirement.get("from_agent"),
            "target_seat_id": requirement.get("target_seat_id"),
            "recommended_assignee_id": preview.get("recommended_assignee_id"),
            "requires_review": preview.get("requires_review"),
            "review_reason": preview.get("review_reason"),
        }
        if text(preview.get("recommended_assignee_id")) not in {args.target_seat, text(requirement.get("target_seat_id"))}:
            report["warnings"].append("route preview did not echo target alias directly; route-to-task will use preview target id")
        step("structured_need_created", "ok", need=report["need"])

        status, route_payload = request_json(
            api_url(api_base, f"/api/requirements/{need_id}/route-to-task"),
            method="POST",
            token=token,
            payload={
                "target_seat_id": args.target_seat,
                "approved": True,
                "auto_dispatch": True,
                "note": "validation approved low-risk structured Need route",
            },
        )
        routed = data_of(route_payload)
        if status != 200 or not isinstance(routed, dict):
            raise RuntimeError(f"route-to-task failed: HTTP {status}: {route_payload}")
        task = routed.get("task") if isinstance(routed.get("task"), dict) else {}
        dispatch = routed.get("dispatch") if isinstance(routed.get("dispatch"), dict) else {}
        task_id = text(task.get("id") if isinstance(task, dict) else "")
        if not task_id:
            raise RuntimeError("route-to-task did not create task")
        report["task"] = task
        report["dispatch"] = dispatch
        step("need_routed_to_task", "ok", task=task, dispatch=dispatch)

        status, requester_queue_payload = request_json(
            api_url(api_base, f"/api/seats/{args.requester_seat}/queues", {"project_id": args.project_id, "limit": 20}),
            token=token,
        )
        requester_queue = data_of(requester_queue_payload)
        if status != 200 or not isinstance(requester_queue, dict):
            raise RuntimeError(f"requester queue failed: HTTP {status}: {requester_queue_payload}")
        my_needs = requester_queue.get("my_needs") if isinstance(requester_queue.get("my_needs"), dict) else {}
        need_ids = {text(item.get("id")) for item in my_needs.get("items", []) if isinstance(item, dict)}
        if need_id not in need_ids:
            report["issues"].append("Created Need is not visible in requester NPC my_needs")
        step("requester_my_needs_checked", "ok", count=my_needs.get("count"), contains_need=need_id in need_ids)

        status, target_queue_payload = request_json(
            api_url(api_base, f"/api/seats/{args.target_seat}/queues", {"project_id": args.project_id, "limit": 20}),
            token=token,
        )
        target_queue = data_of(target_queue_payload)
        if status != 200 or not isinstance(target_queue, dict):
            raise RuntimeError(f"target queue failed: HTTP {status}: {target_queue_payload}")
        my_tasks = target_queue.get("my_tasks") if isinstance(target_queue.get("my_tasks"), dict) else {}
        task_ids = {text(item.get("id")) for item in my_tasks.get("items", []) if isinstance(item, dict)}
        if task_id not in task_ids:
            report["issues"].append("Routed Task is not visible in target NPC my_tasks")
        step("target_my_tasks_checked", "ok", count=my_tasks.get("count"), contains_task=task_id in task_ids)

        status, events_payload = request_json(api_url(api_base, f"/api/tasks/{task_id}/events"), token=token)
        events = data_of(events_payload)
        if status != 200 or not isinstance(events, list):
            raise RuntimeError(f"task events failed: HTTP {status}: {events_payload}")
        has_source_need_event = any(
            isinstance(item, dict)
            and item.get("event_type") == "created_from_need"
            and isinstance(item.get("data"), dict)
            and text(item["data"].get("source_need_id")) == need_id
            for item in events
        )
        if not has_source_need_event:
            report["issues"].append("Task is missing created_from_need event with source_need_id")
        step("task_source_need_event_checked", "ok", has_source_need_event=has_source_need_event)

        report["ok"] = not report["issues"]
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        report_path = output_dir / f"structured-need-task-routing-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"], "warnings": report["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
