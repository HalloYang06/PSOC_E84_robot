from __future__ import annotations

import json
from pathlib import Path


PROFILE_SCHEMA_VERSION = 'patient_device_profile_v1'
VALID_PROFILE_STATUSES = {'draft', 'pending_review', 'approved', 'active', 'archived', 'rejected'}
VALID_TRAINING_MODES = {'passive_training', 'active_assist', 'resistance_training', 'memory_mode'}
SAFE_VLA_PERMISSION_LEVELS = {'disabled', 'suggest_only', 'plan_only'}
FORBIDDEN_MODEL_OUTPUTS = {'can_frame', 'torque_command', 'current_command', 'velocity_command', 'raw_motor_position'}
DEVICE_LIMIT_FLOOR_DEG = -60.0
DEVICE_LIMIT_CEILING_DEG = 60.0
MAX_PATIENT_VELOCITY_DPS = 30.0


def load_patient_profile(path: str | Path) -> dict[str, object]:
    with Path(path).expanduser().open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('patient profile must be a JSON object')
    return payload


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_string(profile: dict[str, object], field: str, errors: list[str]) -> None:
    value = profile.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f'missing or empty {field}')


def _get_nested_dict(payload: dict[str, object], key: str, errors: list[str]) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f'missing or invalid {key}')
        return {}
    return value


def _validate_limit_pair(
    pair: object,
    field_name: str,
    errors: list[str],
    floor: float = DEVICE_LIMIT_FLOOR_DEG,
    ceiling: float = DEVICE_LIMIT_CEILING_DEG,
) -> tuple[float, float] | None:
    if not isinstance(pair, list) or len(pair) != 2:
        errors.append(f'{field_name} must be [min_deg, max_deg]')
        return None
    min_deg, max_deg = pair
    if not _is_number(min_deg) or not _is_number(max_deg):
        errors.append(f'{field_name} must contain numeric limits')
        return None
    min_value = float(min_deg)
    max_value = float(max_deg)
    if min_value >= max_value:
        errors.append(f'{field_name} min must be less than max')
    if min_value < floor or max_value > ceiling:
        errors.append(f'{field_name} [{min_value}, {max_value}] exceeds device envelope [{floor}, {ceiling}]')
    return min_value, max_value


def _resolve_numeric_limit(limits: dict[str, object], joint_name: str) -> object:
    if joint_name in limits:
        return limits[joint_name]
    return limits.get('default')


def _resolve_pair(limits: dict[str, object], joint_name: str) -> tuple[float, float]:
    pair = limits[joint_name]
    return float(pair[0]), float(pair[1])


def _resolve_number_or_default(limits: dict[str, object], joint_name: str, fallback: float | None = None) -> float | None:
    value = _resolve_numeric_limit(limits, joint_name)
    if _is_number(value):
        return float(value)
    return fallback


def validate_patient_profile(profile: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if profile.get('schema_version') != PROFILE_SCHEMA_VERSION:
        errors.append(f'schema_version must be {PROFILE_SCHEMA_VERSION}')
    for field in ('profile_id', 'robot_id', 'device_id'):
        _require_string(profile, field, errors)
    if not isinstance(profile.get('profile_version'), int) or int(profile.get('profile_version', 0)) <= 0:
        errors.append('profile_version must be a positive integer')
    status = profile.get('profile_status')
    if status not in VALID_PROFILE_STATUSES:
        errors.append('profile_status must be one of: ' + ', '.join(sorted(VALID_PROFILE_STATUSES)))

    patient_ref = _get_nested_dict(profile, 'patient_ref', errors)
    if patient_ref and not isinstance(patient_ref.get('patient_id'), str):
        errors.append('patient_ref.patient_id is required')

    device_safety = _get_nested_dict(profile, 'device_safety', errors)
    patient_motion = _get_nested_dict(profile, 'patient_motion', errors)
    model_runtime = _get_nested_dict(profile, 'model_runtime', errors)

    absolute_joint_limits = _get_nested_dict(device_safety, 'absolute_joint_limits_deg', errors) if device_safety else {}
    absolute_velocity_limits = _get_nested_dict(device_safety, 'absolute_velocity_limits_dps', errors) if device_safety else {}
    patient_rom_limits = _get_nested_dict(patient_motion, 'patient_rom_limits_deg', errors) if patient_motion else {}
    patient_velocity_limits = _get_nested_dict(patient_motion, 'patient_velocity_limits_dps', errors) if patient_motion else {}

    joint_names = sorted(set(absolute_joint_limits) | set(patient_rom_limits))
    if not joint_names:
        errors.append('at least one joint limit is required')

    for joint_name in joint_names:
        absolute_pair = _validate_limit_pair(
            absolute_joint_limits.get(joint_name),
            f'device_safety.absolute_joint_limits_deg.{joint_name}',
            errors,
        )
        patient_pair = _validate_limit_pair(
            patient_rom_limits.get(joint_name),
            f'patient_motion.patient_rom_limits_deg.{joint_name}',
            errors,
        )
        if absolute_pair and patient_pair:
            if patient_pair[0] < absolute_pair[0] or patient_pair[1] > absolute_pair[1]:
                errors.append(f'patient_motion.patient_rom_limits_deg.{joint_name} exceeds absolute joint limits')

        velocity = _resolve_numeric_limit(patient_velocity_limits, joint_name)
        if not _is_number(velocity):
            errors.append(f'patient_motion.patient_velocity_limits_dps.{joint_name} or default is required')
        elif float(velocity) <= 0.0 or float(velocity) > MAX_PATIENT_VELOCITY_DPS:
            errors.append(
                f'patient_motion.patient_velocity_limits_dps.{joint_name} must be >0 and <= {MAX_PATIENT_VELOCITY_DPS}'
            )

        absolute_velocity = _resolve_numeric_limit(absolute_velocity_limits, joint_name)
        if _is_number(velocity) and _is_number(absolute_velocity) and float(velocity) > float(absolute_velocity):
            errors.append(f'patient_motion.patient_velocity_limits_dps.{joint_name} exceeds absolute velocity limit')

    training_mode = patient_motion.get('training_mode') if patient_motion else None
    if training_mode not in VALID_TRAINING_MODES:
        errors.append('patient_motion.training_mode must be one of: ' + ', '.join(sorted(VALID_TRAINING_MODES)))

    emergency_policy = _get_nested_dict(device_safety, 'emergency_policy', errors) if device_safety else {}
    if emergency_policy:
        if emergency_policy.get('estop_action') != 'disable_motor_output':
            errors.append('device_safety.emergency_policy.estop_action must be disable_motor_output')
        timeout = emergency_policy.get('heartbeat_timeout_ms')
        if not _is_number(timeout) or float(timeout) <= 0.0:
            errors.append('device_safety.emergency_policy.heartbeat_timeout_ms must be positive')
        if emergency_policy.get('fault_latch') is not True:
            errors.append('device_safety.emergency_policy.fault_latch must be true')

    server_models = model_runtime.get('server_models') if isinstance(model_runtime, dict) else {}
    vla_policy = server_models.get('vla_policy') if isinstance(server_models, dict) else None
    if not isinstance(vla_policy, dict):
        errors.append('model_runtime.server_models.vla_policy is required')
    else:
        permission = vla_policy.get('permission_level')
        if permission not in SAFE_VLA_PERMISSION_LEVELS:
            errors.append('model_runtime.server_models.vla_policy.permission_level must be disabled, suggest_only, or plan_only')
        forbidden_outputs = vla_policy.get('forbidden_outputs', [])
        if not isinstance(forbidden_outputs, list):
            errors.append('model_runtime.server_models.vla_policy.forbidden_outputs must be a list')
        else:
            missing = sorted(FORBIDDEN_MODEL_OUTPUTS - {str(item) for item in forbidden_outputs})
            if missing:
                errors.append('model_runtime.server_models.vla_policy.forbidden_outputs missing: ' + ', '.join(missing))

    m55_models = model_runtime.get('m55_models') if isinstance(model_runtime, dict) else {}
    if not isinstance(m55_models, dict) or not m55_models:
        warnings.append('model_runtime.m55_models is empty; M55 model path is not configured yet')
    elif 'direct_motor_control' in m55_models:
        errors.append('model_runtime.m55_models must not include direct_motor_control')

    return {
        'schema_version': 'patient_device_profile_validation_v1',
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'profile_id': profile.get('profile_id'),
        'profile_version': profile.get('profile_version'),
        'joint_count': len(joint_names),
        'control_boundary': 'profile_validation_only_not_motion_permission',
    }


def build_m33_safety_subset(profile: dict[str, object]) -> dict[str, object]:
    validation = validate_patient_profile(profile)
    if validation['ok'] is not True:
        return {
            'schema_version': 'm33_safety_profile_v1',
            'ok': False,
            'errors': list(validation['errors']),
            'profile_id': profile.get('profile_id'),
            'profile_version': profile.get('profile_version'),
            'control_boundary': 'm33_safety_subset_dry_run_only_not_sent',
        }

    device_safety = profile['device_safety']
    patient_motion = profile['patient_motion']
    absolute_joint_limits = device_safety['absolute_joint_limits_deg']
    patient_rom_limits = patient_motion['patient_rom_limits_deg']
    absolute_velocity_limits = device_safety['absolute_velocity_limits_dps']
    patient_velocity_limits = patient_motion['patient_velocity_limits_dps']
    absolute_acceleration_limits = device_safety.get('absolute_acceleration_limits_dps2', {})
    patient_acceleration_limits = patient_motion.get('patient_acceleration_limits_dps2', {})
    absolute_current_limits = device_safety.get('absolute_torque_current_limits', {})
    patient_current_limits = patient_motion.get('patient_torque_current_limits', {})

    joint_limits_deg: dict[str, list[float]] = {}
    velocity_limits_dps: dict[str, float] = {}
    acceleration_limits_dps2: dict[str, float] = {}
    torque_current_limits: dict[str, dict[str, float]] = {}
    joint_names = sorted(set(absolute_joint_limits) | set(patient_rom_limits))

    for joint_name in joint_names:
        absolute_min, absolute_max = _resolve_pair(absolute_joint_limits, joint_name)
        patient_min, patient_max = _resolve_pair(patient_rom_limits, joint_name)
        joint_limits_deg[joint_name] = [
            max(absolute_min, patient_min),
            min(absolute_max, patient_max),
        ]

        absolute_velocity = _resolve_number_or_default(absolute_velocity_limits, joint_name)
        patient_velocity = _resolve_number_or_default(patient_velocity_limits, joint_name)
        if absolute_velocity is not None and patient_velocity is not None:
            velocity_limits_dps[joint_name] = min(absolute_velocity, patient_velocity)

        absolute_accel = _resolve_number_or_default(absolute_acceleration_limits, joint_name)
        patient_accel = _resolve_number_or_default(patient_acceleration_limits, joint_name)
        if absolute_accel is not None and patient_accel is not None:
            acceleration_limits_dps2[joint_name] = min(absolute_accel, patient_accel)

        absolute_current = _resolve_number_or_default(absolute_current_limits, joint_name)
        if absolute_current is None:
            absolute_current = _resolve_number_or_default(absolute_current_limits, 'default_current_a')
        patient_current = _resolve_number_or_default(patient_current_limits, joint_name, absolute_current)
        if absolute_current is not None and patient_current is not None:
            torque_current_limits[joint_name] = {'current_a': min(absolute_current, patient_current)}

    training_mode = str(patient_motion.get('training_mode'))
    mode_permission = {
        'passive_training': training_mode == 'passive_training',
        'active_assist': training_mode == 'active_assist',
        'resistance_training': training_mode == 'resistance_training',
        'memory_mode': training_mode == 'memory_mode',
        'vla_task_execution': False,
    }

    return {
        'schema_version': 'm33_safety_profile_v1',
        'ok': True,
        'profile_id': profile.get('profile_id'),
        'profile_version': profile.get('profile_version'),
        'machine_calibration_id': device_safety.get('machine_calibration_id'),
        'requires_homing': bool(device_safety.get('requires_homing', True)),
        'homing_state_required': 'homed',
        'joint_limits_deg': joint_limits_deg,
        'velocity_limits_dps': velocity_limits_dps,
        'acceleration_limits_dps2': acceleration_limits_dps2,
        'torque_current_limits': torque_current_limits,
        'mode_permission': mode_permission,
        'emergency_policy': dict(device_safety.get('emergency_policy', {})),
        'source_profile_schema_version': profile.get('schema_version'),
        'control_boundary': 'm33_safety_subset_dry_run_only_not_sent',
    }
