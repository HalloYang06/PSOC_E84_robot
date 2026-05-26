from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.board_manifest_sync_dry_run import (  # noqa: E402
    build_board_manifest_sync_plan,
    capability_labels,
)


class BoardManifestSyncDryRunTests(unittest.TestCase):
    def test_capability_labels_extracts_board_features(self) -> None:
        labels = capability_labels({
            'capabilities': {
                'ros2': {'available': True},
                'can_interfaces': [{'name': 'can0'}],
                'serial_devices': ['/dev/ttyUSB0'],
                'camera_devices': ['/dev/video0'],
                'usb_devices': [{'description': 'Bus 001 Device 002'}],
            }
        })

        self.assertEqual(
            labels,
            ['linux_board', 'board_manifest', 'ros2', 'can', 'serial', 'camera', 'usb'],
        )

    def test_build_board_manifest_sync_plan_registers_linux_board(self) -> None:
        plan = build_board_manifest_sync_plan({
            'schema_version': 'linux_board_manifest_v1',
            'device_id': 'nanopi-m5',
            'robot_id': 'rehab-arm-alpha',
            'platform': {'release': '6.1'},
            'capabilities': {'can_interfaces': [{'name': 'can0'}]},
        }, 'http://server.local/api/rehab-arm/v1/')

        self.assertEqual(plan['schema_version'], 'linux_board_manifest_sync_dry_run_v1')
        self.assertEqual(plan['request_count'], 1)
        request = plan['requests'][0]
        self.assertEqual(request['method'], 'POST')
        self.assertEqual(request['url'], 'http://server.local/api/rehab-arm/v1/devices/register')
        self.assertEqual(request['json']['device_type'], 'linux_board')
        self.assertEqual(request['json']['capabilities'], ['linux_board', 'board_manifest', 'can'])
        self.assertEqual(plan['control_boundary'], 'board_manifest_sync_plan_only_not_motion_permission')

    def test_cli_prints_dry_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / 'board_manifest.json'
            manifest_path.write_text(json.dumps({
                'schema_version': 'linux_board_manifest_v1',
                'device_id': 'nanopi-m5',
                'robot_id': 'rehab-arm-alpha',
                'platform': {'release': '6.1'},
                'capabilities': {'camera_devices': ['/dev/video0']},
            }), encoding='utf-8')
            script = Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'board_manifest_sync_dry_run.py'

            completed = subprocess.run(
                [sys.executable, str(script), str(manifest_path), '--base-url', 'http://server.local/api'],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan['requests'][0]['json']['capabilities'], ['linux_board', 'board_manifest', 'camera'])


if __name__ == '__main__':
    unittest.main()
