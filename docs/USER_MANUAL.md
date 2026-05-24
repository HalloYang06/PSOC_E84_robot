# 康复外骨骼机械臂使用手册

本文档记录当前系统怎么用、怎么验证、哪些命令安全。每完成一个新功能或测试流程，都要同步更新本手册。

## 当前安全边界

- 这是穿戴在人身上的康复外骨骼设备；任何命令、算法或调试动作都必须以人身安全为最高优先级。
- 安全状态不明确时默认不动：不要用“可能没事”作为继续测试的理由。
- 正式运动链路：`JointTrajectory -> NanoPi -> M33 -> 电机`。
- M33 是最终安全责任方，必须负责限位、限速、急停、掉线保护、供电异常处理和电机故障处理。
- NanoPi 直发 CANSimple/私有扩展帧只用于调试，不进入正式 bringup。
- 当前不要发布真实运动轨迹到 `rehab_arm_psoc_bridge`，除非 M33 heartbeat/status 链路已经确认。
- `/rehab_arm/safety_state` 不是 `ok` 时，不要发布真实运动轨迹。
- 人穿戴设备时，禁止使用 `nanopi_can_master.py` 直控电机。
- App 实时近端控制走 BLE 到英飞凌；HTTP 到 NanoPi/OpenClaw 只做高层 AI、报告和远程服务。
- 旧规划 CAN ID 不作为当前依据。

## 真机测试前安全检查

每次真机测试前，先确认：

- 电池电量充足，PSoC/M33、CAN 收发器、电机侧节点供电稳定。
- 硬件急停可触发，触发后电机不会继续输出。
- 机械限位、软件限位、关节方向、关节 ID 映射已经确认。
- `can0` 为 `UP`、`ERROR-ACTIVE`、1Mbps，无持续 error-passive 或 bus-off。
- 能收到 M33 `0x322` heartbeat/status。
- `/rehab_arm/safety_state` 为 `ok`。
- 本次轨迹已经在仿真中跑过，并且没有超限、突变或方向错误。
- 现场有人能立即断电或按下急停。

任一项不满足，都只允许做不运动诊断，不允许让设备带人运动。

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

已验证通过的示例：

```text
TX STD 0x00000321 [1] 01
RX STD 0x00000322 [8] A5 01 07 00 48 EA 6D 00
```

ROS bridge 非运动验证：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p log_heartbeat:=true
```

另开终端查看：

```bash
ros2 topic echo --once /rehab_arm/safety_state
```

已验证通过的示例：

```json
{"state":"ok","source":"psoc","id_hex":"0x322","data":"A504070079F86E00","marker":165,"seq":4,"motors":7,"error_code":0}
```

注意：这个验证只说明 heartbeat/status 链路已经通，不等于允许直接带人运动。真实轨迹下发还需要确认 `0x320` payload、关节映射、限幅策略和急停测试。

### 4.1 Bridge 轨迹安全门控

`rehab_arm_psoc_bridge` 现在默认启用轨迹安全门控：

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `require_psoc_ok_for_trajectory` | `true` | 只有收到新鲜的 M33 `0x322 ok` 才允许接收/发送轨迹 |
| `reject_out_of_limit_trajectory` | `true` | 轨迹点超出软件关节限位时拒绝轨迹 |
| `max_trajectory_points` | `100` | 限制一次轨迹消息的最大点数 |
| `status_timeout_sec` | `2.5` | 超过该时间未收到 PSoC status，认为状态过期 |
| `enable_target_tx` | `false` | 是否真的发送 `0x320` 目标帧；默认只 dry-run 打日志 |

安全行为：

- bridge 启动时先发布 `limited: bridge started, waiting for PSoC status`。
- 没有 M33 `0x322 ok` 时，收到 `/arm_controller/joint_trajectory` 会拒绝，不发 `0x320`。
- 正在发送轨迹时，如果 PSoC 状态过期或变成 fault，会清空剩余轨迹并停止发送。
- 轨迹含未知关节、空点、非有限数值、超限点或过多点时，会拒绝并发布 `limited`。
- 默认 `enable_target_tx=false` 时，合法轨迹也不会真的发 `0x320`，只打印 `DRY-RUN 320 ...`。
- bridge 只会为 `JointTrajectory.joint_names` 中明确出现的关节生成目标帧，不会自动给未命令关节补发目标。

已验证的无状态拒绝测试：

```text
safety limited: rejected trajectory: no PSoC status received
```

已验证的 PSoC 在线但轨迹超限拒绝测试：

```text
safety limited: trajectory point 0 joint shoulder_lift_joint 99.000 outside [-0.700, 1.400]
```

同时监听：

```bash
candump can0,320:7FF
```

通过标准：

- 拒绝轨迹时 `candump can0,320:7FF` 没有任何 `0x320` 帧。
- 这只验证软件门控，不代表可以做真实运动。

已验证的合法轨迹 dry-run 测试：

```text
safety ok: accepted 1 trajectory points
DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000
```

同时 `candump can0,320:7FF` 为空。这个测试说明：PSoC 在线、轨迹合法时，默认仍不会真正发送 `0x320`。

注意：电池低电量时可能再次没有 `0x322`。此时不要反复发布轨迹，先恢复供电。

下一阶段如果要测试合法 `0x320`，必须先满足：

- M33 固件能打印或记录收到的 `0x320` 关节号、目标角度、速度、扭矩/电流字段。
- M33 固件能打印限幅结果、拒绝原因和最终 safety state。
- 不接人，不允许电机执行实际运动，只对照 NanoPi CAN payload 和 M33 日志。
- 如需烧录 M33 固件，由用户执行烧录。
- 只有满足以上条件后，才允许临时设置 `-p enable_target_tx:=true` 做单帧日志对照测试。

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
