#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.patient_profile import (
        build_patient_profile_release_gate,
        load_patient_profile,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.patient_profile import (  # type: ignore[no-redef]
        build_patient_profile_release_gate,
        load_patient_profile,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Check whether a Patient Device Profile may be released to M33, App BLE, or NanoPi cache.',
    )
    parser.add_argument('path', help='Path to patient_device_profile.json')
    parser.add_argument('--target', choices=['m33', 'app_ble', 'nanopi_cache'], default='m33')
    parser.add_argument('--approved-by', default='', help='Required for --target app_ble')
    parser.add_argument('--approved-at', default='', help='Required for --target app_ble')
    parser.add_argument('--expires-at', default='', help='Required for --target app_ble')
    parser.add_argument('--output', default='', help='Optional output path')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    try:
        report = build_patient_profile_release_gate(
            load_patient_profile(args.path),
            target=args.target,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            expires_at=args.expires_at,
        )
    except Exception as exc:
        report = {
            'schema_version': 'patient_profile_release_gate_v1',
            'ok': False,
            'target': args.target,
            'errors': [str(exc)],
            'control_boundary': 'release_gate_only_not_motion_permission',
        }
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    text = json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (',', ':'),
    )
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report.get('ok') is True else 1


if __name__ == '__main__':
    sys.exit(main())
