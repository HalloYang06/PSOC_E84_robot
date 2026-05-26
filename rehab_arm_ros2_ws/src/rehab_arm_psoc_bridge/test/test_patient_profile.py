from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.patient_profile import validate_patient_profile  # noqa: E402


def make_valid_profile() -> dict[str, object]:
    return {
        'schema_version': 'patient_device_profile_v1',
        'profile_id': 'pdp_test_001',
        'profile_version': 1,
        'profile_status': 'active',
        'robot_id': 'rehab_arm_alpha',
        'device_id': 'nanopi_m5_001',
        'patient_ref': {'patient_id': 'patient_001'},
        'device_safety': {
            'absolute_joint_limits_deg': {
                'shoulder_lift_joint': [-60.0, 60.0],
                'elbow_lift_joint': [-60.0, 60.0],
            },
            'absolute_velocity_limits_dps': {'default': 10.0},
            'emergency_policy': {
                'estop_action': 'disable_motor_output',
                'heartbeat_timeout_ms': 2500,
                'fault_latch': True,
            },
        },
        'patient_motion': {
            'patient_rom_limits_deg': {
                'shoulder_lift_joint': [-10.0, 35.0],
                'elbow_lift_joint': [0.0, 50.0],
            },
            'patient_velocity_limits_dps': {'default': 6.0},
            'training_mode': 'active_assist',
        },
        'model_runtime': {
            'm55_models': {
                'intent_model': {
                    'model_id': 'm55_intent_v1',
                    'version': '0.1.0',
                },
            },
            'server_models': {
                'vla_policy': {
                    'permission_level': 'suggest_only',
                    'forbidden_outputs': [
                        'can_frame',
                        'torque_command',
                        'current_command',
                        'velocity_command',
                        'raw_motor_position',
                    ],
                },
            },
        },
    }


class PatientProfileTests(unittest.TestCase):
    def test_valid_profile_passes(self) -> None:
        report = validate_patient_profile(make_valid_profile())

        self.assertIs(report['ok'], True)
        self.assertEqual(report['error_count'], 0)
        self.assertEqual(report['joint_count'], 2)
        self.assertEqual(report['control_boundary'], 'profile_validation_only_not_motion_permission')

    def test_rejects_unsafe_rom_velocity_vla_and_emergency_policy(self) -> None:
        profile = make_valid_profile()
        profile['patient_motion']['patient_rom_limits_deg']['shoulder_lift_joint'] = [-80.0, 80.0]
        profile['patient_motion']['patient_velocity_limits_dps']['default'] = 99.0
        profile['device_safety']['emergency_policy']['estop_action'] = 'hold_position'
        profile['device_safety']['emergency_policy']['fault_latch'] = False
        profile['model_runtime']['server_models']['vla_policy']['permission_level'] = 'direct_control'
        profile['model_runtime']['server_models']['vla_policy']['forbidden_outputs'] = ['can_frame']
        profile['model_runtime']['m55_models']['direct_motor_control'] = {'model_id': 'bad'}

        report = validate_patient_profile(profile)

        self.assertIs(report['ok'], False)
        joined = '\n'.join(report['errors'])
        self.assertIn('patient_motion.patient_rom_limits_deg.shoulder_lift_joint [-80.0, 80.0] exceeds device envelope', joined)
        self.assertIn('patient_motion.patient_rom_limits_deg.shoulder_lift_joint exceeds absolute joint limits', joined)
        self.assertIn('patient_motion.patient_velocity_limits_dps.shoulder_lift_joint must be >0', joined)
        self.assertIn('device_safety.emergency_policy.estop_action must be disable_motor_output', joined)
        self.assertIn('device_safety.emergency_policy.fault_latch must be true', joined)
        self.assertIn('permission_level must be disabled, suggest_only, or plan_only', joined)
        self.assertIn('forbidden_outputs missing', joined)
        self.assertIn('direct_motor_control', joined)

    def test_validate_patient_profile_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'patient_device_profile.json'
            path.write_text(json.dumps(make_valid_profile()), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'validate_patient_profile.py'),
                    str(path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIs(payload['ok'], True)


if __name__ == '__main__':
    unittest.main()
