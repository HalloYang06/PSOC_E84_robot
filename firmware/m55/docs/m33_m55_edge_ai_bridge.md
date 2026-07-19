# PSoC Edge E84 M33/M55 Edge AI 协同链路说明

## 目标

在 `Edgi_Talk_M33_LSM6DS3` 的 IMU 采样任务和本 M55 工程之间建立一条异步 AI 辅助链路：

- M33 侧采集 LSM6DS3 加速度/陀螺仪数据，按窗口写入共享 SoC RAM。
- M55 侧读取 IMU 窗口，运行轻量运动意图/风险评分模型，并把结果写回共享内存结果块。
- M33 侧消费 AI 结果，做有效位、超时、序号一致性校验后，仅作为康复控制状态机的辅助输入。
- AI 输出不直接绕过安全逻辑驱动电机，当前状态机始终保持 `motor_output_allowed = 0`，后续真实电机控制必须继续经过限位、急停、力矩/速度边界等安全门。

## 工程分工

| 工程 | 核心 | 角色 | 关键文件 |
| --- | --- | --- | --- |
| `Edgi_Talk_M33_LSM6DS3` | Cortex-M33 | IMU 生产者 + AI 结果消费者 + 康复控制安全门 | `applications/edge_ai/edge_ai_m33_producer.c`, `edge_ai_m33_consumer.c`, `rehab_control_sm.c` |
| `Edgi_Talk_M55_Blink_LED` | Cortex-M55 | AI 推理工作线程 + 结果发布者 | `applications/edge_ai_bridge/edge_ai_m55_worker.c` |

## 共享内存布局

共享 SoC RAM 基址：`0x261C0000`

| 区域 | 地址 | 方向 | 用途 | 魔数/版本 |
| --- | --- | --- | --- | --- |
| 输入块 | `0x261C0000 + 0x00000000` | M33 -> M55 | IMU 窗口，8 组样本，最多 16 通道 | `0x45414931`, version `2` |
| 结果块 | `0x261C0000 + 0x00001000` | M55 -> M33 | AI 推理结果、置信度、风险分数、有效标志 | `0x45414952`, version `1` |

结果块结构体在两个工程中保持同名同字段：

```c
typedef struct
{
    volatile uint32_t magic;
    volatile uint32_t version;
    volatile uint32_t state;
    volatile uint32_t source_sequence;
    volatile uint32_t result_sequence;
    volatile uint32_t valid_flags;
    volatile uint32_t model_id;
    volatile uint32_t result_class;
    volatile uint32_t confidence_permille;
    volatile uint32_t fatigue_permille;
    volatile uint32_t pain_risk_permille;
    volatile uint32_t latency_ms;
    volatile uint32_t producer_tick;
    volatile uint32_t commit_sequence;
} edge_ai_result_sharedmem_block_t;
```

## 状态与有效位

共享块状态：

- `EMPTY = 0`：可写或已消费。
- `WRITING = 1`：生产端正在写，消费端必须跳过。
- `READY = 2`：生产端提交完成，消费端可以读。

AI 结果有效位：

- `EDGE_AI_RESULT_FLAG_VALID`：M55 认为本次推理结果有效。
- `EDGE_AI_RESULT_FLAG_FRESH`：结果来自新的输入窗口。
- `EDGE_AI_RESULT_FLAG_AUX_ONLY`：结果只能作为辅助输入，不能直接作为电机命令。
- `EDGE_AI_RESULT_FLAG_TIMEOUT`：M55 超时后发布的无效/降级结果。
- `EDGE_AI_RESULT_FLAG_STALE_REJECTED`：输入窗口缺通道、尺寸异常或序号不一致，被拒绝。

## 读写时序

1. M33 的 LSM6DS3 采样流程调用 `edge_ai_m33_producer_push_imu_sample()` 累积 8 个样本。
2. M33 写输入块：先置 `WRITING`，写入 `sequence/sample_count/channel_count/channel_ids/samples`，再写 `commit_sequence = sequence`，最后置 `READY`。
3. M55 线程 `ai_m55` 轮询输入块；只有 magic/version/state/size/commit 全部通过才拷贝窗口。
4. M55 完成轻量模型计算后写结果块：先置 `WRITING`，写入 `source_sequence/result_sequence/valid_flags/confidence/risk`，再写 `commit_sequence = result_sequence`，最后置 `READY`。
5. M33 线程 `ai_m33` 读取结果块；只有 `commit_sequence == result_sequence` 且读前读后序号一致才接受快照。
6. M33 将结果送入 `rehab_control_sm_accept_ai_result()`，状态机再次检查 `VALID + AUX_ONLY`，拒绝 `TIMEOUT/STALE_REJECTED`，并保持电机输出门关闭。
7. M33 消费后 ACK 结果块，将状态置回 `EMPTY`。

## 超时与降级

- M55 超时：若已经见过输入窗口，但超过约 `1000 ms` 没有新 `source_sequence`，发布带 `EDGE_AI_RESULT_FLAG_TIMEOUT` 的结果。
- M33 超时：康复控制状态机超过约 `1000 ms` 未收到新结果，则进入 `REHAB_CONTROL_STATE_AI_TIMEOUT`，清除 `ai_valid`。
- 任一异常结果只会更新诊断状态，不会开启电机输出。

## IPC 边界说明

当前已经打通、可编译验证的闭环是“共享内存数据面 + 状态位/序号握手的异步控制面”。本 M55 工程原有 `applications/m33_m55_comm.c` 使用 MTB IPC queue，可用于语音/状态消息；但 M33 陀螺仪例程当前没有接入对应的 MTB IPC peer，因此本次 IMU/AI 链路没有强依赖硬件 IPC 中断队列唤醒。

如果简历或答辩中要严格写“共享内存 + MTB IPC 中断通知”，建议下一步补 M33 侧 MTB IPC peer，把 `READY` 结果写入后再发一个轻量通知；当前已经具备共享内存、状态标志、序号一致性、超时和安全门这些核心机制。

## 调试命令

M55 shell:

```text
m55_ai
```

显示 M55 已处理窗口数、最近源序号、结果序号、异常窗口数和超时状态。

M33 shell:

```text
rehab_ai
```

显示 M33 康复控制 AI 辅助输入状态、最近序号、分类、置信度和 `motor_allowed`。

## 验证记录

协议一致性测试：

```powershell
python tools\test_edge_ai_shared_contract.py
```

结果：通过，覆盖 M33/M55 两份 `edge_ai_result_contract.h` 的关键常量、字段和 C99 可编译性。

M33 构建：

```powershell
$env:PYTHONPATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\scripts\offline_packages\scons-4.10.0-py3-none-any.whl'
F:\RT-ThreadStudio\platform\env_released\env-new\tools\python-3.11.9-amd64\python.exe -m SCons -j8
```

结果：通过，生成 `rt-thread.elf` 和 `rtthread.hex`。

M55 构建：

```powershell
$env:PYTHONPATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\scripts\offline_packages\scons-4.10.0-py3-none-any.whl'
$env:RTT_EXEC_PATH='F:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin'
F:\RT-ThreadStudio\platform\env_released\env-new\tools\python-3.11.9-amd64\python.exe -m SCons -j8
```

结果：新增 `applications\edge_ai_bridge\edge_ai_m55_worker.o` 已成功编译；最终链接失败在工程既有 WiFi/LCD 诊断符号缺失，例如 `m55_sdio_kick_change`、`drv_lcd_get_init_result`、`g_mmcsd_diag_*`，与本次 AI bridge 新增文件无关。

## 简历表述建议

保守准确版：

> 基于 PSoC Edge E84 Cortex-M33/M55 异构双核与 RT-Thread，实现 M33 IMU 采样到 M55 轻量 AI 推理再回传 M33 控制状态机的共享内存异步链路；设计双向共享数据结构、状态标志、序号提交和超时/有效位校验，使 AI 输出作为康复控制辅助输入接入安全状态机，避免绕过安全逻辑直接驱动电机。

后续补齐 MTB IPC 通知后可强化为：

> 基于共享内存数据面和 MTB IPC 通知控制面，打通 PSoC Edge E84 M33/M55 异构核协同推理链路，实现 IMU 窗口发布、M55 端模型推理、M33 端结果校验与康复控制状态机安全接入。
