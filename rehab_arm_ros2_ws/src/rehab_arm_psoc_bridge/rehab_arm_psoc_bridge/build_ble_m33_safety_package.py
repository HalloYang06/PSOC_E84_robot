#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.patient_profile import build_ble_m33_safety_package, load_patient_profile
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.patient_profile import build_ble_m33_safety_package, load_patient_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Dry-run build of an App BLE package carrying the M33 safety subset.',
    )
    parser.add_argument('path', help='Path to approved/active patient_device_profile.json')
    parser.add_argument('--package-id', default='', help='Optional package id')
    parser.add_argument('--approved-by', required=True, help='Reviewer or approver id')
    parser.add_argument('--approved-at', required=True, help='Approval timestamp')
    parser.add_argument('--expires-at', required=True, help='Package expiry timestamp')
    parser.add_argument('--output', default='', help='Optional output path')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    args = parser.parse_args()

    try:
        package = build_ble_m33_safety_package(
            load_patient_profile(args.path),
            package_id=args.package_id,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            expires_at=args.expires_at,
        )
    except Exception as exc:
        package = {
            'schema_version': 'ble_m33_safety_package_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': 'ble_package_dry_run_only_not_sent',
        }
        print(json.dumps(package, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    text = json.dumps(
        package,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (',', ':'),
    )
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if package.get('ok') is True else 1


if __name__ == '__main__':
    sys.exit(main())
