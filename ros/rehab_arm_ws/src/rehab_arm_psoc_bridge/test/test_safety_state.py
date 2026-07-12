from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.safety_state import bridge_safety_payload


class SafetyStateTests(unittest.TestCase):
    def test_bridge_safety_payload_marks_bridge_state_semantics(self) -> None:
        payload = bridge_safety_payload('limited', 'no PSoC status after 3 heartbeats')

        self.assertEqual(payload['source'], 'psoc_bridge')
        self.assertEqual(payload['state'], 'limited')
        self.assertEqual(payload['control_mode'], 'bridge')
        self.assertEqual(payload['detail'], 'no PSoC status after 3 heartbeats')
        self.assertEqual(payload['detail_semantics'], 'current_bridge_state')
        self.assertEqual(payload['current_detail'], 'no PSoC status after 3 heartbeats')
        self.assertIs(payload['motion_allowed'], False)


if __name__ == '__main__':
    unittest.main()
