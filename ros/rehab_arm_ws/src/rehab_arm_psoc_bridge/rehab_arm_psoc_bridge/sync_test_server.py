#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def make_sync_handler(storage_dir: str | Path) -> type[BaseHTTPRequestHandler]:
    base = Path(storage_dir).expanduser()
    requests_dir = base / 'requests'
    requests_dir.mkdir(parents=True, exist_ok=True)
    log_path = base / 'request_log.jsonl'

    class SyncTestHandler(BaseHTTPRequestHandler):
        request_count = 0

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write('[sync-test-server] ' + format % args + '\n')

        def do_POST(self) -> None:
            type(self).request_count += 1
            index = type(self).request_count
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            body_path = requests_dir / f'{index:04d}_body.bin'
            body_path.write_bytes(body)

            record = {
                'ts_unix': time.time(),
                'index': index,
                'method': 'POST',
                'path': self.path,
                'content_type': self.headers.get('Content-Type', ''),
                'content_length': length,
                'body_path': str(body_path),
            }
            with log_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')

            response = {
                'ok': True,
                'path': self.path,
                'index': index,
                'stored_body_path': str(body_path),
            }
            payload = json.dumps(response, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Connection', 'close')
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionAbortedError):
                pass
            self.close_connection = True

    return SyncTestHandler


def build_server(host: str, port: int, storage_dir: str | Path) -> HTTPServer:
    return HTTPServer((host, port), make_sync_handler(storage_dir))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Local development server for testing rehab arm sync_upload --execute.',
    )
    parser.add_argument('--host', default='127.0.0.1', help='Bind host')
    parser.add_argument('--port', type=int, default=8765, help='Bind port')
    parser.add_argument(
        '--storage-dir',
        default='/tmp/rehab_arm_sync_server',
        help='Directory for request logs and raw request bodies',
    )
    args = parser.parse_args()

    server = build_server(args.host, args.port, args.storage_dir)
    host, port = server.server_address
    print(f'sync test server listening on http://{host}:{port}/api/rehab-arm/v1', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
