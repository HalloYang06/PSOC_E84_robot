from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.board_manifest_sync_upload import (  # noqa: E402
    build_board_manifest_upload_result,
)


class FakeResponse:
    status = 200

    def read(self) -> bytes:
        return b'{"ok":true}'


class BoardManifestSyncUploadTests(unittest.TestCase):
    def test_build_board_manifest_upload_result_uses_opener(self) -> None:
        seen: list[str] = []

        def opener(req, timeout):
            seen.append(f'{req.get_method()} {req.full_url} {timeout}')
            return FakeResponse()

        result = build_board_manifest_upload_result(
            {
                'schema_version': 'linux_board_manifest_v1',
                'device_id': 'nanopi-m5',
                'robot_id': 'rehab-arm-alpha',
                'platform': {'release': '6.1'},
                'capabilities': {'can_interfaces': [{'name': 'can0'}]},
            },
            'http://server.local/api/rehab-arm/v1',
            timeout_sec=2.0,
            opener=opener,
        )

        self.assertEqual(result['schema_version'], 'linux_board_manifest_sync_execute_result_v1')
        self.assertIs(result['ok'], True)
        self.assertEqual(result['completed_count'], 2)
        self.assertEqual(
            seen,
            [
                'POST http://server.local/api/rehab-arm/v1/devices/register 2.0',
                'POST http://server.local/api/rehab-arm/v1/devices/nanopi-m5/board-manifest 2.0',
            ],
        )
        self.assertEqual(result['control_boundary'], 'board_manifest_sync_only_not_motion_permission')

    def test_cli_defaults_to_dry_run_without_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / 'board_manifest.json'
            manifest_path.write_text(json.dumps({
                'schema_version': 'linux_board_manifest_v1',
                'device_id': 'nanopi-m5',
                'robot_id': 'rehab-arm-alpha',
                'platform': {'release': '6.1'},
                'capabilities': {'camera_devices': ['/dev/video0']},
            }), encoding='utf-8')
            script = Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'board_manifest_sync_upload.py'

            completed = subprocess.run(
                [sys.executable, str(script), str(manifest_path), '--base-url', 'http://server.local/api'],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan['schema_version'], 'linux_board_manifest_sync_dry_run_v1')
        self.assertEqual(plan['requests'][0]['json']['capabilities'], ['linux_board', 'board_manifest', 'camera'])


if __name__ == '__main__':
    unittest.main()
