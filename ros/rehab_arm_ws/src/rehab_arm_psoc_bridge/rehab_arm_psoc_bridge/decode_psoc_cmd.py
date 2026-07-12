#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import struct


JOINT_NAMES = {
    0: 'shoulder_lift_joint',
    1: 'elbow_lift_joint',
    2: 'shoulder_abduction_joint',
    3: 'upper_arm_rotation_joint',
    4: 'forearm_rotation_joint',
}


def parse_payload_hex(payload_hex: str) -> bytes:
    cleaned = payload_hex.strip().lower().replace('0x', '').replace(' ', '')
    if len(cleaned) != 16:
        raise ValueError(f'expected 8 payload bytes / 16 hex chars, got {len(cleaned)} chars')
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f'invalid hex payload: {payload_hex}') from exc


def decode_payload(data: bytes) -> dict[str, object]:
    if len(data) != 8:
        raise ValueError(f'expected 8 payload bytes, got {len(data)}')
    cmd = data[0]
    joint_id = data[1]
    deg_x10, rpm, torque_ma = struct.unpack('<hhh', data[2:8])
    target_deg = deg_x10 / 10.0
    target_rad = math.radians(target_deg)
    return {
        'can_id': '0x320',
        'cmd': f'0x{cmd:02X}',
        'joint_id': joint_id,
        'joint_name': JOINT_NAMES.get(joint_id, 'unknown'),
        'deg_x10': deg_x10,
        'target_deg': target_deg,
        'target_rad': target_rad,
        'rpm': rpm,
        'torque_ma': torque_ma,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Decode a NanoPi -> M33 0x320 joint target payload.'
    )
    parser.add_argument('payload_hex', help='8-byte payload, for example 0300390005000000')
    args = parser.parse_args()

    decoded = decode_payload(parse_payload_hex(args.payload_hex))
    for key, value in decoded.items():
        if isinstance(value, float):
            print(f'{key}: {value:.5f}')
        else:
            print(f'{key}: {value}')


if __name__ == '__main__':
    main()
