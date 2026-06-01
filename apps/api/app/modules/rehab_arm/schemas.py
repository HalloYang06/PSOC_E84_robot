from __future__ import annotations

from pydantic import BaseModel, Field


class RehabDeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    project_id: str = ""
    device_type: str = "nanopi"
    software_version: str = "unknown"
    capabilities: list[str] = Field(default_factory=list)


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
    state: str = Field(pattern="^(ok|limited|emergency_stop|fault)$")
    motion_allowed: bool = False
    emergency_stop: bool = False
    m33_mode: str = ""
    detail_code: str = ""
    detail: str = ""
    heartbeat_age_ms: int | None = None
    fault_code: str = ""
    fault_message: str = ""
