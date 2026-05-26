from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.m33_motor_status_smoke import (  # noqa: E402
    CONTROL_BOUNDARY,
    build_m33_motor_status_payload,
    build_smoke_jsonl_records,
    build_smoke_frames,
    build_smoke_quality_report,
    build_smoke_report,
    pack_standard_can_frame,
    write_smoke_jsonl,
)
from rehab_arm_psoc_bridge.data_recording import (  # noqa: E402
    build_recording_quality_report,
    load_jsonl_records,
)
from rehab_arm_psoc_bridge.psoc_motor_status import (  # noqa: E402
    M33_MOTOR_STATUS_MARKER,
    parse_m33_motor_status_frame,
)


class M33MotorStatusSmokeTests(unittest.TestCase):
    def test_build_payload_matches_m33_motor_status_parser(self) -> None:
        data = build_m33_motor_status_payload(
            seq=5,
            motor_id=7,
            position_rad=-0.08,
            velocity_rad_s=0.1,
            temperature_c=34,
        )

        motor = parse_m33_motor_status_frame(0x331, data)

        self.assertEqual(data[0], M33_MOTOR_STATUS_MARKER)
        self.assertIs(motor['valid'], True)
        self.assertEqual(motor['motor_id'], 7)
        self.assertAlmostEqual(motor['position'], -0.08)
        self.assertAlmostEqual(motor['velocity'], 0.1)
        self.assertEqual(motor['temperature'], 34.0)

    def test_build_payload_rejects_out_of_range_values(self) -> None:
        with self.assertRaises(ValueError):
            build_m33_motor_status_payload(1, 3, 40.0, 0.0, None)
        with self.assertRaises(ValueError):
            build_m33_motor_status_payload(1, 3, 0.0, 20.0, None)
        with self.assertRaises(ValueError):
            build_m33_motor_status_payload(1, 3, 0.0, 0.0, 255)

    def test_build_smoke_report_is_dry_run_by_default(self) -> None:
        frames = build_smoke_frames(seq=9)

        report = build_smoke_report(frames, 'rehab-arm-alpha', 'nanopi-m5', False, 'vcan0')

        self.assertIs(report['ok'], True)
        self.assertIs(report['execute'], False)
        self.assertEqual(report['control_boundary'], CONTROL_BOUNDARY)
        self.assertEqual(report['frames'][0]['can_id'], '0x330')
        self.assertEqual(report['expected_motor_state_payload']['valid_motor_count'], 2)
        self.assertIn('never sends 0x320', report['safety_note'])

    def test_pack_standard_can_frame_uses_classic_socketcan_layout(self) -> None:
        data = build_m33_motor_status_payload(1, 3, 0.05, 0.0, None)

        raw = pack_standard_can_frame(0x330, data)

        self.assertEqual(len(raw), 16)
        self.assertEqual(raw[0:4], bytes([0x30, 0x03, 0x00, 0x00]))
        self.assertEqual(raw[4], 8)

    def test_cli_prints_dry_run_json_without_execute(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'm33_motor_status_smoke.py'),
                '--seq',
                '4',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIs(report['execute'], False)
        self.assertEqual(report['frame_count'], 2)
        self.assertEqual(report['frames'][1]['can_id'], '0x331')

    def test_build_smoke_jsonl_records_pass_hardware_telemetry_quality_gate(self) -> None:
        records = build_smoke_jsonl_records(
            build_smoke_frames(seq=1),
            'rehab-arm-alpha',
            'nanopi-m5',
            's1',
        )

        report = build_recording_quality_report(
            records,
            topic_profile='hardware_telemetry',
            min_joint_messages=1,
            require_motor_state=True,
            min_motor_entry_count=2,
        )

        self.assertIs(report['ok'], True)
        self.assertEqual(report['topic_profile'], 'hardware_telemetry')
        self.assertEqual(report['summary']['motor_entry_count_min'], 2)

    def test_build_smoke_quality_report_uses_platform_hardware_contract(self) -> None:
        records = build_smoke_jsonl_records(
            build_smoke_frames(seq=1),
            'rehab-arm-alpha',
            'nanopi-m5',
            's1',
        )

        report = build_smoke_quality_report(records)

        self.assertIs(report['ok'], True)
        self.assertEqual(report['topic_profile'], 'hardware_telemetry')
        self.assertEqual(report['criteria']['min_motor_entry_count'], 2)
        self.assertIn('/rehab_arm/motor_state', report['required_topics'])

    def test_write_smoke_jsonl_outputs_loadable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'smoke.jsonl'

            path = write_smoke_jsonl(
                output,
                build_smoke_frames(seq=2),
                'rehab-arm-alpha',
                'nanopi-m5',
                's2',
            )
            records = load_jsonl_records(path)

        self.assertEqual(records[0]['record_type'], 'session_metadata')
        self.assertEqual(records[-1]['topic'], '/rehab_arm/motor_state')
        self.assertEqual(records[-1]['payload']['valid_motor_count'], 2)

    def test_cli_can_write_jsonl_without_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'smoke.jsonl'
            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'm33_motor_status_smoke.py'),
                    '--output-jsonl',
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            records = load_jsonl_records(output)

        self.assertIs(report['execute'], False)
        self.assertEqual(report['output_jsonl'], str(output))
        self.assertIs(report['quality_report']['ok'], True)
        self.assertEqual(report['quality_report']['topic_profile'], 'hardware_telemetry')
        self.assertEqual(records[-1]['topic'], '/rehab_arm/motor_state')


if __name__ == '__main__':
    unittest.main()
