from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.motor_profiles import (  # noqa: E402
    EXECUTION_ALLOWED_MOTOR_IDS,
    MOTOR_PROFILES,
    motor_profile,
    motor_profiles_payload,
)


class MotorProfilesTests(unittest.TestCase):
    def test_profiles_capture_current_bench_motor_identity(self) -> None:
        self.assertEqual(sorted(MOTOR_PROFILES), [3, 4, 5, 6, 7])
        self.assertEqual(MOTOR_PROFILES[3]['vendor'], 'Sitaiwei')
        self.assertEqual(MOTOR_PROFILES[3]['protocol'], 'CANSimple')
        self.assertEqual(MOTOR_PROFILES[3]['gear_ratio'], 48.0)
        self.assertEqual(MOTOR_PROFILES[3]['joint_command_ratio'], 48.0)
        self.assertEqual(MOTOR_PROFILES[3]['drive_internal_reduction_ratio'], 48.0)
        self.assertEqual(MOTOR_PROFILES[3]['medical_arm_6dof_joint'], 'jian_hengxiang_joint')
        self.assertEqual(MOTOR_PROFILES[4]['model'], 'RS00')
        self.assertEqual(MOTOR_PROFILES[4]['joint_command_ratio'], 1.0)
        self.assertEqual(MOTOR_PROFILES[4]['drive_internal_reduction_ratio'], 10.0)
        self.assertEqual(MOTOR_PROFILES[4]['medical_arm_6dof_joint'], 'jian_zongxiang_joint')
        self.assertEqual(MOTOR_PROFILES[5]['model'], 'RS00')
        self.assertEqual(MOTOR_PROFILES[5]['joint_command_ratio'], 1.0)
        self.assertEqual(MOTOR_PROFILES[5]['drive_internal_reduction_ratio'], 10.0)
        self.assertEqual(MOTOR_PROFILES[5]['medical_arm_6dof_joint'], 'zhou_zongxiang_joint')
        self.assertEqual(MOTOR_PROFILES[6]['model'], 'EL05')
        self.assertEqual(MOTOR_PROFILES[6]['joint_command_ratio'], 1.0)
        self.assertEqual(MOTOR_PROFILES[6]['drive_internal_reduction_ratio'], 9.0)
        self.assertEqual(MOTOR_PROFILES[6]['medical_arm_6dof_joint'], 'jian_xuanzhuan_joint')
        self.assertEqual(MOTOR_PROFILES[7]['model'], 'EL05')
        self.assertEqual(MOTOR_PROFILES[7]['joint_command_ratio'], 1.0)
        self.assertEqual(MOTOR_PROFILES[7]['drive_internal_reduction_ratio'], 9.0)
        self.assertIsNone(MOTOR_PROFILES[7]['medical_arm_6dof_joint'])
        self.assertEqual(MOTOR_PROFILES[7]['mapping_scope'], 'temporary_mujoco_shadow_and_external_bench_only')
        self.assertEqual(EXECUTION_ALLOWED_MOTOR_IDS, {3, 7})

    def test_motor_profile_returns_copy(self) -> None:
        profile = motor_profile(7)
        profile['model'] = 'changed'
        self.assertEqual(MOTOR_PROFILES[7]['model'], 'EL05')

    def test_payload_is_platform_and_app_friendly_json(self) -> None:
        payload = motor_profiles_payload()
        self.assertEqual(payload['schema_version'], 'rehab_arm_motor_profiles_v1')
        self.assertEqual(sorted(payload['profiles']), ['3', '4', '5', '6', '7'])
        self.assertEqual(payload['execution_allowed_motor_ids'], [3, 7])

    def test_cli_pretty_prints_profiles(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'motor_profiles.py'),
                '--pretty',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_motor_profiles_v1')
        self.assertEqual(payload['profiles']['7']['joint_name'], 'forearm_rotation_joint')


if __name__ == '__main__':
    unittest.main()
