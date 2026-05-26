#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.patient_profile import build_m33_safety_subset, load_patient_profile
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.patient_profile import build_m33_safety_subset, load_patient_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Dry-run export of the M33 safety subset from a Patient Device Profile.',
    )
    parser.add_argument('path', help='Path to patient_device_profile.json')
    parser.add_argument('--output', default='', help='Optional path to write m33_safety_profile_v1 JSON')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    args = parser.parse_args()

    try:
        subset = build_m33_safety_subset(load_patient_profile(args.path))
    except Exception as exc:
        subset = {
            'schema_version': 'm33_safety_profile_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': 'm33_safety_subset_dry_run_only_not_sent',
        }
        print(json.dumps(subset, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    text = json.dumps(
        subset,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (',', ':'),
    )
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if subset.get('ok') is True else 1


if __name__ == '__main__':
    sys.exit(main())
