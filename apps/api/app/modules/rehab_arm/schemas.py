from __future__ import annotations

from pydantic import BaseModel, Field


class RehabDeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    device_type: str = "nanopi"
    software_version: str = "unknown"
    capabilities: list[str] = Field(default_factory=list)


class RehabManifestUploadRequest(BaseModel):
    manifest: dict


class RehabSyncStatusRequest(BaseModel):
    device_id: str = Field(min_length=1)
    sync_status: str = Field(min_length=1)
    file_name: str = ""
    record_count: int | None = None
