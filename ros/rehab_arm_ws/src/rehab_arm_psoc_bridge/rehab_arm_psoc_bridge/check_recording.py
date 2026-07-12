#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import (
        RECORDING_TOPIC_PROFILES,
        load_jsonl_records,
        required_topics_for_profile,
        validate_jsonl_records,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        RECORDING_TOPIC_PROFILES,
        load_jsonl_records,
        required_topics_for_profile,
        validate_jsonl_records,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Check rehab arm JSONL recorder output.')
    parser.add_argument('path', help='Path to a recorder JSONL file')
    parser.add_argument(
        '--required-topic',
        action='append',
        dest='required_topics',
        default=None,
        help='Topic that must appear at least once. May be repeated.',
    )
    parser.add_argument(
        '--topic-profile',
        choices=sorted(RECORDING_TOPIC_PROFILES),
        help='Named topic contract preset for common simulation/hardware/perception checks.',
    )
    args = parser.parse_args()

    try:
        records = load_jsonl_records(args.path)
        if args.topic_profile:
            required_topics = required_topics_for_profile(args.topic_profile)
            if args.required_topics:
                required_topics.extend(args.required_topics)
            summary = validate_jsonl_records(records, required_topics)
            summary['topic_profile'] = args.topic_profile
        elif args.required_topics is None:
            summary = validate_jsonl_records(records)
        else:
            summary = validate_jsonl_records(records, args.required_topics)
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

    print(json.dumps(summary, ensure_ascii=False, separators=(',', ':')))
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
