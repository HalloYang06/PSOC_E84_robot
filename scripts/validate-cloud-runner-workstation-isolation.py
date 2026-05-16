from __future__ import annotations

import argparse
import json
import sys
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
    parser = argparse.ArgumentParser(description="Validate cloud workstation inbox isolation between bound runners.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "cloud-runner-isolation"))
    parser.add_argument("--keep-fixtures", action="store_true")
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    runner_id: str | None = None,
    workstation_id: str | None = None,
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
    if workstation_id:
        headers["X-Workstation-Id"] = workstation_id
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


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = stamp.replace("-", "")[-10:]
    node_a = f"iso-a-{suffix}"
    node_b = f"iso-b-{suffix}"
    runner_a = f"runner-{node_a}"
    runner_b = f"runner-{node_b}"
    workstation_id = f"iso-npc-{suffix}"
    title = f"云端多电脑隔离验收 {stamp}"
    report: dict[str, object] = {
        "ok": False,
        "api_base": api_base,
        "project_id": args.project_id,
        "node_a": node_a,
        "node_b": node_b,
        "runner_a": runner_a,
        "runner_b": runner_b,
        "workstation_id": workstation_id,
        "steps": [],
        "issues": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})

    token = ""
    command_id = ""
    try:
        status, login_payload = request_json(
            api_url(api_base, "/api/auth/session"),
            method="POST",
            payload={"email": args.login_email, "password": args.login_password},
        )
        if status != 200:
            raise RuntimeError(f"login failed with HTTP {status}: {login_payload}")
        login_data = data_of(login_payload)
        token = text(login_data.get("access_token") if isinstance(login_data, dict) else "")
        if not token:
            raise RuntimeError("login did not return access token")
        step("login", "ok")

        for node_id, runner_id, label in (
            (node_a, runner_a, "隔离验收电脑 A"),
            (node_b, runner_b, "隔离验收电脑 B"),
        ):
            status, payload = request_json(
                api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes"),
                method="POST",
                token=token,
                payload={
                    "id": node_id,
                    "label": f"{label} {suffix}",
                    "status": "offline",
                    "runner_id": runner_id,
                    "connection_kind": "remote",
                    "os": "Linux/Windows compatible",
                    "metadata": {"validation_kind": "cloud_runner_workstation_isolation"},
                },
            )
            if status != 200:
                raise RuntimeError(f"create node {node_id} failed with HTTP {status}: {payload}")
            reg_status, reg_payload = request_json(
                api_url(api_base, "/api/runners/register"),
                method="POST",
                runner_id=runner_id,
                payload={"runner_id": runner_id, "runner_name": label, "capabilities": ["codex", "threads"]},
            )
            if reg_status != 200:
                raise RuntimeError(f"register runner {runner_id} failed with HTTP {reg_status}: {reg_payload}")
            hb_status, hb_payload = request_json(
                api_url(api_base, "/api/runners/heartbeat"),
                method="POST",
                runner_id=runner_id,
                payload={"runner_id": runner_id},
            )
            if hb_status != 200:
                raise RuntimeError(f"heartbeat {runner_id} failed with HTTP {hb_status}: {hb_payload}")
            step("create_and_register_runner", "ok", node_id=node_id, runner_id=runner_id)

        status, ws_payload = request_json(
            api_url(api_base, f"/api/collaboration/projects/{quote(args.project_id)}/thread-workstations"),
            method="POST",
            token=token,
            payload={
                "id": workstation_id,
                "name": f"隔离验收 NPC {suffix}",
                "status": "active",
                "ai_provider_id": "codex",
                "computer_node_id": node_a,
                "responsibility": "Validate that only the bound runner can consume this inbox.",
                "metadata": {"validation_kind": "cloud_runner_workstation_isolation"},
            },
        )
        if status != 200:
            raise RuntimeError(f"create workstation failed with HTTP {status}: {ws_payload}")
        step("create_bound_workstation", "ok")

        status, command_payload = request_json(
            api_url(api_base, "/api/collaboration/messages"),
            method="POST",
            token=token,
            payload={
                "project_id": args.project_id,
                "message_type": "agent_command",
                "title": title,
                "body": "Only runner A should read and ack this command.",
                "recipient_type": "workstation",
                "recipient_id": workstation_id,
                "status": "queued",
            },
        )
        if status != 200:
            raise RuntimeError(f"create command failed with HTTP {status}: {command_payload}")
        command_data = data_of(command_payload)
        command_id = text(command_data.get("id") if isinstance(command_data, dict) else "")
        if not command_id:
            raise RuntimeError(f"command id missing: {command_payload}")
        step("create_agent_command", "ok", command_id=command_id)

        inbox_path = f"/api/collaboration/projects/{quote(args.project_id)}/thread-workstations/{quote(workstation_id)}/inbox"
        wrong_status, wrong_payload = request_json(
            api_url(api_base, inbox_path, {"limit": 20}),
            workstation_id=workstation_id,
            runner_id=runner_b,
        )
        if wrong_status != 403:
            raise RuntimeError(f"wrong runner read expected 403, got HTTP {wrong_status}: {wrong_payload}")
        step("wrong_runner_read_rejected", "ok", http_status=wrong_status)

        right_status, right_payload = request_json(
            api_url(api_base, inbox_path, {"limit": 20}),
            workstation_id=workstation_id,
            runner_id=runner_a,
        )
        if right_status != 200:
            raise RuntimeError(f"right runner read failed with HTTP {right_status}: {right_payload}")
        inbox_data = data_of(right_payload)
        inbox = [item for item in inbox_data if isinstance(item, dict)] if isinstance(inbox_data, list) else []
        if command_id not in {text(item.get("id")) for item in inbox}:
            raise RuntimeError(f"right runner inbox did not include {command_id}: {right_payload}")
        step("right_runner_read_allowed", "ok", inbox_count=len(inbox))

        ack_path = (
            f"/api/collaboration/projects/{quote(args.project_id)}/thread-workstations/"
            f"{quote(workstation_id)}/messages/{quote(command_id)}/ack"
        )
        wrong_ack_status, wrong_ack_payload = request_json(
            api_url(api_base, ack_path),
            method="POST",
            workstation_id=workstation_id,
            runner_id=runner_b,
            payload={"note": "Wrong runner should not ack."},
        )
        if wrong_ack_status != 403:
            raise RuntimeError(f"wrong runner ack expected 403, got HTTP {wrong_ack_status}: {wrong_ack_payload}")
        step("wrong_runner_ack_rejected", "ok", http_status=wrong_ack_status)

        right_ack_status, right_ack_payload = request_json(
            api_url(api_base, ack_path),
            method="POST",
            workstation_id=workstation_id,
            runner_id=runner_a,
            payload={"note": "Bound runner accepted this task."},
        )
        if right_ack_status != 200:
            raise RuntimeError(f"right runner ack failed with HTTP {right_ack_status}: {right_ack_payload}")
        step("right_runner_ack_allowed", "ok")

        complete_path = (
            f"/api/collaboration/projects/{quote(args.project_id)}/thread-workstations/"
            f"{quote(workstation_id)}/messages/{quote(command_id)}/complete"
        )
        complete_status, complete_payload = request_json(
            api_url(api_base, complete_path),
            method="POST",
            workstation_id=workstation_id,
            runner_id=runner_a,
            payload={
                "result_status": "completed",
                "note": "隔离验收已完成：只有绑定电脑读取并确认了这条测试任务。",
            },
        )
        if complete_status != 200:
            raise RuntimeError(f"right runner complete failed with HTTP {complete_status}: {complete_payload}")
        step("right_runner_complete_allowed", "ok")
        report["ok"] = True
        return 0
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        if token and not args.keep_fixtures:
            for path, name in (
                (f"/api/collaboration/projects/{quote(args.project_id)}/thread-workstations/{quote(workstation_id)}", "cleanup_workstation"),
                (f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_a)}", "cleanup_node_a"),
                (f"/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_b)}", "cleanup_node_b"),
            ):
                try:
                    status, payload = request_json(api_url(api_base, path), method="DELETE", token=token)
                    step(name, "ok" if status == 200 else "warning", http_status=status, payload=payload)
                except Exception as exc:  # noqa: BLE001
                    step(name, "warning", message=str(exc))
        report_path = output_dir / f"cloud-runner-workstation-isolation-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
