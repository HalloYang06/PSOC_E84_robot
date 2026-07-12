#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.candump_motor_telemetry import parse_candump_line
    from rehab_arm_psoc_bridge.psoc_motor_status import parse_m33_motor_status_frame
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.candump_motor_telemetry import parse_candump_line
    from rehab_arm_psoc_bridge.psoc_motor_status import parse_m33_motor_status_frame


ROS_CMD_ID = 0x320
PSOC_STATUS_ID = 0x322
M33_MOTOR_STATUS_BASE_ID = 0x330
M33_MOTOR_STATUS_MAX_ID = 0x337
PRIVATE_PARAM_WRITE_TYPE = 0x12
PRIVATE_STOP_TYPE = 0x04
PRIVATE_MIT_CONTROL_TYPE = 0x01
PRIVATE_MASTER_ID = 0xFD
PARAM_RUN_MODE = 0x7005
PARAM_LOC_REF = 0x7016
PARAM_LIMIT_SPD = 0x7017


def private_ext_id(comm_type: int, data2: int, data1: int) -> int:
    return ((comm_type & 0x1F) << 24) | ((data2 & 0xFFFF) << 8) | (data1 & 0xFF)


def parse_ros_command(data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'raw_data': data.hex().upper(),
        'dlc': len(data),
    }
    if not data:
        payload.update({'valid': False, 'detail': 'empty_command'})
        return payload

    cmd = data[0]
    payload['cmd'] = cmd
    if cmd == 0x03 and len(data) >= 8:
        joint_id = data[1]
        deg_x10 = int.from_bytes(data[2:4], 'little', signed=True)
        rpm = int.from_bytes(data[4:6], 'little', signed=True)
        torque_ma = int.from_bytes(data[6:8], 'little', signed=True)
        payload.update({
            'valid': True,
            'kind': 'set_target',
            'joint_id': joint_id,
            'target_deg': deg_x10 / 10.0,
            'target_rad': math.radians(deg_x10 / 10.0),
            'rpm': rpm,
            'torque_ma': torque_ma,
        })
        return payload
    if cmd == 0x02 and len(data) >= 2:
        payload.update({
            'valid': True,
            'kind': 'stop',
            'joint_id': data[1],
        })
        return payload

    payload.update({'valid': False, 'kind': f'cmd_0x{cmd:02X}', 'detail': 'unsupported_or_short_command'})
    return payload


def parse_param_write(data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {'raw_data': data.hex().upper(), 'valid': len(data) >= 8}
    if len(data) < 8:
        payload['detail'] = 'short_param_write'
        return payload
    index = int.from_bytes(data[0:2], 'little', signed=False)
    value_u32 = int.from_bytes(data[4:8], 'little', signed=False)
    value_f32 = struct.unpack('<f', data[4:8])[0]
    payload.update({
        'index': index,
        'index_hex': f'0x{index:04X}',
        'name': {
            PARAM_RUN_MODE: 'run_mode',
            PARAM_LIMIT_SPD: 'limit_spd',
            PARAM_LOC_REF: 'loc_ref',
        }.get(index, 'unknown'),
        'value_u32': value_u32,
        'value_f32': value_f32,
    })
    return payload


def private_frame_fields(can_id: int) -> tuple[int, int, int]:
    return (can_id >> 24) & 0x1F, (can_id >> 8) & 0xFFFF, can_id & 0xFF


def summarize_m33_status(samples: list[dict[str, object]]) -> dict[str, object]:
    if not samples:
        return {'count': 0, 'first': None, 'latest': None, 'delta_position_rad': None, 'delta_position_deg': None}
    first = samples[0]
    latest = samples[-1]
    first_position = first.get('position')
    latest_position = latest.get('position')
    delta_rad = None
    delta_deg = None
    if isinstance(first_position, (int, float)) and isinstance(latest_position, (int, float)):
        delta_rad = float(latest_position) - float(first_position)
        delta_deg = math.degrees(delta_rad)
    return {
        'count': len(samples),
        'first': first,
        'latest': latest,
        'delta_position_rad': delta_rad,
        'delta_position_deg': delta_deg,
    }


def build_motion_test_report(
    candump_path: str | Path,
    motor_id: int,
    joint_id: int | None = None,
    m33_status_slot: int | None = None,
) -> dict[str, object]:
    source = Path(candump_path).expanduser()
    if m33_status_slot is None:
        m33_status_slot = max(0, motor_id - 1)

    ros_commands: list[dict[str, object]] = []
    target_commands: list[dict[str, object]] = []
    stop_commands: list[dict[str, object]] = []
    param_writes: list[dict[str, object]] = []
    m33_motor_samples: list[dict[str, object]] = []
    stop_private_frames = 0
    mit_control_frames = 0
    psoc_status_frames = 0
    total_lines = 0
    parsed_frames = 0

    with source.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            total_lines += 1
            frame = parse_candump_line(line)
            if frame is None:
                continue
            parsed_frames += 1
            can_id = int(frame['can_id'])
            data = frame['data']
            if not isinstance(data, bytes):
                continue

            if can_id == ROS_CMD_ID:
                command = parse_ros_command(data)
                command['relative_time_s'] = frame['relative_time_s']
                ros_commands.append(command)
                if command.get('kind') == 'set_target' and (joint_id is None or command.get('joint_id') == joint_id):
                    target_commands.append(command)
                if command.get('kind') == 'stop' and (joint_id is None or command.get('joint_id') == joint_id):
                    stop_commands.append(command)
                continue

            if can_id == PSOC_STATUS_ID:
                psoc_status_frames += 1
                continue

            if M33_MOTOR_STATUS_BASE_ID <= can_id <= M33_MOTOR_STATUS_MAX_ID and can_id == M33_MOTOR_STATUS_BASE_ID + m33_status_slot:
                status = parse_m33_motor_status_frame(can_id, data)
                if status.get('valid') is True and status.get('motor_id') == motor_id:
                    status = dict(status)
                    status['relative_time_s'] = frame['relative_time_s']
                    m33_motor_samples.append(status)
                continue

            comm_type, data2, data1 = private_frame_fields(can_id)
            if data1 != motor_id:
                continue
            if comm_type == PRIVATE_PARAM_WRITE_TYPE and data2 == PRIVATE_MASTER_ID:
                param = parse_param_write(data)
                param['relative_time_s'] = frame['relative_time_s']
                param['raw_can_id'] = f'0x{can_id:08X}'
                param_writes.append(param)
            elif comm_type == PRIVATE_STOP_TYPE and data2 == PRIVATE_MASTER_ID:
                stop_private_frames += 1
            elif comm_type == PRIVATE_MIT_CONTROL_TYPE:
                mit_control_frames += 1

    param_names = [item.get('name') for item in param_writes]
    expected_csp_param_names = ['run_mode', 'limit_spd', 'loc_ref']
    has_expected_csp_sequence = all(name in param_names for name in expected_csp_param_names)
    m33_summary = summarize_m33_status(m33_motor_samples)

    report = {
        'schema_version': 'rehab_arm_motion_test_report_v1',
        'source_log': str(source),
        'motor_id': motor_id,
        'joint_id': joint_id,
        'm33_status_slot': m33_status_slot,
        'total_lines': total_lines,
        'parsed_frames': parsed_frames,
        'ros_commands': ros_commands,
        'target_command_count': len(target_commands),
        'stop_command_count': len(stop_commands),
        'private_param_writes': param_writes,
        'private_stop_frame_count': stop_private_frames,
        'mit_control_frame_count': mit_control_frames,
        'psoc_status_frame_count': psoc_status_frames,
        'm33_motor_status': m33_summary,
        'has_expected_csp_sequence': has_expected_csp_sequence,
        'no_legacy_mit_control': mit_control_frames == 0,
        'stop_observed': bool(stop_commands and stop_private_frames),
        'control_boundary': 'offline_log_analysis_not_motion_permission',
        'safety_note': 'This report only analyzes a recorded candump log. It does not connect to CAN or command motors.',
    }
    report['ok'] = bool(target_commands) and has_expected_csp_sequence and report['no_legacy_mit_control'] and report['stop_observed']
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build a formal motion-test report from a candump -L log.')
    parser.add_argument('candump_path')
    parser.add_argument('--motor-id', type=int, required=True)
    parser.add_argument('--joint-id', type=int)
    parser.add_argument('--m33-status-slot', type=int)
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--output', help='Optional JSON output path')
    args = parser.parse_args(argv)

    report = build_motion_test_report(
        args.candump_path,
        motor_id=args.motor_id,
        joint_id=args.joint_id,
        m33_status_slot=args.m33_status_slot,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
