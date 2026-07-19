# Edge AI Transport API 设计说明

这份文档解释 M33 和 M55 之间的数据传输层。新版设计不再把 transport 写死成 IMU，而是统一传输 `edge_ai_signal_window_t`。

核心原则：

```text
transport 只负责搬运 signal window，不负责理解 IMU、肌电、电机或模型语义。
```

## 1. 当前文件

```text
applications/edge_ai/edge_ai_status.h
applications/edge_ai/edge_ai_signal.h
applications/edge_ai/edge_ai_signal.c
applications/edge_ai/edge_ai_transport.h
applications/edge_ai/edge_ai_transport.c
applications/edge_ai/edge_ai_transport_sharedmem.h
applications/edge_ai/edge_ai_transport_sharedmem.c
applications/edge_ai/edge_ai_shared_contract.h
applications/edge_ai/edge_ai_shared_contract.c
applications/edge_ai/edge_ai_online_classifier.h
applications/edge_ai/edge_ai_online_classifier.c
applications/edge_ai/edge_ai_imu_adapter.h
applications/edge_ai/edge_ai_imu_adapter.c
applications/edge_ai/edge_ai_imu_mlp_classifier.h
applications/edge_ai/edge_ai_imu_mlp_classifier.c
```

## 2. 分层边界

```text
edge_ai_signal.*
  定义通用传感器窗口。窗口里有通道表和采样值矩阵。

edge_ai_transport.*
  定义可移植 transport API。主接口发布/读取 signal window。

edge_ai_transport_sharedmem.*
  第一版共享内存 backend。后续换 MTB IPC notify 时优先加 backend，不改模型。

edge_ai_shared_contract.*
  定义 M33/M55 共同遵守的共享地址和 producer/consumer 绑定方式。

edge_ai_online_classifier.*
  通用在线分类服务。它只知道 classifier 回调，不知道具体传感器类型。

edge_ai_online_consumer.*
  M55 consumer 状态机。M33 producer 暂时不存在时先等待，producer format 后自动 attach。

edge_ai_imu_adapter.* / edge_ai_imu_mlp_classifier.*
  当前 IMU MLP 的适配层。IMU 是一个 classifier，不是 transport 的固定形态。
```

## 3. 通用 signal window

`edge_ai_signal_window_t` 可以承载多种传感器通道：

```c
#define EDGE_AI_WINDOW_CAPACITY 8u
#define EDGE_AI_SIGNAL_MAX_CHANNELS 16u

typedef struct
{
    uint32_t sequence;
    uint32_t sample_count;
    uint32_t channel_count;
    uint16_t channel_ids[EDGE_AI_SIGNAL_MAX_CHANNELS];
    edge_ai_signal_sample_t samples[EDGE_AI_WINDOW_CAPACITY];
} edge_ai_signal_window_t;
```

当前通道例子：

```text
EDGE_AI_SIGNAL_ACCEL_X_MG
EDGE_AI_SIGNAL_GYRO_Z_MDPS
EDGE_AI_SIGNAL_EMG_UV
EDGE_AI_SIGNAL_JOINT_ANGLE_DEG
EDGE_AI_SIGNAL_MOTOR_CURRENT_MA
```

后续新增力传感器、编码器、扭矩估计时，优先新增 channel id，而不是新增一套 transport。

## 4. 主 transport API

新代码优先使用这三个接口：

```c
int edge_ai_transport_publish_signal_window(edge_ai_transport_t *transport,
                                            const edge_ai_signal_window_t *window);

int edge_ai_transport_try_read_signal_window(edge_ai_transport_t *transport,
                                             edge_ai_signal_window_t *window);

int edge_ai_transport_ack_signal_window(edge_ai_transport_t *transport,
                                        uint32_t sequence);
```

推荐数据流：

```text
M33 producer:
  build edge_ai_signal_window_t
  publish_signal_window()
  notify M55

M55 consumer:
  online_classifier_process_once()
    try_read_signal_window()
    classifier->predict()
    ack_signal_window()
```

## 5. IMU 兼容包装

为了保护前面已经跑通的 IMU demo，当前仍保留这些函数：

```c
int edge_ai_transport_publish_imu_window(edge_ai_transport_t *transport,
                                         const edge_ai_imu_window_t *window);

int edge_ai_transport_try_read_imu_window(edge_ai_transport_t *transport,
                                          edge_ai_imu_window_t *window);

int edge_ai_transport_ack_imu_window(edge_ai_transport_t *transport,
                                     uint32_t sequence);
```

这三个函数只是兼容包装：内部会把 `edge_ai_imu_window_t` 转成 `edge_ai_signal_window_t`。后续正式外骨骼链路不要继续扩展 `imu_window`，而是直接使用 `signal_window`。

## 6. 共享内存 backend

共享内存块当前是 ABI version 2：

```c
typedef struct
{
    volatile uint32_t magic;
    volatile uint32_t version;
    volatile uint32_t state;
    volatile uint32_t sequence;
    volatile uint32_t sample_count;
    volatile uint32_t channel_count;
    uint16_t channel_ids[EDGE_AI_SIGNAL_MAX_CHANNELS];
    edge_ai_signal_sample_t samples[EDGE_AI_WINDOW_CAPACITY];
    volatile uint32_t commit_sequence;
} edge_ai_sharedmem_block_t;
```

关键字段：

```text
magic/version
  检查 M33/M55 是否使用同一版 ABI。

state
  EMPTY / WRITING / READY。

sequence
  窗口序号，用于排查丢包、重复读、M33/M55 不同步。

channel_ids
  当前窗口包含哪些传感器通道。

commit_sequence
  降低读到半包数据的风险。
```

## 7. format 和 attach 的区别

双核共享内存里有一个很容易踩的坑：如果 M33 已经写好了窗口，M55 启动后又把共享块初始化一遍，就会把 M33 的数据清掉。

所以当前 API 分成两个角色：

```c
int edge_ai_transport_sharedmem_format(edge_ai_transport_t *transport,
                                       edge_ai_sharedmem_transport_t *backend,
                                       volatile void *shared_block,
                                       unsigned int shared_block_size);

int edge_ai_transport_sharedmem_attach(edge_ai_transport_t *transport,
                                       edge_ai_sharedmem_transport_t *backend,
                                       volatile void *shared_block,
                                       unsigned int shared_block_size);
```

推荐规则：

```text
producer 调 format：负责写 magic/version/state，初始化共享块。
consumer 调 attach：只检查 magic/version，然后绑定 backend，不清空数据。
```

在当前 M33 采样、M55 推理的路线里：

```text
M33 = producer = format
M55 = consumer = attach
```

旧的 `edge_ai_transport_sharedmem_init()` 仍然保留，但它等价于 `format()`，只适合 producer 或主机测试初始化。

共享契约层提供了更明确的入口：

```c
edge_ai_shared_contract_bind_producer(&transport, &backend);
edge_ai_shared_contract_bind_consumer(&transport, &backend);
```

默认共享块地址：

```text
EDGE_AI_SHARED_BLOCK_ADDRESS = 0x261C0000
EDGE_AI_SHARED_SOCMEM_SIZE   = 0x00040000
```

## 8. M55 在线分类服务

M55 应用层优先调用：

```c
edge_ai_classifier_t classifier;
edge_ai_online_classifier_result_t result;

edge_ai_imu_mlp_classifier_init(&classifier);

if (edge_ai_online_classifier_process_once(&transport, &classifier, &result) == EDGE_AI_STATUS_OK)
{
    rt_kprintf("[edge_ai_online] seq=%lu classifier=%s label=%s score=%d\r\n",
               (unsigned long)result.sequence,
               classifier.name,
               result.classification.label,
               (int)(result.classification.score * 1000.0f));
}
```

如果后续换成肌电/电机融合模型，只新增类似 `edge_ai_exo_fusion_classifier_init()` 的适配器。`edge_ai_online_classifier_process_once()` 不需要改。

## 9. 验证命令

通用 signal window：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_signal_test.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c -o build/edge_ai_signal_test.exe
.\build\edge_ai_signal_test.exe
```

通用 online classifier：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_online_classifier_test.c applications/edge_ai/edge_ai_online_classifier.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c applications/edge_ai/edge_ai_transport_sharedmem.c -o build/edge_ai_online_classifier_test.exe
.\build\edge_ai_online_classifier_test.exe
```

兼容 IMU transport：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_transport_test.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c applications/edge_ai/edge_ai_transport_sharedmem.c -o build/edge_ai_transport_test.exe
.\build\edge_ai_transport_test.exe
```

期望：

```text
PASS edge_ai signal window
PASS edge_ai online classifier
PASS edge_ai transport API
```

共享契约：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_shared_contract_test.c applications/edge_ai/edge_ai_shared_contract.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c applications/edge_ai/edge_ai_transport_sharedmem.c -o build/edge_ai_shared_contract_test.exe
.\build\edge_ai_shared_contract_test.exe
```

期望：

```text
PASS edge_ai shared contract
```
