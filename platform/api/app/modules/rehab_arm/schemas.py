from __future__ import annotations

from pydantic import BaseModel, Field


class RehabDeviceRegisterRequest(BaseModel):
    schema_version: str = "rehab_arm_device_register_v1"
    device_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    project_id: str = ""
    computer_node_id: str = ""
    runner_id: str = ""
    device_type: str = "nanopi"
    software_version: str = "unknown"
    capabilities: list[str] = Field(default_factory=list)
    control_boundary: str = "gateway_registration_only_not_motion_permission"


class RehabManifestUploadRequest(BaseModel):
    manifest: dict


class RehabSyncStatusRequest(BaseModel):
    device_id: str = Field(min_length=1)
    project_id: str = ""
    sync_status: str = Field(min_length=1)
    file_name: str = ""
    record_count: int | None = None


class RehabSimulationReadinessRequest(BaseModel):
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    report: dict


class RehabBoardManifestRequest(BaseModel):
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    computer_node_id: str = ""
    runner_id: str = ""
    manifest: dict


class RehabMotorSample(BaseModel):
    motor_id: str = Field(min_length=1)
    joint_name: str = ""
    protocol: str = "other"
    position: float | None = None
    velocity: float | None = None
    torque: float | None = None
    current: float | None = None
    temperature: float | None = None
    voltage: float | None = None
    error_code: str | int | None = None
    enabled: bool = False
    fault: bool = False
    raw_can_id: str | int | None = None
    raw_payload_hex: str | None = None


class RehabMotorStateRequest(BaseModel):
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    ts_unix: float
    motors: list[RehabMotorSample] = Field(default_factory=list)
    joint_state: dict | list | None = None
    joint_states: dict | list | None = None
    source: str = "nanopi"


class RehabSensorStateRequest(BaseModel):
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    ts_unix: float | None = None
    emg: dict | list | None = None
    heart_rate: float | None = None
    imu: dict | list | None = None
    fatigue_score: float | None = None
    intent_prediction: dict | str | None = None
    model_outputs: dict | list | None = None
    source: str = "nanopi"


class RehabSafetyStateRequest(BaseModel):
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    schema_version: str = "safety_state_v1"
    state: str = Field(pattern="^(ok|limited|emergency_stop|fault)$")
    motion_allowed: bool = False
    emergency_stop: bool = False
    control_mode: str = ""
    m33_mode: str = ""
    detail_code: str = ""
    detail: str = ""
    heartbeat_age_ms: int | None = None
    source: str = "m33_can_0x322"
    fault_code: str = ""
    fault_message: str = ""


class RehabCommandCenterSnapshotRequest(BaseModel):
    schema_version: str = "command_center_snapshot_v1"
    ts_unix: float | None = None
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    source: str = "nanopi_ros"
    profile: dict = Field(default_factory=dict)
    robot_render_state: dict = Field(default_factory=dict)
    safety: dict = Field(default_factory=dict)
    wiring_health: dict = Field(default_factory=dict)
    model_state: dict = Field(default_factory=dict)
    control_boundary: str = "telemetry_snapshot_only_not_motion_permission"


class RehabVlaTaskRequest(BaseModel):
    schema_version: str = "vla_task_request_v1"
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    session_id: str = ""
    language_goal: str = Field(min_length=1)
    context_refs: dict = Field(default_factory=dict)
    allowed_outputs: list[str] = Field(default_factory=lambda: ["high_level_task", "dry_run_joint_trajectory_candidate"])
    forbidden_outputs: list[str] = Field(default_factory=lambda: [
        "can_frame",
        "motor_current",
        "motor_torque",
        "raw_motor_position",
        "raw_motor_velocity",
        "m33_safety_override",
    ])
    control_boundary: str = "vla_planning_request_only_not_motion_permission"


class RehabModelRelayRequest(BaseModel):
    schema_version: str = "model_relay_request_v1"
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    session_id: str = ""
    input_type: str = Field(default="high_level_task", pattern="^(high_level_task|voice_intent|vla_language_from_voice|vla_context|camera_scene|sensor_summary)$")
    prompt: str = Field(min_length=1)
    context_refs: dict = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=lambda: ["high_level_task", "dry_run_joint_trajectory_candidate", "model_state_suggestion"])
    forbidden_outputs: list[str] = Field(default_factory=lambda: [
        "can_frame",
        "motor_current",
        "motor_torque",
        "motor_velocity",
        "raw_motor_position",
        "raw_motor_velocity",
        "joint_trajectory",
        "trajectory_points",
        "m33_safety_override",
        "motion_allowed_override",
        "motion_permission_granted",
        "direct_motor_command",
    ])
    operator_id: str = ""
    control_boundary: str = "model_relay_request_only_not_motion_permission"


class RehabModelRelayConfigRequest(BaseModel):
    provider: str = Field(default="openai_compatible", min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)
    external_enabled: bool = True


class RehabModelRelayTokenRequest(BaseModel):
    ttl_seconds: int = Field(default=7 * 24 * 60 * 60, ge=60, le=30 * 24 * 60 * 60)
    label: str = Field(default="rehab-arm-model-relay-token", max_length=120)


class RehabCameraStreamOfferRequest(BaseModel):
    schema_version: str = "camera_stream_offer_v1"
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    camera_id: str = Field(min_length=1)
    transport: str = "webrtc_or_mjpeg"
    max_fps: int = 15
    max_width: int = 1280
    max_height: int = 720
    control_boundary: str = "camera_preview_only_not_motion_permission"


class RehabStereoVisionContextRequest(BaseModel):
    schema_version: str = "stereo_rgb_yolo_context_v1"
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    frame_ts_unix: float
    capture_loop: dict | None = None
    left_camera_id: str = Field(min_length=1)
    right_camera_id: str = Field(min_length=1)
    stereo_calibration_id: str = ""
    baseline_m: float | None = None
    image_pair_ref: dict = Field(default_factory=dict)
    detections: dict | list = Field(default_factory=dict)
    target_object: dict | str | None = None
    pixel_servo_hint: dict | None = None
    visual_lock_stability: dict | None = None
    estimated_depth_m: float | None = None
    target_3d_camera_frame: dict | list | None = None
    scene_summary: str = ""
    vla_context: str = ""
    confidence: float | None = None
    control_boundary: str = "stereo_vision_context_only_not_motion_permission"


class RehabEstopRequest(BaseModel):
    schema_version: str = "estop_request_v1"
    request_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    project_id: str = ""
    source: str = "command_center"
    operator_id: str = ""
    reason: str = "operator_pressed_estop"
    requested_action: str = "disable_motor_output"
    control_boundary: str = "estop_request_requires_m33_ack"
