# PSoC CAN Protocol V1

本文档固定 NanoPi ROS bridge 和英飞凌 M33 之间第一版 CAN 对照协议。当前目标是日志对照和安全审核，不是直接带动电机。

厂家电机协议、电机 ID、灵足/伺泰威遥测解码和待确认量程见：[MOTOR_PROTOCOLS.md](MOTOR_PROTOCOLS.md)。本文件只描述 NanoPi 和 M33 之间的正式控制/状态边界。

## 安全边界

- `0x320` 是 NanoPi 到 M33 的关节目标帧，但 NanoPi 默认 dry-run，不发送真实 `0x320`。
- 只有 M33 能打印接收日志、限幅结果、拒绝原因和 safety state 后，才允许临时打开 `enable_target_tx:=true` 做单帧对照。
- M33 收到 `0x320` 后也不能直接驱动电机，必须先经过限位、限速、急停、供电、通信时效和当前模式检查。
- 如果字段无法解析、关节号未知、目标超限、急停触发、heartbeat 超时或电源异常，M33 必须拒绝执行并上报 fault/limited。

## CAN IDs

| CAN ID | 方向 | 帧类型 | 用途 |
|---|---|---|---|
| `0x320` | NanoPi -> M33 | classic CAN standard 11-bit | 关节目标/轨迹片段 |
| `0x321` | NanoPi -> M33 | classic CAN standard 11-bit | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | classic CAN standard 11-bit | M33 status |
| `0x330` ~ `0x337` | M33 -> NanoPi | classic CAN standard 11-bit | M33 聚合后的电机/关节遥测草案 |

## `0x321` NanoPi Heartbeat

Payload:

| Byte | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 0 | `seq` | `uint8` | NanoPi heartbeat 序号，0-255 循环 |

已验证示例：

```text
TX STD 0x00000321 [1] 02
RX STD 0x00000322 [8] A5 02 07 00 17 98 79 00
```

## `0x322` M33 Status

当前已观察到的 payload 格式：

| Byte | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 0 | `marker` | `uint8` | 固定 `0xA5` |
| 1 | `seq` | `uint8` | 对应 heartbeat/status 序号 |
| 2 | `motors` | `uint8` | M33 侧电机/节点状态摘要，目前观察为 `7` |
| 3 | `error_code` | `uint8` | `0` 表示 ok，非 0 表示 fault |
| 4..7 | `status_data` | `uint8[4]` | 当前作为 M33 扩展状态/计数数据，字段待固件确认 |

NanoPi bridge 解析规则：

- `marker != 0xA5` -> `fault`
- `DLC < 4` -> `fault`
- `error_code != 0` -> `fault`
- 其他情况 -> `ok`

### `0x322` V2 扩展状态草案

为后续 M33 安全状态机预留以下 V2 格式。当前 M33 已烧录的 logging-only 固件仍可继续使用上面的 V1 legacy 格式；NanoPi bridge 会先判断 byte4..6 是否像 V2 枚举，如果不像，则按 V1 兼容解析。

| Byte | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 0 | `marker` | `uint8` | 固定 `0xA5` |
| 1 | `seq` | `uint8` | 对应 heartbeat/status 序号 |
| 2 | `motors` | `uint8` | M33 管理的电机/节点数量或摘要 |
| 3 | `error_code` | `uint8` | `0` 表示无硬错误；非 0 强制 ROS 侧进入 `fault` |
| 4 | `safety_state` | `uint8` | 见 safety state enum |
| 5 | `control_mode` | `uint8` | 见 control mode enum |
| 6 | `detail_code` | `uint8` | 最近一次安全评估详情，当前 M33 logging-only 固件不会自动清零 |
| 7 | `heartbeat_age_100ms` | `uint8` | M33 看到的 NanoPi heartbeat 年龄，单位 100ms，饱和到 255 |

Safety state enum:

| 值 | 名称 | ROS `/rehab_arm/safety_state.state` |
|---:|---|---|
| `0` | `ok` | `ok` |
| `1` | `limited` | `limited` |
| `2` | `emergency_stop` | `emergency_stop` |
| `3` | `fault` | `fault` |

Control mode enum:

| 值 | 名称 | 说明 |
|---:|---|---|
| `0` | `boot` | M33 刚启动或初始化中 |
| `1` | `logging_only` | 只解析/打印/拒绝 `0x320`，不输出电机控制 |
| `2` | `standby` | 待机，可收状态，不执行运动 |
| `3` | `armed` | 已通过安全准备，但未执行轨迹 |
| `4` | `active` | 正在执行经过安全审核的轨迹 |
| `5` | `emergency_stop` | 急停保持 |

Detail code enum:

| 值 | 名称 | 说明 |
|---:|---|---|
| `0` | `none` | 无额外原因 |
| `1` | `heartbeat_timeout` | NanoPi heartbeat 超时 |
| `2` | `unsupported_command` | 当前状态机不支持该 `0x320` 命令 |
| `3` | `unknown_joint` | 关节号不存在或未映射 |
| `4` | `target_out_of_limit` | 目标角度超出 M33 最终限位 |
| `5` | `velocity_out_of_limit` | 速度超限 |
| `6` | `torque_out_of_limit` | 扭矩/电流超限 |
| `7` | `emergency_stop` | 急停触发 |
| `8` | `power_fault` | 供电异常 |
| `9` | `motor_fault` | 电机/驱动故障 |
| `10` | `logging_only_no_motor_output` | logging-only 阶段拒绝输出 |

当前 M33 logging-only 固件会把最近一次 ROS safety assessment 的首要拒绝原因放到 byte6 `detail_code`。例如，收到超限 `0x320` 后，下一次 `0x321 -> 0x322` 的 byte6 应为 `4`，NanoPi ROS 会解析为 `target_out_of_limit`。

语义约定：

- `safety_state` 表示当前总体安全状态，例如 `ok/limited/emergency_stop/fault`。
- `detail_code` 当前表示 `last_safety_assessment`，也就是最近一次安全评估详情。
- `detail_code` 不会因为下一次普通 heartbeat 自动恢复为 `0` 或 `10`；它会保留到下一次 ROS safety assessment 覆盖。
- App、服务器、日志系统展示时，应把 `detail_code/detail` 标注为“最近一次拒绝/评估原因”，不要单独当成实时 fault。
- NanoPi parser 为了兼容旧代码仍输出 `detail_code/detail`，同时会额外输出：
  - `detail_semantics: "last_safety_assessment"`
  - `last_assessment_detail_code`
  - `last_assessment_detail`
- NanoPi parser 同时输出 `motion_allowed`，供 App/服务器/仿真主机快速判断是否允许进入运动候选状态。
- 当前 logging-only 阶段 `motion_allowed` 必须为 `false`。
- 后续如果需要同时表达“当前实时 detail”和“最近一次拒绝原因”，应新增协议字段或 V3 扩展，不要改变 V2 byte6 的既有含义。

示例：

```text
V2 logging-only limited:
0x322 [8] A5 02 07 00 01 01 0A 03

解析:
state=limited
control_mode=logging_only
detail=logging_only_no_motor_output
heartbeat_age_ms=300
```

当前 M33 本地补丁的 immediate heartbeat reply 使用 `heartbeat_age_100ms=0`，所以烧录后预期形如：

```text
0x322 [8] A5 <seq> 07 00 01 01 0A 00
```

例如 `A5 22 07 00 01 01 0A 00` 应解析为：

```json
{"protocol_version":2,"state":"limited","control_mode":"logging_only","detail":"logging_only_no_motor_output","heartbeat_age_ms":0}
```

## `0x330~0x337` M33 Motor Status Draft

这是 M33 汇总电机状态后发给 NanoPi 的遥测草案，固件尚未正式实现。NanoPi 侧 parser 已按该草案离线测试通过，但它不进入运动许可链路。

Payload V1:

| Byte | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 0 | `marker` | `uint8` | 固定 `0xB3` |
| 1 | `seq` | `uint8` | 状态序号 |
| 2 | `motor_id` | `uint8` | 当前已知 `3/4/5/6/7` |
| 3 | `flags` | `uint8` | bit0 enabled, bit1 fault, bit2 limited, bit3 emergency_stop |
| 4..5 | `position_mrad` | `int16` little-endian | 关节位置，单位 mrad |
| 6 | `velocity_drad_s` | `int8` | 关节速度，单位 0.1 rad/s |
| 7 | `temperature_c` | `uint8` | 摄氏度，`0xFF` 表示未知 |

NanoPi 侧映射：

- 只读遥测，不发控制命令。
- 转为 `/rehab_arm/motor_state` 时标记 `protocol=m33_motor_status_v1`。
- `psoc_can_bridge_node.py` 会在收到合法 `0x330~0x337` 后发布 `/rehab_arm/motor_state` JSON。
- 同一批合法遥测会同步发布 ROS 标准 `/joint_states`，供 RViz、MuJoCo 状态同步、平台 3D 预览和标注回放读取。
- `0x330` 对应 slot 0，`0x337` 对应 slot 7；slot 到真实关节的最终映射仍需 M33/机械装配确认。
- 运动是否允许仍以 `0x322` safety/status 和 M33 内部安全状态机为准。

## `0x320` Joint Target Command

当前 NanoPi dry-run 编码格式：

| Byte | 字段 | 类型 | 端序 | 说明 |
|---:|---|---|---|---|
| 0 | `cmd` | `uint8` | - | 当前 `0x03` 表示 set target |
| 1 | `joint_id` | `uint8` | - | 关节编号 |
| 2..3 | `deg_x10` | `int16` | little-endian | 目标角度，单位 0.1 deg |
| 4..5 | `rpm` | `int16` | little-endian | 建议速度，当前默认 `5` |
| 6..7 | `torque_ma` | `int16` | little-endian | 建议扭矩/电流，当前默认 `0` |

关节编号：

| joint_id | ROS joint name | 当前软件限位 rad |
|---:|---|---|
| 0 | `shoulder_lift_joint` | `[-0.70, 1.40]` |
| 1 | `elbow_lift_joint` | `[0.00, 1.80]` |
| 2 | `shoulder_abduction_joint` | `[-0.45, 0.80]` |
| 3 | `upper_arm_rotation_joint` | `[-1.20, 1.20]` |
| 4 | `forearm_rotation_joint` | `[-1.20, 1.20]` |

编码公式：

```text
deg_x10 = int(degrees(position_rad) * 10.0)
```

注意：这里使用 Python `int()`，也就是向 0 截断，不做四舍五入。

已验证 dry-run 示例：

```text
ROS input: shoulder_lift_joint = 0.1 rad
DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000
```

解码：

| 字段 | 值 |
|---|---:|
| `cmd` | `0x03` |
| `joint_id` | `0` |
| `deg_x10` | `57` |
| `target_deg` | `5.7 deg` |
| `target_rad` | `0.09948 rad` |
| `rpm` | `5` |
| `torque_ma` | `0` |

## M33 日志要求

M33 侧实现参考见：[M33_0X320_LOGGER_GUIDE.md](M33_0X320_LOGGER_GUIDE.md)。

烧录或运行 M33 侧对照固件时，收到 `0x320` 后至少打印：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 joint_id=0 deg_x10=57 target_deg=5.7 target_rad=0.09948 rpm=5 torque_ma=0
decision=accept_or_reject reason=...
safety_state=ok_or_limited_or_fault
```

M33 还应该打印：

- 当前模式是否允许接收 NanoPi target。
- heartbeat 是否新鲜。
- 急停是否触发。
- 电源/电池状态是否正常。
- 关节号是否存在。
- 目标是否在 M33 最终限位内。
- 限幅后的目标值，如果 M33 选择限幅而不是拒绝。

## M33 安全状态机预编辑边界

当前最近的本地 M33 工程为 `D:\RT-ThreadStudio\workspace\yiliao_m33`，最近 Git 提交为 `ce90173a Bring up M33 CAN path ...`。该工程已经具备以下预编辑基础：

- `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`，默认只解析和审核 `0x320`，不输出电机控制。
- `ctrl_assess_ros_command_safety()` 对 heartbeat、关节号、目标位置、速度和扭矩做初步审核。
- `0x322` V2 byte6 会回传最近一次审核的 `detail_code`。
- M33 串口会打印 `final action=no_motor_output logging_only=1`。

后续进入真实执行前，必须由 M33 工程侧补齐并人工复核：

- 7 轴真实 `joint_id -> motor_id -> 厂家协议 -> 机械关节` 映射。
- 每个关节的 M33 最终限位、速度限制、加速度限制、力矩/电流限制。
- 急停输入、抱闸/制动、供电异常、温度异常和电机故障联锁。
- 电机反馈超时、C8T6 传感超时、NanoPi heartbeat timeout 的降级动作。
- M55 小模型输出只作为建议输入，不能绕过 M33 安全裁决。

在这些参数未确认前，`logging_only` 不应关闭。

## NanoPi 对照命令

生成 payload，不访问 CAN：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1
```

预期输出包含：

```text
can_id: 0x320
joint_name: shoulder_lift_joint
joint_id: 0
position_rad: 0.10000
target_deg: 5.72958
deg_x10: 57
rpm: 5
torque_ma: 0
payload: 0300390005000000
```

只解码 payload，不访问 CAN：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000
```

预期输出包含：

```text
can_id: 0x320
cmd: 0x03
joint_id: 0
joint_name: shoulder_lift_joint
deg_x10: 57
target_deg: 5.7
target_rad: 0.09948
rpm: 5
torque_ma: 0
```

## 下一步

1. 用户确认或烧录 M33 日志固件。
2. NanoPi 先保持 `enable_target_tx=false`，用 dry-run 记录 payload。
3. 用户确认 M33 能安全记录 `0x320` 且不驱动电机。
4. 只在不接人、不运动的台架条件下，临时运行 `enable_target_tx:=true` 做单帧日志对照。
