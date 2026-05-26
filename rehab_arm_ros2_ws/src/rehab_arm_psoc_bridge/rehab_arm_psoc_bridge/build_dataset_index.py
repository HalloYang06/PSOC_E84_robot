#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import build_dataset_index
    from rehab_arm_psoc_bridge.sync_dry_run import load_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_dataset_index
    from rehab_arm_psoc_bridge.sync_dry_run import load_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build a training/replay dataset index from a rehab arm manifest.',
    )
    parser.add_argument('manifest_path', help='Path to manifest_with_quality.json')
    parser.add_argument('--dataset-id', required=True, help='Stable dataset id')
    parser.add_argument(
        '--purpose',
        default='training_candidate',
        help='Dataset purpose, for example training_candidate, replay_review, or vla_context.',
    )
    parser.add_argument(
        '--allow-missing-quality-report',
        action='store_true',
        help='Allow sessions without quality_report into the dataset index.',
    )
    parser.add_argument('--output', default='', help='Optional output path. Prints JSON when omitted.')
    args = parser.parse_args()

    try:
        index = build_dataset_index(
            load_manifest(args.manifest_path),
            dataset_id=args.dataset_id,
            purpose=args.purpose,
            require_quality_report=not args.allow_missing_quality_report,
        )
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

    text = json.dumps(index, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
