# 板上镜像来源不一致与 Cache Seq Mismatch 专项排查记录

日期：2026-07-17  
适用范围：PSoC E84 CM33/CM55 双核固件、M33 -> M55 EMG 共享内存与 IPC 链路  
关联提交：`892f60c6`、`60a34555`、`69b5aa3d`、`0f34ac92`

## 1. 为什么单独记录

本次排查同时遇到了两个容易互相误导的问题：

1. 调试人员最初按独立 M55 Studio 工程理解板上固件，但板上实际运行特征对应集成仓库 `PSOC_E84_robot_delivery/firmware/m55` 的镜像。
2. M33 已经发送 IPC 流描述，M55 却持续出现共享 header `seq` 与 IPC `chunk_index` 不一致。表面像普通 Cache 一致性问题，最终根因却是 M55 同名共享对象被链接到了本地 DTCM。

如果不先确认板上镜像来源，后续用错误 ELF 查符号、反汇编和内存地址，会得到逻辑自洽但完全错误的结论。因此本次最重要的经验不是某一行 Cache API，而是建立以下固定顺序：

```text
确认板上镜像身份
  -> 确认调试 ELF 与板上代码一致
  -> 核对 IPC 描述和共享数据地址
  -> 核对 Cache 操作的实际机器码
  -> 最后才修改协议或业务逻辑
```

## 2. 当时存在的两个 M55 候选工程

排查时本机至少存在以下两个可能被误认为“当前板上 M55”的工程：

| 候选 | 路径 | 角色 |
|---|---|---|
| 独立 Studio 工程 | `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED` | 早期单独开发、烧录和验证 M55 |
| 集成仓库工程 | `F:/RT-ThreadStudio/workspace/PSOC_E84_robot_delivery/firmware/m55` | 与 M33、平台代码统一维护的当前集成实现 |

两个工程都能生成名为 `rt-thread.elf` 和 `rtthread.hex` 的产物，Shell 命令和大量符号名称也相似。只看文件名、工程名或“最后编译时间”不足以确认板上来源。

截至本文提交前，本机两个候选 ELF 的 SHA-256 不同：

```text
集成 M55 ELF:
6DC74430142999D41CE181FAF0C0640961588D4D86A4AEBA985DBA947F4539AB

独立 M55 ELF:
8768C9C1AAF1DCFF4D1372BFF9C95421AFDDCAE4F5FDE3CAAC2B2C7ED91D4F37
```

这些哈希是当前工作区产物的身份记录，不应倒推为故障发生前板上 Flash 的整片哈希。

## 3. 镜像来源是怎样确认的

### 3.1 不能只依赖一个现象

本次采用的是“ELF 指纹组合”而不是单一字符串：

- M55 运行时存在集成工程对应的 Wi-Fi、WebSocket、显示和 TFLM 行为。
- OpenOCD 读取的诊断变量地址和布局能与集成 ELF 的 `nm` 输出对应。
- `g_emg_intent_error_count`、`g_emg_intent_last_seq`、`g_emg_intent_window_count` 的相对顺序和读值符合该 ELF。
- 共享对象和诊断对象的地址组合能解释板上现象。
- 使用独立工程作为调试 ELF 时，无法完整解释当时的链接布局和正在运行的集成功能集合。

因此后续构建、反汇编、符号读取和修复全部转到集成仓库 M55，而不是继续修改独立 M55 工程。

### 3.2 本次证据的边界

故障发生前没有执行“读取整片板上 M55 Flash并计算 SHA-256，再与本地产物逐字节比较”。因此本记录使用“运行特征和 ELF 指纹匹配”这一表述，不把它扩大为板上 Flash 的密码学同一性证明。

以后发布固件必须补上 `m55_fw_info` 或等价身份接口，至少输出：

- 仓库标识
- Git commit
- dirty 标志
- 构建时间
- 协议 ABI 版本
- 链接脚本版本
- 发布清单中的 ELF/HEX SHA-256

没有这些信息时，调试人员很容易拿“刚刚编译的 ELF”连接“之前烧录的固件”。GDB 能连接不代表符号匹配。

## 4. Seq Mismatch 的协议含义

M33 发布 EMG 窗口时，存在两类相关数据：

1. IPC 队列中的轻量流描述，其中包含 `chunk_index`、长度、采样数和通道数等元数据。
2. SOCMEM 中的 `g_m33_m55_pcm_shared`，其中包含共享 header、`seq` 和实际 payload。

M55 收到描述后会检查：

```c
stream->chunk_index == g_m33_m55_pcm_shared.seq
```

不相等时不能继续推理，因为描述可能对应旧窗口，而共享单槽已经被下一窗口覆盖。拒绝旧数据是正确的安全行为。

但 `seq mismatch` 只说明“描述与当前读到的共享 header 不一致”，不能直接断言是丢包。常见原因包括：

- 消费者 Cache 中仍是旧 header。
- 生产者写完后没有 clean，数据未到达共享可见域。
- 两核使用了不同物理地址。
- section 成为 orphan，被 linker 放进普通 RAM。
- 单槽被另一个 producer 覆盖。
- 写 payload、header、发 IPC 的顺序错误。
- 两核结构体 ABI、对齐或字段版本不同。
- 调试 ELF 与板上镜像不一致，读取了错误变量地址。

## 5. 排查过程

### 5.1 先读取 M55 原始计数

通过 OpenOCD 按正确 ELF 的符号地址读取诊断变量，初始证据为：

```text
error_count = 1053
last_seq    = 0
window_count = 0
```

含义是：M55 收到了触发 handler 的输入，但所有窗口都在真正推理前被拒绝。问题位于：

```text
IPC 描述已到达
  -> 共享 header/长度/seq 校验失败
  -> 尚未进入 TFLM inference
```

这一步排除了“模型推理很慢”“CAN 上报丢失”和“模型结果发布失败”作为第一根因。

### 5.2 第一假设：M55 读取了旧 Cache

提交 `892f60c6` 在 M55 校验共享 header 前增加 invalidate，并在读取 payload 前刷新对应范围，同时补充空指针检查。

预期：如果只是 D-Cache 保存旧 `seq`，刷新后 `last_seq` 和 `window_count` 应开始增长。

结果：窗口仍持续拒绝。说明假设没有完全解释故障。

### 5.3 增加发布侧诊断

提交 `60a34555` 增加模型结果发布的：

- sequence
- publish ok
- publish fail
- last return

目的不是“用日志修复问题”，而是把链路分为：

```text
窗口接收 -> 推理 -> 模型结果发布 -> M33 接收
```

当时窗口计数仍为 0，所以发布计数自然不能增长，进一步确认故障在推理入口之前。

### 5.4 反汇编发现 RT-Thread Cache API 是空操作

源码调用 `rt_hw_cpu_dcache_ops()` 不等于最终机器码一定执行 Cache maintenance。

对集成 M55 ELF 反汇编后发现，该调用路径在当前配置下没有生成有效 invalidate 指令，只保留了内存屏障。原因是当前 `rtconfig.h` 没有走到对应 `RT_USING_CACHE` 实现。

提交 `69b5aa3d` 将共享 PCM 的 Cache 操作集中到 `.c` 文件，并直接调用 CM55 CMSIS：

```c
SCB_InvalidateDCache_by_Addr(...);
__DSB();
```

这个修改保证当前构建配置中确实生成 CM55 Cache maintenance 代码。

结果：问题仍未消失。至此可以判断“旧 Cache”是真实风险，但不是唯一根因。

### 5.5 核对两核共享对象的实际链接地址

随后使用 `arm-none-eabi-nm` 和 linker map 核对同名对象：

```text
M33 共享 PCM 地址：0x261C0000
M55 故障时地址：   0x200012C0
```

`0x200012C0` 属于 M55 本地 DTCM。也就是说：

- M33 在 `0x261C0000` 写 header 和 payload。
- IPC 小消息可以正常到达 M55。
- M55 却在 `0x200012C0` 读取自己的本地零值或旧值。
- `stream->chunk_index` 持续变化，而 M55 读到的共享 `seq` 不变化。
- 因此每一帧都稳定地产生 `seq mismatch`。

Cache invalidate 无法修复“读错物理地址”。无论把 `0x200012C0` 刷新多少次，都不会得到 M33 写在 `0x261C0000` 的数据。

### 5.6 为什么同名共享对象落进 DTCM

故障版本代码使用：

```c
__attribute__((section(".cy_shared_socmem"), aligned(32)))
volatile m33_m55_pcm_shared_t g_m33_m55_pcm_shared;
```

但集成 M55 linker script 显式管理的是：

```ld
.ipc_stream_shared(NOLOAD) :
{
    . = ALIGN(32);
    KEEP(*(.ipc_stream_shared))
    . = ALIGN(32);
} > m33_m55_shared
```

`.cy_shared_socmem` 没有进入这段规则，成为 orphan section。链接器没有报错，而是把它放入普通可用内存，最终落在 DTCM。这是最危险的类型：构建成功、符号存在、代码可运行，但双核读写的并非同一物理对象。

提交 `0f34ac92` 将对象 section 改为 `.ipc_stream_shared`。修复后：

```text
261c0000 B g_m33_m55_pcm_shared
```

M33 和 M55 对该对象的物理地址终于一致。

## 6. 修复后的闭环证据

修复 M55 构建并只烧录集成工程的 `firmware/m55/rtthread.hex` 后，执行：

```text
cmd_m55_ipc_start
cmd_m55_emg_stream 1 20 0
cmd_m55_emg_stream 0 20 0
cmd_m55_emg_status
m55qa_status
```

M33 连续收到：

```text
[m55_model_bridge] ai seq=... model=2 result=1 conf=...
                   flags=0x03 win=300 can_ret=0
```

停止测试流后的状态：

```text
windows=212 errors=0
ipc_ready=1 tx_pending=0 rx_pending=0 has_model=1
model seq=392 code=2 result=1 conf=918/1000
```

这证明：

1. M55 不再因共享 header 校验拒绝所有窗口。
2. M55 能读取 payload 并完成推理。
3. 模型结果能通过 IPC 返回 M33。
4. M33 的 CAN 提交接口返回成功。

`can_ret=0` 不证明 NanoPi 或云平台已收到，外部链路仍需 `candump` 和应用日志对账。

## 7. 本次没有修改的范围

为了控制风险，本轮没有修改：

- M33 电机控制和助力状态机
- MuJoCo 动作规划接口
- STM32F103 固件和协议
- CAN 物理层配置
- 蓝牙配对逻辑
- Wi-Fi 资源分区
- NanoPi 和云平台业务代码

本次只解决“正确 M55 镜像中的共享窗口读取与推理返回”。

## 8. 以后必须执行的镜像来源检查

### 8.1 构建前

记录：

```text
repo_root
branch
git_commit
git_dirty
toolchain_version
ELF_path
HEX_path
ELF_SHA256
HEX_SHA256
```

禁止只写“烧录 rtthread.hex”。同名文件在多个工程中没有可追溯性。

### 8.2 烧录前

烧录脚本必须打印并保存：

- 绝对路径
- 文件大小
- SHA-256
- Git commit
- 目标核和 Flash bank

操作人员确认后再执行 `flash write_image` 和 `verify_image`。

### 8.3 运行后

通过 Shell 或 debugger 读取固件身份，必须与发布清单一致。任何一项不一致，都应停止功能调试，先解决镜像来源。

## 9. 以后必须执行的共享内存检查

### 9.1 链接期门禁

建议在 linker script 和 CI 中加入：

```ld
ASSERT(ADDR(.ipc_stream_shared) == ORIGIN(m33_m55_shared),
       "IPC shared section placed at unexpected address")
ASSERT(SIZEOF(.ipc_stream_shared) <= LENGTH(m33_m55_shared),
       "IPC shared section exceeds reserved SOCMEM")
```

CI 再用 `arm-none-eabi-nm` 或 map parser 断言：

```text
g_m33_m55_pcm_shared == 0x261C0000
```

两个核心必须各检查一次，不能只检查 M33。

### 9.2 协议和结构体门禁

共享 header 应包含并校验：

- magic
- ABI version
- header size
- payload length
- sequence
- producer id
- flags
- 可选 CRC

两核应对 `sizeof`、`offsetof` 和 Cache line 对齐做编译期断言。

### 9.3 推荐的发布顺序

生产者：

```text
写 payload
  -> clean payload cache
  -> 写 length/seq/version/CRC
  -> clean header cache
  -> DSB
  -> 发布 IPC descriptor
```

消费者：

```text
接收 IPC descriptor
  -> invalidate header
  -> DSB
  -> 校验 version/length/seq
  -> invalidate payload
  -> 复制或处理 payload
  -> 必要时再次校验 seq，检测处理中被覆盖
```

大 payload 不建议用跨核粗粒度互斥锁解决。单生产者/单消费者场景优先使用明确所有权、sequence 和发布顺序；多生产者必须先仲裁所有权，不能让多个 producer 无协调覆盖同一单槽。

## 10. 遇到 Seq Mismatch 时的最短排查表

按顺序执行，前一项不成立时不要继续猜业务逻辑：

1. 确认板上固件身份与调试 ELF 完全匹配。
2. 用两个 ELF 分别确认共享符号物理地址相同。
3. 读取 `chunk_index`、共享 `seq`、错误计数和成功窗口计数。
4. 检查 section 是否由 linker script 显式接管，禁止 orphan。
5. 反汇编确认 clean/invalidate 指令真实存在。
6. 检查 Cache 操作地址和长度是否覆盖完整 cache line。
7. 检查 producer 写入、clean、barrier、IPC publish 顺序。
8. 检查是否有第二 producer 覆盖单槽。
9. 检查 ABI version、`sizeof`、`offsetof` 和对齐。
10. 最后才检查模型推理和 CAN/云端上报。

## 11. 最终结论

本次 `seq mismatch` 不是简单的 CAN 丢帧，也不是 TFLM 模型故障。完整根因链为：

```text
板上运行的是集成 M55 镜像
  -> 初期按另一个 M55 工程理解，增加了定位噪声
  -> 集成代码使用了 linker 未接管的 section 名
  -> g_m33_m55_pcm_shared 静默落入 M55 DTCM
  -> M33 和 M55 访问不同物理地址
  -> M55 读取的 seq 永远追不上 IPC chunk_index
  -> 所有 EMG 窗口在推理前被拒绝
```

同时还发现 RT-Thread Cache API 在当前构建配置下没有生成有效 invalidate，因此保留 CMSIS Cache 修复仍然必要。正确修复是“统一共享物理地址 + 确保 Cache maintenance 真实生效”，两者缺一不可。
