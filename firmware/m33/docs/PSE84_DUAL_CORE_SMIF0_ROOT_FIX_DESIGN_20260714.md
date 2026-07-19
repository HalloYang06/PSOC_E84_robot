# PSE84 双核 SMIF0 根治设计（2026-07-14）

> **实施状态更新（2026-07-15）：** 本文是根治方案的设计基线。最终确认旧 2 MiB FAL `0x60E00000..0x60FFFFFF` 越过 M55 Non-secure SMIF MPC 独占末端 `0x60FC0000`；故障现场 `BFAR=0x60FC0000`、`CFSR=0x00008200` 与越界首地址完全一致。当前 FAL 已重定位为 `0x60DC0000..0x60FBFFFF`，IPC1 channel 19 / interrupt 15、mailbox `0x261FFF00`、256 B program page 和 64 KiB erase sector 保持不变。Secure fault RAM 闭包、两核 I-Cache 静默、SMIF cache 完成轮询、GPU lifecycle gate 和 guard 有界等待均已落地。本板已完成实际烧录/verify、真实断电冷启动、10 次 reset、双核 Fault/LCD 心跳和受保护写擦验证；50 次物理冷启动、多板、温压满载及事务中掉电仍是发布验证边界。详细证据见 [实施与验证记录](../validation/PSE84_DUAL_CORE_SMIF0_ROOT_FIX_IMPLEMENTATION_20260714.md)。

## 1. 已确认的问题链

1. 旧 FAL 从 `0x60E00000` 起占 2 MiB，独占末端为 `0x61000000`；生成的 M55 Non-secure SMIF MPC 从 `0x60580000` 起长 `0x00A40000`，独占末端为 `0x60FC0000`。硬件在首个非法地址留下 `PRECISERR|BFARVALID` 和 `BFAR=0x60FC0000`，这是确定性的保护越界。
2. M33 和 M55 都从 SMIF0 外部 Flash 的 XIP 区执行代码。
3. 2026-07-14 02:57，M33 Secure 启动代码被改成永久关闭 I-Cache；02:58 的组合镜像包含了该改动。
4. 关闭 I-Cache 从机制上预计会增加 M33 对外部 Flash 的取指流量并改变竞争时序；它既不修复 MPC 越界，也不建立 command window 排他。
5. M55 的 FAL 同时使用 `Cy_SMIF_MemRead/Write/EraseSector()` 发起命令模式事务，但 PDL 只屏蔽 M55 本核中断，不能停止 M33 的 XIP 访问。
6. 实机上暂停 M33 后，卡在 `Cy_SMIF_PopRxFifo()` 的 M55 立即继续并完成 LCD/LVGL 初始化。停核同时改变 M33 的取指、中断和其他总线活动；该结果强烈支持共享 SMIF0 竞争模型，但不单独证明硅内部微观机理。
7. M55 FAL 还存在三个独立缺陷：`smif_context.timeout=0`、4KB 逻辑擦除粒度与 64KB 物理粒度不一致、任何 mount 失败都立即自动格式化。

## 2. 目标和非目标

目标：

- 双核同时运行时不再出现 XIP 与 SMIF 命令事务冲突。
- 任何 FAL 分区和资源烧录范围都不得越过 M55 Non-secure MPC 上界 `0x60FC0000`，也不得覆盖 M55 linker trailer。
- M33 I-Cache 保持开启，且不再复现之前的 XIP/缓存 HardFault。
- 文件系统失败不能阻塞 LCD，也不能触发无条件破坏性格式化。
- 所有握手和 SMIF 操作都有有限超时和可读取的状态计数。

非目标：

- 不通过永久关闭缓存规避问题。
- 不把跳过文件系统或延迟 LCD 当作根治。
- 不在运动控制运行期间执行会长时间停止 M33 XIP 的擦除操作。

## 3. 设计决定

### 3.1 恢复并正确维护 M33 I-Cache

Secure Reset Handler 按以下顺序执行：关闭 I-Cache、`DSB/ISB`、失效 I-Cache 与预取缓冲、等待完成、启用 ECC、重新开启 I-Cache、再次 `DSB/ISB`。SMIF 初始化或重新配置后，从 SRAM 代码失效 SMIF0 fast/slow XIP cache。

永久 cache-off 改动必须撤销；它只是当前问题的触发放大器，也会显著降低 M33 性能。

### 3.2 普通读取不进入命令模式

M55 FAL 的 read 使用 `0x60000000` XIP 映射窗口直接复制。两个核心的普通 XIP 读取由硬件仲裁，不再调用 `Cy_SMIF_MemRead()` 抢占命令 FIFO。

写入和擦除仍需命令模式，必须执行 3.3 的跨核握手。

### 3.3 跨核 SMIF0 所有权协议

在双方 linker 中保留同一个共享 SRAM、NOLOAD、32 字节对齐的控制块，包含 magic/version/boot_epoch、request/ack/release 序号、operation/result、timeout/error/counter。

M33 在启动 M55 之前完成以下动作：

1. 初始化控制块并安装专用 IPC 中断。
2. 中断向量位于 SRAM，完整中断处理和等待循环位于 `.cy_ramfunc`。
3. 标记 guard ready，随后才调用 `Cy_SysEnableCM55()`。

M55 写入或擦除时：

1. 获取 M55 本核 mutex 和专用硬件 IPC semaphore。
2. 写 request 序号并触发 M33 IPC 中断。
3. 有限等待 M33 的 ack；超时则返回错误，不进入 SMIF 命令事务。
4. M33 SRAM 中断关闭本核中断、执行屏障并回复 ack，然后只访问 SRAM 控制块等待 release。
5. M55 从 ITCM/RAM 执行完整 `Cy_SMIF_*` 调用链。
6. 操作结束后确认 SMIF 非 busy，失效 SMIF XIP cache，写 release。
7. M33 执行屏障并退出 SRAM 中断；双方释放锁。

M33 驻留循环和 M55 临界调用链都必须有独立硬件计时超时，不能依赖已被屏蔽的 SysTick。

### 3.4 实时安全约束

64KB sector erase 可能持续数百毫秒。运动控制处于 active 状态时，擦除请求直接返回 `-RT_EBUSY`；只允许在启动阶段或安全空闲状态执行。运行时持久化请求应排队到安全窗口。

### 3.5 修正 Flash/文件系统语义

- FAL 和 LittleFS 的 block size 从 4KB 改为该地址区域真实的 64KB。
- 分区边界继续保持 64KB 对齐。
- `smif_context` 使用明确的非零微秒超时。
- mount 失败先区分总线超时、空白介质和格式损坏。
- 只有确认介质为空且处于启动安全窗口，或用户执行显式维护命令时才允许 mkfs。
- 文件系统不可用时记录错误并继续 LCD/LVGL 初始化。

旧 4KB 几何写出的 LittleFS 数据不能假定可靠；首次迁移需要在完成仲裁后显式重建。

## 4. 失败处理

- guard 未 ready：M55 有限超时，跳过文件系统并继续 LCD。
- M33 ack 超时：不触碰 SMIF，返回 `-RT_ETIMEOUT`。
- SMIF 操作超时：双方保持在 SRAM/ITCM 安全路径，尝试恢复 XIP 和失效 cache；恢复失败则记录原因并执行受控整机复位，禁止返回 XIP 继续执行。
- mount 失败：不得自动格式化，也不得阻塞显示初始化。

## 5. 实施范围

- `secureCore`：修正 Secure Reset Handler 的 I-Cache 失效/重开顺序，并重新生成签名 HEX。
- M33：在 `board.c` 启动 M55 之前安装 guard；新增共享协议与 SRAM 中断实现；linker 固定其代码、栈和控制块位置。
- M55：修改 FAL 读取、写擦仲裁、真实擦除粒度和有限超时；修改 mount/mkfs 策略；linker 固定命令临界路径。
- 资源布局：把 FAL 及其全部子分区同步迁移到 `0x60DC0000..0x60FBFFFF`，烧录脚本和 OpenOCD launch 地址同步更新。
- 不直接修改自动生成的 QSPI memory-slot 参数；通过 wrapper、linker 和静态检查完成修复。

## 6. 验证标准

1. map 静态检查：M33 guard 完整调用链位于内部 SRAM；M55 命令临界调用链位于 ITCM/RAM；共享控制块两边地址一致且无重叠。
2. cache-on 下 M33 单核调度/传感器压力运行，连续观察 fault 寄存器为 0。
3. 双核高负载 XIP 下，M55 连续映射读取 10000 次并校验 CRC。
4. 64KB 擦除、跨页写入、重启读回通过，相邻 sector 哨兵不变。
5. 人为关闭 guard 响应时，M55 必须超时并继续点亮 LCD，不能卡在 `Cy_SMIF_PopRxFifo()`。
6. 运动状态下擦除必须被拒绝，安全空闲时才允许。
7. 连续冷启动至少 50 次：LCD 每次启动，M33/M55 CFSR、HFSR 均为 0，文件系统结果可诊断。

当前单板已经完成第 1、2、4、6 项的核心验收，并完成真实断电 1 次、系统 reset 10 次以及 guard 写擦闭环；第 3 项 10000 次 CRC、第 5 项故障注入、50 次物理断电、多板和温压长稳仍属于发布/量产门槛。因此可以声明“目标根因已修复且当前样板在已测场景稳定”，不能声明“完整量产验证已经结束”。
