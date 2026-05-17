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


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate cloud runner-command routing for two bound computers.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "cloud-runner-command-routing"))
    parser.add_argument("--keep-fixtures", action="store_true")
    return parser.parse_args()


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


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
) -> tuple[int, dict[str, object]]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if runner_id:
        headers["X-Runner-Id"] = runner_id
    if registration_token:
        headers["X-Runner-Registration-Token"] = registration_token
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
        return exc.code, json.loads(raw) if raw else {}


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def command_ids(payload: dict[str, object]) -> set[str]:
    data = data_of(payload)
    if not isinstance(data, list):
        return set()
    return {text(item.get("id")) for item in data if isinstance(item, dict) and text(item.get("id"))}


def read_computer_node(api_base: str, project_id: str, token: str, node_id: str) -> tuple[int, dict[str, object]]:
    return request_json(
        api_url(api_base, f"/api/collaboration/projects/{quote(project_id)}/computer-nodes/{quote(node_id)}"),
        token=token,
    )


def wait_for_computer_node(
    api_base: str,
    project_id: str,
    token: str,
    node_id: str,
    *,
    attempts: int = 5,
) -> dict[str, object]:
    last_status = 0
    last_payload: dict[str, object] = {}
    for attempt in range(attempts):
        last_status, last_payload = read_computer_node(api_base, project_id, token, node_id)
        node_data = data_of(last_payload)
        if last_status == 200 and isinstance(node_data, dict) and text(node_data.get("id")) == node_id:
            return node_data
        time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"computer node {node_id} was not readable after create: HTTP {last_status}: {last_payload}")


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = stamp.replace("-", "")[-10:]
    node_a = f"route-a-{suffix}"
    node_b = f"route-b-{suffix}"
    runner_a = f"runner-{node_a}"
    runner_b = f"runner-{node_b}"
    report: dict[str, object] = {
        "ok": False,
        "api_base": api_base,
        "project_id": args.project_id,
        "node_a": node_a,
        "node_b": node_b,
        "runner_a": runner_a,
        "runner_b": runner_b,
        "steps": [],
        "issues": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    token = ""
    try:
        status, payload = request_json(
            api_url(api_base, "/api/auth/session"),
            method="POST",
            payload={"email": args.login_email, "password": args.login_password},
        )
        if status != 200:
            raise RuntimeError(f"login failed with HTTP {status}: {payload}")
        login_data = data_of(payload)
        token = text(login_data.get("access_token") if isinstance(login_data, dict) else "")
        if not token:
            raise RuntimeError("login did not return access token")
        step("login", "ok")

        for node_id, runner_id, label in (
            (node_a, runner_a, "定向派单电脑 A"),
            (node_b, runner_b, "定向派单电脑 B"),
        ):
            status, create_payload = request_json(
                api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes"),
                method="POST",
                token=token,
                payload={
                    "id": node_id,
                    "label": f"{label} {suffix}",
                    "status": "offline",
                    "connection_kind": "remote",
                    "os": "Linux/Windows compatible",
                    "metadata": {"validation_kind": "cloud_runner_command_routing"},
                },
            )
            if status != 200:
                raise RuntimeError(f"create computer node {node_id} failed with HTTP {status}: {create_payload}")
            wait_for_computer_node(api_base, args.project_id, token, node_id)
            step("create_computer_node", "ok", node_id=node_id)

            status, token_payload = request_json(
                api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}/pairing-token"),
                method="POST",
                token=token,
            )
            if status != 200:
                raise RuntimeError(f"rotate pairing token for {node_id} failed with HTTP {status}: {token_payload}")
            token_data = data_of(token_payload)
            pairing_token = text(token_data.get("token") if isinstance(token_data, dict) else "")
            if not pairing_token:
                raise RuntimeError(f"pairing token missing for {node_id}: {token_payload}")
            step("rotate_pairing_token", "ok", node_id=node_id)

            status, register_payload = request_json(
                api_url(api_base, "/api/runners/register"),
                method="POST",
                runner_id=runner_id,
                registration_token=pairing_token,
                payload={
                    "runner_id": runner_id,
                    "runner_name": label,
                    "computer_node_id": node_id,
                    "capabilities": ["codex", "threads", "runner-command-routing-validation"],
                },
            )
            if status != 200:
                raise RuntimeError(f"register runner {runner_id} failed with HTTP {status}: {register_payload}")
            step("register_runner_with_pairing", "ok", node_id=node_id, runner_id=runner_id)

            status, heartbeat_payload = request_json(
                api_url(api_base, "/api/runners/heartbeat"),
                method="POST",
                runner_id=runner_id,
                payload={"runner_id": runner_id},
            )
            if status != 200:
                raise RuntimeError(f"heartbeat {runner_id} failed with HTTP {status}: {heartbeat_payload}")
            step("runner_heartbeat", "ok", runner_id=runner_id)

            node_after_register = wait_for_computer_node(api_base, args.project_id, token, node_id)
            bound_runner_id = text(node_after_register.get("runner_id"))
            if bound_runner_id != runner_id:
                bind_status, bind_payload = request_json(
                    api_url(api_base, f"/api/runners/{quote(runner_id)}/bindings"),
                    method="POST",
                    token=token,
                    payload={"project_id": args.project_id, "computer_node_id": node_id},
                )
                if bind_status != 200:
                    raise RuntimeError(
                        f"runner {runner_id} did not bind during registration and explicit bind failed with HTTP {bind_status}: {bind_payload}"
                    )
                step("explicit_runner_binding_repaired", "ok", node_id=node_id, runner_id=runner_id)
            else:
                step("verify_runner_binding", "ok", node_id=node_id, runner_id=runner_id)

        commands: list[tuple[str, str, str]] = []
        for target_runner, target_node, title_suffix in (
            (runner_a, node_a, "A"),
            (runner_b, node_b, "B"),
        ):
            title = f"云端定向 runner 派单验收 {title_suffix} {stamp}"
            status, command_payload = request_json(
                api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/runner-commands"),
                method="POST",
                token=token,
                payload={
                    "computer_node_id": target_node,
                    "title": title,
                    "body": f"Only runner {title_suffix} should receive this validation command.",
                },
            )
            if status != 200:
                raise RuntimeError(f"create runner command for {target_node} failed with HTTP {status}: {command_payload}")
            data = data_of(command_payload)
            command_id = text(data.get("id") if isinstance(data, dict) else "")
            recipient_id = text(data.get("recipient_id") if isinstance(data, dict) else "")
            if not command_id or recipient_id != target_runner:
                raise RuntimeError(
                    f"runner command target mismatch for {target_node}: id={command_id!r} recipient={recipient_id!r}"
                )
            commands.append((command_id, target_runner, target_node))
            step("create_runner_command", "ok", command_id=command_id, runner_id=target_runner, node_id=target_node)

        for command_id, target_runner, _target_node in commands:
            other_runner = runner_b if target_runner == runner_a else runner_a
            for runner_id in (target_runner, other_runner):
                status, inbox_payload = request_json(
                    api_url(api_base, f"/api/runners/{quote(runner_id)}/inbox", {"status": "pending", "limit": 50}),
                    runner_id=runner_id,
                )
                if status != 200:
                    raise RuntimeError(f"read inbox for {runner_id} failed with HTTP {status}: {inbox_payload}")
                ids = command_ids(inbox_payload)
                if runner_id == target_runner and command_id not in ids:
                    raise RuntimeError(f"target runner {runner_id} inbox did not include {command_id}")
                if runner_id == other_runner and command_id in ids:
                    raise RuntimeError(f"non-target runner {runner_id} can see {command_id}")
            step("verify_inbox_isolation", "ok", command_id=command_id, runner_id=target_runner)

            status, ack_payload = request_json(
                api_url(api_base, f"/api/runners/{quote(target_runner)}/messages/{quote(command_id)}/ack"),
                method="POST",
                runner_id=target_runner,
                payload={"note": "目标电脑 runner 已接单。"},
            )
            if status != 200:
                raise RuntimeError(f"target runner ack failed with HTTP {status}: {ack_payload}")
            step("target_runner_ack", "ok", command_id=command_id, runner_id=target_runner)

            status, complete_payload = request_json(
                api_url(api_base, f"/api/runners/{quote(target_runner)}/messages/{quote(command_id)}/complete"),
                method="POST",
                runner_id=target_runner,
                payload={"result_status": "completed", "note": "目标电脑 runner 已完成定向派单验收。"},
            )
            if status != 200:
                raise RuntimeError(f"target runner complete failed with HTTP {status}: {complete_payload}")
            step("target_runner_complete", "ok", command_id=command_id, runner_id=target_runner)

            status, closed_inbox = request_json(
                api_url(api_base, f"/api/runners/{quote(target_runner)}/inbox", {"status": "pending", "limit": 50}),
                runner_id=target_runner,
            )
            if status != 200 or command_id in command_ids(closed_inbox):
                raise RuntimeError(f"completed command still visible as pending for {target_runner}: {closed_inbox}")
            step("completed_command_not_pending", "ok", command_id=command_id, runner_id=target_runner)

        report["ok"] = True
        return 0
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        if token and not args.keep_fixtures:
            for node_id, name in ((node_a, "cleanup_node_a"), (node_b, "cleanup_node_b")):
                try:
                    status, cleanup_payload = request_json(
                        api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}"),
                        method="DELETE",
                        token=token,
                    )
                    step(name, "ok" if status == 200 else "warning", http_status=status, payload=cleanup_payload)
                except Exception as exc:  # noqa: BLE001
                    step(name, "warning", message=str(exc))
        report_path = output_dir / f"cloud-runner-command-routing-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
