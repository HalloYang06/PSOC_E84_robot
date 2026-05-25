from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.data_recording import build_sync_dry_run_plan  # noqa: E402
from rehab_arm_psoc_bridge.sync_test_server import build_server  # noqa: E402
from rehab_arm_psoc_bridge.sync_upload import execute_sync_plan  # noqa: E402


class SyncTestServerTests(unittest.TestCase):
    def test_server_accepts_full_sync_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / 's1.jsonl'
            log_path.write_bytes(b'{"record_type":"session_metadata"}\n')
            server_dir = Path(tmpdir) / 'server'
            server = build_server('127.0.0.1', 0, server_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                manifest = {
                    'schema_version': 'rehab_arm_manifest_v1',
                    'sessions': [
                        {
                            'ok': True,
                            'path': str(log_path),
                            'file_name': log_path.name,
                            'session_id': 's1',
                            'device_id': 'nanopi-m5',
                            'robot_id': 'rehab-arm-alpha',
                            'software_version': 'dev',
                            'record_count': 1,
                        },
                    ],
                }
                plan = build_sync_dry_run_plan(
                    manifest,
                    f'http://{host}:{port}/api/rehab-arm/v1',
                )

                result = execute_sync_plan(plan, timeout_sec=2.0)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)

            self.assertIs(result['ok'], True)
            self.assertEqual(result['completed_count'], 4)
            log_records = [
                json.loads(line)
                for line in (server_dir / 'request_log.jsonl').read_text(encoding='utf-8').splitlines()
            ]
            self.assertEqual(len(log_records), 4)
            self.assertEqual(log_records[0]['path'], '/api/rehab-arm/v1/devices/register')
            self.assertEqual(log_records[2]['path'], '/api/rehab-arm/v1/sessions/s1/files')
            self.assertTrue(Path(log_records[2]['body_path']).exists())


if __name__ == '__main__':
    unittest.main()
