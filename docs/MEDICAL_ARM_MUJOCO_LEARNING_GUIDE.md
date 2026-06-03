# medical_arm 6DOF MuJoCo 学习路线

本文只覆盖当前 `medical_arm.zip` 机械臂的 6 关节 MuJoCo shadow 仿真。它不是旧 5 关节 demo 教程，也不是直接真机运动教程。

## 1. 当前你需要认准的主线

| 目的 | 文件或命令 |
|---|---|
| 6 关节 MJCF 模型 | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml` |
| 6 关节名、限位、电机草案 | `rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_schema.yaml` |
| MuJoCo backend 参数、限位夹紧 | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_backend.py` |
| ROS2 仿真节点 | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py` |
| 6DOF 单机 shadow launch | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_shadow.launch.py` |
| NanoPi 硬件 shadow launch | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py` |
| NanoPi 到 MuJoCo 的关节映射 relay | `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/medical_arm_shadow_relay_node.py` |

当前 6 个 MuJoCo joint 固定为：

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

## 2. 第一次学习只跑单机仿真

在仿真主机：

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_shadow.launch.py
```

另开终端看状态：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState
```

发一条 6 关节目标：

```bash
ros2 topic pub --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory \
  "{joint_names: ['jian_hengxiang_joint','jian_zongxiang_joint','jian_xuanzhuan_joint','zhou_zongxiang_joint','wanbu_zongxiang_joint','wanbu_hengxiang_joint'], points: [{positions: [0.1, 0.2, 0.1, 0.4, 0.1, 0.05], time_from_start: {sec: 1, nanosec: 0}}]}"
```

通过标准：

- `/sim/medical_arm/joint_states` 包含 6 个 joint。
- 位置逐渐接近刚发布的目标。
- 没有使用 `/arm_controller/joint_trajectory`。
- 没有启动 NanoPi bridge。
- 没有 CAN、M33、电机动作。

## 3. 学会看自检报告

在 ROS2 工作区：

```bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty
```

重点看这些字段：

| 字段 | 应该怎么理解 |
|---|---|
| `readiness` | `ready_with_mujoco` 表示官方 MuJoCo Python 包可用；`ready_with_fallback_sim` 表示 ROS fallback 仍可跑，但不是严格 MuJoCo |
| `medical_arm_6dof_contract.names` | 当前 6 个 medical arm joint |
| `medical_arm_6dof_topic_contract` | 当前 `/sim/medical_arm/*` topic 合同 |
| `medical_arm_6dof_topic_contract.hardware_shadow_current_mapping` | 当前 7 号 shadow 映射：`forearm_rotation_joint -> jian_xuanzhuan_joint` |
| `missing_actions` | 当前环境缺什么，以及下一步命令 |

严格检查 MuJoCo：

```bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --strict-mujoco
```

## 4. 参数以后在哪里改

### 改仿真外观、质量、阻尼、actuator

改：

```text
rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml
```

优先改这些：

| 内容 | MJCF 位置 |
|---|---|
| 关节范围 | `<joint range="min max">` |
| 阻尼 | `<joint damping="...">` |
| 连杆质量 | `<geom mass="...">` |
| 连杆粗细/长度 | `<geom size="...">`、`fromto="..."` |
| 位置控制强度 | `<actuator><position kp="..." kv="...">` |
| 可视颜色 | `<material>` 或 `<geom material="...">` |

### 改 ROS backend 限位夹紧

改：

```text
rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_backend.py
```

重点是：

```text
MEDICAL_ARM_6DOF_LIMITS
```

这里的限位用于 ROS 输入目标夹紧。MJCF 的 `<joint range>` 和这里要保持一致。

### 改电机/传动/标定草案

改：

```text
rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_schema.yaml
```

当前已知：

- 3 号：`jian_hengxiang_joint`，同步轮电机端 1、输出轴 2，先记 `motor_to_joint_ratio=0.5`。
- 4 号：`jian_zongxiang_joint`，齿轮比未知，后续标定。
- 5 号：`zhou_zongxiang_joint`。
- 6 号：正式 `jian_xuanzhuan_joint`。
- 7 号：EL05 外部调试电机，只能临时代替 6 号做 shadow。
- 1/2 号：腕部 4015 小电机，哪个对应哪个腕部 joint 还未确认。

### 改未接电机的仿真保持位

改：

```text
rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py
```

重点是：

```text
placeholder_positions_json
```

例如想让肘关节在 hardware shadow 时保持 `0.5 rad`：

```text
"zhou_zongxiang_joint":0.5
```

这只影响 MuJoCo shadow 的占位姿态，不代表真实电机在线。

## 5. 接 NanoPi 时只做 hardware shadow

NanoPi：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false \
  -p log_heartbeat:=false
```

仿真主机：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash

ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_hardware_shadow.launch.py
```

验证：

```bash
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
ros2 topic echo --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory
ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState
```

当前通过标准：

```text
/joint_states:
  forearm_rotation_joint = 7号当前位置

/sim/medical_arm/joint_trajectory:
  6 个 medical arm joint
  jian_xuanzhuan_joint = forearm_rotation_joint
  其他 joint = placeholder_positions_json

/sim/medical_arm/joint_states:
  6 个 medical arm joint
```

## 6. 后续补真实关节的顺序

1. 先让某个真实电机在 NanoPi `/joint_states` 出现稳定 fresh 输出端关节状态。
2. 确认这个状态是输出轴 joint，不是电机轴原始位置。
3. 在 `medical_arm_6dof_schema.yaml` 填方向、零点、传动比和 calibrated 状态。
4. 在 `medical_arm_6dof_hardware_shadow.launch.py` 的 `joint_map_json` 增加 source->target 映射。
5. 保持 `enable_target_tx=false`，只看 MuJoCo shadow 是否跟随。
6. 单独做限位、速度、急停和 M33 安全门验证后，才讨论正式真机运动。

## 7. 不要做的事

- 不要把 7 号写进 formal medical arm mapping。
- 不要把 `/sim/medical_arm/joint_trajectory` 直接接到 NanoPi 真机执行。
- 不要把旧 `demo_trajectory_node.py` 当 6DOF planner。
- 不要为了看到动画而关闭 fresh feedback 或 M33 safety gate。
- 不要让 VLA 输出 CAN frame、电机电流、电机力矩或限位覆盖命令。
