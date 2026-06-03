from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PACKAGE_DIR.parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.check_sim_env import build_sim_env_report  # noqa: E402


class CheckSimEnvTests(unittest.TestCase):
    def test_report_accepts_fallback_when_mujoco_is_missing(self) -> None:
        available = {
            'rclpy',
            'rehab_arm_psoc_bridge.data_recording',
            'rehab_arm_psoc_bridge.build_manifest',
            'rehab_arm_psoc_bridge.sync_upload',
        }

        report = build_sim_env_report(
            WORKSPACE_ROOT,
            import_checker=lambda module_name: module_name in available,
        )

        self.assertTrue(report['ok'])
        self.assertEqual(report['schema_version'], 'rehab_arm_sim_env_check_v1')
        self.assertEqual(report['readiness'], 'ready_with_fallback_sim')
        self.assertEqual(report['joint_contract']['count'], 5)
        self.assertEqual(report['joint_contract']['profile'], 'legacy_5dof')
        self.assertEqual(report['medical_arm_6dof_contract']['profile'], 'medical_arm_6dof')
        self.assertEqual(report['medical_arm_6dof_contract']['count'], 6)
        self.assertEqual(
            report['medical_arm_6dof_contract']['names'],
            [
                'jian_hengxiang_joint',
                'jian_zongxiang_joint',
                'jian_xuanzhuan_joint',
                'zhou_zongxiang_joint',
                'wanbu_zongxiang_joint',
                'wanbu_hengxiang_joint',
            ],
        )
        self.assertEqual(
            report['medical_arm_6dof_topic_contract']['shadow_trajectory_command']['topic'],
            '/sim/medical_arm/joint_trajectory',
        )
        self.assertEqual(
            report['medical_arm_6dof_topic_contract']['hardware_shadow_current_mapping'],
            {'forearm_rotation_joint': 'jian_xuanzhuan_joint'},
        )
        self.assertEqual(
            report['medical_arm_6dof_topic_contract']['unconnected_joint_policy'],
            'publish_full_6dof_target_with_explicit_placeholder_positions',
        )
        self.assertEqual(
            report['topic_contract']['trajectory_command']['topic'],
            '/arm_controller/joint_trajectory',
        )
        self.assertEqual(report['topic_contract']['joint_state']['topic'], '/joint_states')
        self.assertEqual(report['topic_contract']['sensor_state']['topic'], '/rehab_arm/sensor_state')
        self.assertEqual(report['topic_contract']['model_state']['topic'], '/rehab_arm/model_state')
        self.assertEqual(report['topic_contract']['safety_state']['topic'], '/rehab_arm/safety_state')
        self.assertEqual(report['topic_contract']['vla_task_goal']['topic'], '/vla/task_goal')
        self.assertEqual(report['topic_contract']['control_boundary'], 'simulation_topic_contract_not_motion_permission')
        self.assertFalse(report['checks']['mujoco']['ok'])
        self.assertTrue(report['checks']['urdf']['ok'])
        self.assertTrue(report['checks']['medical_arm_6dof_mjcf']['ok'])
        self.assertTrue(report['checks']['medical_arm_6dof_schema']['ok'])
        self.assertTrue(report['checks']['medical_arm_6dof_shadow_launch']['ok'])
        self.assertTrue(report['checks']['medical_arm_6dof_hardware_shadow_launch']['ok'])
        self.assertIn('does not open CAN', report['safety_note'])
        self.assertEqual(report['missing_actions'][0]['id'], 'mujoco')
        self.assertEqual(report['missing_actions'][0]['severity'], 'optional')
        self.assertIn('sim_data_collection.launch.py', ' '.join(report['next_commands']))

    def test_strict_mujoco_requires_mujoco_import(self) -> None:
        available = {
            'rclpy',
            'rehab_arm_psoc_bridge.data_recording',
            'rehab_arm_psoc_bridge.build_manifest',
            'rehab_arm_psoc_bridge.sync_upload',
        }

        report = build_sim_env_report(
            WORKSPACE_ROOT,
            import_checker=lambda module_name: module_name in available,
            strict_mujoco=True,
        )

        self.assertFalse(report['ok'])
        self.assertEqual(report['readiness'], 'not_ready')
        self.assertIn('mujoco is required but not available', report['errors'])
        self.assertEqual(report['missing_actions'][0]['id'], 'mujoco')
        self.assertEqual(report['missing_actions'][0]['severity'], 'required')

    def test_report_lists_missing_data_tool_actions(self) -> None:
        available = {'rclpy', 'mujoco'}

        report = build_sim_env_report(
            WORKSPACE_ROOT,
            import_checker=lambda module_name: module_name in available,
        )

        self.assertFalse(report['ok'])
        data_tool_action = next(
            action for action in report['missing_actions']
            if action['id'] == 'data_tools'
        )
        self.assertEqual(data_tool_action['severity'], 'required')
        self.assertIn('rehab_arm_psoc_bridge.data_recording', data_tool_action['missing_modules'])
        self.assertIn('rehab_arm_psoc_bridge', ' '.join(data_tool_action['commands']))

    def test_cli_outputs_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PACKAGE_DIR / 'rehab_arm_sim_mujoco' / 'check_sim_env.py'),
                '--workspace-root',
                str(WORKSPACE_ROOT),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_sim_env_check_v1')
        self.assertIn('checks', payload)

    def test_cli_can_write_report_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'sim_readiness_report.json'

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_sim_mujoco' / 'check_sim_env.py'),
                    '--workspace-root',
                    str(WORKSPACE_ROOT),
                    '--output',
                    str(output_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertTrue(output_path.exists())
            stdout_payload = json.loads(result.stdout)
            file_payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(file_payload['schema_version'], 'rehab_arm_sim_env_check_v1')
            self.assertEqual(file_payload['readiness'], stdout_payload['readiness'])


if __name__ == '__main__':
    unittest.main()
