#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import struct


CMD_SET_TARGET = 0x03

JOINT_IDS = {
    'shoulder_lift_joint': 0,
    'elbow_lift_joint': 1,
    'shoulder_abduction_joint': 2,
    'upper_arm_rotation_joint': 3,
    'forearm_rotation_joint': 4,
}

LIMITS = {
    'shoulder_lift_joint': (-0.70, 1.40),
    'elbow_lift_joint': (0.00, 1.80),
    'shoulder_abduction_joint': (-0.45, 0.80),
    'upper_arm_rotation_joint': (-1.20, 1.20),
    'forearm_rotation_joint': (-1.20, 1.20),
}


def encode_target(joint_name: str, position_rad: float, rpm: int, torque_ma: int) -> bytes:
    if joint_name not in JOINT_IDS:
        known = ', '.join(JOINT_IDS)
        raise ValueError(f'unknown joint {joint_name!r}; known joints: {known}')
    if not math.isfinite(position_rad):
        raise ValueError('position_rad must be finite')
    low, high = LIMITS[joint_name]
    if position_rad < low or position_rad > high:
        raise ValueError(
            f'{joint_name} position {position_rad:.5f} rad outside [{low:.5f}, {high:.5f}]'
        )
    deg_x10 = int(math.degrees(position_rad) * 10.0)
    joint_id = JOINT_IDS[joint_name]
    return bytes([CMD_SET_TARGET, joint_id]) + struct.pack('<hhh', deg_x10, rpm, torque_ma)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Encode a NanoPi -> M33 0x320 joint target payload without sending CAN.'
    )
    parser.add_argument('joint_name', choices=sorted(JOINT_IDS), help='ROS joint name')
    parser.add_argument('position_rad', type=float, help='target position in radians')
    parser.add_argument('--rpm', type=int, default=5, help='suggested speed, default: 5')
    parser.add_argument('--torque-ma', type=int, default=0, help='suggested torque/current, default: 0')
    args = parser.parse_args()

    try:
        payload = encode_target(args.joint_name, args.position_rad, args.rpm, args.torque_ma)
    except ValueError as exc:
        parser.error(str(exc))
    deg_x10 = struct.unpack('<h', payload[2:4])[0]
    print(f'can_id: 0x320')
    print(f'joint_name: {args.joint_name}')
    print(f'joint_id: {JOINT_IDS[args.joint_name]}')
    print(f'position_rad: {args.position_rad:.5f}')
    print(f'target_deg: {math.degrees(args.position_rad):.5f}')
    print(f'deg_x10: {deg_x10}')
    print(f'rpm: {args.rpm}')
    print(f'torque_ma: {args.torque_ma}')
    print(f'payload: {payload.hex().upper()}')


if __name__ == '__main__':
    main()
