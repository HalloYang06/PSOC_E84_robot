from __future__ import annotations

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.mujoco_backend import (  # noqa: E402
    JOINT_NAMES,
    build_rehab_arm_mjcf,
    clamp_positions,
)


class MujocoBackendTests(unittest.TestCase):
    def test_mjcf_contains_the_standard_five_joint_contract(self) -> None:
        xml = build_rehab_arm_mjcf()
        root = ElementTree.fromstring(xml)

        joint_names = [joint.attrib['name'] for joint in root.findall('.//joint')]
        actuator_names = [actuator.attrib['joint'] for actuator in root.findall('.//position')]

        self.assertEqual(joint_names, JOINT_NAMES)
        self.assertEqual(actuator_names, JOINT_NAMES)

    def test_mjcf_encodes_joint_ranges_in_radians(self) -> None:
        root = ElementTree.fromstring(build_rehab_arm_mjcf())
        shoulder = root.find(".//joint[@name='shoulder_lift_joint']")
        elbow = root.find(".//joint[@name='elbow_lift_joint']")

        self.assertIsNotNone(shoulder)
        self.assertEqual(shoulder.attrib['range'], '-0.7 1.4')
        self.assertIsNotNone(elbow)
        self.assertEqual(elbow.attrib['range'], '0.0 1.8')

    def test_target_positions_are_clamped_to_safety_limits(self) -> None:
        positions = clamp_positions([9.0, -9.0, 0.1, 0.2, -0.2])

        self.assertEqual(positions[0], 1.4)
        self.assertEqual(positions[1], 0.0)
        self.assertEqual(positions[2:], [0.1, 0.2, -0.2])


if __name__ == '__main__':
    unittest.main()
