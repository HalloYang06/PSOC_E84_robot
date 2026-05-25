from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.psoc_status import parse_psoc_status_payload


class PsocStatusTests(unittest.TestCase):
    def test_legacy_status_ok_is_compatible(self) -> None:
        status = parse_psoc_status_payload(bytes.fromhex('A50107005E9D0000'))

        self.assertEqual(status['protocol_version'], 1)
        self.assertEqual(status['state'], 'ok')
        self.assertEqual(status['marker'], 0xA5)
        self.assertEqual(status['seq'], 1)
        self.assertEqual(status['motors'], 7)
        self.assertEqual(status['error_code'], 0)
        self.assertEqual(status['status_data'], '5E9D0000')

    def test_status_v2_limited_logging_only(self) -> None:
        status = parse_psoc_status_payload(bytes([0xA5, 2, 7, 0, 1, 1, 10, 3]))

        self.assertEqual(status['protocol_version'], 2)
        self.assertEqual(status['state'], 'limited')
        self.assertEqual(status['control_mode'], 'logging_only')
        self.assertEqual(status['detail'], 'logging_only_no_motor_output')
        self.assertEqual(status['heartbeat_age_ms'], 300)

    def test_status_v2_emergency_stop(self) -> None:
        status = parse_psoc_status_payload(bytes([0xA5, 3, 7, 0, 2, 5, 7, 1]))

        self.assertEqual(status['protocol_version'], 2)
        self.assertEqual(status['state'], 'emergency_stop')
        self.assertEqual(status['control_mode'], 'emergency_stop')
        self.assertEqual(status['detail'], 'emergency_stop')

    def test_status_v2_error_code_forces_fault(self) -> None:
        status = parse_psoc_status_payload(bytes([0xA5, 4, 7, 9, 0, 2, 0, 0]))

        self.assertEqual(status['protocol_version'], 2)
        self.assertEqual(status['state'], 'fault')
        self.assertEqual(status['detail'], 'error_code=9')

    def test_status_v2_reject_reason_detail_codes(self) -> None:
        expected = {
            1: 'heartbeat_timeout',
            2: 'unsupported_command',
            3: 'unknown_joint',
            4: 'target_out_of_limit',
            5: 'velocity_out_of_limit',
            6: 'torque_out_of_limit',
        }

        for code, detail in expected.items():
            with self.subTest(code=code):
                status = parse_psoc_status_payload(bytes([0xA5, 5, 7, 0, 1, 1, code, 0]))
                self.assertEqual(status['protocol_version'], 2)
                self.assertEqual(status['state'], 'limited')
                self.assertEqual(status['control_mode'], 'logging_only')
                self.assertEqual(status['detail_code'], code)
                self.assertEqual(status['detail'], detail)

    def test_bad_marker_is_fault(self) -> None:
        status = parse_psoc_status_payload(bytes.fromhex('AA0107005E9D0000'))

        self.assertEqual(status['state'], 'fault')
        self.assertEqual(status['detail'], 'invalid PSoC status marker')

    def test_short_status_is_fault(self) -> None:
        status = parse_psoc_status_payload(bytes.fromhex('A50107'))

        self.assertEqual(status['state'], 'fault')
        self.assertEqual(status['detail'], 'PSoC status too short')


if __name__ == '__main__':
    unittest.main()
