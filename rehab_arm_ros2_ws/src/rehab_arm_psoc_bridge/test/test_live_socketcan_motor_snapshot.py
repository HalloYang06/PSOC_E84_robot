from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_psoc_bridge.live_socketcan_motor_snapshot import (  # noqa: E402
    CONTROL_BOUNDARY,
    decode_live_motor_frame,
    frame_key,
    pack_socketcan_frame,
    private_active_report_frame,
    unpack_socketcan_frame,
)


class LiveSocketcanMotorSnapshotTests(unittest.TestCase):
    def test_pack_and_unpack_standard_frame(self) -> None:
        raw = pack_socketcan_frame(0x069, b'\x01\x02', is_extended=False)

        frame = unpack_socketcan_frame(raw)

        self.assertEqual(frame['can_id'], 0x069)
        self.assertIs(frame['is_extended'], False)
        self.assertEqual(frame['dlc'], 2)
        self.assertEqual(frame['data'], b'\x01\x02')
        self.assertEqual(frame_key(frame), '0x069')

    def test_pack_and_unpack_extended_frame(self) -> None:
        raw = pack_socketcan_frame(0x180007FD, bytes.fromhex('A4EE7FFF7FFF0140'), is_extended=True)

        frame = unpack_socketcan_frame(raw)

        self.assertEqual(frame['can_id'], 0x180007FD)
        self.assertIs(frame['is_extended'], True)
        self.assertEqual(frame['dlc'], 8)
        self.assertEqual(frame_key(frame), '0x180007FD')

    def test_private_active_report_frame_uses_motor_id_and_enable_flag(self) -> None:
        frame = unpack_socketcan_frame(private_active_report_frame(7, True))

        self.assertEqual(frame['can_id'], 0x1800FD07)
        self.assertIs(frame['is_extended'], True)
        self.assertEqual(frame['data'], bytes([1, 2, 3, 4, 5, 6, 1, 0]))

    def test_decode_cansimple_heartbeat_and_encoder(self) -> None:
        heartbeat_by_node: dict[int, dict[str, object]] = {}
        heartbeat_frame = {
            'can_id': 0x061,
            'is_extended': False,
            'dlc': 8,
            'data': bytes.fromhex('000000000180CECC'),
        }
        key, heartbeat = decode_live_motor_frame(heartbeat_frame, heartbeat_by_node)
        encoder_frame = {
            'can_id': 0x069,
            'is_extended': False,
            'dlc': 8,
            'data': struct.pack('<ff', 0.25, 0.5),
        }

        encoder_key, encoder = decode_live_motor_frame(encoder_frame, heartbeat_by_node)

        self.assertEqual(key, 'motor3_heartbeat')
        self.assertEqual(heartbeat['axis_state'], 1)
        self.assertEqual(encoder_key, 'motor3_encoder')
        self.assertEqual(encoder['motor_id'], 3)
        self.assertAlmostEqual(encoder['position_turns'], 0.25)
        self.assertEqual(encoder['control_boundary'], CONTROL_BOUNDARY)

    def test_decode_private_active_report(self) -> None:
        frame = {
            'can_id': 0x180007FD,
            'is_extended': True,
            'dlc': 8,
            'data': bytes.fromhex('A4EE7FFF7FFF0140'),
        }

        key, motor = decode_live_motor_frame(frame, {})

        self.assertEqual(key, 'motor7_active_report')
        self.assertEqual(motor['motor_id'], 7)
        self.assertEqual(motor['protocol'], 'lingzu_robstride_private_active_report')
        self.assertEqual(motor['raw_position_u16'], 0xA4EE)
        self.assertEqual(motor['control_boundary'], CONTROL_BOUNDARY)


if __name__ == '__main__':
    unittest.main()
