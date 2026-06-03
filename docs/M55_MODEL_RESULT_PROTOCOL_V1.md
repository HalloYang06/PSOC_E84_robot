# M55 Model Result Protocol V1

本文定义 M55 小模型结果如何进入 M33、NanoPi、服务器/VLA 和数据集。它是旁线 `side-channel` 合同，不是运动控制协议。

## 1. 边界

- M55 只输出编号结果、置信度、语音文本、音频摘要和建议。
- M55 不直接控制电机，不发 CAN 电机帧，不写 `0x320`，不放宽 M33 限位。
- M33 可以使用 M55 结果做保守降级，例如疲劳高时降速或暂停；不能因为 M55 说“想动”就跳过限位、急停或 fresh feedback。
- NanoPi/服务器按 `schema_version`、`model_id`、`model_version` 和 `result_code` 解析语义，不允许各端写不同编号表。
- VLA 可以读取 M55 摘要作为上下文，但只能输出高层任务、分段目标或候选轨迹。

## 2. 数据流

```text
C8T6/EMG/音频/训练上下文 -> M33 -> M55
M55 -> 编号结果/置信度/语音文本 -> M33
M33 -> NanoPi -> /rehab_arm/model_state -> recorder/server/VLA
```

第一版不指定 M33 和 M55 内部 IPC，也不占用新的 CAN ID。固件确定传输帧后，需要在 `PSOC_CAN_PROTOCOL_V1.md` 增加对应帧，并保持本文 JSON 语义不变。

## 3. ROS/JSON Payload

Topic:

```text
/rehab_arm/model_state
```

Type:

```text
std_msgs/msg/String JSON
```

Payload:

```json
{
  "schema_version": "rehab_arm_model_state_v1",
  "ts_unix": 1780469632.48,
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "source": "m33_m55_bridge",
  "model_results": [
    {
      "model_id": "m55_emg_intent_v1",
      "model_version": "0.1.0",
      "result_code": 10,
      "label": "elbow_flexion_intent",
      "confidence": 0.82,
      "window_ms": 200,
      "fresh": true,
      "input_summary": {
        "emg_channels": 4,
        "joint_context": ["zhou_zongxiang_joint"]
      }
    }
  ],
  "control_boundary": "model_suggestion_only_not_motion_permission"
}
```

必需字段：

| 字段 | 说明 |
|---|---|
| `schema_version` | 固定 `rehab_arm_model_state_v1` |
| `robot_id/device_id` | 和 NanoPi/M33/服务器设备身份一致 |
| `source` | 默认 `m33_m55_bridge`；离线回放可写 `offline_replay` |
| `model_results[]` | 一个时间点内的一个或多个模型结果 |
| `control_boundary` | 固定 `model_suggestion_only_not_motion_permission` |

单个 `model_result` 必需字段：

| 字段 | 说明 |
|---|---|
| `model_id` | 例如 `m55_emg_intent_v1`、`m55_fatigue_v1`、`m55_voice_asr_v1` |
| `model_version` | 模型版本，必须进入数据集 |
| `result_code` | 小整数编号，固件、NanoPi、服务器共用 |
| `label` | NanoPi/服务器按编号表解析出的语义标签 |
| `confidence` | `0.0~1.0` |
| `fresh` | 是否是当前窗口新鲜结果 |

## 4. 第一版编号表

### `m55_emg_intent_v1`

| `result_code` | `label` | 说明 |
|---:|---|---|
| `0` | `unknown_or_rest` | 静息、未知或置信度不足 |
| `10` | `elbow_flexion_intent` | 肘屈曲意图 |
| `11` | `elbow_extension_intent` | 肘伸展意图 |
| `20` | `wrist_flexion_intent` | 腕屈曲意图 |
| `21` | `wrist_extension_intent` | 腕伸展意图 |
| `30` | `shoulder_assist_request` | 肩部辅助请求 |
| `90` | `co_contraction_or_spasm` | 共收缩、痉挛或异常肌电模式 |

### `m55_fatigue_v1`

| `result_code` | `label` | 说明 |
|---:|---|---|
| `0` | `fatigue_unknown` | 无法判断 |
| `1` | `fatigue_low` | 疲劳低 |
| `2` | `fatigue_medium` | 疲劳中 |
| `3` | `fatigue_high_reduce_assist` | 疲劳高，建议减速/降低辅助 |
| `4` | `fatigue_stop_request` | 疲劳很高，建议暂停并请求确认 |

### `m55_voice_asr_v1`

| `result_code` | `label` | 说明 |
|---:|---|---|
| `0` | `voice_none` | 无有效语音 |
| `1` | `voice_start_request` | 开始训练请求 |
| `2` | `voice_pause_request` | 暂停请求 |
| `3` | `voice_stop_request` | 停止请求 |
| `4` | `voice_pain_or_discomfort` | 疼痛/不适 |
| `5` | `voice_free_text` | 有自由文本，见 `transcript` |

## 5. 数据记录和服务器

- JSONL recorder 必须能记录 `/rehab_arm/model_state`。
- VLA/视觉数据 profile 应包含 `/rehab_arm/model_state` 和 `/rehab_arm/camera_keyframe`。
- 服务器上传可以先通过 JSONL session；后续如做实时接口，也必须复用 `rehab_arm_model_state_v1`。
- 数据集必须保留 `model_id/model_version/result_code/confidence/fresh`，否则不能复现实验。

## 6. 不能做的事

- 不得让 M55 的 `result_code` 直接映射成 `0x320`。
- 不得把 `confidence > 阈值` 当成 `motion_allowed=true`。
- 不得让 VLA 直接读取原始高频 EMG 后输出底层电机控制。
- 不得在 App、NanoPi、服务器分别维护三套编号语义。
