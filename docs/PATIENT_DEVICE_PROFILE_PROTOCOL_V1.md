# Patient Device Profile Protocol V1

本文定义平台、App、NanoPi、M33、M55、仿真主机和后续 VLA 共同遵守的患者/设备运行配置协议。目标是让不同入口看到同一份配置、同一套版本号和同一套安全边界，避免 App、平台、固件各写一套导致临床风险。

## 1. 设计原则

- **一份 active profile**：同一台设备同一时刻只能有一个 active patient device profile。
- **M33 最终裁决**：平台、App、NanoPi、M55、VLA 都只能提出请求、参数或建议；是否允许运动由 M33 安全状态机决定。
- **机器安全和患者偏好分层**：机器绝对限位、急停、通信超时、故障保护是设备安全底线；患者 ROM、限速、训练模式是会话限制，不能放宽设备底线。
- **单机器人坐标系优先**：第一版只使用标准 `robot_joint_angle`，不建立患者相对坐标系；训练时可派生 `rom_percent`。
- **配置版本进入数据集**：每条训练/标注数据必须记录 `profile_id`、`profile_version`、`session_id`，否则无法复现实验。
- **VLA 不直接控制**：VLA 只输出任务目标或计划，不能写 M33 安全参数，不能发 CAN、速度、力矩或裸电机位置。
- **模型建议不等于命令**：M55 的意图、疲劳、辅助等级输出是 `suggestion`，必须由 M33/NanoPi/App 显示或审核后应用。

## 2. 角色和权限

| 角色 | 可写 | 可读 | 禁止 |
|---|---|---|---|
| 平台 | patient profile、训练计划、标注协议、模型版本、设备绑定 | 全部非隐私脱敏状态、数据资产、profile 历史 | 直接发 CAN、绕过 M33 运动 |
| App | 近端会话参数、患者反馈、疼痛/疲劳标注、开始/暂停/停止/急停请求 | active profile、安全状态、训练状态、模型摘要 | 直接发电机底层命令、私自维护另一套 profile |
| NanoPi | 拉取/缓存 active profile，转发安全子集到 M33，上传状态和数据 | active profile、M33 状态、ROS 状态、摄像头元数据 | 自行放宽 M33 限制、正式路径直控电机 |
| M33 | 执行安全子集、最终限幅、急停、heartbeat timeout、故障状态 | 安全子集、电机/传感/M55 建议 | 存储患者隐私、接受未签名/过期 profile 执行动作 |
| M55 | 模型输入配置、模型版本、阈值、推理结果 | M33 汇总状态、传感特征、profile 模型配置 | 直接控制电机或修改 M33 限位 |
| 仿真主机 | 仿真 profile、训练/规划结果、数据质量报告 | active profile、URDF、rosbag、状态 | 跳过 M33 审核直接驱动真机 |
| 服务器/VLA | 任务计划、数据管理、模型管理 | 设备状态、图像、历史数据、标注 | 实时闭环控制、底层电机命令 |

## 3. 数据分层

```text
Device Safety Profile
  设备本体绝对限制，机器出厂/装机标定后稳定存在。

Patient Motion Profile
  不同患者/不同疗程的 ROM、限速、训练模式、疼痛/疲劳策略。

Session Runtime Profile
  本次训练会话的 active profile 版本、开始时间、临时暂停/降级状态。

Model Runtime Profile
  M55/服务器模型版本、阈值、输入输出字段和推理频率。
```

第一版不引入患者相对坐标系。统一使用：

```text
raw_motor_position -> machine_zero -> robot_joint_angle
robot_joint_angle + patient_rom_limits -> rom_percent
```

如果某类电机官方协议已经直接给出可信输出侧绝对角度，`raw_motor_position` 可以直接作为 `robot_joint_angle` 的来源，`machine_zero` 只作为上位机/平台标注的显示和数据集字段存在，不要求 M33 重新维护一套零点数据库。M33 在这种情况下只执行安全子集中的限位、限速、限流、急停和通信超时裁决。

`rom_percent` 是训练特征，不是新的控制坐标系：

```text
rom_percent = (robot_joint_angle - patient_min) / (patient_max - patient_min)
```

## 4. Patient Device Profile JSON

平台和 App 编辑的是同一份 JSON。NanoPi 拉取完整 profile，M33 只接收安全子集，M55 只接收模型子集。

profile 进入 active 状态、同步到 NanoPi、拆分为 M33/M55 子集或进入数据集前，必须先通过 `validate_patient_profile.py` 离线质量门。第一版校验只做保守安全检查：

- `schema_version=patient_device_profile_v1`。
- `profile_id/profile_version/profile_status/robot_id/device_id/patient_ref.patient_id` 必须存在。
- 患者 ROM 必须在设备绝对 joint limits 内，且不能超过第一版默认设备包络 `-60° ~ +60°`。
- 患者限速必须大于 `0`，不能超过 `30 deg/s`，也不能超过设备绝对限速。
- `training_mode` 只能是 `passive_training`、`active_assist`、`resistance_training` 或 `memory_mode`。
- 急停策略必须是 `disable_motor_output`，并且 `fault_latch=true`。
- VLA 权限只能是 `disabled`、`suggest_only` 或 `plan_only`，并且必须明确禁止 `can_frame`、`torque_command`、`current_command`、`velocity_command`、`raw_motor_position`。
- M55 模型配置不能包含 `direct_motor_control`。

校验器只输出 `patient_device_profile_validation_v1` 报告，不写 profile，不下发 M33，不发 ROS/CAN，不授予运动许可。

新患者、新设备或平台/App 第一次建档时，先用当前电机配置表生成保守草稿，再由治疗师/工程师在平台或 App 里审核调整：

```bash
ros2 run rehab_arm_psoc_bridge build_patient_profile_template.py \
  --profile-id pdp_20260527_0001 \
  --robot-id rehab_arm_alpha \
  --device-id nanopi_m5_001 \
  --patient-id patient_001 \
  --validate \
  --pretty \
  --output patient_device_profile_template.json
```

模板默认 `profile_status=draft`、患者 ROM 为每关节 `[-10°, +10°]`、患者限速 `5 deg/s`、急停策略为 `disable_motor_output`。它只是建档起点，不是临床批准，也不会下发 M33 或授予运动权限。

任何 profile 进入 M33、App BLE 或 NanoPi 缓存前，必须先通过发布闸门：

```bash
ros2 run rehab_arm_psoc_bridge check_patient_profile_release_gate.py \
  patient_device_profile.json \
  --target m33 \
  --pretty
```

闸门规则：

- `--target m33`：profile 必须 `active`，校验通过，且能导出 `m33_safety_profile_v1`。
- `--target app_ble`：profile 必须能构造 `ble_m33_safety_package_v1`，并提供 `approved_by/approved_at/expires_at`。
- `--target nanopi_cache`：profile 必须 `approved` 或 `active`，用于本地缓存、仿真、数据采集上下文。
- 闸门只输出 `patient_profile_release_gate_v1` 报告，不连接 BLE，不发 ROS/CAN，不写 M33。

```json
{
  "schema_version": "patient_device_profile_v1",
  "profile_id": "pdp_20260526_0001",
  "profile_version": 12,
  "profile_status": "active",
  "robot_id": "rehab_arm_alpha",
  "device_id": "nanopi_m5_001",
  "patient_ref": {
    "patient_id": "patient_001",
    "side": "right",
    "affected_side": "right",
    "privacy_level": "pseudonymized"
  },
  "device_safety": {
    "machine_calibration_id": "machine_calib_alpha_001",
    "requires_homing": true,
    "absolute_joint_limits_deg": {
      "shoulder_lift_joint": [-60.0, 60.0],
      "elbow_lift_joint": [-60.0, 60.0],
      "shoulder_abduction_joint": [-60.0, 60.0],
      "upper_arm_rotation_joint": [-60.0, 60.0],
      "forearm_rotation_joint": [-60.0, 60.0]
    },
    "absolute_velocity_limits_dps": {
      "shoulder_lift_joint": 10.0,
      "elbow_lift_joint": 10.0,
      "shoulder_abduction_joint": 10.0,
      "upper_arm_rotation_joint": 10.0,
      "forearm_rotation_joint": 10.0
    },
    "absolute_acceleration_limits_dps2": {
      "default": 40.0
    },
    "absolute_torque_current_limits": {
      "default_current_a": 5.0
    },
    "emergency_policy": {
      "estop_action": "disable_motor_output",
      "heartbeat_timeout_ms": 2500,
      "fault_latch": true
    }
  },
  "patient_motion": {
    "patient_rom_limits_deg": {
      "shoulder_lift_joint": [-10.0, 35.0],
      "elbow_lift_joint": [0.0, 50.0],
      "shoulder_abduction_joint": [-5.0, 30.0],
      "upper_arm_rotation_joint": [-20.0, 20.0],
      "forearm_rotation_joint": [-30.0, 30.0]
    },
    "patient_velocity_limits_dps": {
      "default": 6.0
    },
    "patient_acceleration_limits_dps2": {
      "default": 20.0
    },
    "forbidden_zones_deg": [
      {
        "joint_name": "shoulder_abduction_joint",
        "range": [30.0, 60.0],
        "reason": "postoperative_restriction"
      }
    ],
    "warmup_profile": {
      "enabled": true,
      "initial_rom_scale": 0.5,
      "ramp_seconds": 120
    },
    "assist_level": 0.35,
    "training_mode": "active_assist",
    "session_duration_limit_s": 1200,
    "repetition_limit": 30,
    "pain_stop_threshold": 3,
    "fatigue_policy": {
      "fatigue_score_warn": 0.65,
      "fatigue_score_reduce_assist": 0.75,
      "fatigue_score_stop": 0.9,
      "on_warn": "reduce_speed",
      "on_stop": "pause_and_request_confirmation"
    },
    "spasticity_policy": {
      "sensitivity": 0.5,
      "on_detected": "stop_and_hold_safe"
    }
  },
  "model_runtime": {
    "m55_models": {
      "intent_model": {
        "model_id": "m55_intent_v1",
        "version": "0.1.0",
        "input_topics": ["emg_features", "imu_features", "robot_joint_state"],
        "output_topic": "m55_model_result",
        "frequency_hz": 50,
        "confidence_threshold": 0.7
      },
      "fatigue_model": {
        "model_id": "m55_fatigue_v1",
        "version": "0.1.0",
        "frequency_hz": 10,
        "fatigue_score_range": [0.0, 1.0]
      }
    },
    "server_models": {
      "vla_policy": {
        "permission_level": "suggest_only",
        "allowed_task_types": ["describe_scene", "suggest_training_task", "plan_complex_task"],
        "forbidden_outputs": ["can_frame", "torque_command", "current_command", "velocity_command", "raw_motor_position"]
      }
    }
  },
  "training_and_labeling": {
    "task_plan_id": "task_plan_reach_v1",
    "task_labels": ["reach_forward", "return_home"],
    "labeling_protocol_id": "label_protocol_emg_fatigue_v1",
    "required_labels": ["pain_score", "fatigue_score", "intent_label"],
    "data_capture": {
      "record_motor_state": true,
      "record_sensor_state": true,
      "record_camera_keyframes": true,
      "record_model_outputs": true
    }
  },
  "sync": {
    "created_by": "therapist_or_engineer_id",
    "approved_by": "clinician_id",
    "approved_at": "2026-05-26T10:00:00+08:00",
    "active_since": "2026-05-26T10:05:00+08:00",
    "revision_note": "Initial right-arm active-assist profile"
  }
}
```

## 5. M33 安全子集

NanoPi 下发给 M33 的不是完整 patient profile，而是通过平台/App/NanoPi 校验后的安全子集。

```json
{
  "schema_version": "m33_safety_profile_v1",
  "profile_id": "pdp_20260526_0001",
  "profile_version": 12,
  "machine_calibration_id": "machine_calib_alpha_001",
  "requires_homing": true,
  "homing_state_required": "homed",
  "joint_limits_deg": {
    "shoulder_lift_joint": [-10.0, 35.0]
  },
  "velocity_limits_dps": {
    "shoulder_lift_joint": 6.0
  },
  "acceleration_limits_dps2": {
    "shoulder_lift_joint": 20.0
  },
  "torque_current_limits": {
    "shoulder_lift_joint": {
      "current_a": 3.0
    }
  },
  "mode_permission": {
    "passive_training": true,
    "active_assist": true,
    "resistance_training": false,
    "vla_task_execution": false
  },
  "emergency_policy": {
    "estop_action": "disable_motor_output",
    "fault_latch": true,
    "heartbeat_timeout_ms": 2500
  }
}
```

M33 合并限制时必须取更严格值：

```text
effective_min = max(device_absolute_min, patient_min)
effective_max = min(device_absolute_max, patient_max)
effective_velocity = min(device_absolute_velocity, patient_velocity)
effective_acceleration = min(device_absolute_acceleration, patient_acceleration)
effective_current = min(device_absolute_current, patient_current)
```

如果 profile 缺失、版本过期、校验失败、homing 未完成或 M33 heartbeat 超时，M33 必须拒绝 formal target。

当前仓库提供 `export_m33_safety_subset.py` 作为 dry-run 导出工具，用于平台/App/NanoPi 和固件开发者审查最终会给 M33 的安全子集：

```bash
ros2 run rehab_arm_psoc_bridge export_m33_safety_subset.py \
  /path/to/patient_device_profile.json \
  --output /path/to/m33_safety_profile.json \
  --pretty
```

该工具必须先通过 `validate_patient_profile.py`，再输出 `m33_safety_profile_v1`。它只生成 JSON，不下发 M33，不发 CAN，也不授予运动许可。正式下发协议后续必须再加入签名/版本/时效检查和 M33 端解析验证。

## 6. M55 模型协议

M55 模型只输出建议和状态，不直接控制电机。M55 输出给 M33/App/NanoPi 的统一结构：

```json
{
  "schema_version": "m55_model_result_v1",
  "profile_id": "pdp_20260526_0001",
  "profile_version": 12,
  "session_id": "session_20260526_0001",
  "timestamp_ms": 12345678,
  "source": "m55",
  "models": [
    {
      "model_id": "m55_intent_v1",
      "version": "0.1.0",
      "output": {
        "intent": "reach_forward",
        "confidence": 0.82
      }
    },
    {
      "model_id": "m55_fatigue_v1",
      "version": "0.1.0",
      "output": {
        "fatigue_score": 0.42,
        "fatigue_level": "normal"
      }
    }
  ],
  "suggestions": {
    "assist_level_delta": 0.05,
    "speed_scale": 0.9,
    "safety_action": "none"
  },
  "safety_note": "suggestion_only_m33_must_decide"
}
```

M33 可使用 M55 输出做降级，例如疲劳过高时降低速度或暂停；但 M55 不能放宽限位、限速、力矩/电流限制。

## 7. App 和平台同步

### 7.1 同步规则

- 平台是长期存储和审计源。
- App 可以离线缓存，但上线后必须和服务器同步。
- 同一设备同一时间只能绑定一个 `active profile_id + profile_version`。
- App 或平台修改 profile 后必须生成新 `profile_version`，不能原地覆盖。
- NanoPi 执行动作前必须知道当前 active profile 版本。
- M33 状态应回报当前执行的 `profile_version`，供 App/平台确认。

### 7.2 双监控和双控制边界

第一版预留 App 和平台同时监控、同时提出控制请求，但控制权分层，不能互相绕过：

| 入口 | 监控内容 | 可发请求 | 禁止 |
|---|---|---|---|
| App BLE | 近端安全状态、训练进度、电机/传感摘要、M55 模型摘要、告警 | 开始、暂停、停止、急停请求、模式切换、患者反馈、疼痛/疲劳标注、本地会话参数草案 | 直接发 CAN、直接写电机目标、绕过 M33 限位 |
| 平台/服务器 | 多设备在线、profile 版本、数据质量、历史 session、摄像头关键帧、模型/标注/报告 | profile draft、训练计划、高层任务、远程暂停/停止请求、参数变更审批、数据采集/标注任务 | 实时闭环控制、直接急停依赖、直接发底层轨迹/CAN |
| NanoPi | ROS 状态、M33 状态、摄像头、数据上传、仿真/规划桥接 | 转发已审核 profile 安全子集、发送标准 JointTrajectory 片段、上传状态 | 自行放宽 M33 限制、正式路径直控电机 |
| M33 | 最终安全状态、电机和传感汇总、profile 安全子集版本 | 接受或拒绝请求、执行限幅后控制、进入急停/故障/受限 | 存储患者隐私、接受未审核 profile 放宽安全 |

冲突时按安全优先处理：

```text
硬件急停 / M33 fault
  > App 近端 stop/pause/estop request
  > 平台远程 stop/pause request
  > active profile 安全限制
  > NanoPi/仿真/规划轨迹
  > VLA 高层任务
```

App 和平台都可以显示“控制请求已提交”，但只有 M33 回报 `motion_allowed=true` 且 detail 为安全通过时，界面才能显示为“执行中”。平台远程链路延迟和断网都不得影响本地急停、M33 安全状态机和 App 近端 BLE 停止请求。

### 7.3 冲突处理

| 场景 | 处理 |
|---|---|
| App 和平台同时编辑 | 服务器创建两个 draft，要求人工选择，不自动合并安全字段 |
| NanoPi 离线 | 使用最后缓存的 approved profile，但 App/平台必须显示 `offline_cached_profile` |
| 服务器不可达 | 本地急停和 M33 安全继续有效；不允许下载新 VLA 任务 |
| profile version 不一致 | NanoPi/M33 拒绝新运动，进入 `limited/profile_version_mismatch` |
| 患者未选择 | 禁止开始训练，只允许设备自检 |

### 7.4 Profile 变更审查

平台/App 在把 draft profile 提交审核前，应先运行变更审查：

```bash
ros2 run rehab_arm_psoc_bridge review_patient_profile_change.py \
  /path/to/active_profile.json \
  /path/to/draft_profile.json \
  --pretty
```

该工具输出 `patient_device_profile_change_report_v1`，用于提示：

- 新 profile version 没有递增。
- `robot_id/device_id/patient_id` 和旧 active profile 不一致。
- 患者 ROM 被放宽。
- 患者限速被提高。
- `training_mode` 变化。

这些提示不是自动拒绝所有变更；ROM 放宽和限速提高可能是临床上合理的，但必须在平台/App 上显式展示并经过人工确认。

## 8. NanoPi/ROS 数据字段

NanoPi 发布和上传的数据必须包含 profile 上下文：

App 的实时 profile 安全参数链路是 BLE 直连 M33，不依赖 NanoPi：

```text
平台/医生审批 profile
  -> App 同步 approved/active profile
  -> App 构造 ble_m33_safety_package_v1
  -> App BLE 写入 M33
  -> M33 校验 device_id/profile_version/expires_at/signature/safety limits
  -> M33 本地安全状态机最终裁决
```

当前仓库仅提供 `build_ble_m33_safety_package.py` dry-run 工具生成 JSON 草案。它不会进行蓝牙连接，也不会下发 M33。NanoPi 可以读取同一 profile/package 作为 ROS、仿真、数据采集和上传上下文，但不能成为 App BLE 生效的唯一通道。

```json
{
  "schema_version": "rehab_arm_runtime_state_v1",
  "robot_id": "rehab_arm_alpha",
  "device_id": "nanopi_m5_001",
  "profile_id": "pdp_20260526_0001",
  "profile_version": 12,
  "session_id": "session_20260526_0001",
  "machine_calibration_id": "machine_calib_alpha_001",
  "homing_state": "homed",
  "safety_state": "ok",
  "motion_allowed": true,
  "joint_state": [
    {
      "joint_name": "shoulder_lift_joint",
      "robot_joint_angle_deg": 12.5,
      "velocity_dps": 2.0,
      "rom_percent": 0.5,
      "limit_source": "patient_motion_profile"
    }
  ]
}
```

ROS topic 建议：

| Topic | 类型 | 说明 |
|---|---|---|
| `/joint_states` | `sensor_msgs/JointState` | 标准机器人坐标系 |
| `/rehab_arm/safety_state` | JSON String | M33 安全状态、profile version、homing 状态 |
| `/rehab_arm/patient_profile_state` | JSON String | 当前 active profile 摘要 |
| `/rehab_arm/model_state` | JSON String | M55/服务器模型输出摘要 |
| `/rehab_arm/session_event` | JSON String | 开始、暂停、疼痛、疲劳、标注事件 |

## 9. VLA 和复杂任务边界

VLA 可以使用：

- NanoPi 摄像头关键帧或深度图摘要。
- 当前 `robot_joint_state`。
- active profile 的允许任务类型、患者 ROM、疲劳/疼痛状态。
- 历史训练数据和标注。

VLA 输出必须是高层任务：

```json
{
  "schema_version": "vla_task_plan_v1",
  "task_id": "task_001",
  "profile_id": "pdp_20260526_0001",
  "profile_version": 12,
  "goal": "move_occluder_then_reach_target",
  "steps": [
    {
      "type": "planner_request",
      "description": "move blocking object to safe side"
    },
    {
      "type": "planner_request",
      "description": "reach target cup"
    }
  ],
  "forbidden_outputs": ["can_frame", "joint_torque", "raw_motor_position"]
}
```

任务规划器或仿真主机把 VLA 任务转换成候选 `JointTrajectory`，先仿真，再由 NanoPi 发送给 M33，M33 最终裁决。

## 10. 数据采集和训练影响

每条数据必须记录：

- `profile_id`
- `profile_version`
- `session_id`
- `machine_calibration_id`
- `homing_state`
- `robot_joint_angle`
- `rom_percent`
- `assist_level`
- `training_mode`
- `m55_model_versions`
- `vla_model_version`，如果使用 VLA

模型训练建议：

| 模型 | 输入优先级 |
|---|---|
| 仿真/运动规划 | `robot_joint_angle`、URDF、机器标定 |
| EMG 意图 | EMG 特征、IMU、`robot_joint_angle`、`rom_percent`、训练模式 |
| 疲劳检测 | EMG/心率/运动时长、`rom_percent`、assist level、患者 ROM |
| VLA grounding | 摄像头/深度、任务标签、机器人状态、profile 限制摘要 |

第一阶段不强制建患者相对坐标系；如果后续跨患者模型泛化差，再引入 `patient_relative_angle`，但必须作为 V2 协议显式升级。

## 11. 状态枚举

### 11.1 Profile 状态

```text
draft
pending_review
approved
active
archived
rejected
```

### 11.2 Homing 状态

```text
unknown
required
in_progress
homed
failed
bench_runtime_zero
```

`bench_runtime_zero` 只能用于未装机台架，不允许穿戴训练。

M33 第一版不负责零点标注，也不提供 session zero 作为正式接口。上位机、平台和 App 共同维护机械零点、患者 ROM、患者限速、训练模式和标注元数据；M33 只接收审核后的安全限制子集并做最终裁决。若后续确实需要台架零点排故，应另建显式 debug 工具，不进入正式协议。

### 11.3 Safety 状态

```text
ok
limited
emergency_stop
fault
profile_mismatch
homing_required
model_suggestion_rejected
```

## 12. 第一阶段实现范围

第一阶段只实现最小闭环：

1. 平台/App 共用 Patient Device Profile JSON。
2. NanoPi 能显示/缓存 active profile，并把安全子集转换给 M33。
3. M33 执行 joint limit、velocity limit、current limit、homing/profile version gate。
4. M55 输出 `m55_model_result_v1`，只做建议。
5. 数据采集记录 profile/session/model version。
6. VLA 只读 profile 限制摘要，只输出任务计划。

暂不实现：

- 自动云端实时闭环控制。
- 患者相对坐标系。
- M55 直接调节 M33 限位。
- VLA 直接发底层轨迹或 CAN。
- App/平台直接修改 M33 Flash。
