#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_API_BASE = "http://127.0.0.1:8010"
TERMINAL_STATUSES = {"completed", "failed", "done", "cancelled"}


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _text(value: object, fallback: str = "") -> str:
    next_value = str(value or "").strip()
    return next_value or fallback


def log(message: str) -> None:
    print(f"[relay] {datetime.now(timezone.utc).isoformat()} {message}", flush=True)


def _headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {raw}") from exc
    return json.loads(raw) if raw else {}


def _api_url(api_base: str, path: str, query: dict[str, str] | None = None) -> str:
    base = api_base.rstrip("/")
    url = f"{base}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"
    return url


def post_collaboration_message(
    *,
    api_base: str,
    headers: dict[str, str],
    project_id: str,
    workstation_id: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "message_type": "agent_command",
        "title": title,
        "body": body,
        "sender_type": "human",
        "recipient_type": "workstation",
        "recipient_id": workstation_id,
        "status": "queued",
    }
    response = _json_request("POST", _api_url(api_base, "/api/collaboration/messages"), headers=headers, payload=payload)
    data = response.get("data") if isinstance(response, dict) else None
    return data if isinstance(data, dict) else response


def post_project_note(
    *,
    api_base: str,
    headers: dict[str, str],
    project_id: str,
    title: str,
    body: str,
    status: str = "open",
) -> dict[str, Any] | None:
    payload = {
        "project_id": project_id,
        "message_type": "project_sync_note",
        "title": title,
        "body": body,
        "sender_type": "human",
        "recipient_type": "project",
        "recipient_id": project_id,
        "status": status,
    }
    try:
        response = _json_request("POST", _api_url(api_base, "/api/collaboration/messages"), headers=headers, payload=payload)
    except Exception as exc:
        print(f"[relay] failed to write project note: {exc}", file=sys.stderr)
        return None
    data = response.get("data") if isinstance(response, dict) else None
    return data if isinstance(data, dict) else response


def build_relay_status_body(
    *,
    relay_id: str,
    objective: str,
    first_workstation_id: str,
    first_provider: str,
    second_workstation_id: str,
    second_provider: str,
    first_title: str,
    second_title: str,
    note: str,
) -> str:
    return "\n".join(
        [
            f"relay_id: {relay_id}",
            f"目标: {objective}",
            f"第一棒: {first_provider} / {first_workstation_id} / {first_title}",
            f"第二棒: {second_provider} / {second_workstation_id} / {second_title}",
            f"当前说明: {note}",
            "人工审核点: 第二棒最终回复完成后，用户需要确认是否可作为正式交付；涉及硬件、费用、删除、发布等高风险动作必须另走审批。",
            "失败重试: 回到协作消息池的“多 NPC 接力”动作台，保留同一目标重新选择可用线程后再提交。",
        ]
    )


def post_relay_status(
    *,
    api_base: str,
    headers: dict[str, str],
    project_id: str,
    title: str,
    relay_id: str,
    status: str,
    objective: str,
    first_workstation_id: str,
    first_provider: str,
    second_workstation_id: str,
    second_provider: str,
    first_title: str,
    second_title: str,
    note: str,
) -> dict[str, Any] | None:
    payload = {
        "project_id": project_id,
        "agent_id": "platform-relay",
        "message_type": "relay_status",
        "title": f"{title} / 接力状态",
        "body": build_relay_status_body(
            relay_id=relay_id,
            objective=objective,
            first_workstation_id=first_workstation_id,
            first_provider=first_provider,
            second_workstation_id=second_workstation_id,
            second_provider=second_provider,
            first_title=first_title,
            second_title=second_title,
            note=note,
        ),
        "sender_type": "human",
        "sender_id": "platform-relay",
        "recipient_type": "project",
        "recipient_id": project_id,
        "status": status,
    }
    try:
        response = _json_request("POST", _api_url(api_base, "/api/collaboration/messages"), headers=headers, payload=payload)
    except Exception as exc:
        print(f"[relay] failed to write relay status: {exc}", file=sys.stderr)
        return None
    data = response.get("data") if isinstance(response, dict) else None
    return data if isinstance(data, dict) else response


def list_messages(*, api_base: str, headers: dict[str, str], project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    response = _json_request(
        "GET",
        _api_url(api_base, "/api/collaboration/messages", {"project_id": project_id, "limit": str(limit)}),
        headers=headers,
    )
    data = response.get("data") if isinstance(response, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def wait_for_result(
    *,
    api_base: str,
    headers: dict[str, str],
    project_id: str,
    title: str,
    workstation_id: str,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_seen: list[dict[str, Any]] = []
    while time.time() < deadline:
        last_seen = list_messages(api_base=api_base, headers=headers, project_id=project_id, limit=240)
        matches = [
            item
            for item in last_seen
            if _text(item.get("message_type")).lower() == "agent_result"
            and _text(item.get("title")) == title
            and _text(item.get("sender_id") or item.get("agent_id")) == workstation_id
            and _text(item.get("status")).lower() in TERMINAL_STATUSES
        ]
        if matches:
            return sorted(matches, key=lambda item: _text(item.get("updated_at") or item.get("created_at")), reverse=True)[0]
        time.sleep(poll_seconds)
    recent = [
        {
            "type": item.get("message_type"),
            "title": item.get("title"),
            "status": item.get("status"),
            "sender": item.get("sender_id"),
        }
        for item in last_seen[:12]
    ]
    raise TimeoutError(f"timed out waiting for result title={title!r}; recent={recent}")


def run_one_shot_adapter(
    *,
    api_base: str,
    project_id: str,
    workstation_id: str,
    provider_id: str,
    auth_token: str,
    output_dir: Path,
    executor_timeout_seconds: int,
) -> dict[str, Any]:
    script_path = Path(__file__).resolve().with_name("platform-workstation-adapter.py")
    args = [
        sys.executable or "python",
        str(script_path),
        "--api-base",
        api_base,
        "--project-id",
        project_id,
        "--workstation-id",
        workstation_id,
        "--provider",
        provider_id,
        "--auto-ack",
        "--execute-provider-cli",
        "--limit",
        "1",
        "--output-dir",
        str(output_dir),
        "--executor-timeout-seconds",
        str(executor_timeout_seconds),
    ]
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PLATFORM_AUTH_TOKEN": auth_token,
    }
    completed = subprocess.run(
        args,
        cwd=str(Path(__file__).resolve().parent.parent),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=executor_timeout_seconds + 90,
    )
    parsed: dict[str, Any] | None = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "parsed": parsed,
    }


def build_first_body(objective: str, *, final_marker: str) -> str:
    return "\n".join(
        [
            "请只执行这一条平台接力的第一棒，不要开启持续自动化。",
            "你的职责：先做资料收集、要点拆解、文章结构建议，给第二棒 AI 留下可接手材料。",
            f"用户目标：{objective}",
            f"最终回复必须包含标记：{final_marker}",
        ]
    )


def build_second_body(objective: str, first_result: str, *, final_marker: str) -> str:
    return "\n".join(
        [
            "请只执行这一条平台接力的第二棒，不要开启持续自动化。",
            "你的职责：接收第一棒 AI 的结果，整理成面向用户的最终交付，并指出仍需人工审核的点。",
            f"用户目标：{objective}",
            "第一棒最终回复摘要：",
            first_result[:1800],
            f"最终回复必须包含标记：{final_marker}",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a two-NPC relay through the AI collaboration platform.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--relay-id", default="")
    parser.add_argument("--first-workstation-id", required=True)
    parser.add_argument("--first-provider", default="codex")
    parser.add_argument("--second-workstation-id", required=True)
    parser.add_argument("--second-provider", default="claude")
    parser.add_argument("--title", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--wait-timeout-seconds", type=int, default=720)
    parser.add_argument("--executor-timeout-seconds", type=int, default=420)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--output-dir", default="artifacts/workstation-inbox/relay")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log("orchestrator starting")
    auth_token = _text(os.environ.get("PLATFORM_AUTH_TOKEN"), "")
    if not auth_token:
        raise RuntimeError("PLATFORM_AUTH_TOKEN is required for platform relay orchestration")

    api_base = _text(args.api_base, DEFAULT_API_BASE).rstrip("/")
    project_id = _text(args.project_id)
    first_workstation_id = _text(args.first_workstation_id)
    second_workstation_id = _text(args.second_workstation_id)
    first_provider = _text(args.first_provider, "codex").lower()
    second_provider = _text(args.second_provider, "claude").lower()
    title = _text(args.title)
    objective = _text(args.objective)
    started_at = datetime.now(timezone.utc).isoformat()
    relay_id = _text(args.relay_id) or datetime.now().strftime("%Y%m%d-%H%M%S")
    first_title = f"{title} / 第一棒资料拆解"
    second_title = f"{title} / 第二棒最终交付"
    first_marker = f"平台接力第一棒完成 {relay_id}"
    second_marker = f"平台接力第二棒完成 {relay_id}"
    headers = _headers(auth_token)
    output_dir = Path(args.output_dir)
    report: dict[str, Any] = {
        "relay_id": relay_id,
        "project_id": project_id,
        "title": title,
        "started_at": started_at,
        "first": {"workstation_id": first_workstation_id, "provider": first_provider, "title": first_title},
        "second": {"workstation_id": second_workstation_id, "provider": second_provider, "title": second_title},
    }

    log("writing relay start note")
    post_relay_status(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=title,
        relay_id=relay_id,
        status="running",
        objective=objective,
        first_workstation_id=first_workstation_id,
        first_provider=first_provider,
        second_workstation_id=second_workstation_id,
        second_provider=second_provider,
        first_title=first_title,
        second_title=second_title,
        note="编排器已接手，正在准备第一棒派工。",
    )
    post_project_note(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=f"{title} / 平台接力启动",
        body=f"平台已启动两段式 NPC 接力：{first_workstation_id} -> {second_workstation_id}。目标：{objective}",
    )

    log(f"posting first command: {first_title} -> {first_workstation_id}")
    first_command = post_collaboration_message(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        workstation_id=first_workstation_id,
        title=first_title,
        body=build_first_body(objective, final_marker=first_marker),
    )
    report["first"]["command"] = first_command
    log("running first one-shot adapter")
    first_adapter = run_one_shot_adapter(
        api_base=api_base,
        project_id=project_id,
        workstation_id=first_workstation_id,
        provider_id=first_provider,
        auth_token=auth_token,
        output_dir=output_dir,
        executor_timeout_seconds=args.executor_timeout_seconds,
    )
    report["first"]["adapter"] = first_adapter
    if int(first_adapter.get("returncode") or 0) != 0:
        post_relay_status(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=title,
            relay_id=relay_id,
            status="failed",
            objective=objective,
            first_workstation_id=first_workstation_id,
            first_provider=first_provider,
            second_workstation_id=second_workstation_id,
            second_provider=second_provider,
            first_title=first_title,
            second_title=second_title,
            note=f"第一棒适配器执行失败：{_text(first_adapter.get('stderr') or first_adapter.get('stdout'))[:500]}",
        )
        post_project_note(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=f"{title} / 平台接力中止",
            body=f"第一棒适配器执行失败，未继续第二棒。\n{_text(first_adapter.get('stderr') or first_adapter.get('stdout'))[:1500]}",
            status="failed",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    log(f"waiting first result: {first_title}")
    first_result = wait_for_result(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=first_title,
        workstation_id=first_workstation_id,
        timeout_seconds=args.wait_timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    report["first"]["result"] = first_result
    log(f"first result status: {_text(first_result.get('status'))}")
    if _text(first_result.get("status")).lower() == "failed":
        post_relay_status(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=title,
            relay_id=relay_id,
            status="failed",
            objective=objective,
            first_workstation_id=first_workstation_id,
            first_provider=first_provider,
            second_workstation_id=second_workstation_id,
            second_provider=second_provider,
            first_title=first_title,
            second_title=second_title,
            note=f"第一棒最终状态为 failed：{_text(first_result.get('body'))[:500]}",
        )
        post_project_note(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=f"{title} / 平台接力中止",
            body=f"第一棒失败，未继续第二棒。回执：{_text(first_result.get('body'))[:1000]}",
            status="failed",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    post_relay_status(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=title,
        relay_id=relay_id,
        status="running",
        objective=objective,
        first_workstation_id=first_workstation_id,
        first_provider=first_provider,
        second_workstation_id=second_workstation_id,
        second_provider=second_provider,
        first_title=first_title,
        second_title=second_title,
        note="第一棒已完成，正在把结果交给第二棒。",
    )
    log(f"posting second command: {second_title} -> {second_workstation_id}")
    second_command = post_collaboration_message(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        workstation_id=second_workstation_id,
        title=second_title,
        body=build_second_body(objective, _text(first_result.get("body")), final_marker=second_marker),
    )
    report["second"]["command"] = second_command
    log("running second one-shot adapter")
    second_adapter = run_one_shot_adapter(
        api_base=api_base,
        project_id=project_id,
        workstation_id=second_workstation_id,
        provider_id=second_provider,
        auth_token=auth_token,
        output_dir=output_dir,
        executor_timeout_seconds=args.executor_timeout_seconds,
    )
    report["second"]["adapter"] = second_adapter
    if int(second_adapter.get("returncode") or 0) != 0:
        post_relay_status(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=title,
            relay_id=relay_id,
            status="failed",
            objective=objective,
            first_workstation_id=first_workstation_id,
            first_provider=first_provider,
            second_workstation_id=second_workstation_id,
            second_provider=second_provider,
            first_title=first_title,
            second_title=second_title,
            note=f"第二棒适配器执行失败：{_text(second_adapter.get('stderr') or second_adapter.get('stdout'))[:500]}",
        )
        post_project_note(
            api_base=api_base,
            headers=headers,
            project_id=project_id,
            title=f"{title} / 平台接力中止",
            body=f"第二棒适配器执行失败。\n{_text(second_adapter.get('stderr') or second_adapter.get('stdout'))[:1500]}",
            status="failed",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3
    post_relay_status(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=title,
        relay_id=relay_id,
        status="running",
        objective=objective,
        first_workstation_id=first_workstation_id,
        first_provider=first_provider,
        second_workstation_id=second_workstation_id,
        second_provider=second_provider,
        first_title=first_title,
        second_title=second_title,
        note="第二棒已接单，正在等待最终回复。",
    )
    log(f"waiting second result: {second_title}")
    second_result = wait_for_result(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=second_title,
        workstation_id=second_workstation_id,
        timeout_seconds=args.wait_timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    report["second"]["result"] = second_result

    final_status = _text(second_result.get("status")).lower()
    log(f"second result status: {final_status}")
    post_relay_status(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=title,
        relay_id=relay_id,
        status="completed" if final_status == "completed" else "failed",
        objective=objective,
        first_workstation_id=first_workstation_id,
        first_provider=first_provider,
        second_workstation_id=second_workstation_id,
        second_provider=second_provider,
        first_title=first_title,
        second_title=second_title,
        note=f"第二棒已返回最终状态：{final_status or 'unknown'}。",
    )
    post_project_note(
        api_base=api_base,
        headers=headers,
        project_id=project_id,
        title=f"{title} / 平台接力完成",
        body=(
            f"平台两段式 NPC 接力已收口，状态：{final_status or 'unknown'}。\n"
            f"第一棒：{first_title}\n第二棒：{second_title}\n最终摘要：{_text(second_result.get('body'))[:1000]}"
        ),
        status="completed" if final_status == "completed" else "failed",
    )
    log("orchestrator completed")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if final_status == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
