#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.nanopi_action_pipeline import (
        build_operator_review_request_from_dry_run,
        build_pipeline_from_server_action,
    )
    from rehab_arm_psoc_bridge.server_action_ingress import build_example_server_action_command
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.nanopi_action_pipeline import (
        build_operator_review_request_from_dry_run,
        build_pipeline_from_server_action,
    )
    from rehab_arm_psoc_bridge.server_action_ingress import build_example_server_action_command


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build the NanoPi high-level action pipeline plan from a server VLA-A payload.',
    )
    parser.add_argument('--payload', help='Path to server_to_nanopi_high_level_command_v1 JSON')
    parser.add_argument('--mujoco-report', help='Optional mujoco_dry_run_review_report_v1 JSON')
    parser.add_argument('--example', action='store_true')
    parser.add_argument('--session-id', default='session_action_pipeline')
    parser.add_argument('--output')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    else:
        payload = build_example_server_action_command()

    plan = build_pipeline_from_server_action(payload, session_id=args.session_id)
    output: dict[str, object]
    if args.mujoco_report:
        report = json.loads(Path(args.mujoco_report).read_text(encoding='utf-8'))
        output = {
            'schema_version': 'nanopi_action_pipeline_with_operator_review_request_v1',
            'pipeline_plan': plan,
            'operator_review_request': build_operator_review_request_from_dry_run(plan, report),
            'control_boundary': 'nanopi_pipeline_bundle_only_not_motion_permission',
        }
    else:
        output = plan
    text = json.dumps(
        output,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=args.pretty,
        separators=None if args.pretty else (',', ':'),
    )
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if plan.get('accepted_for_pipeline') else 2


if __name__ == '__main__':
    sys.exit(main())
