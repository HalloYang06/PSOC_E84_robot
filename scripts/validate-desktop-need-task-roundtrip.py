from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Desktop-origin messages plus Need/Task queue roundtrip on the cloud project.",
    )
    parser.add_argument("--api-base", default="http://106.55.62.122:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--workstation-id", default="platform-npc-1")
    parser.add_argument("--runner-id", default="runner-windows-desktop-main")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "desktop-need-task-roundtrip"))
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    headers: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
    timeout: int = 30,
) -> dict[str, object]:
    next_headers = {"Accept": "application/json"}
    if token:
        next_headers["Authorization"] = f"Bearer {token}"
    if headers:
        next_headers.update(headers)
    data = None
    if payload is not None:
        next_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=next_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def login(api_base: str, email: str, password: str) -> tuple[str, str]:
    payload = request_json(
        api_url(api_base, "/api/auth/session"),
        method="POST",
        payload={"email": email, "password": password},
    )
    data = data_of(payload)
    if not isinstance(data, dict):
        raise RuntimeError("login response missing data")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    token = text(data.get("access_token"))
    user_id = text(user.get("id") if isinstance(user, dict) else "")
    if not token:
        raise RuntimeError("login did not return access token")
    return token, user_id


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_event = f"desktop-user-roundtrip-{stamp}"
    report: dict[str, object] = {
        "ok": False,
        "api_base": api_base,
        "project_id": args.project_id,
        "workstation_id": args.workstation_id,
        "runner_id": args.runner_id,
        "steps": [],
        "issues": [],
        "warnings": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    try:
        token, user_id = login(api_base, args.login_email, args.login_password)
        step("login", "ok", user_id=user_id)

        desktop_user_note = (
            f"桌面版用户派单回流验收 {stamp}：这是用户直接在 Codex Desktop 线程里追加的任务，"
            "平台应显示为该 NPC 的桌面提问，不要求用户再审核自己的消息。"
        )
        desktop_payload = {
            "role": "user",
            "note": desktop_user_note,
            "phase": "user_dispatch",
            "session_id": "validation-desktop-session",
            "source_event_id": source_event,
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
            "linked_message_id": "",
            "metadata": {"validation": "desktop_need_task_roundtrip", "stamp": stamp},
        }
        desktop_sync = request_json(
            api_url(
                api_base,
                f"/api/collaboration/projects/{args.project_id}/thread-workstations/{args.workstation_id}/desktop-sync",
            ),
            method="POST",
            token=token,
            payload=desktop_payload,
        )
        desktop_data = data_of(desktop_sync)
        desktop_message = desktop_data.get("message") if isinstance(desktop_data, dict) else None
        if not isinstance(desktop_message, dict):
            raise RuntimeError(f"desktop sync response missing message: {desktop_sync}")
        report["desktop_user_message"] = {
            "id": text(desktop_message.get("id")),
            "message_type": text(desktop_message.get("message_type")),
            "sender_type": text(desktop_message.get("sender_type")),
            "recipient_id": text(desktop_message.get("recipient_id")),
            "status": text(desktop_message.get("status")),
        }
        if desktop_message.get("message_type") != "desktop_user_question":
            report["issues"].append("Desktop-origin user task did not become desktop_user_question")
        if desktop_message.get("sender_type") != "human":
            report["issues"].append("Desktop-origin user task did not preserve human sender")
        if desktop_message.get("status") not in {"open", "queued"}:
            report["issues"].append("Desktop-origin user task is not visible as open/queued work")
        step("desktop_user_dispatch_visible", "ok", message=report["desktop_user_message"])

        requirement_title = f"桌面需求闭环验收 {stamp}"
        requirement_payload = {
            "project_id": args.project_id,
            "title": requirement_title,
            "requirement_type": "thread_request",
            "module": "平台验收",
            "priority": "P1",
            "status": "ready_to_route",
            "from_agent": args.workstation_id,
            "to_agent": args.workstation_id,
            "target_seat_id": args.workstation_id,
            "context_summary": "验证 NPC 的需求池能写入结构化需求，并能派给对应 NPC 的任务/待办入口。",
            "expected_output": "平台里能看到需求、派发消息和最终回执关联。",
            "opening_message": "请做最小回执，确认需求池到任务池链路没有断。",
        }
        requirement = data_of(
            request_json(api_url(api_base, "/api/requirements"), method="POST", token=token, payload=requirement_payload)
        )
        if not isinstance(requirement, dict):
            raise RuntimeError("requirement create response missing data")
        report["requirement"] = {
            "id": text(requirement.get("id")),
            "title": text(requirement.get("title")),
            "status": text(requirement.get("status")),
            "from_agent": text(requirement.get("from_agent")),
            "to_agent": text(requirement.get("to_agent")),
            "target_seat_id": text(requirement.get("target_seat_id")),
        }
        step("need_created", "ok", requirement=report["requirement"])

        dispatch_result = data_of(
            request_json(
                api_url(api_base, f"/api/requirements/{requirement['id']}/dispatch"),
                method="POST",
                token=token,
                payload={
                    "target_type": "workstation",
                    "target_id": args.workstation_id,
                    "status": "queued",
                    "title": requirement_title,
                    "body": "这是需求派发验收：请目标 NPC 做最小回执。",
                },
            )
        )
        if not isinstance(dispatch_result, dict) or not isinstance(dispatch_result.get("message"), dict):
            raise RuntimeError("requirement dispatch response missing message")
        dispatch_message = dispatch_result["message"]
        report["requirement_dispatch"] = {
            "message_id": text(dispatch_message.get("id")),
            "message_type": text(dispatch_message.get("message_type")),
            "recipient_id": text(dispatch_message.get("recipient_id")),
            "status": text(dispatch_message.get("status")),
        }
        if dispatch_message.get("message_type") != "requirement_dispatch":
            report["issues"].append("Need dispatch did not create requirement_dispatch message")
        step("need_dispatched_to_npc", "ok", dispatch=report["requirement_dispatch"])

        final_reply = data_of(
            request_json(
                api_url(api_base, f"/api/requirements/{requirement['id']}/final-reply"),
                method="POST",
                token=token,
                payload={
                    "sender_type": "agent",
                    "sender_id": args.workstation_id,
                    "recipient_type": "human",
                    "recipient_id": user_id,
                    "status": "done",
                    "title": requirement_title,
                    "message": "需求闭环最小回执：需求已收到，并已按平台消息链回流。",
                },
            )
        )
        if not isinstance(final_reply, dict) or not isinstance(final_reply.get("message"), dict):
            raise RuntimeError("requirement final reply response missing collaboration message")
        report["requirement_final_reply"] = {
            "message_id": text(final_reply["message"].get("id")),
            "message_type": text(final_reply["message"].get("message_type")),
            "status": text(final_reply["message"].get("status")),
        }
        step("need_final_reply_visible", "ok", final_reply=report["requirement_final_reply"])

        task_title = f"桌面任务闭环验收 {stamp}"
        task = data_of(
            request_json(
                api_url(api_base, "/api/tasks"),
                method="POST",
                token=token,
                payload={
                    "project_id": args.project_id,
                    "title": task_title,
                    "description": "验证任务池能创建任务、派发到 NPC 坐席，并被目标电脑 runner 看到。",
                    "module": "平台验收",
                    "priority": "P1",
                    "status": "ready",
                    "assignee_agent_id": args.workstation_id,
                    "acceptance_criteria": ["任务创建成功", "派发产生 dispatch", "目标 runner 能看到或领取"],
                },
            )
        )
        if not isinstance(task, dict):
            raise RuntimeError("task create response missing data")
        report["task"] = {"id": text(task.get("id")), "title": text(task.get("title")), "status": text(task.get("status"))}
        step("task_created", "ok", task=report["task"])

        task_dispatch = data_of(
            request_json(
                api_url(api_base, f"/api/tasks/{task['id']}/dispatch"),
                method="POST",
                token=token,
                payload={
                    "workstation_id": args.workstation_id,
                    "status": "queued",
                    "notes": "桌面任务闭环验收派发。",
                },
            )
        )
        if not isinstance(task_dispatch, dict):
            raise RuntimeError("task dispatch response missing data")
        report["task_dispatch"] = {
            "id": text(task_dispatch.get("id")),
            "workstation_id": text(task_dispatch.get("workstation_id")),
            "runner_id": text(task_dispatch.get("runner_id")),
            "status": text(task_dispatch.get("status")),
        }
        if report["task_dispatch"]["runner_id"] != args.runner_id:
            report["issues"].append("Task dispatch did not target the expected bound runner")
        step("task_dispatched", "ok", dispatch=report["task_dispatch"])

        next_task = data_of(
            request_json(
                api_url(api_base, f"/api/runners/{args.runner_id}/next-task"),
                headers={"X-Runner-Id": args.runner_id},
            )
        )
        report["runner_next_task"] = {
            "id": text(next_task.get("id") if isinstance(next_task, dict) else ""),
            "title": text(next_task.get("title") if isinstance(next_task, dict) else ""),
            "status": text(next_task.get("status") if isinstance(next_task, dict) else ""),
        }
        if not isinstance(next_task, dict) or text(next_task.get("id")) != text(task.get("id")):
            report["issues"].append("Bound runner did not receive the newly dispatched Task")
        else:
            step("runner_received_task", "ok", task=report["runner_next_task"])
            result = data_of(
                request_json(
                    api_url(api_base, f"/api/runners/{args.runner_id}/tasks/{task['id']}/result"),
                    method="POST",
                    headers={"X-Runner-Id": args.runner_id},
                    payload={
                        "status": "done",
                        "message": "任务闭环最小回执：runner 已领取并写回结果。",
                        "result": {"validation": "desktop_need_task_roundtrip", "stamp": stamp},
                    },
                )
            )
            report["runner_task_result"] = {
                "event_id": text(result.get("id") if isinstance(result, dict) else ""),
                "event_type": text(result.get("event_type") if isinstance(result, dict) else ""),
            }
            step("runner_task_result_written", "ok", result=report["runner_task_result"])

        report["ok"] = not report["issues"]
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        report_path = output_dir / f"desktop-need-task-roundtrip-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"], "warnings": report["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
