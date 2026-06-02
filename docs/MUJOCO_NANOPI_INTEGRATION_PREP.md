# MuJoCo 主机接 NanoPi 准备方案

本文记录 `medical_arm_mujoco.xml` 后续如何接 NanoPi、M33、服务器/VLA。当前目标是先打通只读、shadow、dry-run 链路，不让 MuJoCo 或 VLA 直接获得真机控制权。

## 当前事实

远程 MuJoCo 主机：

```text
host: cal@192.168.2.46
mujoco: /home/cal/mujoco
viewer: /home/cal/mujoco/build/bin/simulate
model: /home/cal/medical_arm_mujoco/medical_arm_mujoco.xml
open script: /home/cal/medical_arm_mujoco/open_mujoco.sh
validate script: /home/cal/medical_arm_mujoco/validate_mujoco.py
```

NanoPi：

```text
host: pi@192.168.2.66
role: ROS2 bridge to M33/CAN
formal trajectory topic: /arm_controller/joint_trajectory
M33 target CAN: 0x320
NanoPi heartbeat CAN: 0x321
M33 status CAN: 0x322
```

ROS2 network baseline:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

## 关键架构边界

```mermaid
flowchart LR
  VLA["服务器/VLA\n语音+视觉+状态\n高层任务/轨迹候选"]
  Sim["Linux MuJoCo 主机\n仿真/可视化/规划/shadow"]
  NanoPi["NanoPi ROS2\n状态聚合/轨迹候选转发"]
  M33["M33\n最终安全裁决/限位/电机控制"]
  Motor["电机/传感器"]

  Motor -->|"CAN 原始反馈/状态"| M33
  M33 -->|"0x322/0x330.. 状态"| NanoPi
  NanoPi -->|"ROS2 状态 topics"| Sim
  Sim -->|"shadow/dry-run JointTrajectory"| NanoPi
  NanoPi -->|"enable_target_tx=false 时只打印 DRY-RUN"| M33
  VLA -->|"任务/候选轨迹"| Sim
  Sim -->|"审核后的候选轨迹"| NanoPi
  NanoPi -->|"正式模式才可发 0x320"| M33
  M33 -->|"本地安全通过后"| Motor
```

必须坚持：

- MuJoCo 主机只做仿真、可视化、规划、数据回放和 dry-run。
- NanoPi 接收候选轨迹，但默认 `enable_target_tx=false`，只做 DRY-RUN。
- M33 是唯一真机最终安全权威。
- VLA 不输出 CAN、电流、力矩、裸电机角或绕过 M33 的命令。

## 不能直接硬接的原因

当前仓库 ROS2 最小仿真仍是早期 5 关节基线：

```text
shoulder_lift_joint
elbow_lift_joint
shoulder_abduction_joint
upper_arm_rotation_joint
forearm_rotation_joint
```

新的 MJCF 是 `medical_arm.zip` 的 6 个真实 URDF 关节：

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

因此下一步要先统一 joint schema。否则会出现：

- NanoPi/M33 以为收到旧 `joint_id=0..4`。
- MuJoCo 以为控制 6 个新 URDF 关节。
- VLA/服务器状态里 `motor_id`、`joint_id`、`urdf_joint` 混用。
- 7 号外部调试电机被误当成机械臂关节。

## Demo 和主线分类

当前仓库已有一些历史 demo，它们可以保留做冒烟测试，但不能混进正式 6 关节 medical arm 主线：

| 入口 | 分类 | 当前用途 | 禁止事项 |
|---|---|---|---|
| `rehab_arm_control/demo_trajectory_node.py` | demo | legacy 5 关节 ROS topic smoke | 不作为 6 关节 planner，不作为真机 workflow |
| `rehab_arm_control/vla_task_planner_node.py` | placeholder demo | 证明 `/vla/task_goal` 能转 topic | 不代表 VLA 已能控制真机 |
| `sim_data_collection.launch.py enable_demo_trajectory:=true` | data demo | 仿真/离线采集 | 不接真实 NanoPi 运动链路 |
| `m33_motor_status_smoke.py` | synthetic smoke | 离线解析和 recorder 测试 | 不当作 fresh motor feedback |
| `nanopi_can_master.py` | bench/debug | can0、电机协议、现场诊断 | 不进入正式 bringup，不用于穿戴控制 |
| `fallback-first-order` sim backend | fallback demo | ROS 节点和 topic 合同 | 不等同真实 MuJoCo 模型 |

后续 AI 必须先声明任务属于 `mainline`、`shadow-sim`、`dry-run`、`bench-debug` 还是 `offline-demo`。分类不清时默认按 `offline-demo` 或只读处理。

## 推荐分阶段接入

### 阶段 0：单机 MuJoCo 可视化

目标：远程主机自己能打开、渲染、检查关节和 actuator。

命令：

```bash
cd /home/cal/medical_arm_mujoco
./open_mujoco.sh
```

验证：

```bash
cd /home/cal/medical_arm_mujoco
MUJOCO_GL=egl python3 validate_mujoco.py
```

通过标准：

- `nq=6 nv=6 nu=6`。
- 6 个 joint 都有 range。
- 6 个 actuator 都有 ctrlrange。
- 预览图能生成。

### 阶段 1：ROS2 shadow 状态，不接 NanoPi 目标

目标：MuJoCo 主机发布仿真状态，但使用独立命名空间，避免和 NanoPi 真实 `/joint_states` 冲突。

建议 topics：

```text
/sim/medical_arm/joint_states
/sim/medical_arm/safety_state
/sim/medical_arm/model_state
/sim/medical_arm/trajectory_candidate
```

不要直接发布到：

```text
/joint_states
/arm_controller/joint_trajectory
```

原因：NanoPi bridge 和真实状态也使用这些公共 topic，早期联调阶段必须避免真假状态混在一起。

### 阶段 2：NanoPi 只读状态上行

目标：MuJoCo 主机能看到 NanoPi/M33 的真实状态，但不发目标。

NanoPi 启动 bridge：

```bash
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

MuJoCo 主机查看：

```bash
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
ros2 topic list
ros2 topic echo /rehab_arm/safety_state --once
ros2 topic echo /rehab_arm/motor_state --once
ros2 topic echo /joint_states --once
```

通过标准：

- 能看到 `/rehab_arm/safety_state`。
- 能看到 `/rehab_arm/motor_state`。
- `/joint_states` 只在 fresh motor status 存在时发布。
- CAN 抓包确认没有 `0x320`。

### 阶段 3：dry-run 轨迹链路

目标：MuJoCo/规划器发布候选轨迹，NanoPi bridge 收到并打印 DRY-RUN，但仍不发 M33 `0x320`。

前提：

```text
enable_target_tx=false
require_psoc_ok_for_trajectory=true
require_fresh_motor_status_for_trajectory=true
```

如果只是测试 ROS2 链路，可临时在台架/只读环境关闭 gate，但必须保持：

```text
enable_target_tx=false
```

通过标准：

- NanoPi 日志出现 `DRY-RUN 320 ...`。
- candump 没有 `0x320`。
- M33/Motor 没有动作。

### 阶段 4：6 关节正式 schema 对齐

需要新增一个统一 schema，例如：

```yaml
schema_version: medical_arm_joint_schema_v1
joints:
  - joint_index: 0
    urdf_joint: jian_hengxiang_joint
    motor_ref: node_id:3
    transmission_ratio: 0.5
    m33_joint_id: null
    calibrated: false
  - joint_index: 1
    urdf_joint: jian_zongxiang_joint
    motor_ref: motor_id:4
    transmission_ratio: null
    m33_joint_id: null
    calibrated: false
```

需要决定：

- M33 `0x320` 是否从旧 5 关节升级为新 6 关节。
- 旧 ROS joint 名是否保留别名，还是全部切到 URDF joint 名。
- NanoPi 是否同时发布：
  - `/joint_states`，正式输出端 joint。
  - `/rehab_arm/motor_state`，原始电机诊断。
  - `/rehab_arm/joint_motor_mapping`，标定版本/传动比/方向/零点。

### 阶段 5：VLA/服务器接入

VLA 输入应使用：

```text
语音文本
摄像头关键帧
输出端 joint state
motor diagnostics
M55 小模型结果
patient profile / ROM / safety limits
history/session context
```

VLA 输出只能是：

```text
task_goal
subtask
trajectory_candidate
assist_level_suggestion
```

不得输出：

```text
CAN frame
motor current
motor torque
raw motor position
emergency override
limit override
```

## 现在可以先准备的具体任务

1. 在仓库 ROS2 代码里新增 `medical_arm_joint_schema.py` 或 YAML，记录 6 关节名、limit、actuator、motor mapping draft。
2. 给 MuJoCo sim node 增加参数：
   - `joint_schema:=medical_arm_6dof`
   - `joint_state_topic:=/sim/medical_arm/joint_states`
   - `trajectory_topic:=/sim/medical_arm/joint_trajectory`
3. 增加一个 bridge/adapter：
   - 输入 `/sim/medical_arm/trajectory_candidate`
   - 输出 `/arm_controller/joint_trajectory`
   - 默认 `dry_run_only=true`
   - 检查 joint 名、limit、速度、加速度、profile。
4. NanoPi bridge 增加 6 关节模式前，禁止把 `medical_arm` 轨迹直接发到旧 `joint_id=0..4`。
5. 服务器/VLA schema 增加字段：
   - `urdf_joint_name`
   - `motor_ref`
   - `transmission_calibration_version`
   - `source=sim|m33|nanopi|vla`
   - `authority=suggestion|candidate|approved_by_m33`

## 最小联调命令模板

MuJoCo 主机：

```bash
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
cd /home/cal/medical_arm_mujoco
MUJOCO_GL=egl python3 validate_mujoco.py
```

NanoPi 只读：

```bash
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

确认无目标帧：

```bash
timeout 3s candump -L can0,320:7FF,321:7FF,322:7FF
```

## 当前不做的事

- 不把 `medical_arm_mujoco.xml` 的 6 关节直接映射到旧 M33 `joint_id=0..4`。
- 不把 legacy `demo_trajectory_node.py` 当作 6 关节主线 planner。
- 不启用 `enable_target_tx=true`。
- 不把 `motor_id=7` 放回机械臂。
- 不让 VLA/服务器/NanoPi 直接发裸电机命令。
