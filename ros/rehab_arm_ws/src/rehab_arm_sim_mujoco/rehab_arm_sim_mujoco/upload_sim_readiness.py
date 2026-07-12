#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable
from urllib import request

try:
    from rehab_arm_sim_mujoco.check_sim_env import SCHEMA_VERSION
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_sim_mujoco.check_sim_env import SCHEMA_VERSION


DEFAULT_BASE_URL = 'http://127.0.0.1:8011/api/rehab-arm/v1'
CONTROL_BOUNDARY = 'simulation_readiness_only_not_motion_permission'

OpenUrl = Callable[[request.Request, float], object]


def load_report(path: str | Path) -> dict[str, object]:
    report_path = Path(path).expanduser()
    with report_path.open('r', encoding='utf-8') as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError('simulation readiness report must be a JSON object')
    if report.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f"expected schema_version={SCHEMA_VERSION}, got {report.get('schema_version')!r}")
    return report


def build_upload_payload(report: dict[str, object], robot_id: str, device_id: str) -> dict[str, object]:
    return {
        'robot_id': robot_id,
        'device_id': device_id,
        'report': report,
    }


def build_upload_plan(
    report: dict[str, object],
    base_url: str,
    robot_id: str,
    device_id: str,
) -> dict[str, object]:
    clean_base = base_url.rstrip('/')
    return {
        'schema_version': 'rehab_arm_sim_readiness_upload_plan_v1',
        'ok': True,
        'execute_required': True,
        'control_boundary': CONTROL_BOUNDARY,
        'request': {
            'method': 'POST',
            'url': f'{clean_base}/devices/{device_id}/simulation-readiness',
            'json': build_upload_payload(report, robot_id, device_id),
        },
    }


def make_http_request(plan: dict[str, object]) -> request.Request:
    item = plan.get('request')
    if not isinstance(item, dict):
        raise ValueError('upload plan request is missing')
    body = json.dumps(item['json'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return request.Request(
        str(item['url']),
        data=body,
        headers={'Content-Type': 'application/json'},
        method=str(item.get('method') or 'POST'),
    )


def execute_upload_plan(
    plan: dict[str, object],
    timeout_sec: float = 10.0,
    opener: OpenUrl | None = None,
) -> dict[str, object]:
    http_request = make_http_request(plan)
    try:
        response = opener(http_request, timeout_sec) if opener else request.urlopen(http_request, timeout=timeout_sec)
        status = int(getattr(response, 'status', getattr(response, 'code', 0)))
        body = response.read().decode('utf-8', errors='replace')
        ok = 200 <= status < 300
        return {
            'schema_version': 'rehab_arm_sim_readiness_upload_result_v1',
            'ok': ok,
            'status': status,
            'url': http_request.full_url,
            'body': body,
            'control_boundary': CONTROL_BOUNDARY,
        }
    except Exception as exc:
        return {
            'schema_version': 'rehab_arm_sim_readiness_upload_result_v1',
            'ok': False,
            'url': http_request.full_url,
            'error': str(exc),
            'control_boundary': CONTROL_BOUNDARY,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Preview or upload a read-only simulation readiness report to the platform.',
    )
    parser.add_argument('report_path', help='Path to sim_readiness_report.json from check_sim_env --output')
    parser.add_argument('--device-id', required=True, help='Device id shown in the platform, for example nanopi-m5')
    parser.add_argument('--robot-id', default='rehab-arm-alpha', help='Robot id. Default: rehab-arm-alpha')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help=f'Platform API base URL. Default: {DEFAULT_BASE_URL}')
    parser.add_argument('--execute', action='store_true', help='Actually send the HTTP POST. Omit for safe dry-run output.')
    parser.add_argument('--timeout-sec', type=float, default=10.0, help='HTTP timeout in seconds')
    args = parser.parse_args(argv)

    report = load_report(args.report_path)
    plan = build_upload_plan(report, args.base_url, args.robot_id, args.device_id)
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    result = execute_upload_plan(plan, timeout_sec=args.timeout_sec)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get('ok') is True else 2


if __name__ == '__main__':
    raise SystemExit(main())
