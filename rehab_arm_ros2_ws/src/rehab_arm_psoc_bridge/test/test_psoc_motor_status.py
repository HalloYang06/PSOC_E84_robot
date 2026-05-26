from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.psoc_motor_status import (  # noqa: E402
    M33_MOTOR_STATUS_MARKER,
    MOTOR_STATUS_FLAG_ENABLED,
    MOTOR_STATUS_FLAG_FAULT,
    MOTOR_STATUS_FLAG_LIMITED,
    is_m33_motor_status_id,
    make_m33_motor_state_payload,
    parse_m33_motor_status_frame,
)


class PsocMotorStatusTests(unittest.TestCase):
    def test_accepts_reserved_status_id_range(self) -> None:
        self.assertIs(is_m33_motor_status_id(0x330), True)
        self.assertIs(is_m33_motor_status_id(0x337), True)
        self.assertIs(is_m33_motor_status_id(0x322), False)
        self.assertIs(is_m33_motor_status_id(0x7C2), False)

    def test_parse_m33_motor_status_frame(self) -> None:
        data = bytes([
            M33_MOTOR_STATUS_MARKER,
            7,
            4,
            MOTOR_STATUS_FLAG_ENABLED | MOTOR_STATUS_FLAG_LIMITED,
            *int(1234).to_bytes(2, 'little', signed=True),
            12,
            36,
        ])

        motor = parse_m33_motor_status_frame(0x330, data)

        self.assertIs(motor['valid'], True)
        self.assertEqual(motor['protocol'], 'm33_motor_status_v1')
        self.assertEqual(motor['protocol_status'], 'proposed_firmware_pending')
        self.assertEqual(motor['status_slot'], 0)
        self.assertEqual(motor['joint_name'], 'shoulder_lift_joint')
        self.assertEqual(motor['motor_id'], 4)
        self.assertEqual(motor['vendor'], 'Lingzu')
        self.assertAlmostEqual(motor['position'], 1.234)
        self.assertAlmostEqual(motor['velocity'], 1.2)
        self.assertEqual(motor['temperature'], 36.0)
        self.assertIs(motor['enabled'], True)
        self.assertIs(motor['limited'], True)
        self.assertIs(motor['fault'], False)
        self.assertEqual(motor['raw_can_id'], '0x330')

    def test_parse_negative_position_and_velocity(self) -> None:
        data = bytes([
            M33_MOTOR_STATUS_MARKER,
            8,
            3,
            MOTOR_STATUS_FLAG_ENABLED,
            *int(-700).to_bytes(2, 'little', signed=True),
            0xF6,
            0xFF,
        ])

        motor = parse_m33_motor_status_frame(0x332, data)

        self.assertIs(motor['valid'], True)
        self.assertEqual(motor['joint_name'], 'shoulder_abduction_joint')
        self.assertEqual(motor['motor_id'], 3)
        self.assertEqual(motor['vendor'], 'Sitaiwei')
        self.assertAlmostEqual(motor['position'], -0.7)
        self.assertAlmostEqual(motor['velocity'], -1.0)
        self.assertIsNone(motor['temperature'])

    def test_fault_flag_is_preserved(self) -> None:
        data = bytes([
            M33_MOTOR_STATUS_MARKER,
            9,
            6,
            MOTOR_STATUS_FLAG_FAULT,
            0,
            0,
            0,
            40,
        ])

        motor = parse_m33_motor_status_frame(0x334, data)

        self.assertIs(motor['valid'], True)
        self.assertIs(motor['enabled'], False)
        self.assertIs(motor['fault'], True)
        self.assertEqual(motor['joint_name'], 'forearm_rotation_joint')

    def test_invalid_marker_is_rejected(self) -> None:
        data = bytes([0x00, 1, 4, MOTOR_STATUS_FLAG_ENABLED, 0, 0, 0, 30])

        motor = parse_m33_motor_status_frame(0x330, data)

        self.assertIs(motor['valid'], False)
        self.assertEqual(motor['detail'], 'invalid M33 motor status marker')

    def test_invalid_length_is_rejected(self) -> None:
        motor = parse_m33_motor_status_frame(0x330, b'\xB3\x01')

        self.assertIs(motor['valid'], False)
        self.assertEqual(motor['detail'], 'M33 motor status payload must be 8 bytes')

    def test_make_motor_state_payload_keeps_only_valid_frames(self) -> None:
        valid = parse_m33_motor_status_frame(
            0x330,
            bytes([M33_MOTOR_STATUS_MARKER, 1, 4, MOTOR_STATUS_FLAG_ENABLED, 0, 0, 0, 32]),
        )
        invalid = parse_m33_motor_status_frame(0x331, bytes([0, 1, 5, 0, 0, 0, 0, 32]))

        payload = make_m33_motor_state_payload([valid, invalid], 'rehab-arm-alpha', 'nanopi-m5', now=10.0)

        self.assertEqual(payload['schema_version'], 'rehab_arm_motor_state_v1')
        self.assertEqual(payload['source'], 'm33_motor_status_v1')
        self.assertEqual(payload['protocol_status'], 'proposed_firmware_pending')
        self.assertEqual(payload['frame_count'], 2)
        self.assertEqual(payload['valid_motor_count'], 1)
        self.assertEqual(payload['motors'][0]['motor_id'], 4)


if __name__ == '__main__':
    unittest.main()
