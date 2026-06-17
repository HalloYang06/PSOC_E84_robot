# MuJoCo 动电机指南

这份文档只讲仿真，不讲真机电机。

结论先说清楚：

- 我现在不是用 MuJoCo 控真机电机。
- MuJoCo 只负责仿真和 shadow 观察。
- 真机电机仍然走 `M33 -> CAN -> motor`。

## 1. 先确认仿真在跑

在 Linux 仿真主机上：

```bash
systemctl is-active rehab-arm-sim-host-shadow.service
```

如果没起来，启动脚本是：

```bash
/usr/local/bin/start_sim_host_medical_arm_shadow.sh
```

## 2. 加载 ROS 环境

```bash
source /opt/ros/jazzy/setup.bash
source /home/cal/.rehab_arm_ros2_network
source /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash
```

注意：

- 当前 ROS 域一般要用 `ROS_DOMAIN_ID=42`。
- 不带域号，常常会看起来像“节点没起来”。

## 3. 看 MuJoCo 的输入输出

MuJoCo shadow 的话题：

- 输入：`/sim/medical_arm/joint_trajectory`
- 输出：`/sim/medical_arm/joint_states`

先看当前输出：

```bash
ros2 topic echo --once /sim/medical_arm/joint_states
```

## 4. 发一个最小动作

单关节小动作示例：

```bash
ros2 topic pub --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory "{
  joint_names: ['jian_hengxiang_joint'],
  points: [{
    positions: [0.15],
    time_from_start: {sec: 2, nanosec: 0}
  }]
}"
```

这会让仿真里的 `jian_hengxiang_joint` 走到 0.15 rad。

如果当前硬件 shadow 服务也在跑，`medical_arm_shadow_relay_node.py` 会持续把真实
`/joint_states` 转发到 `/sim/medical_arm/joint_trajectory`。这时手动发布到同一个
topic 可能被覆盖。只想单独验证 MuJoCo 动作时，可以开一组临时 topic：

```bash
ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py --ros-args \
  -r __node:=codex_mujoco_test_sim \
  -p joint_profile:=medical_arm_6dof \
  -p joint_state_topic:=/codex_mujoco_test/joint_states \
  -p trajectory_topic:=/codex_mujoco_test/joint_trajectory \
  -p safety_state_topic:=/codex_mujoco_test/safety_state \
  -p sensor_state_topic:=/codex_mujoco_test/sensor_state
```

另开一个终端发布：

```bash
ros2 topic pub --once /codex_mujoco_test/joint_trajectory trajectory_msgs/msg/JointTrajectory "{
  joint_names: ['jian_hengxiang_joint'],
  points: [{
    positions: [0.2],
    time_from_start: {sec: 1, nanosec: 0}
  }]
}"
```

读回：

```bash
ros2 topic echo --once /codex_mujoco_test/joint_states
```

2026-06-17 已远程实测：`/codex_mujoco_test/joint_states` 从 `0.0` 变到 `0.2`，
再发 `0.0` 后回到 `0.0`。日志显示 `backend=mujoco-model`。

## 5. 看结果

再读一次：

```bash
ros2 topic echo --once /sim/medical_arm/joint_states
```

如果 `position` 变了，说明 MuJoCo 动起来了。

## 6. 回零

```bash
ros2 topic pub --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory "{
  joint_names: ['jian_hengxiang_joint'],
  points: [{
    positions: [0.0],
    time_from_start: {sec: 2, nanosec: 0}
  }]
}"
```

## 7. 多关节一起动

```bash
ros2 topic pub --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory "{
  joint_names: ['jian_hengxiang_joint','jian_zongxiang_joint','jian_xuanzhuan_joint','zhou_zongxiang_joint','wanbu_zongxiang_joint','wanbu_hengxiang_joint'],
  points: [{
    positions: [0.1, 0.2, 0.1, 0.4, 0.1, 0.05],
    time_from_start: {sec: 2, nanosec: 0}
  }]
}"
```

## 8. 未标定时先试路径规划

未标定时，不要把路径规划理解成“末端到达某个真实空间点”。可以先做
MuJoCo-only 的小幅关节空间轨迹，验证 planner、轨迹格式、限位检查和可视化。

推荐用隔离 topic，避免碰到真机 bridge 或 hardware shadow relay：

```bash
ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py --ros-args \
  -r __node:=codex_path_test_sim \
  -p joint_profile:=medical_arm_6dof \
  -p joint_state_topic:=/codex_path_test/joint_states \
  -p trajectory_topic:=/codex_path_test/joint_trajectory \
  -p safety_state_topic:=/codex_path_test/safety_state \
  -p sensor_state_topic:=/codex_path_test/sensor_state
```

发布一条 6DOF 小幅多点路径：

```bash
ros2 topic pub --once /codex_path_test/joint_trajectory trajectory_msgs/msg/JointTrajectory "{
  joint_names: [
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint'
  ],
  points: [
    {
      positions: [0.05, 0.08, 0.03, 0.10, 0.02, 0.02],
      time_from_start: {sec: 1, nanosec: 0}
    },
    {
      positions: [0.10, 0.12, 0.05, 0.16, 0.03, -0.02],
      time_from_start: {sec: 3, nanosec: 0}
    },
    {
      positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      time_from_start: {sec: 5, nanosec: 0}
    }
  ]
}"
```

读回状态：

```bash
ros2 topic echo --once /codex_path_test/joint_states
```

2026-06-17 已远程实测：该路径在 `backend=mujoco-model` 下执行，中途读回约
`[0.09, 0.112, 0.046, 0.148, 0.028, -0.012]`，随后回到全零。

## 9. 关闭仿真

```bash
pkill -f medical_arm_6dof_hardware_shadow.launch.py || true
pkill -f medical_arm_6dof_shadow.launch.py || true
pkill -f medical_arm_shadow_relay_node.py || true
pkill -f mujoco_sim_node.py || true
```

注意：不要用上面的 `pkill` 去收生产 shadow 服务，除非你明确要停硬件 shadow。
临时纯仿真测试时，只关自己的临时节点即可。

## 10. 真机和 MuJoCo 的区别

- MuJoCo：发 `JointTrajectory`，只影响仿真。
- 真机：发 M33 / CAN 命令，才会动电机。
- 如果你只是想看姿态变化，用 MuJoCo。
- 如果你想动真实电机，先走 M33 安全门，不要直接拿 MuJoCo 当真机控制器。
