from __future__ import annotations

import time


VLA_CANDIDATE_SCHEMA_VERSION = 'vla_plan_candidate_v1'
VLA_CANDIDATE_GATE_REPORT_SCHEMA_VERSION = 'vla_candidate_gate_report_v1'
ALLOWED_CANDIDATE_TYPES = {'dry_run_joint_trajectory'}
REQUIRED_REVIEW_STEPS = {
    'mujoco_dry_run_passed',
    'm33_motion_allowed_true',
    'human_confirmation',
}
FORBIDDEN_LOW_LEVEL_KEYS = {
    'can_frame',
    'can_frames',
    'motor_current',
    'motor_torque',
    'raw_motor_position',
    'raw_motor_velocity',
    'm33_safety_override',
    'motion_allowed_override',
    'direct_motor_command',
}
MEDICAL_ARM_6DOF_JOINTS = {
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint',
}


def _path_join(parent: str, child: object) -> str:
    if parent:
        return f'{parent}.{child}'
    return str(child)


def _walk_payload(value: object, path: str = ''):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = _path_join(path, key)
            yield child_path, key, child
            yield from _walk_payload(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = _path_join(path, index)
            yield child_path, index, child
            yield from _walk_payload(child, child_path)


def build_example_vla_plan_candidate(
    plan_id: str = 'vla_plan_dry_run_001',
    joint_name: str = 'zhou_zongxiang_joint',
    position_rad: float = 0.1,
    now: float | None = None,
) -> dict[str, object]:
    return {
        'schema_version': VLA_CANDIDATE_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'plan_id': plan_id,
        'summary': '建议先做小幅度 MuJoCo dry-run 候选。',
        'candidate': {
            'type': 'dry_run_joint_trajectory',
            'joint_names': [joint_name],
            'points': [
                {
                    'positions': [float(position_rad)],
                    'time_from_start_sec': 2.0,
                }
            ],
        },
        'requires': [
            'mujoco_dry_run_passed',
            'm33_motion_allowed_true',
            'human_confirmation',
        ],
        'control_boundary': 'vla_candidate_only_not_motion_permission',
    }


def validate_vla_plan_candidate(payload: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get('schema_version') != VLA_CANDIDATE_SCHEMA_VERSION:
        errors.append('schema_version must be vla_plan_candidate_v1')
    if payload.get('control_boundary') != 'vla_candidate_only_not_motion_permission':
        errors.append('control_boundary must be vla_candidate_only_not_motion_permission')

    candidate = payload.get('candidate')
    if not isinstance(candidate, dict):
        errors.append('candidate must be an object')
        candidate = {}
    candidate_type = candidate.get('type')
    if candidate_type not in ALLOWED_CANDIDATE_TYPES:
        errors.append('candidate.type must be dry_run_joint_trajectory')

    joint_names = candidate.get('joint_names')
    if not isinstance(joint_names, list) or not joint_names:
        errors.append('candidate.joint_names must be a non-empty list')
        joint_names = []
    else:
        for joint_name in joint_names:
            if joint_name not in MEDICAL_ARM_6DOF_JOINTS:
                errors.append(f'candidate.joint_names contains unknown joint {joint_name!r}')

    points = candidate.get('points')
    if not isinstance(points, list) or not points:
        errors.append('candidate.points must be a non-empty list')
        points = []
    previous_time = -1.0
    for index, point in enumerate(points):
        prefix = f'candidate.points[{index}]'
        if not isinstance(point, dict):
            errors.append(f'{prefix} must be an object')
            continue
        positions = point.get('positions')
        if not isinstance(positions, list):
            errors.append(f'{prefix}.positions must be a list')
        elif len(positions) != len(joint_names):
            errors.append(f'{prefix}.positions length must match candidate.joint_names length')
        else:
            for pos_index, position in enumerate(positions):
                if not isinstance(position, (int, float)):
                    errors.append(f'{prefix}.positions[{pos_index}] must be numeric')
                elif abs(float(position)) > 3.2:
                    errors.append(f'{prefix}.positions[{pos_index}] exceeds conservative dry-run bound 3.2 rad')
        time_from_start = point.get('time_from_start_sec')
        if not isinstance(time_from_start, (int, float)):
            errors.append(f'{prefix}.time_from_start_sec must be numeric')
        elif float(time_from_start) <= previous_time:
            errors.append(f'{prefix}.time_from_start_sec must be strictly increasing')
        else:
            previous_time = float(time_from_start)

    requires = payload.get('requires')
    if not isinstance(requires, list):
        errors.append('requires must be a list')
        requires = []
    missing_steps = sorted(REQUIRED_REVIEW_STEPS - set(str(item) for item in requires))
    for step in missing_steps:
        errors.append(f'requires must include {step}')

    forbidden_paths = []
    for path, key, value in _walk_payload(payload):
        if key in FORBIDDEN_LOW_LEVEL_KEYS and value not in (False, None):
            forbidden_paths.append(path)
    if forbidden_paths:
        errors.append(
            'candidate payload contains forbidden low-level control fields: '
            + ', '.join(forbidden_paths)
        )

    if 'm33_motion_allowed_true' in requires:
        warnings.append(
            'm33_motion_allowed_true is a required future condition, not proof that motion is currently allowed'
        )

    return {
        'schema_version': VLA_CANDIDATE_GATE_REPORT_SCHEMA_VERSION,
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'allowed_next_steps': [
            'mujoco_dry_run_review',
            'operator_review',
        ] if not errors else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'vla_candidate_gate_only_not_motion_permission',
    }
