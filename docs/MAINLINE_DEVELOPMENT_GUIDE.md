# 机械臂主线开发教程

本文只讲当前主线怎么继续开发。目标是把已有的 CAN、M33、NanoPi、ROS2、MuJoCo、路径规划和后续 App/平台接成一条线，而不是再造旁路。

## 1. 当前结论

正式主线只有一条：

```text
当前关节状态 -> 路径规划候选 -> MuJoCo dry-run -> 人确认
-> /arm_controller/joint_trajectory -> NanoPi -> M33 -> 电机
```

安全执行层统一在英飞凌 M33：

- M33 负责最终限位、限速、限流、急停、通信超时、电机 fault、是否执行。
- NanoPi 负责 ROS2 bridge、状态解析、轨迹转发、数据上传。
- Linux 仿真主机负责 MuJoCo、路径规划预演、可视化。
- App、M55、服务器和 VLA 只能给请求、建议、profile 或候选轨迹，不能直接发底层电机命令。

## 2. 已经有的

| 模块 | 已有状态 | 入口 |
|---|---|---|
| 3/4/5/6 电机遥测 | 已经采集到过 raw CAN、M33 聚合、ROS joint 状态 | `docs/PROJECT_PROGRESS.md` |
| 3 号小幅动作 | M33 shell speed-hold 已验证 | `docs/PROJECT_PROGRESS.md` |
| 4/5/6 命令链 | speed-hold/stop 返回正常，位置变化很小 | `docs/PROJECT_PROGRESS.md` |
| M33 安全主站 | `0x321 -> 0x322`、`0x330~0x334` 已验证 | `D:/RT-ThreadStudio/workspace/yiliao_m33` |
| NanoPi ROS2 | `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state` | `rehab_arm_psoc_bridge` |
| MuJoCo 6DOF | 隔离 topic 下 6DOF 轨迹已验证 | `docs/MUJOCO_MOVE_MOTOR_GUIDE.md` |
| VLA/dry-run gate | 候选轨迹、MuJoCo review、operator review 框架已存在 | `rehab_arm_psoc_bridge` |
| 当前主线边界 | 已成文 | `docs/CURRENT_MAINLINES.md` |

## 3. 还差什么

| 缺口 | 先怎么处理 | 后续你要补什么 |
|---|---|---|
| 机械零点 | 先把当前姿态当临时工程零点 | 把每个关节摆到真实机械零位后改零点 |
| 方向 | 先按 `unknown`，规划只做 MuJoCo 小幅测试 | 逐关节小幅动作，记录正方向 |
| 限位 | 先用保守软件范围，只在 M33 最终裁决 | 填真实机械硬限位、患者 ROM |
| 1/2 腕部 | 当前不上电，不进入主线运动 | 上电后补协议、ID、方向、限位 |
| 4/5/6 持续 joint state | 需要短时 active-report 或后续 M33 常态汇总策略 | 决定正式遥测频率和 M33 缓存策略 |
| 路径规划器 | 先做 joint-space 小幅候选 | 再做末端/任务空间规划 |
| 正式执行 | 先 MuJoCo-only，再 M33 gate | 完成 M33 接收 `/arm_controller/joint_trajectory` 小幅验证 |

## 4. 临时零点策略

本阶段采用：

```text
当前上电姿态 = engineering zero
```

这不是临床零点，也不是最终机械零位。它只用于开发 planner、MuJoCo shadow、数据记录和小幅相对轨迹。

临时标定表在：

```text
rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_temporary_calibration.yaml
```

你后续主要改这几个字段：

- `observed_zero_position_rad`
- `direction_sign`
- `joint_to_motor_ratio`
- `soft_limit_rad`
- `velocity_limit_rad_s`
- `notes`

## 5. 开发步骤

### Step 1: 只读确认

NanoPi：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 topic echo --once /joint_states
ros2 topic echo --once /rehab_arm/motor_state
ros2 topic echo --once /rehab_arm/safety_state
```

通过标准：

- 能看到当前已上电关节。
- `/rehab_arm/safety_state` 来自 M33。
- 没有意外 `0x320`。

### Step 2: 用当前姿态生成候选轨迹

未标定前，planner 只生成相对当前姿态的小幅 joint-space 轨迹。

禁止：

- 不生成绝对大角度目标。
- 不做末端笛卡尔到达。
- 不绕过 M33。

允许：

- MuJoCo-only 小幅动作。
- dry-run candidate。
- 人看过后再进入下一步。

### Step 3: MuJoCo dry-run

先按 `docs/MUJOCO_MOVE_MOTOR_GUIDE.md` 的隔离 topic 跑：

```text
/codex_path_test/joint_trajectory
/codex_path_test/joint_states
```

确认轨迹能在 MuJoCo 里走完并回到可控状态。

### Step 4: 正式入口干跑

只验证 NanoPi bridge 是否接受格式，不让它发真机目标：

```text
enable_target_tx=false
```

通过标准：

- bridge 日志能说明 accepted/rejected 原因。
- `candump can0,320:7FF` 没有真实目标帧。

### Step 5: M33 最终小幅执行

只有这些都满足时才做：

- 现场无人穿戴。
- 急停/断电手段明确。
- 只动一个关节。
- 目标相对当前零点很小。
- M33 safety/fresh feedback 正常。
- 动作后立刻 stop 并读回。

正式执行仍只走：

```text
/arm_controller/joint_trajectory -> NanoPi -> M33 -> 电机
```

## 6. 参数谁负责

| 参数 | 先放哪里 | 最终由谁裁决 |
|---|---|---|
| 机械零点、方向、传动比 | temporary calibration YAML / profile | M33 执行前使用安全子集 |
| 软件限位、限速、限流 | profile / M33 config | M33 |
| 患者 ROM | patient profile | M33 只接收审核后安全子集 |
| 规划候选 | Linux/服务器/NanoPi | 不直接执行 |
| 急停、fault、timeout | M33 | M33 |

一句话：上位机可以记录和生成参数，M33 负责最终执行判定。

## 7. 你后续要补的参数表

每个关节至少补这些：

```text
joint_name:
  motor_id:
  current_zero_position_rad:
  real_mechanical_zero_position_rad:
  direction_sign: +1 or -1
  joint_to_motor_ratio:
  soft_limit_min_rad:
  soft_limit_max_rad:
  max_velocity_rad_s:
  max_current_or_torque:
  positive_direction_observation:
  negative_direction_observation:
```

补完后再做：

1. 更新 temporary calibration YAML。
2. 更新 patient/device profile。
3. 导出 M33 safety subset。
4. M33 固件或配置侧确认接收。
5. 单关节小幅 formal path 测试。

## 8. 你接下来最该改的三个地方

1. `medical_arm_6dof_temporary_calibration.yaml`
   这里填零点、方向、传动比、软限位、速度限制。
2. `patient_device_profile`
   这里填患者 ROM、训练模式和真正允许的安全子集。
3. `M33` 侧安全配置
   这里只收最终确认过的安全参数，不收 planner 的草稿。

如果你只想先做路径规划，优先只改第 1 个文件，别急着动 M33 代码。
