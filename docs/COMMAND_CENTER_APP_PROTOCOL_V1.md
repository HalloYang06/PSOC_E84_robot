# Command Center and App Protocol V1

本文定义服务器机械臂总控台、NanoPi、M33/M55、Linux MuJoCo 仿真主机和用户 App 的第一版协议边界。平台仓库由另一个 AI 实现；本仓库只固定必须遵守的接口、字段和安全语义。

## 1. 边界

正式运动入口仍只有：

```text
JointTrajectory -> NanoPi -> M33 -> motor
```

服务器总控台、App、VLA、M55、MuJoCo 均不能绕过 M33：

- 服务器不得直接发 CAN、电流、力矩、速度、裸电机位置或 M33 safety override。
- App 不得直接发底层电机目标；App BLE 只允许训练请求、急停请求、profile 确认、状态显示和标注。
- VLA 只能输出高层任务或 dry-run 轨迹候选，不能输出底层电机控制。
- 急停按钮可以从服务器或 App 发起“请求”，但真实急停执行和电机输出关闭必须由 M33 本地确认；网络断开时本地急停仍必须独立工作。
- 任何协议响应里如果涉及 AI、VLA、语音、图像、模型结果，必须带 `control_boundary`。

## 2. 总控台功能和数据来源

| 总控台功能 | 主要数据源 | 协议对象 | 控制边界 |
|---|---|---|---|
| Three.js + URDF + 电机/传感器数据渲染 | URDF、`/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/sensor_state` | `command_center_snapshot_v1`、`robot_render_state_v1` | 只读显示，不产生真机控制 |
| 摄像头图像采集 | NanoPi camera keyframe/stream | `camera_keyframe_v1`、`camera_stream_offer_v1` | 感知数据，不是控制命令 |
| 语音采集和 API 中转 | App 麦克风、浏览器麦克风、M55 ASR 摘要 | `voice_capture_v1`、`voice_relay_v1`、`rehab_arm_model_state_v1` | 语音只生成文本/意图，不直接运动 |
| VLA | 摄像头、语音、joint、电机、profile、M55 model state | `vla_task_request_v1`、`vla_plan_candidate_v1` | 只输出任务/候选轨迹，进入 dry-run |
| 接线检测 | M33 `0x330~0x337` freshness、C8T6 `0x7C2/0x7C3`、心跳、温度、错误计数 | `wiring_health_v1` | 只报告断线/异常；不能自动补偿控制 |
| 安全状态检测 | M33 `0x322`、NanoPi bridge `/rehab_arm/safety_state` | `safety_state_v1` | `motion_allowed` 只读展示，M33 最终裁决 |
| 急停按钮 | 总控台/App 请求，M33 本地执行 | `estop_request_v1`、`estop_ack_v1` | 请求可远程发起，执行必须由 M33 确认 |

## 3. Transport

第一版使用 REST + WebSocket：

```text
REST base: /api/rehab-arm/v1
WebSocket: /api/rehab-arm/v1/devices/{device_id}/events
```

REST 用于注册、配置、上传、命令请求和查询快照。WebSocket 用于总控台实时显示。WebSocket 掉线不得影响 M33 本地安全。

## 3.1 多账号和数据隔离

服务器总控台会接入云服务器和 AI 合作平台。平台实现必须把医疗臂数据当作多租户医疗/康复数据处理，不能只按 `device_id` 做全局共享。

所有 REST/WebSocket 请求的认证上下文必须至少能解析出：

```json
{
  "tenant_id": "tenant_hospital_or_team",
  "user_id": "user_operator_or_doctor",
  "role": "operator|doctor|admin|annotator|viewer",
  "workspace_id": "workspace_rehab_lab",
  "allowed_device_ids": ["nanopi-m5"],
  "allowed_patient_ids": ["patient_..."]
}
```

平台必须遵守：

- `tenant_id/workspace_id` 是最外层隔离边界；不同账号、不同团队、不同医院的数据默认不可见。
- 设备、患者 profile、训练 session、摄像头帧、语音文本/音频摘要、M55 模型结果、MuJoCo 回放和标注数据都必须绑定 `tenant_id`、`workspace_id`、`device_id`，涉及患者时还必须绑定 `patient_id/profile_id`。
- WebSocket 事件只能推送给有该 `device_id` 权限的连接；不能把一个用户的实时状态广播给全局房间。
- VLA、ASR、TTS、标注和训练任务只能读取调用者有权限的数据；跨患者/跨设备训练集必须有显式管理员授权和审计记录。
- 急停请求、pause 请求和 profile 发布必须记录 `tenant_id/user_id/role/request_id`，但执行权仍在 M33。
- 日志、截图、音频、视频、JSONL 和模型训练样本不能用公开 URL 或无租户前缀对象 key。

本仓库当前只定义合同；实际平台仓库接入前必须先确认平台仓库位置。不要把早期 PSoC/RT-Thread 工程目录当成云平台实现。

所有服务端响应沿用平台统一格式：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_..."
  }
}
```

错误格式：

```json
{
  "error": {
    "code": "HARDWARE_OPERATION_BLOCKED",
    "message": "motion command is not allowed through command center",
    "details": {}
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

## 4. Device Registration

```http
POST /api/rehab-arm/v1/devices/register
Content-Type: application/json
```

Request:

```json
{
  "schema_version": "rehab_arm_device_register_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "device_type": "nanopi_gateway",
  "software_version": "dev",
  "capabilities": [
    "ros2_bridge",
    "m33_can_status",
    "camera_keyframe",
    "voice_relay",
    "command_center_snapshot"
  ],
  "control_boundary": "gateway_registration_only_not_motion_permission"
}
```

## 5. Command Center Snapshot

NanoPi 或仿真主机定期向服务器上传低频总控台快照，服务器也可通过 WebSocket 转发给浏览器。

```http
POST /api/rehab-arm/v1/devices/{device_id}/command-center/snapshot
Content-Type: application/json
```

Payload:

```json
{
  "schema_version": "command_center_snapshot_v1",
  "ts_unix": 1780916046.11,
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "source": "nanopi_ros",
  "profile": {
    "profile_id": "pdp_20260608_0001",
    "profile_version": 1,
    "mapping_version": "medical_arm_6dof_2026_06_08"
  },
  "robot_render_state": {
    "schema_version": "robot_render_state_v1",
    "urdf_asset_id": "rehab_arm_urdf_current",
    "joint_names": [
      "jian_hengxiang_joint",
      "jian_zongxiang_joint",
      "jian_xuanzhuan_joint",
      "zhou_zongxiang_joint",
      "wanbu_zongxiang_joint",
      "wanbu_hengxiang_joint"
    ],
    "positions": [0.0, 1.7453, 1.0472, 2.3562, 0.0, 0.0],
    "velocities": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "fresh": [true, true, true, true, false, false],
    "limit_clamped": [false, true, true, true, false, false]
  },
  "safety": {
    "schema_version": "safety_state_v1",
    "state": "limited",
    "motion_allowed": false,
    "control_mode": "logging_only",
    "detail": "prearm_not_ready",
    "source": "m33_can_0x322"
  },
  "wiring_health": {
    "schema_version": "wiring_health_v1",
    "overall": "degraded",
    "checks": [
      {
        "channel": "motor_3_can",
        "status": "ok",
        "fresh_ms": 35,
        "evidence": "0x330 fresh"
      },
      {
        "channel": "motor_1_wrist",
        "status": "not_wired",
        "fresh_ms": null,
        "evidence": "not installed"
      }
    ]
  },
  "model_state": {
    "schema_version": "rehab_arm_model_state_v1",
    "control_boundary": "model_suggestion_only_not_motion_permission",
    "model_results": []
  },
  "control_boundary": "telemetry_snapshot_only_not_motion_permission"
}
```

Three.js 渲染规则：

- 总控台只使用 `robot_render_state.joint_names/positions` 驱动 URDF 预览。
- URDF joint 名称必须和 `robot_render_state.joint_names` 一致。
- `limit_clamped=true` 必须在 UI 上提示为“显示/仿真限位夹紧”，不能把它当成实际标定完成。
- 缺失或 stale 的 joint 必须显示为灰色/未知，不得用 0 位姿伪装为真实反馈。

## 6. Camera Protocol

关键帧上传：

```http
POST /api/rehab-arm/v1/devices/{device_id}/camera/keyframes
Content-Type: multipart/form-data
```

Metadata:

```json
{
  "schema_version": "camera_keyframe_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "camera_id": "front_rgb",
  "ts_unix": 1780916046.11,
  "image_format": "jpg",
  "width": 1280,
  "height": 720,
  "sha256": "abc123",
  "sync_policy": "keyframe_only",
  "control_boundary": "perception_data_only_not_motor_command"
}
```

实时预览第一版只定义协商对象，不强制实现 WebRTC：

```json
{
  "schema_version": "camera_stream_offer_v1",
  "camera_id": "front_rgb",
  "transport": "webrtc_or_mjpeg",
  "max_fps": 15,
  "max_width": 1280,
  "max_height": 720,
  "control_boundary": "camera_preview_only_not_motion_permission"
}
```

## 7. Voice Protocol

语音来源可以是 App、浏览器总控台或 M55 ASR。服务器可作为 API 中转，但不得直接控制电机。

```http
POST /api/rehab-arm/v1/devices/{device_id}/voice/captures
Content-Type: multipart/form-data
```

Metadata:

```json
{
  "schema_version": "voice_capture_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "source": "app_microphone",
  "audio_format": "wav_pcm16",
  "sample_rate": 16000,
  "duration_ms": 2400,
  "language": "zh-CN",
  "session_id": "session_20260608_0001",
  "control_boundary": "voice_input_only_not_motion_permission"
}
```

语音 API 中转结果：

```json
{
  "schema_version": "voice_relay_v1",
  "transcript": "开始抬手训练",
  "intent": {
    "label": "voice_start_request",
    "confidence": 0.86
  },
  "as_model_state": {
    "schema_version": "rehab_arm_model_state_v1",
    "model_results": [
      {
        "model_id": "server_voice_asr_v1",
        "model_version": "0.1.0",
        "result_code": 1,
        "label": "voice_start_request",
        "confidence": 0.86,
        "fresh": true
      }
    ],
    "control_boundary": "model_suggestion_only_not_motion_permission"
  },
  "control_boundary": "voice_relay_only_not_motion_permission"
}
```

服务器语音结果必须落到 `rehab_arm_model_state_v1` 语义，不能新建另一套语音编号表。

## 8. VLA Protocol

VLA 输入必须是融合后的上下文，不直接消费裸 CAN 控制。

```http
POST /api/rehab-arm/v1/devices/{device_id}/vla/task-requests
Content-Type: application/json
```

Request:

```json
{
  "schema_version": "vla_task_request_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "session_id": "session_20260608_0001",
  "language_goal": "协助患者完成一次缓慢肘屈曲训练",
  "context_refs": {
    "latest_command_center_snapshot_id": "ccs_123",
    "latest_camera_keyframe_id": "cam_456",
    "active_profile_id": "pdp_20260608_0001"
  },
  "allowed_outputs": [
    "high_level_task",
    "dry_run_joint_trajectory_candidate"
  ],
  "forbidden_outputs": [
    "can_frame",
    "motor_current",
    "motor_torque",
    "raw_motor_position",
    "raw_motor_velocity",
    "m33_safety_override"
  ],
  "control_boundary": "vla_planning_request_only_not_motion_permission"
}
```

Response:

```json
{
  "schema_version": "vla_plan_candidate_v1",
  "plan_id": "vla_plan_001",
  "summary": "建议先做肘关节小幅度 dry-run 候选。",
  "candidate": {
    "type": "dry_run_joint_trajectory",
    "joint_names": ["zhou_zongxiang_joint"],
    "points": [
      {
        "positions": [0.1],
        "time_from_start_sec": 2.0
      }
    ]
  },
  "requires": [
    "mujoco_dry_run_passed",
    "m33_motion_allowed_true",
    "human_confirmation"
  ],
  "control_boundary": "vla_candidate_only_not_motion_permission"
}
```

任何 VLA candidate 进入真机前必须转换为正式 ROS `JointTrajectory`，并通过 NanoPi/M33 安全门；服务器返回 `vla_plan_candidate_v1` 本身不允许被当作真机命令。

## 9. Wiring Health Protocol

接线检测不是靠单一状态，而是综合 freshness、心跳、错误计数、温度和协议解析。

```http
GET /api/rehab-arm/v1/devices/{device_id}/wiring-health
```

Response data:

```json
{
  "schema_version": "wiring_health_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "overall": "degraded",
  "checks": [
    {
      "channel": "m33_heartbeat",
      "status": "ok",
      "fresh_ms": 120,
      "evidence": "0x321 -> 0x322"
    },
    {
      "channel": "motor_4_feedback",
      "status": "stale",
      "fresh_ms": 1200,
      "evidence": "0x331 stale bit set"
    },
    {
      "channel": "c8t6_emg_can",
      "status": "missing",
      "fresh_ms": null,
      "evidence": "no 0x7C2/0x7C3 in window"
    }
  ],
  "control_boundary": "diagnostic_only_not_motion_permission"
}
```

Status enum:

```text
ok
stale
missing
fault
not_wired
unknown
```

总控台必须把 `missing/fault/stale` 明确显示给操作者。不得因某一路接线异常自动提高力矩、电流或速度补偿。

## 10. Safety And Estop Protocol

安全状态查询：

```http
GET /api/rehab-arm/v1/devices/{device_id}/safety
```

Response data:

```json
{
  "schema_version": "safety_state_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "state": "limited",
  "motion_allowed": false,
  "control_mode": "logging_only",
  "detail": "prearm_not_ready",
  "last_m33_status_seq": 140,
  "heartbeat_age_ms": 100,
  "source": "m33_can_0x322",
  "control_boundary": "safety_status_only_not_motion_permission"
}
```

远程急停请求：

```http
POST /api/rehab-arm/v1/devices/{device_id}/estop
Content-Type: application/json
```

Request:

```json
{
  "schema_version": "estop_request_v1",
  "request_id": "estop_20260608_0001",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "source": "command_center",
  "operator_id": "operator_001",
  "reason": "operator_pressed_estop",
  "requested_action": "disable_motor_output",
  "control_boundary": "estop_request_requires_m33_ack"
}
```

Ack:

```json
{
  "schema_version": "estop_ack_v1",
  "request_id": "estop_20260608_0001",
  "accepted_by_gateway": true,
  "m33_ack": false,
  "state": "pending_m33_ack",
  "detail": "request queued to local safety path",
  "control_boundary": "not_safe_until_m33_ack"
}
```

只有 `m33_ack=true` 且 M33 safety state 确认 `emergency_stop` 或电机输出关闭后，UI 才能显示“急停已执行”。服务器或 App 发送请求成功不等于电机已经停。

## 11. App Protocol Boundary

App 是患者/治疗师近端界面，不是工程总控台。App 第一版允许：

- 查看 safety、profile、training session、关节/电机/传感摘要。
- 通过 BLE 向 M33 发 `heartbeat`、`stream:on/off`、`stop`、`mode request`、`profile confirm`、疼痛/疲劳反馈、训练开始/暂停/停止请求。
- 通过 HTTP 向服务器上传语音、标注、训练反馈和低频状态。
- 显示服务器/VLA 的建议，但必须标注“建议/待确认”。

App 禁止：

- 发 CAN frame。
- 发底层电机角度、速度、力矩、电流。
- 绕过 M33 设置 `motion_allowed=true`。
- 把语音或 VLA 输出直接变成真机运动。
- 自己维护一套和服务器/M33 不一致的模型编号表或 profile 字段。

App BLE 扩展 payload 必须沿用 [M33_M55_IPC_BLE_FOUNDATION.md](M33_M55_IPC_BLE_FOUNDATION.md) 的字段组：`safety/profile/joints/motors/sensors/model/request`。

## 12. Implementation Order For Other AI

平台仓库实现顺序建议：

1. 只做总控台只读页：设备列表、safety、wiring health、latest snapshot。
2. 加 Three.js + URDF 只读渲染，使用 `robot_render_state_v1`，不做控制。
3. 加 camera keyframe 上传和浏览。
4. 加 voice capture 中转，输出 `voice_relay_v1` 和 `rehab_arm_model_state_v1`。
5. 加 VLA request/candidate，但 candidate 只进入 dry-run。
6. 加 estop request UI，明确区分 request sent、gateway accepted、M33 acknowledged。
7. 最后才考虑把 dry-run 通过人工确认转为正式 `JointTrajectory`，且必须经过 NanoPi/M33 安全门。

本仓库 App 分支后续实现顺序建议：

1. 先适配 BLE 状态显示和 `stop/heartbeat`。
2. 再接 profile confirm、疼痛/疲劳标注。
3. 再做语音上传到服务器。
4. 不做底层控制 UI；工程调试仍使用 bench-debug 工具和明确的安全流程。
