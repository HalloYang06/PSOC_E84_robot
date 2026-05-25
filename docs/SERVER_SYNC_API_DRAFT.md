# Server Sync API Draft

本文档定义 NanoPi/工作站到总服务器的第一版非实时数据同步草案。它只用于数据资产、标注、报告和模型训练，不进入 M33 电机控制闭环。

## Safety Boundary

- 总服务器不直接发 CAN。
- 总服务器不下发电机角度、速度、力矩或电流。
- 总服务器不作为急停、限位、heartbeat 或实时控制依赖。
- NanoPi 断网时，本地 ROS、M33 安全状态机和急停仍必须独立工作。
- 服务器下发的任务只能是高层任务、分段目标、训练配置或数据请求，最终运动仍走 `JointTrajectory -> NanoPi -> M33`。

## Data Model

NanoPi 本地先生成：

```text
<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl
manifest.json
```

JSONL 第一行必须是：

```json
{
  "record_type": "session_metadata",
  "schema_version": "rehab_arm_jsonl_v1",
  "session_id": "rehab-arm-alpha__nanopi-m5__20260525T095052Z",
  "device_id": "nanopi-m5",
  "robot_id": "rehab-arm-alpha",
  "software_version": "dev",
  "mode": "logging_only",
  "source": "nanopi_ros_recorder",
  "sync_status": "local_only",
  "topics": ["/joint_states", "/rehab_arm/safety_state", "/rehab_arm/sensor_state"],
  "motion_allowed_expected": false
}
```

Manifest 使用 `rehab_arm_manifest_v1`，列出每个 JSONL 文件：

```json
{
  "schema_version": "rehab_arm_manifest_v1",
  "log_dir": "/home/pi/rehab_arm_logs",
  "session_count": 1,
  "sessions": [
    {
      "file_name": "rehab-arm-alpha__nanopi-m5__20260525T095052Z.jsonl",
      "sync_status": "local_only",
      "ok": true,
      "session_id": "rehab-arm-alpha__nanopi-m5__20260525T095052Z",
      "device_id": "nanopi-m5",
      "robot_id": "rehab-arm-alpha",
      "schema_version": "rehab_arm_jsonl_v1",
      "topics": ["/joint_states", "/rehab_arm/safety_state", "/rehab_arm/sensor_state"]
    }
  ]
}
```

## First API Endpoints

Base path draft:

```text
/api/rehab-arm/v1
```

### 1. Register Device

```http
POST /api/rehab-arm/v1/devices/register
Content-Type: application/json
```

Request:

```json
{
  "device_id": "nanopi-m5",
  "robot_id": "rehab-arm-alpha",
  "device_type": "nanopi",
  "software_version": "dev",
  "capabilities": ["ros2_bridge", "jsonl_recorder", "manifest_builder"]
}
```

Response:

```json
{"ok": true, "device_id": "nanopi-m5"}
```

### 2. Upload Manifest

```http
POST /api/rehab-arm/v1/sessions/manifest
Content-Type: application/json
```

Request:

```json
{
  "device_id": "nanopi-m5",
  "robot_id": "rehab-arm-alpha",
  "manifest": {
    "schema_version": "rehab_arm_manifest_v1",
    "session_count": 1,
    "sessions": []
  }
}
```

Response:

```json
{
  "ok": true,
  "accepted_sessions": [],
  "missing_files": [],
  "upload_urls": []
}
```

### 3. Upload Session File

First version may use simple multipart upload:

```http
POST /api/rehab-arm/v1/sessions/{session_id}/files
Content-Type: multipart/form-data
```

Fields:

```text
device_id
robot_id
file_name
sha256
file
```

Response:

```json
{"ok": true, "session_id": "...", "file_name": "...", "sync_status": "uploaded"}
```

### 4. Report Sync Status

```http
POST /api/rehab-arm/v1/sessions/{session_id}/sync-status
Content-Type: application/json
```

Request:

```json
{
  "device_id": "nanopi-m5",
  "sync_status": "uploaded",
  "file_name": "rehab-arm-alpha__nanopi-m5__20260525T095052Z.jsonl",
  "record_count": 1234
}
```

## Server To NanoPi Boundary

Allowed server outputs:

- data upload request
- config update proposal
- training session template
- high-level task stage, such as `move_to_preset_A`
- VLA task plan summary for local planner review

Forbidden server outputs:

- CAN frame
- motor current, torque, raw position, raw velocity
- M33 safety override
- emergency stop dependency
- command that bypasses local M33 safety state

## First Implementation Order

1. Keep NanoPi recording local JSONL files.
2. Generate local `manifest.json`.
3. Add a dry-run uploader that prints intended HTTP requests.
4. Add real upload only after server endpoint is confirmed.
5. Server stores data as assets for review, annotation, reports and model training.
