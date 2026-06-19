# CAN 总线电机打通调试与代码复盘

日期：2026-06-05

对象：M33 / NanoPi / CAN 电机链路

目的：把 Git 历史里的 CAN bring-up、真实电机联调、NanoPi/ROS 安全门和后续 M55 shadow 验证整理成一份学习型复盘。重点不是“AI 写了哪些代码”，而是“AI 如何从证据里学习、缩小问题域、写出下一步代码”。

## 1. 先说结论

这条链路不是一次写对的，而是靠分层实验逐步打通：

1. 先确认 M33 能访问 CANFD0 寄存器。
2. 再绕开复杂上层，用 PDL 最小初始化、最小发送、最小轮询验证硬件链路。
3. 再确认电机协议帧：Classic CAN、1 Mbps、RobStride Get_ID、真实 motor_id 与 UID。
4. 再把最小链路封装成 control layer 能用的 direct PDL API。
5. 再接 NanoPi SocketCAN 心跳与 M33 状态帧。
6. 再把“有状态帧”和“有 fresh 电机反馈”分开。
7. 最后才允许 ROS / MuJoCo / M55 进入只读、shadow 或受控台架路径。

真正打通的标志不是“某条命令 ret=0”，而是能同时看到：

- M33 `cmd_control_init can0` 走 direct PDL 成功。
- 电机 Get_ID 能回 `0x000001fe`，UID 可解析。
- NanoPi `can0` 是 `ERROR-ACTIVE`，心跳 `0x321 -> 0x322` 可见。
- M33 周期发 `0x330~0x334`，且目标电机槽位 stale bit 能在真实反馈出现后清零。
- 对 motor7 的只读/shadow 验证里，能看到原始 `0x180007FD`、M33 聚合 `0x334 fresh`、NanoPi `/joint_states`、MuJoCo shadow 同步。
- 只读服务期间没有意外 `0x320` 运动目标帧。

## 2. Git 时间线

| 日期 | 提交 | 复盘意义 |
| --- | --- | --- |
| 2026-03-29 | `c8d85b93` `phase1: define mixed-bus ID plan and classic socketcan setup` | 先把混合总线 ID、Classic CAN 和 SocketCAN 起步脚本定下来，避免边调边猜 ID。 |
| 2026-03-29 | `f57959e8` `phase2: implement f103 private can protocol and hardware filtering` | 传感节点协议先落地，说明系统一开始就不是单电机，而是多节点共享 CAN。 |
| 2026-03-29 / 03-31 | `837e76d9`、`0742be49` | control layer、`drv_can.c`、`CAN_config.h`、motor API 和 ROS `0x320` 入口成型。 |
| 2026-04-05 | `e5a38313` | 底层 CANFD0 bring-up 交接：寄存器访问、MMIO、PCLK、P16.0/P16.1、最小 PDL 命令。 |
| 2026-04-11 | `78ea5999` `Fix M33 CAN motor control bring-up` | 关键转折：确认 `can0`、Classic CAN、1 Mbps、direct PDL、Get_ID 回包、probe 去刷屏、FIFO drain limit。 |
| 2026-05-21 | `ce90173a` | M33 自动启动 control layer，NanoPi 心跳 `0x321/0x322`，电机数扩到 7，传感 ID 对齐。 |
| 2026-05-22 | `a01d4d89`、`51aedab5` | NanoPi MCP2518FD 时钟修为 20 MHz，同时记录 CH340 USB-CAN / SLCAN 不可靠路径。 |
| 2026-05-26 | `82fefa49`、`f608aeef`、`e701e3eb` | CANSimple 协议布局、motor3 tiny motion、M33 bench motion gate 和安全限位开始成体系。 |
| 2026-05-27 | `1e7ecb7b`、`746e0ad4`、`9d4d06f0` | 修正 false fresh、ROS joint 到 motor slot 映射、要求 fresh 反馈后才允许轨迹。 |
| 2026-05-28 | `b58ecaea`、`eaea6ed8` 等 | motor5/MIT/CSP 台架调试形成边界：直控只做 bench debug，正式控制必须回 M33 安全层。 |
| 2026-06-03 | `02da6525` | NanoPi CAN no-ACK 诊断：M33/M55/ROS 不能替代物理层 ACK 证据。 |
| 2026-06-04 | `a3579560`、`9f9aede5`、`40320052` | CAN 物理层恢复、motor7 M55 shadow 复验、direct TX pending 诊断日志补齐。 |

## 3. 调试复盘：AI 是怎么缩小问题域的

### 3.1 分层，不跨层猜

最开始的问题看起来像“电机不回包”。但历史证明它被拆成了多个独立层：

| 层 | 证明方式 | 结论 |
| --- | --- | --- |
| M33 non-secure MMIO | `cmd_can_reg_probe` 能读 `CTL/STATUS/IR` | 缺的是 HSIOM/GPIO/CANFD0 MMIO slave 初始化，不是协议问题。 |
| PDL 初始化 | `cmd_can_init_min` | `Cy_CANFD_Enable()` 和 `Cy_CANFD_Init()` 顺序没错。 |
| PDL 收发 | `cmd_can_send_probe` + `cmd_can_poll_once` | 先用最小链路判断硬件、收发器、波特率和电机协议。 |
| 电机协议 | `0x0000FD01 -> 0x000001fe` | RobStride Get_ID 帧可用，真实 motor id 是 `0x01`，UID 是数据域小端拼接。 |
| control layer | `CONTROL_CAN_USE_DIRECT_PDL=1` | RT-Thread CAN open/interrupt 链路复杂，bring-up 阶段先绕开。 |
| NanoPi | `0x321 -> 0x322` | NanoPi 到 M33 的 CAN 心跳成立后，才继续看 ROS。 |
| 电机 fresh | `0x180007FD` + `0x334 flags` | 有 M33 状态帧不代表有真实电机反馈。 |
| ROS/shadow | `/joint_states`、MuJoCo shadow、无 `0x320` | 上层只读链路必须和运动许可分开。 |

这就是 AI 调试的核心：每次只让一个假设暴露在实验下。实验通过，就把这一层收为事实；实验失败，就不要跳到下一层。

### 3.2 关键故障与决策

#### 设备名误判

现象：控制层找 `canfd0`，但 RT-Thread 注册名实际是 `can0`。

决策：以 RT-Thread device name 为准。底层外设叫 CANFD0，不代表应用层设备名也叫 `canfd0`。

迁移能力：任何 RTOS 外设调试，都要区分“芯片外设名、驱动对象名、RTOS device 名、业务配置名”。

#### 寄存器访问卡死

现象：`cmd_can_reg_probe` 卡在读 `CTL` 前后。

根因：M33 non-secure 侧访问 HSIOM/GPIO/CANFD0 前，相关 MMIO slave 没初始化。

代码动作：补 `Cy_SysClk_PeriGroupSlaveInit(...)`，再手配 PCLK 和 P16.0/P16.1。

学习点：寄存器读不动时，先查访问权限、时钟、总线域、TrustZone/secure 配置，不要急着查协议。

#### CANFD 外设与 Classic CAN 帧混淆

现象：电机不支持 CAN FD。

决策：即使用的是 CANFD0 外设，也强制发 Classic CAN：`brs=false`，`fdf=CY_CANFD_FDF_STANDARD_FRAME`。

学习点：外设能力是上限，不是当前协议格式。和第三方设备通信时，必须按对方支持的最小共同协议来。

#### RT-Thread CAN 路径卡住

现象：`rt_device_open(can0)`、interrupt/rx/tx indicate 路径让 `cmd_control_init` 卡住。

决策：先把已验证的 PDL 收发封装成：

```c
rt_err_t ifx_can_direct_init(void);
rt_err_t ifx_can_direct_send(const struct rt_can_msg *msg);
rt_ssize_t ifx_can_direct_recv(struct rt_can_msg *msg);
```

并在 control layer 用 `CONTROL_CAN_USE_DIRECT_PDL=1` 直接走 PDL polling。

学习点：bring-up 阶段优先获得可观测、可收敛的业务链路。标准驱动路径可以后续单独修，不要和电机联调混成一个大问题。

#### 广播探测被误读成两个电机

现象：`motor=0x01` 和 `motor=0x7F` 同一个 UID 反复刷屏。

根因：`0x7F` 是广播探测，不是真实电机 ID。

代码动作：加入 `s_motor_probe_pending` 和 `s_motor_probe_expected_id`，只接受当前 probe 期待的回包。

学习点：协议里的“请求目标 ID”和“设备真实 ID”要分开。广播、主站 ID、回复标记都不能混成 motor id。

#### host 查询造成 false fresh

现象：NanoPi 发 CANSimple `get-error` 后，M33 聚合状态短暂像 motor3 fresh。

根因：旧逻辑在进入 CANSimple 解析后太早刷新 timestamp，主机查询帧也被当成电机反馈。

代码动作：只有真实 feedback 内容有效时才刷新 `s_motor_feedback[]` timestamp。

学习点：fresh 不是“总线上有这个 node 的帧”，fresh 必须来自设备上报或明确可证明的反馈帧。

#### 有 M33 状态帧不等于有真实关节状态

现象：`0x330~0x334` 可见，但 `/joint_states` 没有。

根因：M33 周期状态帧只说明发布线程在线；如果 flags bit4 stale，位置/速度不能当真实姿态。

代码动作：M33 周期发布所有配置槽位；stale 时位置/速度填 0、温度 `0xFF`、flags bit4 置位。NanoPi 解析 stale 到 `/rehab_arm/motor_state`，但不发布 `/joint_states`。

学习点：诊断状态和控制状态要分开。没有 fresh 数据时保持可观测，但不能伪造可控制状态。

#### ROS joint id 与厂家 motor id 混淆

现象：`0x320` 发出，电机不动，或者 motor7 通过 `joint=7` 不生效。

根因：`0x320` 里的 joint id 是 ROS 关节号，不是厂家电机 ID。正式映射是 ROS joint `0..4` -> M33 motor slot `3/4/5/6/7`。

代码动作：配置 `CONTROL_ROS_JOINTx_MOTOR_JOINT`，M33 遥测按 ROS slot 发布 `0x330..0x334`。

学习点：系统里至少有三种 ID：ROS joint、M33 slot、厂家 motor/node id。调试文档和代码都要明说。

#### no-ACK / TX pending 不能靠软件幻想修复

现象：M33 日志出现 `direct tx pending ... txbto=0`，NanoPi `candump` 无 RX，TX errors 高。

判断：M33/M55 IPC 和模型能跑，不代表 CAN 总线 ACK 正常。TX buffer 长时间 pending 且没有 `txbto`，优先查 CANH/CANL、共地、终端电阻、收发器 EN/STBY、电源和同一物理总线。

学习点：当物理层证据显示 no-ACK 时，停止改 ROS、MuJoCo、TFLM。先恢复 `0x321 -> 0x322` 和 `0x330~0x334`。

#### `limit_cur` 不是电流命令

现象：写 `limit_cur(0x7018)=3.0A` 后，电源电流仍约 `0.1A`。

结论：`limit_cur` 是上限，不是强制输出电流。真实 current mode 需要正确 `run_mode` 和 `iq_ref(0x7006)`；MIT torque feedforward 也不能直接等同厂家 current mode。

学习点：变量名可能误导。凡是“电流、力矩、限幅”相关，都要回到厂家协议定义和实测反馈，不要只看字段名。

## 4. 代码编写复盘

### 4.1 做得好的地方

#### 用最小实验台守住底层事实

`applications/m33/can_driver.c` 里的 `cmd_can_reg_probe`、`cmd_can_init_min`、`cmd_can_send_probe`、`cmd_can_poll_once` 是非常关键的调试资产。

它们的价值不是“功能完整”，而是足够小：

- 不依赖 control layer。
- 不依赖 RT-Thread CAN open/interrupt。
- 能直接暴露 PCLK、NBTP、PSR、TXBRP、TXBTO、RXF0S。
- 后续任何 CAN 异常都能先用它们切分底层和上层。

#### control layer 统一 CAN 出口

所有业务发送最终汇入 `ctrl_can_send()`，底层再根据 `CONTROL_CAN_USE_DIRECT_PDL` 走 direct PDL 或 RT-Thread device。

这让后续 heartbeat、motor status、model status、ROS command、sensor command 都能共享一个出口，也方便补 TX pending 日志。

#### 用配置文件表达真实世界

`applications/control/control_layer_cfg.h` 里把 motor count、motor id、协议类型、型号、gear ratio、calibrated、direction、zero offset、ROS joint map、安全门、状态 ID 都集中配置。

这比把魔法数字散在函数里强得多。调试时可以直接对照：

- motor slot `3` 是 CANSimple/Sitaiwei。
- motor slot `4/5` 是 Lingzu RS00。
- motor slot `6/7` 是 Lingzu EL05。
- ROS joint `0..4` 映射到 motor slot `3/4/5/6/7`。
- `0x320/0x321/0x322/0x323/0x330` 各有明确语义。

#### stale/fresh 语义让系统可观察又 fail-closed

历史上最大的进步之一，是把“没有真实反馈”做成显式状态，而不是沉默。

M33 继续周期发状态帧，让 NanoPi 知道 M33 在线；但 stale bit 告诉上层不能发布 `/joint_states`、不能以该位置作为轨迹起点。这是工程上很好的 fail-closed 设计。

#### 安全门写进代码和文档

代码里有 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE`、`CONTROL_CLINICAL_MOTION_ENABLE`、`CONTROL_ROS_COMMAND_LOGGING_ONLY`、`CONTROL_CALIBRATION_ACTIVE_REPORT_ENABLE`。

文档里也反复强调：

- NanoPi 直发 CAN 只用于台架调试。
- 正式运动主线是 `JointTrajectory -> NanoPi -> M33 -> 电机`。
- M55、VLA、MuJoCo、App BLE 只能给建议、状态、shadow 或 dry-run，不能绕过 M33 授权运动。

这类“权力边界”比单个函数更重要。没有边界，后续 AI 或人很容易把 demo 改成主线。

### 4.2 仍有风险的地方

#### direct PDL 是 bring-up 策略，不应永久替代驱动完善

direct PDL 让电机链路先跑起来，这是正确阶段策略。但中长期仍应单独修 RT-Thread CAN device 路径，重点查：

- `rt_device_open()`。
- 中断 mask 与 NVIC。
- `rt_hw_can_isr()`。
- rx/tx event。
- FIFO ACK 语义。

建议单独建任务修，不要和电机业务联调混在一起。

#### `control_layer.c` 已经过大

当前 control layer 承担了协议编码、反馈解析、安全审核、状态发布、shell 命令、传感器路由、M55 结果发布等职责。短期能跑，长期容易变成难维护的大文件。

建议后续按边界拆：

- `motor_private_protocol.c`
- `motor_cansimple_protocol.c`
- `m33_ros_command.c`
- `m33_safety_gate.c`
- `m33_motor_status.c`
- `m33_can_router.c`

先不要为了“看起来架构好”乱拆。等有测试和明确接口后再拆。

#### bench motion 默认值要现场再确认

当前 M33 分支里 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE` 是 `1U`。这适合台架，但不适合穿戴或无人值守。

每次上电前要确认：

- 是否处在台架。
- 是否有人在机械范围内。
- `0x320` 是否会被发送。
- 是否有 fresh feedback。
- 是否有 M33 `motion_allowed` 或 bench-only 的明确状态。

#### 协议常量需要继续变成测试

历史上多次问题来自 ID、单位、比例和 fresh 判断。建议把这些变成 host-side 单元测试或离线 candump 报告测试：

- `0x320` payload 解析。
- ROS joint -> motor slot 映射。
- RobStride Get_ID 解析。
- CANSimple feedback vs host query 区分。
- stale bit 对 `/joint_states` 的过滤。
- CSP `run_mode/limit_spd/loc_ref` 序列。
- no unexpected `0x320` in readonly mode。

## 5. AI 是怎么“学习”的

这里的“学习”不是模型权重被现场训练了，而是上下文学习和证据学习：

1. 读历史：先看 Git log、文档、代码、测试记录，建立时间线。
2. 抽象层次：把现象拆成物理层、驱动层、协议层、控制层、ROS 层、安全层。
3. 找最小证据：每一层都找一条能证明/证伪的命令或日志。
4. 更新假设：证据通过就固定为事实，失败就缩小到当前层。
5. 写代码只服务于下一个证据：新增命令、日志、状态位、解析器、闸门。
6. 把教训写进合同：文档、配置、测试、状态码，防止下一轮又忘。

把它翻译成人的能力，就是一句话：

**不要靠聪明猜问题，靠证据缩小问题。**

## 6. 你可以怎么把它变成自己的能力

### 6.1 每次调试先画三张图

第一张：物理连接图。

```text
NanoPi MCP2518FD -- CANH/CANL -- M33 CANFD0 -- motor/transceiver
```

第二张：协议 ID 图。

```text
0x320 NanoPi -> M33 command
0x321 NanoPi -> M33 heartbeat
0x322 M33 -> NanoPi status
0x330~0x334 M33 -> NanoPi motor slots
0x180007FD motor7 -> bus active-report
```

第三张：权限图。

```text
M55 / App / VLA / MuJoCo: suggestion, status, shadow
NanoPi: bridge and readiness
M33: final safety authority
Motor: only accepts M33-approved formal path, except explicit bench debug
```

### 6.2 每次只问一个问题

不好的问法：

```text
为什么电机不动？
```

好的问法：

```text
M33 现在能不能发出一帧并被总线 ACK？
NanoPi 能不能看到 0x322？
motor7 有没有原始 0x180007FD？
0x334 的 stale bit 有没有清零？
0x320 的 joint id 是否映射到 motor slot 7？
```

问题越具体，下一步实验越清楚。

### 6.3 每个实验都写四行

```text
假设：如果 CAN 物理层在线，NanoPi 发 0x321 后应看到 M33 0x322。
操作：cansend can0 321#55；同时 candump can0,321:7FF,322:7FF。
期望：看到 0x321 TX 和 0x322 RX，can0 error counters 不增长。
解释：若没有 0x322 且 TX errors 增长，先查物理层，不查 ROS。
```

### 6.4 每次提交都回答三个问题

```text
这次改动缩小了哪个问题域？
新增了什么可观测证据？
它有没有改变运动权限或安全边界？
```

如果一个提交只改代码但没有可观测证据，调试价值通常不够。

### 6.5 遇到复杂系统时先做“负责任的保守”

本项目最好的习惯是：没有 fresh feedback，就不发布 `/joint_states`；只读服务必须没有 `0x320`；M55 模型结果必须是 suggestion-only。

这是嵌入式和机器人系统里非常重要的能力：你不是只追求“让它动”，而是追求“知道什么时候不该让它动”。

## 7. 下次继续调试的推荐顺序

1. 上电后先看 M33 串口是否出现 direct PDL 初始化日志。
2. NanoPi 看 `ip -details -statistics link show can0`，确认 1 Mbps、`ERROR-ACTIVE`、错误计数不增长。
3. 发 `0x321`，确认 `0x322`。
4. 抓 `0x330~0x334`，确认 M33 状态发布。
5. 开目标电机 active-report，只读确认原始反馈帧。
6. 看对应 `0x33x` stale bit 是否清零。
7. 确认 `/rehab_arm/motor_state` 有数据。
8. 只有 fresh 后才期待 `/joint_states`。
9. dry-run 确认没有意外 `0x320`。
10. 台架运动前，单独确认 joint id、motor id、方向、零点、限位、限速、急停和 stop 命令。

## 8. 证据索引

当前分支文件：

- `M33_CAN_交接文档_20260405.md`
- `M33_CAN_调试总结_20260411.md`
- `M33_电机控制打通计划_20260411.md`
- `docs/M33_CAN_NANOPI_BRINGUP_20260521.md`
- `applications/m33/can_driver.c`
- `applications/control/control_layer.c`
- `applications/control/control_layer_cfg.h`
- `libraries/HAL_Drivers/drv_can.c`
- `libraries/HAL_Drivers/CAN_config.h`

历史提交：

- `c8d85b93`
- `f57959e8`
- `837e76d9`
- `0742be49`
- `e5a38313`
- `78ea5999`
- `ce90173a`
- `a01d4d89`
- `51aedab5`
- `82fefa49`
- `f608aeef`
- `e701e3eb`
- `1e7ecb7b`
- `746e0ad4`
- `9d4d06f0`
- `b58ecaea`
- `eaea6ed8`
- `02da6525`
- `a3579560`
- `9f9aede5`
- `40320052`

跨分支证据：

- `origin/feature/rehab-arm-ros2-architecture:docs/PROJECT_PROGRESS.md`
- `origin/feature/rehab-arm-ros2-architecture:docs/TROUBLESHOOTING_AND_LESSONS.md`
- `origin/feature/rehab-arm-ros2-architecture:docs/MOTOR_PROTOCOLS.md`
- `origin/feature/rehab-arm-ros2-architecture:docs/PSOC_CAN_PROTOCOL_V1.md`
- `origin/feature/rehab-arm-ros2-architecture:docs/USER_MANUAL.md`

