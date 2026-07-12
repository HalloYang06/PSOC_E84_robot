#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.server_action_ingress import (
        build_example_server_action_command,
        make_nanopi_action_queue_item,
        validate_server_action_command,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.server_action_ingress import (
        build_example_server_action_command,
        make_nanopi_action_queue_item,
        validate_server_action_command,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate a server_to_nanopi_high_level_command_v1 payload before any dry-run or motion path.',
    )
    parser.add_argument('--payload', help='Path to server action JSON payload')
    parser.add_argument('--example', action='store_true', help='Validate built-in safe example')
    parser.add_argument('--queue-item', action='store_true', help='Also emit the NanoPi high-level queue item')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    else:
        payload = build_example_server_action_command()

    report = validate_server_action_command(payload)
    output: dict[str, object]
    if args.queue_item:
        output = {
            'schema_version': 'server_action_ingress_check_result_v1',
            'report': report,
            'queue_item': make_nanopi_action_queue_item(payload, report),
            'control_boundary': 'ingress_check_result_only_not_motion_permission',
        }
    else:
        output = report
    text = json.dumps(
        output,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=args.pretty,
        separators=None if args.pretty else (',', ':'),
    )
    print(text)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
