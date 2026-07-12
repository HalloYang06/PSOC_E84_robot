from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.calibration_observation import analyze_calibration_observation  # noqa: E402


def hash_line(relative_time: float, can_id: str, data: str) -> str:
    return f'({relative_time:.6f}) can0 {can_id}#{data}\n'


class CalibrationObservationTests(unittest.TestCase):
    def test_analyze_telemetry_only_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            source.write_text(
                hash_line(1.0, '320', '060401')
                + hash_line(1.1, '1800FD07', '0102030405060100')
                + hash_line(1.2, '180007FD', 'F8D47FFF7FFF014A')
                + hash_line(1.3, '180007FD', 'F8D57FFF7FFF014A')
                + hash_line(1.4, '336', 'B39207005A2E0021')
                + hash_line(1.5, '320', '060400')
                + hash_line(1.6, '1800FD07', '0102030405060000'),
                encoding='utf-8',
            )

            report = analyze_calibration_observation(source, motor_id=7)

        self.assertIs(report['ok'], True)
        self.assertIs(report['observation_ok'], True)
        self.assertIs(report['no_motion_control_frames'], True)
        self.assertEqual(report['active_report_enable_frames'], 1)
        self.assertEqual(report['active_report_disable_frames'], 1)
        self.assertEqual(report['raw_active_report']['count'], 2)
        self.assertEqual(report['raw_active_report']['latest']['raw_position_u16'], 0xF8D5)
        self.assertEqual(report['raw_active_report']['raw_position_delta_u16'], 1)
        self.assertEqual(report['m33_status']['count'], 1)
        self.assertEqual(report['m33_status']['latest']['motor_id'], 7)
        self.assertEqual(report['motor_control_frames'], 0)
        self.assertIs(report['safe_to_use_as_motion_proof'], False)

    def test_detects_motion_control_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            source.write_text(
                hash_line(1.0, '01800007', '855481370F5C3333')
                + hash_line(1.1, '180007FD', 'F8D47FFF7FFF014A'),
                encoding='utf-8',
            )

            report = analyze_calibration_observation(source, motor_id=7)

        self.assertIs(report['ok'], False)
        self.assertIs(report['no_motion_control_frames'], False)
        self.assertEqual(report['motor_control_frames'], 1)

    def test_cli_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            source.write_text(hash_line(1.2, '180007FD', 'F8D47FFF7FFF014A'), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'calibration_observation.py'),
                    str(source),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['motor_id'], 7)
        self.assertEqual(payload['raw_active_report']['count'], 1)


if __name__ == '__main__':
    unittest.main()
