from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]


class SimDataCollectionLaunchTests(unittest.TestCase):
    def test_package_metadata_names_bringup_package(self) -> None:
        package_xml = ET.parse(PACKAGE_DIR / 'package.xml').getroot()

        self.assertEqual(package_xml.findtext('name'), 'rehab_arm_bringup')
        exec_depends = {element.text for element in package_xml.findall('exec_depend')}
        self.assertIn('rehab_arm_sim_mujoco', exec_depends)
        self.assertIn('rehab_arm_psoc_bridge', exec_depends)

    def test_launch_starts_sim_motor_state_bridge_and_recorder(self) -> None:
        text = (PACKAGE_DIR / 'launch' / 'sim_data_collection.launch.py').read_text(encoding='utf-8')

        self.assertIn("package='rehab_arm_sim_mujoco'", text)
        self.assertIn("executable='mujoco_sim_node.py'", text)
        self.assertIn("executable='joint_state_motor_state_node.py'", text)
        self.assertIn("executable='data_recorder_node.py'", text)
        self.assertNotIn("demo_trajectory_node", text)
        self.assertNotIn("enable_demo_trajectory", text)
        self.assertNotIn("IfCondition", text)
        self.assertIn("'mode': 'simulation_data_collection'", text)
        self.assertIn("'source': 'simulation_joint_state_bridge'", text)


if __name__ == '__main__':
    unittest.main()
