from __future__ import annotations

import time


REHAB_SESSION_SCHEMA_VERSION = 'rehab_session_plan_v1'
SUPPORTED_TRAINING_MODES = {
    'passive_training',
    'active_assist',
    'resistance_training',
    'memory_mode',
}
REQUIRED_REHAB_TOPICS = [
    '/joint_states',
    '/rehab_arm/safety_state',
    '/rehab_arm/motor_state',
    '/rehab_arm/sensor_state',
    '/rehab_arm/model_state',
    '/rehab_arm/camera_keyframe',
]


def make_emg_input_contract() -> dict[str, object]:
    return {
        'schema_version': 'emg_feature_window_v1',
        'source_path': 'C8T6 -> M33 -> M55 -> M33 -> 0x323 -> NanoPi',
        'channel_count': 4,
        'window_ms': 200,
        'features': [
            'rms',
            'mean_abs',
            'zero_crossing',
            'quality',
            'contact_valid',
        ],
        'raw_signal_topic': '/rehab_arm/sensor_state',
        'model_result_topic': '/rehab_arm/model_state',
        'control_boundary': 'emg_model_suggestion_only_not_motion_permission',
    }


def build_rehab_session_plan(
    robot_id: str,
    device_id: str,
    training_mode: str,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_version: int | None = None,
    now: float | None = None,
) -> dict[str, object]:
    if training_mode not in SUPPORTED_TRAINING_MODES:
        choices = ', '.join(sorted(SUPPORTED_TRAINING_MODES))
        raise ValueError(f'unknown training_mode {training_mode!r}; expected one of: {choices}')

    timestamp = time.time() if now is None else now
    if session_id is None:
        session_id = time.strftime('rehab_%Y%m%dT%H%M%SZ', time.gmtime(timestamp))

    return {
        'schema_version': REHAB_SESSION_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'session_id': session_id,
        'robot_id': robot_id,
        'device_id': device_id,
        'profile_id': profile_id,
        'profile_version': profile_version,
        'training_mode': training_mode,
        'required_topics': list(REQUIRED_REHAB_TOPICS),
        'emg_input_contract': make_emg_input_contract(),
        'voice_input_contract': {
            'schema_version': 'voice_capture_v1',
            'sources': ['m55_microphone', 'app_microphone', 'command_center_microphone'],
            'wake_phrase_default': 'xiao_yi_xiao_yi',
            'relay_schema_version': 'voice_relay_v1',
            'control_boundary': 'voice_input_only_not_motion_permission',
        },
        'path_planning_contract': {
            'input': [
                'patient_profile_rom',
                'current_joint_state',
                'mujoco_shadow_state',
                'm33_safety_state',
                'm55_model_state',
                'voice_or_vla_task_intent',
            ],
            'output': ['dry_run_joint_trajectory_candidate'],
            'must_validate_in': ['MuJoCo shadow', 'M33 safety gate'],
            'forbidden_outputs': ['can_frame', 'raw_motor_position', 'motor_current', 'motor_torque'],
            'control_boundary': 'path_plan_candidate_only_not_motion_permission',
        },
        'phases': [
            {
                'name': 'precheck',
                'requires': [
                    'm33_heartbeat_fresh',
                    'safety_state_ok',
                    'wiring_health_ok',
                    'profile_loaded',
                    'motion_allowed_false_until_operator_confirmed',
                ],
            },
            {
                'name': 'warmup',
                'duration_s': 120,
                'rom_scale': 0.5,
                'output': 'dry_run_joint_trajectory_candidate',
            },
            {
                'name': 'assist_or_motion',
                'mode': training_mode,
                'allowed_outputs': ['dry_run_joint_trajectory_candidate', 'operator_review_request'],
                'forbidden_outputs': ['can_frame', 'direct_motor_command'],
            },
            {
                'name': 'cooldown',
                'duration_s': 60,
                'rom_scale': 0.35,
            },
            {
                'name': 'review',
                'outputs': ['session_summary', 'annotation_queue_candidate', 'model_training_candidate'],
            },
        ],
        'control_boundary': 'rehab_session_plan_only_not_motion_permission',
    }
