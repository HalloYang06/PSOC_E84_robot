# Platform AI Prompt: Rehab Arm VLA L/V/A HTTP Contract

把下面这段发给平台仓库的 AI，要求它只在现有“医疗康复机械臂设备总控台模型中转站”基础上补接口，不要另造一套平台。

```text
你负责云端 AI 协作平台，不改机械臂固件仓库。请按医疗康复机械臂当前主线实现 VLA L/V/A HTTP 对接：

1. M55 语音上云主链路走 WiFi HTTP，不走 CAN。
   - Endpoint: POST /api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay
   - input_type 固定支持 vla_language_from_voice
   - 支持 JSON 或 multipart：metadata=voice_capture_v1，file=PCM/WAV/OPUS 原始语音。
   - M55 只使用平台 relay token，不能看到或保存厂商 API key。

2. 模型中转返回必须先分类：
   - daily_chat：日常聊天，只返回 operator_facing_reply/TTS，不进入 VLA-A。
   - vla_command：康复指令，输出 vla_language_context_v1，作为 VLA 的 L。
   - none：噪声/空输入/低置信度，提示用户重说。

3. NanoPi 摄像头/视觉形成 V：
   - 复用现有总控台摄像头/关键帧能力。
   - 输出 vla_vision_context_v1，包含场景摘要、患者姿态/可见性、环境约束。

4. VLA 融合 L + V + robot context 后产生 A：
   - 输出 server_to_nanopi_high_level_command_v1。
   - 只能是高层动作意图、训练请求、暂停/停止/辅助等级调整请求。
   - 必须包含 source_refs.vla_language_context_id、source_refs.vla_vision_context_id、robot_context_snapshot_id。
   - 必须包含 requires_before_motion:
     active_profile_loaded, wiring_state_checked, safety_state_fresh,
     mujoco_dry_run_required, operator_confirmation_required, m33_final_gate_required.

5. 禁止平台输出或下发：
   - can_frame, can_frames
   - motor_current, motor_torque, motor_velocity
   - raw_motor_position, raw_motor_velocity
   - joint_trajectory, trajectory_points
   - m33_safety_override, motion_allowed_override, motion_permission_granted
   - direct_motor_command

6. 平台下发给 NanoPi 的 A payload 示例：
{
  "schema_version": "server_to_nanopi_high_level_command_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "command_id": "srv_action_001",
  "source": "server_vla_action",
  "source_refs": {
    "vla_language_context_id": "lang_ctx_001",
    "vla_vision_context_id": "vision_ctx_001",
    "robot_context_snapshot_id": "ccs_001"
  },
  "action": {
    "kind": "rehab_training_request",
    "label": "assist_slow_arm_raise",
    "natural_language": "患者请求开始缓慢抬手训练，先进入仿真和安全检查。",
    "priority": "normal"
  },
  "requires_before_motion": [
    "active_profile_loaded",
    "wiring_state_checked",
    "safety_state_fresh",
    "mujoco_dry_run_required",
    "operator_confirmation_required",
    "m33_final_gate_required"
  ],
  "control_boundary": "server_action_high_level_only_not_motion_permission"
}

7. 平台实现后，把一个真实返回样例交给机械臂仓库用：
python -m rehab_arm_psoc_bridge.check_server_action_command --payload server_action.json --queue-item --pretty

通过后才允许进入 vla_candidate_gate -> mujoco_dry_run_review -> operator_review -> m33_safety_gate_preparation。HTTP 200、模型回复、平台按钮都不是运动许可。
```
