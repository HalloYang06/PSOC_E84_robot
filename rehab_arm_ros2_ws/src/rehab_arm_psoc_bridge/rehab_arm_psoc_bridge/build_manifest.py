#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import RECORDING_TOPIC_PROFILES, build_recording_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import RECORDING_TOPIC_PROFILES, build_recording_manifest


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
    parser.add_argument(
        '--include-quality-report',
        action='store_true',
        help='Embed per-session data quality gate reports for annotation and upload review.',
    )
    parser.add_argument('--min-joint-messages', type=int, default=1)
    parser.add_argument('--min-moving-joints', type=int, default=0)
    parser.add_argument('--require-motor-state', action='store_true')
    parser.add_argument('--min-motor-entry-count', type=int, default=0)
    parser.add_argument('--min-camera-keyframes', type=int, default=0)
    parser.add_argument('--allow-motion-allowed-true', action='store_true')
    parser.add_argument(
        '--required-topic',
        action='append',
        dest='required_topics',
        default=None,
        help='Topic that must appear at least once in each session. May be repeated.',
    )
    parser.add_argument(
        '--topic-profile',
        choices=sorted(RECORDING_TOPIC_PROFILES),
        help='Named topic contract preset used inside embedded quality reports.',
    )
    args = parser.parse_args()

    manifest = build_recording_manifest(
        args.log_dir,
        include_summary=args.include_summary,
        include_quality_report=args.include_quality_report,
        min_joint_messages=args.min_joint_messages,
        min_moving_joints=args.min_moving_joints,
        require_motor_state=args.require_motor_state,
        min_motor_entry_count=args.min_motor_entry_count,
        min_camera_keyframes=args.min_camera_keyframes,
        allow_motion_allowed_true=args.allow_motion_allowed_true,
        required_topics=args.required_topics,
        topic_profile=args.topic_profile,
    )
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
