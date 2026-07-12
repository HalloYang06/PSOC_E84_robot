#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import validate_annotation_rows
    from rehab_arm_psoc_bridge.export_annotation_template import load_queue
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import validate_annotation_rows
    from rehab_arm_psoc_bridge.export_annotation_template import load_queue


def load_csv_rows(path: str | Path) -> list[dict[str, object]]:
    with Path(path).expanduser().open('r', encoding='utf-8', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate completed annotation CSV before training export.',
    )
    parser.add_argument('queue_path', help='Path to annotation_queue.json')
    parser.add_argument('csv_path', help='Path to completed annotation CSV')
    parser.add_argument(
        '--approved-status',
        default='approved',
        help='Annotation status value required for training export. Default: approved.',
    )
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output.')
    args = parser.parse_args()

    try:
        report = validate_annotation_rows(
            load_csv_rows(args.csv_path),
            load_queue(args.queue_path),
            approved_status=args.approved_status,
        )
    except Exception as exc:
        report = {
            'schema_version': 'rehab_arm_annotation_validation_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': 'annotation_validation_only_not_motion_permission',
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
