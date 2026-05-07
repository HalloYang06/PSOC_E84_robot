#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_RESULT = "最终回复：多电脑多 AI 协作平台先统一派工，再由线程回写最小回执和最终结果，能明显减少来回催办。"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a deterministic final reply for workstation adapter smoke/acceptance flows.",
    )
    parser.add_argument("prompt_file", help="Markdown prompt file written by the workstation adapter.")
    parser.add_argument("--provider", default="generic")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--result", default="")
    return parser.parse_args()


def build_reply(prompt_text: str, *, provider: str, message_id: str, forced_result: str = "") -> str:
    if forced_result.strip():
        return forced_result.strip()
    cleaned = prompt_text.strip()
    if "协作写作" in cleaned:
        return DEFAULT_RESULT
    if "最终回复" in cleaned:
        return DEFAULT_RESULT
    provider_label = provider.strip() or "generic"
    message_label = message_id.strip() or "unknown-message"
    return f"最终回复：{provider_label} 适配器已执行并回写结果，message_id={message_label}。"


def main() -> int:
    args = parse_args()
    prompt_path = Path(args.prompt_file)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    print(build_reply(prompt_text, provider=args.provider, message_id=args.message_id, forced_result=args.result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
