# M33 0x320 Logging Firmware Guide

本文档给英飞凌 M33 侧实现 `0x320` 接收日志提供最小参考。目标是先做协议对照和安全审核，不驱动电机。

## 当前阶段目标

M33 收到 NanoPi 的 `0x320` 后，只做三件事：

1. 解析 payload。
2. 打印日志。
3. 做安全裁决记录。

当前阶段不要把 `0x320` 直接转成电机命令。

## 前置条件

- CAN 为 classic CAN，标准帧 11-bit，1Mbps。
- M33 已能回复 NanoPi heartbeat：

```text
NanoPi -> M33: 0x321 [seq]
M33 -> NanoPi: 0x322 [A5 seq motors error_code status_data...]
```

- NanoPi bridge 默认 `enable_target_tx=false`，不会发送真实 `0x320`。
- 只有用户烧录并确认 M33 日志固件安全后，NanoPi 才可临时 `enable_target_tx:=true` 做单帧对照。

## `0x320` Payload

| Byte | 字段 | 类型 | 端序 | 说明 |
|---:|---|---|---|---|
| 0 | `cmd` | `uint8_t` | - | `0x03` 表示 set target |
| 1 | `joint_id` | `uint8_t` | - | 关节编号 |
| 2..3 | `deg_x10` | `int16_t` | little-endian | 目标角度，单位 0.1 deg |
| 4..5 | `rpm` | `int16_t` | little-endian | 建议速度 |
| 6..7 | `torque_ma` | `int16_t` | little-endian | 建议扭矩/电流 |

关节编号：

| joint_id | ROS joint name |
|---:|---|
| 0 | `shoulder_lift_joint` |
| 1 | `elbow_lift_joint` |
| 2 | `shoulder_abduction_joint` |
| 3 | `upper_arm_rotation_joint` |
| 4 | `forearm_rotation_joint` |

## M33 最小日志格式

收到 `0x320` 后，串口至少打印：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 joint_id=0 joint=shoulder_lift_joint deg_x10=57 target_deg=5.7 target_rad=0.09948 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output
safety_state=limited
```

如果拒绝原因不同，`reason` 应该改成实际原因，例如：

```text
reason=invalid_dlc
reason=unknown_cmd
reason=unknown_joint
reason=target_out_of_limit
reason=estop_active
reason=power_fault
reason=nanopi_heartbeat_timeout
reason=mode_not_allowed
```

## C 参考解析代码

这段代码只展示字段解析和日志内容，不包含具体 PSoC HAL、RT-Thread CAN API 或 UART API。移植时把 `printf` 换成当前工程的日志函数。

```c
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define PSOC_CMD_ID 0x320u
#define CMD_SET_TARGET 0x03u

typedef enum {
    M33_DECISION_ACCEPT = 0,
    M33_DECISION_REJECT = 1,
} m33_decision_t;

typedef struct {
    uint8_t cmd;
    uint8_t joint_id;
    int16_t deg_x10;
    int16_t rpm;
    int16_t torque_ma;
    float target_deg;
    float target_rad;
} m33_joint_target_t;

static int16_t read_i16_le(const uint8_t *p)
{
    return (int16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static const char *joint_name(uint8_t joint_id)
{
    switch (joint_id) {
    case 0: return "shoulder_lift_joint";
    case 1: return "elbow_lift_joint";
    case 2: return "shoulder_abduction_joint";
    case 3: return "upper_arm_rotation_joint";
    case 4: return "forearm_rotation_joint";
    default: return "unknown";
    }
}

static int decode_0x320(const uint8_t data[8], m33_joint_target_t *out)
{
    out->cmd = data[0];
    out->joint_id = data[1];
    out->deg_x10 = read_i16_le(&data[2]);
    out->rpm = read_i16_le(&data[4]);
    out->torque_ma = read_i16_le(&data[6]);
    out->target_deg = ((float)out->deg_x10) / 10.0f;
    out->target_rad = out->target_deg * 0.017453292519943295f;
    return 0;
}

static const char *validate_0x320(uint8_t dlc, const m33_joint_target_t *target)
{
    if (dlc != 8) {
        return "invalid_dlc";
    }
    if (target->cmd != CMD_SET_TARGET) {
        return "unknown_cmd";
    }
    if (target->joint_id > 4) {
        return "unknown_joint";
    }

    /*
     * TODO: Replace with M33 final safety checks:
     * - current operating mode
     * - heartbeat age
     * - estop state
     * - power state
     * - final joint limit table
     * - motor driver state
     *
     * Before these checks are implemented, keep logging-only reject.
     */
    return "logging_only_no_motor_output";
}

void handle_can_0x320(uint8_t dlc, const uint8_t data[8])
{
    m33_joint_target_t target;
    const char *reason;

    printf("RX 320 dlc=%u data=", (unsigned int)dlc);
    for (uint8_t i = 0; i < dlc && i < 8; ++i) {
        printf("%02X", data[i]);
    }
    printf("\n");

    if (dlc != 8) {
        printf("decision=reject reason=invalid_dlc safety_state=limited\n");
        return;
    }

    decode_0x320(data, &target);
    printf("cmd=0x%02X joint_id=%u joint=%s deg_x10=%d target_deg=%.1f target_rad=%.5f rpm=%d torque_ma=%d\n",
           (unsigned int)target.cmd,
           (unsigned int)target.joint_id,
           joint_name(target.joint_id),
           (int)target.deg_x10,
           (double)target.target_deg,
           (double)target.target_rad,
           (int)target.rpm,
           (int)target.torque_ma);

    reason = validate_0x320(dlc, &target);
    printf("decision=reject reason=%s safety_state=limited\n", reason);
}
```

## 对照步骤

1. NanoPi 生成 payload，不访问 CAN：

```bash
ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1
```

2. NanoPi 解码同一个 payload：

```bash
ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000
```

3. 用户烧录 M33 日志固件。

4. 不接人、不让电机执行运动，确认 M33 侧日志已启动。

5. NanoPi 只发一条单关节测试帧：

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p enable_target_tx:=true \
  -p require_psoc_ok_for_trajectory:=true \
  -p reject_out_of_limit_trajectory:=true
```

另一个终端发布单点轨迹：

```bash
ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory \
  "{joint_names: [shoulder_lift_joint], points: [{positions: [0.1], time_from_start: {sec: 1, nanosec: 0}}]}"
```

6. M33 日志必须和 NanoPi 解码结果一致，且 `decision` 必须是 logging-only reject 或明确安全裁决。

## 不通过标准

出现以下任一情况，停止测试，不继续发 `0x320`：

- M33 没有打印 `RX 320`。
- M33 解码出的 `joint_id/deg_x10/rpm/torque_ma` 与 NanoPi 不一致。
- M33 直接驱动电机。
- M33 没有打印 `decision/reason/safety_state`。
- M33 上报 `0x322 error_code != 0`。
- NanoPi `can0` 进入 error-passive 或 bus-off。

## 需要用户烧录的时机

当要从 dry-run 进入真实 `0x320` 单帧日志对照时，需要用户烧录包含本日志逻辑的 M33 固件。烧录前不要打开 `enable_target_tx:=true`。
