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
| motor 3 | `node_id=3` | 伺泰威 / Sitaiwei | CANSimple/ODrive 类标准帧 | heartbeat `0x061`，encoder estimate `0x069` | 可离线转换为 `/rehab_arm/motor_state` |
| motor 4 | `motor_id=4` | 灵足 / Lingzu RobStride | 私有扩展帧 | active-report `0x180004FD` | 原始遥测已确认，型号待确认 |
| motor 5 | `motor_id=5` | 灵足 / Lingzu RobStride | 私有扩展帧 | active-report `0x180005FD` | 原始遥测已确认，型号待确认 |
| motor 6 | `motor_id=6` | 灵足 / Lingzu RobStride | 私有扩展帧 | active-report `0x180006FD` | 原始遥测已确认，型号待确认 |
| motor 7 | `motor_id=7` | 灵足 / Lingzu RobStride | 私有扩展帧 | active-report `0x180007FD` | 原始遥测已确认，型号待确认 |

待确认项：

- 4/5/6/7 分别是 `RS00/RS01/RS02/RS03/RS04/RS05/RS06/EL05` 中哪一款。
- 真实机械关节绑定关系。
- 每个关节的最终软限位、速度限制、力矩/电流限制、抱闸/急停联锁。
- 伺泰威飞书手册的完整协议细节需要人工导出到本地后再补充；当前工具侧不能读取飞书正文。

## 3. 伺泰威 CANSimple 遥测

当前实测：

| CAN ID | 含义 | 解码 |
|---|---|---|
| `0x061` | `node_id=3` heartbeat | `node_id = can_id >> 5`，`cmd_id = can_id & 0x1F = 0x01` |
| `0x069` | `node_id=3` encoder estimate | `cmd_id = 0x09`，payload 为 little-endian `float32 position_turns, float32 velocity_turns_per_sec` |

NanoPi 离线转换：

- `position = position_turns * 2*pi`
- `velocity = velocity_turns_per_sec * 2*pi`
- heartbeat 会补充 `enabled/fault/axis_state/error_code`。

注意：

- CANSimple 直接命令不进入正式 launch。
- 伺泰威产品/用户/协议手册链接已由用户提供，后续需要导出或开放权限后把波特率、控制模式、错误位和限幅字段补齐。

## 4. 灵足 RobStride 私有扩展帧遥测

本地资料来源：

- `D:\电机上位机\robstride_ros_sample\include\motor_ros2\motor_cfg.h`
- `D:\电机上位机\robstride_ros_sample\src\motor_cfg.cpp`
- `D:\电机上位机\SampleProgram\RS\Robstride01.cpp`
- `D:\电机上位机\RobStride_学习整理.md`

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

- `EL05` 资料在本地产品目录中存在，但当前 ROS2 示例没有给出单独枚举；确认 4/5/6/7 是否为 EL05 后再补量程。
- 主动上报要在测试结束后关闭，避免总线长期高频刷帧。
- 正式路径应由 M33 读取/聚合电机状态，再发给 NanoPi 发布 `/rehab_arm/motor_state`。

## 5. M33 正式数据流预编辑

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

## 6. ROS 正规开发线路

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
