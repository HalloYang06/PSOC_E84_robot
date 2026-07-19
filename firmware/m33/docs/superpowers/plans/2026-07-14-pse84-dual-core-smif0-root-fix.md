# PSE84 双核 SMIF0 根治 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 M33 外部 Flash XIP 与 M55 SMIF0 命令事务并发导致的 M55 启动卡死，同时恢复 M33 I-Cache、修正 S25FS128S 文件系统擦除几何并禁止破坏性自动格式化。

**Architecture:** M55 普通读取改走 0x60000000 XIP 窗口；写入/擦除前通过专用 IPC1 通道通知 M33，M33 在内部 SRAM 中的中断处理函数停驻，直到 M55 的内部 ITCM 命令链完成。共享状态固定放在双核共享 SRAM 末尾 0x261FFF00，双方使用序号、有限超时、状态码和计数器防止永久等待。安全启动按“失效后重开”的顺序恢复 M33 I-Cache。

**Tech Stack:** PSoC Edge E84（Cortex-M33/Cortex-M55）、RT-Thread、Infineon PDL SMIF/IPC、GCC/LD、SCons、OpenOCD/KitProg3、Python `unittest` 静态回归测试。

---

## 成功判据

- M33 Secure 启动最终开启 I-Cache；每次 M55 命令事务结束后，M33 在 SRAM 停驻路径内失效 CPUSS `ICACHE0` 和预取缓冲，再返回 XIP。
- M55 FAL `read()` 不再调用 `Cy_SMIF_MemRead()`，且不会无限等待。
- M55 FAL 逻辑块、LittleFS 擦除请求与该地址区域真实的 64 KiB sector 一致。
- mount 失败只记录错误并继续显示初始化，不自动 `dfs_mkfs()`。
- M33 guard 在启动 M55 之前 ready；其 IRQ 停驻路径完全位于内部 SRAM。
- M55 写/擦命令入口及 PDL 调用链位于 ITCM/RAM；guard 未 ready、ack 超时、运动 active 均返回有限错误。
- 双核冷启动 LCD 正常，M33/M55 CFSR/HFSR 为 0；擦写验证不破坏相邻 64 KiB sector。

## Task 1：先建立会失败的静态回归测试

**Files:**

- Create: `tools/test_pse84_smif0_root_fix_static.py`
- Read: `board/board.c`
- Read: `board/linker_scripts/link.ld`
- Read: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/fal/fal_flash_port.c`
- Read: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/filesystem/mnt.c`
- Read: `../secureCore/libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/COMPONENT_CM33/COMPONENT_SECURE_DEVICE/s_start_pse84.c`

- [ ] 写测试，至少断言以下事实：

```python
self.assertIn("smif0_guard_init", board_before_cm55)
self.assertIn("ICACHE0->CMD = ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk", m33_guard_source)
self.assertIn("0x261FFF00", protocol_header)
self.assertIn(".cy_ramfunc", m33_guard_source)
self.assertNotIn("Cy_SMIF_MemRead(", fal_read_body)
self.assertIn("FLASH_SECTOR_SIZE      (64U * 1024U)", fal)
self.assertNotIn('dfs_mkfs("lfs", "filesystem")', mount_body)
self.assertRegex(secure_after_invalidate, r"ICACHE_CTL.*CA_EN")
```

- [ ] 运行并保存 RED 证据：

```powershell
rtk python -m unittest tools.test_pse84_smif0_root_fix_static -v
```

Expected: 至少因 guard 缺失、FAL 仍为 4 KiB/命令读取、I-Cache 未重开而失败。

## Task 2：恢复 M33 cache 正常配置并修正 M55 无破坏读取路径

**Files:**

- Modify: `../secureCore/libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/COMPONENT_CM33/COMPONENT_SECURE_DEVICE/s_start_pse84.c`
- Modify: `board/board.c`
- Modify: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/fal/fal_flash_port.c`
- Modify: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/filesystem/mnt.c`

- [ ] 在 Secure reset 中保持现有 disable/barrier/invalidate/等待/ECC 顺序，并在其后恢复：

```c
MXCM33->CM33_ICACHE_CTL |= MXCM33_CM33_ICACHE_CTL_CA_EN_Msk;
__DSB();
__ISB();
```

- [ ] M33 `cybsp_init()` 后只安装 guard，不调用未初始化的 SMIF fast/slow cache API；运行时维护对象是 CPUSS `ICACHE0`。

- [ ] M55 FAL 设置真实几何和有限 PDL timeout：

```c
#define FLASH_SECTOR_SIZE      (64U * 1024U)
#define SMIF_TIMEOUT_US        (5U * 1000U * 1000U)
static cy_stc_smif_context_t smif_context = { .timeout = SMIF_TIMEOUT_US };
```

- [ ] FAL `read()` 先做参数/溢出检查，再从 `FLASH_START_ADDRESS + offset` 映射地址复制；禁止调用 `Cy_SMIF_MemRead()`。
- [ ] `_fal_mount()` mount 失败只打印可诊断错误并返回；删除自动 `dfs_mkfs()` 及 mount-after-format 分支，确保 `mnt_init()` 继续返回且后续 LCD/LVGL 初始化可运行。
- [ ] 运行静态测试，确认 cache/read/geometry/mount 子项由 RED 变 GREEN。

## Task 3：实现双核 SMIF0 所有权 guard

**Files:**

- Create: `board/smif0_guard.h`
- Create: `board/smif0_guard.c`
- Modify: `board/SConscript`
- Modify: `board/board.c`
- Modify: `board/linker_scripts/link.ld`
- Create: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/fal/smif0_guard_client.h`
- Create: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/fal/smif0_guard_client.c`
- Modify: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/SConscript`
- Modify: `../Edgi_Talk_M55_Blink_LED/libraries/Common/board/ports/fal/fal_flash_port.c`
- Modify: `../Edgi_Talk_M55_Blink_LED/board/linker_scripts/link.ld`
- Modify: `applications/main.c`

- [ ] 双方使用相同 ABI；固定地址、版本和操作码如下：

```c
#define SMIF0_GUARD_SHARED_ADDRESS (0x261FFF00UL)
#define SMIF0_GUARD_MAGIC          (0x534D4946UL)
#define SMIF0_GUARD_VERSION        (1UL)
#define SMIF0_GUARD_IPC_CHANNEL    (CY_IPC_CHAN_USER + 2UL)
#define SMIF0_GUARD_IPC_INTR       (CY_IPC_INTR_USER + 6UL)
typedef enum { SMIF0_GUARD_OP_WRITE = 1, SMIF0_GUARD_OP_ERASE = 2 } smif0_guard_op_t;
```

- [ ] 共享结构 32 字节对齐并包含 `magic/version/ready/safe_to_block/request_seq/ack_seq/release_seq/operation/result/request_count/deny_count/timeout_count/reset_count`；结构总长不超过保留的 0x100 字节。
- [ ] M33 `smif0_guard_early_init()` 在 board init 中清零共享结构、开启独立硬件计时、安装 `CY_IPC_INTR_MUX(SMIF0_GUARD_IPC_INTR)`、设置 IPC notify mask并使能 NVIC，但此时保持 OFFLINE；因为 RT-Thread board init 期间 PRIMASK=1，不能接受请求。
- [ ] 使用 `INIT_PREV_EXPORT` 在调度器已启动、全局中断已恢复后先写 ONLINE，再调用 `Cy_SysEnableCM55()`；从 `cy_bsp_all_init()` 删除直接启动 M55 的代码。
- [ ] M33 ISR 及其全部 helper 标记 `.cy_ramfunc`：校验消息和序号；运动 active 时写 DENIED 并释放 IPC；允许时写 ack 后只读取共享 SRAM，等待 `release_seq`；收到 release 后在 SRAM 内执行 `ICACHE0->CMD = INV|BUFF_INV` 并有界等待，再返回 XIP；硬件计时超时后记录并发出受控 system reset。
- [ ] linker 添加共享末尾保留断言和 SRAM 路径断言所需符号：

```ld
ASSERT(__cy_shared_socmem_end__ <= 0x261FFF00, "SMIF0 guard mailbox overlaps shared data")
```

- [ ] M55 client 使用本核 mutex 串行化事务；request/release 前 clean 共享 cache line，读 ack 前 invalidate；IPC channel busy、guard not ready、ack timeout 都返回有限错误且不调用 SMIF 命令。
- [ ] FAL 写/擦只在 guard grant 后进入 `.cy_sram_code` 内部函数；内部函数只调用已位于 ITCM 的 `Cy_SMIF_MemWrite/EraseSector/CacheInvalidate`；返回 memory mode 后先发布 release，再解 mutex。
- [ ] erase 对 offset/size 做 64 KiB 对齐检查；运动 active 时 M33 `smif0_guard_set_safe_to_block(false)`，启动/停止安全窗口为 true，active erase 返回 `-RT_EBUSY`。
- [ ] 检查 map：M33 handler 地址必须在 `0x04058000..0x040BCFFF`；M55 命令入口和 `Cy_SMIF_*` 必须在 `0x00000000..ITCM_END`；两边共享地址都为 `0x261FFF00`。

## Task 4：编译、签名、烧录和实机验证

**Files:**

- Modify: `docs/PSE84_M33_XIP_ICACHE_HardFault_完整调试记录_20260714.md`
- Create: `docs/PSE84_DUAL_CORE_SMIF0_ROOT_FIX_IMPLEMENTATION_20260714.md`
- Generated/verify: `../secureCore/build/rtthread.hex`
- Generated/verify: `tools/edgeprotecttools/cm33_s_signed_fw/proj_cm33_s_signed.hex`
- Generated/verify: `build/rtthread.hex`, `rt-thread.map`
- Generated/verify: `../Edgi_Talk_M55_Blink_LED/build/rtthread.hex`, `../Edgi_Talk_M55_Blink_LED/rt-thread.map`

- [ ] 依次构建 Secure、M55、M33；每一步退出码必须为 0：

```powershell
rtk scons -j8 secure_image
rtk scons -j8
rtk scons -j8 secure_image
```

执行目录依次为 `../secureCore`、`../Edgi_Talk_M55_Blink_LED`、当前 M33 工程；Secure 签名输出复制到 M33 组合镜像指定目录后再构建 M33。

- [ ] 运行全部静态测试：

```powershell
rtk python -m unittest discover -s tools -p "test_*static.py" -v
```

Expected: 所有测试通过。

- [ ] 用 KitProg3/OpenOCD 烧录组合 M33 镜像与 M55 镜像，reset run 后分别 halt M33/M55，读取 PC、CFSR/HFSR、guard mailbox、LCD/LVGL 计数器。
- [ ] 执行三类故障注入：guard interrupt mask 关闭时 M55 有限超时且 LCD 继续；运动 active 时 erase 被拒；非法 4 KiB erase 被拒。
- [ ] 使用专用 64 KiB 测试 sector 做 erase/write/read/CRC，再复位读回；同时校验相邻 sector 哨兵未变化。不得在用户配置分区上试验。
- [ ] 断电冷启动至少 10 次作为本轮交付门槛；后续完整验证扩展到 50 次。每次 LCD 有帧、M33/M55 fault 寄存器为 0、guard 无 timeout/reset。
- [ ] 文档记录每次构建产物哈希、map 地址、烧录命令、寄存器值、故障注入结果，以及“已验证”和“尚未验证”的明确边界。

## 计划自检

- 需求覆盖：I-Cache、XIP read、跨核 guard、运动安全、64 KiB 几何、禁止自动 mkfs、LCD 非阻塞、超时、map 和冷启动均有对应任务与验证。
- 类型/地址一致：共享地址固定为 `0x261FFF00`；IPC channel/intr 均落在 IPC1 用户范围，且避开项目已使用的 channel 17/18 与 interrupt 9..14。
- 无占位项：没有 TODO/TBD；硬件验证次数、地址范围、错误路径和命令均明确。
- 变更边界：不改自动生成 QSPI memory-slot 配置，不重构无关业务，不清理用户现有工作树。
