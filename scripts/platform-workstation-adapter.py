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
    lines = [
        f"# {title}",
        "",
        "## Platform Envelope",
        f"- project_id: `{project_id}`",
        f"- workstation_id: `{workstation_id}`",
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
    for line in command_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break
    instruction = command_text
    marker = "## User Instruction"
    if marker in command_text:
        instruction = command_text.split(marker, 1)[1].strip()
    parts = [
        "你是当前电脑线程上的执行 AI。",
        "平台适配器已经负责最小回执和最终回写；不要再调用平台 API，也不要尝试自己发送回执。",
        "开工前如果存在 docs/ai-requirements/ai-required-requirements-ledger.md，必须遵守其中的提需求者、被提需求者、人工审核边界、一次性/心跳模式和完成后回给谁。",
        "凡是标记为需要人工审核的内容，只能分析和说明，不能继续自动执行。",
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
    args = parser.parse_args()

    base = args.api_base.rstrip("/")
    auth_token = str(args.auth_token or os.environ.get("PLATFORM_AUTH_TOKEN") or "").strip() or None
    headers = _adapter_headers(args.workstation_id, workstation_token=args.token, auth_token=auth_token)
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
            if executor_template and message_id:
                if args.watch:
                    print(f"\n[正在调用 {resolved_provider} CLI ...]\n", flush=True)
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
        print("========================================", flush=True)
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
