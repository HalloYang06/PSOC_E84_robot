# M33 to M55 Model Input Protocol V1

本文定义 M33 采集到的传感器、电机上下文和音频窗口如何进入 M55 小模型。它和 `M55_MODEL_RESULT_PROTOCOL_V1.md` 是一进一出两份合同：输入走 `M33 -> M55`，结果走 `M55 -> M33 -> NanoPi`。

## 1. 边界

- M33 是传感器汇总、时间戳、安全状态和电机状态的事实来源。
- M55 只做小模型推理、语音/音频处理和低频语义输出。
- M55 收到的输入不能直接变成电机命令；结果必须回到 M33，经 `0x323` 和 `/rehab_arm/model_state` 出口给 NanoPi/服务器/VLA。
- 第一版 EMG 不把 500-1000 Hz 原始流直接送 VLA。M33 先做窗口、质量和摘要，M55 再做 int8 TFLM 或规则模型推理。

## 2. 现有传输层

不新增跨核链路，复用现有 `m33_m55_comm`：

| 数据类型 | 消息 | 载体 |
|---|---|---|
| 低频快照 | `MSG_TYPE_SENSOR_SNAPSHOT` | MTB-IPC queue 内的 `sensor_snapshot_msg_t` |
| 流式窗口元数据 | `MSG_TYPE_SENSOR_STREAM` | MTB-IPC queue 内的 `sensor_stream_msg_t` |
| 大块 PCM/窗口数据 | `.ipc_stream_shared` | `g_m33_m55_pcm_shared`，M33 flush，M55 invalidate |
| 推理结果 | `MSG_TYPE_AI_INFERENCE_RESP` | M55 回 M33，然后 M33 发 `0x323` |

当前代码地基：

| 核 | 模块 | 作用 |
|---|---|---|
| M33 | `applications/m33/m55_model_input_bridge.*` | 发布 sensor snapshot/window 到 M55。 |
| M33 | `applications/main.c` | 处理 `VOICE_CTRL_PUBLISH_TEST_SNAPSHOT` 测试请求。 |
| M55 | `applications/model_input_bridge.*` | 接收 `MSG_TYPE_SENSOR_SNAPSHOT/STREAM`，调用当前规则模型或后续 TFLM。 |
| M55 | `applications/model_result_publisher.*` | 把模型结果发布回 M33。 |
| M33 | `applications/m33/m55_model_bridge.*` | 把 M55 结果绑定到 `0x323`。 |

## 3. EMG 第一版输入

4 路 EMG 正式接入时按以下顺序补：

1. C8T6 或 M33 采集原始 EMG，明确通道顺序、单位、采样率、饱和/脱落标志和丢包计数。
2. M33 对每个窗口计算 `RMS/MAV/ZC/SSC/WL`、质量标志、窗口毫秒、时间戳和关节上下文。
3. 低频摘要可放 `MSG_TYPE_SENSOR_SNAPSHOT`；较大的窗口放 `.ipc_stream_shared`，短消息只放 `source=MODEL_INPUT_SRC_EMG`、`format`、`channels`、`total_len`、`chunk_index`、`timestamp`。
4. M55 在 `model_input_bridge` 中把输入喂给 `MODEL_SLOT_EMG` 的 int8 TFLM 模型。
5. M55 输出 `m55_emg_intent_v1`、`m55_fatigue_v1` 或 `m55_quality_v1`，仍走 `MSG_TYPE_AI_INFERENCE_RESP -> 0x323 -> /rehab_arm/model_state`。

## 4. 上板验收命令

当前串口 shell 在 M55 侧。使用 `req_snap` 验证完整闭环：

```text
M55 shell: req_snap
M55 -> M33: MSG_TYPE_VOICE_CONTROL / VOICE_CTRL_PUBLISH_TEST_SNAPSHOT
M33 -> M55: MSG_TYPE_SENSOR_SNAPSHOT
M55 -> M33: MSG_TYPE_AI_INFERENCE_RESP
M33 -> NanoPi: CAN 0x323
NanoPi -> ROS: /rehab_arm/model_state
```

期望串口日志：

```text
model_input_request_m33_snapshot ret=0
[m33] ipc publish test snapshot
[m55_input] snapshot seq=... emg=(420,80) hr=76 spo2=98 ret=0
[model_input] snapshot seq=... score=420 detected=1
[model_input] snapshot publish ret=0
[m55_model_bridge] ai seq=... model=1 result=1 conf=420 flags=0x03 win=200 can_ret=0
```

NanoPi 验收：

```bash
timeout 12 candump -L can0,323:7FF
```

期望示例：

```text
can0 323#B50A01012A831400
```

ROS 验收：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
timeout 15 ros2 topic echo --once --full-length /rehab_arm/model_state std_msgs/msg/String
```

期望 JSON 包含 `source=m33_m55_bridge_can_0x323`、`result_code=1`、`confidence=0.42`、`suggestion_only=true` 和 `control_boundary=model_suggestion_only_not_motion_permission`。

## 5. 后续替换小模型

当前 `model_input_bridge` 的 snapshot 路径是规则阈值模型，只用于证明 M33 数据能进入 M55 并返回 NanoPi。后续替换为正式 EMG 模型时：

- 保留 `req_snap` 作为链路自测入口。
- 保留 `MSG_TYPE_SENSOR_SNAPSHOT/STREAM` 输入合同。
- 保留 `MSG_TYPE_AI_INFERENCE_RESP` 和 `0x323` 结果出口。
- 只替换 `model_input_bridge_handle_snapshot()` 或 `model_input_bridge_handle_stream()` 内部推理实现。
- 不把 M55 推理结果直接映射成 `0x320`。
