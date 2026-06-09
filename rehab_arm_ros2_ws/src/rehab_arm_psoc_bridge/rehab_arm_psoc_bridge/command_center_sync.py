from __future__ import annotations

import time
from hashlib import sha256

from rehab_arm_psoc_bridge.rehab_session import build_rehab_session_plan
from rehab_arm_psoc_bridge.voice_gateway import build_voice_pipeline_plan


COMMAND_CENTER_SYNC_PLAN_SCHEMA_VERSION = 'command_center_sync_plan_v1'
COMMAND_CENTER_CONTEXT_SCHEMA_VERSION = 'command_center_auth_context_v1'
DEFAULT_BASE_URL = 'http://server.example/api/rehab-arm/v1'
DEFAULT_WS_PATH = '/devices/{device_id}/events'
REQUIRED_AUTH_CONTEXT_FIELDS = (
    'tenant_id',
    'workspace_id',
    'user_id',
    'role',
    'allowed_device_ids',
)
FORBIDDEN_MOTION_OUTPUTS = (
    'can_frame',
    'motor_current',
    'motor_torque',
    'raw_motor_position',
    'raw_motor_velocity',
    'm33_safety_override',
)


def _compact_base_url(base_url: str) -> str:
    return base_url.rstrip('/')


def stable_request_id(prefix: str, *parts: object, now: float | None = None) -> str:
    timestamp = time.time() if now is None else now
    ts_text = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(timestamp))
    raw = ':'.join(str(part) for part in (prefix, *parts, ts_text))
    suffix = sha256(raw.encode('utf-8')).hexdigest()[:10]
    safe_parts = [str(part).strip().replace('/', '_').replace(' ', '_') for part in (prefix, *parts, ts_text)]
    return '__'.join(part for part in safe_parts if part) + f'__{suffix}'


def make_command_center_context(
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    role: str,
    device_id: str,
    patient_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        'schema_version': COMMAND_CENTER_CONTEXT_SCHEMA_VERSION,
        'tenant_id': tenant_id,
        'workspace_id': workspace_id,
        'user_id': user_id,
        'role': role,
        'allowed_device_ids': [device_id],
        'control_boundary': 'auth_context_only_not_motion_permission',
    }
    if patient_id:
        context['patient_id'] = patient_id
        context['allowed_patient_ids'] = [patient_id]
    if session_id:
        context['session_id'] = session_id
    return context


def make_device_register_payload(
    robot_id: str,
    device_id: str,
    software_version: str = 'dev',
    now: float | None = None,
) -> dict[str, object]:
    return {
        'schema_version': 'rehab_arm_device_register_v1',
        'ts_unix': time.time() if now is None else now,
        'robot_id': robot_id,
        'device_id': device_id,
        'device_type': 'nanopi_gateway',
        'software_version': software_version,
        'capabilities': [
            'ros2_bridge',
            'm33_can_status',
            'm55_model_state',
            'camera_keyframe',
            'voice_relay',
            'command_center_snapshot',
            'mujoco_shadow_state',
        ],
        'control_boundary': 'gateway_registration_only_not_motion_permission',
    }


def make_minimal_command_center_snapshot(
    robot_id: str,
    device_id: str,
    source: str = 'nanopi_ros_dry_run',
    now: float | None = None,
) -> dict[str, object]:
    return {
        'schema_version': 'command_center_snapshot_v1',
        'ts_unix': time.time() if now is None else now,
        'robot_id': robot_id,
        'device_id': device_id,
        'source': source,
        'robot_render_state': {
            'schema_version': 'robot_render_state_v1',
            'urdf_asset_id': 'rehab_arm_urdf_current',
            'joint_names': [
                'jian_hengxiang_joint',
                'jian_zongxiang_joint',
                'jian_xuanzhuan_joint',
                'zhou_zongxiang_joint',
                'wanbu_zongxiang_joint',
                'wanbu_hengxiang_joint',
            ],
            'positions': [0.0, 1.7453, 1.0472, 2.3562, 0.0, 0.0],
            'velocities': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            'fresh': [False, False, False, False, False, False],
            'limit_clamped': [False, False, False, False, False, False],
        },
        'safety': {
            'schema_version': 'safety_state_v1',
            'state': 'unknown',
            'motion_allowed': False,
            'control_mode': 'logging_only',
            'detail': 'dry_run_snapshot_not_live_hardware',
            'source': 'dry_run',
        },
        'wiring_health': {
            'schema_version': 'wiring_health_v1',
            'overall': 'unknown',
            'checks': [
                {
                    'channel': 'm33_heartbeat',
                    'status': 'unknown',
                    'fresh_ms': None,
                    'evidence': 'dry_run_plan_only',
                },
                {
                    'channel': 'c8t6_emg_can',
                    'status': 'not_wired',
                    'fresh_ms': None,
                    'evidence': 'reserved_4ch_emg_path',
                },
            ],
        },
        'model_state': {
            'schema_version': 'rehab_arm_model_state_v1',
            'model_results': [],
            'control_boundary': 'model_suggestion_only_not_motion_permission',
        },
        'control_boundary': 'telemetry_snapshot_only_not_motion_permission',
    }


def make_vla_task_request_payload(
    robot_id: str,
    device_id: str,
    session_id: str,
    language_goal: str,
    profile_id: str | None = None,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    context_refs: dict[str, object] = {
        'latest_command_center_snapshot_id': stable_request_id('ccs', device_id, session_id, now=timestamp),
        'latest_camera_keyframe_id': stable_request_id('cam', device_id, session_id, now=timestamp),
    }
    if profile_id:
        context_refs['active_profile_id'] = profile_id
    return {
        'schema_version': 'vla_task_request_v1',
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'session_id': session_id,
        'language_goal': language_goal,
        'context_refs': context_refs,
        'allowed_outputs': [
            'high_level_task',
            'dry_run_joint_trajectory_candidate',
        ],
        'forbidden_outputs': [
            *FORBIDDEN_MOTION_OUTPUTS,
        ],
        'control_boundary': 'vla_planning_request_only_not_motion_permission',
    }


def _json_request(
    method: str,
    url: str,
    body: dict[str, object],
    request_id: str,
    auth_context: dict[str, object],
    purpose: str,
) -> dict[str, object]:
    return {
        'request_id': request_id,
        'purpose': purpose,
        'method': method,
        'url': url,
        'headers': {
            'Content-Type': 'application/json',
            'X-Rehab-Request-Id': request_id,
            'X-Rehab-Tenant-Id': str(auth_context['tenant_id']),
            'X-Rehab-Workspace-Id': str(auth_context['workspace_id']),
        },
        'json': {
            'auth_context': auth_context,
            'data': body,
        },
        'control_boundary': 'planned_http_request_only_not_motion_permission',
    }


def build_command_center_sync_plan(
    robot_id: str,
    device_id: str,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    role: str = 'operator',
    patient_id: str | None = None,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_version: int | None = None,
    training_mode: str = 'active_assist',
    language_goal: str = '协助患者完成一次缓慢肘屈曲训练',
    prompt_text: str = '开始训练',
    base_url: str = DEFAULT_BASE_URL,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    if session_id is None:
        session_id = time.strftime('session_%Y%m%dT%H%M%SZ', time.gmtime(timestamp))

    base = _compact_base_url(base_url)
    auth_context = make_command_center_context(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        device_id=device_id,
        patient_id=patient_id,
        session_id=session_id,
    )
    register = make_device_register_payload(robot_id, device_id, now=timestamp)
    snapshot = make_minimal_command_center_snapshot(robot_id, device_id, now=timestamp)
    voice_plan = build_voice_pipeline_plan(robot_id, device_id, prompt_text=prompt_text, now=timestamp)
    rehab_plan = build_rehab_session_plan(
        robot_id=robot_id,
        device_id=device_id,
        training_mode=training_mode,
        session_id=session_id,
        profile_id=profile_id,
        profile_version=profile_version,
        now=timestamp,
    )
    vla_request = make_vla_task_request_payload(
        robot_id=robot_id,
        device_id=device_id,
        session_id=session_id,
        language_goal=language_goal,
        profile_id=profile_id,
        now=timestamp,
    )

    requests = [
        _json_request(
            'POST',
            f'{base}/devices/register',
            register,
            stable_request_id('register', device_id, now=timestamp),
            auth_context,
            'register_nanopi_gateway_capabilities',
        ),
        _json_request(
            'POST',
            f'{base}/devices/{device_id}/command-center/snapshot',
            snapshot,
            stable_request_id('snapshot', device_id, session_id, now=timestamp),
            auth_context,
            'upload_low_rate_command_center_snapshot',
        ),
        _json_request(
            'POST',
            f'{base}/devices/{device_id}/voice/relay',
            voice_plan['pipeline'][1]['payload'],
            stable_request_id('voice_relay', device_id, session_id, now=timestamp),
            auth_context,
            'relay_voice_intent_as_model_state',
        ),
        _json_request(
            'POST',
            f'{base}/devices/{device_id}/rehab-sessions/plans',
            rehab_plan,
            stable_request_id('rehab_plan', device_id, session_id, now=timestamp),
            auth_context,
            'publish_rehab_session_dry_run_contract',
        ),
        _json_request(
            'POST',
            f'{base}/devices/{device_id}/vla/task-requests',
            vla_request,
            stable_request_id('vla_task', device_id, session_id, now=timestamp),
            auth_context,
            'request_vla_dry_run_candidate_only',
        ),
    ]

    return {
        'schema_version': COMMAND_CENTER_SYNC_PLAN_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'session_id': session_id,
        'base_url': base,
        'auth_context': auth_context,
        'requests': requests,
        'websocket_subscriptions': [
            {
                'url': f'{base}{DEFAULT_WS_PATH.format(device_id=device_id)}',
                'auth_context': auth_context,
                'events': [
                    'command_center_snapshot_v1',
                    'safety_state_v1',
                    'wiring_health_v1',
                    'rehab_arm_model_state_v1',
                    'vla_plan_candidate_v1',
                    'estop_ack_v1',
                ],
                'control_boundary': 'planned_websocket_subscription_only_not_motion_permission',
            }
        ],
        'forbidden_outputs': [
            *FORBIDDEN_MOTION_OUTPUTS,
            'motion_allowed_override',
        ],
        'control_boundary': 'server_sync_plan_only_not_motion_permission',
    }


def _path_join(parent: str, child: object) -> str:
    if parent:
        return f'{parent}.{child}'
    return str(child)


def _walk_payload(value: object, path: str = ''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield _path_join(path, key), key, child
            yield from _walk_payload(child, _path_join(path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield _path_join(path, index), index, child
            yield from _walk_payload(child, _path_join(path, index))


def validate_command_center_sync_plan(plan: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.get('schema_version') != COMMAND_CENTER_SYNC_PLAN_SCHEMA_VERSION:
        errors.append('root schema_version must be command_center_sync_plan_v1')
    if plan.get('control_boundary') != 'server_sync_plan_only_not_motion_permission':
        errors.append('root control_boundary must be server_sync_plan_only_not_motion_permission')

    auth_context = plan.get('auth_context')
    if not isinstance(auth_context, dict):
        errors.append('auth_context must be an object')
        auth_context = {}
    for field in REQUIRED_AUTH_CONTEXT_FIELDS:
        if not auth_context.get(field):
            errors.append(f'auth_context.{field} is required')
    allowed_device_ids = auth_context.get('allowed_device_ids')
    if not isinstance(allowed_device_ids, list) or plan.get('device_id') not in allowed_device_ids:
        errors.append('auth_context.allowed_device_ids must include root device_id')
    if auth_context.get('patient_id') and not auth_context.get('allowed_patient_ids'):
        errors.append('auth_context.allowed_patient_ids is required when patient_id is present')

    forbidden_outputs = plan.get('forbidden_outputs')
    if not isinstance(forbidden_outputs, list):
        errors.append('forbidden_outputs must be a list')
        forbidden_outputs = []
    for name in (*FORBIDDEN_MOTION_OUTPUTS, 'motion_allowed_override'):
        if name not in forbidden_outputs:
            errors.append(f'forbidden_outputs must include {name}')

    requests = plan.get('requests')
    if not isinstance(requests, list) or not requests:
        errors.append('requests must be a non-empty list')
        requests = []
    for index, request in enumerate(requests):
        prefix = f'requests[{index}]'
        if not isinstance(request, dict):
            errors.append(f'{prefix} must be an object')
            continue
        if request.get('control_boundary') != 'planned_http_request_only_not_motion_permission':
            errors.append(f'{prefix}.control_boundary must be planned_http_request_only_not_motion_permission')
        if request.get('method') not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            errors.append(f'{prefix}.method is invalid')
        if not str(request.get('url', '')).startswith(str(plan.get('base_url', ''))):
            errors.append(f'{prefix}.url must start with base_url')
        request_json = request.get('json')
        if not isinstance(request_json, dict):
            errors.append(f'{prefix}.json must be an object')
            continue
        if request_json.get('auth_context') != auth_context:
            errors.append(f'{prefix}.json.auth_context must match root auth_context')
        data = request_json.get('data')
        if not isinstance(data, dict):
            errors.append(f'{prefix}.json.data must be an object')
        elif 'control_boundary' not in data:
            errors.append(f'{prefix}.json.data.control_boundary is required')

    websocket_subscriptions = plan.get('websocket_subscriptions')
    if not isinstance(websocket_subscriptions, list) or not websocket_subscriptions:
        errors.append('websocket_subscriptions must be a non-empty list')
        websocket_subscriptions = []
    for index, subscription in enumerate(websocket_subscriptions):
        prefix = f'websocket_subscriptions[{index}]'
        if not isinstance(subscription, dict):
            errors.append(f'{prefix} must be an object')
            continue
        if subscription.get('auth_context') != auth_context:
            errors.append(f'{prefix}.auth_context must match root auth_context')
        if subscription.get('control_boundary') != 'planned_websocket_subscription_only_not_motion_permission':
            errors.append(f'{prefix}.control_boundary must be planned_websocket_subscription_only_not_motion_permission')
        if 'events' not in subscription:
            errors.append(f'{prefix}.events is required')

    forbidden_paths: list[str] = []
    for path, key, value in _walk_payload(plan):
        if key in FORBIDDEN_MOTION_OUTPUTS and value not in (False, None):
            forbidden_paths.append(path)
    if forbidden_paths:
        warnings.append(
            'forbidden motion output names appear as payload keys; verify they are only deny-list metadata: '
            + ', '.join(forbidden_paths)
        )

    return {
        'schema_version': 'command_center_sync_quality_report_v1',
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'control_boundary': 'quality_gate_only_not_motion_permission',
    }
