from __future__ import annotations

import time

from rehab_arm_psoc_bridge.operator_review import validate_operator_review_record
from rehab_arm_psoc_bridge.safety_gate import fresh_motor_feedback_gate_detail, psoc_motion_gate_detail


M33_GATE_PREPARATION_SCHEMA_VERSION = 'm33_gate_preparation_package_v1'


def build_m33_gate_preparation_package(
    operator_review_record: dict[str, object],
    psoc_status: dict[str, object] | None,
    last_fresh_motor_status_age_sec: float | None,
    fresh_motor_status_count: int,
    motor_feedback_timeout_sec: float = 1.0,
    allow_bench_motion: bool = False,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    review_quality = validate_operator_review_record(operator_review_record)
    psoc_allowed, psoc_detail = psoc_motion_gate_detail(psoc_status, allow_bench_motion=allow_bench_motion)
    feedback_ok, feedback_detail = fresh_motor_feedback_gate_detail(
        last_fresh_motor_status_age_sec,
        motor_feedback_timeout_sec,
        fresh_motor_status_count,
    )
    ready = bool(review_quality.get('ok')) and psoc_allowed and feedback_ok
    return {
        'schema_version': M33_GATE_PREPARATION_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': operator_review_record.get('robot_id'),
        'device_id': operator_review_record.get('device_id'),
        'session_id': operator_review_record.get('session_id'),
        'source_plan_id': operator_review_record.get('source_plan_id'),
        'mujoco_report_id': operator_review_record.get('mujoco_report_id'),
        'ready_for_m33_gate': ready,
        'review_quality': review_quality,
        'safety_checks': {
            'psoc_motion_gate': {
                'ok': psoc_allowed,
                'detail': psoc_detail,
                'allow_bench_motion': bool(allow_bench_motion),
            },
            'fresh_motor_feedback_gate': {
                'ok': feedback_ok,
                'detail': feedback_detail,
                'timeout_sec': float(motor_feedback_timeout_sec),
                'fresh_motor_status_count': int(fresh_motor_status_count),
                'last_fresh_motor_status_age_sec': last_fresh_motor_status_age_sec,
            },
        },
        'allowed_next_steps': [
            'prepare_joint_trajectory_for_m33_gate',
        ] if ready else [],
        'forbidden_next_steps': [
            'publish_joint_trajectory_without_m33_gate',
            'send_can_frame_directly',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'm33_gate_preparation_only_not_motion_permission',
    }
