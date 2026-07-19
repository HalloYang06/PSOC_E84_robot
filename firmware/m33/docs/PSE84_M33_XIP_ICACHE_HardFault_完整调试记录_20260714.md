# PSE84 M33 XIP/ICACHE HardFault 完整调试记录与答辩手册

> **后续结论更新（2026-07-15）：** 本文保留为 M33 HardFault 的历史定位记录，其中“永久关闭 I-Cache”只是凌晨 3 点阶段性规避，不是最终方案。最终又闭合了一条确定性地址证据：旧 M55 FAL `0x60E00000 + 2 MiB` 延伸到 `0x61000000`，而 M55 Non-secure SMIF MPC 在 `0x60FC0000` 独占结束；旧现场 `BFAR=0x60FC0000`、`CFSR=0x00008200` 正好命中首个非法地址。当前实现把 FAL 移到 `0x60DC0000..0x60FBFFFF`，恢复 M33 I-Cache，并增加 CM33/CM55 SMIF0 所有权协议、Secure/RAM/ITCM 异常与命令闭包、GPU 静默和分层 cache 维护。新镜像已完成烧录/verify、真实断电冷启动、10 次 reset、双核 Fault/LCD 心跳和受保护写擦验证。当前结论以 [PSE84 双核 SMIF0/XIP 根因修复实施与验证记录](PSE84_DUAL_CORE_SMIF0_ROOT_FIX_IMPLEMENTATION_20260714.md) 为准。

> **历史措辞边界：** 本文主体按定位时间线保留。后文出现的“最终 cache-off”“最终 workaround”“CA_EN=0 稳定”等词，只表示 2026-07-14 当时实验阶段的最后状态，不代表当前交付固件。当前交付固件已重新启用 I-Cache；不能从历史段落摘一句“关闭 cache”当作现行修复。

> 日期：2026-07-14
> 工程：Edgi_Talk_M33_Blink_LED（CM33 Non-secure）与 secureCore（CM33 Secure）
> 芯片：PSE846GPS2DBZC4A，silicon revision B0
> RTOS：RT-Thread 5.0.2
> 当前处置状态：目标根因已修复，当前样板在已执行场景下通过；多板、50 次物理冷启动、温压满载、长时 endurance 和事务中掉电恢复仍待发布验证

阅读路线：

- 只看最终结论：第 0、6、7、10 节；
- 复盘完整定位过程：第 2 至 9 节；
- 准备面试答辩：第 13、14、19、20 节；
- 准备量产验证：第 11、15、16 节；
- 查源码和官方资料：第 17、18 节。

---

## 0. 先给结论

本节第 1～8 点是当时 cache-off 阶段如何解释 M33 `UNDEFINSTR/Lockup` 的历史结论。当前最终结论在其上增加了 FAL/MPC 越界的硬件闭环，并已撤销“永久关闭 I-Cache”。当前 firmware 的根治不是单一 cache 开关，而是“合法地址布局 + 跨核 command window guard + RAM/ITCM 闭包 + 分层 cache 维护”。

这次问题不是 RT-Thread 调度器、sensor 模块或 <code>rt_thread_mdelay()</code> 自身造成的共同故障。它们只是不同实验中最先踩到坏指令取值的“受害位置”。

已经闭合的证据链是：

1. M33 从外部 Flash 的 C-AHB/CBUS XIP 地址执行代码。
2. 故障时，同一物理 Flash 偏移在 C-AHB cached/XIP 视图中返回整行 <code>0xFFFFFFFF</code>，而 S-AHB/SBUS raw 视图仍返回与镜像一致的正确机器码。
3. Cortex-M33 执行错误的 <code>0xFFFF</code> Thumb 半字后产生 <code>UNDEFINSTR</code>，现场为 <code>CFSR=0x00010000</code>。
4. 该可配置异常升级为 HardFault，现场为 <code>HFSR=0x40000000</code>，即 <code>FORCED</code>。
5. Secure HardFault handler 自身也位于同一外部 XIP 取指路径，而且它所在的 C-AHB 行同样读成全 <code>0xFFFFFFFF</code>。由于当次 AIRCR、VTOR/vector 与 EXC_RETURN 原值没有完整落盘，“fault 进入 Secure handler 后再次取到坏指令”应标为最符合现场的强推断，而不是已经直接记录到的完整异常轨迹。
6. 核心最终进入 Lockup，调试器看到当前 <code>PC=0xEFFFFFFE</code>。这个值是 Lockup 状态，不是最初出错代码的 PC，不能拿它去做 <code>addr2line</code>。
7. 单变量 A/B 实验显示：在本板、本固件和本烧录流程中，只要 <code>ICACHE0.CTL.CA_EN=1</code> 就快速复现；<code>CA_EN=0</code> 时，在已经完成的回归窗口内不再出现该故障。
8. 最终在 Secure Reset 最早阶段关闭 CM33 instruction cache，失效 cache 与 C-AHB prefetch buffer，且不再重新开启 cache。XIP 没有关闭，代码仍直接从外部 Flash 执行。

最准确的工程表述是：

> 历史阶段确认了 cached XIP 故障域并用 cache-off 获得可复现规避；最终阶段又以 `BFAR=0x60FC0000 == MPC end` 证明旧 FAL 越界，并用 FAL 重定位和跨核 SMIF guard 替代 cache-off。精确到跨核竞争在硅内部的 FIFO/prefetch/bridge 微观失效机理，仍需 Infineon 资料才能进一步细分。

不能写成：

- “已经证明 RT-Thread 调度链表坏了”；
- “已经证明 sensor 的 mutex 有 bug”；
- “已经修复芯片内部物理根因”；
- “五分钟不崩，所以量产绝对稳定”；
- “关闭 cache 就是关闭 XIP”。

---

## 1. 文档中的证据等级

为了避免把推断写成事实，本文使用四种证据等级。

| 等级 | 含义 | 本案例示例 |
|---|---|---|
| A：可静态复核 | 当前仓库文件、ELF、map、反汇编、寄存器头文件、构建脚本可以重新核对 | 最终符号地址、Secure Reset 清 CA_EN、镜像 SHA-256 |
| B：调试会话现场 | 本次 OpenOCD/调试终端中实际读到，但原始完整日志没有单独落盘 | cached 行全 F、raw 行正确、60 秒 loop_count=598 |
| C：受控实验结论 | 只改一个变量并重复观察得到 | cache on/off、prefetch 四象限、HF3 降频 |
| D：机理推断或待确认 | 由 A/B/C 证据推导，但没有厂商内部设计资料 | 可能是 refill/coherency/C-AHB/SMIF 交互问题 |

特别说明：本次 2026-07-14 的部分 OpenOCD 原始终端输出没有保存为独立日志文件。因此本文会如实写成“调试会话记录”，不伪称所有运行态数据都能从当前仓库静态复算。后续复验应把完整 OpenOCD stdout/stderr、镜像 hash 和时间戳一起归档。

---

## 2. 系统结构与必须先懂的术语

### 2.1 XIP 是什么

XIP 是 Execute In Place。它表示程序代码没有在启动时整体复制到 SRAM，而是由 CPU 直接从映射到地址空间的外部 Flash 取指执行。

本次最终方案只是清除了 CM33 I-cache 的 <code>CA_EN</code>：

- 外部 Flash 仍保持 memory-mapped；
- C-AHB XIP 地址仍可被 CPU 取指；
- 程序仍然是 XIP；
- 变化只是每次取指不再命中 CM33 instruction cache，性能可能下降。

因此“关闭 I-cache”和“关闭 XIP”是两个完全不同的动作。

### 2.2 同一片外部 Flash 的四个地址别名

本工程 BSP 的 memory map 给出了以下别名：

| 安全域 | C-AHB/CBUS 视图 | S-AHB/SBUS raw 视图 | 典型用途 |
|---|---:|---:|---|
| Non-secure | <code>0x08000000</code> | <code>0x60000000</code> | C-AHB 通常用于执行；S-AHB 用于 raw 读写/编程 |
| Secure | <code>0x18000000</code> | <code>0x70000000</code> | Secure C-AHB 执行；Secure S-AHB raw 访问 |

地址换算只需要保持物理 offset 不变。例如：

~~~text
Secure C-AHB: 0x181042B0 - 0x18000000 = 0x001042B0
Secure S-AHB: 0x701042B0 - 0x70000000 = 0x001042B0
~~~

所以 <code>0x181042B0</code> 与 <code>0x701042B0</code> 指向同一片外部 Flash 的同一物理偏移，只是访问路径不同。

这正是本次定位的关键：如果 raw 视图正确、C-AHB 视图错误，就不能再优先怀疑 Flash 物理内容被擦空。

### 2.3 CM33 I-cache 寄存器

| 项目 | Non-secure/system alias | Secure alias | 含义 |
|---|---:|---:|---|
| ICACHE0 base | <code>0x42223000</code> | <code>0x52223000</code> | CM33 instruction cache 控制块 |
| CTL | base + <code>0x00</code> | base + <code>0x00</code> | cache/prefetch 控制 |
| CMD | base + <code>0x08</code> | base + <code>0x08</code> | invalidate 命令 |
| STATUS0 | base + <code>0x80</code> | base + <code>0x80</code> | 状态 |

关键位：

| 位 | 掩码 | 含义 |
|---|---:|---|
| <code>CTL.PREF_EN</code> | <code>0x40000000</code> | prefetch enable |
| <code>CTL.CA_EN</code> | <code>0x80000000</code> | instruction cache enable |
| <code>CMD.INV</code> | <code>0x00000001</code> | invalidate cache |
| <code>CMD.BUFF_INV</code> | <code>0x00000002</code> | invalidate C-AHB prefetch buffer |

最终稳定态读到 <code>CTL=0x40000000</code>，它的精确含义是：

- <code>CA_EN=0</code>：I-cache 关闭；
- <code>PREF_EN=1</code>：prefetch 位仍开；
- 不能把它解释成“XIP 关闭”。

还要避免混淆另一个 SMIF cache 硬件块。本文所说的最终修复对象是 CM33 <code>ICACHE0</code>，不是位于另一寄存器区域的 SMIF cache。

### 2.4 HardFault 现场中三个不同的 PC

调试 Cortex-M 异常时，至少要区分：

1. **当前 core PC**：调试器 halt 时核心正在或试图执行的位置。
2. **第一次异常 stacked PC**：异常入口由硬件压栈的原始程序 PC。
3. **嵌套异常 PC**：fault handler 自身再次异常时的现场。

本次 <code>PC=0xEFFFFFFE</code> 是核心进入 Lockup 后的状态值，不是第一次故障地址。正确的源码定位对象是第一次有效异常帧中的 stacked PC，而且必须使用与当次烧录镜像严格匹配的 ELF。

### 2.5 CFSR 与 HFSR

<code>CFSR=0x00010000</code>：

- bit 16 是 <code>UNDEFINSTR</code>；
- 表示处理器尝试执行未定义指令；
- 它本身不能直接证明 cache 坏，因为错误函数指针、栈破坏、跳转到数据区也可能造成相同结果。

<code>HFSR=0x40000000</code>：

- bit 30 是 <code>FORCED</code>；
- 表示一个可配置 fault 被升级为 HardFault；
- 单看该位不能决定异常来自 Secure 还是 Non-secure。

只有把 fault 状态、stacked PC、对应机器码、cached/raw 对照和 CA_EN A/B 放在一起，才能形成因果闭环。

### 2.6 EXC_RETURN 与堆栈选择

异常入口 LR 保存的是 <code>EXC_RETURN</code>。其中的位用于判断：

- 返回到哪个安全域；
- 使用 MSP 还是 PSP；
- basic frame 还是带扩展上下文的 frame。

本工程 Non-secure RT-Thread 的汇编 HardFault veneer 使用 <code>EXC_RETURN bit 2</code> 选择 MSP/PSP，这是正确的基本方向。

Secure 启动文件中的 <code>S_HardFault_Handler</code> 对 Secure 来向检查了 LR bit 2，但对 Non-secure 来向使用 <code>CONTROL_NS.SPSEL</code> 来选择 <code>MSP_NS/PSP_NS</code>。这会降低复杂嵌套场景下的现场采集可靠性。更稳妥的做法是：在无普通 C prologue 的 naked assembly veneer 中第一时间保存 <code>EXC_RETURN</code>，再完全依据它选择原始栈。

这是诊断基础设施的改进项，不是本次 cache 故障的根因修复。

---

## 3. 硬件、软件与构建身份

### 3.1 环境

| 项目 | 记录 |
|---|---|
| MCU | PSE846GPS2DBZC4A |
| silicon | B0 |
| target voltage | 调试会话约 1.82 V |
| RT-Thread | 5.0.2，<code>RT_VER_NUM=0x50002</code> |
| OpenOCD | Infineon build <code>0.12.0+dev-5.50.0.3639</code> |
| KitProg3 firmware | 2.10.878 |
| SROM Boot | 2.0.0.6022 |
| RRAM Boot | 2.0.0.7127 |
| Extended Boot | 1.1.0.1700 |
| NS 工程 | <code>F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED</code> |
| Secure 工程 | <code>F:\RT-ThreadStudio\workspace\secureCore</code> |

### 3.2 最终产物 SHA-256

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| NS <code>Debug/rtthread.elf</code> | 3,072,520 B | <code>43EB5C0FAC1D2C38903BD8D4C0F993CAF2734BF270304E4C18E01E52C62AD582</code> |
| NS <code>Debug/rtthread.bin</code> | 470,904 B | <code>BA576F0DC27EA7B47A32CE04E70AFF38603D6D32016BB83B1689BFD9E86C4125</code> |
| 组合烧录 <code>Debug/rtthread.hex</code> | 1,612,742 B | <code>2F1366C77DB3A302B87B4ADA9BB45461B200336742EF3E3928F0C14887172F6F</code> |
| 仅供 alias 校验的 <code>Debug/rtthread_xip_verify.hex</code> | 1,612,742 B | <code>3F625C5BE146B9308AD14C1F017CFE2891404F7A450B04F13C434BEDC15656FF</code> |
| Secure <code>Debug/rtthread.elf</code> | 1,042,796 B | <code>C736C6A9F32C6513F00AF45E54AB389A3B60720CE303A37E0743735F239E0F54</code> |
| Secure <code>Debug/rtthread.hex</code> | 288,182 B | <code>557F82A01A42F0632BEED490D291434F6704CD4E56B8C8BAD4A4D435A89B095F</code> |
| NS 工程内复制的 signed Secure HEX | 288,182 B | <code>557F82A01A42F0632BEED490D291434F6704CD4E56B8C8BAD4A4D435A89B095F</code> |
| Secure <code>Debug/rtthread.bin</code> | 101,384 B | <code>D272BE827E858311D049C7C2856601C892715CA4C224B403E0095BF6E39B02DB</code> |

### 3.3 最终 ELF 关键符号

Non-secure <code>Debug/rtthread.elf</code>：

| 符号 | 地址 |
|---|---:|
| <code>rt_schedule_insert_thread</code> | <code>0x08379FE0</code> |
| <code>rt_schedule</code> | <code>0x0837A084</code> |
| <code>rt_schedule_remove_thread</code> | <code>0x0837A25C</code> |
| <code>rt_thread_sleep</code> | <code>0x0837A800</code> |
| <code>rt_thread_mdelay</code> | <code>0x0837A960</code> |
| <code>rt_timer_check</code> | <code>0x0837AF9C</code> |
| <code>HardFault_Handler</code> | <code>0x0837B342</code> |
| <code>rt_hw_hard_fault_exception</code> | <code>0x0837B418</code> |
| <code>Reset_Handler</code> | <code>0x08385038</code> |
| <code>sensor_update_latest</code> | <code>0x08390794</code> |
| <code>main</code> | <code>0x0839BE30</code> |
| <code>rt_current_thread</code> | <code>0x240C168C</code> |
| <code>g_rt_hw_fault_dump</code> | <code>0x240C1A50</code> |
| <code>g_m33_boot_marker</code> | <code>0x240CCD50</code> |
| <code>g_runtime</code> | <code>0x240CCDC4</code> |

Secure <code>Debug/rtthread.elf</code>：

| 符号 | 地址 |
|---|---:|
| <code>__s_vector_table</code> | <code>0x18100400</code> |
| <code>SysLib_FaultHandler</code> | <code>0x1810429C</code> |
| <code>S_HardFault_Handler</code> | <code>0x181042BA</code> |
| <code>S_Reset_Handler</code> | <code>0x18104364</code> |
| <code>init_cycfg_clocks</code> | <code>0x181031BC</code> |
| <code>init_cycfg_peripheral_clocks</code> | <code>0x1810334C</code> |

### 3.4 一个非常重要的 ELF 陷阱

工程根目录还存在 2026-07-13 的旧 <code>rt-thread.elf</code>、map 和 HEX。旧 ELF 中：

- <code>main=0x08383A74</code>；
- <code>rt_schedule=0x08397DF4</code>；
- 与最终 <code>Debug/rtthread.elf</code> 完全不同。

因此：

- 不能使用工程根目录旧 ELF 解析最终烧录现场；
- 不能使用 2026-07-14 最终 ELF 反向解析更早实验的地址；
- 每次故障记录必须绑定当次 ELF/HEX hash。

具体例子：历史记录曾写“<code>stacked PC=0x0837A030</code> 位于 <code>rt_list_remove</code>”。但在最终 Debug ELF 中，<code>0x0837A030</code> 实际位于 <code>rt_schedule_insert_thread</code> 内，是更新 ready priority group 的 <code>orrs</code> 附近；最终 ELF 中 <code>rt_schedule</code> 内联的 list remove 在约 <code>0x0837A0F8</code> 以后。

所以本文只保留如下严谨结论：

> 历史构建的 stacked PC 曾被当时的调试记录解析到 scheduler/list 路径；由于对应历史 ELF/hash 没有完整归档，不能拿最终 ELF 对该旧地址做确定源码行声明。

---

## 4. 调试时间线：每一步为什么做、又推翻了什么

### 4.1 第一阶段：先区分 minimal 与 normal

早期为了缩小启动路径，曾使用 minimal 模式和临时 marker。后来明确：

- <code>M33_XIAOZHI_MINIMAL_FRAMEWORK</code> 已改为 <code>0</code>；
- minimal 定位用的临时 marker 已清理；
- 当前测试对象是正常框架固件。

某次早期观察中 <code>g_m33_boot_marker=0</code>、<code>g_runtime=0</code>，一度推断为“可能在 main 前故障”。这个结论后来被更可靠的分段 marker 实验推翻：固件可以进入 <code>main()</code>，且到达 main 时 fault 寄存器仍为零。

这里的经验是：marker 为零只说明“没有观察到该写入”，并不自动证明 main 前崩溃。还必须确认：

- marker 代码确实编入了当前镜像；
- 读的是正确地址和正确 ELF；
- reset 类型没有清掉该变量；
- marker 写点覆盖了真实路径；
- 不是异步中断或另一安全域先 fault。

### 4.2 第二阶段：确认正常框架初始化完成

细化 marker 后观察到：

~~~text
0x33010002
~~~

它表示已经进入 <code>m33_init_framework()</code>，并越过最前面的 M55 IPC auto-init 开关。

继续在初始化链中插入临时 marker，最终观察到：

~~~text
0x33500009
~~~

当时的 marker 布局表明以下正常初始化步骤都已经返回：

- sensor；
- input；
- control；
- CAN；
- safety；
- HTTP；
- openclaw。

这排除了“某个初始化函数同步卡死在里面”的简单解释，但仍不能排除初始化过程早先破坏了内存、随后才暴露。

### 4.3 第三阶段：把窗口缩到正常主循环

主循环每一步增加临时 marker 后，故障前最后观察到：

~~~text
0x34100009
~~~

它位于本轮循环末尾、进入 <code>rt_thread_mdelay(FRAME_PERIOD_MS)</code> 之前。结合当时回溯，第一次重点怀疑：

~~~text
SysTick_Handler
  -> rt_timer_check
  -> main thread sleep timeout
  -> rt_schedule
  -> ready-list remove
~~~

当前线程指针为 main；定时器节点地址 <code>0x240CD32C</code> 落在 main 线程对象的 <code>thread_timer</code> 内。这解释了为什么 main 的 sleep timeout 会经过该路径，也降低了“定时器节点完全指向随机内存”的概率。

但这仍只是受害现场，不是根因证明。

### 4.4 第四阶段：用忙等做单变量反证

为了验证 <code>rt_thread_mdelay()</code> 是否为必要条件，只把主循环末尾 sleep 改成忙等，其余逻辑尽量保持不变。

结果：

- HardFault 没有消失；
- 故障反而提前；
- marker 变成 <code>0x34100002</code>；
- 现场落到 <code>sensor_update_latest()</code> 附近。

这一步很关键，因为它推翻了“sleep/SysTick/调度器是必要根因”的假设。

合理解释变成：

- sleep 改变了执行节奏；
- 也改变了指令 cache line 的访问和 refill 顺序；
- 去掉 sleep 后，另一段更早执行的 XIP 代码先踩到坏取指；
- scheduler 和 sensor 是不同时间点的受害者。

如果 sleep 真是充分根因，移除它后故障应该消失，或至少继续出现同一种确定的调度数据结构破坏；实际并非如此。

### 4.5 第五阶段：读取 RT-Thread fault dump

Non-secure 工程中：

~~~text
g_rt_hw_fault_dump = 0x240C1A50
~~~

RT-Thread 的 HardFault C 处理函数会先写入 magic、EXC_RETURN、PC、LR、CFSR、HFSR 等现场。

干净复现后读取 32 个 word，结构仍全零。

严格结论只能是：

> Non-secure RT-Thread 的 fault capture 没有成功完成。

它不能单独证明：

- “没有发生 HardFault”；
- “Secure HardFault vector 一定无效”；
- “异常一定没进入任何 handler”。

可能原因包括：

- fault 被路由到 Secure；
- 尚未进入 NS handler；
- Secure handler 自身再次 fault；
- dump 写入前已进入 Lockup。

因此后续转向同时检查 Secure/Non-secure SCB、向量表、handler 机器码和 XIP 别名。

### 4.6 第六阶段：从“软件受害点”转向“取指路径”

历史忙等实验的一次有效异常帧记录为：

~~~text
stack frame @ 0x240CDB18
r0   = 0x240C6090
r1   = 0xFFFFFFFF
r2   = 0x00000002
r3   = 0x0000FFFF
r12  = 0x0000005A
lr   = 0x083905CD
pc   = 0x08376EB0
xPSR = 0x01000000
~~~

当时与该构建匹配的符号记录将：

- <code>0x08376EB0</code> 识别到 <code>_rt_mutex_take</code>；
- <code>0x083905CD</code> 识别到 <code>sensor_update_latest()</code>。

注意：这些是历史构建地址，不允许用现在的最终 ELF 重新解释。

真正决定方向的不是函数名，而是同一地址的两条硬件访问路径：

~~~text
NS C-AHB/XIP  0x08376EB0:
FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF ...

NS S-AHB/raw  0x60376EB0:
4FF0E92D 4691B087 46049103 ...
~~~

这说明：

- 外部 Flash 物理内容存在；
- raw 路径仍能读到正确机器码；
- CPU 执行使用的 C-AHB/XIP 视图返回了擦除态样式的错误数据；
- 软件最终在哪个函数触发，取决于哪一条坏 cache line 先被执行。

### 4.7 第七阶段：Secure handler 也暴露在同一故障域

最终 Secure ELF 中：

~~~text
S_HardFault_Handler = 0x181042BA
~~~

故障会话读取其所在的 32-byte 对齐区域：

~~~text
Secure C-AHB/XIP  0x181042B0..0x181042CF:
FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF
FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF

Secure S-AHB/raw  0x701042B0..0x701042CF:
80BD80B4 00AF00BF FDE780B4 00AF1EF0
400F08D0 1EF0040F 0CBFEFF3 0880EFF3
~~~

这两个窗口的物理 offset 都是 <code>0x001042B0</code>。

已经直接证实的是：Secure handler 的代码位于 XIP，而且它对应的 C-AHB 行在故障会话中错误、raw 行正确。

本次没有完整保存 AIRCR 异常目标配置、VTOR/vector、S/NS 分银行 fault 状态和入口 EXC_RETURN 的同一时刻原值，所以还不能声称已经逐指令记录到“CPU 确实 vector 到该 Secure handler”。最能解释全部现场的**强推断模型**是：

~~~mermaid
flowchart LR
    A["NS 代码从 C-AHB/XIP 取指"] --> B["某个 cache/XIP 行返回 0xFFFFFFFF"]
    B --> C["执行无效 Thumb 半字"]
    C --> D["CFSR.UNDEFINSTR"]
    D --> E["HFSR.FORCED / HardFault"]
    E -.-> F["强推断：进入 Secure fault 处理"]
    F --> G["Secure handler 也从 C-AHB/XIP 取指"]
    G --> H["handler 所在行同样返回 0xFFFFFFFF"]
    H --> I["异常处理过程中再次 fault"]
    I --> J["Lockup，当前 PC=0xEFFFFFFE"]
    J --> K["NS g_rt_hw_fault_dump 保持未填充"]
~~~

<code>PC=0xEFFFFFFE</code> 是 Lockup 最终状态，不是“程序普通跳转到了 0xEFFFFFFE”。它与上述异常递归模型相容，但不能单靠这个 PC 反向证明完整路由链。

---

## 5. 假设与单变量实验矩阵

### 5.1 为什么要做矩阵

只看到“cache off 后不崩”还不够。可能同时变化的因素包括：

- prefetch；
- cache 中残留旧行；
- cache 开启时机；
- SMIF transaction merge；
- M33 核心频率；
- SMIF MMIO/group 时钟；
- 外部 MemorySPI 时钟；
- debugger reset 流程。

因此每次只改变一个可控变量，并记录寄存器 readback、marker、loop_count 和 fault 状态。

### 5.2 实验结果总表

| 编号 | 唯一主要变量 | 条件/寄存器变化 | 结果 | 能支持的结论 | 不能扩大成 |
|---|---|---|---|---|---|
| E01 | 原始 cache-on | <code>CA_EN=1</code> | 快速 HardFault/Lockup | 建立基线 | 不能单独证明 cache 内部机理 |
| E02 | prefetch off | cache on，<code>PREF_EN=0</code> | 仍故障 | prefetch 不是必要条件 | prefetch 模块绝对无任何问题 |
| E03 | prefetch on | cache on，<code>PREF_EN=1</code> | 仍故障 | cache-on 问题不依赖 prefetch 开关 | 同上 |
| E04 | cache off + prefetch on | <code>CA_EN=0, PREF_EN=1</code> | 稳定 | CA_EN 是当前可观测触发门 | 已证明终身稳定 |
| E05 | cache off + prefetch off | <code>CA_EN=0, PREF_EN=0</code> | 稳定 | prefetch 不是 cache-off 稳定的必要条件 | — |
| E06 | 先 invalidate 再开 cache | 等待 cache/buffer invalidate 完成后 <code>CA_EN=1</code> | 仍故障 | 不是一次性旧 cache line 残留 | invalidate 指令本身坏 |
| E07 | 延迟开启 cache | Secure 初始化完成、到 NS Reset 附近再开 | 仍故障 | 不是仅由 Secure 早期初始化顺序产生的一次污染 | 所有启动顺序都已穷尽 |
| E08 | 关闭 SMIF DEVICE1 merge | <code>0x8000A001 -> 0x80000001</code> | cache-on 仍故障 | merge 不是必要条件 | SMIF 整体完全无关 |
| E09 | M33 HF0 降频 | 约 200 MHz 降到 100 MHz，cache-on | 仍故障 | 不是单纯 CPU 过快 | 排除所有电源/时序问题 |
| E10 | PERI1/GROUP1 降频 | <code>0x44004040</code> divider field 1 -> 3，cache-on | 仍故障 | 降低 SMIF MMIO/group IP path 未解决 | 它等同于外部 Flash SCK |
| E11 | HF3/MemorySPI 降频 | <code>0x4240124C: 0x80000100 -> 0x80000300</code>，约 200 -> 100 MHz 源；接口约 100 -> 50 MHz | 30 秒窗口内 cache-on 仍于 <code>loop_count=1</code> Lockup | 单纯外部接口频率过高不是充分解释 | 排除一切板级信号完整性问题 |
| E12 | 最终 cache-off | Secure Reset 清 CA_EN，invalidate cache/buffer，不重开 | 10/10 reset、60 秒、5 分钟窗口内无 fault | workaround 对已复现故障模式有效 | 量产寿命已经证明 |

### 5.3 prefetch 四象限

| CA_EN | PREF_EN | 结果 |
|---:|---:|---|
| 1 | 0 | 故障 |
| 1 | 1 | 故障 |
| 0 | 0 | 稳定 |
| 0 | 1 | 稳定 |

在当前测试边界内，结果随 <code>CA_EN</code> 变化，而不是随 <code>PREF_EN</code> 变化。因此可以说：

> CA_EN 所启用的 CM33 cached C-AHB XIP 路径是本次故障出现的必要可观测条件。

不能说：

> 已经由四次测试证明 cache SRAM 的某个 transistor 损坏。

### 5.4 invalidate 为什么不够

invalidate 只清理“现在已经存在”的 cache line 和 prefetch buffer。只要后面重新开启 cache，就会再次发生 line refill。

如果问题位于 refill、cache/C-AHB 一致性或后续访问路径，那么：

~~~text
invalidate
  -> 当前旧行被清除
  -> CA_EN 重新开启
  -> 后续 refill 再次生成错误行
  -> 故障复现
~~~

因此“invalidate 后仍故障”和“cache 永久关闭后稳定”是相互一致的。

### 5.5 两条 SMIF 相关时钟必须分清

早期分析中曾把两条时钟混在一起，后来通过生成配置纠正。

第一条是 SMIF MMIO/PERI group 路径：

- <code>APP_MMIO1.SMIF0</code> 位于 PERI1、group 1、slave 2；
- 根时钟为 HF1；
- 调整 group divider 后，cache-on 仍故障。

第二条是 MemorySPI/外部串行接口的 <code>clk_mem</code>：

- 生成配置中 <code>CYBSP_SMIF_CORE_0_XSPI_FLASH_clock_ref.inst_num=3</code>；
- MemorySPI HAL config 绑定该 clock ref；
- HF3 配置为 200 MHz；
- SMIF 配置使用 <code>CY_SMIF_DLL_DIVIDE_BY_2</code>；
- 因而原接口时钟约为 100 MHz；
- 把 HF3 源从约 200 MHz 降到约 100 MHz 后，接口约降到 50 MHz；
- cache-on 仍于 <code>loop_count=1</code> 进入同类 Lockup。

严谨结论是：

> 两条相关时钟路径的降频都没有使 cache-on 恢复稳定，故“单纯时钟过高”没有得到实验支持。

仍然不能无限扩大成：

> 已经排除所有温度、电压、信号完整性、跨时钟域或电源完整性因素。

---

## 6. 根因边界与置信度

| 结论 | 置信度 | 依据 |
|---|---:|---|
| scheduler 不是共同根因 | 高 | 忙等去掉 sleep 后故障仍存在且受害点漂移 |
| sensor 不是共同根因 | 高 | sensor 与 scheduler 是不同受害点，共同因素是 XIP 取指 |
| raw Flash 内容正确 | 很高 | raw/S-AHB 返回机器码，烧录 raw verify 通过 |
| C-AHB cached/XIP 路径能返回错误行 | 很高 | 同一 offset 的 cached/raw 直接对照 |
| <code>CA_EN=1</code> 是当前场景的必要触发门 | 很高 | on/off 重复 A/B 与 prefetch 四象限 |
| prefetch 是必要条件 | 已否定 | cache-on/prefetch-off 仍故障 |
| 一次性旧 cache line 是充分原因 | 已否定 | invalidate 并等待完成后仍故障 |
| SMIF merge 是必要条件 | 已否定 | merge off 仍故障 |
| 原始 M33/HF3 频率过高是充分原因 | 已否定 | 两类降频后 cache-on 仍故障 |
| 精确内部 silicon 失效机制 | 未知 | 缺少芯片内部观测和厂商勘误 |
| cache-off workaround 对当前故障模式有效 | 高 | 多次 reset 与长于原复现窗口的运行 |
| 已证明量产终身稳定 | 不能声称 | 尚缺多板、冷启动、温压、满负载和长期统计 |

仍可能的内部机理包括：

- cache tag/data line 或 ECC 相关行为；
- refill 状态机；
- C-AHB 与 SMIF bridge 的一致性/握手；
- cache maintenance 与启动配置交互；
- B0 silicon 的未公开限制；
- 软件未满足某条尚未识别的硬件初始化约束。

这些目前都是候选，不是已证实结论。

---

## 7. 最终 Secure workaround

### 7.1 修改位置

文件：

<code>F:\RT-ThreadStudio\workspace\secureCore\libs\TARGET_APP_KIT_PSE84_EVAL_EPC2\COMPONENT_CM33\COMPONENT_SECURE_DEVICE\s_start_pse84.c</code>

函数：

<code>S_Reset_Handler()</code>，约第 422 至 452 行。

### 7.2 实际动作

逻辑顺序：

~~~text
进入 Secure Reset
  -> 关闭中断
  -> 清 ICACHE0.CTL.CA_EN
  -> DSB
  -> ISB
  -> 写 CMD = INV | BUFF_INV
  -> DSB
  -> 有界等待 CMD 两位清零
  -> 超时则进入明确 dead loop
  -> DSB
  -> ISB
  -> 后续不再置 CA_EN
  -> 继续正常 Secure/Non-secure 启动
~~~

关键代码语义：

~~~c
ICACHE0->CTL &= ~ICACHE_CTL_CA_EN_Msk;
__DSB();
__ISB();

ICACHE0->CMD = ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk;
__DSB();
while ((ICACHE0->CMD &
       (ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk)) != 0U)
{
    /* bounded timeout */
}
__DSB();
__ISB();

/* Do not set CA_EN again. */
~~~

寄存器手册指出 <code>INV</code> 已具有失效 cache 与 buffer 的语义，因此写 <code>3</code> 带有一定冗余；但它明确表达“cache line 与 prefetch buffer 都失效”的工程意图，当前没有证据表明该冗余会造成问题。

### 7.3 最终 ELF 反汇编交叉核验

对 SHA-256 为 <code>C736C6A9...</code> 的最终 Secure ELF 反汇编：

| 地址 | 已核验动作 |
|---|---|
| <code>0x18104364</code> | <code>S_Reset_Handler</code> 入口 |
| <code>0x18104378</code> | 清除 CTL 的 CA_EN 位 |
| <code>0x1810438C</code> | 向 CMD 写入 <code>3</code> |
| <code>0x181043BA</code> 附近 | 以 mask <code>3</code> 检查 invalidate 命令完成 |

后续没有重新设置 CA_EN。即使启用可选 ECC 的代码会再次读改写 CTL，它也只 OR 入 ECC 位，不会把已经清除的 CA_EN 恢复。

### 7.4 DSB 与 ISB 的作用

- DSB 保证之前的 cache control/maintenance 和内存系统操作在继续前完成。
- ISB 使后续取指在新的 cache 状态和刷新后的流水线语义下进行。

barrier 不是“万能修复”。它们只保证控制寄存器修改与后续取指之间的顺序。

### 7.5 为什么放在 Secure Reset

- Secure Reset 是 CM33 应用启动最早且统一的控制点；
- 可以在进入大量 NS XIP 代码之前清除 CA_EN；
- 不依赖 sensor、scheduler 或业务线程是否已启动；
- 所有正常框架路径都共享该硬件配置。

仍存在一个需要厂家确认的窗口：Boot ROM 到执行这段应用代码之前是否已经使用 cache，以及能否从 boot 配置一开始就禁用。当前上电和 reset 测试说明该窗口在现有样本上可通过，但还不是对所有冷启动条件的形式化证明。

### 7.6 为什么这是永久规避而不是微观根因修复

它永久避开了已经确认会失效的 cached 取指路径，所以对当前产品固件不是临时 marker 或一次性清 cache。

但它没有改变芯片内部导致坏行的物理原因。最准确的分类是：

- 对已复现软件故障路径：确定性 workaround/containment；
- 对芯片内部根因：尚未修复、尚未精确确认；
- 对产品发布：可以作为当前基线，但必须补性能和环境回归。

---

## 8. 构建、签名、烧录和校验闭环

### 8.1 为什么不能只看“烧录成功”

PSE84 M33 包含 Secure 与 Non-secure 两套映像。错误的 Secure 文件、旧 ELF、未更新 signed HEX 或只校验 raw 地址，都会制造“代码看起来改了，板上却没运行”的假象。

### 8.2 当前 wrapper 的流程

入口：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_m33_verified.ps1
~~~

脚本执行：

1. 构建 Secure <code>Debug</code>；
2. 执行 Secure post-build；
3. 把 Secure 生成的 signed HEX 复制到 NS 工程的组合映像输入目录；
4. 构建 Non-secure；
5. 执行 Non-secure post-build，生成组合烧录 HEX；
6. 生成只用于 alias 校验的 XIP HEX：
   - <code>0x60000000 -> 0x08000000</code>；
   - <code>0x70000000 -> 0x18000000</code>；
7. OpenOCD 通过 raw/S-AHB 范围写入并 verify；
8. invalidate CM33 cache/buffer；
9. 通过 C-AHB aliases 校验组合镜像；
10. reset 到 Non-secure Reset handler；
11. 读取 <code>ICACHE0.CTL</code> 并断言 <code>CA_EN=0</code>；
12. resume 运行。

### 8.3 “XIP verify”的准确含义

alias verify 发生时 cache 已关闭/失效。因此它证明：

- C-AHB 地址映射可以访问正确外部 Flash 内容；
- raw 与 C-AHB alias 在该受控状态下一致；
- 映像 relocation 和地址窗口没有配错。

它不证明：

- cache 开启后的 line refill 一定正确；
- cache-on 长时间运行稳定。

所以本文把它称为“C-AHB alias verify”，不把它夸大为“cache line fill verify”。

### 8.4 flash loader 的未闭合混杂项

wrapper 实际使用 OpenOCD bundled loader：

| FLM | 大小 | SHA-256 |
|---|---:|---|
| OpenOCD bundled <code>PSE84_SMIF.FLM</code> | 489,412 B | <code>BD640BA1F3A21D20348CB59C91ED5E7393BE119BFB3F4ACFA6F6A5F1123A4AFE</code> |
| 工程 GeneratedSource <code>PSE84_SMIF.FLM</code> | 492,716 B | <code>C83D2E216F469BEF8347A180821A9BA6EF7BD6EDE63258ECA5B8B0314290FAC2</code> |

两者不同，尚未完成同条件 A/B。

为什么当前不把 FLM 当首要根因：

- raw verify 通过；
- raw 运行时内容正确；
- cache-off 时同一物理镜像可以稳定执行；
- cache-on/off 与故障高度相关。

但证据管理上仍应把 FLM A/B 列为未闭合项，不能假装它已经被完全排除。

---

## 9. 可信 OpenOCD 调试会话

### 9.1 推荐顺序

~~~text
启动新的 OpenOCD 会话
  -> init
  -> reset init
  -> targets cat1d.cm33
  -> cat1d::reset_halt cm33_ns reset
  -> 记录运行前 S/NS fault status
  -> 只设置一个实验变量并 readback
  -> resume
  -> 等待目标自行运行/故障
  -> halt 一次
  -> poll
  -> 读取 marker、loop、thread、S/NS SCB
  -> 读取原始栈帧
  -> 读取 cached/raw 对应窗口
  -> 保存完整 stdout/stderr 和镜像 hash
~~~

在这个 target 脚本下，可靠的核心序列是：

~~~tcl
init
reset init
targets cat1d.cm33
cat1d::reset_halt cm33_ns reset
~~~

### 9.2 会污染现场的操作

- attach 到正在运行的目标，<code>halt</code> 失败后又直接 <code>resume</code>；
- 同一会话连续重复 <code>cat1d::reset_halt</code>，中间没有 <code>reset init</code>；
- target 仍在错误 core 或错误安全域时读取寄存器；
- OpenOCD 已报告 Secure/AP access denied，却把填充值当成真实内存；
- fault 后再次 resume，然后把二次异常当作第一次异常；
- 用 sticky 的旧 CFSR/HFSR 判断本轮结果；
- 用旧 ELF 做 <code>addr2line</code>。

OpenOCD shutdown 后偶尔出现的“failed to acquire device”如果发生在所有读写已完成且进程 exit code 为 0 之后，应与真正的编程/访问失败分开判断。

### 9.3 每次现场必须保存什么

~~~text
测试编号与时间
板号、芯片 revision、Vtarget
Secure/NS ELF 与 HEX SHA-256
OpenOCD、KitProg3、FLM 版本与 hash
reset 类型
实验前后寄存器值与 readback
当前 PC/LR/xPSR、DHCSR/DFSR
SCB_S 与 SCB_NS 的 CFSR/HFSR/SHCSR
SFSR/SFAR、MMFAR/BFAR
VTOR_S/VTOR_NS、AIRCR
MSP/PSP/MSP_NS/PSP_NS
EXC_RETURN 与原始异常帧
marker、loop_count、rt_current_thread
cached 与 raw 对齐窗口
完整终端 stdout/stderr
~~~

---

## 10. 最终验证结果与边界

### 10.1 已完成的运行验证

最终 cache-off 构建的调试会话记录：

| 验证 | 观察 |
|---|---|
| 10 次 reset | 10/10 进入正常运行窗口；每轮约 2 秒、约 18 loop，无 fault |
| 60 秒运行 | <code>loop_count=0x256=598</code>；marker <code>0x33010002</code>；current thread 有效；CFSR/HFSR 为 0 |
| 5 分钟单会话 | halt 时核心正常位于 SysTick 上下文；CFSR/HFSR 为 0；NS dump 未出现 fault magic；<code>CTL=0x40000000</code> |
| 30 秒恢复测试 | <code>loop_count=0x12A=298</code>；fault status 为 0；随后 resume 并保持运行 |

为什么稳定运行时 marker 仍是 <code>0x33010002</code>：

- 当前正常路径只保留了框架入口附近的粗 marker；
- 后续历史细 marker 已清理；
- 正常模式后续不再更新该粗 marker；
- 因此稳定时保持 <code>0x33010002</code> 是代码设计结果，不代表停在该行。

### 10.2 物理断电的准确表述

开发板在最终阶段前经历过物理断电并重新插入，证明硬件重新上线、补丁映像随后可以烧录和运行。

但第一次调试命令在插回后执行了 <code>reset init</code>。因此现有记录不能夸大成：

> 已经保存了一次完全不受调试器 reset 影响、从上电第一条应用指令起连续观察的冷启动日志。

量产前仍应补：

- 自动上电；
- 不先 reset；
- 延迟连接调试器或由外部心跳判定；
- 多次完整 power cycle；
- 保存每次启动状态。

### 10.3 “稳定”应该怎么回答

可以回答：

> 在当前单板、室温、约 1.82 V、当前业务负载和已完成的 10 次 reset/60 秒/5 分钟窗口中，最终 workaround 稳定，且显著超过 cache-on 的快速复现窗口。

不能回答：

> 已经证明所有板、所有温压、所有负载、整个产品寿命绝不再出问题。

---

## 11. 关闭 I-cache 的影响

### 11.1 预期影响

- 外部 XIP 代码不再从 CM33 I-cache 命中；
- SMIF/C-AHB 取指和等待周期增加；
- 外部总线占用和功耗可能上升；
- 高频 ISR、音频、网络、IPC、加密/算法热点可能变慢；
- 已搬到内部 SRAM/TCM 的代码影响较小。

### 11.2 598 loop / 60 s 能证明什么

它只能证明当前约 10 Hz 主循环仍能保持预期节拍。

它不能证明：

- 最坏 ISR latency 没增加；
- 音频没有 underrun；
- CPU idle 不变；
- 网络吞吐不变；
- watchdog margin 不变；
- 所有实时 deadline 都满足。

主循环包含固定 delay 时，loop_count 本身对执行时间劣化并不敏感。

### 11.3 发布前性能回归

至少应补：

- DWT cycle counter 测关键函数；
- 最大值与 99.9% ISR latency；
- RT-Thread CPU idle 和线程运行时间；
- 音频 underrun/overrun；
- IPC deadline；
- 网络吞吐；
- CAN 满负载；
- watchdog margin；
- sensor + control + audio + network 的最坏组合负载。

---

## 12. 官方文档与 errata 结论

截至 2026-07-14 的公开资料检索，没有找到 PSE84/E84 或 Cortex-M33 r1p0 的公开 erratum，明确描述“CM33 I-cache/C-AHB XIP 整行返回 <code>0xFFFFFFFF</code>，需关闭 CA_EN”这一现象。

这只能说明：

> 当前没有可公开引用的匹配勘误。

它不能说明：

> 芯片一定没有未公开问题。

公开资料能支持的部分包括：

- 外部 SMIF 的 C-AHB alias 会经过 CM33 I-cache，S-AHB/raw 是不同路径；
- <code>CA_EN=0</code> 禁用 instruction cache；
- cache invalidate 与 buffer invalidate 的寄存器语义；
- 当前名义上的外部 Flash 读协议/频率配置处于器件规格范围；
- 公开 PDL/DSL release notes 没有找到匹配修复。

建议向 Infineon MyCase 提交：

- PSE846 B0 完整型号；
- 最小可复现镜像；
- Secure/NS ELF、HEX hash；
- C-AHB 全 F、S-AHB 正确的同 offset dump；
- CA_EN/prefetch 四象限；
- invalidate、延迟开启、merge、HF0、HF3 降频结果；
- Secure handler 二次 fault/Lockup 强推断模型；
- 询问未公开 B0 erratum、boot cache 行为和正式量产 workaround。

---

## 13. 严苛面试官问答

下面的问题不是让人死记寄存器，而是检查能否把“现象、证据、实验和结论边界”讲清楚。

### 13.1 ARM 异常与现场基础

#### Q1：XIP 是什么？关闭 I-cache 后为什么仍然叫 XIP？

XIP 是直接从映射的非易失存储器取指。关闭 <code>CA_EN</code> 只让取指不再使用 CM33 I-cache，代码没有整体搬到 SRAM，外部 Flash 仍被 memory-map，所以仍然是 XIP。

#### Q2：<code>CFSR=0x00010000</code> 精确表示什么？

它是 <code>UFSR.UNDEFINSTR</code>。处理器执行了未定义指令。它只描述异常类型，不直接描述坏指令来自 cache、错误跳转还是返回地址破坏；必须结合 PC 和机器码继续证明。

#### Q3：<code>HFSR=0x40000000</code> 精确表示什么？

它是 <code>HFSR.FORCED</code>，表示一个可配置 fault 被升级成 HardFault。原因可能涉及异常未使能、优先级/路由或异常处理中再次 fault。单看它不能判定安全域。

#### Q4：为什么不能把 <code>0xEFFFFFFE</code> 丢给 addr2line？

Armv8-M 在 Lockup 时可把 PC 表现为该状态值。它不是普通代码地址，也不是第一次异常的 stacked PC。拿它做符号化只会得到无意义结果。

#### Q5：怎样可靠还原第一次异常帧？

handler 入口先保存 LR/EXC_RETURN；由 EXC_RETURN 判断安全域、MSP/PSP 和 basic/extended frame；再读取硬件压栈的 R0-R3、R12、stacked LR、stacked PC、xPSR。还要检查栈范围、对齐、xPSR T 位和 PC 是否落在可执行区。

#### Q6：stacked PC 一定是根因位置吗？

它通常是“触发异常的指令位置”，但不一定是“最早制造问题的位置”。例如内存早先被破坏，可能到函数返回或链表操作才爆炸。本次靠同地址 cached/raw 机器码差异才把触发点提升为取指路径证据。

#### Q7：为什么实验开始前要记录 CFSR/HFSR？

fault status 位可能具有粘滞性，reset 类型也可能不同。必须有 before/after，才能确认状态属于本轮运行，而不是上一轮 debugger 操作留下的。

#### Q8：“当前线程是 main”到底说明什么？

只说明 halt/异常时 RT-Thread 的 current thread 指向 main。中断和 Secure fault 都可以打断 main；它不能证明 main 代码、main 栈或 main timer 就是根因。

### 13.2 marker、回溯与受害点

#### Q9：marker 停在某值，为什么不能直接说下一函数有 bug？

marker 只证明最后一个成功写入的检查点。下一时刻可能执行下一句，也可能被中断、切换线程或进入 Secure 异常。marker 用于缩小时间窗口，不能独立定根因。

#### Q10：<code>0x33500009</code> 证明了什么？

证明当时 marker 覆盖的 sensor/input/control/CAN/safety/HTTP/openclaw 初始化链走到了末端检查点。它排除同步卡死，但不能单独排除初始化早先造成的延迟性破坏。

#### Q11：为什么当时怀疑 <code>rt_thread_mdelay()</code>？

最后 marker 位于 mdelay 前，历史 stacked frame 又在 SysTick、timer timeout、schedule 路径。这是合理假设，所以用忙等替换 mdelay 做必要条件实验。

#### Q12：忙等后为什么反而排除了 sleep 是共同根因？

去掉 sleep 后 fault 仍然出现，只是位置和时间改变。如果 sleep 是必要条件，移除后故障应消失。结果说明 sleep 主要改变执行时序和 cache 访问序列。

#### Q13：忙等后落在 sensor，为什么不能立即认定 sensor 有 bug？

这会再次把受害点当根因。scheduler 与 sensor 逻辑无关，但都从同一 XIP 路径执行；共同硬件路径比“两个模块同时有相同 bug”更能解释现场漂移。

#### Q14：怎样区分 <code>rt_list_remove()</code> 数据指针坏与指令取值坏？

先检查节点地址、前后指针、线程对象范围，再检查 fault PC 的机器码。如果 ELF/raw 指令正确而 C-AHB 同地址为全 F，应优先判断取指损坏；如果指令一致但寄存器内链表指针非法，再追数据破坏。

#### Q15：main timer 节点确实属于 main 对象，这条证据有什么价值？

它解释了为何 main sleep timeout 合法进入 timer/scheduler 路径，并排除“timer 指向完全随机对象”的部分假设；它不能证明调度器就是根因。

#### Q16：为什么最终稳定运行 marker 还是 <code>0x33010002</code>？

当前源码只保留框架入口附近的粗 marker，正常路径后面不再更新。历史细 marker 已删除，所以它是“最后一个保留写点”，不是“程序卡住点”。

### 13.3 TrustZone、fault 路由与异常递归

#### Q17：<code>g_rt_hw_fault_dump</code> 全零能否证明没发生 HardFault？

不能。它只证明 NS RT-Thread 的 capture routine 没成功填完。fault 可能路由到 Secure，或 Secure handler 在写 NS dump 之前就再次 fault。

#### Q18：判断 HardFault 最终进入哪个安全域，应检查什么？

检查 SCB_S/SCB_NS 的 CFSR、HFSR、SHCSR，AIRCR 中异常目标配置，VTOR_S/VTOR_NS 与 HardFault vector，SAU/IDAU/MPU 属性，以及 handler 入口 EXC_RETURN 和实际使用的 S/NS MSP/PSP。

#### Q19：怎样区分“HardFault vector 错”与“handler 代码取指失败”？

先读 vector 项，确认地址、Thumb 位和安全属性；再用匹配 Secure ELF 解析；最后对 handler 入口做 C-AHB/raw 对照。本次已确认 handler 所在的 C-AHB 行变成全 F，但没有把当次 vector 原值完整落盘，所以“handler 取指失败”是强解释，不冒充完整路由轨迹的直接证据。

#### Q20：为什么 Secure handler 会产生二次异常？

handler 代码也在外部 XIP。**如果**第一次 fault 被路由到该 handler，CPU 仍需通过问题路径取指；已观察到的坏 handler 行会使它再次 fault并可能进入 Lockup。这是当前最强解释模型，仍需 AIRCR、VTOR/vector 和入口 EXC_RETURN 的同次快照最终确认。

#### Q21：为什么 NS dump 为零与 Secure 二次 fault 是相容的？

NS dump 只有在 NS 汇编 veneer 和 C capture routine 被正常执行后才会写入。若异常进入 Secure 且 handler 自身先坏掉，NS dump 会保持零；因此二者相容，但“dump 为零”本身不能证明这条路由确实发生。

#### Q22：当前 Secure handler 的采栈设计还有什么风险？

它是普通 C 函数中的 inline assembly，编译器 prologue 可能先动 SP/寄存器；NS 来向又用 CONTROL_NS.SPSEL 推断 MSP_NS/PSP_NS。更稳健的方案是位于内部 SRAM/TCM 的 naked assembly veneer，以 EXC_RETURN 为唯一堆栈选择依据。

#### Q23：为什么 fault handler 最好不和业务代码共用 XIP 故障域？

诊断代码共享同一失效模式，会在最需要它时不可用。量产级 fault island 应把 vector、最小 handler、dump buffer 和必要输出放到可靠内部存储区。

### 13.4 cached/raw 证据与因果实验

#### Q24：本次最强的直接证据是什么？

同一物理 Flash offset，在故障时 C-AHB/XIP 读出整行 <code>0xFFFFFFFF</code>，S-AHB/raw 同时返回正确机器码；Secure 和 Non-secure 都观察到相同路径差异。

#### Q25：如何证明两个 alias 是同一物理位置？

引用 BSP/器件 memory map，并分别减去 alias base，得到相同 offset。例如 <code>0x181042B0-0x18000000</code> 与 <code>0x701042B0-0x70000000</code> 都是 <code>0x001042B0</code>。

#### Q26：怎么排除 Flash 没烧好或已经被擦空？

raw 地址能读到正确机器码；raw verify 通过；raw 内容与 signed/combined image 一致；cache-off 后同一片 Flash 可持续执行。如果 Flash 真空白，raw 路径也应主要返回擦除态。

#### Q27：怎么排除 ELF 不匹配造成的假结论？

Secure 地址只用当次 Secure ELF，NS 地址只用当次 NS ELF；保存 ELF/HEX SHA-256；区分 signed、combined、XIP-verify 文件；历史地址不使用最终 ELF 强行解释。

#### Q28：怎么排除 OpenOCD 访问失败后用 F 填充输出？

检查是否有 AP/security access error，使用正确 target/domain，重复读取相邻有效区和 raw 区，并要求结果与核心 fault、CFSR 和 CA_EN A/B 闭环。单次带 access denied 的 <code>mdw</code> 不算证据。

#### Q29：为什么 CA_EN A/B 比 marker 更有说服力？

marker 只说明时间位置；CA_EN 直接控制被怀疑的硬件路径。同镜像、同负载下 cache-on 快速复现、cache-off 超过复现窗口，且与 cached/raw 差异相互印证。

#### Q30：prefetch 四象限的结论是什么？

cache on 时 prefetch 开关都 fault；cache off 时 prefetch 开关都稳定。所以 prefetch 不是必要条件，CA_EN 是当前故障门。不能由此宣称 prefetch 内部绝无任何缺陷。

#### Q31：为什么 invalidate 后仍 fault 很重要？

它排除了“仅是烧录前遗留一条旧 cache line”的简单解释。前提是命令确实写入、busy 位确实等到清零。

#### Q32：延迟到 NS Reset 再开 cache 仍 fault 说明什么？

说明问题不是只在 Secure 早期初始化瞬间产生的一次污染；只要后续启用 CA_EN，运行中仍可复现。

#### Q33：merge off 仍 fault 说明什么？

只说明 SMIF transaction merge 不是必要条件。外部数据仍由 SMIF 提供，不能扩写成“SMIF 完全无关”。

#### Q34：降低 M33 HF0 后仍 fault 说明什么？

降低了核心侧执行/取指压力，削弱“CPU 只是跑得太快”的解释；它不等同于降低外部 Flash SCK。

#### Q35：最容易混淆的两条 SMIF 时钟是什么？

HF1/PERI1/group1 是 SMIF MMIO/group IP path；MemorySPI 的 clock ref 是 <code>inst_num=3</code>，即 HF3。两条路径都分别降频测试过。

#### Q36：真正的外部接口降频实验结果是什么？

HF3 control 从 <code>0x80000100</code> 改为 <code>0x80000300</code>，源约 200 降到 100 MHz；结合 DLL /2，接口约 100 降到 50 MHz。readback 后 cache-on 仍在 <code>loop_count=1</code> 进入同类 Lockup。

#### Q37：降到约 50 MHz 仍 fault，能否排除所有时序问题？

不能。它只证明降低这条 MemorySPI 时钟没有让 cache-on 恢复。板级信号完整性、温压、电源和内部跨时钟问题不能被无限扩大地排除。

#### Q38：这些实验能把根因定位多细？

可以定位到“CA_EN 启用的 CM33 cached C-AHB XIP 取指路径”。没有厂商资料时，不能进一步指定为 tag RAM、data RAM、refill FSM 或某个 silicon transistor。

### 13.5 workaround、性能和量产结论

#### Q39：最终代码到底改了什么？

Secure Reset 入口关中断、清 CA_EN、DSB/ISB、发出 cache/buffer invalidate、有界等待完成、再次 DSB/ISB，并且后续不重新置 CA_EN。

#### Q40：为什么 DSB/ISB 都需要？

DSB 保证之前的 cache control/maintenance 完成；ISB 刷新取指流水线，使后续指令按新状态执行。它们保证顺序，不修复坏硬件路径。

#### Q41：最终 <code>CTL=0x40000000</code> 怎么解释？

bit31 CA_EN 为 0，I-cache 关闭；bit30 PREF_EN 为 1。该状态已经有 cache-off/prefetch-on 稳定实验。它不代表 XIP 关闭。

#### Q42：这是根本解决还是绕过？

对已复现产品故障路径，是持久、确定性的规避；对芯片内部物理原因，是 workaround，不是微观根因修复；对量产稳定性，还需环境和统计验证。

#### Q43：为什么永久关 cache 有效，而 invalidate 一次无效？

invalidate 之后还会 refill；如果 refill/访问路径会再次产生坏行，问题会重现。永久清 CA_EN 才停止使用该失效路径。

#### Q44：Secure 禁 cache 的代码本身也位于 XIP，是否有早期风险窗口？

有。从 Boot ROM 到执行清 CA_EN 之前仍可能使用 XIP/cache。当前启动测试给出经验置信度，更强的设计是由 boot 配置一开始禁用，或把最早禁用例程放入可靠内部存储；这需要厂家确认。

#### Q45：怎样防止后续 HAL 升级又把 cache 打开？

静态搜索所有 ICACHE0 CTL 写入；在 board/HAL 初始化后读回；诊断构建周期断言 CA_EN 为 0；把“不得重开 CM33 I-cache”写入发布配置约束和回归测试。

#### Q46：关闭 I-cache 的主要性能代价是什么？

外部 XIP 取指等待增加，总线占用和功耗可能上升，高频 ISR、音频、网络、IPC 和计算热点可能变慢。SRAM/TCM 热点受影响较小。

#### Q47：598 loops / 60 s 能证明没有性能影响吗？

不能。它只证明约 10 Hz 主循环仍达标；固定 delay 会掩盖函数执行时间增长。必须测 cycle、deadline、ISR latency、idle 和 underrun。

#### Q48：性能验证至少测什么？

DWT cycles、最大/99.9% ISR latency、RT-Thread idle、线程 runtime、音频 underrun/overrun、IPC deadline、网络/CAN 吞吐和 watchdog margin，并组合最坏业务负载。

#### Q49：五分钟不崩能否称为稳定？

可以说显著超过原 cache-on 快速复现窗口，支持 workaround 有效；不能等同于量产寿命验证。稳定结论必须附板数、次数、温压、负载和时长。

#### Q50：10 次 reset 与 10 次完整断电有什么区别？

reset 可能保留部分电源域、SMIF、cache 或时钟状态；完整断电会重新经历 ROM boot 和电源时序。二者必须分别统计。

#### Q51：怎样证明板上运行的是最终修复镜像？

保存 source diff 与 Secure/NS ELF/HEX hash；检查 Secure ELF 反汇编；烧录后 raw/alias verify；运行时读 CTL、CMD、marker、loop 和 fault status。仅有“program success”不够。

#### Q52：什么条件下才能重新打开 cache？

厂家给出正式配置/workaround 或新 stepping 修复；在目标温压、镜像和完整业务下完成严格 A/B；或者把关键代码搬入内部 SRAM/TCM 并重新设计故障隔离。不能只因为 HAL 升级就试着恢复。

---

## 14. 面试官最容易攻击的逻辑漏洞

| 错误说法 | 正确说法 |
|---|---|
| marker 停在 sensor 前，所以 sensor 崩了 | marker 只限定最后完成点，异步异常和其他安全域仍可能发生 |
| stacked PC 在 scheduler，所以 RT-Thread 链表坏了 | 它是受害现场；忙等后位置漂移，取指路径证据才是共同解释 |
| PC 是 <code>0xEFFFFFFE</code>，程序跳飞到了该地址 | 这是 Lockup 当前状态，不是第一次 stacked PC |
| 当前线程是 main，所以 main 栈溢出 | main 只是当前线程；需检查真实异常帧和栈水位 |
| NS dump 全零，所以没有 HardFault | 只说明 NS capture 未完成 |
| UNDEFINSTR 自身证明 cache 坏 | 还需同地址错误机器码、raw 正确和 CA_EN A/B |
| raw 正确自动证明 cache 坏 | 还要确认 alias、ELF、安全域和 OpenOCD 无访问错误 |
| cache on 崩、off 不崩一次就够了 | 需要重复 A/B、控制其他变量并有直接 cached/raw 证据 |
| invalidate 后仍崩，所以 invalidate 指令坏 | 更合理的是后续 refill 再次生成坏行，前提是命令确实完成 |
| prefetch 位还开，所以 cache 没关 | CA_EN 与 PREF_EN 是独立位；最终 CA_EN 明确为 0 |
| PERI1 divider 就是外部 Flash SCK | PERI1/group 与 HF3 MemorySPI 是两条不同路径 |
| 约 50 MHz 仍崩，所以排除所有时序问题 | 只排除“降低该时钟即可解决” |
| merge off 仍崩，所以 SMIF 完全无关 | 只排除 merge 是必要条件 |
| 没有公开 erratum，所以肯定不是 silicon 问题 | 只能说没有公开匹配记录 |
| 关闭 cache 是修复芯片内部根因 | 它是持久绕开故障路径 |
| 5 分钟和 10 次 reset 证明量产稳定 | 只证明当前窗口，仍需多板、冷启动和温压 |
| 10 Hz loop 正常，所以性能没损失 | 固定 delay 掩盖执行时间，需专门测实时指标 |
| 任意 ELF 都能解析 XIP 地址 | 必须使用与当次镜像、安全域匹配的 ELF |
| reset 等同于断电重插 | 两者经历的硬件初始状态不同 |
| 有 fault dump 结构就一定能捕获 | handler 与故障同域、C prologue 和错误 SP 选择都可能让捕获失败 |

---

## 15. 量产前尚未闭合的事项

### 15.1 P0：必须完成

- 至少多块 PSE846 B0 板做同镜像复验；
- 每块板执行完整断电冷启动循环，而不只是 debugger reset；
- 保存每轮 OpenOCD/串口/外部心跳原始日志；
- 高低温、供电上下限和业务满负载；
- 性能 deadline 与 watchdog margin；
- 静态与运行时防止 CA_EN 被重新开启；
- 向 Infineon 提交 MyCase，获取正式 workaround 结论。

### 15.2 P1：强烈建议

- 把 Secure/NS fault veneer 与最小 dump island 放到内部 SRAM/TCM；
- Secure handler 完全依据 EXC_RETURN 选 SP；
- 为每个实验自动归档 ELF/HEX/FLM hash；
- 完成 bundled FLM 与 project FLM 的同条件 A/B；
- 设计无调试器干预的上电心跳/故障记录；
- 将 cache-off 约束做成自动静态检查和板级 smoke test。

### 15.3 P2：架构优化

- 把高实时热点搬入 SRAM/TCM；
- 对外部 XIP 与内部 fault island 做明确 linker 分区；
- 评估能否只让非关键代码 XIP；
- 在拿到厂家正式方案后评估恢复 cache 的条件与回归矩阵。

---

## 16. 可复用的 Cortex-M33 HardFault 检查清单

### 16.1 第一次抓现场

- [ ] 不立即 resume；
- [ ] 记录当前 PC/LR/xPSR 与 debug lockup 状态；
- [ ] 记录 SCB_S 和 SCB_NS；
- [ ] 保存 EXC_RETURN；
- [ ] 按 EXC_RETURN 选择正确安全域和 MSP/PSP；
- [ ] 读取硬件基本异常帧；
- [ ] 验证栈地址、对齐和 xPSR T 位；
- [ ] 保存 marker、loop、current thread；
- [ ] 保存完整终端日志。

### 16.2 符号化

- [ ] 确认地址属于 Secure 还是 Non-secure；
- [ ] 使用当次烧录对应 ELF；
- [ ] 保存 ELF SHA-256；
- [ ] 用 map/nm/objdump/addr2line 交叉检查；
- [ ] 历史地址不拿当前 ELF 强行解释；
- [ ] 区分 current PC、stacked PC 和 nested-fault PC。

### 16.3 外部 XIP 怀疑项

- [ ] 算出 C-AHB 与 S-AHB 的同物理 offset；
- [ ] 读取对齐 cache line，而不只读一个 word；
- [ ] 检查 OpenOCD 是否报告安全访问错误；
- [ ] 与 ELF/HEX 机器码比较；
- [ ] 做 cache on/off 重复 A/B；
- [ ] 做 prefetch 四象限；
- [ ] invalidate 并等待命令完成；
- [ ] 检查 cache 开启时机、merge 和相关时钟；
- [ ] 分清 CM33 I-cache 与 SMIF cache。

### 16.4 workaround 验证

- [ ] 最终 ELF 反汇编能看到清 CA_EN；
- [ ] 能看到 invalidate 与有界等待；
- [ ] 后续没有重开 CA_EN；
- [ ] 烧录 raw verify 通过；
- [ ] C-AHB alias verify 通过；
- [ ] 运行时 CTL readback 正确；
- [ ] fault status 从运行前到运行后保持为零；
- [ ] reset、power cycle、长跑分别统计；
- [ ] 性能回归不使用 loop_count 代替。

---

## 17. 关键源码与工具索引

### 17.1 Non-secure 工程

- [正常框架、marker 与 main](../applications/main.c)
- [sensor_update_latest](../applications/m33/sensor_manager.c)
- [RT-Thread M33 HardFault 汇编入口](../rt-thread/libcpu/arm/cortex-m33/context_gcc.S)
- [RT-Thread fault dump](../rt-thread/libcpu/arm/cortex-m33/cpuport.c)
- [M33 构建、签名、烧录 wrapper](../tools/flash_m33_verified.ps1)
- [OpenOCD raw/alias verify 流程](../tools/openocd/pse84_m33_verified_flash.tcl)
- [PSE84 memory map/config](../libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/pse84_config.h)
- [SMIF/MemorySPI 生成配置](../libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource/cycfg_peripherals.c)
- [HF clock 生成配置](../libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource/cycfg_clocks.c)

### 17.2 Secure 工程

- [Secure Reset 与 S_HardFault_Handler](../../secureCore/libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/COMPONENT_CM33/COMPONENT_SECURE_DEVICE/s_start_pse84.c)

### 17.3 本工程已有调试资料

- [Cortex-M HardFault 寄存器调试入门](./Cortex-M_HardFault寄存器调试入门学习文档.md)
- [Cortex-M33 TrustZone HardFault 进阶手册](./Cortex-M33_TrustZone_HardFault进阶后端调试手册_20260708.md)
- [M33 HardFault 定位分析活文档](./M33_HardFault调试定位分析活文档_20260708.md)

旧文档是调试过程资料，其中可能保留早期假设、旧 ELF 地址或以 CONTROL_NS 选栈的简化表述。发生冲突时，以本文的证据等级、最终 ELF/hash 和 EXC_RETURN 规则为准。

---

## 18. 官方参考资料

- [Infineon PSoC Edge E8x Architecture Reference Manual, 002-38331 Rev. A](https://www.infineon.com/assets/row/public/documents/30/57/infineon-psoc-edge-e8x-architecture-reference-manual-additionaltechnicalinformation-en.pdf)
- [Infineon PSoC Edge E8x Registers Reference Manual, 002-38897 Rev. A](https://www.infineon.com/assets/row/public/documents/30/57/infineon-psoc-edge-e8x-registers-reference-manual-additionaltechnicalinformation-en.pdf)
- [Armv8-M Architecture Reference Manual](https://documentation-service.arm.com/static/5f8eff92f86e16515cdbe8e47)
- [Arm Cortex-M Exception Model User Guide](https://documentation-service.arm.com/static/64c7832738511951cb7a246e)
- [Arm Cortex-M33 errata, SDEN-756493](https://documentation-service.arm.com/static/624ffc3364e3265f7c90ab1e)
- [Infineon PSE8xx DSL release notes](https://raw.githubusercontent.com/Infineon/mtb-dsl-pse8xxgp/master/RELEASE.md)
- [Infineon CAT1 PDL release notes](https://raw.githubusercontent.com/Infineon/mtb-pdl-cat1/master/RELEASE.md)
- [Infineon S25FS128S/S25FS256S datasheet, 002-00368 Rev. O](https://www.infineon.com/dgdl/Infineon-S25FS128S_S25FS256S_1-DataSheet-v16_00-EN.pdf?fileId=8ac78c8c7d0d8da4017d0ed6b5ab5758)

---

## 19. 最终答辩结论

这次调试真正有价值的不是“试了很多开关”，而是完成了以下闭环：

1. 先用 marker 和异常帧确定故障发生在正常运行期；
2. 通过忙等实验推翻了 sleep/scheduler 的必要根因假设；
3. 不再把 sensor 这个新受害点直接当根因；
4. 用同物理 offset 的 C-AHB/raw 机器码差异直接观察取指路径失效；
5. 用 Secure handler 同类坏行提出解释二次异常、NS dump 为零和 Lockup 的强推断模型；
6. 用 CA_EN/prefetch/invalidate/时钟/merge 的单变量矩阵验证故障边界；
7. 先用 Secure Reset cache-off 得到阶段性 workaround，但没有把短时不崩误写成最终根治；
8. 用旧 FAL/MPC 数学边界与 `PRECISERR|BFARVALID`、`BFAR=0x60FC0000` 闭合确定性越界根因；
9. 把 FAL 移到 `0x60DC0000..0x60FBFFFF`，恢复 I-Cache，并增加跨核 SMIF guard、RAM/ITCM fault/command 闭包与 GPU lifecycle gate；
10. 通过 20/20 测试、三核构建、镜像 hash、raw/alias verify、真实断电、10 次 reset、双核 Fault/LCD 心跳和写擦闭环验证当前方案；
11. 明确区分“当前单板目标场景通过”与“多板、温压、长稳、掉电恢复尚未完成”。

一句话收尾：

> 当前已经能以 `FAL/MPC/BFAR` 闭环解释确定性越界，并以跨核 A/B 解释 command window 冲突；最终镜像已通过本板烧录和目标场景实机验收。可以称“目标根因已修复、当前样板在已测场景稳定”，但量产前仍需多板、50 次物理冷启动、温压满载、长时 endurance 和事务中掉电恢复。

---

## 20. 复验命令卡

以下命令用于复核，不代表任意历史地址都可以用最终 ELF 解析。运行硬件命令前应确认板卡、target 和镜像身份。

### 20.1 构建并走完整校验烧录

~~~powershell
rtk proxy powershell -ExecutionPolicy Bypass -File .\tools\flash_m33_verified.ps1
~~~

只在已经明确确认现有构建产物就是目标映像时，才使用 <code>-SkipBuild</code>。

### 20.2 保存 hash

~~~powershell
rtk proxy certutil -hashfile .\Debug\rtthread.elf SHA256
rtk proxy certutil -hashfile .\Debug\rtthread.hex SHA256
rtk proxy certutil -hashfile ..\secureCore\Debug\rtthread.elf SHA256
rtk proxy certutil -hashfile ..\secureCore\Debug\rtthread.hex SHA256
~~~

### 20.3 查符号和源码

工具链目录应使用本工程实际的 GNU Arm 13.3。示意命令：

~~~powershell
rtk proxy arm-none-eabi-nm -n .\Debug\rtthread.elf
rtk proxy arm-none-eabi-addr2line -e .\Debug\rtthread.elf -f -C 0x0839BE30
rtk proxy arm-none-eabi-objdump -d ..\secureCore\Debug\rtthread.elf
~~~

历史 fault PC 必须换成与该次烧录匹配的 ELF；如果对应 ELF/hash 已丢失，应保留“历史会话解析结果”标签，不重新制造精确源码行。

### 20.4 两种不能混用的现场采集流程

#### A. 保留已经发生的 fault 现场

如果目标已经故障，禁止 <code>reset</code> 和 <code>resume</code>。连接后只尝试 halt 一次并立即读取：

~~~tcl
targets cat1d.cm33
halt
poll

mdw 0x240C1A50 32
mdw 0x240C168C 1
mdw 0x240CCD50 1
mdw 0x240CCDC4 1
mdw 0x42223000 1
mdw 0x42223008 1

mdw 0x181042B0 8
mdw 0x701042B0 8
~~~

如果 halt 失败，先保存错误输出，不要用 <code>resume</code> “试一下”，否则会污染第一次现场。

#### B. 从已知基线干净重新复现

这套流程会主动 reset，不能用于保留已经存在的 fault：

~~~tcl
reset init
targets cat1d.cm33
cat1d::reset_halt cm33_ns reset

# 先读取并保存 baseline fault status、marker、loop 和实验寄存器。
# 只改变一个实验变量并 readback。
resume

# 等待预定复现窗口后，只 halt 一次。
halt
poll

# 再读取 fault status、原始 frame、marker/loop 和 cached/raw 窗口。
~~~

读取 Secure alias 前必须使用允许该访问的 target/domain，并检查 OpenOCD 没有 AP/security error。对于新的 fault PC，应先按 cache line 边界向下对齐，再换算 raw alias，不要机械照抄上面的历史 handler 地址。

### 20.5 建议的实验记录文件名

~~~text
YYYYMMDD-HHMMSS_boardN_testE##_secureSHA_nsSHA_openocd.log
~~~

同目录保存：

- Secure/NS ELF 与 HEX；
- OpenOCD/FLM 版本及 hash；
- 实验寄存器 before/readback/after；
- 完整 stdout/stderr；
- 结果摘要，不覆盖原始日志。

---

## 21. 90 秒面试答辩

这次故障一开始像 RT-Thread 调度链表损坏：main 在 <code>rt_thread_mdelay()</code> 超时后，经 SysTick、timer check 进入 scheduler，stacked PC 落在当时构建的 list remove 路径。但把 sleep 改成忙等后，故障没有消失，只移动到 <code>sensor_update_latest()</code>，所以 scheduler 和 sensor 是时序不同的受害位置。<code>PC=0xEFFFFFFE</code> 又是失真或 Lockup 后的现场，不能直接拿去 addr2line。

第一条关键证据来自 XIP 双 alias：故障时 cached/XIP 视图读到全 F，而 raw 视图仍是正确机器码，解释了 <code>UNDEFINSTR</code>。暂停 M33 后，卡在 SMIF FIFO 的 M55 立即继续并完成 LCD 初始化，说明两核共享 SMIF0 且 command mode 缺少排他。关闭 cache 只能改变取指流量和暴露时序，因此凌晨 3 点的短时稳定只是 workaround。

最终的确定性证据是地址数学闭环：旧 M55 FAL 从 <code>0x60E00000</code> 起占 2 MiB，结束于 <code>0x61000000</code>；M55 Non-secure SMIF MPC 却在 <code>0x60FC0000</code> 结束。硬件现场正是 <code>CFSR=0x00008200</code>、<code>BFAR=0x60FC0000</code>，也就是第一个非法地址。因此最终修复把 FAL 迁到 <code>0x60DC0000..0x60FBFFFF</code>，并同步迁移所有子分区和烧录资源；同时恢复 M33 I-Cache，以 IPC guard 在 program/erase 前让 M33 XIP、M55 I-Cache 和受管理的 GPU 路径静默，命令闭包与 fault 闭包放入 RAM/ITCM，结束后再恢复 memory mode 和分层 cache。

验证不是只看“能启动”：20/20 静态回归、三核构建、raw/XIP verify、真实断电冷启动、10 次系统 reset、两核 Fault 为 0、M33/M55 tick 与 LCD flush 持续增长；运动模式 erase 被拒绝，PASSIVE 下完成 4 个 64 KiB erase，以及临时 token 的 write/read/clear，guard grant/complete 匹配且 timeout 为 0。因此可以说目标根因已修复、当前样板在已测场景稳定；不能说量产终身稳定，因为多板、50 次物理断电、温压满载、长时 endurance 和事务中掉电恢复还没完成。
