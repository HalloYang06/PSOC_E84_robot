from __future__ import annotations

import time


OPERATOR_REVIEW_RECORD_SCHEMA_VERSION = 'operator_review_record_v1'
OPERATOR_REVIEW_QUALITY_REPORT_SCHEMA_VERSION = 'operator_review_quality_report_v1'
ALLOWED_REVIEW_ROLES = {'operator', 'doctor', 'therapist', 'admin'}
REQUIRED_ACKS = {
    'patient_profile_confirmed',
    'mujoco_dry_run_reviewed',
    'm33_safety_gate_required',
    'fresh_motor_feedback_required',
    'estop_available',
}


def build_operator_review_record(
    robot_id: str,
    device_id: str,
    session_id: str,
    reviewer_id: str,
    reviewer_role: str,
    approved_for_m33_gate_preparation: bool,
    patient_id: str | None = None,
    profile_id: str | None = None,
    source_plan_id: str | None = None,
    mujoco_report_id: str | None = None,
    notes: str = '',
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    return {
        'schema_version': OPERATOR_REVIEW_RECORD_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'session_id': session_id,
        'patient_id': patient_id,
        'profile_id': profile_id,
        'source_plan_id': source_plan_id,
        'mujoco_report_id': mujoco_report_id,
        'reviewer': {
            'user_id': reviewer_id,
            'role': reviewer_role,
        },
        'approved_for_m33_gate_preparation': bool(approved_for_m33_gate_preparation),
        'required_acknowledgements': sorted(REQUIRED_ACKS),
        'notes': notes,
        'allowed_next_steps': [
            'prepare_joint_trajectory_for_m33_gate',
        ] if approved_for_m33_gate_preparation else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory_without_m33_gate',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'operator_review_only_not_motion_permission',
    }


def validate_operator_review_record(record: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if record.get('schema_version') != OPERATOR_REVIEW_RECORD_SCHEMA_VERSION:
        errors.append('schema_version must be operator_review_record_v1')
    if record.get('control_boundary') != 'operator_review_only_not_motion_permission':
        errors.append('control_boundary must be operator_review_only_not_motion_permission')

    for field in ('robot_id', 'device_id', 'session_id'):
        if not record.get(field):
            errors.append(f'{field} is required')

    reviewer = record.get('reviewer')
    if not isinstance(reviewer, dict):
        errors.append('reviewer must be an object')
        reviewer = {}
    if not reviewer.get('user_id'):
        errors.append('reviewer.user_id is required')
    if reviewer.get('role') not in ALLOWED_REVIEW_ROLES:
        errors.append(f"reviewer.role must be one of {sorted(ALLOWED_REVIEW_ROLES)}")

    if 'approved_for_m33_gate_preparation' not in record:
        errors.append('approved_for_m33_gate_preparation is required')
    elif not isinstance(record.get('approved_for_m33_gate_preparation'), bool):
        errors.append('approved_for_m33_gate_preparation must be boolean')

    acknowledgements = record.get('required_acknowledgements')
    if not isinstance(acknowledgements, list):
        errors.append('required_acknowledgements must be a list')
        acknowledgements = []
    missing_acks = sorted(REQUIRED_ACKS - set(str(item) for item in acknowledgements))
    for ack in missing_acks:
        errors.append(f'required_acknowledgements must include {ack}')

    forbidden_next_steps = record.get('forbidden_next_steps')
    if not isinstance(forbidden_next_steps, list):
        errors.append('forbidden_next_steps must be a list')
        forbidden_next_steps = []
    for step in (
        'publish_joint_trajectory_without_m33_gate',
        'send_can_frame',
        'set_motor_current',
        'set_motor_torque',
        'override_m33_safety',
    ):
        if step not in forbidden_next_steps:
            errors.append(f'forbidden_next_steps must include {step}')

    if record.get('approved_for_m33_gate_preparation') is True:
        warnings.append('operator approval only permits M33 gate preparation, not direct motion')

    return {
        'schema_version': OPERATOR_REVIEW_QUALITY_REPORT_SCHEMA_VERSION,
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'allowed_next_steps': [
            'prepare_joint_trajectory_for_m33_gate',
        ] if not errors and record.get('approved_for_m33_gate_preparation') is True else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory_without_m33_gate',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'operator_review_quality_gate_only_not_motion_permission',
    }
