from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.medical_arm_shadow_relay_node import (  # noqa: E402
    DEFAULT_JOINT_MAP,
    JointState,
    build_shadow_trajectory,
    parse_joint_map,
)


class MedicalArmShadowRelayNodeTests(unittest.TestCase):
    def test_default_map_shadows_external_motor7_to_jian_xuanzhuan(self) -> None:
        self.assertEqual(DEFAULT_JOINT_MAP, {'forearm_rotation_joint': 'jian_xuanzhuan_joint'})
        self.assertEqual(parse_joint_map(''), DEFAULT_JOINT_MAP)

    def test_parse_joint_map_accepts_json_object(self) -> None:
        payload = {'forearm_rotation_joint': 'jian_xuanzhuan_joint'}
        self.assertEqual(parse_joint_map(json.dumps(payload)), payload)

    def test_build_shadow_trajectory_maps_known_joint(self) -> None:
        source = JointState()
        source.name = ['forearm_rotation_joint']
        source.position = [0.123]

        trajectory = build_shadow_trajectory(source, DEFAULT_JOINT_MAP, 0.25)

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(trajectory.joint_names, ['jian_xuanzhuan_joint'])
        self.assertEqual(trajectory.points[0].positions, [0.123])
        self.assertEqual(trajectory.points[0].time_from_start.nanosec, 250000000)

    def test_build_shadow_trajectory_ignores_unmapped_joints(self) -> None:
        source = JointState()
        source.name = ['unknown_joint']
        source.position = [1.0]

        self.assertIsNone(build_shadow_trajectory(source, DEFAULT_JOINT_MAP, 0.25))


if __name__ == '__main__':
    unittest.main()
