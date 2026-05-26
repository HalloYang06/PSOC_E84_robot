# Motor Protocols And Current Mapping

本文档记录当前已经确认的电机 ID、厂家协议、数据帧和安全边界。它用于 ROS/NanoPi/M33/平台数据采集对齐，不等于最终临床安全参数。

## 1. 安全边界

- 正式运动链路只能是 `JointTrajectory -> NanoPi -> M33 -> 电机`。
- M33 是唯一电机执行和安全裁决主站，负责限位、限速、急停、heartbeat timeout、故障降级和电机输出许可。
- NanoPi 直接 CANSimple 或灵足私有帧只允许用于台架调试、离线抓包和数据接收验证。
- 平台、服务器、VLA、App、M55 和 OpenClaw 都不能直接发电机 CAN 命令。
- 当前所有厂家协议量程都必须在 M33 侧再次检查；ROS/NanoPi 的检查只是前置防呆。

## 2. 当前实测电机映射

| 逻辑对象 | 真实 ID | 厂家 | 协议 | 已确认帧 | 当前用途 |
|---|---:|---|---|---|---|
| motor 3 | `node_id=3` | 伺泰威 / Sitaiwei | CANSimple/ODrive 类标准帧 | heartbeat `0x061`，encoder estimate `0x069` | 减速比 `48:1`；命令已发过，但现场尚未看到真实运动 |
| motor 4 | `motor_id=4` | 灵足 / Lingzu RobStride RS00 | 私有扩展帧 | active-report `0x180004FD` | 官方减速比 `10:1`，原始遥测已确认 |
| motor 5 | `motor_id=5` | 灵足 / Lingzu RobStride RS00 | 私有扩展帧 | active-report `0x180005FD` | 官方减速比 `10:1`，原始遥测已确认 |
| motor 6 | `motor_id=6` | 灵足 / Lingzu EduLite EL05 | 私有扩展帧 | active-report `0x180006FD` | 官方减速比 `9:1`，原始遥测已确认 |
| motor 7 | `motor_id=7` | 灵足 / Lingzu EduLite EL05 | 私有扩展帧 | active-report `0x180007FD` | 官方减速比 `9:1`，原始遥测已确认 |

待确认项：

- 真实机械关节绑定关系。
- 每个关节的最终软限位、速度限制、力矩/电流限制、抱闸/急停联锁。
- 伺泰威/肩关节协议的完整字节级控制流程还需要继续从本地离线 HTML 中提取。

## 3. 伺泰威 / 肩关节驱动资料基线

本地资料来源：

- `D:\电机上位机\肩关节电机资料\MW6010-8_驱动产品手册_飞书离线页.html`
- `D:\电机上位机\肩关节电机资料\肩关节电机_用户手册_飞书离线页.html`
- `D:\电机上位机\肩关节电机资料\守护兽驱动协议手册_飞书离线页.html`
- `D:\电机上位机\肩关节电机资料\肩关节电机_学习整理.md`
- `D:\RT-ThreadStudio\workspace\yiliao_m33\docs\ai-handoffs\motor3-cansimple.md`

在线飞书链接当前会跳转登录页，但本地已有离线页副本。后续优先读本地离线页，不依赖在线链接。

产品手册确认到的硬件接口范围：

- 电源及 CAN 通信端子。
- 第二编码器接口。
- Type-C 调试接口。
- SWD 调试接口。
- 限位开关接口。
- 电机温度接口。
- 抱闸/刹车电阻接口。
- 接口扩展插槽。

用户手册确认到的软件/开发入口：

- 电机精灵、固件升级、查看错误码。
- 驱动参数、电机参数、周期消息。
- 波特率变更、切换通信协议、获取详细错误信息。
- 用户自设零点、PID 和不同控制模式调参。
- MIT 控制、CANOpen、PWM 输入控制、Modbus。
- Python SDK、C/C++ SDK、ROS SDK、Arduino SDK、odrivetool。

协议手册确认到的协议结构：

- CAN Simple 协议。
- CAN 协议实战。
- CANOpen 协议实战。
- 协议帧格式、帧消息、PDO、NMT 心跳、紧急报文、主站监控机制。
- 对象词典与电机参数对应表、故障码一览表。
- CANOpen 控制字 `6040h`、状态字 `6041h`。

## 4. 伺泰威 CANSimple 遥测

当前实测：

| CAN ID | 含义 | 解码 |
|---|---|---|
| `0x061` | `node_id=3` heartbeat | `node_id = can_id >> 5`，`cmd_id = can_id & 0x1F = 0x01` |
| `0x069` | `node_id=3` encoder estimate | `cmd_id = 0x09`，payload 为 little-endian `float32 position_turns, float32 velocity_turns_per_sec` |

NanoPi 离线转换：

- `position = position_turns * 2*pi`
- `velocity = velocity_turns_per_sec * 2*pi`
- heartbeat 会补充 `enabled/fault/axis_state/error_code`。
- heartbeat 的 byte5/byte6/byte7 当前只保留为 `heartbeat_byte5/6/7` raw 字段，并标记 `heartbeat_extension_decode=raw_only_vendor_fields_unconfirmed`。

协议页已确认的 CANSimple 帧格式：

| 字段 | 规则 |
|---|---|
| CAN ID | 标准 11-bit ID |
| ID 分段 | `Bit10~Bit5 = node_id`，`Bit4~Bit0 = cmd_id` |
| ID 计算 | `can_id = (node_id << 5) + cmd_id` |
| Data | classic CAN，最多 8 bytes；很多命令为 8 bytes，部分命令本地 M33 实现使用较短 DLC |
| 字节序 | 小端 `little-endian` |
| 浮点 | IEEE754 `float32` |

本地协议页给出的 `Set_Input_Pos` 示例：

| 项 | 值 |
|---|---|
| `node_id` | `0x05` |
| `cmd_id` | `0x0C` |
| CAN ID | `(0x05 << 5) + 0x0C = 0x0AC` |
| `Input_Pos` | `float32 3.14` -> bytes `C3 F5 48 40` |
| `Vel_FF` | `1000` -> bytes `E8 03` |
| `Torque_FF` | `5000` -> bytes `88 13` |
| Data bytes | `C3 F5 48 40 E8 03 88 13` |

注意：

- CANSimple 直接命令不进入正式 launch。
- 本地离线协议页已确认 CANSimple standard 11-bit CAN、classic data frame 方向与当前实现一致。
- byte0..3 axis error 与 byte4 axis state 已在 M33/NanoPi 离线转换中使用。
- byte5..7 在本地 M33 中曾用于 `flags/temp/life` 调试打印，但与离线协议表参数名还未完全对齐，正式数据集只能 raw-first 保留，不能直接当成可靠温度或安全位。
- 波特率、控制模式、错误位和限幅字段仍需继续从离线页逐项提取，并在 M33 侧二次验证。

当前本地 M33 / NanoPi 调试工具对 CANSimple 控制帧的 payload 布局如下。正式机器人路径不直接使用这些帧；它们用于 M33 固件内部厂家协议输出、离线核对和台架调试。

| 命令 | CAN ID 计算 | Payload | 单位/缩放 | 安全备注 |
|---|---|---|---|---|
| `0x07 Set_Axis_State` | `(node_id << 5) + 0x07` | byte0..3 `uint32 axis_state` | 小端；`1=idle`，`8=closed_loop` | 进入 closed-loop 前必须确认 heartbeat、fault、限位、急停、供电 |
| `0x0B Set_Controller_Mode` | `(node_id << 5) + 0x0B` | byte0..3 `uint32 control_mode`，byte4..7 `uint32 input_mode` | 小端；本地常量 `1=torque`、`2=velocity`、`3=position`，`input_mode=1 passthrough`、`2 vel_ramp` | 模式切换只能由 M33 安全状态机触发 |
| `0x0C Set_Input_Pos` | `(node_id << 5) + 0x0C` | byte0..3 `float32 pos_rev`，byte4..5 `int16 vel_ff_scaled`，byte6..7 `int16 torque_ff_scaled` | `pos_rev = pos_rad / 2*pi`；本地 `vel_ff_scaled = vel_rev_s * 1000`，`torque_ff_scaled = torque_nm * 1000` | 必须先过 joint limit、速度/力矩前置限制和轨迹连续性检查 |
| `0x0D Set_Input_Vel` | `(node_id << 5) + 0x0D` | byte0..3 `float32 vel_rev_s`，byte4..7 `float32 torque_ff_nm` | `vel_rev_s = vel_rad_s / 2*pi` | 只允许低速、受限、可停止的台架调试；正式路径由 M33 限速 |
| `0x0E Set_Input_Torque` | `(node_id << 5) + 0x0E` | byte0..3 `float32 torque_nm` | 本地 M33 发送 DLC=4；NanoPi 调试脚本也发 4 字节 | 人体穿戴场景默认禁用直接力矩，除非 M33 安全状态机明确允许 |
| `0x0F Set_Limits` | `(node_id << 5) + 0x0F` | byte0..3 `float32 vel_limit_rev_s`，byte4..7 `float32 current_or_torque_limit` | M33 当前变量名为 `limit_cur`，真实含义需结合厂家配置再确认 | 必须作为 M33 内部二次保护，不可替代机械/软件限位 |
| `0x18 Clear_Errors` | `(node_id << 5) + 0x18` | 通常 8 字节全 0 | - | 只允许在确认急停/故障原因后执行，不能自动反复清错 |

M33 当前换算常量来源：

- `CONTROL_CANSIMPLE_POS_REV_PER_RAD = 0.15915494309189535`
- `CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S = 0.15915494309189535`
- `CONTROL_CANSIMPLE_VEL_FF_SCALE = 1000`
- `CONTROL_CANSIMPLE_TORQUE_FF_SCALE = 1000`

当前已从协议手册表格/目录确认的 CANSimple 命令包括：

| Command | 名称 | 方向 | 参数/说明 |
|---:|---|---|---|
| `0x01` | `Heartbeat` | 电机 -> 主机 | `Axis_Error`、`Axis_State`、`Motor_Flag`、`Encoder_Flag`、`Controller_Flag`、`Traj_Done`、`Life` |
| `0x02` | `Estop` | 主机 -> 电机 | 紧急停止 |
| `0x03` | `Get_Error` | 电机 -> 主机 | `Error_Type` |
| `0x04` | `RxSdo` | 电机 -> 主机 | 访问可访问参数 |
| `0x05` | `TxSdo` | 电机 -> 主机 | 待细化 |
| `0x06` | `Set_Axis_Node_ID` | 主机 -> 电机 | `Axis_Node_ID` |
| `0x07` | `Set_Axis_State` | 主机 -> 电机 | `Axis_Requested_State` |
| `0x08` | `Mit_Control` | 双向 | MIT 控制 |
| `0x09` | `Get_Encoder_Estimates` | 电机 -> 主机 | `Pos_Estimate`、`Vel_Estimate` |
| `0x0A` | `Get_Encoder_Count` | 电机 -> 主机 | `Shadow_Count`、`Count_In_Cpr` |
| `0x0B` | `Set_Controller_Mode` | 主机 -> 电机 | `Control_Mode`、`Input_Mode` |
| `0x0C` | `Set_Input_Pos` | 主机 -> 电机 | `Input_Pos`、`Vel_FF`、`Torque_FF` |
| `0x0D` | `Set_Input_Vel` | 主机 -> 电机 | 设定输入速度，字节布局待补 |
| `0x0E` | `Set_Input_Torque` | 主机 -> 电机 | 设定输入力矩，字节布局待补 |
| `0x0F` | `Set_Limits` | 主机 -> 电机 | 限幅，字节布局待补 |
| `0x10` | `Start_Anticogging` | 主机 -> 电机 | 抗齿槽校准，正式路径默认禁用 |
| `0x11` | `Set_Traj_Vel_Limit` | 主机 -> 电机 | 轨迹速度限制 |
| `0x12` | `Set_Traj_Accel_Limits` | 主机 -> 电机 | 轨迹加速度限制 |
| `0x13` | `Set_Traj_Inertia` | 主机 -> 电机 | 轨迹惯量 |
| `0x14` | `Get_Iq` | 电机 -> 主机 | Q 轴电流 |
| `0x15` | `Get_Thermistor_Temperature` | 电机 -> 主机 | 温度 |
| `0x16` | `Reboot` | 主机 -> 电机 | 重启，正式路径禁用 |
| `0x17` | `Get_Bus_Voltage_Current` | 电机 -> 主机 | 母线电压/电流 |
| `0x18` | `Clear_Errors` | 主机 -> 电机 | 清除异常，仅允许在安全流程中使用 |
| `0x19` | `Set_Move_Incremental` | 主机 -> 电机 | 增量移动，正式路径默认禁用 |
| `0x1A` | `Set_Pos_Gain` | 主机 -> 电机 | 位置增益 |
| `0x1B` | `Set_Vel_Gains` | 主机 -> 电机 | 速度增益 |
| `0x1C` | `Get_Torques` | 电机 -> 主机 | 力矩 |
| `0x1D` | `Get_Powers` | 电机 -> 主机 | 功率 |
| `0x1E` | `Disable_Can` | 主机 -> 电机 | 关闭 CAN，正式路径禁用 |
| `0x1F` | `Save_Configuration` | 主机 -> 电机 | 保存配置，正式路径禁用 |

当前已从协议手册目录/标题确认的状态/参数项包括：

| 项 | 名称 |
|---:|---|
| `0x61` | 紧急停止 |
| `0x62` | 节点 ID |
| `0x66/0x67` | 位置控制目标 |
| `0x68/0x69` | 速度控制目标 |
| `0x6A/0x6B` | 力矩控制目标 |
| `0x6C/0x6D` | 速度限制 |
| `0x74/0x75` | 梯形位置控制减速度限制 |
| `0x78/0x79` | 位置增益 |
| `0x7C/0x7D` | 速度积分增益 |
| `0x7F` | 清除异常 |
| `0x80` | 存储配置 |
| `0xA1` | 随机端点访问端点号 |
| `0xA2/0xA3` | 随机端点访问写入值 |

## 5. 灵足 RobStride 私有扩展帧遥测

本地资料来源：

- `D:\电机上位机\robstride_ros_sample\include\motor_ros2\motor_cfg.h`
- `D:\电机上位机\robstride_ros_sample\src\motor_cfg.cpp`
- `D:\电机上位机\SampleProgram\RS\Robstride01.cpp`
- `D:\电机上位机\RobStride_学习整理.md`
- `D:\电机上位机\Product_Information\灵足时代产品规格介绍 RobStride Product Specification Document 20250626.pdf`
- `D:\电机上位机\Product_Information\产品资料\RS00\RS00使用说明书260112.pdf`
- `D:\电机上位机\Product_Information\产品资料\EL05\EL05使用说明书260112.pdf`

当前已确认型号：

| motor ID | 型号 | 官方减速比 | 官方资料依据 | 当前备注 |
|---:|---|---:|---|---|
| 4 | RS00 | `10:1` | RS00 使用说明书机械特性、RobStride 产品规格书 | 灵足私有扩展帧 |
| 5 | RS00 | `10:1` | RS00 使用说明书机械特性、RobStride 产品规格书 | 灵足私有扩展帧 |
| 6 | EL05 | `9:1` | EL05 使用说明书机械特性 | 灵足私有扩展帧 |
| 7 | EL05 | `9:1` | EL05 使用说明书机械特性 | 灵足私有扩展帧 |

关键通信类型：

| 类型 | 含义 |
|---:|---|
| `0x00` | Get ID |
| `0x01` | 运控命令 |
| `0x02` | 电机状态反馈 |
| `0x03` | 使能 |
| `0x04` | 停机 |
| `0x06` | 设置机械零位 |
| `0x11` | 读取单参数 |
| `0x12` | 写单参数 / 控制模式 |
| `0x15` | 故障反馈 |
| `0x18` | 主动上报 |

实测 active-report ID：

```text
0x180004FD
0x180005FD
0x180006FD
0x180007FD
```

当前解释：

- 高 5 bit 通信类型为 `0x18`，表示主动上报。
- byte 8 低位 `0xFD` 是当前主机 ID。
- `can_id >> 8 & 0xFF` 是 motor ID。
- payload 按本地示例保留：
  - `data[0..1]`: big-endian `raw_position_u16`
  - `data[2..3]`: big-endian `raw_velocity_u16`
  - `data[4..5]`: big-endian `raw_torque_u16`
  - `data[6..7]`: big-endian `raw_temperature_u16`

工程单位换算：

- 本仓库默认不对 4/5/6/7 输出工程单位，因为真实型号还没确认。
- 如果某个 motor ID 的型号确认，可按本地 `robstride_ros_sample` 的型号量程解码：

```text
value = ((raw / 32767.0) - 1.0) * limit
temperature_c = raw_temperature_u16 * 0.1
```

本地示例量程：

| 型号 | position limit rad | velocity limit rad/s | torque limit Nm |
|---|---:|---:|---:|
| RS00 | `4*pi` | 50 | 17 |
| RS01 | `4*pi` | 44 | 17 |
| RS02 | `4*pi` | 44 | 17 |
| RS03 | `4*pi` | 50 | 60 |
| RS04 | `4*pi` | 15 | 120 |
| RS05 | `4*pi` | 33 | 17 |
| RS06 | `4*pi` | 20 | 36 |

注意：

- `robstride_ros_sample` 当前没有单独 `EL05` 枚举；EL05 的反馈量程和控制量程不能直接套 RS00/RS05/RS06，需要继续从 EL05 用户手册或厂家样例补齐。
- 7号 `5 rpm / 3s` 实测约 `150°`，说明当前调试脚本的速度命令、反馈位置字段和真实输出轴之间仍存在未标定环节；不能只靠减速比解释或替代实测标定。
- 主动上报要在测试结束后关闭，避免总线长期高频刷帧。
- 正式路径应由 M33 读取/聚合电机状态，再发给 NanoPi 发布 `/rehab_arm/motor_state`。

## 6. M33 -> NanoPi 正式电机遥测草案

本节是固件待实现的第一版草案，当前 NanoPi 侧已经有离线 parser 和单元测试；M33 还没有按该格式正式上报。它的目的不是控制电机，而是让 NanoPi、仿真主机、平台和数据标注统一读取“经过 M33 安全边界汇总后的电机状态”。

CAN ID 预留：

| CAN ID | 方向 | 帧类型 | 用途 |
|---|---|---|---|
| `0x330` ~ `0x337` | M33 -> NanoPi | classic CAN standard 11-bit | 每个关节/电机状态一帧 |

Payload V1，8 bytes：

| Byte | 字段 | 类型 | 单位/说明 |
|---:|---|---|---|
| 0 | `marker` | `uint8` | 固定 `0xB3` |
| 1 | `seq` | `uint8` | M33 状态序号，0-255 循环 |
| 2 | `motor_id` | `uint8` | 当前实测 `3/4/5/6/7` |
| 3 | `flags` | `uint8` | bit0 enabled, bit1 fault, bit2 limited, bit3 emergency_stop |
| 4..5 | `position_mrad` | `int16 little-endian` | 关节位置，单位 mrad |
| 6 | `velocity_drad_s` | `int8` | 关节速度，单位 0.1 rad/s |
| 7 | `temperature_c` | `uint8` | 温度摄氏度；`0xFF` 表示未知 |

NanoPi parser 输出：

- `protocol=m33_motor_status_v1`
- `protocol_status=proposed_firmware_pending`
- `position = position_mrad / 1000.0`
- `velocity = velocity_drad_s / 10.0`
- `temperature = null` when `temperature_c == 0xFF`
- 只把 `marker == 0xB3` 且长度正确的帧放入 `/rehab_arm/motor_state`
- `control_boundary=telemetry_only_not_motor_command`

注意：

- 这组帧只表达遥测，不表达运动许可。运动许可仍以 M33 安全状态机和 `0x322` 为准。
- 这些帧从 M33 发出后，NanoPi 可以把它们映射成 `/joint_states` 和 `/rehab_arm/motor_state`，用于 MuJoCo/RViz 状态同步、数据采集、平台展示和标注。
- 如果未来关节数量超过 8 个，或需要电流/电压/力矩高精度字段，应新增 V2 多帧或 CAN FD 设计，不要破坏 V1 字段含义。

## 7. M33 正式数据流预编辑

M33 输入：

- NanoPi `0x321` heartbeat。
- NanoPi `0x320` 关节目标/轨迹片段请求。
- C8T6 传感和健康帧。
- 电机反馈、故障、温度、电流/力矩、编码器状态。
- M55 小模型结果：意图、疲劳、辅助等级、异常建议。
- 硬件急停、限位、供电/温度/抱闸反馈。

M33 输出：

- `0x322` safety/status 给 NanoPi。
- 聚合后的电机/传感/安全状态给 NanoPi 和 App BLE。
- 安全裁决后的电机厂家协议命令。
- 给 M55 的传感、电机和训练上下文。

M33 safety state machine 最小状态：

```text
BOOT -> SELF_TEST -> STANDBY -> READY -> ACTIVE
任意状态 -> LIMITED / SAFE_HOLD / FAULT / EMERGENCY_STOP
```

当前最近 M33 工程 `D:\RT-ThreadStudio\workspace\yiliao_m33` 已有：

- `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`
- `0x320` 解析与 logging-only 拒绝。
- heartbeat timeout 检查。
- joint/position/speed/torque 初步审核。
- `0x322` V2 detail code 回传。

下一步不要直接打开真实执行层。应先完成：

1. 确认 4/5/6/7 型号和关节绑定。
2. 把 7 轴最终限位、速度、扭矩/电流、急停、抱闸和供电规则填入 M33 配置。
3. 让 M33 汇总所有电机状态并转成 NanoPi 可解析的状态帧或 ROS bridge 数据。
4. 在电机断开或空载条件下验证拒绝用例。
5. 再进入低能量受限动作。

M33 后续允许 `motion_allowed=true` 的最小合同：

- `CONTROL_ROS_COMMAND_LOGGING_ONLY` 已经由人工确认关闭，并且本次固件版本被记录。
- NanoPi heartbeat 新鲜，未超时。
- 急停未触发，限位/抱闸/供电/温度状态均正常。
- 参与运动的关节映射、方向、零点、软硬限位、速度上限和电流/扭矩上限已经现场确认。
- 所有参与运动的电机反馈新鲜，且没有 motor fault、bus-off、error-passive 或通信丢失。
- 最近一次 M33 ROS safety assessment 没有拒绝原因，`detail_code=none`。
- M33 `0x322` 同时满足 `error_code=0`、`safety_state=ok`、`control_mode=armed/active`、`detail_code=none`。

不满足任一条件时，M33 必须保持或回退到 `motion_allowed=false`。

## 8. ROS 正规开发线路

第一阶段只打通数据和仿真合同：

```text
URDF/MuJoCo -> JointTrajectory -> NanoPi bridge dry-run -> M33 logging-only audit
M33/电机/C8T6 telemetry -> NanoPi -> /joint_states + /rehab_arm/motor_state + /rehab_arm/safety_state
```

平台只读取：

- `/joint_states`
- `/rehab_arm/motor_state`
- `/rehab_arm/safety_state`
- `/rehab_arm/sensor_state`
- `/rehab_arm/camera_keyframe`

平台不输出运动命令。后续若服务器/VLA 下发任务，也必须转成高层任务，进入仿真/规划，再经 `JointTrajectory -> NanoPi -> M33`。
