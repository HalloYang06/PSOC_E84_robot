#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import build_recording_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_recording_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a local manifest for rehab arm JSONL logs.')
    parser.add_argument('log_dir', help='Directory containing recorder JSONL files')
    parser.add_argument(
        '--output',
        default='',
        help='Optional path to write the manifest JSON. Prints to stdout when omitted.',
    )
    parser.add_argument(
        '--include-summary',
        action='store_true',
        help='Embed per-session recording summaries for dashboards and review tools.',
    )
    args = parser.parse_args()

    manifest = build_recording_manifest(args.log_dir, include_summary=args.include_summary)
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
