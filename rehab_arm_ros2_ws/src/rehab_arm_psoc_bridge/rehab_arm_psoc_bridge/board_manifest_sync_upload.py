#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.board_manifest_sync_dry_run import build_board_manifest_sync_plan
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest
    from rehab_arm_psoc_bridge.sync_upload import OpenUrl, execute_sync_plan
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.board_manifest_sync_dry_run import build_board_manifest_sync_plan
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest
    from rehab_arm_psoc_bridge.sync_upload import OpenUrl, execute_sync_plan


def build_board_manifest_upload_result(
    manifest: dict[str, object],
    base_url: str,
    timeout_sec: float = 10.0,
    opener: OpenUrl | None = None,
) -> dict[str, object]:
    plan = build_board_manifest_sync_plan(manifest, base_url)
    result = execute_sync_plan(plan, timeout_sec=timeout_sec, opener=opener)
    result['schema_version'] = 'linux_board_manifest_sync_execute_result_v1'
    result['control_boundary'] = 'board_manifest_sync_only_not_motion_permission'
    result['source_manifest_schema'] = plan.get('source_manifest_schema')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Preview or upload a linux_board_manifest_v1 to the platform.',
    )
    parser.add_argument('manifest_path', help='Path to board_manifest JSON')
    parser.add_argument(
        '--base-url',
        default=DEFAULT_BASE_URL,
        help=f'Server API base URL. Default: {DEFAULT_BASE_URL}',
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually send HTTP requests. Omit this flag for safe dry-run output.',
    )
    parser.add_argument('--timeout-sec', type=float, default=10.0, help='HTTP timeout in seconds')
    args = parser.parse_args()

    manifest = load_manifest(args.manifest_path)
    if not args.execute:
        plan = build_board_manifest_sync_plan(manifest, args.base_url)
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    result = build_board_manifest_upload_result(
        manifest,
        args.base_url,
        timeout_sec=args.timeout_sec,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
