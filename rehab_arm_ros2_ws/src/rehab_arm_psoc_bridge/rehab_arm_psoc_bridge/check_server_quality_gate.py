#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable
from urllib import request


OpenUrl = Callable[[request.Request, float], object]
DEFAULT_BASE_URL = 'http://106.55.62.122:8011/api/rehab-arm/v1'


def load_server_dashboard(
    base_url: str,
    timeout_sec: float = 10.0,
    opener: OpenUrl | None = None,
) -> dict[str, object]:
    url = f'{base_url.rstrip("/")}/devices/dashboard'
    req = request.Request(url, method='GET')
    try:
        if opener is None:
            response = request.urlopen(req, timeout=timeout_sec)
        else:
            response = opener(req, timeout_sec)
        body = response.read().decode('utf-8', errors='replace')
        payload = json.loads(body)
    except Exception as exc:
        return {
            'schema_version': 'server_quality_gate_check_v1',
            'ok': False,
            'error': str(exc),
            'dashboard_url': url,
        }

    data = payload.get('data') if isinstance(payload, dict) else payload
    return data if isinstance(data, dict) else {}


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _find_device(dashboard: dict[str, object], device_id: str) -> dict[str, object]:
    devices = dashboard.get('devices', [])
    if not isinstance(devices, list):
        return {}
    for item in devices:
        device = _record(item)
        if str(device.get('device_id') or '') == device_id:
            return device
    return {}


def build_quality_gate_check(
    dashboard: dict[str, object],
    device_id: str,
    require_annotation_ready: bool = True,
) -> dict[str, object]:
    device = _find_device(dashboard, device_id)
    if not device:
        return {
            'schema_version': 'server_quality_gate_check_v1',
            'ok': False,
            'device_id': device_id,
            'error': f'device {device_id} not found in server dashboard',
        }

    quality = _record(device.get('data_quality'))
    latest = _record(quality.get('latest_session'))
    blocking_reasons = quality.get('blocking_reasons', [])
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    annotation_ready = quality.get('annotation_ready') is True
    quality_report_ok = latest.get('quality_report_ok')
    control_boundary = str(quality.get('control_boundary') or '')

    errors: list[str] = []
    if require_annotation_ready and not annotation_ready:
        errors.append('annotation_ready is false')
    if quality_report_ok is False:
        errors.append('latest quality_report_ok is false')
    if control_boundary != 'data_quality_only_not_motion_permission':
        errors.append('missing data-only control boundary')
    errors.extend(str(item) for item in blocking_reasons if item)

    return {
        'schema_version': 'server_quality_gate_check_v1',
        'ok': not errors,
        'device_id': device_id,
        'robot_id': device.get('robot_id') or '',
        'annotation_ready': annotation_ready,
        'latest_session_id': latest.get('session_id') or '',
        'quality_report_ok': quality_report_ok,
        'moving_joint_count': latest.get('moving_joint_count', 0),
        'motor_entry_count_min': latest.get('motor_entry_count_min', 0),
        'motor_entry_count_max': latest.get('motor_entry_count_max', 0),
        'quality_criteria': latest.get('quality_criteria') if isinstance(latest.get('quality_criteria'), dict) else {},
        'control_boundary': control_boundary,
        'blocking_reasons': blocking_reasons,
        'errors': errors,
        'safety_note': 'server quality gate is data readiness only, not motion permission',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Check server-side device data quality gate after sync upload.')
    parser.add_argument('device_id', help='Device id to check in /devices/dashboard')
    parser.add_argument(
        '--base-url',
        default=DEFAULT_BASE_URL,
        help=f'Server API base URL. Default: {DEFAULT_BASE_URL}',
    )
    parser.add_argument('--timeout-sec', type=float, default=10.0)
    parser.add_argument(
        '--allow-not-ready',
        action='store_true',
        help='Return success if the device exists even when annotation_ready=false.',
    )
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    dashboard = load_server_dashboard(args.base_url, timeout_sec=args.timeout_sec)
    if dashboard.get('schema_version') == 'server_quality_gate_check_v1' and dashboard.get('ok') is False:
        result = dashboard
    else:
        result = build_quality_gate_check(
            dashboard,
            args.device_id,
            require_annotation_ready=not args.allow_not_ready,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if result.get('ok') is True else 1


if __name__ == '__main__':
    sys.exit(main())
