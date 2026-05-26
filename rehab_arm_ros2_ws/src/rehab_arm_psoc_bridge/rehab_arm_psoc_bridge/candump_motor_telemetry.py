#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import time
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import (
        JSONL_SCHEMA_VERSION,
        RECORDER_VERSION,
        make_payload_record,
        make_motor_state_payload,
        sanitize_identifier,
        write_jsonl_record,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        JSONL_SCHEMA_VERSION,
        RECORDER_VERSION,
        make_payload_record,
        make_motor_state_payload,
        sanitize_identifier,
        write_jsonl_record,
    )


CANSIMPLE_HEARTBEAT_CMD = 0x001
CANSIMPLE_ENCODER_ESTIMATE_CMD = 0x009
CONTROL_BOUNDARY = 'telemetry_only_not_motor_command'

CAN_LINE_RE = re.compile(
    r'\((?P<time>[-0-9.]+)\)\s+\S+\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)*)'
)


def parse_candump_line(line: str) -> dict[str, object] | None:
    match = CAN_LINE_RE.search(line.strip())
    if not match:
        return None
    data = bytes(int(item, 16) for item in match.group('data').split())
    dlc = int(match.group('dlc'))
    if dlc != len(data):
        return None
    return {
        'relative_time_s': float(match.group('time')),
        'can_id': int(match.group('id'), 16),
        'dlc': dlc,
        'data': data,
    }


def cansimple_node_id(can_id: int) -> int:
    return can_id >> 5


def cansimple_cmd_id(can_id: int) -> int:
    return can_id & 0x1F


def decode_cansimple_heartbeat(frame: dict[str, object]) -> dict[str, object] | None:
    data = frame['data']
    if not isinstance(data, bytes) or len(data) < 5:
        return None
    error = int.from_bytes(data[0:4], 'little', signed=False)
    state = data[4]
    return {
        'node_id': cansimple_node_id(int(frame['can_id'])),
        'error_code': f'0x{error:08X}',
        'axis_state': state,
        'enabled': state == 8,
        'fault': error != 0,
        'raw_can_id': f"0x{int(frame['can_id']):03X}",
        'raw_data': data.hex().upper(),
    }


def decode_cansimple_encoder_estimate(
    frame: dict[str, object],
    heartbeat: dict[str, object] | None = None,
) -> dict[str, object] | None:
    data = frame['data']
    if not isinstance(data, bytes) or len(data) != 8:
        return None
    position_turns, velocity_turns_per_sec = struct.unpack('<ff', data)
    node_id = cansimple_node_id(int(frame['can_id']))
    return {
        'motor_id': node_id,
        'joint_name': f'cansimple_node_{node_id}',
        'protocol': 'cansimple_encoder_estimate',
        'position': position_turns * math.tau,
        'velocity': velocity_turns_per_sec * math.tau,
        'position_turns': position_turns,
        'velocity_turns_per_sec': velocity_turns_per_sec,
        'effort': None,
        'current': None,
        'torque': None,
        'temperature': None,
        'voltage': None,
        'enabled': heartbeat.get('enabled') if heartbeat else None,
        'fault': heartbeat.get('fault') if heartbeat else False,
        'error_code': heartbeat.get('error_code') if heartbeat else None,
        'axis_state': heartbeat.get('axis_state') if heartbeat else None,
        'raw_can_id': f"0x{int(frame['can_id']):03X}",
        'raw_data': data.hex().upper(),
    }


def make_raw_can_session_metadata(
    session_id: str,
    device_id: str,
    robot_id: str,
    source_log: str,
    now: float | None = None,
) -> dict[str, object]:
    return {
        'record_type': 'session_metadata',
        'schema_version': JSONL_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'session_id': session_id,
        'device_id': device_id,
        'robot_id': robot_id,
        'software_version': 'dev',
        'recorder_version': RECORDER_VERSION,
        'mode': 'raw_cansimple_motor_telemetry',
        'source': 'candump_motor_telemetry',
        'source_log': source_log,
        'sync_status': 'local_only',
        'topics': ['/rehab_arm/motor_state'],
        'optional_topics': [],
        'motion_allowed_expected': False,
        'control_boundary': CONTROL_BOUNDARY,
    }


def convert_candump_to_records(
    candump_path: str | Path,
    robot_id: str,
    device_id: str,
    session_id: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    source = Path(candump_path).expanduser()
    sid = sanitize_identifier(session_id or source.stem)
    records: list[dict[str, object]] = [
        make_raw_can_session_metadata(sid, device_id, robot_id, str(source)),
    ]
    last_heartbeat_by_node: dict[int, dict[str, object]] = {}
    total_frames = 0
    motor_state_count = 0
    heartbeat_count = 0
    ignored_count = 0
    first_relative_time: float | None = None
    last_relative_time: float | None = None

    with source.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            frame = parse_candump_line(line)
            if frame is None:
                ignored_count += 1
                continue
            total_frames += 1
            relative_time = float(frame['relative_time_s'])
            first_relative_time = relative_time if first_relative_time is None else first_relative_time
            last_relative_time = relative_time
            cmd_id = cansimple_cmd_id(int(frame['can_id']))
            node_id = cansimple_node_id(int(frame['can_id']))
            if cmd_id == CANSIMPLE_HEARTBEAT_CMD:
                heartbeat = decode_cansimple_heartbeat(frame)
                if heartbeat:
                    heartbeat_count += 1
                    last_heartbeat_by_node[node_id] = heartbeat
                continue
            if cmd_id != CANSIMPLE_ENCODER_ESTIMATE_CMD:
                ignored_count += 1
                continue
            motor = decode_cansimple_encoder_estimate(frame, last_heartbeat_by_node.get(node_id))
            if not motor:
                ignored_count += 1
                continue
            payload = make_motor_state_payload(
                [motor],
                robot_id=robot_id,
                device_id=device_id,
                now=relative_time,
                source='candump_cansimple',
            )
            payload['session_id'] = sid
            payload['relative_time_s'] = relative_time
            records.append(make_payload_record('/rehab_arm/motor_state', payload, now=relative_time))
            motor_state_count += 1

    summary = {
        'schema_version': 'rehab_arm_candump_motor_telemetry_summary_v1',
        'ok': motor_state_count > 0,
        'source_log': str(source),
        'session_id': sid,
        'robot_id': robot_id,
        'device_id': device_id,
        'total_frames': total_frames,
        'heartbeat_count': heartbeat_count,
        'motor_state_count': motor_state_count,
        'ignored_count': ignored_count,
        'first_relative_time_s': first_relative_time,
        'last_relative_time_s': last_relative_time,
        'control_boundary': CONTROL_BOUNDARY,
    }
    return records, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Convert a candump log with CANSimple node telemetry into rehab_arm motor_state JSONL.',
    )
    parser.add_argument('candump_path', help='Path to a candump -tz log file')
    parser.add_argument('--output', required=True, help='Output JSONL path')
    parser.add_argument('--device-id', default='nanopi-m5', help='Device id for JSONL metadata')
    parser.add_argument('--robot-id', default='rehab-arm-alpha', help='Robot id for JSONL metadata')
    parser.add_argument('--session-id', help='Optional session id. Defaults to the candump file stem')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print summary JSON')
    args = parser.parse_args(argv)

    records, summary = convert_candump_to_records(
        args.candump_path,
        robot_id=args.robot_id,
        device_id=args.device_id,
        session_id=args.session_id,
    )
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as handle:
        for record in records:
            write_jsonl_record(handle, record)
    summary['output'] = str(output_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if summary['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
