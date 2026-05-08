#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request, error
from urllib.parse import quote


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


DEFAULT_API_BASE = "http://127.0.0.1:8010"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_PROVIDER_EXECUTORS = {
    "claude": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@",
    "qwen": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@",
    "codex": "python @PROVIDER_EXECUTOR@ @PROMPT_FILE@ --provider @PROVIDER@ --message-id @MESSAGE_ID@ --project-id @PROJECT_ID@ --workstation-id @WORKSTATION_ID@ --model @MODEL@",
}


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


def _message_action_url(base: str, project_id: str, workstation_id: str, message_id: str, action: str) -> str:
    encoded_message_id = quote(message_id, safe="")
    return f"{_workstation_messages_url(base, project_id, workstation_id)}/messages/{encoded_message_id}/{action}"


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


def _headers(workstation_id: str, token: str | None = None) -> dict[str, str]:
    encoded, was_encoded = _encode_header_value(workstation_id)
    headers = {"X-Workstation-Id": encoded}
    if was_encoded:
        headers["X-Workstation-Id-Encoding"] = "percent"
    if token:
        headers["X-Workstation-Token"] = token
    return headers


def _adapter_headers(workstation_id: str, *, workstation_token: str | None = None, auth_token: str | None = None) -> dict[str, str]:
    # Real remote adapters identify as a workstation. A platform-launched one-shot can instead
    # use the current human session, so it does not rotate or invalidate a remote adapter token.
    if auth_token and not workstation_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return _headers(workstation_id, workstation_token)


def _command_markdown(command: dict[str, Any], *, project_id: str, workstation_id: str, provider: str) -> str:
    title = str(command.get("title") or "Untitled platform command").strip()
    body = str(command.get("body") or "").strip()
    recipient_id = str(command.get("recipient_id") or "").strip()
    seat_id = recipient_id if recipient_id and recipient_id != workstation_id else ""
    lines = [
        f"# {title}",
        "",
        "## Platform Envelope",
        f"- project_id: `{project_id}`",
        f"- workstation_id: `{workstation_id}`",
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
        "## NPC Knowledge Library Convention",
        f"- Your role manual lives at `docs/npcs/{seat_id or workstation_id}/` (create if missing — see `docs/npcs/README.md`).",
        f"- Workstation context: `docs/workstations/{workstation_id}.md`.",
        "- Project context: `docs/projects/<project-id>/README.md`.",
        "- Read all three before acting; cite the file path you relied on in your reply.",
        "",
        "## Autonomous Collaboration (seat-mcp tools)",
        "- 你的 CLI 应该已经加载了 `seat-mcp` 这个 MCP server（见 `scripts/seat-mcp-server/README.md`）。",
        "- 当你工作中需要别的 NPC（例如代码审核、前端联调、文档撰写），**不要叫用户去派单**，直接调以下工具：",
        "  - `list_peers()`：看你能调动的伙伴（含同工位 / 跨工位 / 工位长）。",
        "  - `request_help(role, ask, expected?)`：按角色关键字找伙伴并自动发起派单。",
        "  - `dispatch_to_peer(seat_id, title, body)`：知道具体 seat_id 时直接指名派单。",
        "  - `read_my_inbox(limit?)`：自查我的协作流——别人派给我的派单 / 别人对我派单的 ack/done/reject 回执 / 我自己发出的派单状态。**在做事之前先调一次，可以确认上下文、避免重复劳动；卡住时再调一次确认对方回了没。**",
        "  - `mark_done(message_id, body, failed?)`：**仅长开窗口模式（PersistentWindow）使用**——处理完一条 incoming_dispatch 后调一次，写 done 回执。一次性弹窗模式不用调（watcher 自动写）。",
        "- 五个工具都会经过平台 review gate：同工位默认免审；跨工位默认 pending_review，由用户在驾驶舱通过后才真发出。",
        "- 工具返回 `needs_review=true` 时，你**只需告诉用户「已发起求助，等审核」**，不要重复发也不要切换到自己干。",
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


def write_command_file(command: dict[str, Any], *, output_dir: Path, project_id: str, workstation_id: str, provider: str) -> Path:
    message_id = str(command.get("id") or "message").strip()
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in message_id) or "message"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_id}.md"
    path.write_text(
        _command_markdown(command, project_id=project_id, workstation_id=workstation_id, provider=provider),
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
    local_prompt = str(command_path.resolve())
    cwd_note = str(executor_cwd or "").strip() or "not configured; this runner will only write the prompt file"
    cli_note = "on" if execute_provider_cli else "off"
    return "\n".join(
        [
            f"{provider} adapter accepted command {message_id}.",
            f"Local prompt file: {local_prompt}",
            f"Provider CLI execution: {cli_note}",
            f"Executor cwd: {cwd_note}",
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


def _extract_executor_prompt(command_text: str) -> str:
    """Keep platform routing out of the provider prompt; the adapter handles ack/final receipts."""
    title = ""
    seat_id = ""
    workstation_id = ""
    for line in command_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped.lstrip("#").strip()
        elif stripped.startswith("- seat_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            seat_id = after.strip().strip("`").split()[0] if after.strip() else ""
        elif stripped.startswith("- workstation_id"):
            after = stripped.split(":", 1)[1] if ":" in stripped else ""
            workstation_id = after.strip().strip("`").split()[0] if after.strip() else ""
    instruction = command_text
    marker = "## User Instruction"
    if marker in command_text:
        instruction = command_text.split(marker, 1)[1].strip()
    seat_label = seat_id or workstation_id or "<seat>"
    workstation_label = workstation_id or "<workstation>"
    parts = [
        "你是当前电脑线程上的执行 AI。",
        "平台适配器已经负责最小回执和最终回写；不要再调用平台 API，也不要尝试自己发送回执。",
        "开工前如果存在 docs/ai-requirements/ai-required-requirements-ledger.md，必须遵守其中的提需求者、被提需求者、人工审核边界、一次性/心跳模式和完成后回给谁。",
        "凡是标记为需要人工审核的内容，只能分析和说明，不能继续自动执行。",
        (
            "你这个 NPC 的「岗位手册」在 docs/npcs/" + seat_label + "/ 下；"
            "本工位（电脑节点）的手册在 docs/workstations/" + workstation_label + ".md；"
            "项目级背景在 docs/projects/<project-id>/README.md。"
            "开工前先读这三处（任何一处缺失就跳过该层），并在最终回复里注明你引用了哪份文档。"
        ),
        (
            "回复必须用 GitHub-flavored Markdown。引用代码/提交/PR 时一律给出 GitHub 链接（owner/repo/blob/branch/path 或 /commit/<sha>），"
            "用当前仓库真实的 remote，不要编造占位 URL。如果改了文件，按「- 修改 <文件名>：<一句话原因> — <github 链接>」列清单。"
        ),
        (
            "需要其他 NPC 帮忙时，直接调 MCP 工具 `list_peers` / `request_help(role, ask)` / `dispatch_to_peer(seat_id, title, body)` "
            "（来自 seat-mcp server）。同工位默认免审、跨工位默认走 pending_review。不要让用户去 UI 上替你派单——这就是平台说的「自主协作」。"
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
        "@PROVIDER_EXECUTOR@": _shell_arg(str(provider_executor)),
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    return rendered


def run_executor(
    *,
    template: str,
    command_path: Path,
    project_id: str,
    workstation_id: str,
    provider: str,
    message_id: str,
    model: str | None,
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
        # 历史教训（5-08 撞 4 次）：
        # - npm 的 claude.ps1 shim 内部 `& "$basedir/.../claude.exe"` 因为路径含 `@`，PS 5.1 + 7 **都**崩
        #   （5.1 报 ApplicationFailedException，7 报 CommandNotFoundException —— 都是 `& "..."` 字符串路径
        #   被 PS parser 错误处理）
        # - 任何让 ps1 调 npm shim 的方式（`& $shim` / 裸 `claude` / `cmd /c $shim`）都会进到这条 `& "..."` 崩
        # - 真解 = **绕过 shim，让 ps1 用 Start-Process 直接调真实 .exe**
        #   Start-Process 走 Windows CreateProcess，不经过 PS string parser，含 @ 的路径完全不受影响
        #
        # Start-Process 路径解析：在 ps1 里查 npm 全局 prefix，拼 node_modules/@anthropic-ai/claude-code/bin/claude.exe
        # 这是 npm 标准布局，每台正确 npm i -g 的机器都一样。
        ps_body += (
            f"Write-Host ''; "
            f"Write-Host '[platform] window ready — workspace cwd is set, env is injected.' -ForegroundColor Green; "
            f"$npmBin = Join-Path $env:APPDATA 'npm'; "
            f"if (Test-Path -LiteralPath $npmBin) {{ $env:PATH = $npmBin + ';' + $env:PATH }}; "
            f"$candidates = @(); "
            f"if ($env:CLAUDE_CODE_EXECPATH) {{ $candidates += $env:CLAUDE_CODE_EXECPATH }}; "
            f"$shimSrc = (Get-Command {repl_cmd} -ErrorAction SilentlyContinue).Source; "
            f"if ($shimSrc) {{ "
            f"  $shimDir = Split-Path -Parent $shimSrc; "
            f"  $candidates += (Join-Path $shimDir 'node_modules\\@anthropic-ai\\claude-code\\bin\\{repl_cmd}.exe'); "
            f"}}; "
            f"$candidates += (Join-Path $env:APPDATA 'npm\\node_modules\\@anthropic-ai\\claude-code\\bin\\{repl_cmd}.exe'); "
            f"$candidates += ('C:\\Users\\' + $env:USERNAME + '\\AppData\\Roaming\\npm\\node_modules\\@anthropic-ai\\claude-code\\bin\\{repl_cmd}.exe'); "
            f"$exePath = $null; "
            f"foreach ($c in $candidates) {{ if ($c -and (Test-Path -LiteralPath $c)) {{ $exePath = $c; break }} }}; "
            f"if (-not $exePath) {{ "
            f"  Write-Host '[platform] WARNING: {repl_cmd}.exe not found. Tried:' -ForegroundColor Red; "
            f"  $candidates | ForEach-Object {{ Write-Host ('  - ' + $_) -ForegroundColor Red }}; "
            f"  Write-Host '[platform] Install: npm i -g @anthropic-ai/claude-code' -ForegroundColor Yellow; "
            f"}} else {{ "
            f"  Write-Host ('[platform] launching ' + $exePath) -ForegroundColor Cyan; "
            f"  Write-Host '[platform] inside the REPL, slash-resume to pick a previous session for history.' -ForegroundColor Gray; "
            f"  Write-Host ''; "
            f"  Start-Process -FilePath $exePath -NoNewWindow -Wait; "
            f"  Write-Host ''; "
            f"  Write-Host ('[platform] {repl_cmd} REPL exited (code=' + $LASTEXITCODE + ')') -ForegroundColor Yellow; "
            f"}}; "
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
        print(f"[{_now_hms()}] [platform] persistent {provider} REPL window spawned via {shell_label} (ps1={ps1})", flush=True)
        if shell_label == "powershell5.1":
            print(f"[{_now_hms()}] [platform] HINT: install PowerShell 7 to enable auto-launch of {provider} inside the window:", flush=True)
            print(f"[{_now_hms()}] [platform]   winget install --id Microsoft.PowerShell --source winget", flush=True)
    except Exception as exc:
        print(f"[{_now_hms()}] [platform] window spawn failed: {exc}", flush=True)


def _append_dispatch_to_inbox(inbox_md_path: Path, command: dict[str, Any], *, project_id: str, workstation_id: str, provider: str) -> None:
    """长开模式下把派单追加到 markdown inbox 文件，给窗口里的 claude 看。"""
    inbox_md_path.parent.mkdir(parents=True, exist_ok=True)
    block = _command_markdown(command, project_id=project_id, workstation_id=workstation_id, provider=provider)
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
    parser.add_argument("--provider", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Optional human session token for platform-launched local one-shot execution.",
    )
    parser.add_argument("--status", default=None, help="queued, acked, all; default uses active inbox statuses")
    parser.add_argument("--limit", type=int, default=10)
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
        "--executor-command",
        default=None,
        help=(
            "Shell command template to run for each inbox item. "
            "Placeholders: @PROMPT_FILE@, @PROMPT_TEXT@, @PROJECT_ID@, @WORKSTATION_ID@, "
            "@PROVIDER@, @MESSAGE_ID@, @MODEL@, @PROVIDER_EXECUTOR@."
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
        default=3.0,
        help="Seconds to sleep between inbox polls when --watch is enabled (default 3).",
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
    headers = _adapter_headers(args.workstation_id, workstation_token=args.token, auth_token=auth_token)
    # Step 8 — expose platform identity to child executors so the seat-mcp-server
    # the NPC's CLI loads can dispatch on the seat's behalf (NPC-initiated collab).
    os.environ["PLATFORM_API_BASE"] = base
    os.environ["PLATFORM_PROJECT_ID"] = str(args.project_id or "")
    os.environ["PLATFORM_WORKSTATION_ID"] = str(args.workstation_id or "")
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
    resolved_provider = (
        str(args.provider or "").strip()
        or str(adapter_config.get("provider_id") or adapter_config.get("provider_label") or "").strip()
        or "generic"
    )
    resolved_provider_key = resolved_provider.strip().lower()
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
    inbox_url = f"{_workstation_messages_url(base, args.project_id, args.workstation_id)}/inbox?limit={args.limit}"
    if args.status:
        inbox_url += f"&status={args.status}"

    output_root = Path(args.output_dir) / _safe_path_component(args.project_id, "project") / _safe_path_component(args.workstation_id, "workstation")
    executor_template = _executor_template(
        resolved_provider,
        resolved_executor_command,
        args.execute_provider_cli,
    )

    persistent_inbox_path = output_root / "_persistent_inbox.md" if args.persistent_window else None

    def process_one_round() -> dict[str, Any]:
        payload = _json_request("GET", inbox_url, headers=headers)
        commands = payload.get("data") or []
        written: list[str] = []
        receipts: list[dict[str, Any]] = []
        executions: list[dict[str, Any]] = []

        if args.watch and commands:
            print(f"\n[{_now_hms()}] 收到 {len(commands)} 条平台指令", flush=True)

        for command in commands:
            command_path = write_command_file(
                command,
                output_dir=output_root,
                project_id=args.project_id,
                workstation_id=args.workstation_id,
                provider=resolved_provider,
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
                ack_url = _message_action_url(base, args.project_id, args.workstation_id, message_id, "ack")
                ack_note = str(args.ack_note or "").strip() or _default_ack_note(
                    provider=resolved_provider,
                    message_id=message_id,
                    command_path=command_path,
                    execute_provider_cli=bool(executor_template),
                    executor_cwd=resolved_executor_cwd,
                )
                receipts.append(_json_request("POST", ack_url, headers=headers, payload={"note": ack_note}).get("data") or {})
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
                )
                # ack 已在上面处理；done 回执由 claude 调 mark_done 写，不在这里写。
                if args.watch:
                    print(
                        f"[长开模式] 已追加到 {persistent_inbox_path}\n"
                        f"  → 让 claude 在窗口里调 `read_my_inbox` 拉这条；处理完调 `mark_done({message_id!r}, body)` 写回执。",
                        flush=True,
                    )
            elif executor_template and message_id:
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
                        "stdout_preview": str(executor_result.get("stdout") or "")[:500],
                        "stderr_preview": str(executor_result.get("stderr") or "")[:500],
                    }
                )

            final_note = args.complete_note
            result_failed = args.failed
            if executor_result is not None:
                final_note = str(executor_result.get("note") or "").strip()
                result_failed = not bool(executor_result.get("ok"))
            if final_note and message_id:
                complete_url = _message_action_url(base, args.project_id, args.workstation_id, message_id, "complete")
                receipts.append(
                    _json_request(
                        "POST",
                        complete_url,
                        headers=headers,
                        payload={
                            "result_status": "failed" if result_failed else "completed",
                            "note": final_note,
                        },
                    ).get("data")
                    or {}
                )
                if args.watch:
                    final_status = "failed" if result_failed else "completed"
                    print(f"\n[已回写平台] status={final_status} note 长度={len(final_note)}", flush=True)
                    print("等待下一条平台指令...\n", flush=True)

        return {
            "project_id": args.project_id,
            "workstation_id": args.workstation_id,
            "provider": resolved_provider,
            "adapter_config": adapter_config,
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
