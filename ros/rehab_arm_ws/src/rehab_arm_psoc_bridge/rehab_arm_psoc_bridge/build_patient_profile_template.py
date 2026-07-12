#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.motor_profiles import MOTOR_PROFILES
    from rehab_arm_psoc_bridge.patient_profile import PROFILE_SCHEMA_VERSION, validate_patient_profile
except ModuleNotFoundError:
    from motor_profiles import MOTOR_PROFILES  # type: ignore[no-redef]
    from patient_profile import PROFILE_SCHEMA_VERSION, validate_patient_profile  # type: ignore[no-redef]


DEFAULT_ABSOLUTE_LIMIT_DEG = [-60.0, 60.0]
DEFAULT_PATIENT_ROM_DEG = [-10.0, 10.0]


def build_patient_profile_template(
    *,
    profile_id: str,
    robot_id: str,
    device_id: str,
    patient_id: str,
    profile_status: str = 'draft',
) -> dict[str, object]:
    joint_names = [
        str(profile['joint_name'])
        for _, profile in sorted(MOTOR_PROFILES.items(), key=lambda item: int(item[1]['joint_id']))
    ]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        'schema_version': PROFILE_SCHEMA_VERSION,
        'profile_id': profile_id,
        'profile_version': 1,
        'profile_status': profile_status,
        'robot_id': robot_id,
        'device_id': device_id,
        'patient_ref': {
            'patient_id': patient_id,
            'side': 'unknown',
            'affected_side': 'unknown',
            'privacy_level': 'pseudonymized',
        },
        'device_safety': {
            'machine_calibration_id': 'machine_calib_unset',
            'requires_homing': True,
            'absolute_joint_limits_deg': {
                joint_name: list(DEFAULT_ABSOLUTE_LIMIT_DEG) for joint_name in joint_names
            },
            'absolute_velocity_limits_dps': {'default': 10.0},
            'absolute_acceleration_limits_dps2': {'default': 40.0},
            'absolute_torque_current_limits': {'default_current_a': 3.0},
            'emergency_policy': {
                'estop_action': 'disable_motor_output',
                'heartbeat_timeout_ms': 2500,
                'fault_latch': True,
            },
        },
        'patient_motion': {
            'patient_rom_limits_deg': {
                joint_name: list(DEFAULT_PATIENT_ROM_DEG) for joint_name in joint_names
            },
            'patient_velocity_limits_dps': {'default': 5.0},
            'patient_acceleration_limits_dps2': {'default': 15.0},
            'patient_torque_current_limits': {'default': 2.0},
            'training_mode': 'passive_training',
            'assist_level': 0.0,
            'session_duration_limit_s': 600,
            'repetition_limit': 10,
            'pain_stop_threshold': 3,
            'fatigue_policy': {
                'fatigue_score_warn': 0.65,
                'fatigue_score_reduce_assist': 0.75,
                'fatigue_score_stop': 0.9,
                'on_warn': 'reduce_speed',
                'on_stop': 'pause_and_request_confirmation',
            },
        },
        'model_runtime': {
            'm55_models': {
                'intent_model': {
                    'model_id': 'm55_intent_unset',
                    'version': '0.0.0',
                    'input_topics': ['emg_features', 'imu_features', 'robot_joint_state'],
                    'output_topic': 'm55_model_result',
                    'frequency_hz': 50,
                    'confidence_threshold': 0.7,
                },
                'fatigue_model': {
                    'model_id': 'm55_fatigue_unset',
                    'version': '0.0.0',
                    'frequency_hz': 10,
                    'fatigue_score_range': [0.0, 1.0],
                },
            },
            'server_models': {
                'vla_policy': {
                    'permission_level': 'suggest_only',
                    'allowed_task_types': [
                        'describe_scene',
                        'suggest_training_task',
                        'plan_complex_task',
                    ],
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
        'training_and_labeling': {
            'task_plan_id': 'task_plan_unset',
            'task_labels': [],
            'labeling_protocol_id': 'label_protocol_unset',
            'required_labels': ['pain_score', 'fatigue_score', 'intent_label'],
            'data_capture': {
                'record_motor_state': True,
                'record_sensor_state': True,
                'record_camera_keyframes': True,
                'record_model_outputs': True,
            },
        },
        'sync': {
            'created_by': 'unset',
            'approved_by': '',
            'approved_at': '',
            'active_since': '',
            'revision_note': 'Generated conservative draft template; review before use.',
            'generated_at': now,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build a conservative Patient Device Profile template from the current motor profile table.',
    )
    parser.add_argument('--profile-id', default='pdp_draft_001')
    parser.add_argument('--robot-id', default='rehab_arm_alpha')
    parser.add_argument('--device-id', default='nanopi_m5_001')
    parser.add_argument('--patient-id', default='patient_unset')
    parser.add_argument('--profile-status', default='draft')
    parser.add_argument('--output', help='Optional path to write patient_device_profile.json')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--validate', action='store_true', help='Include a validation report in the output envelope.')
    args = parser.parse_args(argv)

    profile = build_patient_profile_template(
        profile_id=args.profile_id,
        robot_id=args.robot_id,
        device_id=args.device_id,
        patient_id=args.patient_id,
        profile_status=args.profile_status,
    )
    payload: dict[str, object]
    if args.validate:
        payload = {
            'schema_version': 'patient_device_profile_template_result_v1',
            'ok': True,
            'profile': profile,
            'validation': validate_patient_profile(profile),
            'control_boundary': 'template_generation_only_not_motion_permission',
        }
    else:
        payload = profile

    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (',', ':'),
    )
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + '\n', encoding='utf-8')
    print(text)
    validation = validate_patient_profile(profile)
    return 0 if validation['ok'] is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
