# Voice Wake, ASR Relay, and Speaker Playback Portability Guide

本文固定医疗康复机械臂的语音地基：M55 负责板端音频采集、唤醒词、小模型和低频语义事件；服务器总控台作为 LLM/ASR/TTS API 中转；扬声器播报只反馈状态，不授权运动。

## 1. 优先级

1. 官方硬件示例优先：先看 Infineon PSOC Edge local voice 示例，复用 PDM/I2S/codec/CM33+CM55 工程结构和音频管线。
2. 官方 TinyML 示例优先：最小 wake-word runtime 优先参考 TensorFlow Lite Micro `micro_speech`。
3. 开源模型优先：自定义唤醒词优先评估 OHF/ESPHome `micro-wake-word` 和现成 `.tflite` 模型仓库。
4. 云 ASR/TTS 只做可选 API 中转：不要把 Baidu/OpenAI/其他云接口写成固件唯一依赖。

参考源：

- Infineon [`mtb-example-psoc-edge-mains-powered-local-voice`](https://github.com/Infineon/mtb-example-psoc-edge-mains-powered-local-voice): PSoC Edge E84 本地语音、CM33/CM55、PDM/I2S、扬声器和 DEEPCRAFT 语音管线示例。
- TensorFlow Lite Micro [`micro_speech`](https://github.com/tensorflow/tflite-micro/tree/main/tensorflow/lite/micro/examples/micro_speech): 官方微控制器语音关键词示例，展示 16 kHz 音频、特征、TFLM interpreter、C array 模型和持续推理。
- OHF/ESPHome [`micro-wake-word`](https://github.com/OHF-Voice/micro-wake-word): 开源自定义唤醒词训练框架和模型分发，适合先做可替换 wake-word slot。

## 2. 本项目固定链路

```text
M55 microphone/PDM or M33 shared PCM
  -> voice_service audio window
  -> wake_word_detector or model_manager wake slot
  -> model_result_publisher
  -> M33 m55_model_bridge
  -> CAN 0x323
  -> NanoPi /rehab_arm/model_state
  -> server command center / VLA context
```

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
| `voice_service.*` | 音频窗口、M33 共享 PCM、WebSocket/API relay、ASR/TTS 文本和音频收发 | 直接控制电机 |
| `wake_word_detector.*` | wake-word 特征和模型检测 | 维护服务器协议 |
| `model_manager.*` | 多模型 slot、TFLM load/run | 写死某个业务语义 |
| `model_result_publisher.*` | 统一发布 `MSG_TYPE_AI_INFERENCE_RESP` | 绕过 M33 |
| `m33_m55_comm.*` | MTB-IPC queue 和共享 PCM | 新建第二套跨核链路 |
| NanoPi `voice_gateway.py` | 生成 `voice_capture_v1`、`voice_relay_v1`、`tts_playback_request_v1` 合同 | 发 CAN 或真实运动 |

## 4. 模型移植步骤

1. 先用 Infineon local voice 示例确认板载麦克风、PDM/I2S、扬声器和 CM55 任务模型。
2. 先把 TensorFlow Lite Micro `micro_speech` 或 `micro-wake-word` 的 `.tflite` 跑进 `MODEL_SLOT_WAKE_WORD`。
3. 用 `xxd -i model.tflite > wake_model_data.h` 或等价工具转成 C array。
4. 只替换 `wake_word_model_data.h` 或新增同类 `*_model_data.h`，不要改 IPC、CAN、NanoPi topic。
5. 在 `model_manager` 注册 slot，并用 `model_result_publisher` 输出 `m55_wake_word_v1`。
6. 用 `wake_on`、`voice_test`、`wake_dump_pcm`、`build_voice_pipeline_plan --pretty` 做分层验证。

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

## 7. 下一步上板验收

1. 串口确认 M55 日志出现 `voice service initialized`、`wake detector ready=1`。
2. M55 shell 执行 `wake_on`，让 M33 开始共享 PCM。
3. 说“小医小医”，观察 M55 `wake triggered` 或 `model result publish`。
4. NanoPi 执行 `ros2 topic echo --once /rehab_arm/model_state`，确认 `m55_wake_word_v1`。
5. 总控台收到 `voice_relay_v1` 后，下发 `tts_playback_request_v1`，确认扬声器播报。
6. 全程确认没有 `0x320`、没有 direct motor command、没有把语音当运动许可。
