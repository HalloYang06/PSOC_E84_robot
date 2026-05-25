from __future__ import annotations

import json
import subprocess
import sys
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
        self.assertFalse(report['checks']['mujoco']['ok'])
        self.assertTrue(report['checks']['urdf']['ok'])
        self.assertIn('does not open CAN', report['safety_note'])

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


if __name__ == '__main__':
    unittest.main()
