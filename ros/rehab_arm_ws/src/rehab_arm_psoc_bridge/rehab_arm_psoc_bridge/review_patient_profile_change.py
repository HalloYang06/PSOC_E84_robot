#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.patient_profile import (
        build_patient_profile_change_report,
        load_patient_profile,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.patient_profile import (
        build_patient_profile_change_report,
        load_patient_profile,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Review safety-relevant changes between two Patient Device Profiles.',
    )
    parser.add_argument('old_profile_path', help='Path to old active/approved profile JSON')
    parser.add_argument('new_profile_path', help='Path to new draft profile JSON')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    args = parser.parse_args()

    try:
        report = build_patient_profile_change_report(
            load_patient_profile(args.old_profile_path),
            load_patient_profile(args.new_profile_path),
        )
    except Exception as exc:
        report = {
            'schema_version': 'patient_device_profile_change_report_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': 'profile_change_review_only_not_motion_permission',
        }
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    print(json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (',', ':'),
    ))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
