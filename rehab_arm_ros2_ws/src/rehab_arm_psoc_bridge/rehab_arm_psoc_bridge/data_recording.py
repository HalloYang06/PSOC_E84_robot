from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, TextIO


RECORDER_VERSION = '0.1.0'
JSONL_SCHEMA_VERSION = 'rehab_arm_jsonl_v1'
DEFAULT_RECORDED_TOPICS = [
    '/joint_states',
    '/rehab_arm/safety_state',
    '/rehab_arm/sensor_state',
]


def parse_message_payload(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'raw': text}


def sanitize_identifier(value: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in value.strip())
    return cleaned or 'unknown'


def make_default_session_id(robot_id: str, device_id: str, now: float | None = None) -> str:
    timestamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time() if now is None else now))
    return f'{sanitize_identifier(robot_id)}__{sanitize_identifier(device_id)}__{timestamp}'


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
        'schema_version': JSONL_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'session_id': session_id,
        'device_id': device_id,
        'robot_id': robot_id,
        'software_version': software_version,
        'recorder_version': RECORDER_VERSION,
        'mode': mode,
        'source': 'nanopi_ros_recorder',
        'sync_status': 'local_only',
        'topics': list(DEFAULT_RECORDED_TOPICS),
        'motion_allowed_expected': False,
    }


def write_jsonl_record(handle: TextIO, record: dict[str, object]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')))
    handle.write('\n')


def session_log_path(output_dir: str, session_id: str) -> Path:
    return Path(output_dir).expanduser() / f'{sanitize_identifier(session_id)}.jsonl'


def load_jsonl_records(path: str | Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f'line {line_number}: invalid JSON: {exc.msg}') from exc
            if not isinstance(record, dict):
                raise ValueError(f'line {line_number}: record is not a JSON object')
            records.append(record)
    return records


def validate_jsonl_records(
    records: list[dict[str, object]],
    required_topics: Iterable[str] = DEFAULT_RECORDED_TOPICS,
) -> dict[str, object]:
    metadata = [record for record in records if record.get('record_type') == 'session_metadata']
    topics = {
        str(record.get('topic'))
        for record in records
        if record.get('record_type') == 'topic_message' and record.get('topic') is not None
    }
    required = set(required_topics)
    missing_topics = sorted(required - topics)
    errors: list[str] = []
    if not metadata:
        errors.append('missing session_metadata')
    if missing_topics:
        errors.append('missing required topics: ' + ', '.join(missing_topics))
    return {
        'ok': not errors,
        'record_count': len(records),
        'metadata_count': len(metadata),
        'topics': sorted(topics),
        'missing_topics': missing_topics,
        'errors': errors,
    }


def build_recording_manifest(log_dir: str | Path) -> dict[str, object]:
    base = Path(log_dir).expanduser()
    sessions: list[dict[str, object]] = []
    for path in sorted(base.glob('*.jsonl')):
        entry: dict[str, object] = {
            'path': str(path),
            'file_name': path.name,
            'size_bytes': path.stat().st_size,
            'sync_status': 'local_only',
        }
        try:
            records = load_jsonl_records(path)
            summary = validate_jsonl_records(records)
            metadata = next(
                (record for record in records if record.get('record_type') == 'session_metadata'),
                {},
            )
            entry.update({
                'ok': summary['ok'],
                'session_id': metadata.get('session_id'),
                'device_id': metadata.get('device_id'),
                'robot_id': metadata.get('robot_id'),
                'software_version': metadata.get('software_version'),
                'mode': metadata.get('mode'),
                'schema_version': metadata.get('schema_version'),
                'record_count': summary['record_count'],
                'topics': summary['topics'],
                'missing_topics': summary['missing_topics'],
                'errors': summary['errors'],
            })
        except Exception as exc:
            entry.update({
                'ok': False,
                'errors': [str(exc)],
            })
        sessions.append(entry)
    return {
        'schema_version': 'rehab_arm_manifest_v1',
        'log_dir': str(base),
        'session_count': len(sessions),
        'sessions': sessions,
    }
