from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.patient_profile import (  # noqa: E402
    build_ble_m33_safety_package,
    build_m33_safety_subset,
    build_patient_profile_change_report,
    validate_patient_profile,
)


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
            'machine_calibration_id': 'machine_calib_alpha_001',
            'requires_homing': True,
            'absolute_joint_limits_deg': {
                'shoulder_lift_joint': [-60.0, 60.0],
                'elbow_lift_joint': [-60.0, 60.0],
            },
            'absolute_velocity_limits_dps': {'default': 10.0},
            'absolute_acceleration_limits_dps2': {'default': 40.0},
            'absolute_torque_current_limits': {'default_current_a': 5.0},
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
            'patient_acceleration_limits_dps2': {'default': 20.0},
            'patient_torque_current_limits': {'default': 3.0},
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

    def test_build_m33_safety_subset_takes_stricter_limits(self) -> None:
        profile = make_valid_profile()

        subset = build_m33_safety_subset(profile)

        self.assertIs(subset['ok'], True)
        self.assertEqual(subset['schema_version'], 'm33_safety_profile_v1')
        self.assertEqual(subset['profile_id'], 'pdp_test_001')
        self.assertEqual(subset['machine_calibration_id'], 'machine_calib_alpha_001')
        self.assertEqual(subset['joint_limits_deg']['shoulder_lift_joint'], [-10.0, 35.0])
        self.assertEqual(subset['velocity_limits_dps']['shoulder_lift_joint'], 6.0)
        self.assertEqual(subset['acceleration_limits_dps2']['shoulder_lift_joint'], 20.0)
        self.assertEqual(subset['torque_current_limits']['shoulder_lift_joint']['current_a'], 3.0)
        self.assertIs(subset['mode_permission']['active_assist'], True)
        self.assertIs(subset['mode_permission']['vla_task_execution'], False)
        self.assertEqual(subset['control_boundary'], 'm33_safety_subset_dry_run_only_not_sent')

    def test_build_m33_safety_subset_rejects_invalid_profile(self) -> None:
        profile = make_valid_profile()
        profile['patient_motion']['patient_rom_limits_deg']['shoulder_lift_joint'] = [-90.0, 90.0]

        subset = build_m33_safety_subset(profile)

        self.assertIs(subset['ok'], False)
        self.assertIn('errors', subset)
        self.assertEqual(subset['control_boundary'], 'm33_safety_subset_dry_run_only_not_sent')

    def test_export_m33_safety_subset_cli_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'patient_device_profile.json'
            output = Path(tmpdir) / 'm33_safety_profile.json'
            path.write_text(json.dumps(make_valid_profile()), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'export_m33_safety_subset.py'),
                    str(path),
                    '--output',
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            payload = json.loads(output.read_text(encoding='utf-8'))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload['schema_version'], 'm33_safety_profile_v1')
        self.assertIs(payload['ok'], True)

    def test_build_patient_profile_change_report_flags_wider_limits(self) -> None:
        old_profile = make_valid_profile()
        new_profile = make_valid_profile()
        new_profile['profile_version'] = 2
        new_profile['patient_motion']['patient_rom_limits_deg']['shoulder_lift_joint'] = [-20.0, 40.0]
        new_profile['patient_motion']['patient_velocity_limits_dps']['default'] = 8.0
        new_profile['patient_motion']['training_mode'] = 'passive_training'

        report = build_patient_profile_change_report(old_profile, new_profile)

        self.assertIs(report['ok'], True)
        self.assertEqual(report['warning_count'], 4)
        joined_warnings = '\n'.join(report['warnings'])
        self.assertIn('widens patient ROM', joined_warnings)
        self.assertIn('increases patient velocity limit', joined_warnings)
        self.assertIn('training_mode changed', joined_warnings)
        self.assertEqual(report['control_boundary'], 'profile_change_review_only_not_motion_permission')

    def test_build_patient_profile_change_report_rejects_wrong_version_or_patient(self) -> None:
        old_profile = make_valid_profile()
        new_profile = make_valid_profile()
        new_profile['profile_version'] = 1
        new_profile['patient_ref']['patient_id'] = 'patient_002'

        report = build_patient_profile_change_report(old_profile, new_profile)

        self.assertIs(report['ok'], False)
        joined_errors = '\n'.join(report['errors'])
        self.assertIn('new profile_version must be greater', joined_errors)
        self.assertIn('patient_ref.patient_id changed', joined_errors)

    def test_review_patient_profile_change_cli_reports_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = Path(tmpdir) / 'old_profile.json'
            new_path = Path(tmpdir) / 'new_profile.json'
            old_profile = make_valid_profile()
            new_profile = make_valid_profile()
            new_profile['profile_version'] = 2
            new_profile['patient_motion']['patient_rom_limits_deg']['elbow_lift_joint'] = [0.0, 55.0]
            old_path.write_text(json.dumps(old_profile), encoding='utf-8')
            new_path.write_text(json.dumps(new_profile), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'review_patient_profile_change.py'),
                    str(old_path),
                    str(new_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'patient_device_profile_change_report_v1')
        self.assertEqual(payload['warning_count'], 1)

    def test_build_ble_m33_safety_package_wraps_safety_subset(self) -> None:
        profile = make_valid_profile()

        package = build_ble_m33_safety_package(
            profile,
            package_id='pkg_001',
            approved_by='clinician_001',
            approved_at='2026-05-27T10:00:00+08:00',
            expires_at='2026-05-28T10:00:00+08:00',
        )

        self.assertIs(package['ok'], True)
        self.assertEqual(package['schema_version'], 'ble_m33_safety_package_v1')
        self.assertEqual(package['transport'], 'app_ble_to_m33')
        self.assertEqual(package['package_id'], 'pkg_001')
        self.assertEqual(package['approval']['status'], 'approved')
        self.assertEqual(package['m33_safety_subset']['schema_version'], 'm33_safety_profile_v1')
        self.assertEqual(package['control_boundary'], 'ble_package_dry_run_only_not_sent')

    def test_build_ble_m33_safety_package_rejects_draft_profile(self) -> None:
        profile = make_valid_profile()
        profile['profile_status'] = 'draft'

        package = build_ble_m33_safety_package(
            profile,
            approved_by='clinician_001',
            approved_at='2026-05-27T10:00:00+08:00',
            expires_at='2026-05-28T10:00:00+08:00',
        )

        self.assertIs(package['ok'], False)
        self.assertIsNone(package['m33_safety_subset'])
        self.assertIn('profile_status must be approved or active', '\n'.join(package['errors']))

    def test_build_ble_m33_safety_package_cli_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / 'patient_device_profile.json'
            output_path = Path(tmpdir) / 'ble_package.json'
            profile_path.write_text(json.dumps(make_valid_profile()), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'build_ble_m33_safety_package.py'),
                    str(profile_path),
                    '--approved-by',
                    'clinician_001',
                    '--approved-at',
                    '2026-05-27T10:00:00+08:00',
                    '--expires-at',
                    '2026-05-28T10:00:00+08:00',
                    '--output',
                    str(output_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding='utf-8'))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload['schema_version'], 'ble_m33_safety_package_v1')
        self.assertIs(payload['ok'], True)


if __name__ == '__main__':
    unittest.main()
