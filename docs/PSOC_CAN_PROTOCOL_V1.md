# PSoC CAN Protocol V1

本文档固定 NanoPi ROS bridge 和英飞凌 M33 之间第一版 CAN 对照协议。当前目标是日志对照和安全审核，不是直接带动电机。

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
