#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.vla_candidate_gate import (
        build_example_vla_plan_candidate,
        validate_vla_plan_candidate,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.vla_candidate_gate import (
        build_example_vla_plan_candidate,
        validate_vla_plan_candidate,
    )


def load_json(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('candidate JSON root must be an object')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate a VLA plan candidate before MuJoCo dry-run or operator review.',
    )
    parser.add_argument('--candidate', help='Existing vla_plan_candidate_v1 JSON file to validate')
    parser.add_argument('--example', action='store_true', help='Validate a built-in safe dry-run example candidate')
    parser.add_argument('--output-example', help='Write the built-in example candidate JSON to a file')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        if args.candidate:
            payload = load_json(args.candidate)
        else:
            payload = build_example_vla_plan_candidate()
        if args.output_example:
            target = Path(args.output_example).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        report = validate_vla_plan_candidate(payload)
    except Exception as exc:
        report = {
            'schema_version': 'vla_candidate_gate_report_v1',
            'ok': False,
            'error_count': 1,
            'warning_count': 0,
            'errors': [str(exc)],
            'warnings': [],
            'allowed_next_steps': [],
            'forbidden_next_steps': [
                'publish_joint_trajectory',
                'send_can_frame',
                'set_motor_current',
                'set_motor_torque',
                'override_m33_safety',
            ],
            'control_boundary': 'vla_candidate_gate_only_not_motion_permission',
        }

    print(json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=args.pretty,
        separators=None if args.pretty else (',', ':'),
    ))
    return 0 if report.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())
