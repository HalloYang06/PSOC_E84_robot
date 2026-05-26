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

当前总体数据流图见：[system_data_flow.png](assets/system_data_flow.png)。

第一版数据上传约定：

- 全量电机、传感、安全、模型结果和 session 数据，优先由 NanoPi 汇总后上传总服务器。
- NanoPi 负责摄像头采集，第一版优先上传关键帧、压缩图、目标/遮挡物摘要和机器人状态。
- M55/英飞凌负责语音采集和板端小模型，语音文本、音频摘要、OpenClaw 或模型摘要可以上传服务器。
- VLA 固定走服务器链路，消费 NanoPi 摄像头数据、M55 语音数据、机器人状态、历史数据和标注。
- VLA 用于复杂任务理解和任务分解，例如“先移开遮挡物，再拿目标物品”；它只能输出高层任务或分段目标，不能直接发 CAN 或底层电机命令。

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

## 上电后最小非运动复测

设备重新上电后，先只做下面的非运动检查：

```bash
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details link show can0
```

通过标准：

- `can0` 是 `UP/LOWER_UP`。
- CAN 状态是 `ERROR-ACTIVE`。
- bitrate 是 `1000000`。
- `berr-counter tx 0 rx 0`。

然后只测 heartbeat：

```bash
# 只发 0x321 heartbeat，等待 M33 0x322；不要发 0x320
python3 - <<'PY'
import socket, struct, time, select
s=socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind(("can0",))
s.setblocking(False)
fmt="=IB3x8s"
for seq in range(1,4):
    s.send(struct.pack(fmt, 0x321, 1, bytes([seq]).ljust(8,b"\\x00")))
    print(f"TX 321 {seq:02x}")
    end=time.time()+0.5
    while time.time()<end:
        r,_,_=select.select([s],[],[],0.05)
        if r:
            can_id, dlc, payload=struct.unpack(fmt, s.recv(16))
            print(f"RX {can_id:03X} [{dlc}] {payload[:dlc].hex()}")
PY
```

看到 `RX 322 ...` 才说明 M33 heartbeat/status 链路恢复。

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

先做仿真环境自检：

```bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty
```

通过标准：

- 输出 `schema_version=rehab_arm_sim_env_check_v1`。
- `ok=true`。
- `readiness=ready_with_mujoco` 或 `readiness=ready_with_fallback_sim`。
- `joint_contract.count=5`。
- `checks.urdf.ok=true`。
- `checks.sim_data_collection_launch.ok=true`。
- `safety_note` 明确该命令不打开 CAN、不发 `0x320/0x321`、不命令 M33 或电机。

如果要强制确认真实 MuJoCo Python 包已安装，而不是使用 fallback 仿真：

```bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --strict-mujoco
```

`--strict-mujoco` 失败时，说明 ROS2 框架可能还能用 fallback 跑通数据链路，但这台 Linux 仿真机还没有准备好真实 MuJoCo 动力学仿真。

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

M33 日志固件参考：[M33_0X320_LOGGER_GUIDE.md](M33_0X320_LOGGER_GUIDE.md)。

### 4.2 `0x320` Payload 编码/解码工具

协议规格见：[PSOC_CAN_PROTOCOL_V1.md](PSOC_CAN_PROTOCOL_V1.md)。

生成 payload，不访问 CAN，不会让电机运动：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1
```

已验证输出：

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

只解码 payload，不访问 CAN，不会让电机运动：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000
```

已验证输出：

```text
can_id: 0x320
cmd: 0x03
joint_id: 0
joint_name: shoulder_lift_joint
deg_x10: 57
target_deg: 5.70000
target_rad: 0.09948
rpm: 5
torque_ma: 0
```

M33 侧日志固件应打印同等字段，用于和 NanoPi dry-run payload 对照。

### 4.3 `0x320` 单帧日志对照记录

前提：

- 电机驱动电源断开。
- 外骨骼不穿在人身上。
- M33 已烧录 logging-only 固件。
- M33 不把 `0x320` 连接到电机执行层。

NanoPi 已验证发出的单帧：

```text
TX 320 0300390005000000
can0  320   [8]  03 00 39 00 05 00 00 00
```

M33 串口应看到：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 joint_id=0 joint=shoulder_lift_joint deg_x10=57 target_deg=5.7 target_rad=0.09948 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output
safety_state=limited
```

如果 M33 没有打印 `RX 320`，先检查 M33 CAN filter 是否接收标准帧 `0x320`。

如果 M33 打印字段和 NanoPi 不一致，先停止测试，检查端序、DLC、字段偏移和单位。

当前已观察到的阻塞日志：

```text
[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22
```

这说明 M33 收到了 `cmd=3 joint=0`，但固件可能进入了 direct apply 控制应用路径。当前阶段不允许继续这样测试；必须先把 M33 固件改成 logging-only，不驱动、不 direct apply，只打印字段和安全拒绝原因。

当前本地 M33 工程已经完成 logging-only 补丁并编译通过：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33
```

关键安全开关：

```c
#define CONTROL_ROS_COMMAND_LOGGING_ONLY   1U
```

本地编译命令：

```powershell
cd D:\RT-ThreadStudio\workspace\yiliao_m33
$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path
mingw32-make -C Debug all -j2
```

编译产物：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.elf
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex
```

烧录后复测要求：

- 电机驱动仍然断开。
- 不穿戴在人身上。
- NanoPi 先只测 `0x321 -> 0x322` heartbeat/status。
- 再临时启动 bridge：`enable_target_tx:=true`。
- 只发布一次 `shoulder_lift_joint=0.1 rad` 的单关节轨迹。
- M33 串口必须看到 logging-only reject 日志，而不是 `ros cmd direct apply failed`。

烧录后已验证通过的记录：

```text
bridge: TX 320 0300390005000000
candump: can0  320   [8]  03 00 39 00 05 00 00 00
M33:
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output safety_state=limited
```

通过标准：

- NanoPi bridge、`candump`、M33 串口三处 payload 一致。
- M33 明确 `decision=reject`。
- 不出现 `ros cmd direct apply failed`。
- `can0` 复查仍为 `ERROR-ACTIVE`，没有 `error-passive` 或 `bus-off`。
- 本阶段仍不允许电机运动。

### 4.4 离线协议工具测试

没有硬件、不能上电时，也可以先跑 `0x320` 编码/解码和 `0x322` 状态解析工具回归测试：

```bash
cd D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan
python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v
```

通过标准：

- 17 个测试全部 `ok`。
- 覆盖合法编码、解码、负角度截断、超限拒绝、非有限数拒绝、未知关节拒绝、payload 长度错误和 unknown joint 可见性。
- 覆盖 `0x322` V1 legacy 兼容、V2 limited/logging-only、emergency_stop、error_code 强制 fault、坏 marker 和短帧。

NanoPi 上也可以跑 `0x322` 状态解析测试：

```bash
cd /home/pi/rehab_arm_ros2_ws
python3 -m unittest discover -s src/rehab_arm_psoc_bridge/test -v
```

### 4.5 `0x322` V2 状态解析

协议字段见：[PSOC_CAN_PROTOCOL_V1.md](PSOC_CAN_PROTOCOL_V1.md)。

当前 NanoPi bridge 已支持两种 `0x322`：

- V1 legacy：当前 M33 已验证格式，例如 `A5 03 07 00 A1 34 09 00`。
- V2 扩展：后续 M33 将 byte4..7 解释为 `safety_state/control_mode/detail_code/heartbeat_age_100ms`。
- V2 中 `detail_code/detail` 当前表示最近一次安全评估详情，不是会随普通 heartbeat 自动清零的实时 fault 字段。

V2 logging-only 示例：

```text
0x322 [8] A5 02 07 00 01 01 0A 03
```

解析后 ROS `/rehab_arm/safety_state` 应包含：

```json
{"protocol_version":2,"state":"limited","control_mode":"logging_only","detail":"logging_only_no_motor_output","detail_semantics":"last_safety_assessment","last_assessment_detail":"logging_only_no_motor_output","heartbeat_age_ms":300}
```

当前已验证：

- bridge 在旧 M33 V1 帧下仍兼容，`/rehab_arm/safety_state` 包含 `protocol_version:1`。
- 本阶段只验证 heartbeat/status，不需要发布 `JointTrajectory`，不需要发送 `0x320`。

当前本地 M33 工程已完成 V2 status 补丁并编译通过，等待用户烧录：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex
```

烧录后第一轮只测 heartbeat/status：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p log_heartbeat:=true
```

另开终端查看：

```bash
ros2 topic echo --once /rehab_arm/safety_state std_msgs/msg/String
```

通过标准：

- 不发布 `/arm_controller/joint_trajectory`。
- 不发送 `0x320`。
- `candump` 或 bridge 日志能看到 heartbeat/status 链路仍通。
- `/rehab_arm/safety_state` 包含：

```json
{"protocol_version":2,"state":"limited","control_mode":"logging_only","detail":"logging_only_no_motor_output"}
```

- `can0` 保持 `ERROR-ACTIVE`，没有 `bus-off` 或 `error-passive`。

烧录后已验证通过的 V2 status 记录：

```text
raw heartbeat:
TX 321 01
RX 322 [8] a501070001010a00

ROS /rehab_arm/safety_state:
{"source":"psoc","id_hex":"0x322","data":"A503070001010A00","marker":165,"seq":3,"motors":7,"error_code":0,"protocol_version":2,"state":"limited","safety_code":1,"control_mode":"logging_only","control_mode_code":1,"detail_code":10,"detail":"logging_only_no_motor_output","heartbeat_age_ms":0}
```

这表示 M33 当前明确告诉 NanoPi：系统在线，但处于 `logging_only` 安全受限状态。此状态下不要把它当成可运动状态。

App、服务器、VLA 和仿真主机读取 `/rehab_arm/safety_state` 时的优先级：

1. 先看 `motion_allowed`：`false` 时任何上层都不能请求真实运动。
2. 再看 `state`：只有 `ok` 才可能进入运动候选状态。
3. 再看 `control_mode`：只有后续明确实现的 `armed/active` 才可能对应真实运动控制。
4. 再看 `detail_semantics`：当前 `detail` 是 `last_safety_assessment`，用于解释最近一次拒绝或评估原因。
5. 不要只因为 `detail=none` 或 `detail=logging_only_no_motor_output` 就判断系统可运动。

当前阶段的期望是：

```json
{"motion_allowed":false}
```

如果本机或 NanoPi 上有旧 bridge 进程，先清理再测：

```bash
pgrep -af 'psoc_can_bridge_node|rehab_arm_psoc_bridge'
kill <pid>
```

如果 `ros2 topic echo` 启动太早提示不能判断类型，可以显式指定消息类型：

```bash
ros2 topic echo --once /rehab_arm/safety_state std_msgs/msg/String
```

### 4.6 M33 `0x320` 安全审核日志固件复测

当前 M33 本地工程已补充 `0x320` logging-only 安全审核日志，编译产物在：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex
```

当前最新版已经把原来的“日志里顺手判断”改成 M33 内部结构化安全评估：

- `ctrl_assess_ros_command_safety()` 负责判断 heartbeat、joint、position、rpm、torque。
- `control_ros_safety_assessment_t` 保存状态、裁决、拒绝原因和检查结果。
- `ctrl_log_ros_command_only()` 只打印安全评估结果。
- `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U` 时，最终仍强制 `no_motor_output`。

烧录前确认：

- `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`。
- 电机驱动电源断开。
- 外骨骼不穿在人身上。
- 只做 heartbeat/status 和单帧日志对照，不做运动测试。

烧录后第一步只测 V2 status：

```bash
python3 - <<'PY'
import socket, struct, time, select
s=socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind(("can0",))
s.setblocking(False)
fmt="=IB3x8s"
for seq in range(1,4):
    s.send(struct.pack(fmt, 0x321, 1, bytes([seq]).ljust(8,b"\\x00")))
    print(f"TX 321 {seq:02x}")
    end=time.time()+0.7
    while time.time()<end:
        r,_,_=select.select([s],[],[],0.05)
        if r:
            can_id, dlc, payload=struct.unpack(fmt, s.recv(16))
            print(f"RX {can_id:03X} [{dlc}] {payload[:dlc].hex()}")
            break
s.close()
PY
```

通过标准：

```text
RX 322 [8] a5<seq>070001010a00
```

这表示 M33 在线，但仍处于 `limited/logging_only`，不是可运动状态。

第二步只发一帧合法 `0x320` 对照：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p enable_target_tx:=true
```

另开终端：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory "{joint_names: [shoulder_lift_joint], points: [{positions: [0.1], time_from_start: {sec: 1, nanosec: 0}}]}"
```

M33 串口 `COM26`、`115200 baud`、DTR/RTS 关闭，应看到类似日志：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
safety_state=logging_only decision=reject reason=logging_only_no_motor_output
audit heartbeat_ok=1 heartbeat_age_ms=... heartbeat_timeout_ms=2500 joint_known=1 limit_01deg=[-401,802]
audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0
final action=no_motor_output logging_only=1
```

通过标准：

- NanoPi bridge 打印 `TX 320 0300390005000000`。
- `candump can0,320:7FF` 能看到同一 payload。
- M33 串口能看到 heartbeat、joint、limit、rpm、torque 审核字段。
- M33 最终仍 `decision=reject`。
- M33 最终仍 `final action=no_motor_output logging_only=1`。
- 不出现 `ros cmd direct apply failed`。
- `can0` 复查仍为 `ERROR-ACTIVE`，无 `error-passive` 或 `bus-off`。
- 本阶段仍不允许电机运动。

已验证通过的记录：

```text
raw heartbeat:
TX 321 01
RX 322 [8] a501070001010a00
TX 321 02
RX 322 [8] a502070001010a00
TX 321 03
RX 322 [8] a503070001010a00

bridge:
safety ok: accepted 1 trajectory points
TX 320 0300390005000000

candump:
can0  320   [8]  03 00 39 00 05 00 00 00

M33 COM26:
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
audit mode=logging_only heartbeat_ok=1 heartbeat_age_ms=141 heartbeat_timeout_ms=2500 joint_known=1 limit_01deg=[-401,802]
audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0
decision=reject reason=logging_only_no_motor_output final_reason=logging_only_no_motor_output safety_state=limited
```

注意：这次为了审计 logging-only 固件，bridge 临时使用了：

```bash
-p enable_target_tx:=true -p require_psoc_ok_for_trajectory:=false
```

原因是 M33 当前故意上报 `limited/logging_only`，默认 bridge 会拒绝轨迹。这个参数组合只能用于单帧审计，不允许作为正式运动配置。

安全状态机结构化固件烧录后已验证通过的新记录：

```text
raw heartbeat:
TX 321 01
RX 322 [8] a501070001010a00
TX 321 02
RX 322 [8] a502070001010a00
TX 321 03
RX 322 [8] a503070001010a00

bridge:
safety ok: accepted 1 trajectory points
TX 320 0300390005000000

candump:
can0  320   [8]  03 00 39 00 05 00 00 00

M33 COM26:
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
safety_state=logging_only decision=reject reason=logging_only_no_motor_output
audit heartbeat_ok=1 heartbeat_age_ms=141 heartbeat_timeout_ms=2500 joint_known=1 limit_01deg=[-401,802]
audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0
final action=no_motor_output logging_only=1
```

M33 状态机拒绝用例第一轮已验证：

| 用例 | `0x320` payload | 预期/实测 M33 reason |
|---|---|---|
| 超限 position | `0300840305000000` | `target_out_of_limit` |
| 未知 joint_id | `0309390005000000` | `unknown_joint` |
| 非零 torque/current | `0300390005000100` | `torque_out_of_limit` |
| heartbeat 超时 | 等待超过 2500ms 后发 `0300390005000000` | `heartbeat_timeout` |

每个用例最终都必须看到：

```text
decision=reject
final action=no_motor_output logging_only=1
```

注意：这些危险用例是为了验证 M33 自己的安全状态机，使用 raw SocketCAN 直接发 `0x320`，不会经过 ROS bridge 的前置限位。只能在电机驱动断开、外骨骼不穿戴、M33 logging-only 的条件下执行。

M33 状态机拒绝用例第二轮已验证：

| 用例 | `0x320` payload | 预期/实测 M33 reason |
|---|---|---|
| 速度超限 | `030039001f000000` | `velocity_out_of_limit` |
| unsupported command | `0100` | `unsupported_command` |
| heartbeat 超时 + 多个限位同时失败 | 等待超过 2500ms 后发 `030084031f000100` | `heartbeat_timeout` |

多错误优先级当前规则：

- heartbeat 超时优先级最高。
- heartbeat 正常时，再按 unknown joint、position、velocity、torque 等安全条件拒绝。
- 即使多个条件同时失败，也只输出一个首要 `reason`，其他检查项仍在 audit 字段中可见。

### 4.7 `0x322` detail_code 动态拒绝原因

当前 M33 detail_code 固件目标：

- M33 串口仍打印结构化状态机日志。
- M33 会把最近一次 ROS safety assessment 的首要拒绝原因放进下一次 `0x322` byte6。
- NanoPi ROS `/rehab_arm/safety_state` 可以看到具体 `detail`，不再只能看 COM26 串口。

当前 detail_code 映射：

| code | detail |
|---:|---|
| `1` | `heartbeat_timeout` |
| `2` | `unsupported_command` |
| `3` | `unknown_joint` |
| `4` | `target_out_of_limit` |
| `5` | `velocity_out_of_limit` |
| `6` | `torque_out_of_limit` |
| `10` | `logging_only_no_motor_output` |

烧录 M33 后的最小非运动验证：

1. 先只发 `0x321` heartbeat，初始应看到 `detail=logging_only_no_motor_output`。
2. raw SocketCAN 发一帧超限 `0x320`，例如 `0300840305000000`。
3. 再发 `0x321` heartbeat。
4. 新的 `0x322` 应该带 `byte6=04`，NanoPi ROS 应解析为 `detail=target_out_of_limit`。

通过标准：

- M33 串口 reason 是 `target_out_of_limit`。
- `candump` 看到 `0x322` byte6 为 `04`。
- `/rehab_arm/safety_state` JSON 里 `detail_code=4`，`detail=target_out_of_limit`。
- 仍然不出现任何电机输出，M33 仍处于 logging-only。

已验证通过的示例：

```text
TX heartbeat_71 321 [1] 71
RX 322 [8] a571070001010a00
PARSED detail_code=10 detail=logging_only_no_motor_output

TX target_out_of_limit 320 [8] 0300840305000000
TX heartbeat_72 321 [1] 72
RX 322 [8] a572070001010400
PARSED detail_code=4 detail=target_out_of_limit
```

对应 `candump`：

```text
can0  321   [1]  71
can0  322   [8]  A5 71 07 00 01 01 0A 00
can0  320   [8]  03 00 84 03 05 00 00 00
can0  321   [1]  72
can0  322   [8]  A5 72 07 00 01 01 04 00
```

M33 `COM26` 串口必须同时能看到：

```text
safety_state=limited decision=reject reason=target_out_of_limit
final action=no_motor_output logging_only=1
```

第二个抽样验证：`torque_out_of_limit`：

```text
TX heartbeat_81 321 [1] 81
RX 322 [8] a581070001010400
PARSED detail_code=4 detail=target_out_of_limit

TX torque_out_of_limit 320 [8] 0300390005000100
TX heartbeat_82 321 [1] 82
RX 322 [8] a582070001010600
PARSED detail_code=6 detail=torque_out_of_limit
```

这个结果说明：

- M33 会保留最近一次拒绝原因，直到下一次 ROS safety assessment 覆盖它。
- 新的 torque 超限帧被 M33 识别后，下一帧 `0x322` byte6 从 `04` 更新为 `06`。
- 这仍然只是安全审计链路验证，不代表可以让电机上电运动。

第三个抽样验证：`heartbeat_timeout`：

```text
TX heartbeat_91 321 [1] 91
RX 322 [8] a591070001010600
PARSED detail_code=6 detail=torque_out_of_limit

WAIT 3.2s to exceed M33 heartbeat timeout
TX after_timeout_normal_target 320 [8] 0300390005000000
TX heartbeat_92 321 [1] 92
RX 322 [8] a592070001010100
PARSED detail_code=1 detail=heartbeat_timeout
```

这个结果说明：

- M33 的 heartbeat 超时检查优先级高于普通目标命令审核。
- 超时后即使命令本身看起来在限位内，M33 也会拒绝，并把 `detail_code=1` 回传给 NanoPi。
- 验证时故意停止 heartbeat 超过 `2.5s`，测试结束后要重新确认 `can0` 仍为 `ERROR-ACTIVE` 且错误计数为 0。

如果烧录后没有任何 `0x322`：

- 先不要继续发 `0x320`。
- 检查 M33 是否已复位并运行应用。
- 检查 COM26 是否有启动日志或 shell 响应。
- 按 M33 reset 或给控制板断电重上电后，先只测 heartbeat。
- 仍不通时重新烧录最新 `rtthread.bin`：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
```

## 5. 数据记录

NanoPi 可以先记录安全和传感 topic，作为后续服务器同步、标注、仿真回放的数据源：

推荐用 launch 启动：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch rehab_arm_psoc_bridge data_collection.launch.py \
  output_dir:=/home/pi/rehab_arm_logs \
  session_id:=test_session \
  device_id:=nanopi-m5 \
  robot_id:=rehab-arm-alpha \
  software_version:=dev \
  mode:=logging_only \
  flush_every:=1
```

也可以直接启动节点：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge data_recorder_node.py \
  --ros-args \
  -p output_dir:=/home/pi/rehab_arm_logs \
  -p session_id:=test_session \
  -p device_id:=nanopi-m5 \
  -p robot_id:=rehab-arm-alpha \
  -p software_version:=dev \
  -p mode:=logging_only \
  -p flush_every:=1
```

记录文件：

```text
/home/pi/rehab_arm_logs/test_session.jsonl
```

如果不传 `session_id`，recorder 自动生成：

```text
<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl
```

每行是一条 JSON：

```json
{"record_type":"session_metadata","schema_version":"rehab_arm_jsonl_v1","ts_unix":123.0,"session_id":"test_session","device_id":"nanopi-m5","robot_id":"rehab-arm-alpha","software_version":"dev","recorder_version":"0.1.0","mode":"logging_only","source":"nanopi_ros_recorder","sync_status":"local_only","topics":["/joint_states","/rehab_arm/safety_state","/rehab_arm/sensor_state"],"motion_allowed_expected":false}
{"record_type":"topic_message","ts_unix":124.0,"topic":"/rehab_arm/safety_state","payload":{"state":"limited","motion_allowed":false}}
```

第一版只记录：

- `/joint_states`
- `/rehab_arm/safety_state`
- `/rehab_arm/sensor_state`

可选记录：

- `/rehab_arm/motor_state`
- `/rehab_arm/camera_keyframe`

当前阶段 `motion_allowed` 应保持 `false`，数据记录不代表允许真实运动。

`/joint_states` 记录示例：

```json
{"record_type":"topic_message","topic":"/joint_states","payload":{"stamp":{"sec":12,"nanosec":34},"name":["shoulder_lift_joint"],"position":[0.1],"velocity":[0.2],"effort":[0.3]}}
```

`/rehab_arm/motor_state` payload 示例：

```json
{"schema_version":"rehab_arm_motor_state_v1","robot_id":"rehab-arm-alpha","device_id":"nanopi-m5","source":"nanopi_ros","motors":[{"motor_id":4,"joint_name":"shoulder_lift_joint","protocol":"private_mit","position":0.1,"velocity":0.0,"current":0.3,"temperature":35.0,"fault":false}],"control_boundary":"telemetry_only_not_motor_command"}
```

仿真或离线测试时，可以把 `/joint_states` 转成 `/rehab_arm/motor_state`，供 recorder、总控台和后续标注链路先使用：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge joint_state_motor_state_node.py
```

另开终端发布一条假关节状态：

```bash
ros2 topic pub --once /joint_states sensor_msgs/msg/JointState \
  '{name: ["shoulder_lift_joint"], position: [0.1], velocity: [0.2], effort: [0.3]}'
```

查看输出：

```bash
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
```

通过标准：

- 输出 JSON 的 `schema_version` 是 `rehab_arm_motor_state_v1`。
- `motors[0].joint_name` 是 `shoulder_lift_joint`。
- `position/velocity/effort` 与 `/joint_states` 输入一致。
- `control_boundary` 是 `telemetry_only_not_motor_command`。

注意：这个节点只做遥测转换，不发 CAN，不控制电机。真实电机状态后续仍应来自 M33 上报。

如果已经用 `candump -tz can0` 保存了 CANSimple 原始日志，可以离线转换成统一的 `/rehab_arm/motor_state` JSONL，供总控台、标注、曲线分析和后续训练前检查使用：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge candump_motor_telemetry \
  /home/pi/rehab_arm_logs/can_captures/cansimple_node3_tiny_motion_20260525_195020.log \
  --output /home/pi/rehab_arm_logs/cansimple_node3_tiny_motion.jsonl \
  --device-id nanopi-m5 \
  --robot-id rehab-arm-alpha \
  --session-id cansimple_node3_tiny_motion \
  --pretty
```

当前转换器只解析 CANSimple/ODrive 类标准帧遥测：

- `0x061`：`node_id=3` heartbeat，用来补充 enabled、fault、axis_state、error_code。
- `0x069`：`node_id=3` encoder estimate，按 little-endian float 解码 position/velocity。
- position 从 turns 转成 rad，velocity 从 turns/s 转成 rad/s。

通过标准：

- 输出 summary 中 `ok=true`。
- `motor_state_count` 大于 0。
- JSONL 第一行是 `session_metadata`。
- 后续记录 topic 为 `/rehab_arm/motor_state`。
- payload 的 `schema_version` 是 `rehab_arm_motor_state_v1`。
- `control_boundary` 是 `telemetry_only_not_motor_command`。

注意：`candump_motor_telemetry` 是离线日志转换工具，不打开 SocketCAN，不发 CAN，不发送 `0x320/0x321`，不控制 M33 或电机。闭环刚建立后的 `0x069` 第一次跳变可能包含估计器恢复，不要直接等同于真实机械位移。

仿真数据采集一键启动：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch rehab_arm_bringup sim_data_collection.launch.py \
  output_dir:=/home/pi/rehab_arm_logs \
  session_id:=sim_session \
  device_id:=sim-workstation \
  robot_id:=rehab-arm-alpha \
  software_version:=dev \
  flush_every:=1
```

这个 launch 会启动：

- `rehab_arm_sim_mujoco/mujoco_sim_node.py`
- `rehab_arm_psoc_bridge/joint_state_motor_state_node.py`
- `rehab_arm_psoc_bridge/data_recorder_node.py`

检查记录结果：

```bash
ros2 run rehab_arm_psoc_bridge check_recording.py /home/pi/rehab_arm_logs/sim_session.jsonl
grep '/rehab_arm/motor_state' /home/pi/rehab_arm_logs/sim_session.jsonl | head
```

通过标准：

- checker 输出 `ok=true`。
- JSONL 包含 `/joint_states`。
- JSONL 包含 `/rehab_arm/safety_state`。
- JSONL 包含 `/rehab_arm/sensor_state`。
- JSONL 包含 `/rehab_arm/motor_state`。

如果用 `timeout ros2 launch ...` 做短验证后 SSH 卡住，先不要继续加压板子；等 SSH 恢复后清理可能残留的 launch 或节点进程，再复测。

当前已验证的短采集命令：

```bash
timeout -s INT 8s ros2 launch rehab_arm_bringup sim_data_collection.launch.py \
  output_dir:=/tmp/rehab_sim_collection \
  session_id:=sim_launch_clean \
  device_id:=nanopi-sim-smoke \
  software_version:=dev-smoke \
  flush_every:=1
```

已验证通过的结果：

- `check_recording.py` 返回 `ok=true`。
- `/rehab_arm/motor_state` 数量与 `/joint_states` 同步增长。
- `motor_state` 中 `motor_count=5`。
- launch 退出时不再出现 Python traceback。

采集一段 demo 运动轨迹：

```bash
timeout -s INT 12s ros2 launch rehab_arm_bringup sim_data_collection.launch.py \
  output_dir:=/tmp/rehab_sim_collection \
  session_id:=sim_demo_motion \
  device_id:=nanopi-sim-motion \
  software_version:=dev-motion \
  flush_every:=1 \
  enable_demo_trajectory:=true
```

通过标准：

- launch 日志出现 `Published multi-joint demo JointTrajectory`。
- `check_recording.py /tmp/rehab_sim_collection/sim_demo_motion.jsonl` 返回 `ok=true`。
- JSONL 中 5 个关节的 `position` 都有明显 min/max 变化。
- 这个流程只驱动仿真节点，不发 CAN，不发送 `0x320`。

生成 session 摘要：

```bash
ros2 run rehab_arm_psoc_bridge summarize_recording.py \
  /tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  --pretty
```

摘要会输出：

- `topic_counts`：每个 topic 的消息数。
- `topic_rates_hz`：按记录时间估算的 topic 频率。
- `joint_position_ranges`：每个关节的 min/max/span。
- `moving_joint_count`：span 大于 `0.01 rad` 的关节数。
- `motor_entry_count_min/max`：每条 motor_state 中的电机条目数量范围。
- `safety_states` 和 `motion_allowed_counts`。

通过标准：

- `schema_version` 是 `rehab_arm_recording_summary_v1`。
- 动态 demo session 中 `moving_joint_count` 应为 `5`。
- `topic_counts` 应包含 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。

离线数据质量门：

```bash
ros2 run rehab_arm_psoc_bridge validate_recording_quality.py \
  /tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  --min-joint-messages 100 \
  --min-moving-joints 5 \
  --require-motor-state \
  --min-motor-entry-count 5 \
  --pretty
```

通过标准：

- 输出 `schema_version=rehab_arm_recording_quality_v1`。
- `ok=true`。
- `errors=[]`。
- 当前 logging-only/仿真采集阶段不应出现 `motion_allowed=true`。

如果只是短时间 recorder 冒烟测试，可以降低阈值；如果是动态 demo 采集，应要求 `moving_joint_count=5` 和 `motor_entry_count_min>=5`。

导出 CSV：

```bash
ros2 run rehab_arm_psoc_bridge export_recording_csv.py \
  /tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  --output-dir /tmp/rehab_sim_collection/sim_demo_motion_csv
```

输出：

- `joint_states.csv`
- `motor_states.csv`

这些 CSV 只用于离线检查、画曲线、标注和模型训练前处理，不是控制命令。

对接字段说明见：[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)。

`/rehab_arm/camera_keyframe` payload 示例：

```json
{"schema_version":"rehab_arm_camera_keyframe_v1","robot_id":"rehab-arm-alpha","device_id":"nanopi-m5","source":"nanopi_camera","camera_id":"front_rgb","image_path":"/home/pi/frames/f1.jpg","image_format":"jpg","width":640,"height":480,"sha256":"abc123","scene_summary":"cup visible","detection_summary":{"objects":["cup"]},"control_boundary":"perception_data_only_not_motor_command"}
```

这两个 topic 只是总控台和标注链路的遥测/感知数据，不是运动命令。

摄像头关键帧采集：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run rehab_arm_psoc_bridge camera_keyframe_node.py \
  --ros-args \
  -p device:=/dev/video0 \
  -p output_dir:=/home/pi/rehab_arm_frames \
  -p camera_id:=front_rgb \
  -p robot_id:=rehab-arm-alpha \
  -p device_id:=nanopi-m5 \
  -p width:=640 \
  -p height:=480 \
  -p input_format:=mjpeg \
  -p publish_once:=true
```

通过标准：

- `/home/pi/rehab_arm_frames` 下生成 `.jpg` 文件。
- 节点发布 `/rehab_arm/camera_keyframe`。
- recorder 开启时，JSONL 中出现 `/rehab_arm/camera_keyframe`。

当前实测注意：

- 当前 NanoPi `lsusb` 只看到 USB root hub，没有看到 USB 摄像头。
- `/dev/video0` 当前报 `No such device`。
- `/dev/video22`/`/dev/video31` 是 Rockchip ISP 管线，ffmpeg 报 `Not a video capture device`。
- 重新插 USB/UVC 摄像头或更换深度摄像头后，先跑 `lsusb` 和 `v4l2-ctl --list-devices`。

检查 JSONL 文件是否包含基础数据：

```bash
ros2 run rehab_arm_psoc_bridge check_recording.py /home/pi/rehab_arm_logs/test_session.jsonl
```

通过时输出里应有：

```json
{"ok":true,"missing_topics":[]}
```

生成本地待同步清单：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --output /home/pi/rehab_arm_logs/manifest.json
```

这个清单只扫描本地文件，不上传服务器。`ok=false` 表示该 JSONL 缺少必需 topic 或 metadata，不适合进入标注/同步流程。

生成带 session 摘要的清单：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --include-summary \
  --output /home/pi/rehab_arm_logs/manifest_with_summary.json
```

带 summary 的 manifest 会在每个 session 里嵌入 `rehab_arm_recording_summary_v1`，方便总控台先显示 topic 数量、关节运动范围、motor_state 条目数和 safety 状态分布。默认不加 `--include-summary` 时仍保持旧格式。

预览服务器同步计划：

```bash
ros2 run rehab_arm_psoc_bridge sync_dry_run.py /home/pi/rehab_arm_logs/manifest_with_summary.json \
  --base-url http://server.example/api/rehab-arm/v1
```

通过标准：

- 输出 `schema_version=rehab_arm_sync_dry_run_v1`。
- 输出计划请求，不发真实 HTTP。
- `ok=false` 的 session 只出现在 `skipped_sessions`，不会生成文件上传请求。
- 如果输入的是 `manifest_with_summary.json`，`/sessions/manifest` 计划请求中应保留每个 session 的 `summary` 字段。

安全上传入口：

```bash
# 默认安全模式：只打印计划，不发 HTTP
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest_with_summary.json \
  --base-url http://server.example/api/rehab-arm/v1

# 只有确认服务器 endpoint 后才使用；会真实发 HTTP
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest_with_summary.json \
  --base-url http://server.example/api/rehab-arm/v1 \
  --execute
```

安全要求：

- 未确认服务器前不要加 `--execute`。
- 上传链路只同步数据，不进入 M33 控制闭环。
- 服务器同步失败不能影响本地急停、限位、heartbeat 或安全状态机。

本地假服务器验证：

```bash
ros2 run rehab_arm_psoc_bridge sync_test_server.py \
  --host 127.0.0.1 \
  --port 8765 \
  --storage-dir /tmp/rehab_arm_sync_server
```

另开终端执行：

```bash
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest.json \
  --base-url http://127.0.0.1:8765/api/rehab-arm/v1 \
  --execute
```

通过标准：

- `sync_upload.py` 输出 `schema_version=rehab_arm_sync_execute_result_v1` 和 `ok=true`。
- `/tmp/rehab_arm_sync_server/request_log.jsonl` 有 4 条 POST 记录。
- 第 3 条路径应为 `/api/rehab-arm/v1/sessions/<session_id>/files`，`content_type` 为 `multipart/form-data`。

带 summary manifest 的本地假服务器验证：

```bash
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest_with_summary.json \
  --base-url http://127.0.0.1:8765/api/rehab-arm/v1 \
  --execute
```

通过标准：

- 上传结果 `ok=true`。
- 假服务器收到 4 个 POST。
- 第 2 条 `/sessions/manifest` 的 JSON body 中保留 `summary.schema_version=rehab_arm_recording_summary_v1`。
- 动态 demo session 中 `summary.moving_joint_count=5`。

AI 合作平台云端接口：

```bash
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest.json \
  --base-url http://106.55.62.122:8011/api/rehab-arm/v1 \
  --execute
```

当前状态：

- 该云端接口已初步打通，只用于非实时数据上传。
- 云端工程在 `D:\ai合作产品`，不要搬到本仓库。
- 本仓库只保留 NanoPi 上传客户端和本地假服务器验证工具。
- 真机安全、急停、限位和 M33 控制不依赖云端。
- 推荐上传 `manifest_with_summary.json`。平台会把 summary 映射为通用设备数据质量索引，用于标注、导出和图表实验入口。
- 平台质量索引不是运动许可；即使平台显示数据质量通过，也不能绕过 M33 安全状态机。

带质量门报告的 manifest：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --include-summary \
  --include-quality-report \
  --min-joint-messages 50 \
  --min-moving-joints 5 \
  --require-motor-state \
  --min-motor-entry-count 5 \
  --output /home/pi/rehab_arm_logs/manifest_with_quality.json
```

通过标准：

- 每个有效 session 包含 `quality_report.schema_version=rehab_arm_recording_quality_v1`。
- `quality_report.ok=true` 时，平台可把该 session 作为可标注/可导出的数据资产。
- `quality_report.ok=false` 时，平台必须显示 blocking reason，不能把它当成合格训练数据。
- 质量报告仍然只是数据质量门，不是电机上电或运动许可。

上传到云端后检查质量门：

```bash
ros2 run rehab_arm_psoc_bridge sync_upload.py /home/pi/rehab_arm_logs/manifest_with_quality.json \
  --base-url http://106.55.62.122:8011/api/rehab-arm/v1 \
  --execute \
  --check-quality-gate
```

在开发电脑上检查云端 dashboard：

```powershell
$data = Invoke-RestMethod -Uri 'http://106.55.62.122:8011/api/rehab-arm/v1/devices/dashboard'
$data.data.devices | Select-Object device_id, robot_id, latest_upload_status
```

通过标准：

- 对应设备出现在 `devices` 中。
- `data_quality.annotation_ready=true` 表示该 session 可进入标注/导出。
- `data_quality.latest_session.quality_report_ok=true`。
- `data_quality.control_boundary=data_quality_only_not_motion_permission`，表示这仍然不是运动许可。

也可以用命令行工具直接检查某台设备：

```bash
ros2 run rehab_arm_psoc_bridge check_server_quality_gate nanopi-m5 \
  --base-url http://106.55.62.122:8011/api/rehab-arm/v1 \
  --pretty
```

通过标准：

- 输出 `schema_version=server_quality_gate_check_v1`。
- `ok=true` 表示服务器已收到该设备的合格质量门数据。
- `annotation_ready=true` 表示可以进入平台标注/导出流程。
- `safety_note` 会明确说明这只是数据就绪，不是运动许可。
- 如果 `ok=false`，先看 `errors` 和 `blocking_reasons`，不要把该 session 用作训练数据。

推荐现场使用方式：

- 第一次接服务器时先不加 `--execute`，只看 dry-run 请求计划。
- 确认 endpoint 正确后再加 `--execute --check-quality-gate`。
- 如果上传成功但质量门失败，说明服务器收到了数据，但这段数据还不适合标注/训练。
- `--allow-quality-not-ready` 只用于排查服务器是否收到设备，不应用作训练数据验收标准。

服务器同步 API 草案见：[SERVER_SYNC_API_DRAFT.md](SERVER_SYNC_API_DRAFT.md)。

## 6. 当前真实 CAN ID

| ID | 协议/用途 | 说明 |
|---|---|---|
| `node_id=3` | CANSimple/ODrive 类协议 | heartbeat 标准帧 `0x061` |
| `motor_id=4/5/6/7` | 私有扩展帧 MIT 电机协议 | 当前只允许调试使用，机械关节绑定待确认 |
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | M33 状态回复 |
| `0x7C2` | C8T6 -> M33 | 传感数据 |
| `0x7C3` | C8T6 -> M33 | 健康状态 |

## 6.1 在平台里预览 URDF

本仓库当前可直接预览的 URDF：

```bash
rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf
```

平台操作路径：

1. 打开 AI 合作平台的项目页面。
2. 进入 `设备数据工作台`。
3. 创建或打开一个调试窗口。
4. 切到 `模型预览`。
5. 选择 `rehab_arm.urdf`。
6. 检查 link 数、joint 数、可动 joint、parent/child 和 joint limit。
7. 如需留证据，点击导出模型 manifest。

通过标准：

- 页面显示 `URDF` 格式。
- link 数为 6。
- joint 数为 5。
- 可动 joint 数为 5。
- joint 名称包含 `shoulder_lift_joint`、`shoulder_abduction_joint`、`upper_arm_rotation_joint`、`elbow_lift_joint`、`forearm_rotation_joint`。

注意：

- 模型预览只读，不发 CAN，不发 ROS 控制，不代表允许真机运动。
- 后续如果换成带 mesh 的 URDF，要一起处理 `package://` mesh 路径映射。
- 后续如果使用 xacro，需要先在 ROS 侧展开成 URDF 再给平台。

## 6.2 导出仿真环境自检报告

在 Linux 仿真主机或 ROS2 工作区里，先生成平台可读的仿真准备度报告：

```bash
cd ~/rehab_ws_src/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --output sim_readiness_report.json
```

也可以直接用 Python 脚本测试：

```bash
python3 src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/check_sim_env.py \
  --workspace-root . \
  --pretty \
  --output sim_readiness_report.json
```

通过标准：

- 生成 `sim_readiness_report.json`。
- `schema_version` 为 `rehab_arm_sim_env_check_v1`。
- `readiness=ready_with_mujoco` 表示 MuJoCo 环境可用。
- `readiness=ready_with_fallback_sim` 表示 ROS2 数据链路可先跑，MuJoCo Python 包后续再补。
- `ok=false` 时先修 `errors`，不要进入复杂仿真 launch。

先 dry-run 检查要上传到平台的内容：

```bash
ros2 run rehab_arm_sim_mujoco upload_sim_readiness sim_readiness_report.json \
  --device-id <device_id> \
  --robot-id rehab-arm-alpha \
  --base-url http://<server>:8011/api/rehab-arm/v1
```

确认 URL、`device_id`、`robot_id` 都正确后，再显式执行上传：

```bash
ros2 run rehab_arm_sim_mujoco upload_sim_readiness sim_readiness_report.json \
  --device-id <device_id> \
  --robot-id rehab-arm-alpha \
  --base-url http://<server>:8011/api/rehab-arm/v1 \
  --execute
```

注意：

- 这个报告只说明仿真/采集环境是否准备好。
- 它不是运动许可，不代表真机可以上电或运动。
- 平台只把它显示为数据资产和研发准备度，不会下发 CAN 或电机命令。
- 不加 `--execute` 时不会联网，只打印上传计划。
- 上传完成后可以删除本地 `sim_readiness_report.json`，不要把它提交进 Git。

## 6.3 在平台查看 Linux 开发板接入状态

打开平台项目里的 `Linux 开发板` 页面后，先看总览里的 `接入检查` 面板。

它应该帮助你快速判断下一步：

- `开发板`：服务器是否已经看到 Linux 开发板上传数据。
- `Runner`：平台是否有可执行扫描/调试任务的电脑或 runner。
- `ROS/仿真`：是否上传过仿真环境自检报告。
- `摄像头`：是否收到过开发板摄像头关键帧。
- `CAN/串口`：是否收到过 manifest、`motor_state` 或 `sensor_state`。
- `最近上传`：判断数据是否还新鲜。

注意：

- 这个面板只是机器人开发入口检查，不是总控台运动控制。
- 页面上的 `扫描开发板/runner` 只触发平台扫描/发现流程，不代表真机允许运动。
- 真机运动仍必须走 `JointTrajectory -> NanoPi -> M33 -> 电机`，并由 M33 安全状态机最终裁决。
- 如果只是做仿真、采集或标注，可以先用这个面板确认 ROS/仿真报告和数据上传是否连通。

面板里还有一个默认收起的 `开发板接入脚本清单`。后续给任意 Linux 开发板写预配置脚本时，至少按这个顺序交付：

1. 注册设备：上传 `device_id`、`robot_id`、主机名、在线状态和能力 `manifest`。
2. 扫描接口：报告 CAN、串口、USB、摄像头、ROS2 环境和 runner 可执行能力。
3. 上传只读数据：按项目需要上传 `motor_state`、`sensor_state`、`camera_keyframe`、`simulation_readiness`。
4. 进入采集/标注：确认安全边界后，再开启数据同步、质量门、标注和图表实验。

这个清单适用于 NanoPi、Jetson、x86 工控机或其他 Linux 开发板；具体机器人项目的控制权限和安全裁决必须另行实现，不能由平台清单代替。

## 6.4 在 Linux 开发板生成接入 manifest

在 NanoPi 或任意 Linux 开发板上，先构建 ROS2 工作区并 source 环境，然后运行只读自检：

```bash
cd ~/rehab_ws_src/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge board_manifest \
  --device-id nanopi-m5 \
  --robot-id rehab-arm-alpha \
  --pretty \
  --output board_manifest.json
```

它会生成 `linux_board_manifest_v1`，包含：

- 开发板身份：`device_id`、`robot_id`、hostname、系统版本。
- 接口能力：网卡、`can*`、串口、USB、摄像头、ROS2 是否可用。
- 推荐数据流：`motor_state`、`sensor_state`、`camera_keyframe`、`simulation_readiness`。
- 安全边界：`board_discovery_only_not_motion_permission`。

注意：

- 这个命令只读扫描本机，不联网，不启动 CAN，不发 ROS 控制，不控制电机。
- 生成的 `board_manifest.json` 可以先人工检查；后续再接平台上传工具。
- 临时生成的 manifest 不要提交进 Git，除非它变成正式测试 fixture。

检查要同步到平台的请求计划：

```bash
ros2 run rehab_arm_psoc_bridge board_manifest_sync_dry_run board_manifest.json \
  --base-url http://<server>:8011/api/rehab-arm/v1
```

通过标准：

- 输出 `linux_board_manifest_sync_dry_run_v1`。
- `requests[0].url` 指向 `/devices/register`。
- `requests[0].json.device_type` 为 `linux_board`。
- `requests[1].url` 指向 `/devices/<device_id>/board-manifest`。
- `requests[1].json.manifest.schema_version` 为 `linux_board_manifest_v1`。
- `control_boundary` 为 `board_manifest_sync_plan_only_not_motion_permission`。

注意：

- `board_manifest_sync_dry_run` 只打印请求计划，不联网。
- 真正上传前必须先人工确认 `device_id`、`robot_id`、`capabilities` 和服务器地址。
- 平台现在会分别保存精简注册信息和完整 `linux_board_manifest_v1`。
- 平台页面会用完整 manifest 辅助判断 CAN、串口、USB、摄像头和 ROS2 能力，但这仍然不是运动许可。

确认无误后，才可以显式执行上传：

```bash
ros2 run rehab_arm_psoc_bridge board_manifest_sync_upload board_manifest.json \
  --base-url http://<server>:8011/api/rehab-arm/v1 \
  --execute
```

如果不加 `--execute`，`board_manifest_sync_upload` 也只会输出 dry-run 计划，不会联网。上传通过标准：

- 输出 `linux_board_manifest_sync_execute_result_v1`。
- `ok=true`。
- `completed_count=2`。
- 两个请求分别完成 `/devices/register` 和 `/devices/<device_id>/board-manifest`。
- `control_boundary` 为 `board_manifest_sync_only_not_motion_permission`。

注意：

- 这个上传只同步开发板能力清单，不启动摄像头数据流，不打开 CAN，不控制电机。
- 如果服务器地址、设备 ID 或机器人 ID 不确定，先只运行不带 `--execute` 的预览命令。
- 不要把真实机器的 `board_manifest.json` 当作 demo 文件提交进 Git。

## 7. 文档与 Git 维护

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

测试和 demo 约束：

- 临时 demo、测试报告、截图、样例上传数据不要留在项目目录里。
- 自动化测试需要生成文件时，应写入系统临时目录，测试结束自动清理。
- 只有正式代码、正式测试、正式文档、可复用配置可以进入 Git。
