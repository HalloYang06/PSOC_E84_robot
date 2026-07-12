from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.f103_sensor_state import (  # noqa: E402
    parse_f103_health_payload,
    parse_f103_sensor_payload,
)


class F103SensorStateTests(unittest.TestCase):
    def test_parse_sensor_payload(self) -> None:
        payload = parse_f103_sensor_payload(bytes.fromhex('3412D6FFCDAB4B07'))

        self.assertEqual(payload['schema_version'], 'rehab_arm_sensor_state_v1')
        self.assertEqual(payload['source'], 'f103_sensor')
        self.assertEqual(payload['id_hex'], '0x7C2')
        self.assertEqual(payload['emg_raw'], 0x1234)
        self.assertEqual(payload['emg_filtered'], -42)
        self.assertEqual(payload['heart_rate_raw'], 0xABCD)
        self.assertEqual(payload['heart_rate_bpm'], 75)
        self.assertEqual(payload['flags_hex'], '0x07')
        self.assertIs(payload['emg_contact'], True)
        self.assertIs(payload['imu_valid'], True)
        self.assertIs(payload['heart_rate_valid'], True)
        self.assertEqual(payload['control_boundary'], 'telemetry_only_not_motion_permission')

    def test_parse_short_sensor_payload_is_invalid_but_keeps_raw_data(self) -> None:
        payload = parse_f103_sensor_payload(bytes.fromhex('010203'))

        self.assertIs(payload['valid'], False)
        self.assertEqual(payload['detail'], 'short_frame')
        self.assertEqual(payload['dlc'], 3)
        self.assertEqual(payload['data'], '010203')

    def test_parse_health_payload(self) -> None:
        payload = parse_f103_health_payload(bytes([2, 3, 0, 128]))

        self.assertEqual(payload['schema_version'], 'rehab_arm_sensor_health_v1')
        self.assertEqual(payload['source'], 'f103_health')
        self.assertEqual(payload['id_hex'], '0x7C3')
        self.assertEqual(payload['state_code'], 2)
        self.assertEqual(payload['state'], 'streaming')
        self.assertEqual(payload['error_count'], 3)
        self.assertEqual(payload['queue_fill'], 128)
        self.assertEqual(payload['queue_fill_percent'], 50.2)

    def test_parse_unknown_health_state(self) -> None:
        payload = parse_f103_health_payload(bytes([99, 0, 0, 0]))

        self.assertEqual(payload['state'], 'unknown')
        self.assertIs(payload['valid'], True)


if __name__ == '__main__':
    unittest.main()
