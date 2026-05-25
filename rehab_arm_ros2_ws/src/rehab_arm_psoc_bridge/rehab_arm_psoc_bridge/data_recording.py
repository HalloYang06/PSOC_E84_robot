from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TextIO


RECORDER_VERSION = '0.1.0'


def parse_message_payload(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'raw': text}


def make_jsonl_record(topic: str, text: str, now: float | None = None) -> dict[str, object]:
    return make_payload_record(topic, parse_message_payload(text), now)


def make_payload_record(topic: str, payload: object, now: float | None = None) -> dict[str, object]:
    return {
        'record_type': 'topic_message',
        'ts_unix': time.time() if now is None else now,
        'topic': topic,
        'payload': payload,
    }


def make_joint_state_payload(
    names: list[str],
    positions: list[float],
    velocities: list[float],
    efforts: list[float],
    stamp_sec: int,
    stamp_nanosec: int,
) -> dict[str, object]:
    return {
        'stamp': {
            'sec': stamp_sec,
            'nanosec': stamp_nanosec,
        },
        'name': list(names),
        'position': list(positions),
        'velocity': list(velocities),
        'effort': list(efforts),
    }


def make_session_metadata(
    session_id: str,
    device_id: str,
    robot_id: str,
    software_version: str,
    mode: str,
    now: float | None = None,
) -> dict[str, object]:
    return {
        'record_type': 'session_metadata',
        'ts_unix': time.time() if now is None else now,
        'session_id': session_id,
        'device_id': device_id,
        'robot_id': robot_id,
        'software_version': software_version,
        'recorder_version': RECORDER_VERSION,
        'mode': mode,
        'topics': [
            '/joint_states',
            '/rehab_arm/safety_state',
            '/rehab_arm/sensor_state',
        ],
        'motion_allowed_expected': False,
    }


def write_jsonl_record(handle: TextIO, record: dict[str, object]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')))
    handle.write('\n')


def session_log_path(output_dir: str, session_id: str) -> Path:
    safe_session = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in session_id)
    return Path(output_dir).expanduser() / f'{safe_session}.jsonl'
