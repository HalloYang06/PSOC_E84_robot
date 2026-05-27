from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.check_m33_motor_status_presence import build_presence_report  # noqa: E402


def hash_line(ts: float, can_id: str, data: str) -> str:
    return f'({ts:.6f}) can0 {can_id}#{data}\n'


class CheckM33MotorStatusPresenceTests(unittest.TestCase):
    def test_report_fails_when_only_heartbeat_and_status_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'readonly.candump'
            path.write_text(
                hash_line(1.0, '321', '43')
                + hash_line(1.1, '322', 'A543070000060000'),
                encoding='utf-8',
            )

            report = build_presence_report(path)

        self.assertIs(report['ok'], False)
        self.assertEqual(report['heartbeat_0x321_count'], 1)
        self.assertEqual(report['psoc_status_0x322_count'], 1)
        self.assertEqual(report['valid_m33_motor_status_count'], 0)
        self.assertIn('no valid M33 motor status frames', '\n'.join(report['errors']))
        self.assertEqual(report['control_boundary'], 'candump_readonly_motor_status_presence_not_motion_permission')

    def test_report_passes_with_valid_m33_motor_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'motor_status.candump'
            path.write_text(
                hash_line(1.0, '321', '43')
                + hash_line(1.1, '322', 'A543070000060000')
                + hash_line(1.2, '330', 'B3010301320000FF'),
                encoding='utf-8',
            )

            report = build_presence_report(path)

        self.assertIs(report['ok'], True)
        self.assertEqual(report['m33_motor_status_count'], 1)
        self.assertEqual(report['valid_m33_motor_status_count'], 1)
        self.assertEqual(report['m33_motor_status_ids'], {'0x330': 1})

    def test_report_rejects_unexpected_target_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'target.candump'
            path.write_text(
                hash_line(1.0, '330', 'B3010301320000FF')
                + hash_line(1.1, '320', '0304640001000000'),
                encoding='utf-8',
            )

            report = build_presence_report(path)

        self.assertIs(report['ok'], False)
        self.assertEqual(report['target_0x320_count'], 1)
        self.assertIn('unexpected 0x320 target frames', '\n'.join(report['errors']))

    def test_cli_returns_one_when_motor_status_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'readonly.candump'
            path.write_text(hash_line(1.1, '322', 'A543070000060000'), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'check_m33_motor_status_presence.py'),
                    str(path),
                    '--pretty',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'm33_motor_status_presence_report_v1')
        self.assertIs(payload['ok'], False)


if __name__ == '__main__':
    unittest.main()
