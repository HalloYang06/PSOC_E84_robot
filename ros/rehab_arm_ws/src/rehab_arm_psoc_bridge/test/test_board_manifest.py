from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.board_manifest import (  # noqa: E402
    build_board_manifest,
    discover_device_nodes,
    discover_network_interfaces,
)


class BoardManifestTests(unittest.TestCase):
    def test_discover_network_interfaces_marks_can(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            can0 = root / 'can0'
            eth0 = root / 'eth0'
            can0.mkdir()
            eth0.mkdir()
            (can0 / 'operstate').write_text('down\n', encoding='utf-8')
            (can0 / 'address').write_text('00:00:00:00:00:00\n', encoding='utf-8')
            (eth0 / 'operstate').write_text('up\n', encoding='utf-8')

            interfaces = discover_network_interfaces(root)

        self.assertEqual([item['name'] for item in interfaces], ['can0', 'eth0'])
        self.assertEqual(interfaces[0]['kind'], 'can')
        self.assertEqual(interfaces[0]['operstate'], 'down')
        self.assertEqual(interfaces[1]['kind'], 'network')

    def test_discover_device_nodes_finds_serial_and_camera(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'ttyUSB0').write_text('', encoding='utf-8')
            (root / 'ttyACM1').write_text('', encoding='utf-8')
            (root / 'video0').write_text('', encoding='utf-8')
            (root / 'random').write_text('', encoding='utf-8')

            nodes = discover_device_nodes(root)

        self.assertEqual(nodes['serial'], ['/dev/ttyACM1', '/dev/ttyUSB0'])
        self.assertEqual(nodes['camera'], ['/dev/video0'])

    def test_build_board_manifest_is_read_only_discovery_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            net = root / 'net'
            dev = root / 'dev'
            net.mkdir()
            dev.mkdir()
            can0 = net / 'can0'
            can0.mkdir()
            (can0 / 'operstate').write_text('up\n', encoding='utf-8')
            (dev / 'ttyUSB0').write_text('', encoding='utf-8')
            (dev / 'video2').write_text('', encoding='utf-8')

            manifest = build_board_manifest(
                device_id='nanopi-m5',
                robot_id='rehab-arm-alpha',
                sys_class_net=net,
                dev_dir=dev,
                runner=lambda _args, _timeout: (0, '', ''),
                now=lambda: 1234.5,
            )

        self.assertEqual(manifest['schema_version'], 'linux_board_manifest_v1')
        self.assertEqual(manifest['device_id'], 'nanopi-m5')
        self.assertEqual(manifest['robot_id'], 'rehab-arm-alpha')
        self.assertEqual(manifest['control_boundary'], 'board_discovery_only_not_motion_permission')
        self.assertEqual(manifest['ts_unix'], 1234)
        capabilities = manifest['capabilities']
        self.assertEqual(capabilities['can_interfaces'][0]['name'], 'can0')
        self.assertEqual(capabilities['serial_devices'], ['/dev/ttyUSB0'])
        self.assertEqual(capabilities['camera_devices'], ['/dev/video2'])
        self.assertIn('motor_state', manifest['recommended_streams'])


if __name__ == '__main__':
    unittest.main()
