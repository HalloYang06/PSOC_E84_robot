#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.mujoco_dry_run_review import build_mujoco_dry_run_review_plan
    from rehab_arm_psoc_bridge.vla_candidate_gate import build_example_vla_plan_candidate
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.mujoco_dry_run_review import build_mujoco_dry_run_review_plan
    from rehab_arm_psoc_bridge.vla_candidate_gate import build_example_vla_plan_candidate


def load_json(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('candidate JSON root must be an object')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build a MuJoCo dry-run review plan from a VLA candidate without publishing ROS or CAN.',
    )
    parser.add_argument('--candidate', help='Existing vla_plan_candidate_v1 JSON file')
    parser.add_argument('--example', action='store_true', help='Use built-in safe example VLA candidate')
    parser.add_argument('--robot-id', default='medical_rehab_arm')
    parser.add_argument('--device-id', default='nanopi_dev')
    parser.add_argument('--session-id', default='session_dry_run')
    parser.add_argument('--sim-model', default='medical_arm_6dof.xml')
    parser.add_argument('--command-topic', default='/sim/medical_arm/trajectory_candidate')
    parser.add_argument('--state-topic', default='/sim/medical_arm/joint_states')
    parser.add_argument('--output')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        candidate = load_json(args.candidate) if args.candidate else build_example_vla_plan_candidate()
        plan = build_mujoco_dry_run_review_plan(
            candidate,
            robot_id=args.robot_id,
            device_id=args.device_id,
            session_id=args.session_id,
            sim_model=args.sim_model,
            command_topic=args.command_topic,
            state_topic=args.state_topic,
        )
    except Exception as exc:
        plan = {
            'schema_version': 'mujoco_dry_run_review_plan_v1',
            'accepted_for_review': False,
            'errors': [str(exc)],
            'allowed_next_steps': [],
            'forbidden_next_steps': [
                'publish_joint_trajectory',
                'send_can_frame',
                'set_motor_current',
                'set_motor_torque',
                'override_m33_safety',
            ],
            'control_boundary': 'mujoco_dry_run_plan_only_not_motion_permission',
        }

    text = json.dumps(
        plan,
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
    return 0 if plan.get('accepted_for_review') else 2


if __name__ == '__main__':
    sys.exit(main())
