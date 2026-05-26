#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import build_annotation_queue
    from rehab_arm_psoc_bridge.sync_dry_run import load_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_annotation_queue
    from rehab_arm_psoc_bridge.sync_dry_run import load_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build an offline annotation queue from a rehab arm manifest.',
    )
    parser.add_argument('manifest_path', help='Path to manifest_with_quality.json')
    parser.add_argument(
        '--output',
        default='',
        help='Optional output path. Prints JSON to stdout when omitted.',
    )
    parser.add_argument(
        '--label',
        action='append',
        dest='labels',
        default=None,
        help='Recommended annotation label name. May be repeated.',
    )
    parser.add_argument(
        '--allow-missing-quality-report',
        action='store_true',
        help='Allow sessions without quality_report into the queue.',
    )
    args = parser.parse_args()

    try:
        queue = build_annotation_queue(
            load_manifest(args.manifest_path),
            recommended_labels=args.labels,
            require_quality_report=not args.allow_missing_quality_report,
        )
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

    text = json.dumps(queue, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
