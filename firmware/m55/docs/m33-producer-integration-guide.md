# M33 Producer 接入指南

这份文档讲怎么把 M33 LSM6DS3 工程接到当前 M55 AI 工程。目标不是立刻做复杂 IPC，而是先让 M33 把一个 `edge_ai_signal_window_t` 写进共享内存，M55 从同一块内存读出来推理。

当前状态：M33 producer 代码已经接入 `F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3`，并通过 SCons 构建。实现记录见 `docs/m33-producer-implementation-log.md`。

## 1. 当前角色分工

```text
M33:
  负责采样。第一版先采 LSM6DS3，后续再加肌电、电机和关节数据。
  作为 producer，初始化并写共享块。

M55:
  负责 AI 推理。
  作为 consumer，只挂接共享块，不清空共享块。
```

## 2. 共享地址

当前默认地址定义在：

```text
applications/edge_ai/edge_ai_shared_contract.h
```

关键宏：

```c
#define EDGE_AI_SHARED_SOCMEM_BASE 0x261C0000u
#define EDGE_AI_SHARED_SOCMEM_SIZE 0x00040000u
#define EDGE_AI_SHARED_BLOCK_ADDRESS (EDGE_AI_SHARED_SOCMEM_BASE + 0x00000000u)
```

这个地址和 M33 linker 中的 `.cy_shared_socmem` 对应：

```text
m33_m55_shared : ORIGIN = 0x261C0000, LENGTH = 0x00040000
.cy_shared_socmem (NOLOAD) > m33_m55_shared
```

## 3. M33 要复制哪些文件

第一版 M33 producer 不需要模型文件，只需要通用数据和 transport。当前已经同步的文件如下：

```text
edge_ai_status.h
edge_ai_signal.h
edge_ai_signal.c
edge_ai_transport.h
edge_ai_transport.c
edge_ai_transport_sharedmem.h
edge_ai_transport_sharedmem.c
edge_ai_shared_contract.h
edge_ai_shared_contract.c
```

不要把 `edge_ai_imu_mlp.*`、`edge_ai_online_classifier.*`、`edge_ai_exo_model.*` 复制到 M33。M33 只采样和发布，不做模型推理。

## 4. M33 producer 伪代码

当前 M33 工程已经新增：

```text
applications/edge_ai/edge_ai_m33_producer.*
```

它已经被 `packages/lsm6ds3tr/lsm6ds3tr-c_port.c` 调用。下面伪代码用于理解结构：

```c
#include "edge_ai_shared_contract.h"

static edge_ai_transport_t g_edge_ai_transport;
static edge_ai_sharedmem_transport_t g_edge_ai_backend;
static uint32_t g_sequence;

void edge_ai_m33_producer_init(void)
{
    int status = edge_ai_shared_contract_bind_producer(&g_edge_ai_transport,
                                                       &g_edge_ai_backend);
    rt_kprintf("[m33_edge_ai] producer init status=%d addr=0x%08x\r\n",
               status,
               (unsigned int)edge_ai_shared_contract_get_block_address());
}

void edge_ai_m33_publish_imu_window(void)
{
    edge_ai_signal_window_t window;

    memset(&window, 0, sizeof(window));
    window.sequence = ++g_sequence;
    window.sample_count = 8;
    window.channel_count = 7;
    window.channel_ids[0] = EDGE_AI_SIGNAL_ACCEL_X_MG;
    window.channel_ids[1] = EDGE_AI_SIGNAL_ACCEL_Y_MG;
    window.channel_ids[2] = EDGE_AI_SIGNAL_ACCEL_Z_MG;
    window.channel_ids[3] = EDGE_AI_SIGNAL_GYRO_X_MDPS;
    window.channel_ids[4] = EDGE_AI_SIGNAL_GYRO_Y_MDPS;
    window.channel_ids[5] = EDGE_AI_SIGNAL_GYRO_Z_MDPS;
    window.channel_ids[6] = EDGE_AI_SIGNAL_TEMPERATURE_C;

    // 把 LSM6DS3 采样值填进 window.samples[i].values[]
    // values[0] = ax_mg, values[1] = ay_mg, ...

    edge_ai_transport_publish_signal_window(&g_edge_ai_transport, &window);
}
```

## 5. M55 consumer 伪代码

当前 M55 工程已经接入了一个 RT-Thread 展示层：

```text
applications/edge_ai/edge_ai_online_app.*
```

它内部使用 `edge_ai_online_consumer.*`，会自动等待 M33 producer。M33 没接好之前，M55 串口会偶尔打印：

```text
[edge_ai_online] waiting producer status=-4 attached=0 addr=0x261c0000
```

后续如果你要手写一个更小的 M55 consumer，核心伪代码如下：

```c
#include "edge_ai_shared_contract.h"
#include "edge_ai_imu_mlp_classifier.h"
#include "edge_ai_online_classifier.h"

static edge_ai_transport_t g_edge_ai_transport;
static edge_ai_sharedmem_transport_t g_edge_ai_backend;
static edge_ai_classifier_t g_classifier;

void edge_ai_m55_consumer_init(void)
{
    edge_ai_shared_contract_bind_consumer(&g_edge_ai_transport, &g_edge_ai_backend);
    edge_ai_imu_mlp_classifier_init(&g_classifier);
}

void edge_ai_m55_consumer_poll(void)
{
    edge_ai_online_classifier_result_t result;

    if (edge_ai_online_classifier_process_once(&g_edge_ai_transport,
                                               &g_classifier,
                                               &result) == EDGE_AI_STATUS_OK)
    {
        rt_kprintf("[edge_ai_online] seq=%lu label=%s score=%d\r\n",
                   (unsigned long)result.sequence,
                   result.classification.label,
                   (int)(result.classification.score * 1000.0f));
    }
}
```

## 6. 为什么暂时不加 IPC notify

第一版可以先轮询共享块：

```text
M55 每 100 ms 尝试读一次。
读到 EMPTY 就跳过。
读到 READY 就推理并 ack。
```

这样调试简单，变量少。等轮询版稳定后，再加 MTB IPC notify，把“定时试探”改成“M33 发布后通知 M55”。

## 7. 验收现象

串口期望看到：

```text
[m33_edge_ai] producer init status=0 addr=0x261c0000
[m33_edge_ai] publish seq=1 count=8 channels=7
[edge_ai_online] seq=1 label=idle score=...
```

如果 M55 一直读不到数据，优先检查：

- M33 是否调用了 producer bind，也就是 format；
- M55 是否调用了 consumer bind，也就是 attach；
- 两边 `EDGE_AI_SHAREDMEM_VERSION` 是否一致；
- M33/M55 是否都使用 `0x261C0000`；
- M33 是否真的已经释放 M55 核。
