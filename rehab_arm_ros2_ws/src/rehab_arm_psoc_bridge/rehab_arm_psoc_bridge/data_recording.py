from __future__ import annotations

import json
import hashlib
import time
import csv
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
RECORDING_TOPIC_PROFILES = {
    'simulation_minimum': [
        '/joint_states',
        '/rehab_arm/safety_state',
        '/rehab_arm/sensor_state',
    ],
    'hardware_telemetry': [
        '/joint_states',
        '/rehab_arm/safety_state',
        '/rehab_arm/sensor_state',
        '/rehab_arm/motor_state',
    ],
    'perception_vla': [
        '/joint_states',
        '/rehab_arm/safety_state',
        '/rehab_arm/sensor_state',
        '/rehab_arm/camera_keyframe',
    ],
}


def required_topics_for_profile(profile: str) -> list[str]:
    try:
        return list(RECORDING_TOPIC_PROFILES[profile])
    except KeyError as exc:
        choices = ', '.join(sorted(RECORDING_TOPIC_PROFILES))
        raise ValueError(f'unknown topic profile {profile!r}; expected one of: {choices}') from exc


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


def build_camera_file_check(
    records: list[dict[str, object]],
    camera_base_dir: str | Path | None = None,
) -> dict[str, object]:
    base_dir = Path(camera_base_dir).expanduser() if camera_base_dir is not None else None
    checked: list[dict[str, object]] = []
    missing_count = 0
    hash_mismatch_count = 0
    ok_count = 0

    for record in records:
        if record.get('record_type') != 'topic_message':
            continue
        if record.get('topic') != '/rehab_arm/camera_keyframe':
            continue
        payload = record.get('payload')
        if not isinstance(payload, dict):
            continue
        image_path = payload.get('image_path')
        if not isinstance(image_path, str) or not image_path:
            missing_count += 1
            checked.append({'image_path': image_path, 'ok': False, 'error': 'missing image_path'})
            continue

        path = Path(image_path).expanduser()
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        if not path.exists():
            missing_count += 1
            checked.append({'image_path': image_path, 'resolved_path': str(path), 'ok': False, 'error': 'file missing'})
            continue

        expected_sha = payload.get('sha256')
        actual_sha = file_sha256(path)
        if isinstance(expected_sha, str) and expected_sha and expected_sha != actual_sha:
            hash_mismatch_count += 1
            checked.append({
                'image_path': image_path,
                'resolved_path': str(path),
                'ok': False,
                'error': 'sha256 mismatch',
                'expected_sha256': expected_sha,
                'actual_sha256': actual_sha,
            })
            continue

        ok_count += 1
        checked.append({
            'image_path': image_path,
            'resolved_path': str(path),
            'ok': True,
            'sha256': actual_sha,
        })

    return {
        'schema_version': 'rehab_arm_camera_file_check_v1',
        'checked_count': len(checked),
        'ok_count': ok_count,
        'missing_count': missing_count,
        'hash_mismatch_count': hash_mismatch_count,
        'items': checked,
    }


def build_recording_quality_report(
    records: list[dict[str, object]],
    min_joint_messages: int = 1,
    min_moving_joints: int = 0,
    require_motor_state: bool = False,
    min_motor_entry_count: int = 0,
    min_camera_keyframes: int = 0,
    require_camera_files: bool = False,
    camera_base_dir: str | Path | None = None,
    allow_motion_allowed_true: bool = False,
    required_topics: Iterable[str] | None = None,
    topic_profile: str | None = None,
) -> dict[str, object]:
    if topic_profile:
        selected_required_topics = required_topics_for_profile(topic_profile)
        if required_topics is not None:
            selected_required_topics.extend(required_topics)
    elif required_topics is not None:
        selected_required_topics = list(required_topics)
    else:
        selected_required_topics = list(DEFAULT_RECORDED_TOPICS)

    schema_check = validate_jsonl_records(records, selected_required_topics)
    summary = summarize_jsonl_records(records)
    errors: list[str] = list(schema_check.get('errors', []))
    warnings: list[str] = []

    topic_counts = summary.get('topic_counts', {})
    if not isinstance(topic_counts, dict):
        topic_counts = {}
    joint_message_count = int(topic_counts.get('/joint_states', 0) or 0)
    motor_message_count = int(topic_counts.get('/rehab_arm/motor_state', 0) or 0)
    camera_keyframe_count = int(topic_counts.get('/rehab_arm/camera_keyframe', 0) or 0)
    moving_joint_count = int(summary.get('moving_joint_count', 0) or 0)
    motor_entry_count_min = int(summary.get('motor_entry_count_min', 0) or 0)

    if joint_message_count < min_joint_messages:
        errors.append(
            f'joint state message count {joint_message_count} below required {min_joint_messages}'
        )
    if moving_joint_count < min_moving_joints:
        errors.append(
            f'moving joint count {moving_joint_count} below required {min_moving_joints}'
        )
    if require_motor_state and motor_message_count == 0:
        errors.append('missing required /rehab_arm/motor_state messages')
    if min_motor_entry_count > 0:
        if motor_message_count == 0:
            errors.append(
                f'motor entry count 0 below required {min_motor_entry_count}; no motor_state messages'
            )
        elif motor_entry_count_min < min_motor_entry_count:
            errors.append(
                f'motor entry count min {motor_entry_count_min} below required {min_motor_entry_count}'
            )
    if camera_keyframe_count < min_camera_keyframes:
        errors.append(
            f'camera keyframe count {camera_keyframe_count} below required {min_camera_keyframes}'
        )
    camera_file_check = build_camera_file_check(records, camera_base_dir) if require_camera_files else None
    if isinstance(camera_file_check, dict):
        missing_count = int(camera_file_check.get('missing_count', 0) or 0)
        hash_mismatch_count = int(camera_file_check.get('hash_mismatch_count', 0) or 0)
        if missing_count > 0:
            errors.append(f'camera keyframe file missing count {missing_count}')
        if hash_mismatch_count > 0:
            errors.append(f'camera keyframe sha256 mismatch count {hash_mismatch_count}')

    motion_allowed_counts = summary.get('motion_allowed_counts', {})
    if not isinstance(motion_allowed_counts, dict):
        motion_allowed_counts = {}
    motion_allowed_true = int(motion_allowed_counts.get('true', 0) or 0)
    if motion_allowed_true > 0 and not allow_motion_allowed_true:
        errors.append(
            f'motion_allowed true appeared {motion_allowed_true} times; current offline/logging checks expect false'
        )

    if joint_message_count > 0 and moving_joint_count == 0:
        warnings.append('joint_states were recorded but no joint moved more than 0.01 rad')
    motor_state_required_by_topics = '/rehab_arm/motor_state' in selected_required_topics
    if not require_motor_state and not motor_state_required_by_topics and motor_message_count == 0:
        warnings.append('/rehab_arm/motor_state is absent; this may be fine for early raw recorder checks')

    return {
        'schema_version': 'rehab_arm_recording_quality_v1',
        'ok': not errors,
        'topic_profile': topic_profile,
        'required_topics': selected_required_topics,
        'errors': errors,
        'warnings': warnings,
        'criteria': {
            'min_joint_messages': min_joint_messages,
            'min_moving_joints': min_moving_joints,
            'require_motor_state': require_motor_state,
            'min_motor_entry_count': min_motor_entry_count,
            'min_camera_keyframes': min_camera_keyframes,
            'require_camera_files': require_camera_files,
            'allow_motion_allowed_true': allow_motion_allowed_true,
        },
        'schema_check': schema_check,
        'camera_file_check': camera_file_check,
        'summary': summary,
    }


JOINT_STATE_CSV_FIELDS = [
    'ts_unix',
    'stamp_sec',
    'stamp_nanosec',
    'joint_name',
    'position',
    'velocity',
    'effort',
]
MOTOR_STATE_CSV_FIELDS = [
    'ts_unix',
    'robot_id',
    'device_id',
    'source',
    'joint_name',
    'motor_id',
    'protocol',
    'position',
    'velocity',
    'effort',
    'current',
    'torque',
    'temperature',
    'voltage',
    'enabled',
    'fault',
    'error_code',
    'raw_can_id',
]


def make_joint_state_csv_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in records:
        if record.get('record_type') != 'topic_message' or record.get('topic') != '/joint_states':
            continue
        payload = record.get('payload')
        if not isinstance(payload, dict):
            continue
        names = payload.get('name', [])
        positions = payload.get('position', [])
        velocities = payload.get('velocity', [])
        efforts = payload.get('effort', [])
        stamp = payload.get('stamp', {})
        if not isinstance(names, list):
            continue
        if not isinstance(positions, list):
            positions = []
        if not isinstance(velocities, list):
            velocities = []
        if not isinstance(efforts, list):
            efforts = []
        if not isinstance(stamp, dict):
            stamp = {}
        for index, name in enumerate(names):
            rows.append({
                'ts_unix': record.get('ts_unix'),
                'stamp_sec': stamp.get('sec'),
                'stamp_nanosec': stamp.get('nanosec'),
                'joint_name': name,
                'position': positions[index] if index < len(positions) else '',
                'velocity': velocities[index] if index < len(velocities) else '',
                'effort': efforts[index] if index < len(efforts) else '',
            })
    return rows


def make_motor_state_csv_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in records:
        if record.get('record_type') != 'topic_message' or record.get('topic') != '/rehab_arm/motor_state':
            continue
        payload = record.get('payload')
        if not isinstance(payload, dict):
            continue
        motors = payload.get('motors', [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            rows.append({
                'ts_unix': record.get('ts_unix'),
                'robot_id': payload.get('robot_id'),
                'device_id': payload.get('device_id'),
                'source': payload.get('source'),
                'joint_name': motor.get('joint_name'),
                'motor_id': motor.get('motor_id'),
                'protocol': motor.get('protocol'),
                'position': motor.get('position'),
                'velocity': motor.get('velocity'),
                'effort': motor.get('effort'),
                'current': motor.get('current'),
                'torque': motor.get('torque'),
                'temperature': motor.get('temperature'),
                'voltage': motor.get('voltage'),
                'enabled': motor.get('enabled'),
                'fault': motor.get('fault'),
                'error_code': motor.get('error_code'),
                'raw_can_id': motor.get('raw_can_id'),
            })
    return rows


def write_csv_rows(path: str | Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_recording_manifest(
    log_dir: str | Path,
    include_summary: bool = False,
    include_quality_report: bool = False,
    min_joint_messages: int = 1,
    min_moving_joints: int = 0,
    require_motor_state: bool = False,
    min_motor_entry_count: int = 0,
    min_camera_keyframes: int = 0,
    require_camera_files: bool = False,
    camera_base_dir: str | Path | None = None,
    allow_motion_allowed_true: bool = False,
    required_topics: Iterable[str] | None = None,
    topic_profile: str | None = None,
) -> dict[str, object]:
    base = Path(log_dir).expanduser()
    resolved_camera_base_dir = base if camera_base_dir is None else camera_base_dir
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
            if include_summary:
                entry['summary'] = summarize_jsonl_records(records)
            if include_quality_report:
                entry['quality_report'] = build_recording_quality_report(
                    records,
                    min_joint_messages=min_joint_messages,
                    min_moving_joints=min_moving_joints,
                    require_motor_state=require_motor_state,
                    min_motor_entry_count=min_motor_entry_count,
                    min_camera_keyframes=min_camera_keyframes,
                    require_camera_files=require_camera_files,
                    camera_base_dir=resolved_camera_base_dir,
                    allow_motion_allowed_true=allow_motion_allowed_true,
                    required_topics=required_topics,
                    topic_profile=topic_profile,
                )
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
