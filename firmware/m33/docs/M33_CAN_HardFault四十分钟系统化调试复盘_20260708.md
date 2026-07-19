# M33 CAN / HardFault 四十分钟系统化调试复盘

日期：2026-07-08

主题：M33 侧 CAN 不回包、HardFault、TrustZone 异常接管、CAN RX 读法修复、NanoPi/ROS/cloud 链路验证。

这份文档记录主线程约四十分钟的真实排查过程。重点不是只写“最后通了”，而是复盘每一步为什么这么判断、证据是什么、下一步为什么要这么走。后续没有 AI 辅助时，也可以照这套方法定位类似问题。

## 1. 最终结论

这轮调试最后确认了几件事：

1. M33 之前不是单纯 CAN 不通，而是在 CAN RX 路径触发了 HardFault。
2. RT-Thread 的 `g_rt_hw_fault_dump` 没写入，是因为 HardFault 被 Cortex-M33 TrustZone 的 Secure handler 接管了，不是因为没有 fault。
3. 通过 Secure handler 入口断点和 `MSP_NS / CONTROL_NS`，拿到了真正的 Non-secure 异常栈。
4. 第一阶段 fault 现场显示崩溃暴露在 SysTick / RT-Thread scheduler 路径，这提示要查“谁提前破坏了内存”，不能只盯 CAN 表象。
5. 后续新 fault 明确落在 `drv_can.c` 手写 CAN RX 读取代码第 1020 行附近。
6. 根因是 Non-secure CPU 直接读取固定 MRAM 地址 `0x42850000` 会触发 BusFault/HardFault；OpenOCD 能读这个地址，不代表 Non-secure 程序运行时能直接读。
7. 修复方式是不用硬编码 MRAM 地址，改用 CANFD 硬件 FIFO TOP 寄存器读取 RX FIFO 元素。
8. 修复后 NanoPi 发 `0x321` heartbeat，M33 稳定回 `0x322`，重复帧问题消失，M33 halt 后确认不在异常态。
9. `0x320` 模式帧也被 M33 解析和应用，阻力/被动切换时 CAN 上能看到电机私有协议帧。
10. 云端 WAIT 的后续原因不是 M33 CAN 不回，而是 NanoPi ROS 环境排查问题：节点运行在 `ROS_DOMAIN_ID=42`，不带这个环境变量看不到正确 topic。

## 2. 一开始为什么不直接改 CAN

初始现象看起来像：

```text
M33 没收到 322
NanoPi 发包没响应
模式切不了
云端 WAIT
```

但主线程没有直接改 CAN 解析，而是先走系统化调试：

```text
先读本地指令和 fault/vector 代码
确认最终 ELF 用的是哪个 HardFault handler
只加“保存现场”的最小补丁
不继续乱拆链路
```

这个判断很重要。因为嵌入式里“没回包”可能有很多原因：

```text
CAN 没收到
CAN 收到但没解析
解析后进 fault
回包发了但 NanoPi 没看到
M33 shell 没起
云端/ROS 层没发布
```

如果不先确认 CPU 是否 fault，很容易在错误层面上改代码。

## 3. 第一步：确认最终 ELF 的 HardFault handler

主线程先查：

```powershell
arm-none-eabi-nm.exe -n .\rt-thread.elf | Select-String 'HardFault_Handler|UsageFault_Handler|BusFault_Handler|MemManage_Handler'
```

确认最终 ELF 中：

```text
HardFault_Handler = 0x08398292
rt_hw_hard_fault_exception = 0x0839834c
```

结论：

```text
最终用的是 RT-Thread 的 HardFault_Handler
不能在 main.c 里随便再写一个同名 handler
正确切入点应是 RT-Thread Cortex-M33 fault 路径
```

这一步防止了一个常见误区：看到启动文件里有弱符号 handler，就随手改启动文件或 main.c。最终链接用谁，要以 ELF 符号为准。

## 4. 第二步：加最小 fault dump 补丁

主线程读了：

```text
rt-thread/libcpu/arm/cortex-m33/context_gcc.S
rt-thread/libcpu/arm/cortex-m33/cpuport.c
```

发现 RT-Thread 已经把异常信息组织成 `exception_info` 传给：

```c
rt_hw_hard_fault_exception()
```

因此不需要重写汇编，只需要在 C 入口最前面保存一份全局 dump。

设计原则：

```text
不依赖串口
不改变原来的打印/死循环逻辑
只保存现场到全局变量
用 DAP/OpenOCD 读内存
```

这是很好的嵌入式故障定位习惯。串口在 fault 时可能已经不可用，现场必须能从 DAP 读出来。

## 5. 第三步：编译、烧录、读取 dump

编译通过后烧录：

```text
program build/rtthread.hex verify
```

烧录需要注意：

```text
set DEVICE PSE84xGxS2
set ENABLE_CM55 1
```

因为 M33 镜像涉及外部 SMIF/QSPI 地址，烧录时需要 CM55/SMIF 依赖被拉起。否则容易出现：

```text
no flash bank found for address 0x60340400
wrote 0 bytes
```

烧录 verify OK 后，主线程读：

```text
g_rt_hw_fault_dump
```

结果：

```text
dump 仍然全 0
```

关键判断：

```text
不是“进了 RT-Thread HardFault C 函数但串口没打印”
而是异常没有顺利走到 rt_hw_hard_fault_exception()
```

这一步把排查方向从“RT-Thread dump 内容怎么解”转到了“异常为什么没有进 RT-Thread handler”。

## 6. 第四步：读 fault 状态寄存器

主线程 halt CPU 后读：

```text
PC / LR / MSP / PSP / xPSR
VTOR
ICSR
SHCSR
CFSR/HFSR 等 fault status
```

读到关键状态：

```text
CPU 确实在 HardFault active
CFSR = 0x00010000
```

`CFSR = 0x00010000` 表示：

```text
UsageFault.UNDEFINSTR
CPU 执行了未定义指令
```

但由于 dump 没写入，说明这个 fault 没正常进入 RT-Thread C handler。

## 7. 第五步：给 RT-Thread HardFault handler 下断点

主线程给两个地址下硬件断点：

```text
HardFault_Handler          0x08398292
rt_hw_hard_fault_exception 0x0839834c
```

第一次 `reset halt` 因为这块板子的 Test Mode acquisition 问题不作为代码证据。

换成：

```text
先挂断点
reset run
sleep
halt
```

结果：

```text
两个 RT-Thread handler 断点都没有命中
OpenOCD 报 double fault / lockup
```

关键判断：

```text
不是 C handler 里没写 dump
而是异常入口/向量路由阶段就没进 RT-Thread handler
```

下一步自然要查：

```text
VTOR 指向哪张向量表
HardFault vector 实际指向哪里
```

## 8. 第六步：读 VTOR 和向量表，发现 TrustZone 接管

主线程读当前 VTOR 指向的向量表，发现：

```text
RT-Thread HardFault_Handler = 0x08398293
实际 HardFault vector       = 0x181042bb
```

注意最低 bit 是 Thumb bit：

```text
0x08398293 实际代码入口是 0x08398292
0x181042bb 实际代码入口是 0x181042ba
```

结论：

```text
异常实际跳到了 0x181042ba 这套 Secure/vendor handler
所以 RT-Thread handler 断点不会命中
```

随后查 `0x18104xxx`：

```text
不属于当前 rt-thread.elf
addr2line 查不到
```

这进一步说明它属于预签名 Secure 固件或厂商安全域，而不是当前 Non-secure app。

## 9. 第七步：确认 BFHFNMINS 路由配置

主线程查到配置：

```text
SCB_AIRCR_BFHFNMINS_VAL = 0
```

含义：

```text
BusFault / HardFault / NMI 目标状态在 Secure state
```

这和现象完全吻合：

```text
Non-secure RT-Thread app 出错
        |
        v
HardFault 被 Secure handler 接管
        |
        v
RT-Thread dump 不写入
RT-Thread handler 断点不命中
```

同时发现当前工程合并的是预签名 Secure 固件：

```text
tools/edgeprotecttools/cm33_s_signed_fw/proj_cm33_s_signed.hex
```

所以仅修改当前工程里的：

```text
partition_ARMCM33.h
```

不能直接改变板子上实际运行的 Secure fault 路由。

## 10. 第八步：在 Secure HardFault 入口断住

既然 fault 被 Secure 接走，就改在实际 Secure handler 入口下断点：

```text
bp 0x181042ba 2 hw
```

断点命中后，说明判断正确。

读到：

```text
LR = 0xffffffa1
```

结合 Secure/Non-secure 异常返回语义，判断它正在处理来自 Non-secure 的 fault。

此时不能只读 Secure 的 `MSP/PSP`，而要读：

```text
MSP_NS
PSP_NS
CONTROL_NS
```

## 11. 第九步：从 MSP_NS 拿真正 Non-secure 异常栈

主线程读到：

```text
CONTROL_NS = 0
MSP_NS     = 0x240fcf18
```

判断规则：

```text
CONTROL_NS bit[1] = 0 -> Non-secure 使用 MSP_NS
CONTROL_NS bit[1] = 1 -> Non-secure 使用 PSP_NS
```

所以真正的异常栈在：

```text
0x240fcf18
```

Cortex-M 硬件异常栈格式：

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

解析出：

```text
stacked PC = 0x0839c1e0
stacked LR = 0x0839c555
xPSR       = 0x6100000f
```

`xPSR` 低位：

```text
0x0f = exception 15 = SysTick
```

说明：

```text
fault 发生时 Non-secure app 正在 SysTick 中断/RTOS tick 路径里
```

## 12. 第十步：addr2line/objdump 反查第一个现场

反查：

```powershell
arm-none-eabi-addr2line.exe -e .\rt-thread.elf -f -C 0x0839c1e0 0x0839c555
```

并用 objdump 看附近：

```powershell
arm-none-eabi-objdump.exe -d -S .\rt-thread.elf --start-address=0x0839c180 --stop-address=0x0839c600
```

定位到：

```text
RT-Thread SysTick / timer / scheduler 路径
_thread_timeout()
rt_schedule_insert_thread()
```

关键思维：

```text
崩溃点在 scheduler，不代表 scheduler 是根因
```

更合理判断：

```text
前面某段代码破坏了线程/定时器/链表/栈
SysTick 调度时第一个踩到坏对象
```

这一步建立了“崩溃点”和“破坏点”分离的判断。

## 13. 第十一步：继续缩小，发现 CAN RX 真实 fault

后续主线程继续测试 NanoPi 发包：

```text
321#A1...
321#A2...
7C1#0102030405060708
```

发现 M33 仍 fault。

读 CAN 相关寄存器/MRAM，看到硬件 FIFO 里确实有数据：

```text
说明硬件层收到了帧
问题在 M33 软件读取/解析 RX 数据路径
```

重新读取异常栈并反查新 PC：

```text
PC = 0x08398f20
```

`addr2line` 明确落在：

```text
drv_can.c 第 1020 行附近
```

也就是主线程之前手写的 CAN RX 读取 MRAM 元素地址代码。

## 14. 第十二步：确认根因是直接读固定 MRAM 地址

主线程查看源码和反汇编，确认 fault 点不是常量装载，而是真实 load：

```text
0x42850000 + index * 16
```

之前代码用固定基址读取 CAN MRAM：

```text
0x42850000
```

OpenOCD 能读这个地址，但程序运行时 Non-secure CPU 直接 load 会 fault。

这一步非常有价值：

```text
DAP 能读某地址 != Non-secure 程序运行时能读某地址
```

可能原因包括：

```text
安全属性
总线访问权限
外设窗口访问方式限制
MRAM 需要通过指定寄存器窗口读取
```

因此不能继续用硬编码 MRAM 地址读 FIFO 元素。

## 15. 第十三步：修复为 CANFD FIFO TOP 读法

主线程查 PDL：

```text
cy_canfd.c
RXFTOP
F0TPE
RXFTOP0_DATA
```

找到正确思路：

```text
打开 RXFTOP_CTL.F0TPE
通过 RXFTOP0_DATA 连续读取 R0/R1/data0/data1
不直接碰 MRAM 地址
```

修复策略：

```text
用硬件提供的 FIFO TOP 寄存器窗口读 RX FIFO 元素
避免 Non-secure CPU 直接访问 0x42850000 MRAM
```

这是最小修复：

```text
不拆 CAN 链路
不改 NanoPi 协议
不动 BLE
只修 RX 读取方式
```

## 16. 第十四步：验证 321 -> 322 回包恢复

修复后编译、烧录、verify OK。

NanoPi 上测试：

```bash
cansend can0 321#B100000000000000
cansend can0 321#B200000000000000
cansend can0 7C1#0102030405060708
candump -tz can0
```

结果：

```text
每次 321 都有单个 322 回包
重复回包问题也消失
```

随后 halt M33 读状态：

```text
xPSR = 0x81000000
CFSR/HFSR = 0
```

判断：

```text
M33 在 Thread 状态
不在 HardFault 异常态
CAN RX fault 已拿下
```

调试计数也显示：

```text
收到了 7C1 数据
收到了 heartbeat
```

## 17. 第十五步：验证 0x320 模式切换

主线程查代码确认模式帧：

```text
CAN ID = 0x320
Byte0 = 0x04  表示 SET_MODE
Byte1 = sequence
Byte2 = mode
```

模式值：

```text
0x00 passive
0x03 assist
0x04 resist
```

测试序列：

```bash
cansend can0 321#C1
cansend can0 320#0401030000000000   # seq=1 assist
cansend can0 321#C2
cansend can0 320#0402040000000000   # seq=2 resist
cansend can0 321#C3
cansend can0 320#0403000000000000   # seq=3 passive
cansend can0 321#C4
```

观察结果：

```text
发阻力/被动时 CAN 上出现电机私有协议帧
例如 0x0400FD04/05/06 和对应 0x0200...
```

说明：

```text
0x320 已经被 M33 执行到电机链路
模式切换不是完全没进 M33
```

随后读内存确认：

```text
最后一条 0x320 已解析成 04 03 00
即 set_mode seq=3 passive
ROS ID/解析/应用计数都在涨
```

## 18. 第十六步：云端 WAIT 继续定位到 NanoPi ROS 环境

M33 CAN 已确认：

```text
每秒 321 都有 322
0x320 模式帧能执行
M33 不在 fault
```

但云端仍 WAIT。

这时主线程没有回头怀疑 M33，而是继续分层：

```text
M33 CAN 层已通
下一层查 NanoPi ROS bridge/uploader
```

NanoPi 进程存在：

```text
psoc_can_bridge_node.py
sensor_state_uploader_node.py
VLA upload loop
can0 UP
```

但最初 `ros2 topic list` 只看到 `/rosout`，日志有：

```text
no PSoC status
```

继续查进程环境，发现：

```text
ROS_DOMAIN_ID=42
```

而手动 shell 查询时没带这个环境，所以看不到正确 ROS graph。

带上环境：

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

再查 topic，就能看到相关 topic 名字。

这个结论很重要：

```text
云端 WAIT 后续不是 M33 CAN 不回
而是 NanoPi ROS/uploader 层还需要继续查 publisher/discovery/status 发布
```

## 19. 这四十分钟里的关键方法论

### 19.1 分层，不跳层

这次链路很长：

```text
NanoPi cansend
  -> CAN 总线
  -> M33 CAN RX 硬件
  -> M33 CAN driver
  -> control parser
  -> rehab mode manager
  -> 电机私有协议帧
  -> NanoPi ROS bridge
  -> uploader
  -> 云平台页面
```

排查时不能看到云端 WAIT 就直接改云端，也不能看到 M33 没回 322 就直接改协议。

每一层都要回答：

```text
这一层有没有输入？
这一层有没有输出？
这一层有没有 fault？
```

### 19.2 先证明 CPU 活着

CAN 不回包时，第一问题不是格式，而是：

```text
M33 是否还活着？
是否进 HardFault？
是否在 Thread state？
CFSR/HFSR 是否为 0？
```

如果 CPU 已 fault，再调协议没有意义。

### 19.3 dump 没有，不代表没 fault

本次 `g_rt_hw_fault_dump` 全 0，但 CPU 实际 fault。

原因：

```text
TrustZone Secure handler 接管了 HardFault
RT-Thread Non-secure dump 没机会写
```

所以：

```text
dump 无效 -> 查 VTOR/vector/Secure handler
```

### 19.4 断点没中，不代表不会进异常

RT handler 断点没中，是因为实际 vector 指向：

```text
0x181042bb
```

而不是：

```text
0x08398293
```

所以断点必须打在真实 vector 指向的地址。

### 19.5 DAP 能读，不代表程序能读

这是本次最实用的底层教训之一。

OpenOCD 能读：

```text
0x42850000
```

但 Non-secure M33 程序直接 load 可能 BusFault。

外设/MRAM/安全映射地址必须按芯片手册和 PDL 推荐方式访问。

### 19.6 崩溃点不等于根因

第一次 PC 落在 SysTick scheduler。

这只能说明：

```text
调度时踩到了坏现场
```

后续继续缩小，才找到更明确的 CAN RX MRAM 直接读取 fault。

## 20. 后续自己定位类似问题的固定流程

以后遇到 M33/CAN/RTOS 类问题，按这个流程：

```text
1. 复现问题，记录触发动作
2. 抓串口最后日志
3. halt CPU，读 PC/LR/xPSR/MSP/PSP
4. 读 CFSR/HFSR/SHCSR/AIRCR/VTOR
5. 看 RT fault dump 是否有效
6. 如果 dump 无效，查 VTOR 和 HardFault vector
7. 判断异常是否被 Secure handler 接管
8. 如果是 Secure 接管，断 0x181... handler
9. 读 MSP_NS/PSP_NS/CONTROL_NS
10. 从异常栈 +0x18 取 stacked PC
11. addr2line/objdump 反查
12. 判断崩溃点
13. 继续通过最小输入复现，缩小破坏点
14. 每次只改一个变量
15. 编译、烧录、verify
16. 用 CAN 抓包和 CPU fault 状态双重验证
17. 再往 NanoPi/ROS/cloud 上层查
```

## 21. 本次关键命令备忘

### 查符号

```powershell
$nm='F:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin\arm-none-eabi-nm.exe'
& $nm -n .\rt-thread.elf | Select-String 'HardFault_Handler|rt_hw_hard_fault_exception|g_rt_hw_fault_dump'
```

### 读 fault 状态

```text
reg pc
reg lr
reg msp
reg psp
reg xpsr
mdw 0xE000ED08 1
mdw 0xE000ED24 1
mdw 0xE000ED28 8
```

### 断 Secure HardFault

```text
bp 0x181042ba 2 hw
reset run
sleep 2500
halt
reg msp_ns
reg psp_ns
reg control_ns
```

### 反查地址

```powershell
$addr2line='F:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin\arm-none-eabi-addr2line.exe'
& $addr2line -e .\rt-thread.elf -f -C 0x08398f20
```

### NanoPi CAN 验证

```bash
candump -tz can0
cansend can0 321#B100000000000000
cansend can0 321#B200000000000000
cansend can0 7C1#0102030405060708
```

### 模式切换验证

```bash
cansend can0 321#C1
cansend can0 320#0401030000000000
cansend can0 321#C2
cansend can0 320#0402040000000000
cansend can0 321#C3
cansend can0 320#0403000000000000
```

### ROS_DOMAIN_ID 验证

```bash
source /opt/ros/jazzy/setup.bash
source ~/rehab_arm_ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
ros2 topic list
ros2 node list
```

## 22. 本次修复的核心代码方向

CAN RX 读取从：

```text
直接按固定 0x42850000 + index * 16 读 MRAM
```

改成：

```text
使用 CANFD FIFO TOP 寄存器窗口读取
打开 RXFTOP_CTL.F0TPE
连续读 RXFTOP0_DATA 获取 R0/R1/data0/data1
```

修复原因：

```text
避免 Non-secure CPU 直接访问不可直接 load 的 MRAM 地址
使用芯片/PDL 推荐的硬件寄存器窗口路径
```

验证结果：

```text
321 -> 322 稳定
无重复回包
M33 不再 HardFault
0x320 mode command 能进入电机链路
```

## 23. 学习总结

这四十分钟最值得学的是：

```text
不要被“CAN 不通”这个表象牵着走。
先证明 CPU 是否活着。
再证明 fault 是否进了你的 handler。
再根据 TrustZone 判断真正 handler 在哪里。
再从正确的 Non-secure 异常栈取 PC。
再反查代码。
再缩小到具体一行。
最后用最小修复验证。
```

一句话：

```text
系统化调试不是慢，而是避免在错误层面上快。
```

这次之所以能从“322 没回”走到“CAN RX MRAM 直接读取 BusFault”，靠的就是每一步都用硬证据关掉一个假设。
