#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (
        MOTOR_GEAR_RATIO_BY_ID,
        decode_private_active_report,
        parse_candump_line,
    )
    from rehab_arm_psoc_bridge.psoc_motor_status import parse_m33_motor_status_frame
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (
        MOTOR_GEAR_RATIO_BY_ID,
        decode_private_active_report,
        parse_candump_line,
    )
    from rehab_arm_psoc_bridge.psoc_motor_status import parse_m33_motor_status_frame


PRIVATE_MASTER_ID = 0xFD
PRIVATE_TYPE_CTRL = 0x01
PRIVATE_TYPE_ACTIVE_REPORT = 0x18
ROBSTRIDE_POSITION_MIN_RAD = -12.57
ROBSTRIDE_POSITION_MAX_RAD = 12.57
M33_MOTOR_STATUS_BASE_ID = 0x330


def _uint16_to_float(value: int, low: float, high: float) -> float:
    return float(value) * (high - low) / 65535.0 + low


def _private_fields(can_id: int) -> tuple[int, int, int]:
    return (can_id >> 24) & 0x1F, (can_id >> 8) & 0xFFFF, can_id & 0xFF


def _summarize_raw_samples(samples: list[dict[str, object]]) -> dict[str, object]:
    if not samples:
        return {
            'count': 0,
            'latest': None,
            'raw_position_delta_u16': None,
            'robstride_position_delta_rad_untrusted': None,
        }

    first = samples[0]
    latest = samples[-1]
    first_raw = int(first['raw_position_u16'])
    latest_raw = int(latest['raw_position_u16'])
    delta_raw = latest_raw - first_raw
    first_rad = _uint16_to_float(first_raw, ROBSTRIDE_POSITION_MIN_RAD, ROBSTRIDE_POSITION_MAX_RAD)
    latest_rad = _uint16_to_float(latest_raw, ROBSTRIDE_POSITION_MIN_RAD, ROBSTRIDE_POSITION_MAX_RAD)

    latest_summary = {
        'relative_time_s': latest['relative_time_s'],
        'raw_can_id': latest['raw_can_id'],
        'raw_data': latest['raw_data'],
        'raw_position_u16': latest_raw,
        'raw_velocity_u16': latest['raw_velocity_u16'],
        'raw_torque_u16': latest['raw_torque_u16'],
        'raw_temperature_u16': latest['raw_temperature_u16'],
        'robstride_position_rad_untrusted': latest_rad,
    }

    return {
        'count': len(samples),
        'first': {
            'relative_time_s': first['relative_time_s'],
            'raw_position_u16': first_raw,
            'robstride_position_rad_untrusted': first_rad,
        },
        'latest': latest_summary,
        'raw_position_delta_u16': delta_raw,
        'robstride_position_delta_rad_untrusted': latest_rad - first_rad,
    }


def analyze_calibration_observation(
    candump_path: str | Path,
    motor_id: int = 7,
    m33_status_slot: int | None = None,
) -> dict[str, object]:
    source = Path(candump_path).expanduser()
    if m33_status_slot is None:
        m33_status_slot = motor_id - 1

    raw_samples: list[dict[str, object]] = []
    m33_status_samples: list[dict[str, object]] = []
    active_report_enable_frames = 0
    active_report_disable_frames = 0
    motor_control_frames = 0
    total_frames = 0
    parsed_frames = 0
    ignored_lines = 0

    with source.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            total_frames += 1
            frame = parse_candump_line(line)
            if frame is None:
                ignored_lines += 1
                continue
            parsed_frames += 1
            can_id = int(frame['can_id'])
            data = frame['data']
            if not isinstance(data, bytes):
                continue

            comm_type, data2, data1 = _private_fields(can_id)
            if data1 == motor_id and comm_type == PRIVATE_TYPE_CTRL:
                motor_control_frames += 1
            if data1 == motor_id and comm_type == PRIVATE_TYPE_ACTIVE_REPORT and data2 == PRIVATE_MASTER_ID:
                if len(data) >= 7 and data[6] != 0:
                    active_report_enable_frames += 1
                else:
                    active_report_disable_frames += 1

            raw = decode_private_active_report(frame)
            if raw and raw.get('motor_id') == motor_id:
                raw = dict(raw)
                raw['relative_time_s'] = frame['relative_time_s']
                raw_samples.append(raw)
                continue

            if can_id == M33_MOTOR_STATUS_BASE_ID + m33_status_slot:
                status = parse_m33_motor_status_frame(can_id, data)
                if status.get('valid') is True and status.get('motor_id') == motor_id:
                    status = dict(status)
                    status['relative_time_s'] = frame['relative_time_s']
                    m33_status_samples.append(status)

    latest_m33 = m33_status_samples[-1] if m33_status_samples else None
    gear_ratio = MOTOR_GEAR_RATIO_BY_ID.get(motor_id)
    observation_ok = bool(raw_samples or m33_status_samples)
    no_motion_control_frames = motor_control_frames == 0

    result = {
        'schema_version': 'rehab_arm_calibration_observation_v1',
        'source_log': str(source),
        'motor_id': motor_id,
        'm33_status_slot': m33_status_slot,
        'joint_name_hint': latest_m33.get('joint_name') if isinstance(latest_m33, dict) else None,
        'gear_ratio': gear_ratio,
        'total_lines': total_frames,
        'parsed_frames': parsed_frames,
        'ignored_lines': ignored_lines,
        'active_report_enable_frames': active_report_enable_frames,
        'active_report_disable_frames': active_report_disable_frames,
        'raw_active_report': _summarize_raw_samples(raw_samples),
        'm33_status': {
            'count': len(m33_status_samples),
            'latest': latest_m33,
        },
        'motor_control_frames': motor_control_frames,
        'no_motion_control_frames': no_motion_control_frames,
        'observation_ok': observation_ok,
        'safe_to_use_as_motion_proof': False,
        'notes': [
            'Telemetry observation only; do not use this as proof that the joint is calibrated.',
            'robstride_position_* fields use the official private-protocol +/-12.57 rad mapping, but this project has not yet proven that field equals physical output angle.',
            'A valid zero calibration still requires human-confirmed mechanical zero, direction, small-angle validation, and M33 limit review.',
        ],
    }
    result['ok'] = observation_ok and no_motion_control_frames
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Summarize a telemetry-only motor calibration candump capture.',
    )
    parser.add_argument('candump_path', help='Path to a candump -L log')
    parser.add_argument('--motor-id', type=int, default=7)
    parser.add_argument('--m33-status-slot', type=int, help='0-based M33 0x330 status slot; defaults to motor_id-1')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args(argv)

    report = analyze_calibration_observation(
        args.candump_path,
        motor_id=args.motor_id,
        m33_status_slot=args.m33_status_slot,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
