# Rehab Functional Roadmap

本文把康复机械臂后续功能拆成可复用模块。原则：所有 AI、语音、EMG、仿真和服务器只输出建议或候选；正式运动仍是 `JointTrajectory -> NanoPi -> M33 -> motor`，M33 是最终安全裁决。

## 1. 主线能力

| 能力 | 当前落点 | 输出 |
|---|---|---|
| 状态采集 | M33/NanoPi ROS2 | `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state` |
| M55 小模型 | M33/M55 IPC + `0x323` | `/rehab_arm/model_state` |
| 4 路 EMG 预留 | C8T6 -> M33 -> M55 | `emg_feature_window_v1`、`m55_emg_intent_v1` |
| 语音唤醒/ASR/TTS | M55 + 服务器 API relay | `voice_capture_v1`、`voice_relay_v1`、`tts_playback_request_v1` |
| MuJoCo shadow | Linux 仿真主机 | `/sim/medical_arm/joint_states`、dry-run 验证 |
| 路径规划 | 服务器/VLA + NanoPi/仿真 | `dry_run_joint_trajectory_candidate` |
| 数据/标注/训练 | NanoPi recorder + 云平台 | JSONL、dataset index、annotation queue |

## 2. 康复训练会话

新增纯数据规划模块 `rehab_session.py`，只生成 `rehab_session_plan_v1`，不发 CAN，不发布真实 ROS 运动命令。

训练模式：

- `passive_training`: 被动活动度训练，M33 限位和 therapist/operator 确认优先。
- `active_assist`: EMG/语音/VLA 提供意图，系统只给辅助候选轨迹。
- `resistance_training`: 后续用于阻力训练，必须等力矩/电流/疼痛反馈完整后再开放。
- `memory_mode`: 复现已审核 session 的轨迹，必须先在 MuJoCo 和 M33 safety gate dry-run。

固定阶段：

```text
precheck -> warmup -> assist_or_motion -> cooldown -> review
```

## 3. 4 路 EMG 预留合同

路径：

```text
C8T6 -> M33 -> M55 -> M33 -> CAN 0x323 -> NanoPi /rehab_arm/model_state
```

原始/滤波信号仍走 `/rehab_arm/sensor_state`。M55 输入窗口第一版固定：

- 4 channels
- 200 ms window
- features: `rms`、`mean_abs`、`zero_crossing`、`quality`、`contact_valid`

EMG 输出只能是 `model_suggestion_only_not_motion_permission`。例如：

- `emg_relax`
- `emg_flex_intent`
- `emg_extend_intent`
- `emg_stop_or_resist`
- `emg_contact_bad`

## 4. 语音和播报

语音链路按 [VOICE_WAKE_TTS_PORTABILITY_GUIDE.md](VOICE_WAKE_TTS_PORTABILITY_GUIDE.md)：

- M55 采集原始 PCM 或接收 M33 shared PCM。
- 唤醒词优先复用 Infineon 官方 local voice 示例、TFLite Micro `micro_speech` 和开源 `micro-wake-word`。
- 服务器总控台作为 ASR/LLM/TTS API 中转。
- 扬声器播报只反馈“收到/暂停/安全检查失败”等状态，不授权运动。

## 5. 路径规划和仿真

路径规划第一版只做候选：

```text
patient profile + joint/motor/safety + EMG/voice/VLA intent
  -> path planner
  -> MuJoCo dry-run
  -> operator review
  -> JointTrajectory candidate
  -> NanoPi
  -> M33 safety gate
```

当前开发基线见 [MAINLINE_DEVELOPMENT_GUIDE.md](MAINLINE_DEVELOPMENT_GUIDE.md)。未完成正式标定前，先使用
`medical_arm_6dof_temporary_calibration.yaml` 的“当前姿态 = 工程临时零点”策略，只做小幅 joint-space 候选和 MuJoCo dry-run。

安全职责统一放在 M33：planner、MuJoCo、平台和 App 只生成候选、审核记录或 profile；M33 才是最终执行和拒绝点。

需要逐步补：

1. 真实关节零点、方向、软限位。
2. 3 号同步轮 `motor:joint = 1:2` 的输出换算标定。
3. 4 号齿轮减速比标定。
4. 1/2 腕部 4015 电机接线、反馈和限位。
5. MuJoCo MJCF 质量、惯量、阻尼、摩擦、末端负载和人体接触边界。
6. 患者 ROM/profile 到 planner 的约束映射。

## 6. 云平台隔离

云服务器/AI 合作平台接入必须先实现租户隔离：

- `tenant_id`
- `workspace_id`
- `user_id`
- `role`
- `device_id`
- `patient_id/profile_id`
- `session_id/dataset_id`

不同账号、不同团队、不同患者的数据默认不可见。平台 WebSocket、对象存储、VLA 上下文、ASR/TTS 中转和训练数据集都必须带这些边界。

## 7. 下一步最小任务

1. NanoPi 增加只读 voice gateway 上传节点，把 `voice_capture_v1`/`voice_relay_v1` 送总控台。
2. M55 用官方/开源 wake-word 模型替换当前验证模型，同时保留 `model_manager` slot 和 `0x323` 出口。
3. C8T6 上电后先把 4 路 EMG 原始质量指标进 `/rehab_arm/sensor_state`。
4. 用 `build_rehab_session_plan` 生成 dry-run 训练计划，交给 MuJoCo shadow 验证。
