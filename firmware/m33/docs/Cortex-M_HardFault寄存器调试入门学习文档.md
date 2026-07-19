# Cortex-M HardFault 寄存器调试入门学习文档

本文面向刚开始接触 Cortex-M 调试的人，目标不是背完所有寄存器，而是建立一套能反复使用的调试思维：

```text
PC 告诉我现在停在哪里；
异常栈帧里的 PC 告诉我 fault 前真正执行哪里；
CFSR/HFSR 告诉我为什么 fault；
VTOR/AIRCR 告诉我异常被谁接管。
```

## 1. 先分清两类寄存器

### 1.1 CPU 核心寄存器

这些是 CPU 当前运行现场，通常在 RT-Thread Studio 的 Registers 窗口直接看。

```text
PC    当前或即将执行的指令地址
LR    返回地址；异常时也可能是异常返回码
SP    当前栈指针的统称
MSP   Main Stack Pointer，异常/内核常用
PSP   Process Stack Pointer，RT-Thread 线程常用
xPSR  程序状态寄存器；低 9 位 IPSR 可判断当前异常号
```

常见判断：

```text
xPSR & 0x1FF = 0   Thread mode，普通线程/业务代码
xPSR & 0x1FF = 3   HardFault
xPSR & 0x1FF = 4   MemManage
xPSR & 0x1FF = 5   BusFault
xPSR & 0x1FF = 6   UsageFault
```

例如：

```text
xPSR = 0x01000003
```

低 9 位是 3，说明当前正在 HardFault Handler 中。

### 1.2 SCB 系统控制寄存器

这些不是普通 CPU 寄存器，而是 memory-mapped register，也就是固定地址上的硬件寄存器。

```text
0xE000ED08  VTOR   当前向量表地址
0xE000ED0C  AIRCR  异常/复位控制，TrustZone 下还影响 HardFault 路由
0xE000ED24  SHCSR  fault 使能/活动/挂起状态
0xE000ED28  CFSR   fault 具体原因
0xE000ED2C  HFSR   HardFault 总状态
0xE000ED34  MMFAR  MemManage fault 地址
0xE000ED38  BFAR   BusFault 地址
```

OpenOCD 读取示例：

```text
mdw 0xE000ED28 1
mdw 0xE000ED2C 1
mdw 0xE000ED38 1
```

RT-Thread Studio 中可以在 Memory Browser 输入这些地址查看。

## 2. C 代码为什么能访问硬件寄存器

MCU 里很多寄存器就是特殊内存地址。

例如：

```c
*(volatile uint32_t *)0xE000ED0C = value;
```

含义是：

```text
把 0xE000ED0C 当成 uint32_t 指针；
用 * 解引用；
把 value 写到这个地址对应的硬件寄存器里。
```

它不是修改 `0xE000ED0C` 这个数字，而是修改这个地址指向的内容。

CMSIS 会把这种写法包装成结构体：

```c
typedef struct
{
    volatile uint32_t CPUID;  /* offset 0x00 */
    volatile uint32_t ICSR;   /* offset 0x04 */
    volatile uint32_t VTOR;   /* offset 0x08 */
    volatile uint32_t AIRCR;  /* offset 0x0C */
} SCB_Type;

#define SCB_BASE 0xE000ED00UL
#define SCB ((SCB_Type *)SCB_BASE)
```

所以：

```c
SCB->AIRCR = value;
```

等价于：

```c
*(volatile uint32_t *)(0xE000ED00 + 0x0C) = value;
```

也就是：

```c
*(volatile uint32_t *)0xE000ED0C = value;
```

## 3. 异常栈帧怎么看

Cortex-M 进入异常时，硬件会自动压 8 个 word 到当前栈里：

```text
SP + 0x00  r0
SP + 0x04  r1
SP + 0x08  r2
SP + 0x0C  r3
SP + 0x10  r12
SP + 0x14  lr
SP + 0x18  pc
SP + 0x1C  xpsr
```

所以，如果调试器显示：

```text
psp_ns = 0x240cdb18
```

就读：

```text
mdw 0x240cdb18 8
```

第 6 个 word 是 fault 前 LR，第 7 个 word 是 fault 前 PC。

示例：

```text
0x240cdb18: 240c6090 ffffffff 00000002 0000ffff 0000005a 083905cd 08376eb0 01000000
```

对应关系：

```text
r0   = 0x240c6090
r1   = 0xffffffff
r2   = 0x00000002
r3   = 0x0000ffff
r12  = 0x0000005a
lr   = 0x083905cd
pc   = 0x08376eb0
xpsr = 0x01000000
```

然后用 `addr2line` 查：

```text
arm-none-eabi-addr2line -e Debug/rtthread.elf -f -C 0x08376eb0 0x083905cd
```

## 4. CFSR/HFSR 怎么看

`CFSR` 是最常用的 fault 原因寄存器，地址：

```text
0xE000ED28
```

它由三段组成：

```text
bits 0~7    MemManage fault
bits 8~15   BusFault
bits 16~31  UsageFault
```

常见位：

```text
bit 0   IACCVIOL     取指权限错误
bit 1   DACCVIOL     数据访问权限错误
bit 7   MMARVALID    MMFAR 有效
bit 8   IBUSERR      取指总线错误
bit 9   PRECISERR    精确数据总线错误
bit 15  BFARVALID    BFAR 有效
bit 16  UNDEFINSTR   执行了非法指令
bit 17  INVSTATE     状态错误
bit 18  INVPC        异常返回 PC 错误
bit 19  NOCP         协处理器/FPU 不可用
bit 24  UNALIGNED    非对齐访问
bit 25  DIVBYZERO    除 0
```

`HFSR` 地址：

```text
0xE000ED2C
```

常见重点：

```text
bit 30 FORCED
```

如果 `HFSR.FORCED=1`，通常表示原本是 MemManage、BusFault 或 UsageFault，最后升级成 HardFault。

## 5. VTOR 和向量表

`VTOR` 是 Vector Table Offset Register，地址：

```text
0xE000ED08
```

它指向当前异常向量表。

向量表本质是函数指针数组：

```text
vector[0] = 初始 SP
vector[1] = Reset_Handler
vector[2] = NMI_Handler
vector[3] = HardFault_Handler
vector[4] = MemManage_Handler
vector[5] = BusFault_Handler
vector[6] = UsageFault_Handler
```

如果：

```text
SCB->VTOR = 0x34037000
```

那么 HardFault Handler 地址在：

```text
0x34037000 + 3 * 4 = 0x3403700C
```

读取：

```text
mdw 0x34037000 8
```

如果第 4 个 word 是：

```text
0x181042bb
```

说明 HardFault Handler 指向 `0x181042ba`，最低 bit 只是 Thumb 标志。

## 6. TrustZone、Secure、Non-secure

Cortex-M33 支持 TrustZone，会把世界分成：

```text
Secure      安全世界，先启动，配置权限、异常路由、安全资源
Non-secure  普通世界，通常跑 RT-Thread 应用代码
```

本工程中：

```text
Secure:
  启动配置
  SAU/权限
  AIRCR
  Secure HardFault handler

Non-secure:
  RT-Thread
  applications/
  CAN 控制逻辑
  sensor_update_latest()
  rt_mutex_take()
```

`AIRCR.BFHFNMINS` 决定 BusFault、HardFault、NMI 的目标安全状态。

本工程中：

```c
#define SCB_AIRCR_BFHFNMINS_VAL 0
```

含义：

```text
HardFault 交给 Secure 处理。
```

所以可能出现：

```text
Non-secure 代码先 fault
  -> HardFault 路由到 Secure
  -> Secure handler 又 fault
  -> 最后看到 pc=0xeffffffe
```

## 7. 外部 Flash 地址别名

本工程 BSP 文档说明，同一片外部 flash 有多个地址别名：

```text
0x08000000  Non-secure CBUS/XIP 执行视图
0x60000000  Non-secure SBUS/raw/烧录读写视图
0x18000000  Secure CBUS/XIP 执行视图
0x70000000  Secure SBUS/raw/烧录读写视图
```

也就是：

```text
0x08xxxxxx + 0x58000000 = 0x60xxxxxx
0x18xxxxxx + 0x58000000 = 0x70xxxxxx
```

如果 PC 在：

```text
0x08376eb0
```

那么对应 raw alias 是：

```text
0x60376eb0
```

正常情况下两边应该读出同一段机器码：

```text
mdw 0x08376eb0 8
mdw 0x60376eb0 8
```

如果出现：

```text
0x08376eb0: ffffffff ffffffff ffffffff ffffffff ...
0x60376eb0: 4ff0e92d 4691b087 46049103 ...
```

说明 flash 内容本身存在，但 CPU 执行用的 CBUS/XIP 视图读错了。

## 8. 固定调试流程

遇到 HardFault，不要先猜。按这个顺序读：

```text
1. reg
   看 pc、lr、xpsr、msp、psp、msp_ns、psp_ns。

2. 判断当前模式
   xPSR & 0x1FF。

3. 找异常栈帧
   Thread mode 用 PSP 的概率高；
   Handler mode 用 MSP 的概率高；
   RT-Thread 线程一般看 PSP/PSP_NS。

4. 读异常栈帧
   mdw <sp> 8
   第 6 个 word 是 lr，第 7 个 word 是 pc。

5. 查源码位置
   arm-none-eabi-addr2line -e Debug/rtthread.elf -f -C <pc> <lr>

6. 读 fault 原因
   mdw 0xE000ED28 1   CFSR
   mdw 0xE000ED2C 1   HFSR

7. 必要时读 fault 地址
   mdw 0xE000ED34 1   MMFAR
   mdw 0xE000ED38 1   BFAR

8. 读 VTOR 和向量表
   mdw 0xE000ED08 1
   mdw <VTOR> 8

9. 如果 PC 在外部 flash
   对比 CBUS/XIP 和 SBUS/raw alias。
```

## 9. 本次案例的最小复盘

现场：

```text
pc = 0xeffffffe
xPSR = 0x01000003
```

说明停在 Secure HardFault/lockup。

读 Non-secure 栈帧：

```text
stacked pc = 0x08376eb0
stacked lr = 0x083905cd
```

`addr2line`：

```text
0x08376eb0 -> _rt_mutex_take
0x083905cd -> sensor_update_latest()
```

继续对比地址别名：

```text
0x08376eb0: ffffffff ffffffff ffffffff ffffffff ...
0x60376eb0: 4ff0e92d 4691b087 46049103 ...

0x181042b8: ffffffff ffffffff ...
0x701042b8: b480e7fd f01eaf00 ...
```

结论：

```text
不是 mutex 逻辑本身坏；
而是外部 flash 的 CBUS/XIP 执行视图读到擦除态；
raw/SBUS 视图里代码是正常的。
```

## 10. 学习路线

建议按这个顺序练：

```text
第 1 步：C 指针和 memory-mapped register
第 2 步：PC/LR/SP/xPSR
第 3 步：异常栈帧
第 4 步：CFSR/HFSR/BFAR/MMFAR
第 5 步：VTOR 和向量表
第 6 步：TrustZone Secure/Non-secure
第 7 步：外部 flash XIP 和地址别名
```

不要试图一次背完所有寄存器。真正的能力是：

```text
看到现象 -> 知道该读哪几个寄存器 -> 让这些寄存器互相印证。
```
