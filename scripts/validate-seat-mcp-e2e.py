#!/usr/bin/env python
"""
Seat MCP structured Need e2e validation.

This script starts scripts/seat-mcp-server/server.py exactly as a CLI runner
would, calls the new structured Need tools over stdio JSON-RPC, then verifies
against the real platform API that:

1. The requester NPC sees the Need in "my needs".
2. Routing the Need creates a Task for the target NPC.
3. The target NPC sees that Task in "my tasks".

Legacy request_help/dispatch_to_peer are checked only as compatibility tools,
not as the main workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
SERVER_PY = REPO / "scripts" / "seat-mcp-server" / "server.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate real seat MCP structured Need -> target Task workflow.")
    parser.add_argument("--api-base", default=os.environ.get("API_BASE") or "http://127.0.0.1:8010")
    parser.add_argument("--project-id", default=os.environ.get("PROJECT_ID") or "proj_ai_collab")
    parser.add_argument("--login-email", default=os.environ.get("LOGIN_EMAIL") or "lead@example.com")
    parser.add_argument("--login-password", default=os.environ.get("LOGIN_PASSWORD") or "password")
    parser.add_argument("--requester-seat", default=os.environ.get("REQUESTER_SEAT") or "")
    parser.add_argument("--target-seat", default=os.environ.get("TARGET_SEAT") or "")
    parser.add_argument("--output-dir", default=str(REPO / "artifacts" / "seat-mcp-e2e"))
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def api_url(api_base: str, path: str, query: dict[str, object] | None = None) -> str:
    url = f"{api_base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


def request_json(
    api_base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, object] | None = None,
    query: dict[str, object] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, object]]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(api_url(api_base, path, query), data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def data_of(payload: dict[str, object]) -> object:
    return payload.get("data") if isinstance(payload, dict) else None


def login(api_base: str, email: str, password: str) -> str:
    status, payload = request_json(api_base, "POST", "/api/auth/session", payload={"email": email, "password": password})
    data = data_of(payload)
    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError(f"login failed: HTTP {status}: {payload}")
    return text(data.get("access_token"))


def choose_seats(api_base: str, token: str, project_id: str, requester: str, target: str) -> tuple[dict[str, object], dict[str, object]]:
    status, payload = request_json(api_base, "GET", f"/api/collaboration/projects/{project_id}/thread-workstations", token=token)
    data = data_of(payload)
    if status != 200 or not isinstance(data, list):
        raise RuntimeError(f"thread workstations read failed: HTTP {status}: {payload}")
    seats = [item for item in data if isinstance(item, dict)]
    if requester:
        requester_seat = next((s for s in seats if requester in {text(s.get("id")), text(s.get("config_id")), text(s.get("name"))}), None)
    else:
        requester_seat = seats[0] if seats else None
    if not requester_seat:
        raise RuntimeError(f"requester seat not found: {requester or '<auto>'}")
    requester_id = text(requester_seat.get("id"))
    if target:
        target_seat = next((s for s in seats if target in {text(s.get("id")), text(s.get("config_id")), text(s.get("name"))}), None)
    else:
        target_seat = next((s for s in seats if text(s.get("id")) != requester_id), None)
    if not target_seat:
        raise RuntimeError(f"target seat not found: {target or '<auto>'}")
    return requester_seat, target_seat


class McpClient:
    def __init__(self, env: dict[str, str]):
        merged_env = {**os.environ, **env, "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(SERVER_PY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=merged_env,
        )
        self._req_id = 0

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("MCP subprocess pipes are not available")
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"server.py returned no response; stderr={stderr!r}")
        return json.loads(line)

    def call_tool(self, name: str, args: dict[str, object]) -> dict[str, object]:
        resp = self.call("tools/call", {"name": name, "arguments": args})
        result = resp.get("result") if isinstance(resp, dict) else None
        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, list) or not content:
            raise RuntimeError(f"tool {name} returned malformed response: {resp}")
        first = content[0] if isinstance(content[0], dict) else {}
        return json.loads(text(first.get("text")))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


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
        "steps": [],
        "issues": [],
        "warnings": [],
    }

    def step(name: str, status: str, **extra: object) -> None:
        report["steps"].append({"name": name, "status": status, **extra})
        print(f"[{status.upper()}] {name}" + (f" {json.dumps(extra, ensure_ascii=False)}" if extra else ""))

    client: McpClient | None = None
    try:
        token = login(api_base, args.login_email, args.login_password)
        step("login", "ok")

        requester, target = choose_seats(api_base, token, args.project_id, args.requester_seat, args.target_seat)
        requester_id = text(requester.get("id"))
        target_id = text(target.get("id"))
        report["requester_seat"] = {"id": requester_id, "name": requester.get("name")}
        report["target_seat"] = {"id": target_id, "name": target.get("name")}
        step("seats_selected", "ok", requester=report["requester_seat"], target=report["target_seat"])

        client = McpClient(
            {
                "PLATFORM_API_BASE": api_base,
                "PLATFORM_PROJECT_ID": args.project_id,
                "PLATFORM_SEAT_ID": requester_id,
                "PLATFORM_WORKSTATION_ID": requester_id,
                "PLATFORM_AUTH_TOKEN": token,
            }
        )

        init = client.call("initialize")
        if init.get("result", {}).get("serverInfo", {}).get("name") != "seat-mcp":
            raise RuntimeError(f"unexpected initialize response: {init}")
        step("mcp_initialize", "ok")

        tools_resp = client.call("tools/list")
        tools = [item.get("name") for item in tools_resp.get("result", {}).get("tools", []) if isinstance(item, dict)]
        for required in ["create_need", "check_my_needs", "check_my_tasks", "request_help", "dispatch_to_peer"]:
            if required not in tools:
                raise RuntimeError(f"missing MCP tool {required}")
        step("mcp_tools_listed", "ok", tools=tools)

        peers = client.call_tool("list_peers", {})
        all_peer_ids = {
            text(item.get("seat_id"))
            for item in (peers.get("same_workstation") or []) + (peers.get("cross_workstation") or [])
            if isinstance(item, dict)
        }
        if target_id not in all_peer_ids:
            raise RuntimeError(f"target seat is not visible in list_peers: target={target_id} peers={sorted(all_peer_ids)}")
        step("mcp_peers_checked", "ok", peer_count=len(all_peer_ids))

        need_title = f"[e2e] 结构化 Need 到目标任务 {stamp}"
        need = client.call_tool(
            "create_need",
            {
                "title": need_title,
                "why_needed": "我需要目标 NPC 验证 P0 派单链路，不能再依赖关键词猜测。",
                "required_capability": "platform structured need task validation",
                "expected_output": "目标 NPC 的任务池出现由 Need 路由生成的任务。",
                "input_context": "这是 seat-mcp-server 真子进程 e2e 验收。",
                "risk_level": "low",
                "priority": "P2",
                "suggested_assignee": target_id,
                "acceptance_criteria": ["Need 在发起方我的需求中可见", "Task 在目标方我的任务中可见"],
                "module": "平台验收",
                "auto_route": False,
            },
        )
        need_id = text(need.get("need_id"))
        if need.get("ok") is not True or not need_id:
            raise RuntimeError(f"create_need failed: {need}")
        step("mcp_create_need", "ok", need_id=need_id, recommended=need.get("recommended_assignee_id"))

        my_needs = client.call_tool("check_my_needs", {"limit": 20})
        need_items = (my_needs.get("my_needs") or {}).get("items") if isinstance(my_needs.get("my_needs"), dict) else []
        if need_id not in {text(item.get("id")) for item in need_items if isinstance(item, dict)}:
            raise RuntimeError(f"created Need is not visible in requester queue: {my_needs}")
        step("requester_my_needs_checked", "ok")

        status, route_payload = request_json(
            api_base,
            "POST",
            f"/api/requirements/{need_id}/route-to-task",
            token=token,
            payload={
                "target_seat_id": target_id,
                "approved": True,
                "auto_dispatch": True,
                "note": "seat MCP e2e validation route approval",
            },
        )
        route_data = data_of(route_payload)
        if status != 200 or not isinstance(route_data, dict):
            raise RuntimeError(f"route-to-task failed: HTTP {status}: {route_payload}")
        task = route_data.get("task") if isinstance(route_data.get("task"), dict) else {}
        task_id = text(task.get("id") if isinstance(task, dict) else "")
        if not task_id:
            raise RuntimeError(f"route-to-task did not return task: {route_payload}")
        step("route_need_to_task", "ok", task_id=task_id, dispatch=route_data.get("dispatch"))

        target_client = McpClient(
            {
                "PLATFORM_API_BASE": api_base,
                "PLATFORM_PROJECT_ID": args.project_id,
                "PLATFORM_SEAT_ID": target_id,
                "PLATFORM_WORKSTATION_ID": target_id,
                "PLATFORM_AUTH_TOKEN": token,
            }
        )
        try:
            target_client.call("initialize")
            target_tasks = target_client.call_tool("check_my_tasks", {"limit": 20})
        finally:
            target_client.close()
        task_items = (target_tasks.get("my_tasks") or {}).get("items") if isinstance(target_tasks.get("my_tasks"), dict) else []
        if task_id not in {text(item.get("id")) for item in task_items if isinstance(item, dict)}:
            raise RuntimeError(f"routed Task is not visible in target queue: {target_tasks}")
        step("target_my_tasks_checked", "ok")

        legacy = client.call_tool("request_help", {"role": "platform reviewer", "ask": "兼容性验收：只创建 Need，不直接生成消息。"})
        if legacy.get("ok") is not True or not legacy.get("need_id") or legacy.get("message_id"):
            raise RuntimeError(f"request_help compatibility contract failed: {legacy}")
        step("legacy_request_help_checked", "ok", need_id=legacy.get("need_id"))

        report["ok"] = True
        return 0
    except Exception as exc:  # noqa: BLE001
        report["issues"].append(str(exc))
        step("exception", "failed", message=str(exc))
        return 1
    finally:
        if client is not None:
            client.close()
        report_path = output_dir / f"seat-mcp-e2e-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
