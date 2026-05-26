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
        make_joint_state_payload,
        make_payload_record,
        make_motor_state_payload,
        sanitize_identifier,
        write_jsonl_record,
    )
    from rehab_arm_psoc_bridge.psoc_motor_status import (
        make_joint_state_fields_from_m33_motor_state,
        parse_m33_motor_status_frame,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        JSONL_SCHEMA_VERSION,
        RECORDER_VERSION,
        make_joint_state_payload,
        make_payload_record,
        make_motor_state_payload,
        sanitize_identifier,
        write_jsonl_record,
    )
    from rehab_arm_psoc_bridge.psoc_motor_status import (
        make_joint_state_fields_from_m33_motor_state,
        parse_m33_motor_status_frame,
    )


CANSIMPLE_HEARTBEAT_CMD = 0x001
CANSIMPLE_ENCODER_ESTIMATE_CMD = 0x009
PRIVATE_ACTIVE_REPORT_TYPE = 0x18
PRIVATE_MASTER_ID = 0xFD
LINGZU_POSITION_LIMIT_RAD = 4 * math.pi
LINGZU_ACTUATOR_LIMITS = {
    'RS00': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 50.0, 'torque': 17.0},
    'RS01': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 44.0, 'torque': 17.0},
    'RS02': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 44.0, 'torque': 17.0},
    'RS03': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 50.0, 'torque': 60.0},
    'RS04': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 15.0, 'torque': 120.0},
    'RS05': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 33.0, 'torque': 17.0},
    'RS06': {'position': LINGZU_POSITION_LIMIT_RAD, 'velocity': 20.0, 'torque': 36.0},
}
LINGZU_ACTUATOR_TYPE_BY_ID: dict[int, str] = {}
MOTOR_VENDOR_BY_ID = {
    3: 'Sitaiwei',
    4: 'Lingzu',
    5: 'Lingzu',
    6: 'Lingzu',
    7: 'Lingzu',
}
CONTROL_BOUNDARY = 'telemetry_only_not_motor_command'

CAN_LINE_RE = re.compile(
    r'\((?P<time>[-0-9.]+)\)\s+\S+\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)*)'
)
CAN_HASH_LINE_RE = re.compile(
    r'\((?P<time>[-0-9.]+)\)\s+\S+\s+(?P<id>[0-9A-Fa-f]+)#(?P<data>[0-9A-Fa-f]*)'
)


def parse_candump_line(line: str) -> dict[str, object] | None:
    text = line.strip()
    match = CAN_LINE_RE.search(text)
    if match:
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
    match = CAN_HASH_LINE_RE.search(text)
    if not match:
        return None
    data_text = match.group('data')
    if len(data_text) % 2:
        return None
    data = bytes.fromhex(data_text)
    return {
        'relative_time_s': float(match.group('time')),
        'can_id': int(match.group('id'), 16),
        'dlc': len(data),
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
    heartbeat_byte5 = data[5] if len(data) >= 6 else None
    heartbeat_byte6 = data[6] if len(data) >= 7 else None
    heartbeat_byte7 = data[7] if len(data) >= 8 else None
    return {
        'node_id': cansimple_node_id(int(frame['can_id'])),
        'axis_error_u32': error,
        'error_code': f'0x{error:08X}',
        'axis_state': state,
        'enabled': state == 8,
        'fault': error != 0,
        'heartbeat_byte5': heartbeat_byte5,
        'heartbeat_byte6': heartbeat_byte6,
        'heartbeat_byte7': heartbeat_byte7,
        'heartbeat_extension_decode': 'raw_only_vendor_fields_unconfirmed',
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
        'vendor': MOTOR_VENDOR_BY_ID.get(node_id),
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
        'heartbeat_byte5': heartbeat.get('heartbeat_byte5') if heartbeat else None,
        'heartbeat_byte6': heartbeat.get('heartbeat_byte6') if heartbeat else None,
        'heartbeat_byte7': heartbeat.get('heartbeat_byte7') if heartbeat else None,
        'heartbeat_extension_decode': heartbeat.get('heartbeat_extension_decode') if heartbeat else None,
        'raw_can_id': f"0x{int(frame['can_id']):03X}",
        'raw_data': data.hex().upper(),
    }


def lingzu_u16_to_symmetric_float(value: int, limit: float) -> float:
    return ((float(value) / 32767.0) - 1.0) * limit


def decode_lingzu_engineering_values(
    motor_id: int,
    position_raw: int,
    velocity_raw: int,
    torque_raw: int,
    temperature_raw: int,
    actuator_type_by_id: dict[int, str] | None = None,
) -> dict[str, object]:
    actuator_type = (actuator_type_by_id or LINGZU_ACTUATOR_TYPE_BY_ID).get(motor_id)
    values: dict[str, object] = {
        'actuator_type': actuator_type or 'unknown',
        'engineering_decode': 'raw_only_actuator_type_unconfirmed',
        'position': None,
        'velocity': None,
        'effort': None,
        'torque': None,
        'temperature': None,
    }
    if not actuator_type:
        return values
    limits = LINGZU_ACTUATOR_LIMITS.get(actuator_type)
    if not limits:
        values['engineering_decode'] = 'raw_only_actuator_type_not_in_local_reference'
        return values
    values.update(
        {
            'engineering_decode': 'lingzu_robstride_ros_sample_actuator_mapping',
            'position': lingzu_u16_to_symmetric_float(position_raw, limits['position']),
            'velocity': lingzu_u16_to_symmetric_float(velocity_raw, limits['velocity']),
            'effort': lingzu_u16_to_symmetric_float(torque_raw, limits['torque']),
            'torque': lingzu_u16_to_symmetric_float(torque_raw, limits['torque']),
            'temperature': temperature_raw * 0.1,
        }
    )
    return values


def decode_private_active_report(frame: dict[str, object]) -> dict[str, object] | None:
    can_id = int(frame['can_id'])
    data = frame['data']
    if not isinstance(data, bytes) or len(data) != 8:
        return None
    if (can_id & 0xFF) != PRIVATE_MASTER_ID:
        return None
    if ((can_id >> 24) & 0x1F) != PRIVATE_ACTIVE_REPORT_TYPE:
        return None
    motor_id = (can_id >> 8) & 0xFF
    position_raw = int.from_bytes(data[0:2], 'big', signed=False)
    velocity_raw = int.from_bytes(data[2:4], 'big', signed=False)
    torque_raw = int.from_bytes(data[4:6], 'big', signed=False)
    temperature_raw = int.from_bytes(data[6:8], 'big', signed=False)
    engineering = decode_lingzu_engineering_values(
        motor_id,
        position_raw,
        velocity_raw,
        torque_raw,
        temperature_raw,
    )
    return {
        'motor_id': motor_id,
        'joint_name': f'private_motor_{motor_id}',
        'vendor': MOTOR_VENDOR_BY_ID.get(motor_id),
        'protocol': 'lingzu_robstride_private_active_report',
        'position': engineering['position'],
        'velocity': engineering['velocity'],
        'effort': engineering['effort'],
        'current': None,
        'torque': engineering['torque'],
        'temperature': engineering['temperature'],
        'voltage': None,
        'enabled': None,
        'fault': None,
        'error_code': None,
        'actuator_type': engineering['actuator_type'],
        'engineering_decode': engineering['engineering_decode'],
        'raw_position_u16': position_raw,
        'raw_velocity_u16': velocity_raw,
        'raw_torque_u16': torque_raw,
        'raw_temperature_u16': temperature_raw,
        'temperature_raw': temperature_raw,
        'status_raw': f'0x{data[7]:02X}',
        'raw_can_id': f'0x{can_id:08X}',
        'raw_data': data.hex().upper(),
        'decode_source': 'local D:\\电机上位机 RobStride sample: Communication_Type_MotorRequest/0x18 payload; engineering units require actuator model',
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
        'topics': ['/rehab_arm/motor_state', '/joint_states'],
        'optional_topics': [],
        'motion_allowed_expected': False,
        'control_boundary': CONTROL_BOUNDARY,
    }


def split_stamp(relative_time: float) -> tuple[int, int]:
    sec = int(relative_time)
    nanosec = int(round((relative_time - sec) * 1_000_000_000))
    if nanosec >= 1_000_000_000:
        sec += 1
        nanosec -= 1_000_000_000
    return sec, nanosec


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
    joint_state_count = 0
    heartbeat_count = 0
    private_active_report_count = 0
    m33_motor_status_count = 0
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
            m33_motor = parse_m33_motor_status_frame(int(frame['can_id']), frame['data'])
            if m33_motor.get('valid') is True:
                payload = make_motor_state_payload(
                    [m33_motor],
                    robot_id=robot_id,
                    device_id=device_id,
                    now=relative_time,
                    source='candump_m33_motor_status',
                )
                payload['session_id'] = sid
                payload['relative_time_s'] = relative_time
                records.append(make_payload_record('/rehab_arm/motor_state', payload, now=relative_time))
                motor_state_count += 1
                m33_motor_status_count += 1
                joint_fields = make_joint_state_fields_from_m33_motor_state(payload)
                if joint_fields['name']:
                    stamp_sec, stamp_nanosec = split_stamp(relative_time)
                    joint_payload = make_joint_state_payload(
                        names=joint_fields['name'],
                        positions=joint_fields['position'],
                        velocities=joint_fields['velocity'],
                        efforts=joint_fields['effort'],
                        stamp_sec=stamp_sec,
                        stamp_nanosec=stamp_nanosec,
                    )
                    joint_payload['session_id'] = sid
                    joint_payload['relative_time_s'] = relative_time
                    joint_payload['source'] = 'candump_m33_motor_status'
                    joint_payload['control_boundary'] = CONTROL_BOUNDARY
                    records.append(make_payload_record('/joint_states', joint_payload, now=relative_time))
                    joint_state_count += 1
                continue
            private_motor = decode_private_active_report(frame)
            if private_motor:
                payload = make_motor_state_payload(
                    [private_motor],
                    robot_id=robot_id,
                    device_id=device_id,
                    now=relative_time,
                    source='candump_private_active_report',
                )
                payload['session_id'] = sid
                payload['relative_time_s'] = relative_time
                records.append(make_payload_record('/rehab_arm/motor_state', payload, now=relative_time))
                motor_state_count += 1
                private_active_report_count += 1
                continue
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
        'private_active_report_count': private_active_report_count,
        'm33_motor_status_count': m33_motor_status_count,
        'motor_state_count': motor_state_count,
        'joint_state_count': joint_state_count,
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
