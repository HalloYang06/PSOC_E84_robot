#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


EXECUTION_ALLOWED_MOTOR_IDS = {3, 7}

MOTOR_PROFILES: dict[int, dict[str, object]] = {
    3: {
        'motor_id': 3,
        'joint_id': 0,
        'joint_name': 'shoulder_lift_joint',
        'vendor': 'Sitaiwei',
        'model': 'CANSimple/ODrive-like',
        'protocol': 'CANSimple',
        'gear_ratio': 48.0,
        'test_status': 'bench_test_allowed',
        'notes': 'Current formal path uses CANSimple/ODrive-like rev units through M33.',
    },
    4: {
        'motor_id': 4,
        'joint_id': 1,
        'joint_name': 'elbow_lift_joint',
        'vendor': 'Lingzu',
        'model': 'RS00',
        'protocol': 'RobStride CSP',
        'gear_ratio': 1.0,
        'test_status': 'configured_not_test_allowed_yet',
        'notes': 'Configured for planning; live bench execution is not allowlisted yet.',
    },
    5: {
        'motor_id': 5,
        'joint_id': 2,
        'joint_name': 'shoulder_abduction_joint',
        'vendor': 'Lingzu',
        'model': 'RS00',
        'protocol': 'RobStride CSP',
        'gear_ratio': 1.0,
        'test_status': 'configured_not_test_allowed_yet',
        'notes': 'Configured for planning; live bench execution is not allowlisted yet.',
    },
    6: {
        'motor_id': 6,
        'joint_id': 3,
        'joint_name': 'upper_arm_rotation_joint',
        'vendor': 'Lingzu',
        'model': 'EL05',
        'protocol': 'RobStride CSP',
        'gear_ratio': 1.0,
        'test_status': 'configured_not_test_allowed_yet',
        'notes': 'Configured for planning; live bench execution is not allowlisted yet.',
    },
    7: {
        'motor_id': 7,
        'joint_id': 4,
        'joint_name': 'forearm_rotation_joint',
        'vendor': 'Lingzu',
        'model': 'EL05',
        'protocol': 'RobStride CSP',
        'gear_ratio': 1.0,
        'test_status': 'bench_test_allowed',
        'notes': 'Motor7 formal M33 path has been bench-validated with CSP parameter writes.',
    },
}


def motor_profile(motor_id: int) -> dict[str, object]:
    try:
        return dict(MOTOR_PROFILES[motor_id])
    except KeyError as exc:
        choices = ', '.join(str(item) for item in sorted(MOTOR_PROFILES))
        raise ValueError(f'unknown motor_id {motor_id}; expected one of: {choices}') from exc


def motor_profiles_payload() -> dict[str, object]:
    return {
        'schema_version': 'rehab_arm_motor_profiles_v1',
        'profiles': {str(key): value for key, value in sorted(MOTOR_PROFILES.items())},
        'execution_allowed_motor_ids': sorted(EXECUTION_ALLOWED_MOTOR_IDS),
        'control_boundary': 'configuration_only_not_motion_permission',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Print the rehab arm motor profile table.')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--output', help='Optional path to write JSON.')
    args = parser.parse_args(argv)

    payload = motor_profiles_payload()
    text = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
