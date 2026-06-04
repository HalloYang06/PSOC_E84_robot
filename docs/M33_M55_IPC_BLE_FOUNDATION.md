# M33/M55 IPC and BLE App Foundation

本文固定当前 PSoC Edge E84 的 M33/M55/App 地基，后续 AI、固件、NanoPi、App 和服务器开发都按本文复用现有实现，不能另造一套并行通信链路。

## 1. GitHub 工程对应关系

当前 GitHub 主仓库是 `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git`。

| 角色 | GitHub 分支 | 本地有效参考 | 说明 |
|---|---|---|---|
| M33 控制/安全核 | `M33` | `D:/RT-ThreadStudio/workspace/yiliao_m33` | 正式 M33 固件工作区，包含 CAN、M33/M55 IPC、BLE App 服务。 |
| M55 WiFi/AI 核 | `M55` | `D:/RT-ThreadStudio/workspace/_m55_ref_repo` 和 `D:/RT-ThreadStudio/workspace/wifi` | `docs/PSoC_README.md` 记录 `git clone -b M55 ... wifi`；`wifi` 是当时的 M55 WiFi 工程，但当前 `.git` 损坏，Git 历史以 `_m55_ref_repo` 为准。 |
| NanoPi/ROS/MuJoCo | `feature/rehab-arm-ros2-architecture` | `D:/RT-ThreadStudio/workspace/_nanopi_rosnode_usbcan` | 当前主仓库文档、ROS2、MuJoCo、服务器 topic 合同。 |

`wifi` 目录名可以作为 M55 工程线索，但不能只凭目录名下结论；以后必须从 GitHub 分支、提交历史和本文档引用交叉确认。

## 2. M33/M55 通讯地基

现有通讯不是新设计的裸地址协议，而是：

```text
短消息: Infineon MTB-IPC queue
大块 PCM: .ipc_stream_shared 共享内存区
```

现有源文件：

| 核 | 文件 | 作用 |
|---|---|---|
| M33 | `applications/common/m33_m55_comm.h/.c` | 创建 MTB-IPC 实例和双向 queue，发布/消费 `m33_m55_message_t`。 |
| M55 | `applications/m33_m55_comm.h/.c` | 连接 M33 创建的 queue，发布/消费 `m33_m55_message_t`。 |
| M33/M55 | `board/linker_scripts/link.ld` | 定义 `m33_m55_shared : ORIGIN = 0x261C0000, LENGTH = 0x00040000`，并把 `.ipc_stream_shared` 放入该共享区。 |
| M33/M55 | `libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/mtb_ipc_config.h` | Infineon MTB-IPC/SRF channel、semaphore、IRQ 预留配置。 |

当前共享内存事实：

```text
m33_m55_shared = 0x261C0000, size = 0x00040000
.ipc_stream_shared -> m33_m55_shared
m55_allocatable_shared = 0x240FF000, size = 0x00001000
```

当前短消息类型已经包含：

| 类型 | 用途 |
|---|---|
| `MSG_TYPE_SENSOR_SNAPSHOT` | 传感、电机和训练上下文快照。 |
| `MSG_TYPE_SENSOR_STREAM` | 流式传感窗口；音频 PCM 可只发元数据，实际数据放共享区。 |
| `MSG_TYPE_AI_INFERENCE_REQ/RESP` | 小模型推理请求/结果。 |
| `MSG_TYPE_REHAB_ANALYSIS_REQ/RESP` | 康复训练分析请求/结果。 |
| `MSG_TYPE_AUDIO_DATA` | 小块音频数据。 |
| `MSG_TYPE_ASR_TEXT` | M55 ASR 文本回 M33。 |
| `MSG_TYPE_TTS_REQUEST/TTS_AUDIO` | M55 与 M33 语音播放链路。 |
| `MSG_TYPE_VOICE_CONTROL` | M55 请求 M33 开始/停止采集或监听。 |

当前大块 PCM 结构：

```text
m33_m55_pcm_shared_t
seq, total_len, sample_rate, channels, bits_per_sample, timestamp, crc32, data[]
capacity = 16000 * 2 * 2 bytes
```

M33 写入共享 PCM 后必须 `RT_HW_CACHE_FLUSH`；M55 读取前必须 `RT_HW_CACHE_INVALIDATE`。后续 EMG 如果需要大块窗口，也应复用同一模式：短消息只放 `source/format/seq/len/timestamp`，大块数据放共享区或扩展共享区，不要再新建一套跨核传输。

## 3. M55 到 NanoPi/服务器的数据出口

M55 输出不能直接走电机链路。正式路径是：

```text
M55 小模型/语音
  -> m33_m55_comm_publish()
  -> M33 绑定时间戳、安全状态、profile 版本
  -> M33 CAN `0x323` 模型摘要帧
  -> NanoPi 解析编号语义
  -> /rehab_arm/model_state
  -> recorder/server/VLA
```

当前模块边界必须保持：

- M55 WiFi 工程用 `applications/model_result_publisher.*` 发布小模型结果，不把推理逻辑堆到 `main.c`。
- M33 用 `applications/m33/m55_model_bridge.*` 消费 `MSG_TYPE_AI_INFERENCE_RESP`/`MSG_TYPE_ASR_TEXT`，再经 control layer 发 `0x323`。
- NanoPi 用 `m33_model_status.py` 解析 `0x323`，发布 `/rehab_arm/model_state`。
- 任何 AI/VLA/语音/EMG 结果都只能是 `model_suggestion_only_not_motion_permission`，正式运动仍走 `JointTrajectory -> NanoPi -> 0x320 -> M33 safety gate -> 电机`。

如果 M55 通过 WiFi 直连服务器，只允许上传低频语音文本、音频摘要、OpenClaw 服务状态、模型摘要或诊断信息。全量机器人状态、正式运动状态和 safety truth 仍以 NanoPi 汇总 M33 数据为主。

## 3A. M33 到 M55 的模型输入

M33 采集到的数据进入 M55 也是主线架构的一部分，不是 demo 旁路。当前合同见 [M33_M55_MODEL_INPUT_PROTOCOL_V1.md](M33_M55_MODEL_INPUT_PROTOCOL_V1.md)。

正式方向：

```text
C8T6/EMG/音频/电机上下文 -> M33
M33 -> MSG_TYPE_SENSOR_SNAPSHOT 或 MSG_TYPE_SENSOR_STREAM -> M55
M55 model_input_bridge/model_manager -> MSG_TYPE_AI_INFERENCE_RESP -> M33
M33 -> 0x323 -> NanoPi -> /rehab_arm/model_state
```

当前已上板验证的测试闭环是 M55 shell `req_snap` 请求 M33 发布一帧测试 sensor snapshot；M33 再通过 `MSG_TYPE_SENSOR_SNAPSHOT` 发回 M55，M55 规则模型输出结果后经 `0x323` 到 NanoPi。该测试只证明跨核输入链路和结果出口，不代表真实 EMG 模型已经训练完成。

新增台架验证入口是 M55 shell `req_m7`：M55 请求 M33 读取 7 号外部 EL05 电机反馈，M33 以 `source=MODEL_INPUT_SRC_MOTOR_FEEDBACK` 的 snapshot 发回 M55，M55 的 `motor7_model_runner` 调用现有 TFLite Micro 模型并仍按 `0x323` 出口返回。该入口用于验证真实电机反馈进入 M55 TFLM runtime，不把 7 号电机升级为正式机械臂关节，也不让 M55 控制电机。

## 4. M33 BLE 到 App 地基

M33 已有 App BLE 服务雏形，当前是 NUS 风格 GATT：

| 项 | 当前实现 |
|---|---|
| Device name | `OpenClaw-NUS` |
| Service UUID | 源码字节数组 `BT_APP_UUID_SERVICE_NUS` 为准 |
| RX characteristic | App 写入 M33，handle `HDLC_NUS_RX_VALUE` |
| TX characteristic | M33 notify App，handle `HDLC_NUS_TX_VALUE` |
| 当前 App 命令 | `stream:on`、`stream:off`、`heartbeat`、`stop`、`mode:<mode>`、`move:<joint>:<target>` |
| 当前 M33 上行 | `app_ble_service_update_telemetry()` 生成短 JSON，`bt_app_gatt_send()` 分片 notify |

当前 BLE 上行 JSON 还很短，字段含义如下：

| 当前字段 | 含义 |
|---|---|
| `s` | streaming enabled |
| `m` | control mode |
| `sh` | shoulder angle |
| `el` | elbow angle |
| `la` | lateral position |
| `hr` | heart rate |
| `sp` | SpO2 |
| `e1/e2` | 旧 2 路 EMG 摘要 |
| `sf` | safety state |

正式 App 字段第一版应扩展为：

| 方向 | 字段组 | 说明 |
|---|---|---|
| M33 -> App | `safety` | `motion_allowed`、`safety_state`、`detail_code`、急停/故障 latch、通信新鲜度。 |
| M33 -> App | `profile` | active profile id/version、模式、患者 ROM 摘要、限速/辅助等级摘要。 |
| M33 -> App | `joints` | 输出端关节位置/速度、fresh/stale、限位距离摘要。 |
| M33 -> App | `motors` | 电机温度、故障、在线状态、当前映射版本。 |
| M33 -> App | `sensors` | 4 路 EMG 低频质量/均值/RMS 摘要、IMU/心率/SpO2 摘要。 |
| M33 -> App | `model` | M55 模型编号、置信度、fresh、`model_suggestion_only_not_motion_permission`。 |
| App -> M33 | `request` | start/pause/stop/estop request、mode request、profile confirm、pain/fatigue feedback、annotation、heartbeat。 |

App BLE 只允许做近端显示、训练请求、profile 确认、急停请求和标注。App 不允许发 CAN、电机目标、底层关节轨迹或绕过 M33 限位的命令。现有 `move:<joint>:<target>` 只能留作 bench/debug，并且必须被 M33 安全状态机审核。

## 5. 后续 AI 必须遵守

- 不要新建第二套 M33/M55 通讯。复用 `m33_m55_comm.h/.c`、MTB-IPC queue 和 `.ipc_stream_shared`。
- 不要只实现 M55 到 M33 的结果出口；M33 到 M55 的传感器输入也必须按 `M33_M55_MODEL_INPUT_PROTOCOL_V1.md` 走。
- 不要把 `wifi` 目录当成无 Git 证据的新工程；M55 主线来自 GitHub `M55` 分支。
- 不要让 M55、App、服务器或 VLA 直接控制电机。
- 不要把 M55 的 `confidence` 或 App 的 `start` 当成 `motion_allowed=true`。
- 不要把 M33/M55 新逻辑堆进 `main.c`。M55 结果发布用 `model_result_publisher.*` 或后续同类模块；M33 桥接用 `m55_model_bridge.*` 或后续同类模块。
- 不要绕过 `0x323`/`/rehab_arm/model_state` 合同另建 M55 结果 topic 或 CAN ID，除非先更新本文件、`PSOC_CAN_PROTOCOL_V1.md` 和 `M55_MODEL_RESULT_PROTOCOL_V1.md`。
- 不要在 App、M33、NanoPi、服务器分别维护不同模型编号表。编号语义以 `M55_MODEL_RESULT_PROTOCOL_V1.md` 为准。
- 不要把 M55 WiFi 做成全量机器人状态主链路。正式机器人状态以 M33 -> NanoPi -> server 为主。
- 所有新增字段先更新 `PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`、`M55_MODEL_RESULT_PROTOCOL_V1.md`、`PSOC_CAN_PROTOCOL_V1.md` 或 ROS topic 合同，再写代码。
