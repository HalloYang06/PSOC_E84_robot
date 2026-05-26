from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.candump_motor_telemetry import (  # noqa: E402
    CONTROL_BOUNDARY,
    decode_lingzu_engineering_values,
    convert_candump_to_records,
    decode_cansimple_encoder_estimate,
    decode_cansimple_heartbeat,
    decode_private_active_report,
    parse_candump_line,
)


def candump_line(relative_time: float, can_id: str, data: bytes) -> str:
    hex_data = ' '.join(f'{byte:02X}' for byte in data)
    return f' ({relative_time:010.6f})  can0  {can_id}   [{len(data)}]  {hex_data}\n'


class CandumpMotorTelemetryTests(unittest.TestCase):
    def test_parse_candump_line(self) -> None:
        frame = parse_candump_line(' (001.230000)  can0  069   [8]  00 00 80 3F 00 00 00 40')

        self.assertEqual(frame['can_id'], 0x069)
        self.assertEqual(frame['dlc'], 8)
        self.assertEqual(frame['data'], b'\x00\x00\x80?\x00\x00\x00@')

    def test_parse_candump_log_hash_line(self) -> None:
        frame = parse_candump_line('(1779777167.168395) can0 180006FD#BE9B7FFF7FFF0136')

        self.assertEqual(frame['can_id'], 0x180006FD)
        self.assertEqual(frame['dlc'], 8)
        self.assertEqual(frame['data'], bytes.fromhex('BE9B7FFF7FFF0136'))

    def test_decode_cansimple_heartbeat(self) -> None:
        frame = parse_candump_line(candump_line(0.1, '061', b'\x00\x00\x00\x00\x08\x80\xCE\x00'))

        heartbeat = decode_cansimple_heartbeat(frame)

        self.assertEqual(heartbeat['node_id'], 3)
        self.assertEqual(heartbeat['axis_state'], 8)
        self.assertIs(heartbeat['enabled'], True)
        self.assertIs(heartbeat['fault'], False)

    def test_decode_encoder_estimate_converts_turns_to_radians(self) -> None:
        data = struct.pack('<ff', 0.25, 0.5)
        frame = parse_candump_line(candump_line(0.2, '069', data))
        heartbeat = {'enabled': True, 'fault': False, 'error_code': '0x00000000', 'axis_state': 8}

        motor = decode_cansimple_encoder_estimate(frame, heartbeat)

        self.assertEqual(motor['motor_id'], 3)
        self.assertEqual(motor['vendor'], 'Sitaiwei')
        self.assertEqual(motor['protocol'], 'cansimple_encoder_estimate')
        self.assertAlmostEqual(motor['position'], 0.25 * math.tau)
        self.assertAlmostEqual(motor['velocity'], 0.5 * math.tau)
        self.assertEqual(motor['raw_can_id'], '0x069')
        self.assertIs(motor['enabled'], True)

    def test_decode_private_active_report_preserves_raw_fields(self) -> None:
        frame = parse_candump_line('(1779777167.170439) can0 180004FD#97BA7FCF7FFF0140')

        motor = decode_private_active_report(frame)

        self.assertEqual(motor['motor_id'], 4)
        self.assertEqual(motor['vendor'], 'Lingzu')
        self.assertEqual(motor['protocol'], 'lingzu_robstride_private_active_report')
        self.assertEqual(motor['actuator_type'], 'unknown')
        self.assertEqual(motor['engineering_decode'], 'raw_only_actuator_type_unconfirmed')
        self.assertIsNone(motor['position'])
        self.assertIsNone(motor['velocity'])
        self.assertIsNone(motor['torque'])
        self.assertIsNone(motor['temperature'])
        self.assertEqual(motor['raw_position_u16'], 0x97BA)
        self.assertEqual(motor['raw_velocity_u16'], 0x7FCF)
        self.assertEqual(motor['raw_torque_u16'], 0x7FFF)
        self.assertEqual(motor['temperature_raw'], 0x0140)
        self.assertEqual(motor['raw_temperature_u16'], 0x0140)
        self.assertEqual(motor['status_raw'], '0x40')
        self.assertEqual(motor['raw_can_id'], '0x180004FD')

    def test_decode_lingzu_engineering_values_when_actuator_model_is_known(self) -> None:
        values = decode_lingzu_engineering_values(
            4,
            0x8000,
            0x7FFF,
            0x8000,
            0x0140,
            actuator_type_by_id={4: 'RS00'},
        )

        self.assertEqual(values['actuator_type'], 'RS00')
        self.assertEqual(values['engineering_decode'], 'lingzu_robstride_ros_sample_actuator_mapping')
        self.assertAlmostEqual(values['position'], 0.0003835069, places=6)
        self.assertAlmostEqual(values['velocity'], 0.0, places=6)
        self.assertAlmostEqual(values['torque'], 0.0005188147, places=6)
        self.assertAlmostEqual(values['temperature'], 32.0)

    def test_convert_candump_to_motor_state_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            source.write_text(
                candump_line(0.0, '061', b'\x00\x00\x00\x00\x08\x80\xCE\x00')
                + candump_line(0.01, '069', struct.pack('<ff', 0.25, 0.5))
                + candump_line(0.02, '069', struct.pack('<ff', 0.30, 0.1)),
                encoding='utf-8',
            )

            records, summary = convert_candump_to_records(source, 'rehab-arm-alpha', 'nanopi-m5', 's1')

        self.assertIs(summary['ok'], True)
        self.assertEqual(summary['motor_state_count'], 2)
        self.assertEqual(records[0]['record_type'], 'session_metadata')
        self.assertEqual(records[0]['control_boundary'], CONTROL_BOUNDARY)
        self.assertEqual(records[1]['topic'], '/rehab_arm/motor_state')
        payload = records[1]['payload']
        self.assertEqual(payload['schema_version'], 'rehab_arm_motor_state_v1')
        self.assertEqual(payload['motors'][0]['motor_id'], 3)
        self.assertEqual(payload['control_boundary'], CONTROL_BOUNDARY)

    def test_convert_candump_includes_private_active_report_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            source.write_text(
                '(1779777167.168395) can0 180006FD#BE9B7FFF7FFF0136\n'
                '(1779777167.170439) can0 180004FD#97BA7FCF7FFF0140\n',
                encoding='utf-8',
            )

            records, summary = convert_candump_to_records(source, 'rehab-arm-alpha', 'nanopi-m5', 's1')

        self.assertIs(summary['ok'], True)
        self.assertEqual(summary['private_active_report_count'], 2)
        self.assertEqual(summary['motor_state_count'], 2)
        self.assertEqual(records[1]['payload']['source'], 'candump_private_active_report')
        self.assertEqual(records[1]['payload']['motors'][0]['motor_id'], 6)
        self.assertEqual(records[1]['payload']['motors'][0]['vendor'], 'Lingzu')

    def test_cli_writes_output_to_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'capture.log'
            output = Path(tmpdir) / 'converted.jsonl'
            source.write_text(
                candump_line(0.0, '061', b'\x00\x00\x00\x00\x08\x80\xCE\x00')
                + candump_line(0.01, '069', struct.pack('<ff', 0.25, 0.5)),
                encoding='utf-8',
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_psoc_bridge' / 'candump_motor_telemetry.py'),
                    str(source),
                    '--output',
                    str(output),
                    '--session-id',
                    's1',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(output.exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary['motor_state_count'], 1)
            self.assertEqual(len(output.read_text(encoding='utf-8').splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
