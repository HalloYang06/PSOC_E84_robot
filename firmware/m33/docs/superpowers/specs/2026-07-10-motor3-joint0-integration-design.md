# 3号电机接入现有四关节控制链路设计

日期：2026-07-10

## 1. 背景

当前 M33 正式 ROS 映射为 `joint0/1/2 -> motor4/5/6`，NanoPi 产品服务默认以只读模式运行。现场新接入的 3 号电机使用 Classic CAN 1 Mbps、CANSimple 标准帧、node ID 3。

本设计按用户确认的最终映射，把 3 号电机加入现有系统，同时保留 4、5、6 号电机：

| ROS joint | 电机 | 协议 | M33 状态槽位 | 位置软件限位 |
| --- | ---: | --- | ---: | ---: |
| `joint0` | 3 | CANSimple | `0x330` | -60.0° 到 +60.0° |
| `joint1` | 4 | RobStride private/CSP | `0x331` | 0.0° 到 103.1° |
| `joint2` | 6 | RobStride private/CSP | `0x332` | -60.0° 到 +60.0° |
| `joint3` | 5 | RobStride private/CSP | `0x333` | 0.0° 到 150.0° |

这会有意改变当前 `joint0` 的含义：它由 motor4 改为 motor3。motor4、motor6、motor5 分别迁移到 `joint1`、`joint2`、`joint3`。

## 2. 目标与非目标

### 目标

- 在 M33 和 NanoPi 两端使用同一份四关节映射。
- 复用已经存在的 motor3 CANSimple 编解码、48:1 比例、方向和校准参数。
- 保留 motor4/5/6 的协议、比例、零点、方向和台架控制能力。
- 保持开机默认只读；只有显式进入 bench-motion 路径才允许发送运动目标。
- 用原始 `0x061` 心跳和 `0x069` 编码器帧证明 motor3 在线，再允许微动。

### 非目标

- 不切换 CANOpen、CAN FD 或私有扩展帧协议。
- 不改变 1 Mbps 波特率或 CANFD0 Classic CAN 配置。
- 不把 motor3 自动加入 assist/resist 康复模式。
- 不为本次接入重新开启此前关闭的 CAN RX、ROS command 或 motor-status 后台线程。
- 不绕过 M33 安全审核，把 NanoPi 直发 CANSimple 作为正式运动路径。
- 不扩大到临床运动许可。

## 3. M33 设计

### 3.1 ROS 映射与限位

`applications/control/control_layer_cfg.h` 使用以下四关节配置：

```c
#define CONTROL_ROS_JOINT_COUNT            4U
#define CONTROL_ROS_JOINT0_MOTOR_JOINT     3U
#define CONTROL_ROS_JOINT1_MOTOR_JOINT     4U
#define CONTROL_ROS_JOINT2_MOTOR_JOINT     6U
#define CONTROL_ROS_JOINT3_MOTOR_JOINT     5U

#define CONTROL_ROS_JOINT0_MIN_01DEG       (-600)
#define CONTROL_ROS_JOINT0_MAX_01DEG       600
#define CONTROL_ROS_JOINT1_MIN_01DEG       0
#define CONTROL_ROS_JOINT1_MAX_01DEG       1031
#define CONTROL_ROS_JOINT2_MIN_01DEG       (-600)
#define CONTROL_ROS_JOINT2_MAX_01DEG       600
#define CONTROL_ROS_JOINT3_MIN_01DEG       0
#define CONTROL_ROS_JOINT3_MAX_01DEG       1500
```

motor3 已有的 motor ID、CANSimple 协议、Sitaiwei 型号标记、48:1 比例、校准状态、方向和零点继续作为唯一数据源，不复制第二套常量。

### 3.2 康复模式边界

`CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK` 和 `CONTROL_PREARM_REQUIRED_JOINT_MASK` 保持 `0x38`。这两个掩码继续覆盖当前 4/5/6 号电机组，不因 ROS joint 重排而把 motor3 自动加入 assist/resist。

motor3 只接受显式 `joint0` 目标，并继续经过 M33 的心跳、校准、位置、速度、力矩和 bench-motion 审核。

### 3.3 CAN 数据流

```text
NanoPi ROS joint0 target
  -> standard CAN 0x320, payload joint_id=0
  -> M33 maps ROS joint0 to motor slot 3
  -> existing CANSimple node3 command sequence
  -> standard IDs 0x067/0x06B/0x06C/0x06D/0x06F/0x078

motor3 feedback
  -> 0x061 heartbeat and 0x069 encoder estimate
  -> existing M33 CANSimple parser and feedback cache
  -> reserved aggregate status slot 0x330 when status publication is active
```

motor4、motor6、motor5 的聚合状态槽位依次为 `0x331`、`0x332`、`0x333`。

当前 minimal M33 主循环继续调用 `control_layer_poll_once()`；本次不重新启用历史上为收敛 HardFault 而关闭的后台线程。初次硬件验证以 NanoPi 上的原始 `0x061/0x069` 为准，不把缺少自动 `0x330` 发布误判为 motor3 无回包。

## 4. NanoPi 设计

NanoPi ROS2 包同步为相同顺序：

```text
joint0 = shoulder_lift_joint       = motor3
joint1 = elbow_lift_joint          = motor4
joint2 = upper_arm_rotation_joint  = motor6
joint3 = shoulder_abduction_joint  = motor5
```

需要同步修改：

- `psoc_target.py` 的 `JOINT_NAMES`、ID 和限位。
- `motor_profiles.py` 的四个 motor profile、joint ID 和执行白名单。
- 依赖状态槽位或 joint 顺序的测试和离线检查工具。
- bench motion 计划生成器对 motor3/joint0 的解析。

开机服务 `rehab-arm-nanopi-readonly.service` 保持 `enable_target_tx=false`。运动测试使用已有的显式 bench-motion launch；不得把产品默认服务直接改成自动发目标帧。

## 5. 故障处理与安全门

1. 在任何运动命令之前，被动监听至少 3 秒。
2. 必须观察到 node3 的 `0x061` 和 `0x069`；否则停止软件运动验证。
3. 若缺少这两类帧，检查电机供电、CANH/CANL、共地、node ID 3、CANSimple、1 Mbps、CAN enable 和周期消息设置。
4. 必须确认 `0x321 -> 0x322`，证明 M33 在线并能处理 NanoPi 心跳。
5. 第一次运动只允许空载、人员现场看护、1°、1 rpm、500 mA 上限。
6. 出现心跳中断、非零 error、方向错误、超限或意外运动时，立即发停止/Idle，并停止后续测试。
7. CANSimple 写命令通常没有独立 ACK；成功判据是 `0x061` 状态变化和 `0x069` 位置/速度变化。

## 6. 测试策略

实施严格采用测试先行：

- M33 静态回归测试先断言四关节数量、精确映射、精确限位，以及 assist/prearm 掩码仍为 `0x38`。
- 先运行测试并确认它因当前三关节映射而失败，再修改生产配置。
- NanoPi 单元测试先断言四个 motor profile 和 joint 顺序，且旧的 motor4/5/6 参数不被改写。
- 编码测试断言 `joint0` 编成 motor3 目标、`joint1` 编成 motor4、`joint2` 编成 motor6、`joint3` 编成 motor5。
- dry-run 验证 motor3 计划解析为 joint0，且未显式执行时不发送 CAN 目标帧。
- M33 完整构建必须成功，相关 host/static 测试和 NanoPi pytest 必须全部通过。
- 上板验证按 `0x061/0x069 -> 0x321/0x322 -> dry-run -> 1°微动 -> stop/Idle` 顺序执行。

## 7. 验收标准

- M33 与 NanoPi 对四个 joint 的映射完全一致。
- 4、5、6 号电机原有协议参数、标定值和 assist/resist 掩码保持不变。
- 默认 NanoPi 服务仍然只读。
- motor3 上电后能持续看到 `0x061` 和 `0x069`。
- NanoPi 心跳能得到 M33 `0x322` 回复。
- motor3 的 1°微动方向和幅度正确，随后能可靠停止并回到 Idle。
- 任一安全前置条件不满足时，测试脚本返回非零并且不发送运动目标。

## 8. 已知风险

- 当前现场尚未看到 motor3 的 `0x061/0x069`，因此代码映射修复不等于电机已经在线。
- motor3 的 48:1 比例沿用现有项目配置；首次运动前仍需与厂家上位机显示值或铭牌确认。
- 自动 `0x330~0x333` 状态发布当前关闭；恢复该线程需要独立的栈、调度和 HardFault 回归，不纳入本次接入。
- 变更 joint 语义后，任何缓存旧 joint 顺序的 ROS bag、脚本或外部应用都必须同步更新后才能发送目标。
