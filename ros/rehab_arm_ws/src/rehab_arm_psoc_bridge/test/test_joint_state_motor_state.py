from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.data_recording import make_motor_entries_from_joint_state  # noqa: E402
from rehab_arm_psoc_bridge.joint_state_motor_state_node import parse_joint_motor_map  # noqa: E402


class JointStateMotorStateTests(unittest.TestCase):
    def test_make_motor_entries_from_joint_state_without_mapping(self) -> None:
        motors = make_motor_entries_from_joint_state(
            names=['shoulder_lift_joint'],
            positions=[0.1],
            velocities=[0.2],
            efforts=[0.3],
        )

        self.assertEqual(motors[0]['joint_name'], 'shoulder_lift_joint')
        self.assertIsNone(motors[0]['motor_id'])
        self.assertEqual(motors[0]['protocol'], 'simulated_joint_state')
        self.assertEqual(motors[0]['position'], 0.1)
        self.assertEqual(motors[0]['fault'], False)

    def test_make_motor_entries_from_joint_state_with_mapping(self) -> None:
        motors = make_motor_entries_from_joint_state(
            names=['shoulder_lift_joint'],
            positions=[0.1],
            velocities=[],
            efforts=[],
            joint_motor_map={
                'shoulder_lift_joint': {
                    'motor_id': 4,
                    'protocol': 'private_mit',
                    'raw_can_id': '0x04',
                    'enabled': True,
                },
            },
        )

        self.assertEqual(motors[0]['motor_id'], 4)
        self.assertEqual(motors[0]['protocol'], 'private_mit')
        self.assertIsNone(motors[0]['velocity'])
        self.assertEqual(motors[0]['raw_can_id'], '0x04')
        self.assertIs(motors[0]['enabled'], True)

    def test_parse_joint_motor_map(self) -> None:
        mapping = parse_joint_motor_map(
            '{"shoulder_lift_joint":{"motor_id":4,"protocol":"private_mit"}}',
        )

        self.assertEqual(mapping['shoulder_lift_joint']['motor_id'], 4)
        self.assertEqual(mapping['shoulder_lift_joint']['protocol'], 'private_mit')

    def test_parse_joint_motor_map_rejects_list(self) -> None:
        with self.assertRaises(ValueError):
            parse_joint_motor_map('[]')


if __name__ == '__main__':
    unittest.main()
