#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.voice_gateway import build_voice_pipeline_plan
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.voice_gateway import build_voice_pipeline_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build a dry-run M55 voice wake/API relay/TTS playback contract plan.',
    )
    parser.add_argument('--robot-id', default='medical_rehab_arm')
    parser.add_argument('--device-id', default='nanopi_dev')
    parser.add_argument('--prompt-text', default='开始训练')
    parser.add_argument('--wake-phrase', default='xiao_yi_xiao_yi')
    parser.add_argument('--output', help='Optional path to write JSON')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    plan = build_voice_pipeline_plan(
        robot_id=args.robot_id,
        device_id=args.device_id,
        prompt_text=args.prompt_text,
        wake_phrase=args.wake_phrase,
    )
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
