#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Callable
from urllib import request

try:
    from rehab_arm_psoc_bridge.data_recording import build_sync_dry_run_plan
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import build_sync_dry_run_plan
    from rehab_arm_psoc_bridge.sync_dry_run import DEFAULT_BASE_URL, load_manifest


OpenUrl = Callable[[request.Request, float], object]


def encode_json_body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def encode_multipart_body(fields: dict[str, object], file_field: str = 'file') -> tuple[bytes, str]:
    boundary = f'rehab_arm_{uuid.uuid4().hex}'
    chunks: list[bytes] = []
    file_path = Path(str(fields['file_path'])).expanduser()
    file_name = str(fields.get('file_name') or file_path.name)

    def add_field(name: str, value: object) -> None:
        chunks.append(f'--{boundary}\r\n'.encode('ascii'))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('ascii'))
        chunks.append(str(value).encode('utf-8'))
        chunks.append(b'\r\n')

    for key, value in fields.items():
        if key == 'file_path':
            continue
        add_field(key, value)

    chunks.append(f'--{boundary}\r\n'.encode('ascii'))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
            'Content-Type: application/jsonl\r\n\r\n'
        ).encode('utf-8')
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode('ascii'))
    return b''.join(chunks), boundary


def make_http_request(item: dict[str, object]) -> request.Request:
    method = str(item.get('method') or 'POST')
    url = str(item['url'])
    headers: dict[str, str] = {}
    data: bytes
    if 'json' in item:
        data = encode_json_body(item['json'])
        headers['Content-Type'] = 'application/json'
    elif 'multipart' in item:
        data, boundary = encode_multipart_body(item['multipart'])  # type: ignore[arg-type]
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
    else:
        raise ValueError(f'unsupported request item: {item}')
    return request.Request(url, data=data, headers=headers, method=method)


def execute_sync_plan(
    plan: dict[str, object],
    timeout_sec: float = 10.0,
    opener: OpenUrl | None = None,
) -> dict[str, object]:
    open_url = opener
    results: list[dict[str, object]] = []
    for index, item in enumerate(plan.get('requests', []), start=1):
        if not isinstance(item, dict):
            results.append({'index': index, 'ok': False, 'error': 'request item is not an object'})
            continue
        http_request = make_http_request(item)
        try:
            if open_url is None:
                response = request.urlopen(http_request, timeout=timeout_sec)
            else:
                response = open_url(http_request, timeout_sec)
            status = int(getattr(response, 'status', getattr(response, 'code', 0)))
            body = response.read().decode('utf-8', errors='replace')
            results.append({
                'index': index,
                'ok': 200 <= status < 300,
                'status': status,
                'url': http_request.full_url,
                'body': body,
            })
        except Exception as exc:
            results.append({
                'index': index,
                'ok': False,
                'url': http_request.full_url,
                'error': str(exc),
            })
            break
    return {
        'schema_version': 'rehab_arm_sync_execute_result_v1',
        'ok': all(result.get('ok') is True for result in results),
        'request_count': len(plan.get('requests', [])),
        'completed_count': len(results),
        'results': results,
        'skipped_sessions': plan.get('skipped_sessions', []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Preview or execute server sync for rehab arm manifest data.',
    )
    parser.add_argument('manifest_path', help='Path to a rehab_arm_manifest_v1 JSON file')
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
    plan = build_sync_dry_run_plan(manifest, args.base_url)
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    result = execute_sync_plan(plan, timeout_sec=args.timeout_sec)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
