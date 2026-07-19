# 边缘智能康复机械臂系统｜作品集项目页

> 这份文档用于放在简历作品集/飞书文档里。它不是项目交接文档，也不是论文式说明，而是从“我参与了什么、解决了什么问题、项目完整链路是什么”来介绍这个项目。

## 1. 项目简介

这是一个面向康复训练场景的边缘智能机械臂系统。项目目标是做一套可以采集患者训练数据、控制多关节电机、支持康复训练模式，并接入边缘 AI 小模型进行运动意图识别和训练辅助决策的系统。

系统整体不是单片机单独控制电机，而是一个多端协同的机器人系统：

- PSoC Edge E84 的 M33 核负责实时控制、安全判断、CAN 电机通信和传感数据汇总。
- STM32F103/C8T6 传感节点负责采集肌电、心率、血氧、IMU 等康复数据，并通过 CAN 上传。
- NanoPi 负责 SocketCAN、ROS2 bridge、状态聚合、上层轨迹接口和后续摄像头/服务器接入。
- Linux 工作站负责 ROS2、MuJoCo 仿真、hardware shadow、数据采集和调试可视化。
- M55/边缘 AI 侧负责接收 M33 提供的数据窗口，运行小模型，返回运动意图、疲劳或辅助建议等结果。

我在这个项目中主要做了三块：

- **通信**：CAN 总线、电机通信、STM32F103 传感报文、NanoPi SocketCAN/ROS2 桥接。
- **控制**：电机探测、参数读写、速度/位置/电流控制、康复训练模式解耦和实机调试。
- **模型**：康复训练数据采集、特征整理、模型训练、端侧部署和推理结果接入。

## 2. 项目整体架构

项目的真实运动主线是：

```text
JointTrajectory
    -> NanoPi ROS2 Bridge
    -> CAN 0x320
    -> M33 安全/控制层
    -> 电机驱动器
```

状态上行主线是：

```text
电机反馈 / STM32F103 传感数据
    -> CAN
    -> M33 汇总
    -> NanoPi ROS2
    -> /joint_states / motor_state / safety_state / model_state
    -> MuJoCo shadow / 数据采集 / 上层系统
```

边缘 AI 链路是：

```text
肌电 / 关节状态 / 电机反馈
    -> M33 数据快照
    -> M55 或端侧小模型
    -> 推理结果
    -> M33 / NanoPi 状态链路
    -> 康复训练策略辅助输入
```

项目里最重要的安全边界是：

```text
AI、App、服务器、MuJoCo、M55 都只能提供状态或建议；
真正是否让电机运动，最终必须由 M33 控制层判断。
```

这个边界也影响了我后面所有调试和代码设计：不能因为上层模型给出“需要助力”，就直接下发电机电流；也不能因为 ROS2 发来了轨迹，就绕过 M33 的限位、反馈新鲜度和安全状态。

## 3. 技术栈

### 嵌入式侧

- MCU：Infineon PSoC Edge E84，Cortex-M33 / Cortex-M55
- RTOS：RT-Thread
- 通信：CAN / CANFD 外设 classic CAN 模式、M33-M55 IPC、BLE NUS
- 电机协议：RobStride/灵足类私有扩展帧、CANSimple/ODrive 类标准帧
- 调试方式：RT-Thread FinSH/MSH、串口日志、CAN 抓包、OpenOCD/DAP 寄存器读写

### 上位机和机器人侧

- NanoPi：Linux、SocketCAN、MCP2518FD、systemd 自启动服务
- ROS2：`rclpy`、`JointTrajectory`、`JointState`、ROS2 launch
- 仿真：MuJoCo、hardware shadow、URDF/MJCF 关节映射
- 数据链路：JSON 状态消息、rosbag/JSONL 数据采集思路

### AI 模型侧

- 数据来源：肌电、心率、血氧、关节角度、电机位置/速度/力矩/温度等
- 模型目标：运动意图识别、训练状态识别、辅助等级建议
- 端侧部署：轻量模型部署、模型输入封装、推理结果解析、控制链路接入

## 4. 我负责和参与的工作

### 4.1 M33 侧 CAN 总线和电机通信

我主要负责把 M33 和电机驱动器之间的 CAN 通信链路打通。这部分一开始不是写完代码就能跑，而是遇到了很多硬件和协议层问题。

我实际做的调试过程大概是：

1. 先确认 M33 能访问 CANFD0 寄存器。
2. 再用 PDL 最小初始化、最小发送、最小轮询，绕开复杂上层驱动，确认硬件链路是否可用。
3. 确认电机不支持 CAN FD，所以虽然 MCU 外设叫 CANFD0，但实际必须发送 classic CAN 帧。
4. 调整到电机匹配的 1 Mbps 波特率。
5. 用 Get_ID 帧拿到电机回包，确认真实 motor id 和 UID。
6. 再把最小链路封装到 control layer 中，供电机控制和状态上报复用。

这部分解决过的问题包括：

- RT-Thread 注册设备名是 `can0`，不是外设名 `canfd0`。
- M33 non-secure 侧访问 CANFD0 前，需要初始化 HSIOM/GPIO/CANFD0 对应 MMIO slave。
- 电机不支持 CAN FD，需要强制 classic CAN，不能发送 FD frame。
- 广播 probe 会返回同一个 UID，容易误判成多个电机，需要做 expected id 过滤。
- RX FIFO 轮询要加 drain limit，避免异常状态下控制线程一直处理 CAN。
- TX pending 或 bus-off 时不能继续猜上层逻辑，要回到 CANH/CANL、共地、终端电阻、收发器和 ACK 证据。

这块我觉得最有收获的是：调电机不能只看 `ret=0`，必须看回包、寄存器状态、总线 ACK 和真实反馈。

### 4.2 电机控制和实机调试

在通信打通之后，我参与了电机控制功能的开发和实机验证，包括：

- 电机探测和 UID 解析。
- 电机使能、停止、故障清除。
- 参数读写，例如 `run_mode(0x7005)`、`limit_cur(0x7018)`、`spd_ref(0x700A)`。
- 速度控制、位置控制、电流控制。
- 电机反馈解析，包括位置、速度、力矩、温度、故障状态。
- 通过串口 shell 命令进行分阶段台架调试。

调试中有一个比较典型的问题：一开始用速度模式控制康复关节，命令返回成功，但是在真实肘关节负载下电机几乎不动。后来定位到 `limit_cur` 只是电流/力矩上限，不是实际输出电流。要让当前关节产生稳定助力，需要进入 current mode 并写 `iq_ref(0x7006)`。

所以后面我补了电流控制验证链路：

```text
设置 run_mode=current
写入 iq_ref(0x7006)
限制最大电流
用 cmd_motor_current_hold 做台架验证
```

这个经验后来也影响了康复训练模式的实现：主动、助力、抗阻这类模式不能简单地复用速度控制，否则在负载下效果不稳定。

### 4.3 STM32F103 传感节点接入

项目里还有一个 STM32F103/C8T6 传感节点，负责采集康复训练相关数据。我参与了 M33 侧对这些 CAN 报文的接入和解析。

传感节点主要通过 CAN 上传：

- 肌电 EMG 数据。
- 心率/血氧数据。
- 传感节点健康状态。
- ACK/控制响应。

我做的工作包括：

- 对齐 STM32F103 传感节点 CAN ID 和 payload 格式。
- 在 M33 侧缓存传感数据、健康状态和 ACK。
- 把传感数据接入康复训练和 AI 数据采集链路。
- 区分“收到节点报文”和“数据真正有效”，避免无效数据参与控制或训练。

这部分对后面的 AI 模型很重要，因为模型训练不能只靠单一电机反馈，还要结合患者训练过程中的肌电和生命体征数据。

### 4.4 康复训练模式解耦

康复训练不是简单写几个 `mode`。如果模式逻辑、底层电机 API、传感反馈和参数配置混在一起，后面很难继续扩展。

所以我参与把康复训练功能拆成几个层次：

- 模式管理：主动、助力、抗阻、记忆回放等模式切换。
- 策略计算：根据反馈计算当前应该输出的辅助或阻抗。
- 底层控制：调用电机速度、位置或电流控制接口。
- 状态反馈：输出当前模式、反馈是否 fresh、电流输出、是否达到限幅等状态。
- 调试入口：通过 shell 命令调整方向、增益、电流上限等参数。

其中主动/助力/抗阻模式后面改成以电流输出为主，因为电流模式更接近实际助力和阻抗控制需求。记忆回放仍然保留位置控制，因为它更像轨迹复现。

这块我比较重视几个边界：

- 没有 fresh 电机反馈，不继续输出训练电流。
- 输出电流必须受限流保护。
- `rehab stop` 和底层 `cmd_motor_stop` 必须能立即停止。
- 台架调试路径和正式穿戴控制路径要分开。
- AI 结果只能作为策略辅助输入，不能直接控制电机。

### 4.5 NanoPi / ROS2 桥接

除了 M33 固件，我也参与了 NanoPi 和 ROS2 这部分。NanoPi 在项目中不是普通上位机，而是连接机器人系统和嵌入式控制层的桥。

NanoPi 主要负责：

- 通过 SocketCAN 打开 `can0`。
- 向 M33 发送 heartbeat：`0x321`。
- 接收 M33 状态：`0x322`。
- 解析 M33 电机遥测：`0x330~0x337`。
- 解析 M33/M55 模型状态：`0x323`。
- 接收 ROS2 的 `/arm_controller/joint_trajectory`。
- 在安全条件满足时，把轨迹编码为 `0x320` 发给 M33。
- 发布 ROS2 状态 topic。

我参与和熟悉的 ROS2 话题包括：

```text
/arm_controller/joint_trajectory
/joint_states
/rehab_arm/safety_state
/rehab_arm/motor_state
/rehab_arm/model_state
/rehab_arm/sensor_state
```

其中 `psoc_can_bridge_node.py` 里有一个很关键的设计：默认 `enable_target_tx=false`。也就是说，bridge 可以读取状态、解析轨迹、打印 dry-run 日志，但默认不会真的发 `0x320` 运动目标。这对调试很重要，因为我们可以先验证 ROS2、CAN、状态解析、MuJoCo shadow 都通了，再决定是否进入真实运动测试。

我参与这部分时关注的重点是：

- ROS joint id、M33 motor slot、厂家 motor id 必须分清楚。
- 有 M33 状态帧不代表有 fresh 电机反馈。
- stale 数据不能发布成真实 `/joint_states`。
- `0x320` 是真实运动目标帧，普通只读服务不能意外发出。
- NanoPi direct CAN 调试脚本只能用于 bench-debug，不能作为正式控制路径。

### 4.6 MuJoCo hardware shadow 和 6DOF 映射

项目里还有 MuJoCo 仿真和 hardware shadow，用来把真实或占位关节状态映射到 6DOF 医疗机械臂模型里。

这一块的作用是：

- 在不直接驱动全部真机电机的情况下，先验证 ROS2 状态链路。
- 把 NanoPi 收到的 `/joint_states` 映射到 `/sim/medical_arm/joint_trajectory`。
- 在 MuJoCo 中显示 6 个 medical arm joint 的状态。
- 为后续轨迹规划、VLA dry-run、数据采集和可视化做准备。

项目中的 6DOF schema 包含这些关节：

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

当前部分电机还处于台架/占位状态，比如 7 号 EL05 是外部调试电机，不属于正式机械臂关节。作品集里我会如实写成“hardware shadow / bench-debug 验证”，不会写成完整 6DOF 真机闭环已经完成。

### 4.7 边缘 AI 小模型链路

AI 部分我主要做的是康复训练小模型链路，不是语音唤醒词。

这条链路包括：

```text
传感/电机数据采集
    -> 特征整理
    -> 模型训练
    -> 端侧部署
    -> 推理结果接入控制状态
```

模型输入主要来自：

- STM32F103 传感节点：肌电、心率、血氧等。
- M33 电机控制层：关节位置、速度、力矩、温度、故障等。
- 康复训练模式：当前训练模式、主动/助力/抗阻状态等上下文。

模型目标是识别训练中的状态，比如患者是否主动发力、是否需要助力、当前训练状态是否异常等。模型结果不会直接控制电机，而是作为康复策略的辅助输入。

我参与的工作包括：

- 打通训练数据采集链路。
- 整理康复训练样本和特征。
- 参与小模型训练。
- 将模型部署到边缘端。
- 将推理结果接入 M33/NanoPi 状态链路，用于后续策略判断和上层显示。

## 5. 项目调试中印象最深的几个问题

### 5.1 电机不回包，不一定是协议错

一开始电机不回包时，不能直接怀疑控制算法。实际排查下来，可能是：

- M33 还不能访问 CANFD0 寄存器。
- CANFD0 时钟或引脚没初始化。
- classic CAN / CAN FD 帧格式不匹配。
- 波特率不匹配。
- 物理层没有 ACK。
- 收发器、供电、共地、终端电阻有问题。

所以我后面习惯用分层方法排查：寄存器 -> 最小 CAN 收发 -> 电机 Get_ID -> control layer -> ROS2 -> MuJoCo。

### 5.2 `ret=0` 不等于电机真的产生了有效输出

速度控制命令返回成功，但实际负载下电机不动，这让我意识到嵌入式控制不能只看 API 返回值。必须结合电机反馈、电源电流、机械负载和协议语义判断。

最后通过 current mode 和 `iq_ref(0x7006)` 才把真实助力输出链路打通。

### 5.3 有状态帧不等于有真实关节状态

M33 可以周期发送 `0x330~0x334`，但如果里面标记 stale，就说明这个槽位没有 fresh 反馈。NanoPi 不能把 stale 数据发布成真实 `/joint_states`，否则上层仿真或规划会误以为关节状态可信。

这个问题后来变成系统里的一个规则：

```text
状态在线 != 反馈 fresh
反馈 fresh != 允许运动
AI 有结果 != 运动许可
```

### 5.4 ROS2/NanoPi 默认必须只读

`0x320` 是 NanoPi 发给 M33 的真实目标帧。只要它出现在总线上，就可能进入真实运动路径。所以 ROS2 bridge 默认 `enable_target_tx=false`，先做 dry-run 和状态验证。

这个设计让我们可以安全地验证：

- NanoPi 能否收到 M33 状态。
- `/joint_states` 是否正确。
- MuJoCo shadow 是否能跟随。
- 模型状态是否能发布到 `/rehab_arm/model_state`。

但不会误发真实运动命令。

## 6. 目前项目阶段

这个项目还在研发阶段，不能夸大成完整量产医疗设备。比较准确的阶段描述是：

已经完成或打通的部分：

- M33 与电机 CAN 通信链路。
- 电机探测、参数读写、速度/位置/电流控制调试。
- STM32F103 传感节点数据接入链路。
- 康复训练模式的模块化拆分。
- NanoPi SocketCAN/ROS2 bridge 的状态读取和 dry-run 轨迹链路。
- M33 状态、模型状态、电机状态到 ROS2 topic 的解析和发布。
- MuJoCo 6DOF hardware shadow 的基础链路。
- 康复数据采集、模型训练、端侧部署和推理结果接入闭环。

仍在继续完善的部分：

- 完整 6DOF 真机机械臂的所有关节标定。
- 每个关节的最终传动比、方向、零点、限位和回差。
- 正式穿戴场景下的完整安全验收。
- 真实多通道 EMG 数据下模型的长期验证。
- VLA/服务器与真机运动之间的安全审核闭环。

我会在作品集中如实写清楚这些边界，因为这反而更能体现这个项目是真实做过的，而不是包装出来的 demo。

## 7. 可以放在作品集首页的短版

**项目名称：边缘智能康复机械臂控制系统**

基于 PSoC Edge E84、RT-Thread、CAN 总线、STM32F103 传感节点、NanoPi ROS2 和边缘 AI 小模型，开发一套面向康复训练的机械臂控制系统。系统通过 CAN 总线接入多关节电机和传感单元，由 M33 负责实时控制和安全裁决，NanoPi 负责 ROS2/CAN 桥接和状态聚合，M55/边缘端负责小模型推理，Linux 工作站负责 MuJoCo shadow 和数据采集。

我主要负责 CAN 通信、电机控制、康复训练模式解耦、NanoPi/ROS2 状态链路和 AI 小模型部署链路。项目中完成了 M33 与电机驱动器的 classic CAN/1Mbps 通信、电机 Get_ID/UID 解析、参数读写、速度/位置/电流控制、STM32F103 传感数据接入、ROS2 `/joint_states` 与 `/rehab_arm/*` 状态发布、MuJoCo hardware shadow，以及康复数据采集、模型训练和端侧推理结果接入。

项目调试中重点解决了 CANFD0 外设初始化、classic CAN 适配、物理层 ACK、bus-off/TX pending、fresh/stale 反馈区分、`limit_cur` 与真实电流输出区别、`iq_ref(0x7006)` 电流控制、ROS2 dry-run 安全门等问题。

## 8. 简历项目经历版本

**边缘智能康复机械臂控制系统｜PSoC Edge E84 / RT-Thread / CAN / NanoPi ROS2 / 边缘 AI**

- 基于 PSoC Edge E84、RT-Thread、CAN 总线和 NanoPi ROS2 开发康复机械臂控制系统，参与 M33 实时控制、STM32F103 传感接入、NanoPi ROS2 bridge、MuJoCo shadow 和边缘 AI 小模型部署链路。
- 负责 M33 与电机驱动器的 CAN 通信调试，完成 CANFD0 底层初始化、classic CAN/1Mbps 适配、电机 Get_ID/UID 解析、参数读写和速度/位置/电流控制验证。
- 接入 STM32F103 传感节点 CAN 报文，采集肌电、心率、血氧、关节状态和电机反馈等数据，为康复训练控制和 AI 模型训练提供数据来源。
- 参与 NanoPi ROS2/CAN 桥接开发，围绕 `0x320/0x321/0x322/0x330~0x337` 完成状态解析、heartbeat、dry-run 轨迹链路和 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/motor_state` 等 topic 发布。
- 对康复训练功能进行模块化解耦，将底层电机控制、传感反馈、模式管理和策略输出拆分，支持主动、助力、抗阻、记忆回放等模式扩展。
- 实机调试中定位 `limit_cur` 与实际电流输出的区别，通过 current mode 和 `iq_ref(0x7006)` 打通电流控制链路，用于康复助力/抗阻模式。
- 打通边缘 AI 小模型闭环，完成康复数据采集、特征整理、模型训练、端侧部署和推理结果接入，用于运动意图识别和训练辅助决策。
- 增加 probe 回包过滤、CAN RX 轮询限制、bus-off/TX pending 诊断、fresh/stale 反馈区分、ROS2 `enable_target_tx=false` dry-run 安全门和故障停止逻辑，提高实机调试和控制链路鲁棒性。

## 9. 面试时可以展开讲的点

如果面试官问这个项目，可以按这条线讲：

1. 先讲系统：M33 做实时控制，NanoPi 做 ROS2 bridge，STM32F103 做传感，M55/模型做建议，MuJoCo 做 shadow。
2. 再讲通信：CANFD0 外设、classic CAN、1Mbps、Get_ID、SocketCAN、`0x320/0x321/0x322`。
3. 再讲控制：参数读写、速度/位置/电流模式、`limit_cur` 和 `iq_ref(0x7006)`。
4. 再讲 ROS：`JointTrajectory`、`/joint_states`、dry-run、fresh/stale、MuJoCo hardware shadow。
5. 最后讲 AI：传感和电机数据采集、特征、训练、端侧部署，结果只做辅助建议。

这条线比较自然，也能体现你不是只做了某一个函数，而是参与了从底层硬件通信到上层 ROS2/AI 链路的完整系统。
