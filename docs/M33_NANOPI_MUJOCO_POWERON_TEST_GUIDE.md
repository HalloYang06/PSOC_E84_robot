# M33-NanoPi-MuJoCo 上电启动与测试教程

本文用于你后续从上电开始，按顺序验证：

```text
电机/传感反馈 -> M33 -> NanoPi -> 无线 ROS2 -> Linux 仿真主机 -> MuJoCo 6DOF shadow
```

当前结论先写清楚：

- M33 对上的是 legacy 5 槽位链路：`0x330~0x334` 对应 ROS joint `0..4`，当前应映射到 motor slot `3/4/5/6/7`。
- 已实测对上的是 7 号 EL05 外部调试电机：M33 `0x334` fresh，NanoPi `/joint_states` 发布 `forearm_rotation_joint`，仿真主机 relay 映射到 6DOF MuJoCo `jian_xuanzhuan_joint`。
- medical_arm 6DOF 正式关节还没有全部接到 M33：`jian_hengxiang_joint`、`jian_zongxiang_joint`、`zhou_zongxiang_joint`、两个腕部关节目前在 hardware shadow 中还是占位角。
- 7 号不在机械臂上，只能做 `bench-debug + shadow-sim`，不能写进正式医疗臂映射。

## 0. 设备、路径和安全边界

| 设备 | 地址/路径 | 作用 |
|---|---|---|
| NanoPi | `pi@192.168.2.66` | SocketCAN、M33/CAN 读取、ROS2 bridge |
| Linux 仿真主机 | `cal@192.168.2.46` | ROS2、MuJoCo、可视化、shadow relay |
| 仿真主机 ROS2 repo | `/home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws` | 当前主线 ROS2 工作区 |
| standalone MuJoCo viewer | `/home/cal/medical_arm_mujoco/open_medical_arm_6dof_shadow.sh` | 只看模型可视化 |

安全边界：

- 前 7 步全部保持 `enable_target_tx=false`，不向 M33 发送真实 `0x320` 目标。
- 只允许 7 号外部电机做小幅台架测试；机械臂本体未完成标定前不要发真实运动。
- 人不要穿戴设备做本教程。
- 每次测试后都执行停止和关闭 active-report。

## 1. 上电顺序

建议顺序：

1. 确认机械臂本体不会被本轮命令驱动；只保留你要看的外部 7 号电机。
2. 给 M33、CAN 收发器、电机驱动供电。
3. 给 NanoPi 上电，等待系统启动。
4. 给 Linux 仿真主机上电，确认和 NanoPi 在同一 ROS2 网络。
5. 准备急停/断电手段。

不要一上电就发目标位置。先做只读检查。

## 2. NanoPi CAN 和 M33 在线检查

登录 NanoPi：

```bash
ssh pi@192.168.2.66
```

检查 CAN 状态：

```bash
ip -details -statistics link show can0
```

通过标准：

```text
state ERROR-ACTIVE
bitrate 1000000
berr-counter tx 0 rx 0
```

被动抓 3 秒：

```bash
timeout 3 candump -L can0
```

如果总线在线，通常会看到 M33 周期状态：

```text
0x330
0x331
0x332
0x333
0x334
```

发送一次 M33 heartbeat，只验证在线，不控制电机：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 20 --wait 1
```

通过标准：

```text
TX STD 0x321 [...]
RX STD 0x322 [...]
```

如果没有 `0x322` 或 CAN 变成 `BUS-OFF`，停止，不进入后续步骤。先查电池、M33 供电、共地、CANH/CANL、终端电阻和收发器使能。

## 3. M33 遥测槽位对齐检查

只读抓 M33 状态：

```bash
timeout 3 candump -L can0,330:7FF,331:7FF,332:7FF,333:7FF,334:7FF,320:7FF
```

通过标准：

- 能看到 `0x330~0x334`。
- 抓包里不能出现 `0x320`，因为这是只读检查。
- payload byte0 应是 `B3`。
- payload byte2 应按当前 M33 槽位显示：

```text
0x330 -> motor 3
0x331 -> motor 4
0x332 -> motor 5
0x333 -> motor 6
0x334 -> motor 7
```

如果 byte3 带 `0x10`，表示 stale：M33 槽位在线，但还没有新鲜电机反馈。stale 时不要期待 NanoPi 发布 `/joint_states`。

## 4. 7 号 EL05 遥测打开

当前已验证的硬件 shadow 只依赖 7 号外部电机。先发 stop/clear-fault，再打开 active-report：

```bash
python3 /home/pi/nanopi_can_master.py private stop --iface can0 --motor 7 --clear-fault --wait 0.1
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --enable-report --wait 0.5
timeout 2 candump -L can0,180007FD:1FFFFFFF,188007FD:1FFFFFFF,334:7FF
```

通过标准：

```text
能看到 0x180007FD
能看到 0x334
0x334 byte2 = 07
0x334 byte3 不再是 stale 0x10，或至少能看到 fresh 样本
```

如果只看到 stale `0x334`，说明 M33 有槽位但没有 7 号新鲜反馈，先不要启动 ROS shadow。

## 5. NanoPi 只读 ROS2 bridge

仍在 NanoPi，启动 bridge。注意必须是 `enable_target_tx=false`：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false \
  -p log_heartbeat:=false
```

另开一个 NanoPi 终端验证：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
```

当前 7 号在线时，`/joint_states` 应类似：

```text
name:
- forearm_rotation_joint
position:
- 0.049
```

如果 `/rehab_arm/motor_state` 有数据但 `/joint_states` 没有，通常是 fresh feedback gate 没过。回到第 3/4 步看 `0x334` 是否 stale。

## 6. 仿真主机环境检查

登录仿真主机：

```bash
ssh cal@192.168.2.46
```

构建并检查：

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
./build_ros2.sh --packages-select rehab_arm_description rehab_arm_sim_mujoco rehab_arm_psoc_bridge
source install/setup.bash

ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --strict-mujoco
```

重点看：

```text
readiness = ready_with_mujoco
medical_arm_6dof_contract.count = 6
medical_arm_6dof_topic_contract.hardware_shadow_current_mapping:
  forearm_rotation_joint -> jian_xuanzhuan_joint
```

如果只想打开 standalone MuJoCo viewer：

```bash
cd /home/cal/medical_arm_mujoco
./open_medical_arm_6dof_shadow.sh
```

这个 viewer 只看模型，不接 NanoPi。

## 7. 单机 MuJoCo 6DOF shadow

这一步不需要 NanoPi，用来确认仿真本身能跑。

仿真主机终端 1：

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_shadow.launch.py
```

仿真主机终端 2：

```bash
source /opt/ros/jazzy/setup.bash
source /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash

ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState
```

发布一个仿真目标：

```bash
ros2 topic pub --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory \
  "{joint_names: ['jian_hengxiang_joint','jian_zongxiang_joint','jian_xuanzhuan_joint','zhou_zongxiang_joint','wanbu_zongxiang_joint','wanbu_hengxiang_joint'], points: [{positions: [0.1, 0.2, 0.1, 0.4, 0.1, 0.05], time_from_start: {sec: 1, nanosec: 0}}]}"
```

通过标准：

- `/sim/medical_arm/joint_states` 包含 6 个 joint。
- 不依赖 NanoPi。
- 不发 CAN。

## 8. NanoPi 到 MuJoCo hardware shadow

前提：

- 第 4 步 7 号 `0x334` fresh。
- 第 5 步 NanoPi `/joint_states` 有 `forearm_rotation_joint`。
- NanoPi bridge 仍然 `enable_target_tx=false`。

仿真主机启动 hardware shadow：

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source install/setup.bash

ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_hardware_shadow.launch.py
```

另开仿真主机终端验证：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash

ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
ros2 topic echo --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory
ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState
```

当前通过标准：

```text
/joint_states:
  forearm_rotation_joint = 7号当前位置

/sim/medical_arm/joint_trajectory:
  joint_names 有 6 个 medical arm joint
  positions 第 3 个 jian_xuanzhuan_joint = forearm_rotation_joint
  其他 5 个 = placeholder_positions_json

/sim/medical_arm/joint_states:
  6 个 medical arm joint
  jian_xuanzhuan_joint 跟随 7号
```

当前实测样例：

```text
/joint_states forearm_rotation_joint = 0.049
/sim/medical_arm/joint_trajectory positions = [0.0, 0.0, 0.049, 0.0, 0.0, 0.0]
```

## 9. 可选：7 号小幅 M33 正规路径台架测试

只有满足以下条件才做：

- 只接外部 7 号电机。
- 没有人穿戴设备。
- 7 号不会带动机械臂本体。
- 你能随时断电。

7 号在 M33 legacy 槽位里是 ROS joint `4`，不是 joint `7`。

```bash
python3 /home/pi/nanopi_can_master.py m33 active-report --iface can0 --joint 4 --enable-report --wait 0.1
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 2 --rpm 1 --torque-ma 0 --wait 0
sleep 1.2
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg -2 --rpm 1 --torque-ma 0 --wait 0
sleep 1.2
python3 /home/pi/nanopi_can_master.py m33 stop --iface can0 --joint 4 --clear-fault --wait 0.1
```

同时抓包：

```bash
timeout 8 candump -L can0,320:7FF,334:7FF,180007FD:1FFFFFFF,188007FD:1FFFFFFF
```

通过标准：

- 能看到 `0x320` 只在这一步出现。
- `0x334` 位置发生小幅变化。
- MuJoCo hardware shadow 的 `jian_xuanzhuan_joint` 跟随变化。

这一步不是医疗臂正式 6DOF 运动验收，只是 7 号外部电机台架链路验收。

## 10. 停止和清理

NanoPi：

```bash
pkill -f psoc_can_bridge_node.py || true
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --wait 0.1
python3 /home/pi/nanopi_can_master.py private stop --iface can0 --motor 7 --clear-fault --wait 0.1
ip -details -statistics link show can0 | sed -n '1,4p'
```

仿真主机：

```bash
pkill -f medical_arm_6dof_hardware_shadow.launch.py || true
pkill -f medical_arm_shadow_relay_node.py || true
pkill -f mujoco_sim_node.py || true
pgrep -af 'medical_arm_6dof_shadow_sim|medical_arm_shadow_relay|mujoco_sim_node.py|medical_arm_shadow_relay_node.py' || true
```

通过标准：

- NanoPi 没有 `psoc_can_bridge_node.py` 残留。
- 仿真主机没有 MuJoCo/relay 残留。
- 7 号 active-report 已关闭。
- `can0` 仍为 `ERROR-ACTIVE`，错误计数没有持续增长。

## 11. 出问题时先看哪里

| 现象 | 先看 |
|---|---|
| `candump` 完全没帧 | 电池、M33 供电、CANH/CANL、共地、终端电阻、收发器使能 |
| 有 `0x330~0x334` 但没有 `/joint_states` | `0x334` 是否 stale；fresh feedback gate 是否通过 |
| 仿真主机看不到 NanoPi `/joint_states` | 两端是否都 `source ~/.rehab_arm_ros2_network`；ROS_DOMAIN_ID 是否一致；无线网络是否互通 |
| `/sim/medical_arm/joint_trajectory` 只有一个 joint | relay 不是最新版本，或 `publish_full_target=false` |
| MuJoCo 6DOF joint 不动 | 查 `/sim/medical_arm/joint_trajectory` 是否有目标；joint 名是否完全一致 |
| 出现意外 `0x320` | 立即停止，确认是不是进入了第 9 步；普通只读/shadow 阶段不允许出现 |

## 12. 后续补正式 6DOF 的顺序

1. 先把真实 1/2/3/4/5/6 电机反馈接入 M33，并证明对应 `0x330~0x334` 或后续 6DOF 新状态槽位 fresh。
2. NanoPi bridge 发布输出端 joint state，不发布电机轴原始角度。
3. 在 `medical_arm_6dof_schema.yaml` 补方向、零点、传动比、`calibrated=true`。
4. 在 `medical_arm_6dof_hardware_shadow.launch.py` 补 `joint_map_json`。
5. 先只看 MuJoCo shadow 跟随。
6. M33 安全状态机、限位、速度、电流、急停全部通过后，再讨论 `enable_target_tx=true`。
