from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.m33_ros_contract import (  # noqa: E402
    RawCanPayload,
    build_m33_ros_topic_records,
)
from rehab_arm_psoc_bridge.psoc_motor_status import (  # noqa: E402
    M33_MOTOR_STATUS_MARKER,
    MOTOR_STATUS_FLAG_ENABLED,
    MOTOR_STATUS_FLAG_LIMITED,
)


class M33RosContractTests(unittest.TestCase):
    def test_limited_status_with_motor_telemetry_publishes_topics_but_rejects_motion(self) -> None:
        contract = build_m33_ros_topic_records(
            status_data=bytes([0xA5, 2, 7, 0, 1, 1, 10, 0]),
            motor_frames=[
                RawCanPayload(
                    0x330,
                    bytes([
                        M33_MOTOR_STATUS_MARKER,
                        1,
                        7,
                        MOTOR_STATUS_FLAG_ENABLED | MOTOR_STATUS_FLAG_LIMITED,
                        *int(250).to_bytes(2, 'little', signed=True),
                        3,
                        36,
                    ]),
                ),
            ],
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            now=100.25,
        )

        self.assertEqual(contract['schema_version'], 'm33_ros_topic_contract_v1')
        self.assertEqual(contract['topics'], [
            '/rehab_arm/safety_state',
            '/rehab_arm/motor_state',
            '/joint_states',
        ])
        self.assertIs(contract['motion_candidate_allowed'], False)
        self.assertIn('logging_only_no_motor_output', contract['motion_gate_detail'])
        self.assertEqual(contract['safety_state']['state'], 'limited')
        self.assertIs(contract['safety_state']['motion_allowed'], False)
        self.assertEqual(contract['motor_state']['valid_motor_count'], 1)
        self.assertEqual(contract['motor_state']['motors'][0]['joint_name'], 'shoulder_lift_joint')
        self.assertEqual(contract['motor_state']['motors'][0]['control_boundary'], 'telemetry_only_not_motor_command')
        self.assertEqual(contract['joint_state']['name'], ['shoulder_lift_joint'])
        self.assertEqual(contract['joint_state']['position'], [0.25])
        self.assertEqual(contract['joint_state']['velocity'], [0.3])

    def test_only_v2_ok_armed_none_allows_motion_candidate(self) -> None:
        contract = build_m33_ros_topic_records(
            status_data=bytes([0xA5, 9, 7, 0, 0, 3, 0, 0]),
            motor_frames=[],
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            now=101.0,
        )

        self.assertEqual(contract['topics'], ['/rehab_arm/safety_state'])
        self.assertIs(contract['motion_candidate_allowed'], True)
        self.assertEqual(contract['motion_gate_detail'], 'PSoC motion_allowed true')
        self.assertIsNone(contract['motor_state'])
        self.assertIsNone(contract['joint_state'])

    def test_invalid_motor_frame_does_not_create_fake_joint_state(self) -> None:
        contract = build_m33_ros_topic_records(
            status_data=bytes([0xA5, 2, 7, 0, 1, 1, 10, 0]),
            motor_frames=[RawCanPayload(0x330, bytes([0, 1, 7, 0, 0, 0, 0, 36]))],
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            now=102.0,
        )

        self.assertEqual(contract['topics'], ['/rehab_arm/safety_state'])
        self.assertIsNone(contract['motor_state'])
        self.assertIsNone(contract['joint_state'])
        self.assertIs(contract['motion_candidate_allowed'], False)


if __name__ == '__main__':
    unittest.main()
