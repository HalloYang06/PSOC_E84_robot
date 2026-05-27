from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.feedback_source_readiness import (  # noqa: E402
    CONTROL_BOUNDARY,
    build_feedback_source_readiness_report,
)


def candump_line(relative_time: float, can_id: str, data: bytes) -> str:
    hex_data = ' '.join(f'{byte:02X}' for byte in data)
    return f' ({relative_time:010.6f})  can0  {can_id}   [{len(data)}]  {hex_data}\n'


class FeedbackSourceReadinessTests(unittest.TestCase):
    def test_reports_missing_raw_feedback_when_m33_is_stale_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'readonly.candump'
            source.write_text(
                candump_line(0.0, '322', bytes([0xA5, 1, 7, 0, 0, 6, 0, 0]))
                + candump_line(0.1, '330', bytes([0xB3, 2, 3, 0x10, 0, 0, 0, 0xFF]))
                + candump_line(0.2, '331', bytes([0xB3, 3, 4, 0x10, 0, 0, 0, 0xFF])),
                encoding='utf-8',
            )

            report = build_feedback_source_readiness_report(source)

        self.assertIs(report['ok'], True)
        self.assertIs(report['raw_motor_feedback_ready'], False)
        self.assertIs(report['m33_joint_state_ready'], False)
        self.assertEqual(report['decision'], 'motor_feedback_source_missing')
        self.assertEqual(report['m33']['stale_count'], 2)
        self.assertIn('no raw motor feedback frames observed', '\n'.join(report['warnings']))
        self.assertEqual(report['control_boundary'], CONTROL_BOUNDARY)

    def test_reports_ready_when_fresh_m33_and_raw_sources_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'ready.candump'
            source.write_text(
                candump_line(0.0, '061', bytes([0, 0, 0, 0, 8, 0, 0, 0]))
                + candump_line(0.1, '069', bytes([0, 0, 0, 0, 0, 0, 0, 0]))
                + '(000.200000) can0 180007FD#80007FFF80000140\n'
                + candump_line(0.3, '330', bytes([0xB3, 1, 3, 0x01, 50, 0, 1, 30])),
                encoding='utf-8',
            )

            report = build_feedback_source_readiness_report(source)

        self.assertIs(report['raw_motor_feedback_ready'], True)
        self.assertIs(report['m33_joint_state_ready'], True)
        self.assertIs(report['safe_to_expect_joint_states'], True)
        self.assertEqual(report['decision'], 'ready_for_ros_joint_states')
        self.assertEqual(report['raw_sources']['cansimple_heartbeats_by_node'], {'3': 1})
        self.assertEqual(report['raw_sources']['cansimple_encoder_estimates_by_node'], {'3': 1})
        self.assertEqual(report['raw_sources']['lingzu_active_reports_by_motor'], {'7': 1})

    def test_target_frames_fail_readonly_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'target.candump'
            source.write_text(
                candump_line(0.0, '320', bytes([3, 4, 0, 0, 0, 0, 0, 0])),
                encoding='utf-8',
            )

            report = build_feedback_source_readiness_report(source)

        self.assertIs(report['ok'], False)
        self.assertTrue(report['safety']['motion_command_observed'])
        self.assertIn('0x320 target frames were observed', report['errors'][0])

    def test_cli_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'readonly.candump'
            source.write_text(
                candump_line(0.0, '330', bytes([0xB3, 1, 3, 0x10, 0, 0, 0, 0xFF])),
                encoding='utf-8',
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'feedback_source_readiness.py'),
                    str(source),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema_version'], 'rehab_arm_feedback_source_readiness_v1')


if __name__ == '__main__':
    unittest.main()
