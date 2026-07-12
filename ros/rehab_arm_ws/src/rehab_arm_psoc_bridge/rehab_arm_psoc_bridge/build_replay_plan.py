#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import build_replay_plan, load_jsonl_records
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_replay_plan, load_jsonl_records


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build an offline replay plan from a rehab arm JSONL recording.',
    )
    parser.add_argument('path', help='Path to a recorder JSONL file')
    parser.add_argument(
        '--topic',
        action='append',
        default=[],
        help='Topic to include. Repeat for multiple topics. Default: include all topic messages.',
    )
    parser.add_argument(
        '--no-payload',
        action='store_true',
        help='Only output timing and topic metadata, without message payloads.',
    )
    parser.add_argument('--output', help='Optional path to write the replay plan JSON')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    args = parser.parse_args()

    try:
        plan = build_replay_plan(
            load_jsonl_records(args.path),
            topics=args.topic,
            include_payload=not args.no_payload,
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
