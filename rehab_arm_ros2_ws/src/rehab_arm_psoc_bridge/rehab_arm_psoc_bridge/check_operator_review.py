#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.operator_review import (
        build_operator_review_record,
        validate_operator_review_record,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.operator_review import (
        build_operator_review_record,
        validate_operator_review_record,
    )


def load_json(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('operator review JSON root must be an object')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate an operator review record without granting motion permission.',
    )
    parser.add_argument('--review', help='Existing operator_review_record_v1 JSON file')
    parser.add_argument('--example', action='store_true', help='Validate a built-in approved example')
    parser.add_argument('--robot-id', default='medical_rehab_arm')
    parser.add_argument('--device-id', default='nanopi_dev')
    parser.add_argument('--session-id', default='session_dry_run')
    parser.add_argument('--patient-id', default='patient_dry_run')
    parser.add_argument('--profile-id', default='profile_dry_run')
    parser.add_argument('--reviewer-id', default='operator_dev')
    parser.add_argument('--reviewer-role', default='operator')
    parser.add_argument('--approved', action='store_true')
    parser.add_argument('--source-plan-id', default='vla_plan_dry_run_001')
    parser.add_argument('--mujoco-report-id', default='mujoco_report_dry_run_001')
    parser.add_argument('--output-example')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        if args.review:
            record = load_json(args.review)
        else:
            record = build_operator_review_record(
                robot_id=args.robot_id,
                device_id=args.device_id,
                session_id=args.session_id,
                patient_id=args.patient_id,
                profile_id=args.profile_id,
                reviewer_id=args.reviewer_id,
                reviewer_role=args.reviewer_role,
                approved_for_m33_gate_preparation=args.approved or args.example,
                source_plan_id=args.source_plan_id,
                mujoco_report_id=args.mujoco_report_id,
                notes='dry-run operator review example',
            )
        if args.output_example:
            target = Path(args.output_example).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        report = validate_operator_review_record(record)
    except Exception as exc:
        report = {
            'schema_version': 'operator_review_quality_report_v1',
            'ok': False,
            'error_count': 1,
            'warning_count': 0,
            'errors': [str(exc)],
            'warnings': [],
            'allowed_next_steps': [],
            'forbidden_next_steps': [
                'publish_joint_trajectory_without_m33_gate',
                'send_can_frame',
                'set_motor_current',
                'set_motor_torque',
                'override_m33_safety',
            ],
            'control_boundary': 'operator_review_quality_gate_only_not_motion_permission',
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
