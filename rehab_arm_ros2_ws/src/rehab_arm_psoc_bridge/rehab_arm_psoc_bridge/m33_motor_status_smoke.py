#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.psoc_motor_status import (
        M33_MOTOR_STATUS_MARKER,
        MOTOR_STATUS_FLAG_ENABLED,
        make_m33_motor_state_payload,
        parse_m33_motor_status_frame,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.psoc_motor_status import (
        M33_MOTOR_STATUS_MARKER,
        MOTOR_STATUS_FLAG_ENABLED,
        make_m33_motor_state_payload,
        parse_m33_motor_status_frame,
    )


CAN_FRAME_FMT = '=IB3x8s'
CAN_SFF_MASK = 0x000007FF
CONTROL_BOUNDARY = 'synthetic_m33_motor_status_telemetry_only_not_motor_command'


def build_m33_motor_status_payload(
    seq: int,
    motor_id: int,
    position_rad: float,
    velocity_rad_s: float,
    temperature_c: int | None,
    flags: int = MOTOR_STATUS_FLAG_ENABLED,
) -> bytes:
    position_mrad = int(position_rad * 1000.0)
    velocity_drad_s = int(velocity_rad_s * 10.0)
    if not -32768 <= position_mrad <= 32767:
        raise ValueError('position_rad is outside int16 mrad smoke-frame range')
    if not -128 <= velocity_drad_s <= 127:
        raise ValueError('velocity_rad_s is outside int8 0.1rad/s smoke-frame range')
    if temperature_c is None:
        temperature_raw = 0xFF
    elif 0 <= temperature_c <= 254:
        temperature_raw = int(temperature_c)
    else:
        raise ValueError('temperature_c must be 0..254 or None')
    return bytes([
        M33_MOTOR_STATUS_MARKER,
        seq & 0xFF,
        motor_id & 0xFF,
        flags & 0xFF,
    ]) + int(position_mrad).to_bytes(2, 'little', signed=True) + bytes([
        velocity_drad_s & 0xFF,
        temperature_raw,
    ])


def build_smoke_frames(seq: int = 1) -> list[dict[str, object]]:
    samples = [
        {'can_id': 0x330, 'motor_id': 3, 'position_rad': 0.050, 'velocity_rad_s': 0.0, 'temperature_c': None},
        {'can_id': 0x331, 'motor_id': 7, 'position_rad': -0.080, 'velocity_rad_s': 0.1, 'temperature_c': 34},
    ]
    frames: list[dict[str, object]] = []
    for offset, sample in enumerate(samples):
        data = build_m33_motor_status_payload(
            seq=seq + offset,
            motor_id=int(sample['motor_id']),
            position_rad=float(sample['position_rad']),
            velocity_rad_s=float(sample['velocity_rad_s']),
            temperature_c=sample['temperature_c'],
        )
        can_id = int(sample['can_id'])
        frames.append({
            'can_id': can_id,
            'can_id_hex': f'0x{can_id:03X}',
            'data': data,
            'data_hex': data.hex().upper(),
            'cansend': f'{can_id:03X}#{data.hex().upper()}',
        })
    return frames


def pack_standard_can_frame(can_id: int, data: bytes) -> bytes:
    return struct.pack(CAN_FRAME_FMT, can_id & CAN_SFF_MASK, len(data), data[:8].ljust(8, b'\x00'))


def send_smoke_frames(interface: str, frames: list[dict[str, object]], gap_sec: float) -> None:
    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    try:
        sock.bind((interface,))
        for frame in frames:
            sock.send(pack_standard_can_frame(int(frame['can_id']), bytes(frame['data'])))
            time.sleep(gap_sec)
    finally:
        sock.close()


def build_smoke_report(
    frames: list[dict[str, object]],
    robot_id: str,
    device_id: str,
    execute: bool,
    interface: str,
) -> dict[str, object]:
    parsed = [
        parse_m33_motor_status_frame(int(frame['can_id']), bytes(frame['data']))
        for frame in frames
    ]
    expected_payload = make_m33_motor_state_payload(
        frames=parsed,
        robot_id=robot_id,
        device_id=device_id,
        now=0.0,
    )
    return {
        'ok': True,
        'execute': execute,
        'interface': interface,
        'frame_count': len(frames),
        'frames': [
            {
                'can_id': frame['can_id_hex'],
                'data': frame['data_hex'],
                'cansend': frame['cansend'],
            }
            for frame in frames
        ],
        'expected_motor_state_payload': expected_payload,
        'control_boundary': CONTROL_BOUNDARY,
        'safety_note': (
            'Synthetic 0x330~0x337 telemetry only. This tool never sends 0x320, '
            'does not command M33, and does not authorize motor motion.'
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Dry-run or send synthetic M33 0x330~0x337 motor telemetry frames.'
    )
    parser.add_argument('--interface', default='vcan0', help='SocketCAN interface for --execute.')
    parser.add_argument('--robot-id', default='rehab-arm-alpha')
    parser.add_argument('--device-id', default='nanopi-m5')
    parser.add_argument('--seq', type=int, default=1)
    parser.add_argument('--gap-sec', type=float, default=0.02)
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually send synthetic telemetry frames. Without this flag, only print a dry-run report.',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.gap_sec < 0:
        raise SystemExit('--gap-sec must be >= 0')
    frames = build_smoke_frames(seq=args.seq)
    if args.execute:
        send_smoke_frames(args.interface, frames, args.gap_sec)
    report = build_smoke_report(frames, args.robot_id, args.device_id, args.execute, args.interface)
    print(json.dumps(report, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
