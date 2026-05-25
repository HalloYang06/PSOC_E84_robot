from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TextIO


def parse_message_payload(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'raw': text}


def make_jsonl_record(topic: str, text: str, now: float | None = None) -> dict[str, object]:
    return {
        'ts_unix': time.time() if now is None else now,
        'topic': topic,
        'payload': parse_message_payload(text),
    }


def write_jsonl_record(handle: TextIO, record: dict[str, object]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')))
    handle.write('\n')


def session_log_path(output_dir: str, session_id: str) -> Path:
    safe_session = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in session_id)
    return Path(output_dir).expanduser() / f'{safe_session}.jsonl'
