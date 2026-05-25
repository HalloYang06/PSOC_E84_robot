from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.sync_upload import (  # noqa: E402
    encode_json_body,
    encode_multipart_body,
    execute_sync_plan,
    make_http_request,
)


class FakeResponse:
    status = 200

    def read(self) -> bytes:
        return b'{"ok":true}'


class SyncUploadTests(unittest.TestCase):
    def test_encode_json_body_is_compact_utf8(self) -> None:
        body = encode_json_body({'ok': True, 'name': '康复'})

        self.assertEqual(json.loads(body.decode('utf-8')), {'ok': True, 'name': '康复'})
        self.assertNotIn(b'\n', body)

    def test_encode_multipart_body_includes_fields_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            path.write_bytes(b'{"record_type":"session_metadata"}\n')

            body, boundary = encode_multipart_body({
                'device_id': 'nanopi-m5',
                'robot_id': 'rehab-arm-alpha',
                'file_name': 's1.jsonl',
                'sha256': 'abc123',
                'file_path': str(path),
            })

        self.assertIn(boundary.encode('ascii'), body)
        self.assertIn(b'name="device_id"', body)
        self.assertIn(b'nanopi-m5', body)
        self.assertIn(b'name="file"; filename="s1.jsonl"', body)
        self.assertIn(b'{"record_type":"session_metadata"}', body)

    def test_make_http_request_for_json(self) -> None:
        req = make_http_request({
            'method': 'POST',
            'url': 'http://server.local/api/devices/register',
            'json': {'device_id': 'nanopi-m5'},
        })

        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.full_url, 'http://server.local/api/devices/register')
        self.assertEqual(req.headers['Content-type'], 'application/json')
        self.assertEqual(json.loads(req.data.decode('utf-8')), {'device_id': 'nanopi-m5'})

    def test_execute_sync_plan_uses_opener(self) -> None:
        seen: list[str] = []

        def opener(req, timeout):
            seen.append(f'{req.get_method()} {req.full_url} {timeout}')
            return FakeResponse()

        result = execute_sync_plan({
            'requests': [
                {
                    'method': 'POST',
                    'url': 'http://server.local/api/sessions/manifest',
                    'json': {'manifest': {}},
                },
            ],
            'skipped_sessions': [],
        }, timeout_sec=1.5, opener=opener)

        self.assertIs(result['ok'], True)
        self.assertEqual(result['completed_count'], 1)
        self.assertEqual(seen, ['POST http://server.local/api/sessions/manifest 1.5'])


if __name__ == '__main__':
    unittest.main()
