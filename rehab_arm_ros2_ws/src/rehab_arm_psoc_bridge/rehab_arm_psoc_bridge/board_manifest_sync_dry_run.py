#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest


def capability_labels(manifest: dict[str, object]) -> list[str]:
    capabilities = manifest.get('capabilities')
    if not isinstance(capabilities, dict):
        capabilities = {}
    labels = ['linux_board', 'board_manifest']
    ros2 = capabilities.get('ros2')
    if isinstance(ros2, dict) and ros2.get('available'):
        labels.append('ros2')
    if capabilities.get('can_interfaces'):
        labels.append('can')
    if capabilities.get('serial_devices'):
        labels.append('serial')
    if capabilities.get('camera_devices'):
        labels.append('camera')
    if capabilities.get('usb_devices'):
        labels.append('usb')
    return labels


def build_board_manifest_sync_plan(
    manifest: dict[str, object],
    base_url: str,
) -> dict[str, object]:
    if manifest.get('schema_version') != 'linux_board_manifest_v1':
        raise ValueError('expected linux_board_manifest_v1')
    base = base_url.rstrip('/')
    platform_info = manifest.get('platform')
    if not isinstance(platform_info, dict):
        platform_info = {}
    register_payload = {
        'device_id': str(manifest.get('device_id') or '').strip(),
        'robot_id': str(manifest.get('robot_id') or '').strip(),
        'device_type': 'linux_board',
        'software_version': str(platform_info.get('release') or 'unknown'),
        'capabilities': capability_labels(manifest),
    }
    if not register_payload['device_id']:
        raise ValueError('manifest.device_id is required')
    if not register_payload['robot_id']:
        raise ValueError('manifest.robot_id is required')
    requests = [
        {
            'method': 'POST',
            'url': f'{base}/devices/register',
            'json': register_payload,
        },
        {
            'method': 'POST',
            'url': f'{base}/devices/{register_payload["device_id"]}/board-manifest',
            'json': {
                'device_id': register_payload['device_id'],
                'robot_id': register_payload['robot_id'],
                'manifest': manifest,
            },
        },
    ]
    return {
        'schema_version': 'linux_board_manifest_sync_dry_run_v1',
        'base_url': base,
        'request_count': len(requests),
        'requests': requests,
        'control_boundary': 'board_manifest_sync_plan_only_not_motion_permission',
        'source_manifest_schema': manifest.get('schema_version'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Print planned server registration requests for a linux_board_manifest_v1 file.',
    )
    parser.add_argument('manifest_path', help='Path to board_manifest JSON')
    parser.add_argument(
        '--base-url',
        default=DEFAULT_BASE_URL,
        help=f'Server API base URL. Default: {DEFAULT_BASE_URL}',
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest_path)
    plan = build_board_manifest_sync_plan(manifest, args.base_url)
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
