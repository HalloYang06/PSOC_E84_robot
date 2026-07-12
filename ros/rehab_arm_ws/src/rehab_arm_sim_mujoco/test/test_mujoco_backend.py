from __future__ import annotations

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.mujoco_backend import (  # noqa: E402
    JOINT_NAMES,
    MEDICAL_ARM_6DOF_JOINT_NAMES,
    MEDICAL_ARM_6DOF_PROFILE,
    build_rehab_arm_mjcf,
    clamp_positions,
    default_model_path,
    joint_names_for_profile,
    load_mjcf_xml,
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

    def test_medical_arm_profile_contains_six_real_urdf_joint_names(self) -> None:
        xml = build_rehab_arm_mjcf(MEDICAL_ARM_6DOF_PROFILE)
        root = ElementTree.fromstring(xml)

        joint_names = [joint.attrib['name'] for joint in root.findall('.//joint')]
        actuator_names = [actuator.attrib['joint'] for actuator in root.findall('.//position')]

        self.assertEqual(joint_names, MEDICAL_ARM_6DOF_JOINT_NAMES)
        self.assertEqual(actuator_names, MEDICAL_ARM_6DOF_JOINT_NAMES)
        self.assertEqual(joint_names_for_profile(MEDICAL_ARM_6DOF_PROFILE), MEDICAL_ARM_6DOF_JOINT_NAMES)

    def test_target_positions_are_clamped_to_safety_limits(self) -> None:
        positions = clamp_positions([9.0, -9.0, 0.1, 0.2, -0.2])

        self.assertEqual(positions[0], 1.4)
        self.assertEqual(positions[1], 0.0)
        self.assertEqual(positions[2:], [0.1, 0.2, -0.2])

    def test_medical_arm_profile_target_positions_are_clamped(self) -> None:
        positions = clamp_positions([9.0, -9.0, 0.1, 9.0, 0.2, -0.2], MEDICAL_ARM_6DOF_PROFILE)

        self.assertEqual(positions[0], 1.5708)
        self.assertEqual(positions[1], -0.5236)
        self.assertEqual(positions[3], 2.3562)
        self.assertEqual(positions[4:], [0.2, -0.2])

    def test_default_model_file_is_available_and_matches_joint_contract(self) -> None:
        model_path = default_model_path()
        self.assertTrue(model_path.exists(), model_path)

        root = ElementTree.fromstring(load_mjcf_xml(str(model_path)))
        joint_names = [joint.attrib['name'] for joint in root.findall('.//joint')]

        self.assertEqual(joint_names, JOINT_NAMES)

    def test_medical_arm_model_file_is_available_and_matches_joint_contract(self) -> None:
        model_path = default_model_path(MEDICAL_ARM_6DOF_PROFILE)
        self.assertTrue(model_path.exists(), model_path)

        root = ElementTree.fromstring(load_mjcf_xml(str(model_path), MEDICAL_ARM_6DOF_PROFILE))
        joint_names = [joint.attrib['name'] for joint in root.findall('.//joint')]

        self.assertEqual(joint_names, MEDICAL_ARM_6DOF_JOINT_NAMES)

    def test_empty_model_path_loads_default_model_file(self) -> None:
        self.assertEqual(load_mjcf_xml(''), default_model_path().read_text(encoding='utf-8'))

    def test_missing_model_path_falls_back_to_generated_model(self) -> None:
        self.assertEqual(load_mjcf_xml('/path/that/does/not/exist.xml'), build_rehab_arm_mjcf())

    def test_joint_state_effort_uses_active_joint_profile_length(self) -> None:
        node_source = (
            PACKAGE_DIR
            / 'rehab_arm_sim_mujoco'
            / 'mujoco_sim_node.py'
        ).read_text(encoding='utf-8')

        self.assertIn('msg.effort = [0.0] * len(self.joint_names)', node_source)
        self.assertNotIn('msg.effort = [0.0] * len(JOINT_NAMES)', node_source)


if __name__ == '__main__':
    unittest.main()
