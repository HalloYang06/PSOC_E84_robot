#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import (
        make_annotation_template_rows,
        write_csv_rows,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        make_annotation_template_rows,
        write_csv_rows,
    )


def load_queue(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        queue = json.load(handle)
    if not isinstance(queue, dict):
        raise ValueError('annotation queue root must be a JSON object')
    return queue


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Export a CSV annotation template from rehab_arm_annotation_queue_v1.',
    )
    parser.add_argument('queue_path', help='Path to annotation_queue.json')
    parser.add_argument('--output', required=True, help='CSV output path')
    args = parser.parse_args()

    try:
        rows, fields = make_annotation_template_rows(load_queue(args.queue_path))
        write_csv_rows(args.output, rows, fields)
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

    print(json.dumps({
        'schema_version': 'rehab_arm_annotation_template_export_v1',
        'ok': True,
        'row_count': len(rows),
        'field_count': len(fields),
        'output': str(Path(args.output).expanduser()),
        'control_boundary': 'annotation_template_only_not_motion_permission',
    }, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
