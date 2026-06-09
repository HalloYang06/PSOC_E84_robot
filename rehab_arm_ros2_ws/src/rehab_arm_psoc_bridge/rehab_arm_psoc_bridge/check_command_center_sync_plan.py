#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.command_center_sync import (
        DEFAULT_BASE_URL,
        build_command_center_sync_plan,
        validate_command_center_sync_plan,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.command_center_sync import (
        DEFAULT_BASE_URL,
        build_command_center_sync_plan,
        validate_command_center_sync_plan,
    )


def load_json(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('plan JSON root must be an object')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate a command-center sync dry-run plan without network or CAN access.',
    )
    parser.add_argument('--plan', help='Existing command_center_sync_plan_v1 JSON file to validate')
    parser.add_argument('--robot-id', default='medical_rehab_arm')
    parser.add_argument('--device-id', default='nanopi_dev')
    parser.add_argument('--tenant-id', default='tenant_rehab_lab')
    parser.add_argument('--workspace-id', default='workspace_rehab_lab')
    parser.add_argument('--user-id', default='operator_dev')
    parser.add_argument('--role', default='operator')
    parser.add_argument('--patient-id', default='patient_dry_run')
    parser.add_argument('--session-id', default='session_dry_run')
    parser.add_argument('--profile-id', default='profile_dry_run')
    parser.add_argument('--profile-version', type=int)
    parser.add_argument('--training-mode', default='active_assist')
    parser.add_argument('--language-goal', default='协助患者完成一次缓慢肘屈曲训练')
    parser.add_argument('--prompt-text', default='开始训练')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        if args.plan:
            plan = load_json(args.plan)
        else:
            plan = build_command_center_sync_plan(
                robot_id=args.robot_id,
                device_id=args.device_id,
                tenant_id=args.tenant_id,
                workspace_id=args.workspace_id,
                user_id=args.user_id,
                role=args.role,
                patient_id=args.patient_id,
                session_id=args.session_id,
                profile_id=args.profile_id,
                profile_version=args.profile_version,
                training_mode=args.training_mode,
                language_goal=args.language_goal,
                prompt_text=args.prompt_text,
                base_url=args.base_url,
            )
        report = validate_command_center_sync_plan(plan)
    except Exception as exc:
        report = {
            'schema_version': 'command_center_sync_quality_report_v1',
            'ok': False,
            'error_count': 1,
            'warning_count': 0,
            'errors': [str(exc)],
            'warnings': [],
            'control_boundary': 'quality_gate_only_not_motion_permission',
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
