#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import (
        build_recording_quality_report,
        load_jsonl_records,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        build_recording_quality_report,
        load_jsonl_records,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate rehab arm JSONL recording quality.')
    parser.add_argument('path', help='Path to a recorder JSONL file')
    parser.add_argument(
        '--min-joint-messages',
        type=int,
        default=1,
        help='Minimum required /joint_states messages. Default: 1.',
    )
    parser.add_argument(
        '--min-moving-joints',
        type=int,
        default=0,
        help='Minimum joints whose position span must exceed 0.01 rad. Default: 0.',
    )
    parser.add_argument(
        '--require-motor-state',
        action='store_true',
        help='Require at least one /rehab_arm/motor_state message.',
    )
    parser.add_argument(
        '--min-motor-entry-count',
        type=int,
        default=0,
        help='Minimum motor entries required in every motor_state message. Default: 0.',
    )
    parser.add_argument(
        '--allow-motion-allowed-true',
        action='store_true',
        help='Allow safety_state payloads with motion_allowed=true.',
    )
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output.')
    args = parser.parse_args()

    if args.min_joint_messages < 0:
        parser.error('--min-joint-messages must be >= 0')
    if args.min_moving_joints < 0:
        parser.error('--min-moving-joints must be >= 0')
    if args.min_motor_entry_count < 0:
        parser.error('--min-motor-entry-count must be >= 0')

    try:
        report = build_recording_quality_report(
            load_jsonl_records(args.path),
            min_joint_messages=args.min_joint_messages,
            min_moving_joints=args.min_moving_joints,
            require_motor_state=args.require_motor_state,
            min_motor_entry_count=args.min_motor_entry_count,
            allow_motion_allowed_true=args.allow_motion_allowed_true,
        )
    except Exception as exc:
        report = {
            'schema_version': 'rehab_arm_recording_quality_v1',
            'ok': False,
            'errors': [str(exc)],
            'warnings': [],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    if args.pretty:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, separators=(',', ':')))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
