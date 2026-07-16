# M33-M55 EMG IPC 故障复盘与验证记录

日期：2026-07-17  
范围：PSoC E84 M33/M55 双核工程中的 EMG 窗口共享、M55 推理、结果返回 M33 及 CAN 提交链路  
结论：本轮只修复 M55 侧共享内存读取和诊断能力，没有修改电机控制、助力模式、轨迹规划、CAN 协议、M33 固件或蓝牙配对逻辑。

## 1. 用户可见现象

1. M33 能接收 CAN 帧，`0x7C2`、`0x321`、`0x322`、`0x180205FD` 等计数或反馈在变化。
2. 电机反馈可读取，但助力动作没有出现，容易把问题归因到 CAN RX 或控制线程。
3. M33 到 M55 的 EMG 流发布看似正常，但 M55 没有形成可见的模型返回。
4. GDB 暂停时经常落在 `idle_thread_entry()`。这只表示采样瞬间 CPU 没有可运行任务，本身不是 HardFault 或死锁证据。
5. Shell 偶发无法交互需要单独从串口占用、线程状态、中断风暴和栈破坏角度排查，不能仅凭停在 idle 线程判定系统死机。

## 2. 本轮诊断边界

本轮目标是先证明并修复以下最小闭环：

```text
M33 EMG 窗口
  -> 共享 SOCMEM + IPC 元数据
  -> M55 读取窗口并执行 TFLM 推理
  -> M55 发布模型结果
  -> M33 接收模型结果
  -> M33 将结果提交到 CAN 发送路径
```

本轮不把“CAN 提交成功”扩大解释为“外部 NanoPi 和云平台已经收到”。后两段仍需在 NanoPi 上通过 `candump` 和业务日志独立验证。

## 3. 关键误判与证据

### 3.1 最初怀疑缓存一致性

M55 原始诊断计数显示：

- `error_count=1053`
- `last_seq=0`
- `window_count=0`

这表示每个收到的流描述都在真正推理前被拒绝。由于 M33 写共享区、M55 读共享区，首先怀疑 M55 读到了旧的 header 或 payload，于是补充了 header/payload cache invalidate。

### 3.2 RT-Thread cache API 实际没有执行清缓存

反汇编确认，原先调用的 `rt_hw_cpu_dcache_ops()` 在当前 M55 配置中没有产生有效 cache 操作，只剩内存屏障。原因是集成 M55 工程的 `rtconfig.h` 没有启用对应 `RT_USING_CACHE` 路径。

因此改为在 M55 通信实现文件中直接调用 CMSIS：

- `SCB_InvalidateDCache_by_Addr()`
- `__DSB()`

这消除了“源码看起来调用了 invalidate，但编译结果没有执行”的配置依赖。

### 3.3 最终根因是 M55 共享对象链接到了错误内存

清缓存修复后，窗口仍全部被拒绝。进一步核对 ELF 符号和 linker map，发现：

- M33 使用的共享块地址是 `0x261C0000`。
- M55 的 `g_m33_m55_pcm_shared` 当时却链接在 `0x200012C0`，属于 M55 DTCM。
- C 代码使用了 `.cy_shared_socmem`，但当前 M55 linker script 明确映射的是 `.ipc_stream_shared (NOLOAD)`。
- 未被脚本接管的 orphan section 被链接器放入 DTCM，导致两个核心实际读写的不是同一块内存。

将对象 section 改为 `.ipc_stream_shared` 后，最终 ELF 符号为：

```text
261c0000 B g_m33_m55_pcm_shared
```

这是本次故障的决定性修复。

## 4. 提交记录

每一步均为独立提交，便于单独审查或回退：

| 提交 | 作用 | 风险范围 |
|---|---|---|
| `892f60c6` | M55 推理前校验空指针，并对共享 header/payload 做显式 invalidate | 仅 M55 EMG 输入读取 |
| `60a34555` | 记录 M55 模型结果发布成功数、失败数和最近返回值，增加 `mdl_stat` | 仅诊断，可单独回退 |
| `69b5aa3d` | 用实际生效的 CMSIS CM55 cache maintenance 替换配置相关的空操作 | 仅 M55 共享 PCM 读取 |
| `0f34ac92` | 将 M55 的共享 PCM 视图放入 linker script 管理的 `.ipc_stream_shared` | 仅共享对象放置，是根因修复 |

没有修改：

- M33 控制线程和 CAN RX 消费路径
- 助力、主动、抗阻状态机
- 电机限位、急停或轨迹规划
- MuJoCo 已完成的动作规划下发接口
- STM32F103 协议
- 蓝牙配对代码
- Wi-Fi、显示和云端业务逻辑

## 5. 构建与烧录范围

构建使用工程配置对应的 GNU Arm Embedded Toolchain 13.3 和 RT-Thread Studio SCons。

最终增量构建结果：

```text
scons: `.' is up to date.
scons: done building targets.
```

修复时的完整构建结果为：

```text
text=1723456 data=17500 bss=4532020 total=6272976
```

烧录只写入集成工程生成的 M55 `rtthread.hex`：

- 写入约 1,744,896 bytes
- verify 约 1,740,956 bytes
- 没有重烧 M33
- 没有覆盖 WHD/Wi-Fi 资源
- 没有改写电机或 F103 固件

OpenOCD 在 verify 和 shutdown 后出现的 KitProg acquire 提示发生在有效写入和校验完成之后，不等同于本次烧录失败。最终调试结束时未保留 OpenOCD/GDB 后台进程。

## 6. 板端验证结果

测试命令：

```text
cmd_m55_ipc_start
cmd_m55_emg_stream 1 20 0
cmd_m55_emg_stream 0 20 0
cmd_m55_emg_status
m55qa_status
```

运行中 M33 连续打印：

```text
[m55_model_bridge] ai seq=... model=2 result=1 conf=... flags=0x03 win=300 can_ret=0
```

该日志能分别证明：

1. M55 已经消费 EMG 窗口并产生推理结果。
2. 结果通过 IPC 返回 M33。
3. M33 将模型结果提交到 CAN 路径，接口返回 `can_ret=0`。

停止流后的最终状态：

```text
[m55_emg] running=0 samples=15 write=3 last_seq=235 have_seq=1
           windows=212 errors=0 dup=4 period=20 step=100
[m55qa] ipc_ready=1 tx_pending=0 rx_pending=0 has_model=1
[m55qa] model seq=392 code=2 result=1 conf=918/1000
         flags=0x03 window_ms=300
```

同时观察到：

- WebSocket 仍连接。
- IP 为 `192.168.3.32`。
- RSSI 为 `-42`。
- 显示初始化和刷新返回值正常。
- 测试 EMG stream 已停止，没有留下持续注入任务。

## 7. 当前能证明和不能证明的内容

### 已证明

- M33 和 M55 对共享 EMG 缓冲区使用同一物理地址。
- M55 能读取窗口并完成推理。
- M55 推理结果能返回 M33。
- M33 的 CAN 提交接口接受该结果。
- 本轮修复没有破坏当时在线的 Wi-Fi、WebSocket 和显示状态。

### 尚未证明

- NanoPi 物理 CAN 控制器一定收到每一帧。
- NanoPi 应用一定解析并上传每一条模型结果。
- 云平台一定完成持久化和前端展示。
- 当前模型对真实 EMG 意图的准确率满足控制要求。
- 助力模式无动作已经因此完全解决。助力链路还包含状态机、安全门限、故障位、控制线程和电机命令输出。

`can_ret=0` 只表示 M33 本地发送接口接收成功，不能替代总线抓包和上位机业务确认。

## 8. 下一轮建议测试

### 8.1 M33-M55 稳定性

1. 连续运行 30 分钟、2 小时、8 小时三档压力测试。
2. 每分钟记录窗口数、推理数、发布成功/失败数、IPC pending、heap 最低水位和线程栈高水位。
3. 验证序号单调性，区分重复、丢失、过期和乱序。
4. 在压力测试结束后确认 shell、Wi-Fi、显示和控制周期仍可响应。

### 8.2 CAN 到 NanoPi

1. NanoPi 先执行 `ip -details -statistics link show can0`，确认接口为 `UP` 且 bitrate 一致。
2. 使用 `candump -L can0` 记录原始帧和时间戳。
3. 将 M33 的模型 `seq` 与 NanoPi 接收序号逐条对账。
4. 同时记录 `bus-off`、error-passive、RX/TX dropped 和 restart 次数。
5. 再对账 NanoPi 应用日志及云端消息 ID，形成四段链路证据。

### 8.3 助力模式

按以下顺序逐层验证，避免直接改控制算法：

1. 模式切换命令是否被解析且只切换一次。
2. 控制状态机是否进入 ASSIST，并满足使能、急停、限位和故障门槛。
3. `fault=0x02` 的设备定义和清除条件必须从电机协议确认，不能长期无条件忽略。
4. 控制线程是否消费最新命令，命令 age 是否超时。
5. 最终输出的目标角度、速度和力矩是否非零且在限幅内。
6. CAN 实际发出的电机控制帧是否与目标一致。
7. 空载、低力矩、有人佩戴三个阶段逐步验证。

## 9. 仍需整改的工程问题

1. M33 IPC 目前复位后仍需手动执行 `cmd_m55_ipc_start`。自动初始化必须在完成启动顺序和失败重试测试后再开启。
2. EMG 流目前按测试命令启动，不应在未完成安全闭环前自动驱动助力。
3. 模型当前对测试信号持续给出 `result=1` 且置信度较高，这只能证明链路通，不证明分类正确，需要真实数据集和混淆矩阵验证。
4. EMG 结果必须作为高层意图输入，由 M33 安全状态机二次裁决，不能绕过限位、急停、故障和命令超时保护。
5. 双核共享结构应继续保持固定宽度类型、版本号、长度、序号和所有权规则；批量 payload 使用 cache line 对齐与 cache maintenance，控制元数据可采用单写单读序号协议，避免直接对大缓冲区加粗粒度锁。
6. 共享区 section 名称必须由两核 linker script 和代码共同约束，并在 CI 中通过 `nm`/map 检查地址，防止再次静默落入 orphan section。
7. CAN 工业化整改仍需补齐 bus-off 自动恢复、错误计数、消息 freshness、序号、心跳、发送队列背压、关键命令确认和安全降级。

## 10. 回退策略

四个源码提交相互独立，但根因修复依赖完整链路。若需要回退，应优先在测试分支逐个 `git revert`，不要使用 `reset --hard`。其中：

- `60a34555` 是纯诊断提交，可独立回退。
- `0f34ac92` 是共享地址根因修复，不建议单独回退。
- `69b5aa3d` 保证 cache invalidate 在当前 M55 配置中真实执行。
- `892f60c6` 让 EMG handler 在读取共享数据前执行必要校验和 invalidate。

回退后必须重新检查 `g_m33_m55_pcm_shared` 的 ELF 地址，并重新执行完整的 M33 -> M55 -> M33 验证。
