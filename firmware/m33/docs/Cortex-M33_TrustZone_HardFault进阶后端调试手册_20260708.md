# Cortex-M33 TrustZone / HardFault 进阶后端调试手册

日期：2026-07-08

适用项目：PSoC Edge / Cortex-M33 / RT-Thread / TrustZone / OpenOCD / NanoPi-CAN 康复控制链路

## 1. 这份文档解决什么问题

在 Cortex-M33 上调试 HardFault，比普通 STM32F4/F7 复杂很多。原因是 Cortex-M33 可能启用了 TrustZone，CPU 内部有 Secure 和 Non-secure 两个安全状态。

普通 Cortex-M 项目里，HardFault 通常直接进应用自己的 `HardFault_Handler`，然后 RTOS 或用户代码可以打印异常栈。

但在 Cortex-M33 TrustZone 项目里，HardFault 可能被 Secure 世界接管。这样会出现非常迷惑的现象：

- M33 串口不出 `msh />`。
- RT-Thread 的 `rt_hw_hard_fault_exception()` 没打印。
- 自己在 RT-Thread HardFault handler 打断点也不命中。
- OpenOCD 显示 CPU 确实在 HardFault / Lockup。
- CAN、BLE、F103、NanoPi 看起来像都不通，但真实原因可能是系统早期已经 fault。

这份文档教你一套完整的后端调试方法：

```text
寄存器 -> fault 类型 -> Secure/Non-secure 路由 -> 异常栈 -> stacked PC -> addr2line -> 代码现场
```

## 2. 必须先懂的几个概念

### 2.1 Cortex-M33

Cortex-M33 是 Armv8-M 架构的 MCU 内核。相比 Cortex-M3/M4，它支持更多安全和调试特性，其中最关键的是 TrustZone。

在普通业务里，你看到的是：

```text
M33 跑 RT-Thread
M55 跑 AI/模型/语音
NanoPi 通过 CAN/ROS2 交互
F103 采集肌电/传感器
```

但在底层启动和异常处理里，M33 不是一个简单的“裸 Cortex-M”。它可能有：

```text
Secure boot
Secure firmware
Non-secure RT-Thread app
Secure vector table
Non-secure vector table
Secure stack
Non-secure stack
```

### 2.2 TrustZone 是什么

TrustZone 是 Arm 的硬件安全隔离机制。它把一个 CPU 分成两个安全状态：

```text
Secure state
Non-secure state
```

可以粗略理解为：

```text
Secure      = 启动、安全配置、受保护资源、异常路由、厂商安全固件
Non-secure  = 普通应用、RT-Thread、CAN、BLE、rehab 控制逻辑
```

这不是两个 CPU，而是同一个 Cortex-M33 内核在不同安全状态下运行。

### 2.3 Secure 和 Non-secure 分别有什么

常见划分：

```text
Secure:
  - Secure boot
  - 安全配置
  - Secure vector table
  - Secure fault handler
  - 访问控制配置
  - 某些安全外设和安全内存

Non-secure:
  - RT-Thread
  - M33 shell
  - CAN 控制
  - BLE APP 链路
  - rehab service
  - M33 与 M55 IPC 业务逻辑
```

所以当你调试 `RT-Thread HardFault` 时，必须先判断：异常到底进了 Non-secure RT-Thread，还是被 Secure handler 接走了。

## 3. 为什么这次不能像普通 STM32 那样调

普通 Cortex-M HardFault 调试常用套路：

1. 进 `HardFault_Handler`。
2. 判断用 MSP 还是 PSP。
3. 从异常栈取 PC。
4. `addr2line` 反查代码。

在 Cortex-M33 TrustZone 项目里，这套流程可能失效，因为 fault 不一定进 Non-secure handler。

本项目里看到的现象是：

```text
g_rt_hw_fault_dump 全 0
RT-Thread HardFault handler 断点不命中
OpenOCD 报 HardFault / double fault / lockup
当前 VTOR 指向 Secure vector table
SCB_AIRCR_BFHFNMINS_VAL = 0
```

这意味着：

```text
Non-secure app 发生 fault
        |
        v
HardFault 被路由到 Secure state
        |
        v
RT-Thread 的 rt_hw_hard_fault_exception() 没机会执行
```

所以你不能只读普通 `MSP/PSP`，还要读：

```text
MSP_NS
PSP_NS
CONTROL_NS
SCB_NS->VTOR
Secure SCB->VTOR
AIRCR.BFHFNMINS
```

## 4. 异常栈帧：最重要的基础

### 4.1 CPU 自动压栈什么

Cortex-M 进入异常时，硬件会自动压入一个基本栈帧：

```text
offset  内容
0x00    r0
0x04    r1
0x08    r2
0x0C    r3
0x10    r12
0x14    lr
0x18    pc
0x1C    xpsr
```

所以，只要你找到了正确的异常栈地址，就能拿到：

```text
stacked PC = stack + 0x18
stacked LR = stack + 0x14
stacked xPSR = stack + 0x1C
```

这是 HardFault 定位里最关键的公式。

### 4.2 为什么 PC 最重要

PC 是 fault 发生时 CPU 要执行或刚刚执行到的位置。

拿到 PC 后，用：

```powershell
arm-none-eabi-addr2line.exe -e .\rt-thread.elf -f -C 0x0839c1e0
```

就可以反查到函数名和源码行。

如果没有源码行，也可以用：

```powershell
arm-none-eabi-objdump.exe -d -S .\rt-thread.elf --start-address=0x0839c180 --stop-address=0x0839c600
```

看反汇编。

## 5. MSP、PSP、MSP_NS、PSP_NS

### 5.1 MSP 和 PSP

Cortex-M 有两种栈指针：

```text
MSP = Main Stack Pointer
PSP = Process Stack Pointer
```

典型 RTOS 用法：

```text
中断/异常       用 MSP
线程上下文       常用 PSP
```

但具体要看 `CONTROL` 寄存器。

### 5.2 TrustZone 下有两套栈

Cortex-M33 TrustZone 下，Secure 和 Non-secure 各有一套：

```text
MSP_S / PSP_S
MSP_NS / PSP_NS
```

OpenOCD 里通常可以读：

```text
reg msp
reg psp
reg msp_ns
reg psp_ns
reg control_ns
```

如果异常被 Secure 接管，但 fault 起源于 Non-secure app，那么你真正要看的往往是：

```text
MSP_NS 或 PSP_NS
```

### 5.3 CONTROL_NS 怎么用

`CONTROL_NS` 可以判断 Non-secure thread mode 使用哪个栈。

常见判断：

```text
CONTROL_NS bit[1] = 0 -> 使用 MSP_NS
CONTROL_NS bit[1] = 1 -> 使用 PSP_NS
```

本项目现场里读到：

```text
CONTROL_NS = 0
```

所以判断：

```text
Non-secure 异常栈在 MSP_NS
```

再读：

```text
MSP_NS = 0x240fcf18
```

则：

```text
stacked PC = *(0x240fcf18 + 0x18)
```

## 6. VTOR 和向量表

### 6.1 VTOR 是什么

VTOR 是 Vector Table Offset Register，表示当前异常向量表在哪里。

异常发生时，CPU 会从向量表里取 handler 地址。

例如：

```text
vector[0] = 初始 SP
vector[1] = Reset_Handler
vector[2] = NMI_Handler
vector[3] = HardFault_Handler
...
```

### 6.2 TrustZone 下有两个 VTOR

普通 Cortex-M 只有一个 SCB->VTOR。

Cortex-M33 TrustZone 下要区分：

```text
Secure SCB->VTOR
Non-secure SCB_NS->VTOR
```

如果 CPU 当前停在 Secure HardFault，那么读普通：

```text
mdw 0xE000ED08 1
```

读到的是 Secure VTOR。

Non-secure VTOR 通常在：

```text
SCB_NS->VTOR
```

调试时要两边都看。

### 6.3 本项目里的关键判断

当时读到当前 VTOR 指向 RAM vector，HardFault vector 不是 RT-Thread 的：

```text
RT-Thread HardFault_Handler = 0x08398293
实际向量表里的 HardFault vector = 0x181042bb
```

这说明异常实际跳进了 Secure 固件里的 handler，而不是 RT-Thread 的 handler。

这就是为什么 RT-Thread 的 fault dump 没写入。

## 7. AIRCR.BFHFNMINS：HardFault 到底给谁处理

### 7.1 它控制什么

在 Armv8-M TrustZone 中，`AIRCR.BFHFNMINS` 控制 BusFault、HardFault、NMI 的目标安全状态。

本项目配置里看到：

```text
SCB_AIRCR_BFHFNMINS_VAL = 0
```

含义是：

```text
BusFault / HardFault / NMI target Secure state
```

所以即使 Non-secure app 出错，HardFault 也可能被 Secure 侧接住。

### 7.2 为什么改工程里的 partition 不一定生效

本项目使用的是预签名 Secure 固件，例如：

```text
tools/edgeprotecttools/cm33_s_signed_fw/proj_cm33_s_signed.hex
```

如果 Secure 镜像不是当前工程重新编译和签名生成的，那么你改：

```text
partition_ARMCM33.h
```

可能不会影响板子上真正运行的 Secure 配置。

所以解决方向有两个：

```text
方案 A：重新生成 Secure 固件，让 HardFault 回到 Non-secure RT handler
方案 B：接受 Secure 接管，在 Secure handler 入口读 MSP_NS/PSP_NS 手动解析现场
```

当前更现实的是方案 B。

## 8. Fault 状态寄存器怎么看

### 8.1 常用寄存器

常用 SCB fault/status 寄存器：

```text
0xE000ED04  ICSR
0xE000ED08  VTOR
0xE000ED0C  AIRCR
0xE000ED24  SHCSR
0xE000ED28  CFSR
0xE000ED2C  HFSR
0xE000ED30  DFSR
0xE000ED34  MMFAR
0xE000ED38  BFAR
```

OpenOCD 读取：

```text
mdw 0xE000ED04 1
mdw 0xE000ED08 1
mdw 0xE000ED0C 1
mdw 0xE000ED24 1
mdw 0xE000ED28 8
```

如果要看 Non-secure SCB_NS，地址通常是 Secure alias 下的 NS SCB 区域，调试时可尝试：

```text
mdw 0xE002ED08 1
mdw 0xE002ED28 8
mdw 0xE002ED0C 1
```

具体芯片和调试器支持会有差异。

### 8.2 CFSR 的结构

CFSR 是 Configurable Fault Status Register，可以拆成：

```text
MMFSR  = CFSR[7:0]
BFSR   = CFSR[15:8]
UFSR   = CFSR[31:16]
```

本项目现场读到：

```text
CFSR = 0x00010000
```

高 16 位 UFSR 的 bit0 置位：

```text
UNDEFINSTR
```

含义是：

```text
执行了未定义指令
```

这可能是真正跳到了错误地址，也可能是栈/函数指针/返回地址被破坏后，CPU 从非代码区域或错误地址取指。

## 9. xPSR 怎么看

异常栈里的 xPSR 也很有价值。

本项目现场：

```text
xPSR = 0x6100000f
```

xPSR 低位 IPSR 表示当前异常号。

```text
0x0f = 15
```

Cortex-M 异常号 15 是 SysTick。

所以可以判断：

```text
HardFault 发生时，Non-secure app 正在处理 SysTick
```

这就解释了为什么 CAN 可能已经发了几帧，随后系统 tick/调度一跑就 fault。

## 10. 本项目这次现场是怎么一步步判断的

### 10.1 先读 RT-Thread fault dump

目标：

```text
看 g_rt_hw_fault_dump 是否有 magic
```

如果有：

```text
magic = FA17FA17
```

说明进了 RT-Thread 的 C 级 fault handler。

当时结果：

```text
g_rt_hw_fault_dump 全 0
```

判断：

```text
没有进入 RT-Thread 的 rt_hw_hard_fault_exception()
```

### 10.2 给 RT handler 打断点

查符号：

```powershell
arm-none-eabi-nm.exe -n .\rt-thread.elf | Select-String 'HardFault_Handler|rt_hw_hard_fault_exception'
```

得到类似：

```text
HardFault_Handler = 0x08398292
rt_hw_hard_fault_exception = 0x0839834c
```

打断点后不命中，反而出现 double fault / lockup。

判断：

```text
异常没有走 RT-Thread 的 Non-secure HardFault handler
```

### 10.3 读 Secure VTOR

读：

```text
mdw 0xE000ED08 1
```

再读 VTOR 指向的向量表：

```text
mdw <VTOR地址> 24
```

发现 HardFault vector 指向：

```text
0x181042bb
```

而不是 RT-Thread 的：

```text
0x08398293
```

判断：

```text
HardFault 被 Secure 固件接管
```

### 10.4 在 Secure HardFault 入口断住

给实际 Secure handler 入口打断点：

```text
bp 0x181042ba 2 hw
reset run
sleep 2500
halt
```

读寄存器：

```text
reg pc
reg lr
reg msp_ns
reg psp_ns
reg control_ns
```

得到：

```text
CONTROL_NS = 0
MSP_NS = 0x240fcf18
```

判断：

```text
Non-secure 异常栈在 MSP_NS
```

### 10.5 解析异常栈

读：

```text
mdw 0x240fcf00 48
```

按照：

```text
r0 r1 r2 r3 r12 lr pc xpsr
```

解析出：

```text
stacked PC = 0x0839c1e0
stacked LR = 0x0839c555
xPSR       = 0x6100000f
```

判断：

```text
异常发生时正在 SysTick 中断里
```

### 10.6 addr2line / objdump 反查

执行：

```powershell
arm-none-eabi-addr2line.exe -e .\rt-thread.elf -f -C 0x0839c1e0 0x0839c555
```

再用 objdump 看上下文：

```powershell
arm-none-eabi-objdump.exe -d -S .\rt-thread.elf --start-address=0x0839c180 --stop-address=0x0839c600
```

定位到 RT-Thread tick/timer/scheduler 路径：

```text
_thread_timeout()
rt_schedule_insert_thread()
```

最终判断：

```text
第一现场不是 CAN 驱动本身，而是 SysTick 唤醒线程/调度线程时触发 fault。
CAN 前面发过帧，只是随后调度路径炸了。
```

## 11. OpenOCD 常用命令模板

### 11.1 基础连接并 halt

```powershell
$openocd='F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin\openocd.exe'
$scripts='F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\scripts'

& $openocd `
  -s $scripts `
  -f interface/kitprog3.cfg `
  -c 'set DEVICE PSE84xGxS2' `
  -c 'set ENABLE_CM55 0' `
  -f target/infineon/pse84.cfg `
  -c 'adapter serial 17040F11022F2400' `
  -c 'transport select swd' `
  -c "init; targets cat1d.cm33; halt; reg pc; reg lr; reg msp; reg psp; reg xpsr; shutdown"
```

### 11.2 读取 fault/status 寄存器

```text
mdw 0xE000ED08 1
mdw 0xE000ED04 1
mdw 0xE000ED24 1
mdw 0xE000ED28 8
mdw 0xE000ED0C 1
```

### 11.3 读取 Non-secure 扩展寄存器

```text
reg msp_ns
reg psp_ns
reg msplim_ns
reg psplim_ns
reg control_ns
reg primask_ns
reg basepri_ns
reg faultmask_ns
```

### 11.4 在 Secure HardFault 入口断住

```text
bp 0x181042ba 2 hw
reset run
sleep 2500
halt
reg pc
reg lr
reg msp_ns
reg psp_ns
reg control_ns
rbp all
```

### 11.5 读取异常栈

假设：

```text
MSP_NS = 0x240fcf18
```

则：

```text
mdw 0x240fcf18 8
```

解析：

```text
word0 = r0
word1 = r1
word2 = r2
word3 = r3
word4 = r12
word5 = lr
word6 = pc
word7 = xpsr
```

## 12. addr2line / objdump 常用命令

### 12.1 查符号地址

```powershell
$nm='F:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin\arm-none-eabi-nm.exe'
& $nm -n .\rt-thread.elf | Select-String 'HardFault_Handler|rt_hw_hard_fault_exception'
```

### 12.2 地址反查函数和源码行

```powershell
$addr2line='F:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin\arm-none-eabi-addr2line.exe'
& $addr2line -e .\rt-thread.elf -f -C 0x0839c1e0 0x0839c555
```

### 12.3 反汇编某段地址

```powershell
$objdump='F:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin\arm-none-eabi-objdump.exe'
& $objdump -d -S .\rt-thread.elf --start-address=0x0839c180 --stop-address=0x0839c600
```

## 13. 看到不同现象时怎么判断

### 13.1 `g_rt_hw_fault_dump` 有 magic

说明：

```text
进入了 RT-Thread fault handler
```

处理：

```text
直接解析 dump 里的 stacked PC
addr2line 反查
```

### 13.2 dump 全 0，但 CPU 在 HardFault

说明可能：

```text
没有进 RT handler
异常被 Secure 接管
或者 handler 入口前就 double fault
```

处理：

```text
读 VTOR
读向量表
读 BFHFNMINS
断 Secure handler
读 MSP_NS/PSP_NS
```

### 13.3 CFSR 是 UNDEFINSTR

说明：

```text
CPU 执行了未定义指令
```

常见原因：

- 函数指针被踩。
- 返回地址被踩。
- 线程栈溢出。
- 跳到 RAM 数据区执行。
- flash 地址/relocation 错。
- Thumb bit 错误。
- 异常返回栈帧损坏。

### 13.4 xPSR 异常号是 15

说明：

```text
fault 发生时正在 SysTick
```

优先查：

- RT-Thread timer list。
- 线程对象。
- scheduler ready list。
- 是否有线程栈溢出。
- 是否有野指针破坏内核链表。

### 13.5 断点不命中 RT handler

优先怀疑：

```text
HardFault 被 Secure handler 接管
```

不要急着改 CAN。

## 14. 对 RT-Thread 调度现场的理解

如果 PC 落在：

```text
_thread_timeout()
rt_schedule_insert_thread()
rt_timer_check()
SysTick_Handler()
```

这不一定说明 RT-Thread 内核有 bug。

更常见的是：

```text
某个模块把线程对象/定时器对象/链表节点/栈破坏了
SysTick 刚好扫描或调度时踩到坏数据
```

所以应回查最近改动：

- 多线程共享数据有没有锁。
- ISR 里有没有调用非 ISR-safe API。
- 数组下标有没有越界。
- joint id 和 array index 有没有混用。
- `memcpy` 长度有没有错。
- 结构体版本有没有两边不一致。
- 线程栈是否太小。

## 15. 本项目下一步应该重点查什么

结合“三路助力前 CAN 还能通”的历史，重点不是先怀疑 CAN driver，而是查三路助力/阻力改动是否踩内核数据结构。

优先检查：

### 15.1 joint id 到数组下标

危险写法：

```c
state[joint_id]
```

如果 `joint_id` 是 4/5/6，而数组长度是 `CONTROL_MOTOR_JOINT_COUNT`，可能越界。

更安全：

```c
index = joint_id - 1;
if (index >= CONTROL_MOTOR_JOINT_COUNT) return -RT_EINVAL;
```

### 15.2 mask 遍历

例如 mask `0x38` 表示 joint 4/5/6。

遍历时要确认：

```c
bit = 1U << (joint - 1)
index = joint - 1
```

不要把 bit mask 当数组 index。

### 15.3 rehab service 状态结构体

重点看：

- `active_joint_mask`
- `assist_engaged_mask`
- per-joint strategy state arrays
- worker thread 里是否越界访问
- status copy 是否结构体大小一致

### 15.4 线程栈

如果新增三路控制后线程栈变深，可能造成栈溢出。

优先加大：

- control thread stack
- rehab worker stack
- CAN RX processing thread stack
- BLE 相关线程栈

### 15.5 ISR 和 callback

CAN RX ISR 或回调里不要做重活：

- 不要阻塞等待。
- 不要拿可能阻塞的 mutex。
- 不要长时间解析。
- 不要直接调复杂 rehab 状态机。

推荐：

```text
ISR/callback 只入队
worker thread 里处理
```

## 16. 安全调试顺序

在电机/康复臂场景中，不要一上来切阻力/助力。

推荐顺序：

```text
1. 只确认 M33 shell
2. 只确认 CAN debug 计数
3. 只确认 F103 sensor 数据
4. 只开启电机 feedback report
5. 只读 motor feedback
6. 跑 prearm check
7. NanoPi 只发 passive
8. NanoPi 发 assist/resist 但不让电机输出大力
9. 短测后立即 passive
```

M33 shell 命令：

```text
cmd_control_debug
cmd_sensor_show
cmd_motor_report 4 1
cmd_motor_report 5 1
cmd_motor_report 6 1
cmd_motor_fb 4
cmd_motor_fb 5
cmd_motor_fb 6
cmd_m33_prearm_check 0x38
rehab status
cmd_ros_last
```

NanoPi 侧：

```bash
/home/pi/rehab_mode.sh passive
/home/pi/rehab_mode.sh resist
/home/pi/rehab_mode.sh passive
```

## 17. 如何把这套方法变成固定脚本

建议后续做两个脚本。

### 17.1 `tools/m33_fault_snapshot.ps1`

功能：

- halt CM33
- 读 PC/LR/MSP/PSP/xPSR
- 读 MSP_NS/PSP_NS/CONTROL_NS
- 读 Secure/NS VTOR
- 读 CFSR/HFSR/SHCSR/AIRCR
- dump 当前栈附近 128 words

输出保存到：

```text
build/fault_snapshot_YYYYMMDD_HHMMSS.log
```

### 17.2 `tools/m33_decode_fault.ps1`

功能：

- 输入 stacked PC/LR
- 自动运行 addr2line
- 自动 objdump 前后 0x100 字节
- 输出 fault 解读模板

## 18. 常见误区

### 18.1 “CAN 发了几帧，所以 CAN driver 崩了”

不一定。

如果 fault PC 在 SysTick/调度路径，说明 CAN 可能只是前面做过事情，真正炸点在调度时暴露。

### 18.2 “RT-Thread 没打印 HardFault，所以不是 HardFault”

不对。

TrustZone 下 HardFault 可能被 Secure handler 接走，RT-Thread 没机会打印。

### 18.3 “改 partition_ARMCM33.h 就能改变异常路由”

不一定。

如果 Secure 固件是预签名 hex，当前工程里的 header 不会影响已经签好的 Secure 镜像。

### 18.4 “看到 UNDEFINSTR 就是代码里写了非法指令”

不一定。

更多时候是跳飞了：

- 栈坏了。
- 函数指针坏了。
- 返回地址坏了。
- vector 表坏了。
- Thumb bit 错了。

## 19. 官方参考资料

以下是 Arm 官方资料，建议收藏：

- Cortex-M33 exception entry/return 和异常栈帧：  
  https://developer.arm.com/documentation/100235/0003/the-cortex-m33-processor/exception-model/exception-entry-and-return

- Cortex-M33 exception return / EXC_RETURN：  
  https://developer.arm.com/documentation/100235/0100/The-Cortex-M33-Processor/Exception-model/Exception-entry-and-return/Exception-return

- Cortex-M33 fault handling / Lockup：  
  https://developer.arm.com/documentation/100235/0100/The-Cortex-M33-Processor/Fault-handling/Lockup

- Cortex-M33 Configurable Fault Status Register：  
  https://developer.arm.com/documentation/100235/0004/the-cortex-m33-peripherals/system-control-block/configurable-fault-status-register

- Cortex-M33 exception handlers，包含 `AIRCR.BFHFNMINS` 说明：  
  https://developer.arm.com/documentation/100235/0100/The-Cortex-M33-Processor/Exception-model/Exception-handlers

- Armv8-M Exception Priority Scheme and Security Extension：  
  https://developer.arm.com/documentation/ka001410/latest/

- Cortex-M33 core registers：  
  https://developer.arm.com/documentation/100235/0004/the-cortex-m33-processor/programmer-s-model/core-registers

- VTOR register and vector table overview：  
  https://developer.arm.com/documentation/107706/0100/Exceptions-and-interrupts-overview/Vector-table/VTOR-register-and-initialization

## 20. 一句话总结

在 Cortex-M33 TrustZone 项目里，HardFault 调试不能只看 RT-Thread 的 handler。正确路径是：

```text
先判断 fault 被 Secure 还是 Non-secure 接管
再找正确的 MSP/PSP 或 MSP_NS/PSP_NS
再从异常栈 +0x18 取 stacked PC
最后用 addr2line/objdump 回到代码
```

本项目这次的关键结论是：

```text
fault 被 Secure HardFault handler 接管
RT-Thread dump 没写入
真实 Non-secure 异常栈在 MSP_NS
stacked PC 落在 SysTick/RT-Thread 调度路径
下一步应重点查线程/定时器/调度数据结构是否被三路 rehab 改动踩坏
```
