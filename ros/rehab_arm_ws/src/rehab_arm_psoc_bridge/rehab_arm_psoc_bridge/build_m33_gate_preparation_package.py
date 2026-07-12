#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.m33_gate_preparation import build_m33_gate_preparation_package
    from rehab_arm_psoc_bridge.operator_review import build_operator_review_record
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.m33_gate_preparation import build_m33_gate_preparation_package
    from rehab_arm_psoc_bridge.operator_review import build_operator_review_record


def _load_json(path: str | None) -> dict[str, object] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path} root must be an object')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build an M33 gate preparation package after operator review and live safety checks.',
    )
    parser.add_argument('--operator-review', help='operator_review_record_v1 JSON')
    parser.add_argument('--psoc-status', help='Parsed PSoC safety_state JSON')
    parser.add_argument('--fresh-motor-age-sec', type=float)
    parser.add_argument('--fresh-motor-count', type=int, default=0)
    parser.add_argument('--motor-feedback-timeout-sec', type=float, default=1.0)
    parser.add_argument('--allow-bench-motion', action='store_true')
    parser.add_argument('--example', action='store_true')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    review = _load_json(args.operator_review)
    if review is None:
        review = build_operator_review_record(
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            session_id='session_m33_gate',
            reviewer_id='operator_example',
            reviewer_role='operator',
            approved_for_m33_gate_preparation=True,
            source_plan_id='plan_example',
            mujoco_report_id='mujoco_report_example',
        )
    psoc_status = _load_json(args.psoc_status)
    if psoc_status is None and args.example:
        psoc_status = {
            'motion_allowed': True,
            'state': 'ok',
            'control_mode': 'armed',
            'detail': 'none',
            'error_code': 0,
            'protocol_version': 2,
        }

    package = build_m33_gate_preparation_package(
        review,
        psoc_status=psoc_status,
        last_fresh_motor_status_age_sec=args.fresh_motor_age_sec,
        fresh_motor_status_count=args.fresh_motor_count,
        motor_feedback_timeout_sec=args.motor_feedback_timeout_sec,
        allow_bench_motion=args.allow_bench_motion,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if package['ready_for_m33_gate'] else 2


if __name__ == '__main__':
    sys.exit(main())
