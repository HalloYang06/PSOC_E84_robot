from __future__ import annotations

import time
from hashlib import sha256


SERVER_ACTION_COMMAND_SCHEMA_VERSION = 'server_to_nanopi_high_level_command_v1'
SERVER_ACTION_GATE_REPORT_SCHEMA_VERSION = 'server_action_ingress_gate_report_v1'
NANOPI_ACTION_QUEUE_ITEM_SCHEMA_VERSION = 'nanopi_high_level_action_queue_item_v1'

ALLOWED_ACTION_KINDS = {
    'rehab_training_request',
    'pause_training_request',
    'stop_training_request',
    'adjust_assistance_request',
    'operator_review_request',
}
REQUIRED_BEFORE_MOTION = {
    'active_profile_loaded',
    'wiring_state_checked',
    'safety_state_fresh',
    'mujoco_dry_run_required',
    'operator_confirmation_required',
    'm33_final_gate_required',
}
FORBIDDEN_LOW_LEVEL_KEYS = {
    'can_frame',
    'can_frames',
    'motor_current',
    'motor_torque',
    'motor_velocity',
    'raw_motor_position',
    'raw_motor_velocity',
    'm33_safety_override',
    'motion_allowed_override',
    'motion_permission_granted',
    'direct_motor_command',
    'joint_trajectory',
    'trajectory_points',
}


def _stable_command_id(device_id: str, label: str, now: float | None = None) -> str:
    timestamp = time.time() if now is None else now
    ts_text = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(timestamp))
    raw = f'{device_id}:{label}:{ts_text}'
    suffix = sha256(raw.encode('utf-8')).hexdigest()[:10]
    return f'srv_action__{device_id}__{ts_text}__{suffix}'


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


def build_example_server_action_command(
    robot_id: str = 'rehab-arm-alpha',
    device_id: str = 'nanopi-m5',
    action_label: str = 'assist_slow_arm_raise',
    language_context_id: str = 'lang_ctx_example',
    vision_context_id: str = 'vision_ctx_example',
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    return {
        'schema_version': SERVER_ACTION_COMMAND_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'command_id': _stable_command_id(device_id, action_label, timestamp),
        'source': 'server_vla_action',
        'source_refs': {
            'vla_language_context_id': language_context_id,
            'vla_vision_context_id': vision_context_id,
            'robot_context_snapshot_id': 'command_center_snapshot_latest',
        },
        'action': {
            'kind': 'rehab_training_request',
            'label': action_label,
            'natural_language': '患者请求开始缓慢抬手训练，先进入仿真和安全检查。',
            'priority': 'normal',
        },
        'requires_before_motion': sorted(REQUIRED_BEFORE_MOTION),
        'allowed_next_steps': [
            'vla_candidate_gate',
            'mujoco_dry_run_review',
            'operator_review',
            'm33_safety_gate_preparation',
        ],
        'forbidden_next_steps': [
            'publish_joint_trajectory',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'forbidden_outputs': sorted(FORBIDDEN_LOW_LEVEL_KEYS),
        'control_boundary': 'server_action_high_level_only_not_motion_permission',
    }


def validate_server_action_command(payload: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get('schema_version') != SERVER_ACTION_COMMAND_SCHEMA_VERSION:
        errors.append('schema_version must be server_to_nanopi_high_level_command_v1')
    if payload.get('control_boundary') != 'server_action_high_level_only_not_motion_permission':
        errors.append('control_boundary must be server_action_high_level_only_not_motion_permission')
    if not payload.get('robot_id'):
        errors.append('robot_id is required')
    if not payload.get('device_id'):
        errors.append('device_id is required')
    if not payload.get('command_id'):
        errors.append('command_id is required')

    action = payload.get('action')
    if not isinstance(action, dict):
        errors.append('action must be an object')
        action = {}
    action_kind = action.get('kind')
    if action_kind not in ALLOWED_ACTION_KINDS:
        errors.append('action.kind is not an allowed high-level request kind')
    if not action.get('label'):
        errors.append('action.label is required')

    source_refs = payload.get('source_refs')
    if not isinstance(source_refs, dict):
        errors.append('source_refs must be an object')
        source_refs = {}
    if not source_refs.get('vla_language_context_id'):
        errors.append('source_refs.vla_language_context_id is required')
    if not source_refs.get('vla_vision_context_id'):
        warnings.append('source_refs.vla_vision_context_id is missing; A should normally fuse V before NanoPi ingress')

    requires = payload.get('requires_before_motion')
    if not isinstance(requires, list):
        errors.append('requires_before_motion must be a list')
        requires = []
    missing = sorted(REQUIRED_BEFORE_MOTION - set(str(item) for item in requires))
    for item in missing:
        errors.append(f'requires_before_motion must include {item}')

    forbidden_paths: list[str] = []
    for path, key, value in _walk_payload(payload):
        if key in FORBIDDEN_LOW_LEVEL_KEYS and value not in (False, None):
            forbidden_paths.append(path)
    if forbidden_paths:
        errors.append(
            'server action contains forbidden low-level control fields: '
            + ', '.join(forbidden_paths)
        )

    allowed_next_steps = payload.get('allowed_next_steps')
    if not isinstance(allowed_next_steps, list):
        errors.append('allowed_next_steps must be a list')
        allowed_next_steps = []
    for unsafe_step in ('publish_joint_trajectory', 'send_can_frame', 'set_motor_current', 'set_motor_torque'):
        if unsafe_step in allowed_next_steps:
            errors.append(f'allowed_next_steps must not include {unsafe_step}')

    return {
        'schema_version': SERVER_ACTION_GATE_REPORT_SCHEMA_VERSION,
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'allowed_next_steps': [
            'vla_candidate_gate',
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
        'control_boundary': 'server_action_ingress_gate_only_not_motion_permission',
    }


def make_nanopi_action_queue_item(
    payload: dict[str, object],
    gate_report: dict[str, object] | None = None,
    now: float | None = None,
) -> dict[str, object]:
    report = gate_report if gate_report is not None else validate_server_action_command(payload)
    timestamp = time.time() if now is None else now
    accepted = bool(report.get('ok'))
    action = payload.get('action') if isinstance(payload.get('action'), dict) else {}
    command_id = str(payload.get('command_id') or _stable_command_id(str(payload.get('device_id') or 'device'), 'unknown', timestamp))
    return {
        'schema_version': NANOPI_ACTION_QUEUE_ITEM_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': payload.get('robot_id'),
        'device_id': payload.get('device_id'),
        'queue_item_id': f'nanopi_queue__{command_id}',
        'source_command_id': command_id,
        'accepted': accepted,
        'reject_reasons': report.get('errors', []),
        'action': {
            'kind': action.get('kind'),
            'label': action.get('label'),
            'natural_language': action.get('natural_language'),
            'priority': action.get('priority', 'normal'),
        },
        'source_refs': payload.get('source_refs', {}),
        'next_pipeline': [
            'vla_candidate_gate',
            'mujoco_dry_run_review',
            'operator_review',
            'm33_safety_gate_preparation',
        ] if accepted else [],
        'blocked_pipeline': [
            'publish_joint_trajectory',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'gate_report': report,
        'control_boundary': 'nanopi_action_queue_only_not_motion_permission',
    }
