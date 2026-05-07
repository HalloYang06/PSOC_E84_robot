from __future__ import annotations

import json
import re
from typing import Iterable


QUESTION_ONLY_RE = re.compile(r"^\?+$")
LATIN1_MOJIBAKE_RE = re.compile(r"(?:Ã.|Â.|â.|ðŸ|ï¿|¢|¤|¦|œ|ž|€|™)")
COMMON_MOJIBAKE_RE = re.compile(
    r"(?:[\uFFFD�]|\u9358\u54c7\u5699|\u7ec2\u8364\u5699|\u942e\u53d1\u9369\u54c4\u6e7e|\u5bee\u20ac|\u5bee\u4f60|\u93fa\ue812\u61e1|\u6405\u6d07\u5712|\u6d60\u8bec\u59df|\u9357\u5ff0\u4f5c|\u95c3\u71d7\u669f|\u5a11\u64c3\u5735|\u95b8\u7b80\u5100|\u7ece\u5f04\u589d)"
)

MAP_NPC_INTERACTION = "\u5730\u56fe NPC \u4ea4\u4e92"
COLLAB_UI_CLOSURE = "\u534f\u4f5c\u754c\u9762\u6536\u53e3"
COLLAB_DISPLAY_CLOSURE = "\u534f\u4f5c\u5c55\u793a\u6536\u53e3"
COLLAB_PROOF = "\u534f\u4f5c\u8bc1\u660e"
CURRENT_TASK = "\u5f53\u524d\u4efb\u52a1"


def text(value: object | None) -> str:
    return str(value or "").strip()


def looks_dirty_text(value: object | None) -> bool:
    raw = text(value)
    if not raw:
        return False
    if "??" in raw or "????" in raw:
        return True
    if QUESTION_ONLY_RE.fullmatch(raw):
        return True
    question_mark_count = raw.count("?")
    if question_mark_count >= 4 and question_mark_count >= len(raw) / 2:
        return True
    return bool(LATIN1_MOJIBAKE_RE.search(raw) or COMMON_MOJIBAKE_RE.search(raw))


def related_file_list(value: object | None) -> list[str]:
    if isinstance(value, list):
        return [text(item) for item in value if text(item)]
    raw = text(value)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return [text(item) for item in parsed if text(item)]
    return [raw]


def clean_title_prefix(raw_title: object | None) -> str:
    raw = text(raw_title)
    if not raw or "/" not in raw:
        return ""
    prefix = text(raw.split("/", 1)[0])
    return "" if looks_dirty_text(prefix) else prefix


def infer_requirement_suffix(
    related_files: Iterable[str],
    context_summary: object | None,
    expected_output: object | None,
    raw_title: object | None = None,
) -> str:
    related_blob = " ".join(item.lower() for item in related_files)
    hints = " ".join([text(context_summary).lower(), text(expected_output).lower(), text(raw_title).lower()])
    if "harvest-moon-phaser3-game" in related_blob:
        return MAP_NPC_INTERACTION
    if "project-playable-shell" in related_blob or "project-playable-shell.module.css" in related_blob:
        return COLLAB_UI_CLOSURE
    if "npc" in hints and "enter" in hints:
        return MAP_NPC_INTERACTION
    if "server-data" in related_blob:
        return COLLAB_DISPLAY_CLOSURE
    if "proof" in hints:
        return COLLAB_PROOF
    return CURRENT_TASK


def normalized_requirement_title(
    raw_title: object | None,
    related_files: Iterable[str],
    context_summary: object | None,
    expected_output: object | None,
) -> str:
    raw = text(raw_title)
    if raw and not looks_dirty_text(raw):
        return raw
    prefix = clean_title_prefix(raw_title)
    suffix = infer_requirement_suffix(related_files, context_summary, expected_output, raw_title=raw_title)
    return f"{prefix} / {suffix}" if prefix else suffix


def normalized_message_title(
    raw_title: object | None,
    *,
    requirement_title: str,
    message_type: object | None,
    status: object | None,
) -> str:
    raw = text(raw_title)
    if raw and not looks_dirty_text(raw):
        return raw
    message_type_value = text(message_type).lower()
    status_value = text(status).lower()
    if message_type_value in {"requirement_progress_ack", "agent_report"} and status_value == "in_progress":
        return f"{requirement_title} / minimal ack"
    if message_type_value == "requirement_final_reply" and status_value in {"done", "completed", "closed", "resolved"}:
        return f"{requirement_title} / final reply"
    return requirement_title
