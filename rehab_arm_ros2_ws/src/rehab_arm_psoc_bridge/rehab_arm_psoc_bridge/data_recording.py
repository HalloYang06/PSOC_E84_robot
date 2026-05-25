from __future__ import annotations

import json
import hashlib
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
OPTIONAL_RECORDED_TOPICS = [
    '/rehab_arm/motor_state',
    '/rehab_arm/camera_keyframe',
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


def make_motor_state_payload(
    motors: list[dict[str, object]],
    robot_id: str,
    device_id: str,
    now: float | None = None,
    source: str = 'nanopi_ros',
) -> dict[str, object]:
    return {
        'schema_version': 'rehab_arm_motor_state_v1',
        'ts_unix': time.time() if now is None else now,
        'robot_id': robot_id,
        'device_id': device_id,
        'source': source,
        'motors': [dict(motor) for motor in motors],
        'control_boundary': 'telemetry_only_not_motor_command',
    }


def make_motor_entries_from_joint_state(
    names: list[str],
    positions: list[float],
    velocities: list[float],
    efforts: list[float],
    joint_motor_map: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    mapping = joint_motor_map or {}
    motors: list[dict[str, object]] = []
    for index, joint_name in enumerate(names):
        mapped = dict(mapping.get(joint_name, {}))
        motors.append({
            'motor_id': mapped.get('motor_id'),
            'joint_name': joint_name,
            'protocol': mapped.get('protocol', 'simulated_joint_state'),
            'position': positions[index] if index < len(positions) else None,
            'velocity': velocities[index] if index < len(velocities) else None,
            'effort': efforts[index] if index < len(efforts) else None,
            'current': mapped.get('current'),
            'torque': mapped.get('torque'),
            'temperature': mapped.get('temperature'),
            'voltage': mapped.get('voltage'),
            'enabled': mapped.get('enabled'),
            'fault': mapped.get('fault', False),
            'error_code': mapped.get('error_code'),
            'raw_can_id': mapped.get('raw_can_id'),
            'source_index': index,
        })
    return motors


def make_camera_keyframe_payload(
    camera_id: str,
    image_path: str,
    sha256: str,
    robot_id: str,
    device_id: str,
    width: int | None = None,
    height: int | None = None,
    image_format: str = 'jpg',
    now: float | None = None,
    source: str = 'nanopi_camera',
    scene_summary: str = '',
    detection_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        'schema_version': 'rehab_arm_camera_keyframe_v1',
        'ts_unix': time.time() if now is None else now,
        'robot_id': robot_id,
        'device_id': device_id,
        'source': source,
        'camera_id': camera_id,
        'image_path': image_path,
        'image_format': image_format,
        'width': width,
        'height': height,
        'sha256': sha256,
        'scene_summary': scene_summary,
        'detection_summary': detection_summary or {},
        'control_boundary': 'perception_data_only_not_motor_command',
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
        'optional_topics': list(OPTIONAL_RECORDED_TOPICS),
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


def _update_numeric_range(ranges: dict[str, dict[str, float]], name: str, value: object) -> None:
    if not isinstance(value, (int, float)):
        return
    numeric = float(value)
    current = ranges.setdefault(name, {'min': numeric, 'max': numeric, 'span': 0.0})
    current['min'] = min(current['min'], numeric)
    current['max'] = max(current['max'], numeric)
    current['span'] = current['max'] - current['min']


def summarize_jsonl_records(records: list[dict[str, object]]) -> dict[str, object]:
    topic_counts: dict[str, int] = {}
    topic_first_ts: dict[str, float] = {}
    topic_last_ts: dict[str, float] = {}
    joint_ranges: dict[str, dict[str, float]] = {}
    motor_ranges: dict[str, dict[str, float]] = {}
    safety_states: dict[str, int] = {}
    motion_allowed_counts = {'true': 0, 'false': 0, 'missing': 0}
    motor_entry_counts: list[int] = []
    metadata = next(
        (record for record in records if record.get('record_type') == 'session_metadata'),
        {},
    )

    for record in records:
        if record.get('record_type') != 'topic_message':
            continue
        topic = record.get('topic')
        if not isinstance(topic, str):
            continue
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        ts_unix = record.get('ts_unix')
        if isinstance(ts_unix, (int, float)):
            ts = float(ts_unix)
            topic_first_ts[topic] = min(topic_first_ts.get(topic, ts), ts)
            topic_last_ts[topic] = max(topic_last_ts.get(topic, ts), ts)

        payload = record.get('payload')
        if topic == '/joint_states' and isinstance(payload, dict):
            names = payload.get('name', [])
            positions = payload.get('position', [])
            if isinstance(names, list) and isinstance(positions, list):
                for name, position in zip(names, positions):
                    _update_numeric_range(joint_ranges, str(name), position)
        elif topic == '/rehab_arm/motor_state' and isinstance(payload, dict):
            motors = payload.get('motors', [])
            if isinstance(motors, list):
                motor_entry_counts.append(len(motors))
                for motor in motors:
                    if not isinstance(motor, dict):
                        continue
                    key = str(motor.get('joint_name') or motor.get('motor_id') or 'unknown')
                    _update_numeric_range(motor_ranges, key, motor.get('position'))
        elif topic == '/rehab_arm/safety_state' and isinstance(payload, dict):
            state = str(payload.get('state', 'unknown'))
            safety_states[state] = safety_states.get(state, 0) + 1
            motion_allowed = payload.get('motion_allowed')
            if motion_allowed is True:
                motion_allowed_counts['true'] += 1
            elif motion_allowed is False:
                motion_allowed_counts['false'] += 1
            else:
                motion_allowed_counts['missing'] += 1

    topic_rates_hz: dict[str, float] = {}
    for topic, count in topic_counts.items():
        duration = topic_last_ts.get(topic, 0.0) - topic_first_ts.get(topic, 0.0)
        topic_rates_hz[topic] = count / duration if count > 1 and duration > 0.0 else 0.0

    return {
        'schema_version': 'rehab_arm_recording_summary_v1',
        'record_count': len(records),
        'metadata': dict(metadata) if isinstance(metadata, dict) else {},
        'topic_counts': dict(sorted(topic_counts.items())),
        'topic_rates_hz': dict(sorted(topic_rates_hz.items())),
        'joint_position_ranges': dict(sorted(joint_ranges.items())),
        'moving_joint_count': sum(1 for item in joint_ranges.values() if item['span'] > 0.01),
        'motor_position_ranges': dict(sorted(motor_ranges.items())),
        'motor_entry_count_min': min(motor_entry_counts) if motor_entry_counts else 0,
        'motor_entry_count_max': max(motor_entry_counts) if motor_entry_counts else 0,
        'safety_states': dict(sorted(safety_states.items())),
        'motion_allowed_counts': motion_allowed_counts,
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


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).expanduser().open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_sync_dry_run_plan(manifest: dict[str, object], base_url: str) -> dict[str, object]:
    base = base_url.rstrip('/')
    sessions = [
        session for session in manifest.get('sessions', [])
        if isinstance(session, dict) and session.get('ok') is True
    ]
    devices: dict[tuple[str, str], dict[str, object]] = {}
    for session in sessions:
        device_id = str(session.get('device_id') or 'unknown')
        robot_id = str(session.get('robot_id') or 'unknown')
        devices[(device_id, robot_id)] = {
            'device_id': device_id,
            'robot_id': robot_id,
            'device_type': 'nanopi',
            'software_version': session.get('software_version') or 'unknown',
            'capabilities': ['ros2_bridge', 'jsonl_recorder', 'manifest_builder'],
        }

    requests: list[dict[str, object]] = []
    for device in devices.values():
        requests.append({
            'method': 'POST',
            'url': f'{base}/devices/register',
            'json': device,
        })

    requests.append({
        'method': 'POST',
        'url': f'{base}/sessions/manifest',
        'json': {
            'manifest': manifest,
        },
    })

    for session in sessions:
        path = Path(str(session.get('path')))
        session_id = str(session.get('session_id'))
        requests.append({
            'method': 'POST',
            'url': f'{base}/sessions/{session_id}/files',
            'multipart': {
                'device_id': session.get('device_id'),
                'robot_id': session.get('robot_id'),
                'file_name': session.get('file_name'),
                'sha256': file_sha256(path),
                'file_path': str(path),
            },
        })
        requests.append({
            'method': 'POST',
            'url': f'{base}/sessions/{session_id}/sync-status',
            'json': {
                'device_id': session.get('device_id'),
                'sync_status': 'dry_run_ready',
                'file_name': session.get('file_name'),
                'record_count': session.get('record_count'),
            },
        })

    skipped = [
        session for session in manifest.get('sessions', [])
        if isinstance(session, dict) and session.get('ok') is not True
    ]
    return {
        'schema_version': 'rehab_arm_sync_dry_run_v1',
        'base_url': base,
        'request_count': len(requests),
        'requests': requests,
        'skipped_sessions': [
            {
                'file_name': session.get('file_name'),
                'session_id': session.get('session_id'),
                'errors': session.get('errors', []),
            }
            for session in skipped
        ],
    }
