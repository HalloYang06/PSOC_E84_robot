# M55 Small Model Deployment Guide

本文按当前 GitHub `M55` 分支的 WiFi/AI 工程来部署小模型。不要另起工程，也不要绕开现有 `model_manager`、`wake_word_detector`、`voice_service` 和 `m33_m55_comm`。

## 1. 当前工程基线

M55 工程对应：

```bash
git clone -b M55 git@github.com:ChillAmnesiac/Medical-Rehabilitation-Manipulator.git wifi
```

当前本地可查证实现：

| 文件 | 状态 |
|---|---|
| `applications/model_manager.h/.cpp` | 多 slot TFLite Micro 管理器，slot 包含 wake word、VAD、ASR frontend、IMU、EMG、fusion。 |
| `applications/wake_word_detector.h/.cpp` | 独立 wake word TFLM 推理，MFCC 输入，输出置信度。 |
| `applications/wake_word_model_data.h` | 已转换成 C array 的模型数据。 |
| `applications/voice_service.c` | M33 PCM 输入、wake 检测、Baidu ASR/TTS、WebSocket、ASR 文本回 M33。 |
| `applications/m33_m55_comm.h/.c` | M55 侧 MTB-IPC queue 与共享 PCM。 |
| `packages/TensorflowLiteMicro-latest` | RT-Thread package，包含官方 TFLite Micro、microfrontend、CMSIS-NN 相关源码。 |

## 2. 官方/现有路径

第一版小模型按 TFLite Micro 路线走：

```text
训练/导出模型
  -> int8 quantized .tflite
  -> xxd -i 转 C array
  -> 放入 M55 工程的 model_data.h/.cc
  -> model_manager_load_tflm_model()
  -> model_manager_run_*()
  -> m33_m55_comm_publish(MSG_TYPE_AI_INFERENCE_RESP)
  -> M33 -> NanoPi -> /rehab_arm/model_state
```

当前 `packages/TensorflowLiteMicro-latest/docs/user-guide.md` 也采用同一路径：量化 `.tflite` 后用 `xxd -i converted_model.tflite > model_data.cc` 转成 C 数组。后续如果使用 Infineon DeepCraft/官方工具生成模型，也必须落到当前 M55 工程的 TFLM/模型 slot/IPC 出口，不要绕过现有主线。

## 3. EMG 小模型建议部署顺序

4 路 EMG 不建议第一天就上复杂 VLA。按以下顺序补：

1. 先在 M33/C8T6 侧确认 4 路 EMG 采样、时间戳、通道顺序、单位和丢包计数。
2. M33 做窗口摘要：RMS、MAV、ZC、SSC、WL、质量标志、饱和/脱落检测。
3. M33 通过 `MSG_TYPE_SENSOR_SNAPSHOT` 或 `MSG_TYPE_SENSOR_STREAM` 发给 M55。
4. M55 在 `MODEL_SLOT_EMG` 跑 int8 TFLM 或先跑规则模型。
5. M55 输出 `MSG_TYPE_AI_INFERENCE_RESP`，字段映射到 `m55_emg_intent_v1`、`m55_fatigue_v1` 或 `m55_quality_v1`。
6. M33 绑定安全状态后经 CAN 汇总给 NanoPi。
7. NanoPi 发布 `/rehab_arm/model_state`，服务器/VLA 只当上下文，不当运动许可。

## 4. 最小模型输出

M55 小模型第一版只输出低频结果：

| 输出 | 建议频率 | 用途 |
|---|---:|---|
| `m55_emg_intent_v1` | 2-10 Hz | 肘/腕/肩意图编号和置信度。 |
| `m55_fatigue_v1` | 1-2 Hz | 疲劳等级，M33 可保守降速或暂停。 |
| `m55_quality_v1` | 1-5 Hz | 电极脱落、饱和、噪声、共收缩异常。 |
| `m55_voice_asr_v1` | 事件触发 | 语音文本或 start/pause/stop/pain 请求。 |
| `m55_wake_word_v1` | 事件触发/高置信 | 当前上板验证小模型：M55 wake-word 结果经 `0x323` 到 NanoPi。 |

所有结果都必须带：

```text
schema_version/model_id/model_version/result_code/confidence/fresh/window_ms
control_boundary = model_suggestion_only_not_motion_permission
```

## 5. 编译和烧录检查

在 RT-Thread Studio 中：

1. 打开 GitHub `M55` 分支对应的 `wifi` 工程。
2. 确认 `packages/TensorflowLiteMicro-latest` 存在。
3. 确认 `.config` 启用 M55、WiFi、TFLM、C++ 支持和需要的 heap。
4. 替换或新增模型 C array，例如 `applications/emg_model_data.h/.cc`。
5. 在 `voice_service` 或新的 M55 模型任务中调用：

```c
model_manager_init();
model_manager_configure_slot(MODEL_SLOT_EMG, &slot_cfg);
model_manager_load_tflm_model(MODEL_SLOT_EMG, emg_model_tflite, emg_model_tflite_len);
```

6. 推理完成后填 `m33_m55_message_t`，用 `m33_m55_comm_publish()` 发回 M33。当前已提供模块化示例：
   - M55：`applications/model_result_publisher.c` 发布 `MSG_TYPE_AI_INFERENCE_RESP`。
   - M33：`applications/m33/m55_model_bridge.c` 消费结果并调用 `control_publish_m55_model_result()`。
   - NanoPi：`m33_model_status.py` 解析 `0x323` 并发布 `/rehab_arm/model_state`。
7. 烧录顺序仍是 Secure M33 -> M33 -> M55。

本轮代码只准备固件和 NanoPi 地基；真正上板需要你烧录 M33 和 M55 后再验收。

## 6. 上板验证

串口日志通过以下关键字判断：

| 阶段 | 期望日志 |
|---|---|
| M55 启动 | `It's cortex-m55` |
| IPC | `[m33_m55_comm] ready on CM55` 或 `attached queues on CM55` |
| 语音服务 | `[voice_service] initialized`、`wake detector ready=1` |
| TFLM | `tflm slot0 ready=...` 或模型 slot info |
| M33 收到 | M33 消费 `MSG_TYPE_AI_INFERENCE_RESP` 或 `MSG_TYPE_ASR_TEXT` 后输出绑定日志 |
| CAN 汇总 | NanoPi candump 看到 `0x323#B5...` |
| NanoPi 收到 | `/rehab_arm/model_state` 出现 `rehab_arm_model_state_v1` JSON |

如果 M55 先启动而 M33 尚未创建 IPC，M55 现有代码会 retry attach。这不是错误；等 M33 ready 后应看到 attach 成功。

## 7. 不要做

- 不要直接从 M55 发 CAN 电机帧。
- 不要让 M55 WiFi 直接给服务器下发运动命令。
- 不要把原始 500-1000 Hz EMG 全量塞给 VLA 做实时控制。
- 不要让 `result_code` 直接映射成 `0x320`。
- 不要替换掉 `model_manager` 后又写一套模型 runner，除非先在本文和架构合同中说明迁移原因。
