# Voice Wake, ASR Relay, and Speaker Playback Portability Guide

本文固定医疗康复机械臂的语音地基：M55 负责板端音频采集、唤醒词、小模型和低频语义事件；服务器总控台作为 LLM/ASR/TTS API 中转；扬声器播报只反馈状态，不授权运动。

## 1. 优先级

1. 官方硬件示例优先：先看 Infineon PSOC Edge local voice 示例，复用 PDM/I2S/codec/CM33+CM55 工程结构和音频管线。
2. 官方 CM55 local voice 优先：正式 wake/ASR 地基先迁移 `PDM microphone -> AFE -> Voice Assistant inferencing -> control_task map_id -> I2S speaker`，不要复活此前失败的自写 wake 主路径。
3. 官方 TinyML 示例作为最小 fallback：如果 DeepCraft/Voice Assistant 训练或授权暂时不可用，再参考 TensorFlow Lite Micro `micro_speech` 做最小关键词验证。
4. 开源模型作为可替换 fallback：自定义唤醒词再评估 OHF/ESPHome `micro-wake-word` 和现成 `.tflite` 模型仓库。
4. 云 ASR/TTS 只做可选 API 中转：不要把 Baidu/OpenAI/其他云接口写成固件唯一依赖。

参考源：

- Infineon [`mtb-example-psoc-edge-mains-powered-local-voice`](https://github.com/Infineon/mtb-example-psoc-edge-mains-powered-local-voice): PSoC Edge E84 本地语音、CM33/CM55、PDM/I2S、扬声器和 DEEPCRAFT 语音管线示例。
- TensorFlow Lite Micro [`micro_speech`](https://github.com/tensorflow/tflite-micro/tree/main/tensorflow/lite/micro/examples/micro_speech): 官方微控制器语音关键词示例，展示 16 kHz 音频、特征、TFLM interpreter、C array 模型和持续推理。
- OHF/ESPHome [`micro-wake-word`](https://github.com/OHF-Voice/micro-wake-word): 开源自定义唤醒词训练框架和模型分发，适合先做可替换 wake-word slot。

## 2. 本项目固定链路

```text
M55 official local voice audio path
  -> PDM microphone ISR / 10 ms PCM frames
  -> audio_feed_interface
  -> DEEPCRAFT AFE
  -> Voice Assistant inferencing_interface
  -> control_task map_id
  -> rehab voice result adapter
  -> M33 m55_model_bridge
  -> CAN 0x323
  -> NanoPi /rehab_arm/model_state
  -> server command center / VLA context
```

旧 `voice_service`、`wake_word_detector`、`wake_on`、`wake_dump_pcm` 只能保留为诊断、PCM dump 或过渡验证入口；它们不是新的正式 wake 主线。

播报链路：

```text
LLM/server text
  -> tts_playback_request_v1
  -> server TTS audio or M55 TTS backend
  -> M55 MSG_TYPE_TTS_REQUEST/TTS_AUDIO
  -> M33 speaker/I2S path
```

这两条链路都不能输出 `0x320`、CAN motor frame、`motion_allowed=true` 或任何直接电机命令。

## 3. 模块边界

M55 固件必须保持模块化：

| 模块 | 职责 | 不允许 |
|---|---|---|
| `official_voice_audio.*` 或等价模块 | 从 Infineon local voice 迁移的 PDM/AFE/VA 音频管线适配层 | 绕过 M33/M55 IPC 或直接控制电机 |
| `official_voice_result_adapter.*` 或等价模块 | 将官方 `map_id/intent` 映射成本项目 `MSG_TYPE_AI_INFERENCE_RESP` | 直接发 CAN 或写服务器协议细节 |
| `voice_service.*` | 过渡期 PCM dump、API relay、诊断命令 | 作为正式 wake 主线，或直接控制电机 |
| `wake_word_detector.*` | 历史自写 wake 诊断/fallback | 作为正式 wake 主线，或维护服务器协议 |
| `model_manager.*` | 多模型 slot、TFLM load/run | 写死某个业务语义 |
| `model_result_publisher.*` | 统一发布 `MSG_TYPE_AI_INFERENCE_RESP` | 绕过 M33 |
| `m33_m55_comm.*` | MTB-IPC queue 和共享 PCM | 新建第二套跨核链路 |
| NanoPi `voice_gateway.py` | 生成 `voice_capture_v1`、`voice_relay_v1`、`tts_playback_request_v1` 合同 | 发 CAN 或真实运动 |

## 4. 模型移植步骤

1. 在独立官方例程 `_ifx_local_voice` 里先验证板载麦克风、PDM/I2S、扬声器、CM55 任务和 `Okay Infineon` 唤醒。
2. 记录官方例程关键文件：`mains_powered_local_voice.c`、`audio_feed_interface.c`、`pdm_mic_interface.c`、`inferencing_task.c`、`control_task.c`。
3. 在当前 GitHub `M55` 分支的 `wifi` 工程新增模块化适配层，不把官方代码直接堆进 `main.c`。
4. 第一阶段只迁移 PDM/PCM 自测和 10 ms frame 统计，验收串口日志、峰值/RMS 和无溢出。
5. 第二阶段迁移 AFE/VA 初始化和 map_id 输出，把 map_id 映射到 `MSG_TYPE_AI_INFERENCE_RESP`。
6. 第三阶段接 M33 结果出口：`M55 -> M33 -> CAN 0x323 -> NanoPi /rehab_arm/model_state`。
7. 第四阶段接服务器 ASR/LLM/TTS API 中转和扬声器播报；播报只做反馈，不授权运动。
8. 如果官方 DeepCraft/Voice Assistant 暂时受授权或模型训练阻塞，再用 `micro_speech` 或 `micro-wake-word` 的 `.tflite` 作为 fallback 模型，仍走相同 IPC/result adapter。

fallback `.tflite` 的导入方式仍然是：

```bash
xxd -i model.tflite > wake_model_data.h
```

但这只用于 fallback slot，不替代官方 local voice 主线。

## 5. 唤醒词建议

第一版建议只做一个中文提示词，例如“小医小医”。但模型实现上不要把中文写死进固件接口：

- 固件只输出 `wake_start_request`、置信度、窗口长度和模型版本。
- 服务器/文档记录当前 wake phrase。
- 换唤醒词时只换模型和 profile，不改 M33/NanoPi/服务器协议。

## 6. NanoPi 合同生成

在 ROS2 工作区安装或直接从源码运行：

```bash
python -m rehab_arm_psoc_bridge.build_voice_pipeline_plan --pretty \
  --robot-id medical_rehab_arm \
  --device-id nanopi_dev \
  --wake-phrase 小医小医 \
  --prompt-text 开始训练
```

输出包含：

- `voice_capture_v1`: M55/浏览器/App 采集到的音频或文本摘要。
- `voice_relay_v1`: 服务器 ASR/LLM API 中转结果。
- `rehab_arm_model_state_v1`: 映射后的 M55 语义编号。
- `tts_playback_request_v1`: 扬声器播报请求。

所有 payload 都带 `control_boundary`，且只允许作为 VLA 上下文或用户反馈。

## 7. 总控台模型中转边界

语音、摄像头、肌电、电机遥测和 M55 小模型结果进入大语言模型/VLA 时，只能走平台模型中转站：

```text
NanoPi /rehab_arm/model_state + camera/voice/EMG/safety summaries
  -> AI collaboration platform command-center model relay
  -> high_level_task / model_state_suggestion / dry_run_joint_trajectory_candidate
  -> dry-run simulation / operator review / M33 safety gate
```

固定接口见 [SERVER_SYNC_API_DRAFT.md](SERVER_SYNC_API_DRAFT.md) 的 `Command-Center Model Relay`。本仓库、NanoPi、M55、M33 和 App 都不能保存或请求厂商 API key；API key 只允许在云端平台服务端配置。

模型中转禁止输出和禁止执行：

- `can_frame`
- `motor_current`
- `motor_torque`
- `raw_motor_position`
- `raw_motor_velocity`
- `m33_safety_override`
- `direct_motor_command`

如果平台返回 `provider.external_call_ok=false`，设备端只能显示建议不可用、等待配置或安全过滤，不能本地补生成真实动作。急停确认必须等 `estop_ack_v1` 且 `m33_ack=true`，不能只凭 HTTP 200。

## 8. 下一步上板验收

1. 官方例程独立验收：说 `Okay Infineon` 后串口出现 wake/command map_id，LED/I2S 反馈正常。
2. 当前 `wifi` 工程 PDM 验收：M55 shell 执行 `pdm_mic_self_test 3`，串口出现 10 ms frame 统计，对麦克风说话时 `peak/avg_abs` 明显变化，无 FIFO overflow。
3. 当前 `wifi` 工程 I2S/扬声器验收：M55 shell 执行 `official_voice_speaker_test 1`，能听到短促 beep，串口出现 `speaker beep ok`。
4. 当前 `wifi` 工程阈值校准：M55 shell 执行 `voice_calibrate 2`，按输出的 `suggested: voice_thresholds ...` 设置现场阈值；`voice_thresholds` 可查看当前配置，`voice_pdm_gain` 可查看或调整 PDM gain。
5. 当前 `wifi` 工程 local voice 地基验收：M55 shell 执行 `local_voice_listen 5`，对麦克风说话后串口出现 `local activity detected`，并通过 `model_result_publish_wake_word(...)` 发布 `MSG_TYPE_AI_INFERENCE_RESP`。
6. M33/NanoPi 出口验收：NanoPi 先执行 `ros2 topic echo --once /rehab_arm/model_state std_msgs/msg/String`，再在 M55 shell 执行 `local_voice_listen 5`，确认 `m55_wake_word_v1` 或后续 `m55_voice_asr_v1`，且 `control_boundary=model_suggestion_only_not_motion_permission`。
7. 总控台收到 `voice_relay_v1` 后，下发 `tts_playback_request_v1`，确认扬声器播报。
8. 全程确认没有 `0x320`、没有 direct motor command、没有把语音当运动许可。

## 9. 当前官方 map_id 迁移验收

2026-06-09 已完成第一阶段官方 `map_id` 出口迁移：没有把完整 FreeRTOS/LVGL/music-player demo 复制进主线，而是在 M55 `wifi` 工程中增加 `official_voice_result_adapter.*`，把官方 local voice `map_id` 转成本项目现有的 `MSG_TYPE_AI_INFERENCE_RESP`。

已验证命令：

```text
ov_map 101 900  -> m55_wake_word_v1 / wake_start_request
ov_map 401 880  -> m55_voice_asr_v1 / voice_start_request
ov_map 408 850  -> m55_voice_asr_v1 / voice_pause_request
ov_map 402 850  -> m55_voice_asr_v1 / voice_stop_request
```

上板证据：

- M55 shell 有短命令 `ov_map` 和长命令 `official_voice_map_id`。
- M33 串口打印 `[m55_model_bridge] ... can_ret=0`。
- NanoPi `candump` 抓到 `0x323#B5...`。
- ROS_DOMAIN_ID=42 下 `/rehab_arm/model_state` 收到 `model_id=m55_voice_asr_v1`、`result_name=voice_start_request`、`suggestion_only=true`、`control_boundary=model_suggestion_only_not_motion_permission`。

注意：COM26 FINSH 串口在日志较多时会丢字符。现场验收优先用短命令 `ov_map`，每个字符间隔 50 ms 以上；如果置信度数字丢位，只影响本次测试置信度，不改变 `map_id` 语义出口。
