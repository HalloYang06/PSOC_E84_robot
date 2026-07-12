from __future__ import annotations

import time

from rehab_arm_psoc_bridge.vla_candidate_gate import validate_vla_plan_candidate


MUJOCO_DRY_RUN_REVIEW_PLAN_SCHEMA_VERSION = 'mujoco_dry_run_review_plan_v1'
MUJOCO_DRY_RUN_REVIEW_REPORT_SCHEMA_VERSION = 'mujoco_dry_run_review_report_v1'
DEFAULT_SIM_MODEL = 'medical_arm_6dof.xml'
DEFAULT_COMMAND_TOPIC = '/sim/medical_arm/trajectory_candidate'
DEFAULT_STATE_TOPIC = '/sim/medical_arm/joint_states'


def build_mujoco_dry_run_review_plan(
    vla_candidate: dict[str, object],
    robot_id: str,
    device_id: str,
    session_id: str,
    sim_model: str = DEFAULT_SIM_MODEL,
    command_topic: str = DEFAULT_COMMAND_TOPIC,
    state_topic: str = DEFAULT_STATE_TOPIC,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    gate_report = validate_vla_plan_candidate(vla_candidate)
    if not gate_report['ok']:
        return {
            'schema_version': MUJOCO_DRY_RUN_REVIEW_PLAN_SCHEMA_VERSION,
            'ts_unix': timestamp,
            'robot_id': robot_id,
            'device_id': device_id,
            'session_id': session_id,
            'accepted_for_review': False,
            'gate_report': gate_report,
            'blocked_reason': 'vla_candidate_gate_failed',
            'allowed_next_steps': [],
            'forbidden_next_steps': [
                'publish_joint_trajectory',
                'send_can_frame',
                'set_motor_current',
                'set_motor_torque',
                'override_m33_safety',
            ],
            'control_boundary': 'mujoco_dry_run_plan_only_not_motion_permission',
        }

    candidate = vla_candidate['candidate']
    return {
        'schema_version': MUJOCO_DRY_RUN_REVIEW_PLAN_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'session_id': session_id,
        'accepted_for_review': True,
        'source_plan_id': vla_candidate.get('plan_id'),
        'sim_target': {
            'sim_model': sim_model,
            'command_topic': command_topic,
            'state_topic': state_topic,
            'candidate_type': candidate.get('type'),
            'joint_names': list(candidate.get('joint_names', [])),
            'point_count': len(candidate.get('points', [])),
        },
        'candidate': candidate,
        'gate_report': gate_report,
        'review_checks': [
            {
                'name': 'load_mjcf_model',
                'required': True,
                'pass_condition': 'MuJoCo loads the model without fallback-only errors',
            },
            {
                'name': 'joint_name_match',
                'required': True,
                'pass_condition': 'candidate joints match medical_arm_6dof joint names',
            },
            {
                'name': 'limit_check',
                'required': True,
                'pass_condition': 'simulated positions stay within configured joint limits',
            },
            {
                'name': 'continuity_check',
                'required': True,
                'pass_condition': 'trajectory time and position deltas are smooth enough for rehab dry-run review',
            },
            {
                'name': 'collision_or_self_intersection_visual_check',
                'required': True,
                'pass_condition': 'operator observes no obvious collision or unsafe pose in MuJoCo/Three.js view',
            },
            {
                'name': 'm33_safety_precondition',
                'required': True,
                'pass_condition': 'future real execution still requires M33 motion_allowed=true and fresh motor feedback',
            },
        ],
        'expected_report_schema': MUJOCO_DRY_RUN_REVIEW_REPORT_SCHEMA_VERSION,
        'allowed_next_steps': [
            'run_mujoco_dry_run',
            'record_operator_review',
        ],
        'forbidden_next_steps': [
            'publish_joint_trajectory',
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'mujoco_dry_run_plan_only_not_motion_permission',
    }


def validate_mujoco_dry_run_review_report(report: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if report.get('schema_version') != MUJOCO_DRY_RUN_REVIEW_REPORT_SCHEMA_VERSION:
        errors.append('schema_version must be mujoco_dry_run_review_report_v1')
    if report.get('control_boundary') != 'mujoco_review_only_not_motion_permission':
        errors.append('control_boundary must be mujoco_review_only_not_motion_permission')
    if report.get('dry_run_passed') is not True:
        errors.append('dry_run_passed must be true before any operator approval step')
    if report.get('motion_permission_granted') is True:
        errors.append('MuJoCo dry-run report must not grant real motion permission')

    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        errors.append('checks must be a non-empty list')
        checks = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            errors.append(f'checks[{index}] must be an object')
            continue
        if check.get('passed') is not True:
            errors.append(f"checks[{index}] {check.get('name', '<unnamed>')} must pass")

    if report.get('m33_motion_allowed') is True:
        warnings.append('m33_motion_allowed in report is telemetry context only; M33 must be checked again at execution time')

    return {
        'schema_version': 'mujoco_dry_run_review_quality_report_v1',
        'ok': not errors,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'allowed_next_steps': [
            'operator_review',
            'prepare_joint_trajectory_for_m33_gate',
        ] if not errors else [],
        'forbidden_next_steps': [
            'send_can_frame',
            'set_motor_current',
            'set_motor_torque',
            'override_m33_safety',
        ],
        'control_boundary': 'mujoco_review_quality_gate_only_not_motion_permission',
    }
