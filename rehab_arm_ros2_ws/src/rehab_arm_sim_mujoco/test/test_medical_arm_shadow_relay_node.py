from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.medical_arm_shadow_relay_node import (  # noqa: E402
    DEFAULT_JOINT_MAP,
    DEFAULT_TARGET_JOINT_NAMES,
    JointState,
    build_shadow_trajectory,
    parse_joint_map,
    parse_placeholder_positions,
    parse_string_list,
)


class MedicalArmShadowRelayNodeTests(unittest.TestCase):
    def test_default_map_uses_installed_medical_arm_joints(self) -> None:
        self.assertEqual(
            DEFAULT_JOINT_MAP,
            {
                'shoulder_lift_joint': 'jian_hengxiang_joint',
                'elbow_lift_joint': 'jian_zongxiang_joint',
                'shoulder_abduction_joint': 'zhou_zongxiang_joint',
                'upper_arm_rotation_joint': 'jian_xuanzhuan_joint',
            },
        )
        self.assertEqual(parse_joint_map(''), DEFAULT_JOINT_MAP)

    def test_parse_joint_map_accepts_json_object(self) -> None:
        payload = {'shoulder_lift_joint': 'jian_hengxiang_joint'}
        self.assertEqual(parse_joint_map(json.dumps(payload)), payload)

    def test_parse_target_joint_names_accepts_json_list(self) -> None:
        payload = ['jian_hengxiang_joint', 'jian_xuanzhuan_joint']
        self.assertEqual(
            parse_string_list(json.dumps(payload), default=DEFAULT_TARGET_JOINT_NAMES, parameter_name='target_joint_names_json'),
            payload,
        )

    def test_parse_placeholder_positions_accepts_json_object(self) -> None:
        payload = {'jian_hengxiang_joint': 0.25}
        self.assertEqual(parse_placeholder_positions(json.dumps(payload)), payload)

    def test_build_shadow_trajectory_publishes_full_medical_arm_target_by_default(self) -> None:
        source = JointState()
        source.name = ['shoulder_lift_joint', 'elbow_lift_joint', 'shoulder_abduction_joint', 'upper_arm_rotation_joint']
        source.position = [0.123, 0.234, 0.345, 0.456]

        trajectory = build_shadow_trajectory(
            source,
            DEFAULT_JOINT_MAP,
            0.25,
            publish_full_target=True,
            target_joint_names=DEFAULT_TARGET_JOINT_NAMES,
        )

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(trajectory.joint_names, DEFAULT_TARGET_JOINT_NAMES)
        self.assertEqual(list(trajectory.points[0].positions), [0.123, 0.234, 0.456, 0.345, 0.0, 0.0])
        self.assertEqual(trajectory.points[0].time_from_start.nanosec, 250000000)

    def test_build_shadow_trajectory_uses_configured_placeholders_for_unconnected_joints(self) -> None:
        source = JointState()
        source.name = ['upper_arm_rotation_joint']
        source.position = [0.123]

        trajectory = build_shadow_trajectory(
            source,
            DEFAULT_JOINT_MAP,
            0.25,
            publish_full_target=True,
            target_joint_names=DEFAULT_TARGET_JOINT_NAMES,
            placeholder_positions={'jian_hengxiang_joint': 0.2},
        )

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(list(trajectory.points[0].positions), [0.2, 0.0, 0.123, 0.0, 0.0, 0.0])

    def test_build_shadow_trajectory_can_use_sparse_legacy_mode(self) -> None:
        source = JointState()
        source.name = ['upper_arm_rotation_joint']
        source.position = [0.123]

        trajectory = build_shadow_trajectory(source, DEFAULT_JOINT_MAP, 0.25, publish_full_target=False)

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(trajectory.joint_names, ['jian_xuanzhuan_joint'])
        self.assertEqual(list(trajectory.points[0].positions), [0.123])

    def test_build_shadow_trajectory_ignores_unmapped_joints_in_sparse_mode(self) -> None:
        source = JointState()
        source.name = ['unknown_joint']
        source.position = [1.0]

        self.assertIsNone(build_shadow_trajectory(source, DEFAULT_JOINT_MAP, 0.25, publish_full_target=False))

    def test_build_shadow_trajectory_publishes_placeholders_without_live_mapping_in_full_mode(self) -> None:
        source = JointState()
        source.name = ['unknown_joint']
        source.position = [1.0]

        trajectory = build_shadow_trajectory(
            source,
            DEFAULT_JOINT_MAP,
            0.25,
            publish_full_target=True,
            target_joint_names=DEFAULT_TARGET_JOINT_NAMES,
        )

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(trajectory.joint_names, DEFAULT_TARGET_JOINT_NAMES)
        self.assertEqual(list(trajectory.points[0].positions), [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


if __name__ == '__main__':
    unittest.main()
