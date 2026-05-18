from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
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
            "Validate the real cloud dispatch loop: create a computer node, pair a Runner, "
            "send a platform command, poll the Runner inbox, ack, complete, and verify visible receipts."
        ),
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "cloud-runner-dispatch"))
    parser.add_argument("--keep-node", action="store_true", help="Leave the temporary computer node in the project.")
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    runner_id: str | None = None,
    registration_token: str | None = None,
    payload: dict[str, object] | None = None,
    timeout: int = 30,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if runner_id:
        headers["X-Runner-Id"] = runner_id
    if registration_token:
        headers["x-runner-registration-token"] = registration_token
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
        payload["_http_status"] = exc.code
        return payload


def http_status(payload: dict[str, object]) -> int:
    raw = payload.get("_http_status")
    return int(raw) if isinstance(raw, int) else 200


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def list_messages(api_base: str, project_id: str, token: str, *, limit: int = 200) -> list[dict[str, object]]:
    payload = request_json(
        api_url(api_base, "/api/collaboration/messages", {"project_id": project_id, "limit": limit}),
        token=token,
    )
    data = data_of(payload)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def find_by_title(messages: list[dict[str, object]], *, title: str, message_type: str) -> dict[str, object] | None:
    for item in messages:
        if text(item.get("message_type")) == message_type and text(item.get("title")) == title:
            return item
    return None


def project_node(api_base: str, project_id: str, token: str, node_id: str) -> dict[str, object] | None:
    payload = request_json(api_url(api_base, f"/api/projects/{quote(project_id)}/config"), token=token)
    config = data_of(payload)
    collab = config.get("collaboration_config") if isinstance(config, dict) else {}
    nodes = collab.get("computer_nodes") if isinstance(collab, dict) else []
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if isinstance(node, dict) and text(node.get("id")) == node_id:
            return node
    return None


def project_node_direct(api_base: str, project_id: str, token: str, node_id: str) -> dict[str, object] | None:
    payload = request_json(api_url(api_base, f"/api/collaboration/projects/{quote(project_id)}/computer-nodes/{quote(node_id)}"), token=token)
    data = data_of(payload)
    if isinstance(data, dict) and text(data.get("id")) == node_id:
        return data
    return None


def wait_for_project_node(api_base: str, project_id: str, token: str, node_id: str, *, attempts: int = 5) -> dict[str, object]:
    last_payload: dict[str, object] = {}
    for attempt in range(attempts):
        node = project_node_direct(api_base, project_id, token, node_id)
        if node is not None:
            return node
        last_payload = request_json(api_url(api_base, f"/api/collaboration/projects/{quote(project_id)}/computer-nodes/{quote(node_id)}"), token=token)
        time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"computer node {node_id} was not readable after create: last_payload={last_payload}")


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = stamp.replace("-", "")[-10:]
    node_id = f"cloud-dispatch-{suffix}"
    runner_id = f"runner-{node_id}"
    title = f"云端派单闭环验收 {stamp}"
    body = "请回写最小回执：证明云端平台已经把任务派到这台电脑的 Runner 收件箱。"

    report: dict[str, object] = {
        "ok": False,
        "stamp": stamp,
        "api_base": api_base,
        "project_id": args.project_id,
        "node_id": node_id,
        "runner_id": runner_id,
        "command_title": title,
        "steps": [],
        "issues": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    token = ""
    command_id = ""
    try:
        login_payload = request_json(
            api_url(api_base, "/api/auth/session"),
            method="POST",
            payload={"email": args.login_email, "password": args.login_password},
        )
        login_data = data_of(login_payload)
        token = text(login_data.get("access_token") if isinstance(login_data, dict) else "")
        if not token:
            raise RuntimeError("login did not return access_token")
        step("login", "ok")

        create_payload = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes"),
            method="POST",
            token=token,
            payload={
                "id": node_id,
                "label": f"云端派单验收电脑 {suffix}",
                "status": "offline",
                "connection_kind": "remote",
                "host": "cloud-dispatch-validation",
                "os": "Linux/Windows compatible",
                "metadata": {"validation_kind": "cloud_runner_dispatch_fullchain"},
            },
        )
        if http_status(create_payload) != 200:
            raise RuntimeError(f"create computer node failed with HTTP {http_status(create_payload)}: {create_payload}")
        create_data = data_of(create_payload)
        if not isinstance(create_data, dict) or text(create_data.get("id")) != node_id:
            raise RuntimeError(f"create computer node returned unexpected payload: {create_payload}")
        wait_for_project_node(api_base, args.project_id, token, node_id)
        step("create_computer_node", "ok", create_payload=create_payload)

        pairing_payload = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}/pairing-token"),
            method="POST",
            token=token,
            payload={},
        )
        pairing_data = data_of(pairing_payload)
        pairing_token = text(pairing_data.get("token") if isinstance(pairing_data, dict) else "")
        if not pairing_token:
            raise RuntimeError("pairing token missing")
        step("issue_pairing_token", "ok")

        register_payload = request_json(
            api_url(api_base, "/api/runners/register"),
            method="POST",
            registration_token=pairing_token,
            payload={
                "runner_id": runner_id,
                "runner_name": f"Cloud dispatch validation runner {suffix}",
                "capabilities": ["codex", "threads", "filesystem"],
                "hardware_access": False,
                "computer_node_id": node_id,
            },
        )
        register_data = data_of(register_payload)
        if not isinstance(register_data, dict) or text(register_data.get("id")) != runner_id:
            raise RuntimeError(f"runner registration returned unexpected payload: {register_payload}")
        step("register_runner", "ok")

        node_after_register = wait_for_project_node(api_base, args.project_id, token, node_id)
        if text(node_after_register.get("runner_id")) != runner_id:
            bind_payload = request_json(
                api_url(api_base, f"/api/runners/{quote(runner_id)}/bindings"),
                method="POST",
                token=token,
                payload={"project_id": args.project_id, "computer_node_id": node_id},
            )
            bind_data = data_of(bind_payload)
            if not isinstance(bind_data, dict) or text(bind_data.get("runner_id")) != runner_id:
                raise RuntimeError(f"runner binding was not established after registration: {bind_payload}")
            step("explicit_runner_binding_repaired", "ok")
        else:
            step("verify_runner_binding", "ok")

        for index in range(2):
            request_json(
                api_url(api_base, "/api/runners/heartbeat"),
                method="POST",
                runner_id=runner_id,
                payload={"runner_id": runner_id},
            )
            step("runner_heartbeat", "ok", index=index + 1)
            time.sleep(0.25)

        node_after_heartbeat = project_node(api_base, args.project_id, token, node_id)
        report["node_after_heartbeat"] = node_after_heartbeat
        watch_state = text((node_after_heartbeat or {}).get("runner_watch_state"))
        effective_status = text((node_after_heartbeat or {}).get("runner_effective_status"))
        if watch_state != "watching" or effective_status != "online":
            report["issues"].append(
                f"computer node did not report online watching state: runner_watch_state={watch_state}, runner_effective_status={effective_status}"
            )
        step("verify_computer_online_state", "ok" if not report["issues"] else "warning", runner_watch_state=watch_state, runner_effective_status=effective_status)

        command_payload = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/runner-commands"),
            method="POST",
            token=token,
            payload={"computer_node_id": node_id, "title": title, "body": body},
        )
        command_data = data_of(command_payload)
        command_id = text(command_data.get("id") if isinstance(command_data, dict) else "")
        if not command_id:
            raise RuntimeError(f"runner command did not return id: {command_payload}")
        step("create_runner_command", "ok", command_id=command_id)

        inbox_payload = request_json(
            api_url(api_base, f"/api/runners/{quote(runner_id)}/inbox", {"limit": 20}),
            runner_id=runner_id,
        )
        inbox_data = data_of(inbox_payload)
        inbox = [item for item in inbox_data if isinstance(item, dict)] if isinstance(inbox_data, list) else []
        inbox_item = next((item for item in inbox if text(item.get("id")) == command_id), None)
        if inbox_item is None:
            raise RuntimeError(f"runner inbox did not include command {command_id}")
        step("runner_inbox_received", "ok", inbox_count=len(inbox), command_status=text(inbox_item.get("status")))

        ack_note = "Runner 已收到云端派单，正在回写最小回执。"
        ack_payload = request_json(
            api_url(api_base, f"/api/runners/{quote(runner_id)}/messages/{quote(command_id)}/ack"),
            method="POST",
            runner_id=runner_id,
            payload={"note": ack_note},
        )
        ack_data = data_of(ack_payload)
        ack_receipt = ack_data.get("receipt") if isinstance(ack_data, dict) else None
        if not isinstance(ack_receipt, dict) or text(ack_receipt.get("message_type")) != "runner_ack":
            raise RuntimeError(f"ack did not return runner_ack receipt: {ack_payload}")
        step("runner_ack", "ok", receipt_id=text(ack_receipt.get("id")))

        final_note = "Runner 已完成云端派单闭环验收：任务从平台进入 Runner 收件箱，并已返回最终回执。"
        final_payload = request_json(
            api_url(api_base, f"/api/runners/{quote(runner_id)}/messages/{quote(command_id)}/complete"),
            method="POST",
            runner_id=runner_id,
            payload={"result_status": "completed", "note": final_note},
        )
        final_data = data_of(final_payload)
        final_receipt = final_data.get("receipt") if isinstance(final_data, dict) else None
        if not isinstance(final_receipt, dict) or text(final_receipt.get("message_type")) != "runner_result":
            raise RuntimeError(f"complete did not return runner_result receipt: {final_payload}")
        step("runner_complete", "ok", receipt_id=text(final_receipt.get("id")))

        messages = list_messages(api_base, args.project_id, token)
        command_message = next((item for item in messages if text(item.get("id")) == command_id), None)
        ack_message = find_by_title(messages, title=title, message_type="runner_ack")
        result_message = find_by_title(messages, title=title, message_type="runner_result")
        report["visible_messages"] = {
            "command": command_message,
            "ack": ack_message,
            "result": result_message,
        }
        if not command_message or text(command_message.get("status")) != "completed":
            report["issues"].append("completed runner command is not visible with completed status")
        if not ack_message:
            report["issues"].append("runner ack receipt is not visible in collaboration messages")
        if not result_message or text(result_message.get("status")) != "completed":
            report["issues"].append("runner final receipt is not visible with completed status")
        step("verify_visible_receipts", "ok" if not report["issues"] else "failed")

        report["ok"] = not report["issues"]
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        if token and not args.keep_node:
            try:
                request_json(
                    api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}"),
                    method="DELETE",
                    token=token,
                )
                step("cleanup_computer_node", "ok")
            except Exception as exc:  # noqa: BLE001
                step("cleanup_computer_node", "warning", message=str(exc))
        report_path = output_dir / f"cloud-runner-dispatch-fullchain-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
