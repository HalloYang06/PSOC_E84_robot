#!/usr/bin/env python
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_SYSTEM_PROMPT = (
    "你是 AI 协作平台里的线程执行器。"
    "根据平台命令生成一条可以直接回写到最终回复池的中文最终回复。"
    "开工前遵守 docs/ai-requirements/ai-required-requirements-ledger.md 的需求表和人工审核边界。"
    "默认只能做阅读、分析、总结、审查类工作；禁止修改文件、删除文件、安装软件、提交代码或执行会产生副作用的操作。"
    "只输出最终回复正文，不要解释过程，不要使用 markdown 代码块。"
    "输出必须以“最终回复：”开头，内容尽量简洁、具体、可交付。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a platform workstation command through a real provider CLI.")
    parser.add_argument("prompt_file", help="Markdown prompt file written by the workstation adapter.")
    parser.add_argument("--provider", required=True, choices=["claude", "codex", "qwen"])
    parser.add_argument("--message-id", default="")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--workstation-id", default="")
    parser.add_argument("--cwd", default=None, help="Optional safe working directory for the provider process.")
    parser.add_argument("--model", default=None, help="Optional provider model override. Codex defaults to gpt-5.4 for older CLIs.")
    return parser.parse_args()


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_platform_command(prompt_text: str) -> tuple[str, str]:
    text = prompt_text.strip()
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "平台协作任务"
    instruction_match = re.search(r"##\s+User Instruction\s*(.*)$", text, re.DOTALL)
    instruction = instruction_match.group(1).strip() if instruction_match else text
    return title, instruction


def _compose_prompt(prompt_text: str, *, message_id: str) -> str:
    title, instruction = _extract_platform_command(prompt_text)
    prefix = (
        "请根据下面的平台协作任务，直接产出一条给用户看的最终回复。"
        "开工前如果存在 docs/ai-requirements/ai-required-requirements-ledger.md，必须先遵守其中的提需求者、被提需求者、人工审核边界、一次性/心跳模式和完成后回给谁。"
        "不要复述平台 envelope，不要列环境信息，不要解释过程，不要说你已经收到任务。"
        "除非任务正文明确要求且人类已经批准，否则只允许阅读、分析、总结、审查，不允许改文件或执行有副作用的动作。"
        "如果任务正文要求先最小回执再最终回复，这里只负责最终回复。"
        "输出必须只有一句中文，以“最终回复：”开头，尽量控制在 80 个汉字以内。"
    )
    if message_id.strip():
        prefix += f" 当前 message_id={message_id.strip()}。"
    return f"{prefix}\n\n任务标题：{title}\n任务正文：{instruction}\n"


def _ensure_cli_available(name: str) -> str:
    candidates = [name]
    if sys.platform.startswith("win"):
        candidates = [f"{name}.cmd", name]
    binary = ""
    for candidate in candidates:
        binary = shutil.which(candidate) or ""
        if binary:
            break
    if not binary:
        raise RuntimeError(f"{name} CLI is not available on PATH")
    return binary


def _run_subprocess(command: list[str], *, input_text: str, cwd: str | None, timeout_seconds: int = 300) -> subprocess.CompletedProcess[str]:
    command_to_run: list[str] | str = command
    if sys.platform.startswith("win") and command and str(command[0]).lower().endswith(".cmd"):
        command_to_run = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
    return subprocess.run(
        command_to_run,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or None,
        timeout=timeout_seconds,
    )


def _run_claude(prompt: str, *, cwd: str | None) -> str:
    binary = _ensure_cli_available("claude")
    completed = _run_subprocess(
        [
            binary,
            "--print",
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "text",
            "--no-session-persistence",
        ],
        input_text=prompt,
        cwd=cwd,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"claude CLI failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}")
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("claude CLI returned empty stdout")
    return output


def _resolve_codex_model(model: str | None) -> str:
    raw = str(model or "").strip()
    if not raw or raw.lower() in {"codex", "openai", "default"}:
        return "gpt-5.4"
    return raw


def _run_codex(prompt: str, *, cwd: str | None, model: str | None) -> str:
    binary = _ensure_cli_available("codex")
    resolved_model = _resolve_codex_model(model)
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False, encoding="utf-8") as handle:
        output_path = Path(handle.name)
    try:
        completed = _run_subprocess(
            [
                binary,
                "exec",
                "-m",
                resolved_model,
                "--skip-git-repo-check",
                "--ephemeral",
                "--output-last-message",
                str(output_path),
                "-",
            ],
            input_text=prompt,
            cwd=cwd,
            timeout_seconds=420,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"codex CLI failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}")
        output = output_path.read_text(encoding="utf-8", errors="replace").strip() if output_path.exists() else ""
        if not output:
            output = completed.stdout.strip()
        if not output:
            raise RuntimeError("codex CLI returned empty output")
        return output
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


def _run_qwen(prompt: str, *, cwd: str | None) -> str:
    binary = _ensure_cli_available("qwen")
    completed = _run_subprocess(
        [
            binary,
            "--output-format",
            "text",
            "--approval-mode",
            "yolo",
        ],
        input_text=prompt,
        cwd=cwd,
        timeout_seconds=420,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"qwen CLI failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}")
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("qwen CLI returned empty stdout")
    return output


def _normalize_final_reply(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise RuntimeError("provider output was empty after trimming")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if "最终回复：" in cleaned:
        cleaned = cleaned[cleaned.index("最终回复：") :].strip()
    else:
        cleaned = f"最终回复：{cleaned}"
    return cleaned


def main() -> int:
    args = parse_args()
    prompt_path = Path(args.prompt_file)
    prompt_text = _read_prompt(prompt_path)
    final_prompt = f"{DEFAULT_SYSTEM_PROMPT}\n\n{_compose_prompt(prompt_text, message_id=args.message_id)}"

    provider = args.provider.strip().lower()
    if provider == "claude":
        output = _run_claude(final_prompt, cwd=args.cwd)
    elif provider == "codex":
        output = _run_codex(final_prompt, cwd=args.cwd, model=args.model)
    elif provider == "qwen":
        output = _run_qwen(final_prompt, cwd=args.cwd)
    else:
        raise RuntimeError(f"Unsupported provider: {provider}")

    print(_normalize_final_reply(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
