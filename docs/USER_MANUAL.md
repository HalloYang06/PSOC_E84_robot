# 康复外骨骼机械臂使用手册

本文档记录当前系统怎么用、怎么验证、哪些命令安全。每完成一个新功能或测试流程，都要同步更新本手册。

## 当前安全边界

- 正式运动链路：`JointTrajectory -> NanoPi -> M33 -> 电机`。
- NanoPi 直发 CANSimple/私有扩展帧只用于调试，不进入正式 bringup。
- 当前不要发布真实运动轨迹到 `rehab_arm_psoc_bridge`，除非 M33 heartbeat/status 链路已经确认。
- App 实时近端控制走 BLE 到英飞凌；HTTP 到 NanoPi/OpenClaw 只做高层 AI、报告和远程服务。
- 旧规划 CAN ID 不作为当前依据。

## 1. NanoPi ROS2 工作区

NanoPi 上当前工作区：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

本仓库对应工作区：

```text
rehab_arm_ros2_ws/
```

## 2. 仿真节点使用

构建：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select rehab_arm_sim_mujoco
source install/setup.bash
```

启动：

```bash
ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py
```

验证 topic：

```bash
ros2 topic list | grep -E "joint_states|rehab_arm"
ros2 topic echo --once /joint_states
```

通过标准：

- 能看到 `/joint_states`。
- 能看到 `/rehab_arm/safety_state`。
- 能看到 `/rehab_arm/sensor_state`。
- `/joint_states` 包含 5 个关节：`shoulder_lift_joint`、`elbow_lift_joint`、`shoulder_abduction_joint`、`upper_arm_rotation_joint`、`forearm_rotation_joint`。

短时冒烟测试：

```bash
timeout 4 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py
```

不应该出现 Python traceback。

## 3. Demo 轨迹使用

先启动仿真节点。另开终端：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_control demo_trajectory_node.py
```

观察：

```bash
ros2 topic echo /joint_states
```

通过标准：

- demo 节点日志出现 `Published multi-joint demo JointTrajectory`。
- `/joint_states.position` 不再全是 0。
- 关节位置随轨迹平滑变化。

## 4. PSoC Bridge 非运动测试

当前只允许做 heartbeat/启动验证，不发布真实轨迹。

构建：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select rehab_arm_psoc_bridge
source install/setup.bash
```

检查 CAN：

```bash
ip -details -statistics link show can0
```

当前期望：

```text
can0 UP
state ERROR-ACTIVE
bitrate 1000000
```

启动 bridge，打开 heartbeat 日志：

```bash
timeout 4 ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p log_heartbeat:=true
```

当前已知现象：

- 应用层能打印 `TX 321 01`，说明节点尝试发送 NanoPi heartbeat。
- 但还没有看到 M33 `0x322` 回复。
- 如果 `TX packets` 不增加而 `TX dropped/errors` 增加，说明总线层 ACK 未成功。
- bridge 会在没有收到 PSoC status 时发布 limited safety 状态：

```bash
ros2 topic echo --once /rehab_arm/safety_state
```

当前 M33 未回复时的示例：

```json
{"state":"limited","detail":"no PSoC status after 4 heartbeats","source":"psoc_bridge"}
```

下一步验证：

```bash
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
candump can0
ip -details -statistics link show can0
```

只有看到 `0x322` 回复，或 TX packets 正常增长后，才继续 bridge 状态解析和轨迹下发。

如果没有 `0x322`：

- 先检查电池电量。已出现过因电池没电导致 NanoPi 能打印 `TX 321`，但 PSoC/M33 不 ACK、不回复 `0x322` 的情况。
- 不要发布真实 `JointTrajectory` 到 bridge。
- 检查 PSoC/M33 是否上电。
- 检查 CANH/CANL、共地、终端电阻。
- 检查 M33 固件是否实现 `0x321 -> 0x322`。
- 检查 PSoC CAN 波特率是否为 1Mbps。

电池充电或更换后，按下面顺序复测：

```bash
ip -details -statistics link show can0
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
```

通过标准：

- `can0` 仍为 `UP`、`ERROR-ACTIVE`、1Mbps。
- 能收到 M33 `0x322` 状态回复，或至少看到 TX packets 正常增长且不再持续 dropped/errors。
- 通过前不要让 bridge 接收真实运动轨迹。

## 5. 当前真实 CAN ID

| ID | 协议/用途 | 说明 |
|---|---|---|
| `node_id=3` | CANSimple/ODrive 类协议 | heartbeat 标准帧 `0x061` |
| `motor_id=4/5/6/7` | 私有扩展帧 MIT 电机协议 | 当前只允许调试使用，机械关节绑定待确认 |
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | M33 状态回复 |
| `0x7C2` | C8T6 -> M33 | 传感数据 |
| `0x7C3` | C8T6 -> M33 | 健康状态 |

## 6. 文档与 Git 维护

每次完成任务后同步更新：

- [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)：记录进度、验证、失败、下一步。
- [TROUBLESHOOTING_AND_LESSONS.md](TROUBLESHOOTING_AND_LESSONS.md)：记录踩坑、根因、技巧。
- [USER_MANUAL.md](USER_MANUAL.md)：记录新增使用方式、命令、验证标准。

每次完成一个可测试任务后：

```bash
git status
git add <本次相关文件>
git commit -m "<简短说明>"
git push origin feature/rehab-arm-ros2-architecture
```

不要提交与本次任务无关的用户改动。
