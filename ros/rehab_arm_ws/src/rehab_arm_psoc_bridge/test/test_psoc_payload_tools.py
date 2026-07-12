from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.decode_psoc_cmd import decode_payload, parse_payload_hex
from rehab_arm_psoc_bridge.encode_psoc_cmd import encode_target


class PsocPayloadToolTests(unittest.TestCase):
    def test_encode_known_shoulder_target(self) -> None:
        payload = encode_target('shoulder_lift_joint', 0.1, rpm=5, torque_ma=0)
        self.assertEqual(payload.hex().upper(), '0300390005000000')

    def test_decode_known_shoulder_payload(self) -> None:
        decoded = decode_payload(bytes.fromhex('0300390005000000'))

        self.assertEqual(decoded['can_id'], '0x320')
        self.assertEqual(decoded['cmd'], '0x03')
        self.assertEqual(decoded['joint_id'], 0)
        self.assertEqual(decoded['joint_name'], 'shoulder_lift_joint')
        self.assertEqual(decoded['deg_x10'], 57)
        self.assertAlmostEqual(decoded['target_deg'], 5.7)
        self.assertAlmostEqual(decoded['target_rad'], math.radians(5.7))
        self.assertEqual(decoded['rpm'], 5)
        self.assertEqual(decoded['torque_ma'], 0)

    def test_round_trip_negative_position_uses_python_int_truncation(self) -> None:
        payload = encode_target('upper_arm_rotation_joint', -0.2, rpm=7, torque_ma=-12)
        decoded = decode_payload(payload)

        self.assertEqual(decoded['joint_id'], 3)
        self.assertEqual(decoded['joint_name'], 'upper_arm_rotation_joint')
        self.assertEqual(decoded['deg_x10'], int(math.degrees(-0.2) * 10.0))
        self.assertEqual(decoded['rpm'], 7)
        self.assertEqual(decoded['torque_ma'], -12)

    def test_parse_payload_hex_accepts_spaces_and_prefix(self) -> None:
        self.assertEqual(
            parse_payload_hex('0x03 00 39 00 05 00 00 00'),
            bytes.fromhex('0300390005000000'),
        )

    def test_encode_rejects_out_of_limit_position(self) -> None:
        with self.assertRaisesRegex(ValueError, 'outside'):
            encode_target('shoulder_lift_joint', 99.0, rpm=5, torque_ma=0)

    def test_encode_rejects_nonfinite_position(self) -> None:
        with self.assertRaisesRegex(ValueError, 'finite'):
            encode_target('shoulder_lift_joint', math.nan, rpm=5, torque_ma=0)

    def test_encode_rejects_unknown_joint(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unknown joint'):
            encode_target('not_a_joint', 0.0, rpm=5, torque_ma=0)

    def test_decode_rejects_short_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, 'expected 8 payload bytes'):
            decode_payload(bytes.fromhex('03003900'))

    def test_parse_payload_hex_rejects_bad_length(self) -> None:
        with self.assertRaisesRegex(ValueError, '16 hex chars'):
            parse_payload_hex('03003900')

    def test_decode_unknown_joint_is_visible(self) -> None:
        decoded = decode_payload(bytes([0x03, 99, 0, 0, 5, 0, 0, 0]))
        self.assertEqual(decoded['joint_id'], 99)
        self.assertEqual(decoded['joint_name'], 'unknown')


if __name__ == '__main__':
    unittest.main()
