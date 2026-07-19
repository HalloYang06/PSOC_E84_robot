# 下一步：M33 采集 IMU 到 M55 在线推理

现在已经完成三件事：

1. PC 脚本能从 M33 串口日志采集带标签 IMU 数据。
2. Python 能训练 IMU MLP，并导出 C 头文件。
3. M55 能运行 `applications/edge_ai/edge_ai_imu_mlp.*`，对固定 IMU 窗口做板端推理。

下一步要做的是把“固定窗口”换成“实时窗口”。推荐先走 M33 采集、M55 推理这条路：

```text
LSM6DS3
  -> M33 I2C 驱动读取
  -> M33 写入共享内存窗口
  -> M33 通过 IPC/事件通知 M55
  -> M55 复制窗口到本地 buffer
  -> edge_ai_imu_mlp_predict_window()
  -> M55 串口打印 predicted label
```

## 为什么不让 M55 也直接读 IMU

第一版不建议 M33 和 M55 同时访问同一个 I2C IMU。这样会有几个麻烦：

- I2C 总线所有权不清楚，两个核可能同时抢外设。
- 驱动初始化可能重复做，容易出现偶发总线错误。
- 出问题后很难判断是模型错、采样错、IPC 错，还是 I2C 错。

所以先让 M33 做唯一的 IMU owner，M55 只消费整理好的窗口。

## 建议的模块边界

M33 工程后续新增：

```text
applications/imu_stream/
  imu_stream_sample.h      公共样本结构
  imu_stream_shared.h      共享内存布局
  imu_stream_producer.c    M33 采样、组窗口、发通知
```

M55 工程后续新增：

```text
applications/edge_ai/
  edge_ai_signal.*                 通用传感器窗口，支持 IMU/EMG/电机等多通道
  edge_ai_transport.*              可移植 transport API，主接口是 signal window
  edge_ai_transport_sharedmem.*    第一版共享内存 backend
  edge_ai_online_classifier.*      通用在线分类服务，负责 try_read -> predict -> ack
  edge_ai_imu_adapter.*            signal window 到 IMU MLP sample 的适配
  edge_ai_imu_mlp_classifier.*     当前 IMU MLP 的 classifier adapter
  edge_ai_online_classifier_app.c  后续再加的 RT-Thread 展示层
```

注意：`edge_ai_imu_mlp.c` 不应该依赖 IPC、RT-Thread 线程或 I2C。它只接收 `imu_mlp_sample_t[]`，输出 `imu_mlp_result_t`。这样将来换 TFLM 或 MTB ML 时，模型层仍然干净。

transport API 的详细说明见 `docs/edge-ai-transport-api.md`。

当前 M55 侧已经先实现了 `edge_ai_online_classifier_process_once()`。它还没有绑定真实共享内存地址，但主机测试已经验证了核心流程：

```text
sharedmem publish signal window -> online classifier process -> classifier predict -> ack
```

后面接板子时，优先做一个很薄的 RT-Thread 展示层，让它周期调用 `edge_ai_online_classifier_process_once()` 并打印 `[edge_ai_online]` 日志。

## 第一版在线窗口格式

建议先固定 8 个采样点，和当前训练脚本一致：

```c
typedef struct
{
    float ax_mg;
    float ay_mg;
    float az_mg;
    float gx_mdps;
    float gy_mdps;
    float gz_mdps;
    float temp_c;
} imu_mlp_sample_t;

typedef struct
{
    uint32_t sequence;
    uint32_t sample_count;
    imu_mlp_sample_t samples[8];
} edge_ai_imu_window_t;
```

第一版不要追求高频率，先做到每 200 ms 或 500 ms 推理一次。跑通以后再优化采样率、窗口滑动、时间戳和丢包统计。

## 验收标准

在线链路跑通时，串口应能看到：

```text
[m33_imu] seq=12 window ready count=8
[imu_online] seq=12 predicted=idle score=...
[m33_imu] seq=13 window ready count=8
[imu_online] seq=13 predicted=shake score=...
```

如果只看到 M33 日志，看不到 M55 日志，先查 M33 是否释放 M55。

如果看到 M55 日志但预测一直不变，先查共享内存窗口是否更新。

如果预测随机跳，先查窗口采样顺序、单位和训练时是否一致。

## 做这一步之前不要做什么

- 不要同时加肌电。
- 不要马上换 TFLM。
- 不要马上启用 U55/NNLite。
- 不要让 M33/M55 同时读 IMU。

师傅建议：先把 IMU 在线链路闭环跑稳。等“采样、窗口、通知、推理、日志”这条链路稳定以后，再把 IMU 换成肌电或把模型换成 TFLM，调试难度会小很多。
