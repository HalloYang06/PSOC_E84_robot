#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request, error
from urllib.parse import quote


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


DEFAULT_API_BASE = "http://127.0.0.1:8010"
MAX_PLATFORM_NOTE_CHARS = 3800
PEER_DISPATCH_FENCE_RE = re.compile(
    r"```platform-peer-dispatches\s*(?P<payload>.*?)```",
    re.IGNORECASE | re.DOTALL,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_PROVIDER_EXECUTORS = {
    "claude": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@",
    "qwen": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@",
    "codex": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@ --model @MODEL@",
}

CODEX_APP_SERVER_EXECUTOR = "__codex_app_server_turn__"
CODEX_DESKTOP_UI_EXECUTOR = "__codex_desktop_ui_turn__"
CODEX_DESKTOP_UI_LOCK_PATH = Path(tempfile.gettempdir()) / "ai-collab-codex-desktop-ui-delivery.lock"
CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS = 8


def _adapter_config_url(base: str, project_id: str, workstation_id: str) -> str:
    encoded_project_id = quote(project_id, safe="")
    encoded_workstation_id = quote(workstation_id, safe="")
    return (
        f"{base.rstrip('/')}/api/collaboration/projects/{encoded_project_id}"
        f"/thread-workstations/{encoded_workstation_id}/adapter-config"
    )


def _workstation_messages_url(base: str, project_id: str, workstation_id: str) -> str:
    encoded_project_id = quote(project_id, safe="")
    encoded_workstation_id = quote(workstation_id, safe="")
    return (
        f"{base.rstrip('/')}/api/collaboration/projects/{encoded_project_id}"
        f"/thread-workstations/{encoded_workstation_id}"
    )


def _workstation_inbox_url(
    base: str,
    project_id: str,
    workstation_id: str,
    *,
    limit: int,
    status: str | None = None,
    message_id: str | None = None,
) -> str:
    url = f"{_workstation_messages_url(base, project_id, workstation_id)}/inbox?limit={limit}"
    normalized_status = str(status or "").strip()
    if normalized_status:
        url += f"&status={quote(normalized_status, safe='')}"
    elif str(message_id or "").strip():
        # One-shot recovery often targets an acked/in_progress Desktop dispatch.
        # Query all states so the local message-id filter can still find it.
        url += "&status=all"
    return url


def _message_action_url(base: str, project_id: str, workstation_id: str, message_id: str, action: str) -> str:
    encoded_message_id = quote(message_id, safe="")
    return f"{_workstation_messages_url(base, project_id, workstation_id)}/messages/{encoded_message_id}/{action}"


def _command_metadata(command: dict[str, Any]) -> dict[str, Any]:
    metadata = command.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    extra_data = command.get("extra_data")
    if isinstance(extra_data, dict):
        return dict(extra_data)
    return {}


def _desktop_retry_dedupe_key(command: dict[str, Any]) -> str:
    message_id = str(command.get("id") or "").strip()
    metadata = _command_metadata(command)
    retry_requested = bool(metadata.get("desktop_sync_retry_requested"))
    retry_count = str(metadata.get("desktop_sync_retry_count") or "").strip()
    if retry_requested and retry_count:
        return f"{message_id}:desktop-retry:{retry_count}"
    return message_id


def _root_message_id_for_child_dispatch(command: dict[str, Any]) -> str | None:
    metadata = _command_metadata(command)
    for value in (
        metadata.get("root_message_id"),
        (metadata.get("delegation_context") or {}).get("root_message_id")
        if isinstance(metadata.get("delegation_context"), dict)
        else None,
        metadata.get("source_message_id"),
        (metadata.get("delegation_context") or {}).get("source_message_id")
        if isinstance(metadata.get("delegation_context"), dict)
        else None,
        command.get("id"),
    ):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return None


def _post_workstation_progress(
    *,
    base: str,
    project_id: str,
    workstation_id: str,
    message_id: str,
    headers: dict[str, str],
    note: str,
    state: str = "in_progress",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    progress_url = _message_action_url(base, project_id, workstation_id, message_id, "progress")
    return _json_request(
        "POST",
        progress_url,
        headers=headers,
        payload={
            "note": note,
            "state": state,
            "metadata": metadata or {},
        },
    ).get("data") or {}


def _complete_workstation_command(
    *,
    base: str,
    project_id: str,
    workstation_id: str,
    message_id: str,
    headers: dict[str, str],
    note: str,
    result_status: str = "completed",
) -> dict[str, Any]:
    complete_url = _message_action_url(base, project_id, workstation_id, message_id, "complete")
    try:
        return _json_request(
            "POST",
            complete_url,
            headers=headers,
            payload={
                "result_status": result_status,
                "note": note,
            },
        ).get("data") or {}
    except RuntimeError as exc:
        raw = str(exc)
        if "HTTP 409" in raw and "MESSAGE_NOT_PENDING" in raw:
            return {
                "already_closed": True,
                "message_id": message_id,
                "result_status": result_status,
                "note": "平台指令已收口，本次重复同步已跳过。",
            }
        raise


def _ack_workstation_command(
    *,
    base: str,
    project_id: str,
    workstation_id: str,
    message_id: str,
    headers: dict[str, str],
    note: str,
) -> dict[str, Any]:
    ack_url = _message_action_url(base, project_id, workstation_id, message_id, "ack")
    try:
        return _json_request(
            "POST",
            ack_url,
            headers=headers,
            payload={"note": note},
        ).get("data") or {}
    except RuntimeError as exc:
        raw = str(exc)
        if "HTTP 409" in raw and (
            "MESSAGE_ALREADY_CLAIMED" in raw
            or "MESSAGE_NOT_PENDING" in raw
            or "already" in raw.lower()
            or "closed" in raw.lower()
            or "claimed" in raw.lower()
            or "收尾" in raw
        ):
            return {
                "already_claimed": True,
                "message_id": message_id,
                "note": "平台指令已被领取或收口，本次重复接单已跳过。",
            }
        raise


def _sync_desktop_event(
    *,
    base: str,
    project_id: str,
    workstation_id: str,
    headers: dict[str, str],
    role: str,
    note: str,
    session_id: str | None,
    source_event_id: str | None,
    source_timestamp: str | None,
    phase: str | None = None,
    linked_message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sync_url = f"{_workstation_messages_url(base, project_id, workstation_id)}/desktop-sync"
    return _json_request(
        "POST",
        sync_url,
        headers=headers,
        payload={
            "role": role,
            "note": note,
            "phase": phase,
            "session_id": session_id,
            "source_event_id": source_event_id,
            "source_timestamp": source_timestamp,
            "linked_message_id": linked_message_id,
            "metadata": metadata or {},
        },
    ).get("data") or {}


def _create_peer_dispatch(
    *,
    base: str,
    project_id: str,
    sender_seat_id: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    source_message_id: str | None = None,
    root_message_id: str | None = None,
) -> dict[str, Any] | None:
    target = str(payload.get("seat_id") or payload.get("recipient_id") or "").strip()
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or payload.get("ask") or "").strip()
    if not target or not title or not body:
        return None
    metadata = {
        "origin": "platform_peer_dispatches",
        "source": "npc_final_reply",
        "source_agent_id": sender_seat_id,
        "payload_json": payload.get("payload_json") if isinstance(payload.get("payload_json"), dict) else {
            "card_kind": str(payload.get("card_kind") or "task"),
            "title": title[:200],
            "summary": str(payload.get("summary") or "NPC 自主协作派单"),
            "status": "queued",
            "risk_level": str(payload.get("risk_level") or "L1"),
            "items": [
                {"label": "来源 NPC", "value": sender_seat_id},
                {"label": "目标 NPC", "value": target},
            ],
            "actions": [{"label": "回执", "value": "返回协作结果"}],
        },
    }
    cleaned_source = str(payload.get("source_message_id") or source_message_id or "").strip()
    cleaned_root = str(payload.get("root_message_id") or root_message_id or cleaned_source).strip()
    if cleaned_source:
        metadata["source_message_id"] = cleaned_source
    if cleaned_root:
        metadata["root_message_id"] = cleaned_root
    message_payload = {
        "project_id": project_id,
        "sender_type": "agent",
        "sender_id": sender_seat_id,
        "recipient_type": "thread_workstation",
        "recipient_id": target,
        "message_type": "agent_command",
        "title": title[:200],
        "body": body
        + "\n\n（由上游 NPC 在当前目标链中发起协作；平台会按项目规则记录、审核和回收回执。）",
        "status": "queued",
        "metadata": metadata,
    }
    return _json_request(
        "POST",
        f"{base.rstrip('/')}/api/collaboration/messages",
        headers=headers,
        payload=message_payload,
    ).get("data") or {}


def _launch_peer_dispatch_adapter(
    *,
    base: str,
    project_id: str,
    target_workstation_id: str,
    message_id: str,
    auth_token: str | None,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    target = str(target_workstation_id or "").strip()
    command_id = str(message_id or "").strip()
    if not target or not command_id:
        return {"launched": False, "error": "missing target workstation or message id"}

    safe_target = re.sub(r"[^a-zA-Z0-9._-]+", "-", target)[:96] or "workstation"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_base_dir = _normalize_workstation_output_base(output_dir, project_id=project_id)
    root_output_dir = output_base_dir / project_id
    target_output_dir = root_output_dir / target
    log_dir = root_output_dir / "peer-launch-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{safe_target}-{command_id}-{stamp}.out.log"
    stderr_path = log_dir / f"{safe_target}-{command_id}-{stamp}.err.log"

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--api-base",
        base,
        "--project-id",
        project_id,
        "--workstation-id",
        target,
        "--message-id",
        command_id,
        "--auto-ack",
        "--execute-provider-cli",
        "--ignore-automation-switch",
        "--output-dir",
        str(output_base_dir),
        "--executor-timeout-seconds",
        str(max(1, int(timeout_seconds or 1800))),
    ]
    if auth_token:
        cmd.extend(["--auth-token", auth_token])

    env = dict(os.environ)
    if auth_token:
        env["PLATFORM_AUTH_TOKEN"] = auth_token
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        stdout_fh = stdout_path.open("a", encoding="utf-8", errors="replace")
        stderr_fh = stderr_path.open("a", encoding="utf-8", errors="replace")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(Path.cwd()),
                stdin=subprocess.DEVNULL,
                stdout=stdout_fh,
                stderr=stderr_fh,
                env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        finally:
            stdout_fh.close()
            stderr_fh.close()
        return {
            "launched": True,
            "pid": proc.pid,
            "target_workstation_id": target,
            "message_id": command_id,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    except Exception as exc:
        return {
            "launched": False,
            "target_workstation_id": target,
            "message_id": command_id,
            "error": str(exc),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }


def _extract_peer_dispatches(note: str) -> list[dict[str, Any]]:
    dispatches: list[dict[str, Any]] = []
    for match in PEER_DISPATCH_FENCE_RE.finditer(str(note or "")):
        raw = match.group("payload").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict):
                dispatches.append(item)
    return dispatches


def _fit_platform_note(note: str, *, message_id: str, result_status: str, output_path: Path | None = None) -> str:
    normalized = str(note or "").strip()
    if len(normalized) <= MAX_PLATFORM_NOTE_CHARS:
        return normalized
    suffix_parts = [
        "",
        "",
        "[平台提示] NPC 回执超过平台单条 note 限制，已截断以保证任务可以收口。",
        f"message_id: {message_id}",
        f"result_status: {result_status}",
    ]
    if output_path is not None:
        suffix_parts.append("完整输出已保存为平台证据，可在工作台点“证据/查看回执”预览。")
    suffix = "\n".join(suffix_parts)
    budget = max(400, MAX_PLATFORM_NOTE_CHARS - len(suffix))
    return f"{normalized[:budget].rstrip()}{suffix}"


def _prepare_final_note(note: str, *, message_id: str, result_status: str, output_path: Path | None = None) -> str:
    if output_path is not None:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(str(note or ""), encoding="utf-8")
        except Exception:
            pass
    return _fit_platform_note(note, message_id=message_id, result_status=result_status, output_path=output_path)


def _json_request(method: str, url: str, *, headers: dict[str, str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    req_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=req_headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {raw}") from exc
    return json.loads(raw) if raw else {}


def _encode_header_value(value: str) -> tuple[str, bool]:
    """urllib encodes header values as latin-1 — non-ASCII workstation ids
    crash at send time. Percent-encode + flag header so the receiver decodes back."""
    if not value:
        return "", False
    try:
        value.encode("ascii")
        return value, False
    except UnicodeEncodeError:
        return quote(value, safe=""), True


def _headers(workstation_id: str, token: str | None = None, runner_id: str | None = None) -> dict[str, str]:
    encoded, was_encoded = _encode_header_value(workstation_id)
    headers = {"X-Workstation-Id": encoded}
    if was_encoded:
        headers["X-Workstation-Id-Encoding"] = "percent"
    if token:
        headers["X-Workstation-Token"] = token
    if runner_id:
        headers["X-Runner-Id"] = runner_id
    return headers


def _adapter_headers(
    workstation_id: str,
    *,
    workstation_token: str | None = None,
    auth_token: str | None = None,
    runner_id: str | None = None,
) -> dict[str, str]:
    # Real remote adapters identify as a workstation. A platform-launched one-shot can instead
    # use the current human session, so it does not rotate or invalidate a remote adapter token.
    if auth_token and not workstation_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return _headers(workstation_id, workstation_token, runner_id)


def _command_markdown(
    command: dict[str, Any],
    *,
    project_id: str,
    workstation_id: str,
    provider: str,
    computer_node_id: str = "",
    workstation_knowledge_path: str = "",
) -> str:
    title = str(command.get("title") or "Untitled platform command").strip()
    body = str(command.get("body") or "").strip()
    recipient_id = str(command.get("recipient_id") or "").strip()
    seat_id = recipient_id if recipient_id and recipient_id != workstation_id else ""
    seat_doc_path = f"docs/npcs/{seat_id or workstation_id}"
    default_workstation_doc_path = f"docs/workstations/{computer_node_id}.md" if computer_node_id else ""
    project_knowledge_path = f"docs/projects/{project_id}/README.md"
    knowledge_lines: list[str] = []
    if Path(seat_doc_path).exists():
        knowledge_lines.append(f"- Role manual: `{seat_doc_path}`.")
    if workstation_knowledge_path and Path(workstation_knowledge_path).exists():
        knowledge_lines.append(f"- Workstation context: `{workstation_knowledge_path}`.")
    elif default_workstation_doc_path and Path(default_workstation_doc_path).exists():
        knowledge_lines.append(f"- Workstation context: `{default_workstation_doc_path}`.")
    if Path(project_knowledge_path).exists():
        knowledge_lines.append(f"- Project context: `{project_knowledge_path}`.")
    lines = [
        f"# {title}",
        "",
        "## Platform Envelope",
        f"- project_id: `{project_id}`",
        f"- workstation_id: `{workstation_id}`",
        f"- computer_node_id: `{computer_node_id or ''}`",
        f"- recipient_id: `{recipient_id or workstation_id}`",
        f"- seat_id (your NPC identity for docs): `{seat_id or workstation_id}`",
        f"- provider: `{provider}`",
        f"- message_id: `{command.get('id')}`",
        f"- message_type: `{command.get('message_type')}`",
        f"- status: `{command.get('status')}`",
        f"- requirement_id: `{command.get('requirement_id') or ''}`",
        "",
        "## Required Response Contract",
        "- First send a minimal acknowledgement through the platform adapter.",
        "- Then send a final reply through the platform adapter when the work is complete.",
        "- If this computer uses a different local path, resolve the repository locally instead of trusting another computer's path.",
        "- Before doing work, read docs/ai-requirements/ai-required-requirements-ledger.md if present; obey proposer, target, review gate, one-shot/heartbeat mode, and reply-to fields.",
        "- If the task requires human review, stop after analysis/minimal acknowledgement and wait for approval.",
        "",
        "## NPC Knowledge Library",
        *(knowledge_lines if knowledge_lines else ["- No project/NPC/workstation knowledge file is currently registered on disk for this seat. Do not report missing default docs; proceed from the platform command and cite only files you actually read."]),
        "- Read the listed knowledge files before acting. Cite only files that exist and that you actually relied on.",
        "",
        "## Autonomous Collaboration (seat-mcp tools)",
        "- 你的 CLI 应该已经加载了 `seat-mcp` 这个 MCP server（见 `scripts/seat-mcp-server/README.md`）。",
        "- 当你工作中缺少输入、能力或协作产物时，**不要叫用户去派单**，先按员工表/基础 skill 判断自己缺什么，再调用结构化 Need 工具：",
        "  - `list_peers()`：查看项目员工表里的伙伴、职责、工位和协作边界。",
        "  - `create_need(title, why_needed, required_capability, expected_output, input_context, risk_level, priority, acceptance_criteria, suggested_assignee?)`：写入我的需求。平台 NeedRouter 会根据员工表、skill、知识库、状态和审核策略，把 Need 转成目标 NPC 的 Task。",
        "  - `check_my_needs(limit?)`：查看我提出、等待别人满足的需求。",
        "  - `check_my_tasks(limit?)`：查看分配给我承接的任务。",
        "  - `request_help(role, ask, expected?)`：旧兼容工具，只会转成结构化 Need；不要把它当关键词自动派单。",
        "  - `dispatch_to_peer(seat_id, title, body)`：旧兼容工具，仅在用户已经明确批准或低风险同工位场景使用。",
        "  - `read_my_inbox(limit?)`：兼容旧消息队列查询。新语义优先用 `check_my_needs` / `check_my_tasks`。",
        "  - `mark_done(message_id, body, failed?)`：**仅长开窗口模式（PersistentWindow）使用**——处理完一条 incoming_dispatch 后调一次，写 done 回执。一次性弹窗模式不用调（watcher 自动写）。",
        "- 结构化 Need 的归属：Need 属于提需求的 NPC；Task 属于承接的 NPC。不要把消息当队列。",
        "- NeedRouter 会经过平台 review gate：高风险、跨工位、硬件/部署/固件/ROS 写/模型发布/Git 回退等必须等待用户审核。",
        "- 工具返回 `needs_review=true` 时，你**只需告诉用户「已发起求助，等审核」**，不要重复发也不要切换到自己干。",
        "- 如果当前 CLI 没有成功加载 seat-mcp，但你确实需要其他 NPC 协作，请在最终回复末尾追加一个 JSON 代码块：",
        "  ```platform-peer-dispatches",
        "  [{\"seat_id\":\"platform-npc-1\",\"title\":\"请协作...\",\"body\":\"具体请求...\",\"card_kind\":\"task\",\"risk_level\":\"L1\"}]",
        "  ```",
        "  平台 adapter 会把它转换为真实的 NPC-to-NPC 派单。只有你确实需要同伴时才输出这段。",
        "- 如果用户明确要求你“自己组织 / 主动派单 / 自主合作 / 不要让用户手动派单”，而当前 CLI 又没有 seat-mcp 工具，"
        "你必须使用 `platform-peer-dispatches` 代码块发起同伴派单；不能只写“建议派给谁”。",
        "",
        "## Reply Formatting",
        "- Reply in GitHub-flavored Markdown.",
        "- Cite touched files / commits / PRs as GitHub links: `https://github.com/<owner>/<repo>/blob/<branch>/<path>` or `/commit/<sha>`. Use the local repo's actual remote — do not invent placeholder URLs.",
        "- If the requirement asks for code changes, list each change in a bullet with the link.",
        "- Keep platform-routing chatter out of the reply body (the adapter handles ack/complete envelopes).",
        "",
        "## User Instruction",
        body or "No body was provided.",
        "",
    ]
    return "\n".join(lines)


def write_command_file(
    command: dict[str, Any],
    *,
    output_dir: Path,
    project_id: str,
    workstation_id: str,
    provider: str,
    computer_node_id: str = "",
    workstation_knowledge_path: str = "",
) -> Path:
    message_id = str(command.get("id") or "message").strip()
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in message_id) or "message"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_id}.md"
    path.write_text(
        _command_markdown(
            command,
            project_id=project_id,
            workstation_id=workstation_id,
            provider=provider,
            computer_node_id=computer_node_id,
            workstation_knowledge_path=workstation_knowledge_path,
        ),
        encoding="utf-8",
    )
    return path


def _default_ack_note(
    *,
    provider: str,
    message_id: str,
    command_path: Path,
    execute_provider_cli: bool,
    executor_cwd: str | None,
) -> str:
    mode = "桌面线程处理中" if execute_provider_cli else "已写入待办，等待桌面线程处理"
    cwd_note = "本项目工作区" if str(executor_cwd or "").strip() else "待绑定工作区"
    return "\n".join(
        [
            f"目标 NPC 已接到平台派单：{message_id}。",
            f"处理方式：{mode}。",
            f"工作区：{cwd_note}。",
            "平台会继续同步最小回执、待收口状态和最终结果。",
        ]
    )


def _shell_arg(value: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


def _safe_path_component(value: str, fallback: str = "item") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(value or "").strip())
    cleaned = cleaned.strip(".-_")
    return cleaned[:96] or fallback


def _executor_template(provider: str, explicit_command: str | None, use_provider_default: bool) -> str:
    explicit = str(explicit_command or "").strip()
    if explicit:
        return explicit
    if not use_provider_default:
        return ""
    return DEFAULT_PROVIDER_EXECUTORS.get(provider.strip().lower(), "")

def _strip_session_prefix(value: str | None, provider: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered_provider = str(provider or "").strip().lower()
    prefixes = []
    if lowered_provider:
        prefixes.append(f"{lowered_provider}-session-")
    prefixes.extend(["codex-session-", "claude-session-"])
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _default_executor_template(
    provider: str,
    explicit_command: str | None,
    use_provider_default: bool,
    *,
    automation_thread_id: str | None = None,
    desktop_delivery_mode: str | None = None,
) -> tuple[str, str]:
    explicit = str(explicit_command or "").strip()
    if explicit:
        return explicit, "custom"
    if not use_provider_default:
        return "", "disabled"
    provider_key = str(provider or "").strip().lower()
    session_id = _strip_session_prefix(automation_thread_id, provider_key)
    if provider_key == "codex" and session_id:
        if str(desktop_delivery_mode or "").strip().lower() == "codex_app_server":
            return CODEX_APP_SERVER_EXECUTOR, "codex_app_server"
        if str(desktop_delivery_mode or "").strip().lower() == "codex_desktop_ui":
            return CODEX_DESKTOP_UI_EXECUTOR, "codex_desktop_ui"
        # A bound Codex thread should be visible in Codex Desktop by default.
        # If the UI bridge is not really available, the delivery attempt fails
        # loudly instead of silently turning user/Boss/NPC dispatches into a
        # background app-server run that the human cannot watch.
        return CODEX_DESKTOP_UI_EXECUTOR, "codex_desktop_ui_required"
    return DEFAULT_PROVIDER_EXECUTORS.get(provider_key, ""), "provider_exec"


def _extract_executor_prompt(command_text: str) -> str:
    """Keep platform routing out of the provider prompt; the adapter handles ack/final receipts."""
    title = ""
    message_id = ""
    seat_id = ""
    workstation_id = ""
    computer_node_id = ""
    seat_doc_path = ""
    workstation_knowledge_path = ""
    project_knowledge_path = ""
    in_knowledge_block = False
    for line in command_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped.lstrip("#").strip()
        elif stripped.startswith("- message_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            tokens = after.strip().strip("`").split()
            message_id = tokens[0].strip("`") if tokens else ""
        elif stripped.startswith("- seat_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            tokens = after.strip().strip("`").split()
            seat_id = tokens[0].strip("`") if tokens else ""
        elif stripped.startswith("- workstation_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            tokens = after.strip().strip("`").split()
            workstation_id = tokens[0].strip("`") if tokens else ""
        elif stripped.startswith("- computer_node_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            tokens = after.strip().strip("`").split()
            computer_node_id = tokens[0].strip("`") if tokens else ""
        if stripped.startswith("## NPC Knowledge Library"):
            in_knowledge_block = True
            continue
        if in_knowledge_block and stripped.startswith("## "):
            in_knowledge_block = False
        if in_knowledge_block and stripped.startswith("- Role manual:"):
            chunk = stripped.split(":", 1)[1] if ":" in stripped else ""
            chunk = chunk.strip().strip(".").strip()
            if chunk.startswith("`") and chunk.endswith("`"):
                seat_doc_path = chunk.strip("`")
        if in_knowledge_block and stripped.startswith("- Workstation context:"):
            chunk = stripped.split(":", 1)[1] if ":" in stripped else ""
            chunk = chunk.strip().strip(".").strip()
            if chunk.startswith("`") and chunk.endswith("`"):
                workstation_knowledge_path = chunk.strip("`")
        if in_knowledge_block and stripped.startswith("- Project context:"):
            chunk = stripped.split(":", 1)[1] if ":" in stripped else ""
            chunk = chunk.strip().strip(".").strip()
            if chunk.startswith("`") and chunk.endswith("`"):
                project_knowledge_path = chunk.strip("`")
    instruction = command_text
    marker = "## User Instruction"
    if marker in command_text:
        instruction = command_text.split(marker, 1)[1].strip()
    seat_label = seat_id or workstation_id or "<seat>"
    knowledge_targets = [
        label
        for label in [seat_doc_path, workstation_knowledge_path, project_knowledge_path]
        if label and Path(label).exists()
    ]
    if knowledge_targets:
        knowledge_instruction = (
            "开工前先读这些已存在的知识文件，并在最终回复里注明你引用了哪份文档："
            + "、".join(knowledge_targets)
            + "。"
        )
    else:
        knowledge_instruction = "当前没有为此 NPC 注册到磁盘的知识文件；不要报告默认路径缺失，直接按平台命令和实际代码/文档行动。"
    parts = [
        "你是当前电脑线程上的执行 AI。",
        (
            "平台跟踪标记：message_id: `" + message_id + "`。"
            "请保留这个标记在本轮上下文中；平台用它把桌面线程的最终回复同步回 NPC 对话框。"
        ) if message_id else "",
        "平台适配器已经负责最小回执和最终回写；不要再调用平台 API，也不要尝试自己发送回执。",
        "开工前如果存在 docs/ai-requirements/ai-required-requirements-ledger.md，必须遵守其中的提需求者、被提需求者、人工审核边界、一次性/心跳模式和完成后回给谁。",
        "凡是标记为需要人工审核的内容，只能分析和说明，不能继续自动执行。",
        knowledge_instruction,
        (
            "回复必须用 GitHub-flavored Markdown。引用代码/提交/PR 时一律给出 GitHub 链接（owner/repo/blob/branch/path 或 /commit/<sha>），"
            "用当前仓库真实的 remote，不要编造占位 URL。如果改了文件，按「- 修改 <文件名>：<一句话原因> — <github 链接>」列清单。"
        ),
        (
            "需要其他 NPC 帮忙时，优先调 MCP 工具 `create_need(...)`（来自 seat-mcp server）。"
            "先用 `list_peers()` 看员工表，再把缺口写成结构化 Need；不要用关键词猜派单，也不要让用户去 UI 上替你派单。"
        ),
        (
            "如果当前执行环境没有暴露 seat-mcp 工具，但用户要求你自己组织、主动派单、自主合作、协调 1-6 号 NPC，"
            "你不能把“工具不可用”当作最终答案。请先给出一句简短说明，然后在最终回复末尾追加一个 "
            "`platform-peer-dispatches` fenced JSON 代码块。平台 adapter 会把这个代码块转换成真实的 NPC-to-NPC 派单。"
        ),
        (
            "兜底派单格式示例：\n"
            "```platform-peer-dispatches\n"
            "[{\"seat_id\":\"platform-npc-1\",\"title\":\"请协作前端规划\",\"body\":\"请从前端用户体验角度审查机器人开发平台结构。\",\"card_kind\":\"task\",\"risk_level\":\"L1\"}]\n"
            "```"
        ),
        (
            "只有确实需要同伴协作时才输出 `platform-peer-dispatches`；一旦用户明确要求自主组织协作，"
            "至少派给一个明确 seat_id，不能只写建议名单。"
        ),
        "请只根据下面的用户指令输出最终回复内容。",
    ]
    if title:
        parts.append(f"\n# {title}")
    parts.append(instruction.strip())
    return "\n\n".join(part for part in parts if part)


def _fetch_adapter_config(base: str, *, project_id: str, workstation_id: str, headers: dict[str, str]) -> dict[str, Any]:
    payload = _json_request("GET", _adapter_config_url(base, project_id, workstation_id), headers=headers)
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def _render_executor_command(
    template: str,
    *,
    prompt_file: Path,
    prompt_text: str,
    project_id: str,
    workstation_id: str,
    provider: str,
    message_id: str,
    model: str | None,
    session_id: str | None,
) -> str:
    provider_executor = Path(__file__).resolve().with_name("platform-provider-executor.py")
    replacements = {
        "@PROMPT_FILE@": _shell_arg(str(prompt_file)),
        "@PROMPT_TEXT@": _shell_arg(prompt_text),
        "@PROJECT_ID@": _shell_arg(project_id),
        "@WORKSTATION_ID@": _shell_arg(workstation_id),
        "@PROVIDER@": _shell_arg(provider),
        "@MESSAGE_ID@": _shell_arg(message_id),
        "@MODEL@": _shell_arg(str(model or "").strip()),
        "@SESSION_ID@": _shell_arg(str(session_id or "").strip()),
        "@PROVIDER_EXECUTOR@": _shell_arg(str(provider_executor)),
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    return rendered


def _normalize_workstation_output_base(output_dir: Path, *, project_id: str) -> Path:
    """Return the base directory before <project>/<seat> for workstation artifacts.

    Boss/NPC peer launches may start from an already seat-scoped directory. Keeping a
    single normalization point prevents paths such as proj/seat/proj/seat/...
    """
    raw = Path(output_dir)
    project = str(project_id or "").strip()
    if not project:
        return raw
    parts = list(raw.parts)
    lowered_project = project.lower()
    for index in range(len(parts)):
        if parts[index].lower() == lowered_project:
            base_parts = parts[:index]
            if not base_parts:
                return Path(".")
            return Path(*base_parts)
    return raw


def _codex_bin_path() -> str:
    explicit = os.environ.get("CODEX_BIN") or os.environ.get("CODEX_EXE") or ""
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.exists():
            return str(candidate)
    local_app_data = os.environ.get("LOCALAPPDATA") or ""
    if local_app_data:
        candidate = Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if candidate.exists():
            return str(candidate)
    import shutil

    for name in ("codex.exe", "codex.cmd", "codex"):
        found = shutil.which(name)
        if found:
            return found
    user_profile = os.environ.get("USERPROFILE") or ""
    if user_profile:
        npm_candidate = Path(user_profile) / "AppData" / "Roaming" / "npm" / "codex.cmd"
        if npm_candidate.exists():
            return str(npm_candidate)
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    windows_apps = Path(program_files) / "WindowsApps"
    if windows_apps.exists():
        try:
            candidates = sorted(
                windows_apps.glob("OpenAI.Codex_*_x64__*/app/resources/codex.exe"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                return str(candidates[0])
        except OSError:
            pass
    return "codex"


def _codex_desktop_thread_url(thread_id: str) -> str:
    return f"codex://threads/{thread_id.lower()}"


def _codex_sessions_root() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "sessions"


def _find_codex_session_file(session_id: str | None) -> Path | None:
    thread_id = _strip_session_prefix(session_id, "codex")
    if not thread_id:
        return None
    root = _codex_sessions_root()
    if not root.is_dir():
        return None
    matches = sorted(
        root.rglob(f"*{thread_id}.jsonl"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )
    return matches[0] if matches else None


def _content_parts_to_text(parts: Any) -> str:
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
            continue
        if not isinstance(part, dict):
            continue
        value = part.get("text") or part.get("output_text") or part.get("input_text")
        if value:
            texts.append(str(value))
    return "\n".join(text for text in texts if text).strip()


def _codex_record_role_and_text(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return (role, text, phase) for known Codex Desktop jsonl event shapes."""
    record_type = str(record.get("type") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    phase = str(payload.get("phase") or "")
    if record_type == "response_item":
        item_type = str(payload.get("type") or "")
        if item_type == "message":
            return (
                str(payload.get("role") or ""),
                _content_parts_to_text(payload.get("content")),
                phase,
            )
    if record_type == "event_msg":
        event_type = str(payload.get("type") or "")
        if event_type == "agent_message":
            return "assistant", str(payload.get("message") or "").strip(), phase
        if event_type == "user_message":
            return "user", str(payload.get("message") or "").strip(), phase
    return "", "", phase


def _message_id_marker(message_id: str) -> str:
    return f"message_id: `{message_id}`"


def _find_codex_desktop_reply(
    *,
    session_id: str | None,
    message_id: str,
) -> dict[str, Any] | None:
    session_file = _find_codex_session_file(session_id)
    if session_file is None or not session_file.exists():
        return None

    marker = _message_id_marker(message_id)
    try:
        lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    marker_index = -1
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, text, _phase = _codex_record_role_and_text(record)
        if role == "user" and marker in text:
            marker_index = index

    if marker_index < 0:
        return None

    for line in lines[marker_index + 1 :]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, text, phase = _codex_record_role_and_text(record)
        if role == "user" and marker in text:
            continue
        if role != "assistant" or not text:
            continue
        if phase != "final_answer":
            continue
        return {
            "text": text,
            "phase": phase,
            "timestamp": record.get("timestamp"),
            "session_file": str(session_file),
        }
    return None


def _codex_desktop_event_id(record: dict[str, Any], index: int) -> str:
    for key in ("id", "event_id", "item_id", "message_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    for key in ("id", "event_id", "item_id", "message_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return f"jsonl:{index}"


def _codex_desktop_followup_events(
    *,
    session_id: str | None,
    known_message_ids: set[str],
    max_events: int = 20,
) -> list[dict[str, Any]]:
    session_file = _find_codex_session_file(session_id)
    if session_file is None or not session_file.exists():
        return []
    try:
        lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    marker_index = -1
    markers = [_message_id_marker(message_id) for message_id in known_message_ids if message_id]
    if not markers:
        return []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, text, _phase = _codex_record_role_and_text(record)
        if role == "user" and any(marker in text for marker in markers):
            marker_index = index
    if marker_index < 0:
        return []

    events: list[dict[str, Any]] = []
    for index, line in enumerate(lines[marker_index + 1 :], start=marker_index + 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, text, phase = _codex_record_role_and_text(record)
        if role not in {"user", "assistant"} or not text:
            continue
        if role == "user" and any(marker in text for marker in markers):
            continue
        if role == "assistant" and phase not in {"", "minimal_ack", "final_answer"}:
            continue
        events.append(
            {
                "role": role,
                "text": text,
                "phase": phase or ("minimal_ack" if role == "assistant" else "user_message"),
                "timestamp": record.get("timestamp"),
                "event_id": _codex_desktop_event_id(record, index),
                "session_file": str(session_file),
            }
        )
    return events[-max_events:]


def _codex_desktop_prompt_seen(
    *,
    session_id: str | None,
    message_id: str,
) -> dict[str, Any] | None:
    session_file = _find_codex_session_file(session_id)
    if session_file is None or not session_file.exists():
        return None
    marker = _message_id_marker(message_id)
    try:
        lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role, text, phase = _codex_record_role_and_text(record)
        if role == "user" and marker in text:
            return {
                "timestamp": record.get("timestamp"),
                "phase": phase,
                "session_file": str(session_file),
            }
    return None


def _wait_for_codex_desktop_prompt_seen(
    *,
    session_id: str | None,
    message_id: str,
    timeout_seconds: int,
    poll_seconds: float = 0.75,
) -> dict[str, Any] | None:
    deadline = time.time() + max(0, timeout_seconds)
    while time.time() <= deadline:
        seen = _codex_desktop_prompt_seen(session_id=session_id, message_id=message_id)
        if seen:
            return seen
        time.sleep(max(0.25, poll_seconds))
    return None


def _wait_for_codex_desktop_reply(
    *,
    session_id: str | None,
    message_id: str,
    timeout_seconds: int,
    poll_seconds: float = 2.0,
) -> dict[str, Any] | None:
    deadline = time.time() + max(0, timeout_seconds)
    while time.time() <= deadline:
        reply = _find_codex_desktop_reply(session_id=session_id, message_id=message_id)
        if reply:
            return reply
        time.sleep(max(0.5, poll_seconds))
    return None


class _DesktopDeliveryLock:
    def __init__(self, path: Path, *, timeout_seconds: int = 180) -> None:
        self.path = path
        self.timeout_seconds = max(1, timeout_seconds)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout_seconds
        last_error: Exception | None = None
        while time.time() <= deadline:
            try:
                self.handle = self.path.open("x")
                self.handle.write(f"pid={os.getpid()} acquired_at={datetime.now().isoformat()}\n")
                self.handle.flush()
                return self
            except FileExistsError as exc:
                last_error = exc
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    age = 0
                if age > self.timeout_seconds:
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                time.sleep(0.5)
        raise TimeoutError(f"timed out waiting for Codex Desktop UI delivery lock: {self.path}") from last_error

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            try:
                self.handle.close()
            except Exception:
                pass
        try:
            self.path.unlink()
        except OSError:
            pass


def _run_codex_desktop_ui_turn(
    *,
    prompt_text: str,
    session_id: str | None,
    message_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    thread_id = _strip_session_prefix(session_id, "codex")
    if not thread_id:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Codex Desktop UI delivery requires a bound Codex thread id.",
            "note": "Codex Desktop UI delivery failed: missing bound thread id.",
            "delivery_mode": "codex_desktop_ui",
            "desktop_visible": False,
        }
    if os.name != "nt":
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Codex Desktop UI delivery is currently implemented for interactive Windows runners only.",
            "note": "Codex Desktop UI delivery failed: this runner is not an interactive Windows desktop.",
            "delivery_mode": "codex_desktop_ui",
            "desktop_visible": False,
            "thread_id": thread_id,
        }

    helper = r"""
param(
  [Parameter(Mandatory = $true)][string]$ThreadUrl,
  [Parameter(Mandatory = $true)][string]$PromptText,
  [int]$InitialWaitMs = 2600
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Focus {
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
}
"@

function Get-ForegroundTitle {
  $handle = [Win32Focus]::GetForegroundWindow()
  $builder = New-Object System.Text.StringBuilder 512
  [void][Win32Focus]::GetWindowText($handle, $builder, $builder.Capacity)
  return $builder.ToString()
}

function Focus-CodexDesktop {
  $shell = New-Object -ComObject WScript.Shell
  $matched = $false
  foreach ($name in @("Codex", "codex")) {
    try {
      if ($shell.AppActivate($name)) {
        $matched = $true
        Start-Sleep -Milliseconds 320
        break
      }
    } catch {
    }
  }
  if (-not $matched) {
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "start", '""', $ThreadUrl) -WindowStyle Hidden | Out-Null
    Start-Sleep -Milliseconds 900
  }
  return Get-ForegroundTitle
}

function Assert-CodexForeground {
  param([string]$Stage)
  $title = Get-ForegroundTitle
  if ($title -notmatch "(?i)codex") {
    throw ("desktop_focus_lost stage=" + $Stage + "; foreground=" + $title)
  }
  return $title
}

function Try-SetClipboardText {
  param([string]$Text)
  $lastError = $null
  for ($i = 0; $i -lt 8; $i++) {
    try {
      [System.Windows.Forms.Clipboard]::SetText($Text)
      return $true
    } catch {
      $lastError = $_
      Start-Sleep -Milliseconds (180 + ($i * 120))
    }
  }
  throw $lastError
}

function Try-SendPlatformPrompt {
  param([string]$Text)
  $title = Focus-CodexDesktop
  Assert-CodexForeground -Stage "before_clipboard" | Out-Null
  Try-SetClipboardText -Text $Text | Out-Null
  Start-Sleep -Milliseconds 180
  $title = Focus-CodexDesktop
  Assert-CodexForeground -Stage "before_paste" | Out-Null
  [System.Windows.Forms.SendKeys]::SendWait("^v")
  Start-Sleep -Milliseconds 220
  $title = Focus-CodexDesktop
  Assert-CodexForeground -Stage "before_submit" | Out-Null
  [System.Windows.Forms.SendKeys]::SendWait("^{ENTER}")
  Start-Sleep -Milliseconds 180
  Assert-CodexForeground -Stage "after_submit" | Out-Null
  Write-Output ("delivery_attempt=1; foreground=" + $title)
}

Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "start", '""', $ThreadUrl) -WindowStyle Hidden | Out-Null
Start-Sleep -Milliseconds $InitialWaitMs
Try-SendPlatformPrompt -Text $PromptText
"""
    thread_url = _codex_desktop_thread_url(thread_id)
    wait_ms = 3200
    helper_path = None
    delivery_attempts = 0
    try:
        with _DesktopDeliveryLock(CODEX_DESKTOP_UI_LOCK_PATH, timeout_seconds=max(60, min(timeout_seconds, 240))):
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as helper_file:
                helper_file.write(helper)
                helper_path = helper_file.name
            completed: subprocess.CompletedProcess[str] | None = None
            seen = None
            max_attempts = max(1, CODEX_DESKTOP_UI_MAX_DELIVERY_ATTEMPTS)
            for attempt in range(max_attempts):
                delivery_attempts = attempt + 1
                attempt_wait_ms = wait_ms if attempt == 0 else 900
                current = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        helper_path,
                        "-ThreadUrl",
                        thread_url,
                        "-PromptText",
                        prompt_text,
                        "-InitialWaitMs",
                        str(attempt_wait_ms),
                    ],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=max(12, min(timeout_seconds, 30)),
                )
                if completed is None:
                    completed = current
                else:
                    completed = subprocess.CompletedProcess(
                        completed.args,
                        current.returncode,
                        stdout=f"{completed.stdout}\n{current.stdout}".strip(),
                        stderr=f"{completed.stderr}\n{current.stderr}".strip(),
                    )
                if current.returncode != 0 and attempt < max_attempts - 1:
                    time.sleep(0.4)
                    continue
                if current.returncode == 0:
                    seen = _wait_for_codex_desktop_prompt_seen(
                        session_id=session_id,
                        message_id=message_id,
                        timeout_seconds=min(max(timeout_seconds, 1), 12),
                    )
                    if seen:
                        break
                if attempt < max_attempts - 1:
                    time.sleep(min(1.6, 0.35 + (attempt * 0.2)))
            if completed and completed.returncode == 0:
                if not seen:
                    return {
                        "ok": False,
                        "recoverable": True,
                        "returncode": completed.returncode,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                        "note": (
                            "已尝试把派单送到绑定桌面线程，但桌面线程还没有确认收到。"
                            "可能是桌面窗口被用户操作打断；平台会保持待收口，可重新同步或手动收口。"
                        ),
                        "delivery_mode": "codex_desktop_ui",
                        "desktop_visible": True,
                        "desktop_delivery_confirmed": False,
                        "desktop_delivery_unconfirmed": True,
                        "desktop_delivery_attempts": delivery_attempts,
                        "desktop_delivery_auto_retried": delivery_attempts > 1,
                        "thread_id": thread_id,
                        "desktop_thread_url": thread_url,
                    }
                return {
                    "ok": True,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "note": (
                        "已把这条平台派单发送到绑定的 Codex Desktop 线程。"
                        "完整处理过程会在桌面版 Codex 对话框里继续；平台不会把这次投递当作最终完成。"
                    ),
                    "delivery_mode": "codex_desktop_ui",
                    "desktop_visible": True,
                    "desktop_delivery_confirmed": True,
                    "desktop_delivery_attempts": delivery_attempts,
                    "desktop_delivery_auto_retried": delivery_attempts > 1,
                    "desktop_seen": seen,
                    "thread_id": thread_id,
                    "desktop_thread_url": thread_url,
                }
    except Exception as exc:
        return {
            "ok": False,
            "recoverable": True,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "note": (
                "桌面投递被本机操作打断，平台已保留任务并进入待收口。"
                "请点击“重新同步”再次发送，或确认桌面结果后手动收口。"
            ),
            "delivery_mode": "codex_desktop_ui",
            "desktop_visible": True,
            "desktop_delivery_confirmed": False,
            "desktop_delivery_unconfirmed": True,
            "desktop_delivery_attempts": delivery_attempts,
            "desktop_delivery_auto_retried": delivery_attempts > 1,
            "thread_id": thread_id,
            "desktop_thread_url": thread_url,
        }
    finally:
        if helper_path:
            try:
                Path(helper_path).unlink(missing_ok=True)
            except Exception:
                pass
    ok = completed.returncode == 0
    if ok:
        seen = _wait_for_codex_desktop_prompt_seen(
            session_id=session_id,
            message_id=message_id,
            timeout_seconds=min(max(timeout_seconds, 1), 20),
        )
        if not seen:
            return {
                "ok": False,
                "recoverable": True,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "note": (
                    "已尝试把派单送到绑定桌面线程，但桌面线程还没有确认收到。"
                    "可能是桌面窗口被用户操作打断；平台会保持待收口，可重新同步或手动收口。"
                ),
                "delivery_mode": "codex_desktop_ui",
                "desktop_visible": True,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_unconfirmed": True,
                "thread_id": thread_id,
                "desktop_thread_url": thread_url,
            }
        return {
            "ok": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "note": (
                "已把这条平台派单发送到绑定的 Codex Desktop 线程。"
                "完整处理过程会在桌面版 Codex 对话框里继续；平台不会把这次投递当作最终完成。"
            ),
            "delivery_mode": "codex_desktop_ui",
            "desktop_visible": True,
            "desktop_delivery_confirmed": True,
            "desktop_seen": seen,
            "thread_id": thread_id,
            "desktop_thread_url": thread_url,
        }
    return {
        "ok": False,
        "recoverable": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "note": (
            "桌面投递暂未成功确认，平台已保留任务并进入待收口。"
            "请点击“重新同步”再次发送，或确认桌面结果后手动收口。"
        ),
        "delivery_mode": "codex_desktop_ui",
        "desktop_visible": True,
        "desktop_delivery_confirmed": False,
        "desktop_delivery_unconfirmed": True,
        "desktop_delivery_attempts": delivery_attempts,
        "desktop_delivery_auto_retried": delivery_attempts > 1,
        "thread_id": thread_id,
        "desktop_thread_url": thread_url,
    }


def _jsonrpc_send(proc: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise RuntimeError("codex app-server stdin is not available")
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def _run_codex_app_server_turn(
    *,
    prompt_text: str,
    session_id: str | None,
    cwd: str | None,
    timeout_seconds: int,
    model: str | None,
) -> dict[str, Any]:
    thread_id = _strip_session_prefix(session_id, "codex")
    if not thread_id:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Codex app-server delivery requires a bound Codex thread id.",
            "note": "Codex app-server delivery failed: missing bound thread id.",
        }
    resolved_cwd = str(cwd or "").strip() or None
    cwd_warning = ""
    if resolved_cwd:
        cwd_path = Path(resolved_cwd).expanduser()
        if cwd_path.is_dir():
            resolved_cwd = str(cwd_path)
        else:
            cwd_warning = f"本机配置的执行目录不可用：{resolved_cwd!r}；已自动改用适配器启动目录。"
            resolved_cwd = None
    codex_bin = _codex_bin_path()
    try:
        proc = subprocess.Popen(
            [codex_bin, "app-server", "--listen", "stdio://"],
            cwd=resolved_cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )
    except OSError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "note": "\n".join(part for part in [cwd_warning, f"Codex app-server could not start: {exc}"] if part),
        }

    stdout_lines: list[str] = []
    stderr_chunks: list[str] = []
    final_text_parts: list[str] = []
    thread_resumed = False
    turn_started = False
    turn_completed = False
    request_error: dict[str, Any] | None = None
    started_at = time.time()

    import threading

    def _read_stderr() -> None:
        if proc.stderr is None:
            return
        try:
            for chunk in iter(proc.stderr.readline, ""):
                if chunk == "":
                    break
                stderr_chunks.append(chunk)
        except Exception:
            pass

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    try:
        _jsonrpc_send(
            proc,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "ai-collab-platform",
                        "title": "AI Collab Platform",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            },
        )
        if proc.stdout is None:
            raise RuntimeError("codex app-server stdout is not available")
        while time.time() - started_at < timeout_seconds:
            line = proc.stdout.readline()
            if line == "":
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            stdout_lines.append(line)
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") == 1 and msg.get("result"):
                resume_params: dict[str, Any] = {
                    "threadId": thread_id,
                    "cwd": resolved_cwd,
                    "approvalPolicy": "never",
                    "sandbox": "danger-full-access",
                    "persistExtendedHistory": True,
                }
                if model:
                    resume_params["model"] = model
                _jsonrpc_send(proc, {"id": 2, "method": "thread/resume", "params": resume_params})
            elif msg.get("id") == 2:
                if msg.get("error"):
                    request_error = dict(msg.get("error") or {})
                    break
                thread_resumed = True
                turn_params: dict[str, Any] = {
                    "threadId": thread_id,
                    "cwd": resolved_cwd,
                    "input": [{"type": "text", "text": prompt_text}],
                    "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "dangerFullAccess"},
                }
                if model:
                    turn_params["model"] = model
                _jsonrpc_send(proc, {"id": 3, "method": "turn/start", "params": turn_params})
            elif msg.get("id") == 3:
                if msg.get("error"):
                    request_error = dict(msg.get("error") or {})
                    break
                turn_started = True
            elif msg.get("method") == "turn/started":
                turn_started = True
            elif msg.get("method") == "item/agentMessage/delta":
                params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                final_text_parts.append(str(params.get("delta") or ""))
            elif msg.get("method") == "item/completed":
                params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                item = params.get("item") if isinstance(params.get("item"), dict) else {}
                if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                    text = str(item.get("text") or "").strip()
                    if text:
                        final_text_parts = [text]
            elif msg.get("method") == "turn/completed":
                turn_completed = True
                break
        else:
            request_error = {"message": f"Codex app-server turn timed out after {timeout_seconds}s"}
    except Exception as exc:
        request_error = {"message": str(exc)}
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        stderr_thread.join(timeout=1)

    stdout = "".join(stdout_lines).strip()
    stderr = "".join(stderr_chunks).strip()
    final_text = "".join(final_text_parts).strip()
    ok = bool(thread_resumed and turn_started and turn_completed and not request_error)
    if ok:
        note = final_text or "Codex app-server session turn completed without a final text."
        return {
            "ok": True,
            "returncode": 0,
            "stdout": final_text or stdout,
            "stderr": stderr,
            "note": "\n".join(part for part in [cwd_warning, note] if part),
            "delivery_mode": "codex_app_server",
            "thread_id": thread_id,
        }
    error_text = str((request_error or {}).get("message") or stderr or "Codex app-server turn failed")
    return {
        "ok": False,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr or error_text,
        "note": "\n".join(part for part in [cwd_warning, f"Codex app-server delivery failed: {error_text}"] if part),
        "delivery_mode": "codex_app_server",
        "thread_id": thread_id,
    }


def run_executor(
    *,
    template: str,
    command_path: Path,
    project_id: str,
    workstation_id: str,
    provider: str,
    message_id: str,
    model: str | None,
    session_id: str | None = None,
    cwd: str | None,
    timeout_seconds: int,
    live_output: bool = False,
    spawn_window: bool = False,
) -> dict[str, Any]:
    command_text = command_path.read_text(encoding="utf-8")
    prompt_text = _extract_executor_prompt(command_text)
    executor_prompt_path = command_path.with_name(f"{command_path.stem}.executor.md")
    executor_prompt_path.write_text(prompt_text, encoding="utf-8")
    executor_prompt_path = executor_prompt_path.resolve()
    if template == CODEX_APP_SERVER_EXECUTOR:
        return _run_codex_app_server_turn(
            prompt_text=prompt_text,
            session_id=session_id,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            model=model,
        )
    if template == CODEX_DESKTOP_UI_EXECUTOR:
        app_server_result = _run_codex_app_server_turn(
            prompt_text=prompt_text,
            session_id=session_id,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            model=model,
        )
        if app_server_result.get("ok"):
            return {
                **app_server_result,
                "note": "\n".join(
                    part
                    for part in [
                        "已通过 Codex 后台线程通道恢复绑定线程并完成本轮处理；不会抢占用户当前窗口或剪贴板，但也不会保证 Codex Desktop 当前界面实时显示这条单次派单。",
                        str(app_server_result.get("note") or "").strip(),
                    ]
                    if part
                ),
                "delivery_mode": "codex_app_server",
                "desktop_visible": False,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_method": "codex_app_server_thread_resume",
            }
        allow_sendkeys_fallback = os.environ.get("AI_COLLAB_ALLOW_CODEX_UI_SENDKEYS_FALLBACK") == "1"
        if not allow_sendkeys_fallback:
            return {
                **app_server_result,
                "ok": False,
                "recoverable": True,
                "note": "\n".join(
                    part
                    for part in [
                        "Codex 后台线程通道暂未完成投递；为避免打断用户当前桌面操作，平台没有使用剪贴板或快捷键兜底。",
                        str(app_server_result.get("note") or "").strip(),
                        "请保持 Codex 登录并确认该线程可恢复；如果必须让桌面界面立刻可见，需要接入 Codex 桌面自动化通道，而不是后台 app-server。",
                    ]
                    if part
                ),
                "delivery_mode": "codex_app_server",
                "desktop_visible": False,
                "desktop_delivery_confirmed": False,
                "desktop_delivery_method": "codex_app_server_thread_resume",
            }
        ui_result = _run_codex_desktop_ui_turn(
            prompt_text=prompt_text,
            session_id=session_id,
            message_id=message_id,
            timeout_seconds=timeout_seconds,
        )
        if ui_result.get("ok"):
            return ui_result
        ui_note = str(ui_result.get("note") or "").strip()
        if ui_result.get("recoverable") and ui_result.get("desktop_delivery_confirmed") is False:
            return {
                **ui_result,
                "ok": False,
                "recoverable": True,
                "note": ui_note
                or (
                    "桌面线程暂未确认收到这条派单。平台会保持待收口，"
                    "可重新同步、延长等待或手动收口。"
                ),
                "desktop_visible": bool(ui_result.get("desktop_visible", True)),
                "delivery_mode": "codex_desktop_ui",
            }
        return {
            **ui_result,
            "ok": False,
            "note": "\n".join(
                part
                for part in [
                    ui_note,
                    "平台要求用户派工、Boss 派工、NPC 互派都必须在桌面版看到详细处理过程；本次未确认 Codex Desktop 可见投递，已停止后台降级。",
                    "请在工作台点击“重新同步”，或确认桌面结果后手动收口；管理员也可以检查该 NPC 的桌面线程绑定。",
                ]
                if part
            ),
            "desktop_visible": False,
            "delivery_mode": "codex_desktop_ui_required_failed",
        }
    resolved_cwd = str(cwd or "").strip() or None
    cwd_warning = ""
    if resolved_cwd:
        cwd_path = Path(resolved_cwd).expanduser()
        if cwd_path.is_dir():
            resolved_cwd = str(cwd_path)
        else:
            cwd_warning = (
                f"本机配置的执行目录不可用：{resolved_cwd!r}；"
                "已自动改用适配器启动目录。"
            )
            resolved_cwd = None
    rendered = _render_executor_command(
        template,
        prompt_file=executor_prompt_path,
        prompt_text=prompt_text,
        project_id=project_id,
        workstation_id=workstation_id,
        provider=provider,
        message_id=message_id,
        model=model,
        session_id=session_id,
    )
    if spawn_window:
        return _spawn_in_new_window(
            rendered,
            cwd=resolved_cwd,
            timeout_seconds=timeout_seconds,
            provider=provider,
            cwd_warning=cwd_warning,
            title=f"NPC {workstation_id} · {provider}",
        )
    if live_output:
        return _run_executor_streaming(
            rendered,
            cwd=resolved_cwd,
            timeout_seconds=timeout_seconds,
            provider=provider,
            cwd_warning=cwd_warning,
        )
    try:
        completed = subprocess.run(
            rendered,
            shell=True,
            cwd=resolved_cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return {
            "ok": False,
            "returncode": None,
            "stdout": stdout,
            "stderr": stderr or f"executor timed out after {timeout_seconds}s",
            "note": "\n".join(
                part
                for part in [cwd_warning, f"{provider} executor timed out after {timeout_seconds}s."]
                if part
            ),
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "note": "\n".join(
                part
                for part in [
                    cwd_warning,
                    f"{provider} executor could not start: {exc}",
                ]
                if part
            ),
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode == 0:
        return {
            "ok": True,
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "note": "\n".join(
                part
                for part in [
                    cwd_warning,
                    stdout or f"{provider} executor completed without stdout.",
                ]
                if part
            ),
        }
    return {
        "ok": False,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "note": "\n".join(
            part
            for part in [
                cwd_warning,
                f"{provider} executor failed with exit code {completed.returncode}.",
                stdout,
                stderr,
            ]
            if part
        ),
    }


def _resolve_bound_session(
    *,
    base: str,
    project_id: str,
    workstation_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """读 seat 的 thread_workstation 行，解析它绑定的 claude/codex session_id + cwd + provider。

    返回 dict: {provider, session_id, cwd, source_file, seat_name, error?}
    - 如果 config_id 是 `claude-session-<uuid>` / `codex-session-<uuid>`，session_id 就是后缀
    - cwd 优先 extra_data.cwd，其次 workspace_root；都空就 None（让 caller 退化）
    - 解析不出 session_id 时返回 error，caller 应在窗口里报错并停在 Read-Host
    """
    from urllib.parse import quote as _q
    encoded_project_id = _q(project_id, safe="")
    encoded_workstation_id = _q(workstation_id, safe="")
    list_url = f"{base.rstrip('/')}/api/collaboration/projects/{encoded_project_id}/thread-workstations"
    try:
        payload = _json_request("GET", list_url, headers=headers)
    except Exception as exc:
        return {"error": f"无法读取 seat 列表: {exc}"}
    seats = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(seats, list):
        return {"error": "seat 列表返回格式异常"}
    me = next(
        (
            s for s in seats
            if str(s.get("id") or "") == workstation_id
            or str(s.get("config_id") or "") == workstation_id
            or str(s.get("name") or "") == workstation_id
        ),
        None,
    )
    if me is None:
        return {"error": f"在项目 {project_id} 下找不到 seat {workstation_id!r}"}
    # API 把 DB 列 extra_data 通过 alias 映射到字段名 `metadata`（见 schemas.py 的 from_attributes alias）。
    # 老字段名 extra_data 也兼容一下（DB 直读路径）。
    extra = me.get("metadata") if isinstance(me.get("metadata"), dict) else (me.get("extra_data") if isinstance(me.get("extra_data"), dict) else {})
    config_id = str(me.get("config_id") or "")
    # 优先从 config_id 前缀抽 session_id
    session_id = ""
    provider_family = ""
    if config_id.startswith("claude-session-"):
        session_id = config_id[len("claude-session-"):]
        provider_family = "claude"
    elif config_id.startswith("codex-session-"):
        session_id = config_id[len("codex-session-"):]
        provider_family = "codex"
    else:
        # 兜底：extra_data 里偶尔会有 session_id 字段
        session_id = str(extra.get("session_id") or "").strip()
        provider_family = str(extra.get("provider_family") or extra.get("ai_provider") or "").strip().lower()
    cwd = str(extra.get("cwd") or extra.get("workspace_root") or "").strip() or None
    source_file = str(extra.get("source_file") or "").strip() or None
    # sync-claude-session-threads.ps1 把扫描到的 cwd 字段按系统 ANSI 写库导致中文乱码（如 'D:\\ai������Ʒ'）。
    # 从对应 jsonl 第一段读 UTF-8 的 cwd 兜底，覆盖掉乱码值。
    if source_file and Path(source_file).exists():
        try:
            with open(source_file, "r", encoding="utf-8", errors="replace") as f:
                for _i, _line in enumerate(f):
                    if _i > 5:
                        break
                    try:
                        _rec = json.loads(_line)
                    except Exception:
                        continue
                    _real_cwd = _rec.get("cwd") if isinstance(_rec, dict) else None
                    if isinstance(_real_cwd, str) and _real_cwd.strip():
                        cwd = _real_cwd.strip()
                        break
        except Exception:
            pass
    return {
        "provider": provider_family or "claude",
        "session_id": session_id or None,
        "cwd": cwd,
        "source_file": source_file,
        "seat_name": str(me.get("name") or me.get("config_id") or workstation_id),
    }


def _open_persistent_window(
    *,
    provider: str,
    cwd: str | None,
    title: str,
    inbox_md_path: Path,
    project_id: str,
    workstation_id: str,
    seat_id: str,
    session_id: str | None = None,
    seat_name: str = "",
    bind_error: str = "",
) -> None:
    """长开模式：watcher 启动时弹一次 PowerShell 窗口，里面跑 `claude --resume <session_id>` 续上 NPC 绑定的会话。
    之后所有派单都只追加到 inbox_md_path（一个共享 markdown 文件）。
    NPC 在窗口里通过 MCP `read_my_inbox` 拉新派单 + `mark_done` 写回执。
    用户可在窗口直接打字。watcher 不阻塞；窗口关与不关都不影响 watcher 主循环。
    如果 seat 还没绑定 session_id（bind_error 非空），就在窗口里红字提示，停在 Read-Host 不起 claude。"""
    if os.name != "nt":
        print(f"[platform] --persistent-window 目前仅支持 Windows；当前平台 {os.name}，已忽略。", flush=True)
        return
    inbox_str = str(inbox_md_path).replace("'", "''")
    # Windows 下 / 和 \ 都能用，但 npm shim 的 join 在 / 风格 cwd 下会拼错路径，统一成 \。
    cwd_normalized = str(Path(cwd).resolve()) if cwd else ""
    cwd_clause = f"Set-Location -LiteralPath '{cwd_normalized.replace(chr(39), chr(39)*2)}'; " if cwd_normalized else ""
    intro = (
        f"Write-Host '========================================' -ForegroundColor Cyan; "
        f"Write-Host 'NPC persistent CLI window' -ForegroundColor Green; "
        f"Write-Host ('project: {project_id}') -ForegroundColor Yellow; "
        f"Write-Host ('workstation: {workstation_id}') -ForegroundColor Yellow; "
        f"Write-Host ('seat: {seat_id}') -ForegroundColor Yellow; "
        f"Write-Host ('inbox: {inbox_str}') -ForegroundColor Gray; "
        f"Write-Host '----------------------------------------' -ForegroundColor Cyan; "
        f"Write-Host 'How to use:' -ForegroundColor Cyan; "
        f"Write-Host '  1) Talk to claude directly here.' -ForegroundColor Gray; "
        f"Write-Host '  2) New dispatches appended to the inbox file. Tell claude: call read_my_inbox.' -ForegroundColor Gray; "
        f"Write-Host '  3) After handling a dispatch, claude calls mark_done(message_id, body).' -ForegroundColor Gray; "
        f"Write-Host '  4) Closing this window does NOT stop the watcher.' -ForegroundColor Gray; "
        f"Write-Host '========================================' -ForegroundColor Cyan; "
    )
    # 长开模式里直接根据 seat 绑定的 provider 选可执行命令名（claude / codex），不管 adapter-config 的 provider label。
    p_lower = (provider or "").lower()
    if "codex" in p_lower:
        repl_cmd = "codex"
    else:
        repl_cmd = "claude"
    # PowerShell 里 -Command 参数的字符串里不能出现裸单引号（`’` / `'`），也不能漏闭合。
    # 一律把 PS 字符串里的单引号 escape 成双单引号。
    def _psq(s: str) -> str:
        return s.replace("'", "''")
    # 把 watcher 进程当下的 PLATFORM_* env 显式写进 ps1，让窗口里的 claude 一开就用对 seat 身份
    # （否则 PLATFORM_SEAT_ID 要等第一条派单才设置，这时 claude 已经 fork 了拿不到）。
    env_lines = []
    for var in ("PLATFORM_API_BASE", "PLATFORM_PROJECT_ID", "PLATFORM_WORKSTATION_ID", "PLATFORM_SEAT_ID", "PLATFORM_ADAPTER_TOKEN", "PLATFORM_AUTH_TOKEN"):
        val = os.environ.get(var) or ""
        if val:
            env_lines.append(f"$env:{var} = '{_psq(val)}'; ")
    # 保底：如果 PLATFORM_SEAT_ID 为空就用 watcher 拿到的 seat_id 兜底（一一对应）
    if "PLATFORM_SEAT_ID" not in os.environ or not os.environ.get("PLATFORM_SEAT_ID"):
        env_lines.append(f"$env:PLATFORM_SEAT_ID = '{_psq(seat_id)}'; ")
    env_block = "".join(env_lines)
    ps_body = (
        f"$Host.UI.RawUI.WindowTitle = '{_psq(title)}'; "
        f"{cwd_clause}"
        f"{env_block}"
        f"{intro}"
        f"$ErrorActionPreference = 'Continue'; "
    )
    if bind_error:
        # seat 没绑 session：直接在窗口红字提示，不起 claude；用户处理后下次再起 watcher
        ps_body += (
            f"Write-Host ''; "
            f"Write-Host '[platform] 这个 NPC 还没绑定具体的 claude/codex 线程，无法 resume：' -ForegroundColor Red; "
            f"Write-Host ' {_psq(bind_error)}' -ForegroundColor Red; "
            f"Write-Host ''; "
            f"Write-Host '解决：' -ForegroundColor Yellow; "
            f"Write-Host '  1) 先在另一个 PowerShell 跑 sync-claude-session-threads.ps1 把本机线程同步上来' -ForegroundColor Gray; "
            f"Write-Host '  2) 在驾驶舱机房面板把这个 NPC 绑定到一条具体的 claude session' -ForegroundColor Gray; "
            f"Write-Host '  3) 重起 watcher' -ForegroundColor Gray; "
        )
    else:
        # 历史教训（5-08 撞 5 次后定型）：用户最早原话是「开个 powershell 输 claude」——
        # ps1 别尝试任何形式自动起 claude REPL（`& exe` / Start-Process / 裸名字 / cmd /c shim 全踩坑）。
        # ps1 只做 setup：cwd / env / PATH 修好，然后 -NoExit 把 PS 提示符给用户，
        # 用户在交互 prompt 里输 `claude`（PS 走交互 stdin，避免任何 string-parser / TTY-sniffing 问题）。
        # 这条路用户已亲测 OK（"2.1.133 (Claude Code)" 在此模式下能起 REPL）。
        ps_body += (
            f"Write-Host ''; "
            f"Write-Host '[platform] window ready — workspace cwd is set, env is injected.' -ForegroundColor Green; "
            f"$npmBin = Join-Path $env:APPDATA 'npm'; "
            f"if (Test-Path -LiteralPath $npmBin) {{ $env:PATH = $npmBin + ';' + $env:PATH }}; "
            f"if (Get-Command {repl_cmd} -ErrorAction SilentlyContinue) {{ "
            f"  Write-Host '[platform] {repl_cmd} is on PATH.' -ForegroundColor Green; "
            f"}} else {{ "
            f"  Write-Host '[platform] WARNING: {repl_cmd} not on PATH. Install: npm i -g @anthropic-ai/claude-code' -ForegroundColor Red; "
            f"}}; "
            f"Write-Host ''; "
            f"Write-Host '----------------------------------------' -ForegroundColor Cyan; "
            f"Write-Host ('[platform] type ''{repl_cmd}'' below to launch the REPL.') -ForegroundColor Cyan; "
            f"Write-Host '[platform] inside the REPL, slash-resume to pick a previous session for history.' -ForegroundColor Gray; "
            f"Write-Host ''; "
        )
    # 不再 Read-Host —— 让 -NoExit 直接把 PS 提示符交给用户，他们自己输 `claude`/`codex` 启 REPL。
    # 这样：每台电脑都能用（靠 PATH shim）、watcher 不阻塞、用户能 cd 切目录、能输 git 命令、能多次重启 REPL。
    if not bind_error:
        ps_body += (
            f"Write-Host ''; "
            f"Write-Host '----------------------------------------' -ForegroundColor Cyan; "
            f"Write-Host '[platform] this PS window stays open. Type a command:' -ForegroundColor Cyan; "
            f"Write-Host ''; "
        )
    else:
        # bind_error 路径仍然停一停让用户看清提示
        ps_body += (
            f"Write-Host ''; "
            f"Write-Host 'Press Enter to dismiss (watcher keeps running)...' -ForegroundColor Cyan; "
            f"$null = Read-Host"
        )
    # 长 -Command argv 走 cmd.exe / powershell 编码层会被 GBK 截断（中文 workstation_id 是常见触发点），
    # 改为写到临时 .ps1 文件 + -File 启动，绕开 argv 编码完全可控。
    import tempfile as _tmp
    ps1 = Path(_tmp.gettempdir()) / f"platform-window-{os.getpid()}.ps1"
    # 不写 BOM、不用 chcp（之前那两条会让某些命令在 -File 模式下状态异常）。
    # PowerShell 5.1 默认按系统 ANSI 读 .ps1，所以脚本里**禁止**出现非 ASCII 字符——
    # 中文标题等都已经在 ps_body 里只用 ASCII（重要中文已经从 intro 里清掉了）。
    ps1.write_text(ps_body, encoding="utf-8-sig" if any(ord(c) > 127 for c in ps_body) else "ascii", errors="replace")
    # 直接用 argv 列表调 powershell，绕过 cmd.exe / shell=True 的 quote 剥离链。
    # 关键：用 CREATE_NEW_CONSOLE flag 让 powershell 自己开新窗口（不依赖 Start-Process）。
    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        creationflags = subprocess.CREATE_NEW_CONSOLE
    # 优先 pwsh 7（没有 -File 占 stdin 的坑，ps1 能自动起 claude REPL）；找不到 fallback powershell 5.1。
    import shutil as _sh
    pwsh_exe = _sh.which("pwsh") or _sh.which("pwsh.exe") or ""
    if not pwsh_exe:
        # 兜底几个标准安装位置
        for cand in [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
        ]:
            if Path(cand).exists():
                pwsh_exe = cand
                break
    shell_exe = pwsh_exe or "powershell.exe"
    shell_label = "pwsh7" if pwsh_exe else "powershell5.1"
    try:
        subprocess.Popen(
            [shell_exe, "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            creationflags=creationflags,
            close_fds=True,
        )
        print(f"[{_now_hms()}] [platform] persistent {provider} setup window spawned via {shell_label} (ps1={ps1})", flush=True)
    except Exception as exc:
        print(f"[{_now_hms()}] [platform] setup window spawn failed: {exc}", flush=True)

    # 关键改动（2026-05-08 第 6 次尝试）：不让 ps1 起 claude（任何 PS 路径都崩），
    # 改成 Python 直接 Popen claude.exe + CREATE_NEW_CONSOLE 自己开第二个窗口。
    # 完全绕开 PS string parser / shim chain / TTY sniffing 链路。
    # 直接 CreateProcess 行 — sandbox 已验过 Python `subprocess.run([exe, '--version'])` exit=0。
    if not bind_error:
        # 多候选解析 .exe 真路径（npm 全局标准布局；APPDATA 重定向兜底）
        repl_exe_full = ""
        candidates: list[str] = []
        ccp = os.environ.get("CLAUDE_CODE_EXECPATH") or ""
        if ccp:
            candidates.append(ccp)
        # 通过 shutil.which 找 shim，shim 同目录里 node_modules/...
        try:
            shim_path = _sh.which(repl_cmd) or _sh.which(f"{repl_cmd}.cmd") or _sh.which(f"{repl_cmd}.ps1") or ""
            if shim_path:
                shim_dir = Path(shim_path).resolve().parent
                candidates.append(str(shim_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / f"{repl_cmd}.exe"))
        except Exception:
            pass
        # APPDATA / 硬编码兜底
        appdata = os.environ.get("APPDATA") or ""
        if appdata:
            candidates.append(str(Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / f"{repl_cmd}.exe"))
        username = os.environ.get("USERNAME") or ""
        if username:
            candidates.append(f"C:\\Users\\{username}\\AppData\\Roaming\\npm\\node_modules\\@anthropic-ai\\claude-code\\bin\\{repl_cmd}.exe")
        for cand in candidates:
            if cand and Path(cand).exists():
                repl_exe_full = cand
                break

        if not repl_exe_full:
            print(f"[{_now_hms()}] [platform] {repl_cmd}.exe not found, tried:", flush=True)
            for cand in candidates:
                print(f"[{_now_hms()}]   - {cand}", flush=True)
            print(f"[{_now_hms()}] [platform] install: npm i -g @anthropic-ai/{repl_cmd}-code", flush=True)
        else:
            try:
                # CREATE_NEW_CONSOLE 让 claude.exe 自己开终端窗口；env 完整继承（PLATFORM_* 已注入）；
                # cwd 用 NPC 绑定的 cwd 让 claude 进对项目目录。
                claude_env = dict(os.environ)
                # 保险：再次确认 PLATFORM_* env 注入（理论上已经在）
                claude_env["PLATFORM_API_BASE"] = os.environ.get("PLATFORM_API_BASE") or base
                claude_env["PLATFORM_PROJECT_ID"] = os.environ.get("PLATFORM_PROJECT_ID") or str(args.project_id)
                claude_env["PLATFORM_SEAT_ID"] = os.environ.get("PLATFORM_SEAT_ID") or seat_id
                claude_env["PLATFORM_WORKSTATION_ID"] = os.environ.get("PLATFORM_WORKSTATION_ID") or str(args.workstation_id)
                subprocess.Popen(
                    [repl_exe_full],
                    cwd=cwd_normalized or None,
                    env=claude_env,
                    creationflags=creationflags,
                    close_fds=True,
                )
                print(f"[{_now_hms()}] [platform] {repl_cmd} REPL spawned in its own console (exe={repl_exe_full})", flush=True)
            except Exception as exc:
                print(f"[{_now_hms()}] [platform] {repl_cmd} spawn failed: {exc}", flush=True)


def _append_dispatch_to_inbox(
    inbox_md_path: Path,
    command: dict[str, Any],
    *,
    project_id: str,
    workstation_id: str,
    provider: str,
    computer_node_id: str = "",
    workstation_knowledge_path: str = "",
) -> None:
    """长开模式下把派单追加到 markdown inbox 文件，给窗口里的 claude 看。"""
    inbox_md_path.parent.mkdir(parents=True, exist_ok=True)
    block = _command_markdown(
        command,
        project_id=project_id,
        workstation_id=workstation_id,
        provider=provider,
        computer_node_id=computer_node_id,
        workstation_knowledge_path=workstation_knowledge_path,
    )
    sep = "\n\n---\n\n"
    header = f"\n\n# 📥 新派单 @ {_now_hms()} (message_id={command.get('id')})\n\n"
    if not inbox_md_path.exists():
        inbox_md_path.write_text(
            "# NPC 长开模式派单 inbox\n\n"
            "> 这个文件由 watcher 维护。每条新派单会追加到下面。\n"
            "> 在 claude 窗口里调 `read_my_inbox` 看完整字段（含 id / sender / status）。\n"
            "> 处理完后调 `mark_done(message_id, body)` 写回执；watcher 不会自动写。\n",
            encoding="utf-8",
        )
    with inbox_md_path.open("a", encoding="utf-8") as f:
        f.write(sep + header + block)


def _spawn_in_new_window(
    rendered: str,
    *,
    cwd: str | None,
    timeout_seconds: int,
    provider: str,
    cwd_warning: str,
    title: str = "Claude Code 线程",
    output_capture_path: Path | None = None,
) -> dict[str, Any]:
    """在 Windows 下弹独立 PowerShell 终端跑 CLI，让用户能看到真实的 AI 对话过程。
    为了能把 CLI 的 stdout 拉回 watcher，用 Tee-Object 把 stdout 同时写到
    output_capture_path；watcher 等进程结束后读这个文件作为 note。"""
    import shlex
    capture = output_capture_path
    if capture is None:
        import tempfile, uuid
        capture = Path(tempfile.gettempdir()) / f"platform-claude-{uuid.uuid4().hex[:8]}.log"
    capture_str = str(capture).replace("'", "''")
    rendered_escaped = rendered.replace('"', '""')
    # PowerShell 里：先 cd，再用 Start-Transcript 抓 stdout，再执行命令；完成后按任意键关闭
    ps_body = (
        f"$Host.UI.RawUI.WindowTitle = '{title}'; "
        f"Start-Transcript -Path '{capture_str}' -Force | Out-Null; "
    )
    if cwd:
        ps_body += f"Set-Location -LiteralPath '{cwd}'; "
    if cwd_warning:
        ps_body += f"Write-Host '{cwd_warning}' -ForegroundColor Yellow; "
    # 关键：watcher 不阻塞等用户关窗口；只等 Stop-Transcript 写完文件就读它
    # 用一个 sentinel 文件标记"CLI 已退出"
    sentinel = capture.with_suffix(".done")
    ps_body += (
        f"Write-Host '[platform] 正在启动 {provider} CLI...' -ForegroundColor Cyan; "
        f"Invoke-Expression \"{rendered_escaped}\"; "
        f"$exit = $LASTEXITCODE; "
        f"Stop-Transcript | Out-Null; "
        f"New-Item -Path '{str(sentinel).replace(chr(39), chr(39)*2)}' -ItemType File -Force | Out-Null; "
        f"Write-Host ''; "
        f"Write-Host '[platform] CLI 已退出 (exit=' -NoNewline -ForegroundColor Cyan; "
        f"Write-Host \"$exit\" -NoNewline -ForegroundColor Yellow; "
        f"Write-Host ')，按 Enter 关闭此窗口（保留窗口随时回看对话）...' -ForegroundColor Cyan; "
        f"$null = Read-Host; "
        f"exit $exit"
    )
    # Start-Process 不带 -Wait：watcher 立刻不阻塞
    full_command = (
        f"powershell.exe -NoProfile -Command "
        f"\"Start-Process -FilePath powershell -ArgumentList "
        f"@('-NoProfile','-Command',\\\"{ps_body.replace(chr(34), chr(34) * 2)}\\\") "
        f"\""
    )
    import subprocess as _sp
    import time as _time
    started_at = _time.time()
    try:
        _sp.run(full_command, shell=True, timeout=10)  # 启动窗口本身只用几秒
    except _sp.TimeoutExpired:
        pass
    # 等 sentinel 文件出现（即 Stop-Transcript 完成）
    while _time.time() - started_at < timeout_seconds:
        if sentinel.exists():
            break
        _time.sleep(0.5)
    rc = 0 if sentinel.exists() else None
    try:
        sentinel.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        stdout = capture.read_text(encoding="utf-8", errors="replace") if capture.exists() else ""
    except Exception:
        stdout = ""
    return {
        "ok": rc == 0,
        "returncode": rc,
        "stdout": stdout,
        "stderr": "" if rc == 0 else f"executor timed out after {timeout_seconds}s (window may still be open)",
        "note": "\n".join(
            part for part in [cwd_warning, stdout or f"{provider} executor completed without stdout."] if part
        ),
        "captured_log_path": str(capture),
    }


def _run_executor_streaming(
    rendered: str,
    *,
    cwd: str | None,
    timeout_seconds: int,
    provider: str,
    cwd_warning: str,
) -> dict[str, Any]:
    """Stream executor stdout/stderr to the current terminal while still capturing
    the full text for the final completion note. Lets the user watching this
    terminal actually see Claude/Codex work in real time."""
    import threading
    import time as _time

    captured_stdout: list[str] = []
    captured_stderr: list[str] = []

    def _pump(stream, sink: list[str], prefix: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                if line == "":
                    break
                sink.append(line)
                sys.stdout.write(f"{prefix}{line}")
                sys.stdout.flush()
        finally:
            try:
                stream.close()
            except Exception:
                pass

    proc = subprocess.Popen(
        rendered,
        shell=True,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    t_out = threading.Thread(target=_pump, args=(proc.stdout, captured_stdout, ""), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, captured_stderr, "[stderr] "), daemon=True)
    t_out.start()
    t_err.start()
    started = _time.time()
    try:
        while proc.poll() is None:
            if _time.time() - started > timeout_seconds:
                proc.kill()
                t_out.join(timeout=2)
                t_err.join(timeout=2)
                stderr = "".join(captured_stderr).strip() or f"executor timed out after {timeout_seconds}s"
                stdout = "".join(captured_stdout).strip()
                return {
                    "ok": False,
                    "returncode": None,
                    "stdout": stdout,
                    "stderr": stderr,
                    "note": "\n".join(
                        part
                        for part in [cwd_warning, f"{provider} executor timed out after {timeout_seconds}s."]
                        if part
                    ),
                }
            _time.sleep(0.1)
    except KeyboardInterrupt:
        proc.kill()
        raise
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    stdout = "".join(captured_stdout).strip()
    stderr = "".join(captured_stderr).strip()
    rc = proc.returncode
    if rc == 0:
        return {
            "ok": True,
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
            "note": "\n".join(
                part for part in [cwd_warning, stdout or f"{provider} executor completed without stdout."] if part
            ),
        }
    return {
        "ok": False,
        "returncode": rc,
        "stdout": stdout,
        "stderr": stderr,
        "note": "\n".join(
            part
            for part in [
                cwd_warning,
                f"{provider} executor failed with exit code {rc}.",
                stdout,
                stderr,
            ]
            if part
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll and reply to AI collaboration platform workstation commands.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workstation-id", required=True)
    parser.add_argument("--runner-id", default=None, help="Bound runner id for multi-computer workstation routing.")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Optional human session token for platform-launched local one-shot execution.",
    )
    parser.add_argument("--status", default=None, help="queued, acked, all; default uses active inbox statuses")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--message-id",
        default=None,
        help="Process only one platform inbox message id. Useful for manual one-shot recovery without touching older backlog.",
    )
    parser.add_argument("--output-dir", default="artifacts/workstation-inbox")
    parser.add_argument("--auto-ack", action="store_true", help="Immediately write a minimal ack for each queued command.")
    parser.add_argument("--ack-note", default=None, help="Custom minimal acknowledgement note to write when --auto-ack is enabled.")
    parser.add_argument("--complete-note", default=None, help="If set, also complete each command with this final reply.")
    parser.add_argument("--failed", action="store_true", help="Use failed status when --complete-note is set.")
    parser.add_argument(
        "--execute-provider-cli",
        action="store_true",
        help="Run the default local CLI executor for the provider and complete with its stdout.",
    )
    parser.add_argument(
        "--ignore-automation-switch",
        action="store_true",
        help="Process inbox commands even when adapter-config reports automation_enabled=false.",
    )
    parser.add_argument(
        "--executor-command",
        default=None,
        help=(
            "Shell command template to run for each inbox item. "
            "Placeholders: @PROMPT_FILE@, @PROMPT_TEXT@, @PROJECT_ID@, @WORKSTATION_ID@, "
            "@PROVIDER@, @MESSAGE_ID@, @MODEL@, @SESSION_ID@, @PROVIDER_EXECUTOR@."
        ),
    )
    parser.add_argument(
        "--executor-cwd",
        default=None,
        help="Local repository path to run the provider CLI from. Each computer chooses its own path.",
    )
    parser.add_argument(
        "--executor-model",
        default=None,
        help="Optional model override for provider CLI execution. Codex falls back to gpt-5.4 on older CLIs.",
    )
    parser.add_argument("--executor-timeout-seconds", type=int, default=None)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Long-running mode: keep polling the workstation inbox and process new commands as they arrive. "
        "Prints 'platform message received / Claude working / reply written' banners + streams CLI stdout to this terminal "
        "so the human watching this thread can see the collaboration happen.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.5,
        help="Seconds to sleep between inbox and Desktop JSONL sync polls when --watch is enabled (default 1.5).",
    )
    parser.add_argument(
        "--spawn-window",
        action="store_true",
        help="Launch each provider CLI invocation in a separate PowerShell window so the user "
             "can watch Claude/Codex talk in its own terminal (Windows only). Otherwise output "
             "streams to the current watcher terminal.",
    )
    parser.add_argument(
        "--persistent-window",
        action="store_true",
        help="(长开模式) watcher 启动时弹一次 claude REPL 长开窗口，后续派单只追加到 inbox 文件——"
             "不再每条派单弹一次，也不再自动写 done 回执。NPC 在窗口里调 MCP read_my_inbox "
             "拉新派单、调 mark_done 显式声明完成。用户可在窗口直接打字与 claude 互动。"
             "和 --spawn-window 互斥；--persistent-window 优先。",
    )
    args = parser.parse_args()

    base = args.api_base.rstrip("/")
    auth_token = str(args.auth_token or os.environ.get("PLATFORM_AUTH_TOKEN") or "").strip() or None
    runner_id = str(args.runner_id or os.environ.get("PLATFORM_RUNNER_ID") or "").strip() or None
    headers = _adapter_headers(args.workstation_id, workstation_token=args.token, auth_token=auth_token, runner_id=runner_id)
    # Step 8 — expose platform identity to child executors so the seat-mcp-server
    # the NPC's CLI loads can dispatch on the seat's behalf (NPC-initiated collab).
    os.environ["PLATFORM_API_BASE"] = base
    os.environ["PLATFORM_PROJECT_ID"] = str(args.project_id or "")
    os.environ["PLATFORM_WORKSTATION_ID"] = str(args.workstation_id or "")
    if runner_id:
        os.environ["PLATFORM_RUNNER_ID"] = runner_id
    # 长开模式：watcher 启动时就把 SEAT_ID 钉到 workstation_id（同一个 seat 一对一），
    # 让弹窗里的 claude 一开就有正确身份；后续每条派单仍会按 recipient_id 覆盖（兼容工位长转交场景）。
    if args.persistent_window and not os.environ.get("PLATFORM_SEAT_ID"):
        os.environ["PLATFORM_SEAT_ID"] = str(args.workstation_id or "")
    if args.token:
        os.environ["PLATFORM_ADAPTER_TOKEN"] = str(args.token)
    if auth_token:
        os.environ["PLATFORM_AUTH_TOKEN"] = auth_token
    adapter_config = _fetch_adapter_config(
        base,
        project_id=args.project_id,
        workstation_id=args.workstation_id,
        headers=headers,
    )
    automation_enabled = bool(adapter_config.get("automation_enabled"))
    if not automation_enabled and not args.ignore_automation_switch:
        result = {
            "project_id": args.project_id,
            "workstation_id": args.workstation_id,
            "automation_enabled": False,
            "automation_mode": adapter_config.get("automation_mode") or "manual",
            "commands": 0,
            "written": [],
            "receipts": [],
            "executions": [],
            "note": "NPC automation is disabled in adapter-config; watcher is in manual mode.",
        }
        if args.watch:
            print("========================================", flush=True)
            print("NPC 自动化未开启", flush=True)
            print(f"项目: {args.project_id}", flush=True)
            print(f"线程: {args.workstation_id}", flush=True)
            print("平台会继续记录派单，但本 watcher 不会自动接单或执行。", flush=True)
            print("如需临时绕过，启动 adapter 时加 --ignore-automation-switch。", flush=True)
            print("========================================", flush=True)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    resolved_provider = (
        str(args.provider or "").strip()
        or str(adapter_config.get("provider_id") or adapter_config.get("provider_label") or "").strip()
        or "generic"
    )
    resolved_provider_key = resolved_provider.strip().lower()
    resolved_computer_node_id = str(adapter_config.get("computer_node_id") or "").strip()
    resolved_workstation_knowledge_path = (
        f"docs/workstations/{resolved_computer_node_id}.md" if resolved_computer_node_id else ""
    )
    resolved_executor_model = (
        str(args.executor_model or "").strip()
        or str(os.environ.get("PLATFORM_EXECUTOR_MODEL") or "").strip()
        or str(adapter_config.get("model") or "").strip()
    )
    if resolved_provider_key == "codex" and (
        not resolved_executor_model or resolved_executor_model.lower() in {"codex", "openai", "default"}
    ):
        resolved_executor_model = "gpt-5.4"
    resolved_executor_command = str(args.executor_command or "").strip() or str(adapter_config.get("executor_command") or "").strip()
    resolved_executor_cwd = str(args.executor_cwd or "").strip() or str(adapter_config.get("executor_cwd") or "").strip() or None
    resolved_timeout = args.executor_timeout_seconds
    if resolved_timeout is None:
        raw_timeout = adapter_config.get("executor_timeout_seconds")
        try:
            resolved_timeout = int(raw_timeout) if raw_timeout not in (None, "") else 1800
        except (TypeError, ValueError):
            resolved_timeout = 1800
    if resolved_timeout <= 0:
        resolved_timeout = 1800
    inbox_url = _workstation_inbox_url(
        base,
        args.project_id,
        args.workstation_id,
        limit=args.limit,
        status=args.status,
        message_id=args.message_id,
    )

    output_base = _normalize_workstation_output_base(Path(args.output_dir), project_id=args.project_id)
    output_root = output_base / _safe_path_component(args.project_id, "project") / _safe_path_component(args.workstation_id, "workstation")
    resolved_session_id = _strip_session_prefix(adapter_config.get("automation_thread_id"), resolved_provider)
    executor_template, executor_mode = _default_executor_template(
        resolved_provider,
        resolved_executor_command,
        args.execute_provider_cli,
        automation_thread_id=adapter_config.get("automation_thread_id"),
        desktop_delivery_mode=adapter_config.get("desktop_delivery_mode"),
    )

    persistent_inbox_path = output_root / "_persistent_inbox.md" if args.persistent_window else None
    persistent_seen_path = output_root / "_persistent_seen.json" if args.persistent_window else None
    seen_ids: set[str] = set()
    if persistent_seen_path is not None and persistent_seen_path.exists():
        try:
            seen_ids = set(json.loads(persistent_seen_path.read_text(encoding="utf-8")) or [])
        except Exception:
            seen_ids = set()

    def _persist_seen() -> None:
        if persistent_seen_path is None:
            return
        try:
            persistent_seen_path.parent.mkdir(parents=True, exist_ok=True)
            persistent_seen_path.write_text(
                json.dumps(sorted(seen_ids)[-500:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[dedupe] 写 {persistent_seen_path} 失败: {exc}", flush=True)

    def sweep_desktop_receipts() -> list[dict[str, Any]]:
        if executor_template != CODEX_DESKTOP_UI_EXECUTOR or not resolved_session_id:
            return []
        sweep_url = f"{_workstation_messages_url(base, args.project_id, args.workstation_id)}/inbox?limit={args.limit}&status=all"
        payload = _json_request("GET", sweep_url, headers=headers)
        candidates = payload.get("data") or []
        receipts: list[dict[str, Any]] = []
        for command in candidates:
            if not isinstance(command, dict):
                continue
            message_id = str(command.get("id") or "").strip()
            status = str(command.get("status") or "").strip().lower()
            if not message_id or status not in {"acked", "in_progress"}:
                continue
            desktop_seen = _codex_desktop_prompt_seen(session_id=resolved_session_id, message_id=message_id)
            if not desktop_seen:
                continue
            desktop_reply = _find_codex_desktop_reply(session_id=resolved_session_id, message_id=message_id)
            final_note = str((desktop_reply or {}).get("text") or "").strip()
            if not final_note:
                continue
            safe_note = _prepare_final_note(
                final_note,
                message_id=message_id,
                result_status="completed",
                output_path=output_root / f"{message_id}.md",
            )
            receipts.append(
                _complete_workstation_command(
                    base=base,
                    project_id=args.project_id,
                    workstation_id=args.workstation_id,
                    message_id=message_id,
                    headers=headers,
                    note=safe_note,
                )
            )
            if args.watch:
                print(f"[桌面回执补偿] 已补回 Desktop final reply：{message_id} 长度={len(final_note)}", flush=True)
        return receipts

    def sync_desktop_followups(candidates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        if executor_template != CODEX_DESKTOP_UI_EXECUTOR or not resolved_session_id:
            return []
        known_message_ids = {
            str(item.get("id") or "").strip()
            for item in (candidates or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        if not known_message_ids:
            sweep_url = f"{_workstation_messages_url(base, args.project_id, args.workstation_id)}/inbox?limit={args.limit}&status=all"
            payload = _json_request("GET", sweep_url, headers=headers)
            known_message_ids = {
                str(item.get("id") or "").strip()
                for item in (payload.get("data") or [])
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
        events = _codex_desktop_followup_events(
            session_id=resolved_session_id,
            known_message_ids=known_message_ids,
            max_events=20,
        )
        synced: list[dict[str, Any]] = []
        linked_message_id = sorted(known_message_ids)[-1] if known_message_ids else None
        for event in events:
            text_value = str(event.get("text") or "").strip()
            if not text_value:
                continue
            if event.get("role") == "assistant":
                # Final answers are completed through the stronger complete endpoint.
                # The sync endpoint keeps quick questions/minimal acks visible.
                if str(event.get("phase") or "") == "final_answer" and len(text_value) > 800:
                    continue
            synced.append(
                _sync_desktop_event(
                    base=base,
                    project_id=args.project_id,
                    workstation_id=args.workstation_id,
                    headers=headers,
                    role=str(event.get("role") or ""),
                    note=text_value[:3900],
                    phase=str(event.get("phase") or ""),
                    session_id=resolved_session_id,
                    source_event_id=str(event.get("event_id") or ""),
                    source_timestamp=str(event.get("timestamp") or ""),
                    linked_message_id=linked_message_id,
                    metadata={"session_file": event.get("session_file")},
                )
            )
        if args.watch and synced:
            print(f"[桌面快速同步] 已同步 {len(synced)} 条 Desktop 提问/最小回执", flush=True)
        return synced

    def process_one_round() -> dict[str, Any]:
        payload = _json_request("GET", inbox_url, headers=headers)
        commands = payload.get("data") or []
        desktop_sync_receipts = sync_desktop_followups(commands)
        swept_receipts = sweep_desktop_receipts()
        if args.message_id:
            wanted_message_id = str(args.message_id).strip()
            commands = [c for c in commands if str(c.get("id") or "").strip() == wanted_message_id]
        written: list[str] = []
        receipts: list[dict[str, Any]] = [*desktop_sync_receipts, *swept_receipts]
        executions: list[dict[str, Any]] = []

        if args.persistent_window:
            fresh = [c for c in commands if _desktop_retry_dedupe_key(c) not in seen_ids]
            if args.watch and commands and not fresh:
                pass
            commands = fresh

        if args.watch and commands:
            print(f"\n[{_now_hms()}] 收到 {len(commands)} 条平台指令", flush=True)

        for command in commands:
            command_path = write_command_file(
                command,
                output_dir=output_root,
                project_id=args.project_id,
                workstation_id=args.workstation_id,
                provider=resolved_provider,
                computer_node_id=resolved_computer_node_id,
                workstation_knowledge_path=resolved_workstation_knowledge_path,
            )
            written.append(str(command_path))
            message_id = str(command.get("id") or "").strip()
            status = str(command.get("status") or "").strip().lower()
            title = str(command.get("title") or "").strip() or "(无标题)"
            body = str(command.get("body") or "").strip()

            if args.watch:
                print("\n========================================", flush=True)
                print(f"[收到平台指令] {title}", flush=True)
                print(f"消息ID: {message_id}", flush=True)
                print(f"线程: {args.workstation_id}  来源: {command.get('sender_type')}/{command.get('sender_id')}", flush=True)
                print("----------------------------------------", flush=True)
                preview = body if len(body) <= 800 else body[:800] + " ...(truncated)"
                print(preview, flush=True)
                print("========================================", flush=True)

            if args.auto_ack and message_id and status in {"queued", "pending"}:
                ack_note = str(args.ack_note or "").strip() or _default_ack_note(
                    provider=resolved_provider,
                    message_id=message_id,
                    command_path=command_path,
                    execute_provider_cli=bool(executor_template),
                    executor_cwd=resolved_executor_cwd,
                )
                ack_receipt = _ack_workstation_command(
                    base=base,
                    project_id=args.project_id,
                    workstation_id=args.workstation_id,
                    message_id=message_id,
                    headers=headers,
                    note=ack_note,
                )
                receipts.append(ack_receipt)
                if ack_receipt.get("already_claimed"):
                    if args.watch:
                        print(f"[跳过旧指令] {message_id} 已被领取或收口，继续监听。", flush=True)
                    continue
                if args.watch:
                    print(f"[已 ack] {ack_note}", flush=True)

            executor_result: dict[str, Any] | None = None
            if args.persistent_window and persistent_inbox_path is not None:
                # 长开模式：不 spawn CLI，只把派单追加到 inbox 文件，让窗口里的 claude 自己拉。
                _append_dispatch_to_inbox(
                    persistent_inbox_path,
                    command,
                    project_id=args.project_id,
                    workstation_id=args.workstation_id,
                    provider=resolved_provider,
                    computer_node_id=resolved_computer_node_id,
                    workstation_knowledge_path=resolved_workstation_knowledge_path,
                )
                if message_id:
                    seen_ids.add(_desktop_retry_dedupe_key(command))
                    _persist_seen()
                # ack 已在上面处理；done 回执由 claude 调 mark_done 写，不在这里写。
                if args.watch:
                    print(
                        f"[长开模式] 已追加到 {persistent_inbox_path}\n"
                        f"  → 让 claude 在窗口里调 `read_my_inbox` 拉这条；处理完调 `mark_done({message_id!r}, body)` 写回执。",
                        flush=True,
                    )
            elif executor_template and message_id:
                desktop_prompt_seen = (
                    _codex_desktop_prompt_seen(session_id=resolved_session_id, message_id=message_id)
                    if executor_template == CODEX_DESKTOP_UI_EXECUTOR
                    else None
                )
                if desktop_prompt_seen:
                    if args.watch:
                        print(
                            f"\n[桌面同步] 该派单已存在于 Codex Desktop session，跳过重复投递：{message_id}\n",
                            flush=True,
                        )
                    executor_result = {
                        "ok": True,
                        "returncode": 0,
                        "stdout": "",
                        "stderr": "",
                        "note": "已检测到该派单已投递到 Codex Desktop，正在同步桌面最终回执。",
                        "delivery_mode": "codex_desktop_ui",
                        "desktop_visible": True,
                        "desktop_delivery_confirmed": True,
                        "desktop_seen": desktop_prompt_seen,
                    }
                else:
                    if args.watch:
                        print(f"\n[正在调用 {resolved_provider} CLI ...]\n", flush=True)
                    # Step 8 — expose THIS message's recipient seat to the seat-mcp-server
                    # so the NPC self-dispatches as itself (sender_id = recipient of this msg).
                    seat_for_msg = str(command.get("recipient_id") or "").strip() or str(args.workstation_id or "")
                    os.environ["PLATFORM_SEAT_ID"] = seat_for_msg
                    executor_result = run_executor(
                        template=executor_template,
                        command_path=command_path,
                        project_id=args.project_id,
                        workstation_id=args.workstation_id,
                        provider=resolved_provider,
                        message_id=message_id,
                        model=resolved_executor_model,
                        session_id=resolved_session_id,
                        cwd=resolved_executor_cwd,
                        timeout_seconds=resolved_timeout,
                        live_output=args.watch,
                        spawn_window=args.spawn_window,
                    )
                executions.append(
                    {
                        "message_id": message_id,
                        "ok": executor_result.get("ok"),
                        "returncode": executor_result.get("returncode"),
                        "delivery_mode": executor_result.get("delivery_mode"),
                        "desktop_visible": executor_result.get("desktop_visible"),
                        "desktop_delivery_confirmed": executor_result.get("desktop_delivery_confirmed"),
                        "desktop_delivery_unconfirmed": executor_result.get("desktop_delivery_unconfirmed"),
                        "desktop_delivery_attempts": executor_result.get("desktop_delivery_attempts"),
                        "stdout_preview": str(executor_result.get("stdout") or "")[:500],
                        "stderr_preview": str(executor_result.get("stderr") or "")[:500],
                    }
                )

            final_note = args.complete_note
            result_failed = args.failed
            if executor_result is not None:
                final_note = str(executor_result.get("note") or "").strip()
                result_failed = not bool(executor_result.get("ok"))
                if (
                    executor_result.get("delivery_mode") == "codex_desktop_ui"
                    and executor_result.get("desktop_delivery_confirmed") is False
                    and executor_result.get("recoverable")
                ):
                    final_note = ""
                    result_failed = False
                    progress_note = (
                        "桌面线程暂未确认收到这条派单。可能是窗口焦点被打断，平台已保留任务，"
                        "可点击“重新同步”“延长等待”或在确认桌面结果后“手动收口”。"
                    )
                    try:
                        progress_receipt = _post_workstation_progress(
                            base=base,
                            project_id=args.project_id,
                            workstation_id=args.workstation_id,
                            message_id=message_id,
                            headers=headers,
                            note=progress_note,
                            state="desktop_delivery_unconfirmed",
                            metadata={
                                "delivery_mode": "codex_desktop_ui",
                                "desktop_visible": True,
                                "desktop_delivery_confirmed": False,
                                "desktop_delivery_unconfirmed": True,
                                "desktop_delivery_attempts": executor_result.get("desktop_delivery_attempts"),
                                "desktop_delivery_auto_retried": executor_result.get("desktop_delivery_auto_retried"),
                                "desktop_closeout_waiting": True,
                                "desktop_sync_retry_available": True,
                                "desktop_thread_url": executor_result.get("desktop_thread_url"),
                                "thread_id": executor_result.get("thread_id"),
                                "blocked_taxonomy": {
                                    "failed": False,
                                    "timed_out": True,
                                    "auto_closed": False,
                                    "retryable": True,
                                    "log_available": False,
                                    "split_suggested": False,
                                    "exception_kind": "desktop_delivery_unconfirmed",
                                    "blocked_reason_code": "desktop_delivery_unconfirmed",
                                    "blocked_reason_label": "桌面线程暂未确认收到，可重新同步",
                                    "evidence_complete": False,
                                    "platform_defect": False,
                                    "nudge_required": True,
                                    "wait_extension_available": True,
                                    "desktop_sync_retry_available": True,
                                    "manual_close_required": True,
                                    "desktop_closeout_waiting": True,
                                    "desktop_delivery_attempts": executor_result.get("desktop_delivery_attempts"),
                                    "desktop_delivery_auto_retried": executor_result.get("desktop_delivery_auto_retried"),
                                },
                            },
                        )
                        receipts.append(progress_receipt)
                        if args.watch:
                            print("[桌面投递] 未确认收到，已保持待收口并提供重新同步。", flush=True)
                    except Exception as exc:
                        if args.watch:
                            print(f"[桌面投递] 写入未确认进度失败：{exc}", flush=True)
                elif executor_result.get("delivery_mode") == "codex_desktop_ui" and executor_result.get("ok"):
                    # Desktop UI delivery only submits the prompt into the visible Codex thread.
                    # The real work happens in Desktop. Wait for the bound session jsonl to
                    # receive an assistant reply, then project that final answer back to the
                    # platform as a compact receipt. This keeps the full process in Desktop
                    # without pretending delivery itself is completion.
                    final_note = ""
                    result_failed = False
                    progress_note = (
                        "已把这条派单送进绑定桌面线程；完整处理过程在桌面版继续。"
                        "平台正在等待桌面线程写出最终回复。"
                    )
                    try:
                        progress_receipt = _post_workstation_progress(
                            base=base,
                            project_id=args.project_id,
                            workstation_id=args.workstation_id,
                            message_id=message_id,
                            headers=headers,
                            note=progress_note,
                            state="awaiting_desktop_reply",
                            metadata={
                                "delivery_mode": "codex_desktop_ui",
                                "desktop_visible": True,
                                "desktop_delivery_confirmed": True,
                                "desktop_delivery_attempts": executor_result.get("desktop_delivery_attempts"),
                                "desktop_delivery_auto_retried": executor_result.get("desktop_delivery_auto_retried"),
                                "desktop_thread_url": executor_result.get("desktop_thread_url"),
                                "thread_id": executor_result.get("thread_id"),
                                "session_file": (
                                    executor_result.get("desktop_seen", {}).get("session_file")
                                    if isinstance(executor_result.get("desktop_seen"), dict)
                                    else None
                                ),
                            },
                        )
                        receipts.append(progress_receipt)
                        if args.watch:
                            print("[桌面投递] 已向平台写入等待 Desktop 最终回复的进度。", flush=True)
                    except Exception as exc:
                        if args.watch:
                            print(f"[桌面投递] 写入 progress 失败：{exc}", flush=True)
                    desktop_reply = _wait_for_codex_desktop_reply(
                        session_id=resolved_session_id,
                        message_id=message_id,
                        timeout_seconds=min(max(resolved_timeout, 1), 1800),
                    )
                    if desktop_reply:
                        final_note = str(desktop_reply.get("text") or "").strip()
                        if args.watch:
                            print(
                                f"[桌面回执同步] 已读取 Codex Desktop 回复，长度={len(final_note)}",
                                flush=True,
                            )
                    elif args.watch:
                        print(
                            "[桌面回执同步] 已完成桌面投递，但等待 Desktop 最终回复超时；"
                            "平台保留 in_progress，稍后可再次运行 adapter 同步。",
                            flush=True,
                        )
            if final_note and message_id:
                final_status = "failed" if result_failed else "completed"
                for peer_payload in _extract_peer_dispatches(final_note):
                    peer_dispatch = _create_peer_dispatch(
                        base=base,
                        project_id=args.project_id,
                        sender_seat_id=args.workstation_id,
                        headers=headers,
                        payload=peer_payload,
                        source_message_id=message_id,
                        root_message_id=_root_message_id_for_child_dispatch(command),
                    )
                    if peer_dispatch:
                        receipts.append(peer_dispatch)
                        peer_status = str(peer_dispatch.get("status") or "").strip().lower()
                        peer_target = str(peer_dispatch.get("recipient_id") or "").strip()
                        if peer_status == "queued" and peer_target:
                            launch_receipt = _launch_peer_dispatch_adapter(
                                base=base,
                                project_id=args.project_id,
                                target_workstation_id=peer_target,
                                message_id=str(peer_dispatch.get("id") or ""),
                                auth_token=auth_token,
                                output_dir=output_root,
                                timeout_seconds=resolved_timeout,
                            )
                            receipts.append({"peer_dispatch_launch": launch_receipt})
                            if args.watch:
                                print(
                                    f"[自主协作] 已自动启动下游 NPC: {peer_target} "
                                    f"message={peer_dispatch.get('id')} launched={launch_receipt.get('launched')}",
                                    flush=True,
                                )
                        elif args.watch and peer_status == "pending_review":
                            print(
                                f"[自主协作] 下游派单待审，未自动启动: {peer_dispatch.get('id')} -> {peer_target}",
                                flush=True,
                            )
                        if args.watch:
                            print(
                                f"[自主协作] 已创建 peer dispatch: {peer_dispatch.get('id')} -> {peer_dispatch.get('recipient_id')}",
                                flush=True,
                            )
                receipts.append(
                    _complete_workstation_command(
                        base=base,
                        project_id=args.project_id,
                        workstation_id=args.workstation_id,
                        message_id=message_id,
                        headers=headers,
                        result_status=final_status,
                        note=_prepare_final_note(
                            final_note,
                            message_id=message_id,
                            result_status=final_status,
                            output_path=command_path,
                        ),
                    )
                )
                if args.watch:
                    print(f"\n[已回写平台] status={final_status} note 长度={len(final_note)}", flush=True)
                    print("等待下一条平台指令...\n", flush=True)

        return {
            "project_id": args.project_id,
            "workstation_id": args.workstation_id,
            "provider": resolved_provider,
            "adapter_config": adapter_config,
            "executor_mode": executor_mode,
            "session_id": resolved_session_id,
            "commands": len(commands),
            "written": written,
            "receipts": receipts,
            "executions": executions,
        }

    if args.watch:
        print("========================================", flush=True)
        print(f"线程 watcher 已启动", flush=True)
        print(f"项目: {args.project_id}", flush=True)
        print(f"线程: {args.workstation_id}", flush=True)
        print(f"提供商: {resolved_provider}", flush=True)
        print(f"执行模式: {executor_mode}  会话: {resolved_session_id or '<none>'}", flush=True)
        print(f"轮询: 每 {args.poll_seconds}s 一次  执行目录: {resolved_executor_cwd or '(adapter 启动目录)'}", flush=True)
        print(f"API: {base}", flush=True)
        if args.persistent_window and persistent_inbox_path is not None:
            print(f"模式: 长开窗口（PersistentWindow）", flush=True)
            print(f"派单 inbox: {persistent_inbox_path}", flush=True)
            print(f"  watcher 不会 spawn CLI；新派单会追加到 inbox 文件。", flush=True)
            print(f"  在弹出的 claude 窗口里调 read_my_inbox / mark_done 处理。", flush=True)
        elif args.spawn_window:
            print(f"模式: 一次性弹窗（每条派单弹一次）", flush=True)
        print("========================================", flush=True)
        if args.persistent_window and persistent_inbox_path is not None:
            # 解析 seat 的绑定 session（claude --resume 用）
            bind = _resolve_bound_session(
                base=base,
                project_id=str(args.project_id),
                workstation_id=str(args.workstation_id),
                headers=headers,
            )
            seat_for_window = str(os.environ.get("PLATFORM_SEAT_ID") or "").strip() or str(args.workstation_id or "")
            seat_name = bind.get("seat_name") or str(args.workstation_id or "")
            session_id = bind.get("session_id")
            bind_provider = bind.get("provider") or resolved_provider
            bind_cwd = bind.get("cwd") or resolved_executor_cwd
            bind_error = bind.get("error") or ""
            if not bind_error and not session_id:
                bind_error = (
                    f"seat config_id 不是 claude-session-<uuid> 或 codex-session-<uuid> 形式，"
                    f"也没在 extra_data 里发现 session_id（这通常是手动建的逻辑工位，未做线程绑定）"
                )
            print(f"[{_now_hms()}] [platform] bind: session={(session_id or '')[:8] or '<none>'} provider={bind_provider} cwd={bind_cwd or '<none>'}{' bind_error=' + bind_error if bind_error else ''}", flush=True)
            short_sid = (session_id or "")[:8]
            window_title = (
                f"NPC {seat_name} · {bind_provider}"
                + (f" · session={short_sid}" if short_sid else "")
            )
            _open_persistent_window(
                provider=bind_provider,
                cwd=bind_cwd,
                title=window_title,
                inbox_md_path=persistent_inbox_path,
                project_id=str(args.project_id),
                workstation_id=str(args.workstation_id),
                seat_id=seat_for_window,
                session_id=session_id,
                seat_name=seat_name,
                bind_error=bind_error,
            )
        print("等待平台指令... (Ctrl+C 退出)\n", flush=True)
        try:
            while True:
                try:
                    process_one_round()
                except Exception as exc:
                    print(f"[轮询错误] {exc}", flush=True)
                time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            print("\n[watcher 已退出]", flush=True)
            return 0

    result = process_one_round()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
