#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.rehab_session import build_rehab_session_plan
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.rehab_session import build_rehab_session_plan


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a dry-run rehab session plan.')
    parser.add_argument('--robot-id', default='medical_rehab_arm')
    parser.add_argument('--device-id', default='nanopi_dev')
    parser.add_argument('--training-mode', default='active_assist')
    parser.add_argument('--session-id')
    parser.add_argument('--profile-id')
    parser.add_argument('--profile-version', type=int)
    parser.add_argument('--output')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        plan = build_rehab_session_plan(
            robot_id=args.robot_id,
            device_id=args.device_id,
            training_mode=args.training_mode,
            session_id=args.session_id,
            profile_id=args.profile_id,
            profile_version=args.profile_version,
        )
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

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
    return 0


if __name__ == '__main__':
    sys.exit(main())
