# EMG Intent TFLM on M55

这份记录只写当前 M55 工程里的肌电推理链路。旧 IMU demo 不再是默认方向；新的链路是：

```text
M33 F103/C8T6 EMG CAN cache
  -> shared SoC RAM raw uint16 window
  -> MSG_TYPE_SENSOR_STREAM / MODEL_INPUT_SRC_EMG
  -> M55 TFLite Micro int8 inference
  -> MODEL_CODE_EMG_INTENT result
  -> AI_INFERENCE_RESP back to M33
```

## 1. M55 负责什么

M55 不直接采集肌电。当前分工是：

- M33 从 F103/C8T6 节点拿到 `emg3_raw[0..2]`。
- M33 把一段 3 通道 EMG 窗口写入共享内存。
- M33 通过 IPC 发 `MSG_TYPE_SENSOR_STREAM` 通知 M55。
- M55 从共享内存读窗口，提取和 PC 训练一致的 20 个特征。
- M55 把特征量化成 int8，送进 TFLite Micro 模型。
- M55 把 `intent_label / confidence / timestamp / quality` 这类结果通过现有 result publisher 回 M33。

这意味着大数据走 shared memory，小消息走 IPC。

## 2. 关键文件

```text
applications/emg_intent_bridge.cpp
applications/emg_intent_bridge.h
applications/intent_tflm_runtime.cpp
applications/intent_tflm_runtime.h
applications/intent_model_int8.cc
applications/intent_model_int8.h
applications/intent_golden_samples.cc
applications/intent_golden_samples.h
applications/intent_tflm_smoke.cpp
applications/voice_service.c
tools/test_emg_intent_bridge_contract.py
tools/test_intent_tflm_smoke_contract.py
```

`voice_service.c` 里新增了 EMG stream 分支：

```c
if (msg->payload.sensor_stream.source == MODEL_INPUT_SRC_EMG)
{
    (void)emg_intent_bridge_handle_stream(&msg->payload.sensor_stream);
    break;
}
```

所以 EMG stream 不会进入音频 PCM 处理路径。

## 3. 输入协议

M55 期望收到的 `sensor_stream_msg_t`：

```text
type          = MSG_TYPE_SENSOR_STREAM
source        = MODEL_INPUT_SRC_EMG
format        = MODEL_INPUT_FMT_UINT16
channels      = 3
sample_rate   = 50
frame_samples = 15
total_len     = frame_samples * 3 * 2
reserved1     = stale_count
```

共享内存数据格式：

```text
sample0_ch0 uint16 little-endian
sample0_ch1 uint16 little-endian
sample0_ch2 uint16 little-endian
sample1_ch0 uint16 little-endian
...
```

现在的模型不是吃原始波形，而是吃窗口特征。

## 4. 特征和量化

`emg_intent_bridge.cpp` 从每个窗口提取 20 个特征：

```text
sample_count
biceps mean/std/min/max/mav/rms
triceps mean/std/min/max/mav/rms
anterior_deltoid mean/std/min/max/mav/rms
stale_count
```

然后使用 PC 训练导出的预处理参数：

```text
kFeatureMeans[]
kFeatureStds[]
EMG_INTENT_INPUT_SCALE
EMG_INTENT_INPUT_ZERO_POINT
```

量化流程：

```text
raw EMG window
  -> float features
  -> z-score normalize
  -> int8 quantized input
  -> TFLite Micro model
```

这个步骤必须和 PC 训练/量化时的 `preprocess.json` 一致，否则 PC 上精度好，板端也可能乱判。

## 5. 模型输出

当前 int8 模型标签顺序：

```text
0 elbow_extend
1 elbow_flex
2 rest
3 shoulder_flex
```

`rest` 不算有效动作。当前阈值：

```text
confidence >= 400 permille
```

也就是大约 40% 以上才认为检测到非静息动作。这个阈值后面要根据真实板端数据调。

## 6. 本地验证命令

在 M55 工程根目录运行：

```powershell
python -m unittest tools.test_emg_intent_bridge_contract tools.test_intent_tflm_smoke_contract tools.test_opus_integration_contract tools.test_sdio_diag_link_contract
```

构建：

```powershell
$env:RTT_EXEC_PATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\gnu_gcc\arm_gcc\mingw\bin'
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

## 7. 上板验证顺序

先烧 M33，再烧 M55。上电后先不要急着看最终动作，按下面顺序排查。

M55 串口：

```text
intent_tflm_smoke -v
emg_intent
```

M33 串口：

```text
m55_emg_stream 1 20 1
m55_emg_status
```

应该看到的日志方向：

```text
M33: [m55_emg] publish seq=... samples=15 stale=... len=90
M55: [emg_intent] seq=... label=... idx=... conf=... detected=...
M55: [m55_model_bridge] ai result ...
```

## 8. 当前状态

当前完成的是：

- M55 编译期接入 int8 `.tflite` C array。
- M55 侧 TFLite Micro runtime 封装完成。
- M55 侧 EMG stream 消费、特征提取、int8 推理、结果发布完成。
- M55 侧契约测试和本地 SCons 构建已用于验证。

还没有完成的是：

- 真实板端串口日志验证。
- M33 收到 M55 结果后接入控制状态机。
- 根据真实肌电数据重新调 confidence 阈值和窗口参数。

