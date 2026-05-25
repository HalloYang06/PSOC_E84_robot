#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import build_sync_dry_run_plan
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_sync_dry_run_plan


DEFAULT_BASE_URL = 'http://server.example/api/rehab-arm/v1'


def load_manifest(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError('manifest root must be a JSON object')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Print the planned server sync requests without making network calls.',
    )
    parser.add_argument('manifest_path', help='Path to a rehab_arm_manifest_v1 JSON file')
    parser.add_argument(
        '--base-url',
        default=DEFAULT_BASE_URL,
        help=f'Server API base URL. Default: {DEFAULT_BASE_URL}',
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest_path)
    plan = build_sync_dry_run_plan(manifest, args.base_url)
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
