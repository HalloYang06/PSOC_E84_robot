from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.psoc_status import parse_psoc_status_payload
from rehab_arm_psoc_bridge.safety_gate import psoc_motion_gate_detail


class SafetyGateTests(unittest.TestCase):
    def test_no_status_rejects(self) -> None:
        allowed, detail = psoc_motion_gate_detail(None)

        self.assertFalse(allowed)
        self.assertEqual(detail, 'no PSoC status received')

    def test_legacy_ok_status_still_rejects_without_motion_allowed(self) -> None:
        status = parse_psoc_status_payload(bytes.fromhex('A50107005E9D0000'))

        self.assertEqual(status['state'], 'ok')
        self.assertIs(status['motion_allowed'], False)
        allowed, detail = psoc_motion_gate_detail(status)

        self.assertFalse(allowed)
        self.assertIn('motion_allowed is not true', detail)
        self.assertIn('protocol_version=1', detail)
        self.assertIn('state=ok', detail)

    def test_logging_only_status_rejects_with_detail(self) -> None:
        status = parse_psoc_status_payload(bytes([0xA5, 2, 7, 0, 1, 1, 10, 0]))

        allowed, detail = psoc_motion_gate_detail(status)

        self.assertFalse(allowed)
        self.assertIn('state=limited', detail)
        self.assertIn('control_mode=logging_only', detail)
        self.assertIn('detail=logging_only_no_motor_output', detail)

    def test_v2_armed_motion_allowed_accepts(self) -> None:
        status = parse_psoc_status_payload(bytes([0xA5, 4, 7, 0, 0, 3, 0, 0]))

        allowed, detail = psoc_motion_gate_detail(status)

        self.assertTrue(allowed)
        self.assertEqual(detail, 'PSoC motion_allowed true')


if __name__ == '__main__':
    unittest.main()
