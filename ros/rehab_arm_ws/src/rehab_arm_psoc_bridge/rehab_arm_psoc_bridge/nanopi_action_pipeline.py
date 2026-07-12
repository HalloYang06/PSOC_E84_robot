from __future__ import annotations

import time

from rehab_arm_psoc_bridge.mujoco_dry_run_review import build_mujoco_dry_run_review_plan
from rehab_arm_psoc_bridge.mujoco_dry_run_review import validate_mujoco_dry_run_review_report
from rehab_arm_psoc_bridge.server_action_ingress import make_nanopi_action_queue_item
from rehab_arm_psoc_bridge.vla_candidate_gate import build_example_vla_plan_candidate


NANOPI_ACTION_PIPELINE_PLAN_SCHEMA_VERSION = 'nanopi_action_pipeline_plan_v1'
OPERATOR_REVIEW_REQUEST_SCHEMA_VERSION = 'operator_review_request_v1'

ACTION_TO_JOINT_TARGET = {
    'assist_slow_arm_raise': ('jian_zongxiang_joint', 0.08),
    'assist_elbow_flexion': ('zhou_zongxiang_joint', 0.1),
    'assist_wrist_flexion': ('wanbu_zongxiang_joint', 0.08),
    'pause_training': ('zhou_zongxiang_joint', 0.0),
    'stop_training': ('zhou_zongxiang_joint', 0.0),
}


def _select_candidate_target(queue_item: dict[str, object]) -> tuple[str, float]:
    action = queue_item.get('action') if isinstance(queue_item.get('action'), dict) else {}
    label = str(action.get('label') or '')
    return ACTION_TO_JOINT_TARGET.get(label, ('zhou_zongxiang_joint', 0.05))


def build_nanopi_action_pipeline_plan(
    queue_item: dict[str, object],
    session_id: str = 'session_action_pipeline',
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    if queue_item.get('schema_version') != 'nanopi_high_level_action_queue_item_v1':
        return {
            'schema_version': NANOPI_ACTION_PIPELINE_PLAN_SCHEMA_VERSION,
            'ts_unix': timestamp,
            'accepted_for_pipeline': False,
            'blocked_reason': 'queue_item_schema_mismatch',
            'allowed_next_steps': [],
            'forbidden_next_steps': [
                'publish_joint_trajectory',
                'send_can_frame',
                'set_motor_current',
                'set_motor_torque',
                'override_m33_safety',
            ],
            'control_boundary': 'nanopi_action_pipeline_plan_only_not_motion_permission',
        }

    if queue_item.get('accepted') is not True:
        return {
            'schema_version': NANOPI_ACTION_PIPELINE_PLAN_SCHEMA_VERSION,
            'ts_unix': timestamp,
            'robot_id': queue_item.get('robot_id'),
            'device_id': queue_item.get('device_id'),
            'queue_item_id': queue_item.get('queue_item_id'),
            'accepted_for_pipeline': False,
            'blocked_reason': 'queue_item_not_accepted',
            'reject_reasons': queue_item.get('reject_reasons', []),
            'allowed_next_steps': [],
            'forbidden_next_steps': queue_item.get('blocked_pipeline', []),
            'control_boundary': 'nanopi_action_pipeline_plan_only_not_motion_permission',
        }

    joint_name, position_rad = _select_candidate_target(queue_item)
    candidate = build_example_vla_plan_candidate(
        plan_id=f"{queue_item.get('queue_item_id')}__candidate",
        joint_name=joint_name,
        position_rad=position_rad,
        now=timestamp,
    )
    candidate['source_queue_item_id'] = queue_item.get('queue_item_id')
    candidate['source_command_id'] = queue_item.get('source_command_id')
    candidate['summary'] = 'NanoPi 从服务器 A 高层队列项生成的保守 dry-run 候选。'

    dry_run_plan = build_mujoco_dry_run_review_plan(
        candidate,
        robot_id=str(queue_item.get('robot_id') or ''),
        device_id=str(queue_item.get('device_id') or ''),
        session_id=session_id,
        now=timestamp,
    )

    return {
        'schema_version': NANOPI_ACTION_PIPELINE_PLAN_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': queue_item.get('robot_id'),
        'device_id': queue_item.get('device_id'),
        'session_id': session_id,
        'queue_item_id': queue_item.get('queue_item_id'),
        'source_command_id': queue_item.get('source_command_id'),
        'accepted_for_pipeline': bool(dry_run_plan.get('accepted_for_review')),
        'candidate': candidate,
        'dry_run_review_plan': dry_run_plan,
        'allowed_next_steps': [
            'run_mujoco_dry_run',
            'record_operator_review',
        ] if dry_run_plan.get('accepted_for_review') else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'nanopi_action_pipeline_plan_only_not_motion_permission',
    }


def build_pipeline_from_server_action(
    server_action: dict[str, object],
    session_id: str = 'session_action_pipeline',
    now: float | None = None,
) -> dict[str, object]:
    queue_item = make_nanopi_action_queue_item(server_action, now=now)
    return build_nanopi_action_pipeline_plan(queue_item, session_id=session_id, now=now)


def build_operator_review_request_from_dry_run(
    pipeline_plan: dict[str, object],
    dry_run_report: dict[str, object],
    reviewer_role_hint: str = 'operator',
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    quality = validate_mujoco_dry_run_review_report(dry_run_report)
    accepted = bool(pipeline_plan.get('accepted_for_pipeline')) and bool(quality.get('ok'))
    return {
        'schema_version': OPERATOR_REVIEW_REQUEST_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': pipeline_plan.get('robot_id'),
        'device_id': pipeline_plan.get('device_id'),
        'session_id': pipeline_plan.get('session_id'),
        'queue_item_id': pipeline_plan.get('queue_item_id'),
        'source_command_id': pipeline_plan.get('source_command_id'),
        'source_plan_id': (
            pipeline_plan.get('candidate', {}).get('plan_id')
            if isinstance(pipeline_plan.get('candidate'), dict)
            else None
        ),
        'mujoco_quality_report': quality,
        'ready_for_operator_review': accepted,
        'reviewer_role_hint': reviewer_role_hint,
        'required_acknowledgements': [
            'patient_profile_confirmed',
            'mujoco_dry_run_reviewed',
            'm33_safety_gate_required',
            'fresh_motor_feedback_required',
            'estop_available',
        ],
        'allowed_next_steps': [
            'build_operator_review_record',
        ] if accepted else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory_without_m33_gate',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'operator_review_request_only_not_motion_permission',
    }
