from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.motion_test_report import build_motion_test_report  # noqa: E402


class MotionTestReportTests(unittest.TestCase):
    def test_build_motion_test_report_accepts_formal_csp_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'motion.candump'
            path.write_text(
                '\n'.join([
                    '(1.000000) can0 320#0304640001000000',
                    '(1.010000) can0 1200FD07#0570000005000000',
                    '(1.020000) can0 1200FD07#177000005077D63D',
                    '(1.030000) can0 1200FD07#16700000C3B8323E',
                    '(1.100000) can0 336#B3010701B7FF0020',
                    '(2.100000) can0 336#B3020700AE000020',
                    '(2.200000) can0 320#020400',
                    '(2.210000) can0 0400FD07#0000000000000000',
                    '(2.220000) can0 322#A52A070000060000',
                ]) + '\n',
                encoding='utf-8',
            )

            report = build_motion_test_report(path, motor_id=7, joint_id=4)

        self.assertIs(report['ok'], True)
        self.assertEqual(report['target_command_count'], 1)
        self.assertEqual(report['stop_command_count'], 1)
        self.assertEqual(report['private_stop_frame_count'], 1)
        self.assertEqual(report['mit_control_frame_count'], 0)
        self.assertTrue(report['has_expected_csp_sequence'])
        self.assertAlmostEqual(report['m33_motor_status']['delta_position_rad'], 0.247)
        self.assertAlmostEqual(report['m33_motor_status']['delta_position_deg'], math.degrees(0.247))

    def test_build_motion_test_report_rejects_missing_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'motion.candump'
            path.write_text(
                '\n'.join([
                    '(1.000000) can0 320#0304640001000000',
                    '(1.010000) can0 1200FD07#0570000005000000',
                    '(1.020000) can0 1200FD07#177000005077D63D',
                    '(1.030000) can0 1200FD07#16700000C3B8323E',
                ]) + '\n',
                encoding='utf-8',
            )

            report = build_motion_test_report(path, motor_id=7, joint_id=4)

        self.assertIs(report['ok'], False)
        self.assertIs(report['stop_observed'], False)

    def test_cli_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'motion.candump'
            path.write_text(
                '\n'.join([
                    '(1.000000) can0 320#0304640001000000',
                    '(1.010000) can0 1200FD07#0570000005000000',
                    '(1.020000) can0 1200FD07#177000005077D63D',
                    '(1.030000) can0 1200FD07#16700000C3B8323E',
                    '(2.200000) can0 320#020400',
                    '(2.210000) can0 0400FD07#0000000000000000',
                ]) + '\n',
                encoding='utf-8',
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'motion_test_report.py'),
                    str(path),
                    '--motor-id',
                    '7',
                    '--joint-id',
                    '4',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_motion_test_report_v1')


if __name__ == '__main__':
    unittest.main()
