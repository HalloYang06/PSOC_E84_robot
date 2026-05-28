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
- App BLE 和平台/服务器可以同时监控、同时提出 pause/stop/profile draft 等请求，但都不能直接控制电机；M33 永远按最保守状态做最终安全裁决。
- 旧规划 CAN ID 不作为当前依据。

当前总体数据流图见：[system_data_flow.png](assets/system_data_flow.png)。

M33 物理安全输入映射合同见：[M33_SAFETY_INPUT_MAPPING.md](M33_SAFETY_INPUT_MAPPING.md)。后续接真实急停、电源/电压、限位前，先按该文档确认输入源、`confirmed` 条件和 `safe_now` 条件。

当前预选的 40Pin 诊断输入只有急停：physical pin 11 / `GPIO0` / `RPI_GPIO_10`。这个脚只允许接 3.3V 逻辑；电机母线、电池或 5V 信号不能直接接入。电源 OK 当前不接、不实现；限速和限位后续由用户在 M33 代码中按真实机械零点、软限位、编码器/关节映射设置。

M33 pre-arm 现在预留了代码配置型安全检查：位置限位、速度限制、扭矩/电流限制。它们会在串口中以 `PREARM_CODE_LIMITS` 单独显示；默认都是 `confirmed=0 safe_now=0`，等用户后续直接改 M33 代码填入真实限制后再打开。

当前开发台架固件允许临时打开小幅运动链路：`CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U`。这只用于空载或隔离台架开发，不是穿戴安全模式。该模式下 M33 仍会审核 `0x320`：ROS 关节号必须合法，位置目标必须在 `-60°~+60°`，速度必须在 `-5~+5 rpm`，`torque_ma` 必须为 `0`。ROS joint id 是 `0-based`，M33 会映射到内部 `1-based` 电机关节槽位。

当前 M33 电机减速比配置已经按真实型号对齐：joint3 伺泰威 `48:1`，joint4/5 灵足 RS00 `10:1`，joint6/7 灵足 EL05 `9:1`。用户后续改安全限位时，要继续使用 joint/output-side 角度和速度思维；M33 内部会负责转换到 motor-side 单位。未重新编译、烧录并复测前，不要把这个配置视为已在板端生效。

`0x320` 的 `joint_id` 是 ROS 关节号，不是厂家电机 ID。当前正规链路映射应为：ROS joint `0..4` -> M33 motor slot `3/4/5/6/7`。因此通过 M33 正规路径测试 7 号时，命令应该是 `--joint 4`，不是 `--joint 7`：

```bash
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 30 --rpm 3 --torque-ma 0
```

这条映射需要 M33 重新编译烧录后才生效。烧录前，`--joint 4` 仍可能打到旧映射下的 motor slot 5。

重要：7 号已证明 ROS joint4 能经 M33 打到 motor7，但在零点/方向/绝对位置参考未标定前，`m33 target --joint 4 --deg ...` 这类绝对位置目标可能造成剧烈转动。当前 M33 默认应保持 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=0U`，不要再次发送 ROS 位置目标到电机。下一步只能做低速短时速度脉冲和反馈记录，用于标定方向、比例和零点。

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
- `topic_contract.trajectory_command.topic=/arm_controller/joint_trajectory`。
- `topic_contract.joint_state.topic=/joint_states`。
- `topic_contract.safety_state.topic=/rehab_arm/safety_state`。
- `topic_contract.sensor_state.topic=/rehab_arm/sensor_state`。
- `topic_contract.vla_task_goal.topic=/vla/task_goal`。
- `topic_contract.control_boundary=simulation_topic_contract_not_motion_permission`。
- `checks.urdf.ok=true`。
- `checks.sim_data_collection_launch.ok=true`。
- `safety_note` 明确该命令不打开 CAN、不发 `0x320/0x321`、不命令 M33 或电机。

这些 `topic_contract` 是仿真主机、NanoPi、平台采集标注和后续 VLA 之间的标准 ROS 接口清单。它只能说明“软件合同应该长什么样”，不能说明 topic 已经实时发布，更不能说明真机允许运动。真机运动仍必须走 M33 安全状态机。

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
| `require_psoc_ok_for_trajectory` | `true` | 只有收到新鲜的 M33 `0x322` 且 `motion_allowed=true` 才允许接收/发送轨迹 |
| `reject_out_of_limit_trajectory` | `true` | 轨迹点超出软件关节限位时拒绝轨迹 |
| `max_trajectory_points` | `100` | 限制一次轨迹消息的最大点数 |
| `status_timeout_sec` | `2.5` | 超过该时间未收到 PSoC status，认为状态过期 |
| `enable_target_tx` | `false` | 是否真的发送 `0x320` 目标帧；默认只 dry-run 打日志 |

安全行为：

- bridge 启动时先发布 `limited: bridge started, waiting for PSoC status`。
- 没有 M33 `0x322 motion_allowed=true` 时，收到 `/arm_controller/joint_trajectory` 会拒绝，不发 `0x320`。
- 旧版 V1 `0x322 state=ok` 只代表状态兼容，不代表运动许可；bridge 仍会拒绝轨迹。
- 正在发送轨迹时，如果 PSoC 状态过期或变成 fault，会清空剩余轨迹并停止发送。
- 轨迹含未知关节、空点、非有限数值、超限点或过多点时，会拒绝并发布 `limited`。
- 默认 `enable_target_tx=false` 时，合法轨迹也不会真的发 `0x320`，只打印 `DRY-RUN 320 ...`。
- bridge 只会为 `JointTrajectory.joint_names` 中明确出现的关节生成目标帧，不会自动给未命令关节补发目标。

已验证的无状态拒绝测试：

```text
safety limited: rejected trajectory: no PSoC status received
```

已验证的 M33 logging-only 拒绝测试：

```text
safety limited: rejected trajectory: PSoC motion_allowed is not true, protocol_version=2, state=limited, control_mode=logging_only, detail=logging_only_no_motor_output
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

没有硬件、不能上电时，也可以先跑 `0x320` 编码/解码、`0x322` 状态解析和 `0x330~0x337` M33 电机遥测草案解析工具回归测试：

```bash
cd D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan
python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v
```

通过标准：

- 全部测试都显示 `ok`。
- 覆盖合法编码、解码、负角度截断、超限拒绝、非有限数拒绝、未知关节拒绝、payload 长度错误和 unknown joint 可见性。
- 覆盖 `0x322` V1 legacy 兼容、V2 limited/logging-only、emergency_stop、error_code 强制 fault、坏 marker 和短帧。
- 覆盖 `0x330~0x337` M33 电机遥测草案：ID 范围、marker、长度、位置/速度/温度换算、fault/limited/enabled 标志和 motor_state payload 过滤。

NanoPi 上也可以跑 `0x322` 状态解析测试：

```bash
cd /home/pi/rehab_arm_ros2_ws
python3 -m unittest discover -s src/rehab_arm_psoc_bridge/test -v
```

只跑 M33 电机遥测草案解析测试：

```bash
python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_psoc_motor_status.py -v
```

注意：`0x330~0x337` 是 M33 固件的正式遥测链路，只用于 NanoPi/ROS/平台读取电机状态。它不是运动命令，也不能替代 `0x322` 安全状态。

当 M33 开始发送合法 `0x330~0x337` 时，现有 `psoc_can_bridge_node.py` 会自动把这些帧聚合发布到：

```text
/rehab_arm/motor_state
/joint_states
```

`/rehab_arm/motor_state` 用于电机状态、温度、故障、平台表格和数据集字段；`/joint_states` 用于 RViz、MuJoCo 状态同步、平台 three.js/URDF 机械臂姿态和标注回放。它们都不下发运动，不代表系统可以动；是否允许运动仍看 M33 `0x322` safety/status 和 M33 内部安全状态机。

M33 遥测帧 `flags bit4=1` 表示 `stale_or_no_feedback`。这种帧说明 M33 的槽位上报线程还活着，但该电机没有新鲜反馈；NanoPi 会把它保留在 `/rehab_arm/motor_state` 里给平台显示缺数据，但不会把它写进 `/joint_states`，避免把 0 rad 假姿态喂给仿真、规划或 three.js 预览。

bridge 也会用这些 M33 遥测刷新内部 `current_positions`。这只是让后续轨迹处理知道“当前姿态大概在哪里”，不是运动许可；没有新鲜、允许运动的 `0x322` 状态时，轨迹仍会被拒绝。

离线验证 M33 到 ROS topic 的组合合同：

```bash
cd ~/nanopi_can_ros_ws/src/rehab_arm_psoc_bridge
python3 -m unittest test/test_m33_ros_contract.py test/test_psoc_status.py test/test_psoc_motor_status.py test/test_safety_gate.py
```

通过标准：

- limited/logging-only 的 `0x322` 仍然生成 `/rehab_arm/safety_state`，但 `motion_candidate_allowed=false`。
- 合法 `0x330~0x337` 只生成 `/rehab_arm/motor_state` 和 `/joint_states` 遥测，不会改变运动许可。
- 只有 `0x322` V2 同时满足 `state=ok`、`control_mode=armed/active`、`detail=none`、`error_code=0` 时，NanoPi 才把它当成运动候选许可。

当前本地 M33 工程已补好 `0x330~0x334` 周期上报逻辑：这些帧对应 ROS joint `0..4`，再映射到 motor slot `3/4/5/6/7`。有新鲜反馈时发布真实位置/速度/温度；没有新鲜反馈时发布 stale 帧。等待用户用 RT-Thread Studio 编译烧录。烧录后先只验收遥测，不发 `0x320` 运动命令：

```bash
ip -details link show can0
timeout 5 candump -L can0,330:7F8,061:7FF,069:7FF,180007FD:1FFFFFFF
```

通过标准：

- `can0` 为 `ERROR-ACTIVE`，tx/rx error counter 为 0。
- 3 号伺泰威在线时，能看到 `0x061/0x069`。
- 7 号灵足 active-report 打开时，能看到 `0x180007FD`。
- M33 聚合遥测生效后，能看到 `0x330~0x334` 中的周期帧；`0x335~0x337` 预留。
- `0x330~0x334` 的 byte2 应分别是当前正式链路真实电机 `3/4/5/6/7`，不能再是内部旧槽位 `1/2/3/4/5`。
- `0x330~0x337` payload byte0 必须是 `B3`。
- 如果 payload byte3 带 `0x10`，说明该槽位暂时没有新鲜电机反馈；这是可诊断状态，不是运动许可。
- 整个过程不发布 `/arm_controller/joint_trajectory`，不发送 `0x320`。

已验证通过的只读样例：

```text
0x330#B3xx0310000000FF
0x331#B3xx0410000000FF
0x332#B3xx0510000000FF
0x333#B3xx0610000000FF
0x334#B3xx0710000000FF
```

其中 `xx` 是循环序号，`03/04/05/06/07` 是真实 motor_id，`10` 是 stale/no-feedback 标志。此时 `/rehab_arm/motor_state` 应该有 5 个 stale 电机条目，但 `/joint_states` 不应该发布这些 0 位姿。

如果要继续从 stale 进入真实姿态，先证明电机原始反馈存在：

```bash
timeout 3s candump -L can0 > /tmp/fresh_feedback_probe.candump
```

通过标准：

- 3 号伺泰威在线时，应能看到 `0x061` heartbeat 和 `0x069` encoder estimate。
- 7 号灵足打开 active-report 后，应能看到 `0x180007FD` 或运动/状态变化时的 `0x188007FD`。
- 如果只看到 `0x330~0x334` 且 byte3 一直是 `0x10`，说明 M33 发布线程在线，但电机原始反馈还没有进入总线；此时不要发布轨迹。

如果要确认灵足电机节点是否在线，可以只做 Get_ID 非运动探测：

```bash
python3 /home/pi/nanopi_can_master.py probe --iface can0 --start 4 --end 7 --wait 0.2
```

通过标准：

- 至少能看到某个电机的 Get_ID 回复或后续 active-report 原始帧。
- 如果 4~7 全无回复，但 `can0` 仍是 `ERROR-ACTIVE` 且 M33 `0x322` 正常，优先检查电机侧供电、CAN 支路、终端、共地和节点 ID。

如果要确认 3 号 CANSimple 是否在线，只做非运动查询：

```bash
python3 /home/pi/nanopi_can_master.py cansimple get-error --iface can0 --node 3 --error-type 0 --wait 0.8
python3 /home/pi/nanopi_can_master.py cansimple address --iface can0 --wait 0.8
```

通过标准：

- 能看到 3 号真实 `0x061` heartbeat、`0x069` encoder estimate，或电机对查询的有效回复。
- 只看到 NanoPi 发出的 `0x063#00` 或 broadcast `0x7E6#`，不能证明 3 号在线。
- M33 最新固件要求：如果没有真实 `0x061/0x069`，`0x330` 仍应保持 `flags bit4=stale`；主机查询帧不能把它刷新成 fresh。

已验证通过的安全现象：

- 发 `0x063#00` 后，如果总线上没有 `0x061/0x069`，`0x330` 仍保持 `B3 xx 03 10 00 00 00 FF`。
- 这表示 motor3 状态仍是 stale，NanoPi 不应发布对应 `/joint_states`。

正式 5 关节 M33 遥测检查：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 run rehab_arm_psoc_bridge check_m33_motor_status_presence.py /tmp/post_flash_readonly_probe.candump --pretty
```

通过标准：

- `ok=true`
- `m33_motor_status_ids` 只需要包含 `0x330..0x334`
- `motor_ids_by_status_id` 应为 `0x330:3`、`0x331:4`、`0x332:5`、`0x333:6`、`0x334:7`
- `target_0x320_count=0`
- 没有新鲜电机反馈时，`fresh_m33_motor_status_count=0` 且 `stale_m33_motor_status_count>0`

如果需要 M33 串口手动触发一次缓存上报，可在 M33 shell 运行：

```text
cmd_m33_motor_status_once
```

期望串口输出类似：

```text
m33_motor_status_once sent=<n> base=0x330 period_ms=100 fresh_ms=1000
```

新版本即使没有新鲜电机反馈也应 `sent>0`，并通过 `flags bit4=1` 表示 stale。如果仍然 `sent=0`，优先检查 M33 是否烧录了新固件、`control_layer_init()` 是否启动、CAN direct send 是否正常。

烧录后已经验证过的最小只读链路如下：

```bash
# 1. 看 M33 是否在线回复状态，不会让电机运动
rm -f /tmp/m33_probe.log
timeout 4 candump -L can0,322:7FF,330:7F8 > /tmp/m33_probe.log &
DUMP_PID=$!
sleep 0.3
cansend can0 321#01
wait "$DUMP_PID" || true
cat /tmp/m33_probe.log

# 2. 临时打开 7 号灵足主动遥测 5 秒，结束会自动关闭
cd /home/pi/rehab_arm_ros2_ws
python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/live_socketcan_motor_snapshot.py \
  --iface can0 \
  --duration 5 \
  --enable-active-report 7 \
  --pretty
```

通过标准：

- 第 1 步能看到 `0x322`，例如 `322#A501070001010A00`。
- 第 2 步能看到 `counts` 里包含 `0x180007FD` 和 `0x336`。
- `0x336` 的 candump 形如 `336#B3...`，byte0 是 `B3`。

ROS bridge 只读验收：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py \
  --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

另开一个 NanoPi 终端，在 7 号 active-report 打开的时间窗口内查看：

```bash
ros2 topic list -t
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

注意：短时验收时要给 `ros2 topic echo --once` 显式写消息类型，否则 topic 还没出现在 ROS graph 时，CLI 可能无法自动推断类型。

推荐以后上电后直接运行固定脚本：

```bash
chmod +x /home/pi/nanopi_live_telemetry_check.sh
/home/pi/nanopi_live_telemetry_check.sh
```

如果脚本还没有同步到 NanoPi，先从仓库复制：

```bash
scp scripts/nanopi_live_telemetry_check.sh pi@192.168.2.66:/home/pi/nanopi_live_telemetry_check.sh
```

脚本通过时会输出：

```text
PASS: live telemetry path is valid and read-only.
```

这个脚本会检查：

- `can0` 是 `ERROR-ACTIVE`。
- `0x321#01` 能收到 M33 `0x322`。
- 7 号灵足临时 active-report 能触发 M33 `0x336#B3...`。
- ROS topic 有 `/rehab_arm/motor_state` 和 `/joint_states`。
- 验收期间没有任何 `0x320` target frame。

可选环境变量：

```bash
IFACE=can0 ACTIVE_REPORT_MOTOR=7 SNAPSHOT_SECONDS=5 /home/pi/nanopi_live_telemetry_check.sh
ACTIVE_REPORT_MOTOR=none /home/pi/nanopi_live_telemetry_check.sh
BUILD_WORKSPACE=1 /home/pi/nanopi_live_telemetry_check.sh
```

`ACTIVE_REPORT_MOTOR=none` 适合只想看已有 M33 telemetry 的情况；`BUILD_WORKSPACE=1` 会先重编 `/home/pi/rehab_arm_ros2_ws`。

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

后续 M33 只有在同时满足以下条件时才允许上报 `motion_allowed=true`：

- `error_code=0`
- `state=ok`
- `control_mode=armed` 或 `control_mode=active`
- `detail_code=none`
- M33 内部确认 heartbeat、急停、限位、供电、温度、抱闸、电机反馈、关节映射和限速限流全部通过

开发台架固件应上报 `control_mode=bench_armed`，而不是正式 `armed`。NanoPi parser 会识别 `bench_armed`，但默认仍解析为 `motion_allowed=false`，避免平台/App/ROS 把台架状态误当成人体穿戴许可。

正式 clinical build 还需要 M33 侧显式打开 clinical motion 开关。若 clinical 开关打开但 pre-arm 条件不满足，`0x322` 应保持 `motion_allowed=false`，并回报 `detail=prearm_not_ready`。

如果 `state=ok/control_mode=armed` 但 `detail_code` 仍是 `motor_fault`、`target_out_of_limit`、`logging_only_no_motor_output` 等非 `none`，NanoPi 仍会把 `motion_allowed` 解析为 `false`。

如果本机或 NanoPi 上有旧 bridge 进程，先清理再测：

```bash
pgrep -af 'psoc_can_bridge_node|rehab_arm_psoc_bridge'
kill <pid>
```

当前 NanoPi 工作区的 bridge 可执行名可能带 `.py` 后缀。若 `ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node` 提示 `No executable found`，先查：

```bash
ros2 pkg executables rehab_arm_psoc_bridge
```

若列表中是 `psoc_can_bridge_node.py`，启动命令也要用这个名字。

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
- `cmd_m33_prearm_check` 会打印预 armed 检查表，但不会改变模式，不会允许运动。

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

旧版 logging-only 固件会表示 M33 在线但不可运动。开发台架固件打开 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` 后，`0x322` 可临时上报 `ok/armed`，让 NanoPi bridge 放行受限的 `0x320 set_target`；这仍然只代表台架开发许可，不代表人体穿戴许可。

可选：在 M33 shell 查看预 armed 检查表：

```text
cmd_m33_prearm_check
```

也可以临时指定本次诊断需要检查的电机槽位 mask，不会写入配置：

```text
cmd_m33_prearm_check 0x40
cmd_m33_prearm_check 0x44
```

- `0x40`：只检查 slot6，也就是当前 `0x336` 对应的 7 号灵足槽位。
- `0x44`：检查 slot2 + slot6，也就是当前 3 号伺泰威和 7 号灵足槽位。
- 不带参数时使用固件默认 `CONTROL_PREARM_REQUIRED_JOINT_MASK=0x7F`，要求 7 个槽位全部满足。

当前默认应该失败，示例字段如下：

```text
PREARM: ready=0 motion_allowed_would_be=0
PREARM_MASK: required_mask=0x0000007F source=config default_mask=0x0000007F
PREARM_MODE: logging_only_clear=0 logging_only_compile=1 allow_with_logging_only=0
PREARM_HEARTBEAT: ok=<0|1> age_ms=<n> timeout_ms=2500
PREARM_INPUTS: estop_confirmed=0 power_confirmed=1 limits_confirmed=0
PREARM_INPUT_DETAIL: estop source=rpi40_pin11_gpio0_rpi_gpio10 safe_now=0; power source=not_used_no_power_ok_input safe_now=1; limits source=software_joint_limits_user_configured safe_now=0
PREARM_CODE_LIMITS: position confirmed=0 safe_now=0; speed confirmed=0 safe_now=0; torque_current confirmed=0 safe_now=0
PREARM_MOTORS: required_mask=0x0000007F fresh_mask=<mask> fault_mask=<mask> fresh_count=<n> fresh_ok=<0|1> fault_free=<0|1>
PREARM_NOTE: diagnostic only; this command never changes mode and never enables motion
```

解释：

- `ready=0` 是当前正确结果。
- `logging_only_clear=0` 表示固件仍处于 logging-only，不允许真实输出；开发台架固件会把该项清掉，但仍要通过 M33 的小幅运动审核。
- `estop_confirmed=0` 和 `limits_confirmed=0` 表示急停、代码限速限位还没有接入并确认；`power_confirmed=1` 只是因为本阶段不使用 power OK 输入。
- `confirmed=0 safe_now=0` 表示该安全输入尚未现场验证，也没有处于可放行状态；即使 source 已经预选，也不能运动。
- `PREARM_CODE_LIMITS` 表示代码配置型安全限制是否已确认：位置限位、速度限制、扭矩/电流限制必须分别确认。
- `fresh_mask` 只表示 M33 最近收到哪些电机反馈，不等于可以运动。

也可以单独查看物理安全输入合同：

```text
cmd_m33_safety_inputs
```

当前默认期望输出类似：

```text
SAFETY_INPUT: name=estop source=rpi40_pin11_gpio0_rpi_gpio10 confirmed=0 safe_now=0 meaning=emergency stop input must be wired, tested, and released
SAFETY_INPUT: name=power source=not_used_no_power_ok_input confirmed=1 safe_now=1 meaning=power OK input is not used in this firmware slice
SAFETY_INPUT: name=limits source=software_joint_limits_user_configured confirmed=0 safe_now=0 meaning=joint limits must be calibrated before any assisted motion
SAFETY_INPUT_NOTE: diagnostic only; defaults are unwired/unconfirmed and must block prearm
```

通过标准：

- `confirmed=0` 和 `safe_now=0` 是当前正确结果。
- 这一步只说明安全输入合同已经能被串口看到，不代表可以运动。
- 后续接真实急停、电源检测、限位检测时，必须同时证明 `confirmed=1` 和 `safe_now=1`，并且仍要满足 heartbeat、logging mode、motor freshness、fault-free 等条件。

烧录后已验证的新安全输入输出：

```text
cmd_m33_safety_inputs
SAFETY_INPUT: name=estop source=rpi40_pin11_gpio0_rpi_gpio10 confirmed=0 safe_now=0 meaning=emergency stop input must be wired, tested, and released
SAFETY_INPUT: name=power source=not_used_no_power_ok_input confirmed=1 safe_now=1 meaning=power OK input is not used in this firmware slice
SAFETY_INPUT: name=limits source=software_joint_limits_user_configured confirmed=0 safe_now=0 meaning=joint limits must be calibrated before any assisted motion
SAFETY_INPUT_NOTE: diagnostic only; defaults are unwired/unconfirmed and must block prearm
```

已验证的烧录后输出：

```text
PREARM: ready=0 motion_allowed_would_be=0
PREARM_MODE: logging_only_clear=0 logging_only_compile=1 allow_with_logging_only=0
PREARM_HEARTBEAT: ok=1 age_ms=78 timeout_ms=2500
PREARM_INPUTS: estop_confirmed=0 power_confirmed=0 limits_confirmed=0
PREARM_MOTORS: required_mask=0x0000007F fresh_mask=0x00000000 fault_mask=0x00000000 fresh_count=0 fresh_ok=0 fault_free=1
```

这表示 M33 在线、heartbeat 新鲜，但旧版正式 pre-arm 仍未通过。开发台架固件可以临时做小幅运动验证；人在设备内时不要使用该模式。

已验证的 7 号诊断 mask 输出：

```text
cmd_m33_prearm_check 0x40
PREARM: ready=0 motion_allowed_would_be=0
PREARM_MASK: required_mask=0x00000040 source=argv default_mask=0x0000007F
PREARM_HEARTBEAT: ok=1 age_ms=165 timeout_ms=2500
PREARM_MOTORS: required_mask=0x00000040 fresh_mask=0x00000040 fault_mask=0x00000000 fresh_count=1 fresh_ok=1 fault_free=1
```

这只证明 slot6/7号 telemetry 在检查瞬间是新鲜的；`ready=0` 仍然是正确结果。

新安全输入固件烧录后，7 号 telemetry 新鲜时也已验证：

```text
PREARM_INPUT_DETAIL: estop source=rpi40_pin11_gpio0_rpi_gpio10 safe_now=0; power source=not_used_no_power_ok_input safe_now=1; limits source=software_joint_limits_user_configured safe_now=0
PREARM_MOTORS: required_mask=0x00000040 fresh_mask=0x00000040 fault_mask=0x00000000 fresh_count=1 fresh_ok=1 fault_free=1
```

这说明电机 freshness 条件可以满足，但物理安全输入仍然正确地阻止 pre-arm。

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

如果已经用 `candump -tz can0` 或 `candump -L can0` 保存了原始 CAN 日志，可以离线转换成统一 JSONL，供总控台、标注、曲线分析、MuJoCo/RViz 回放和后续训练前检查使用：

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

当前转换器解析三类只读遥测：

- `0x322`：M33 安全状态，转换后 topic 为 `/rehab_arm/safety_state`，用于检查 `state/detail/control_mode/motion_allowed`。
- `0x330~0x337`：M33 汇总后的正式电机/关节遥测草案，转换后 source 为 `candump_m33_motor_status`，并同时生成 `/rehab_arm/motor_state` 和 `/joint_states`。
- `0x061`：`node_id=3` heartbeat，用来补充 enabled、fault、axis_state、error_code。
- `0x069`：`node_id=3` encoder estimate，按 little-endian float 解码 position/velocity。
- position 从 turns 转成 rad，velocity 从 turns/s 转成 rad/s。
- `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`：私有协议 active-report 状态帧，对应电机 4/5/6/7。
- 灵足 private active-report 目前默认只保留 `raw_position_u16`、`raw_velocity_u16`、`raw_torque_u16`、`raw_temperature_u16`、`status_raw` 和原始 CAN 数据；在 4/5/6/7 的真实型号确认前，不把它伪装成真实 rad、Nm 或摄氏度。
- 电机协议总表见：[MOTOR_PROTOCOLS.md](MOTOR_PROTOCOLS.md)。

通过标准：

- 输出 summary 中 `ok=true`。
- `motor_state_count` 大于 0。
- 如果日志里包含 M33 `0x322`，`safety_state_count` 应大于 0，并且当前非穿戴/调试阶段 `motion_allowed_counts.true` 应为 0。
- 如果日志里包含 M33 `0x330~0x337`，`m33_motor_status_count` 和 `joint_state_count` 都应大于 0。
- JSONL 第一行是 `session_metadata`。
- 后续记录 topic 至少包含 `/rehab_arm/safety_state` 或 `/rehab_arm/motor_state`。
- M33 `0x330~0x337` 记录还会包含 `/joint_states`，用于仿真姿态、RViz、平台 three.js/URDF 预览和标注回放。
- `/rehab_arm/motor_state` payload 的 `schema_version` 是 `rehab_arm_motor_state_v1`。
- `control_boundary` 是 `telemetry_only_not_motor_command`。

注意：`candump_motor_telemetry` 是离线日志转换工具，不打开 SocketCAN，不发 CAN，不发送 `0x320/0x321`，不控制 M33 或电机。`/joint_states` 和 `/rehab_arm/motor_state` 只能证明状态可见，不能证明允许运动；运动候选许可仍只看 `/rehab_arm/safety_state.motion_allowed`。闭环刚建立后的 `0x069` 第一次跳变可能包含估计器恢复，不要直接等同于真实机械位移。

如果只读验收里出现 `motion_allowed_counts.true > 0`，先不要发布 `/arm_controller/joint_trajectory`。这通常表示 M33 当前烧录的是开发台架 armed 固件，或者 safety 状态已经被配置为放行。此时必须先确认现场无人穿戴、限位/限速/急停策略符合当前测试目的，并再次抓包确认没有意外 `0x320`，再决定是否进入小角度运动测试。

如果要临时抓 4/5/6/7 的原始周期状态，先由调试工具打开 private active-report，再抓包，测试结束必须关闭 active-report。正式 ROS 路径后续仍要由 M33 聚合并发布 `/rehab_arm/motor_state`，NanoPi 直接打开 private active-report 只用于调试接收链路。

如果 M33 固件还没有真正发送 `0x330~0x337`，可以先用合成遥测帧 smoke 工具验证 NanoPi bridge 和 recorder 链路。

如果设备已经上电，并且只想直接从真实 `can0` 看当前电机状态，可以运行短时真 CAN 快照工具。这个工具默认只监听；如果要让灵足电机临时上报状态，显式指定 `--enable-active-report <motor_id>`，工具结束时会自动关闭该 active-report。

```bash
cd /home/pi/rehab_arm_ros2_ws
python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/live_socketcan_motor_snapshot.py \
  --iface can0 \
  --duration 3 \
  --enable-active-report 7 \
  --output-jsonl /home/pi/rehab_arm_logs/live_snapshots/live_3_7.jsonl \
  --session-id live_3_7_powered \
  --pretty
```

通过标准：

- 输出 `schema_version=live_socketcan_motor_snapshot_v1`。
- `counts` 中能看到当前在线电机的 CAN ID，例如 3 号伺泰威 `0x061/0x069`，7 号灵足 `0x180007FD`。
- `latest.motor3_encoder.vendor` 为 `Sitaiwei`。
- `latest.motor7_active_report.vendor` 为 `Lingzu`。
- `motor_state_compatible_entries` 中只有遥测字段，不包含运动命令。
- 如果加了 `--output-jsonl`，会写出 recorder/platform 可读取的 JSONL：第一行 `session_metadata`，第二行 `/rehab_arm/motor_state`。
- `control_boundary` 是 `telemetry_only_not_motor_command`。

注意：

- 这个工具不发送位置、速度、力矩、`0x320` 或 M33 控制命令。
- `--enable-active-report` 只用于让指定灵足电机周期上报状态，属于调试遥测开关；正式机器人路径仍然应由 M33 汇总后发布 `/rehab_arm/motor_state`。
- 如果 4/5/6 被断电或关闭，它们不会回复 Get_ID，也不会出现 active-report，这是预期现象，不要当成解析失败。
- 从 Windows PowerShell 远程执行 SSH 命令时，不要在双引号里直接写远端 `$(date ...)`，否则 PowerShell 可能先在本机解析。需要时间戳文件名时，优先先 SSH 到 NanoPi 后执行，或用固定文件名验证链路。

先干跑，不发 CAN：

```bash
cd /home/pi/rehab_arm_ros2_ws
python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_motor_status_smoke.py \
  --interface vcan0
```

通过标准：

- 输出 JSON 中 `execute=false`。
- `frames` 里有 `0x330` 和 `0x331`。
- `expected_motor_state_payload.valid_motor_count=2`。
- `safety_note` 明确不会发送 `0x320`，不会命令 M33，不会授权电机运动。

也可以生成一份最小 JSONL，用来直接验证数据采集、质量门和后续平台导入：

```bash
python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_motor_status_smoke.py \
  --output-jsonl /home/pi/rehab_arm_logs/synthetic_m33_motor_status_smoke.jsonl

python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/validate_recording_quality.py \
  /home/pi/rehab_arm_logs/synthetic_m33_motor_status_smoke.jsonl \
  --topic-profile hardware_telemetry \
  --require-motor-state \
  --min-motor-entry-count 2
```

通过标准：

- quality report 的 `ok=true`。
- `topic_profile=hardware_telemetry`。
- summary 中 `/rehab_arm/motor_state` 至少 1 条。
- summary 中 `motor_entry_count_min=2`。

`m33_motor_status_smoke.py --output-jsonl` 的 stdout 会同时带一个 `quality_report`。平台“Linux 开发板设备数据工作台”可以先读取这些字段作为最小合同：

- `quality_report.ok`
- `quality_report.topic_profile`
- `quality_report.required_topics`
- `quality_report.summary.topic_counts`
- `quality_report.summary.motor_entry_count_min`
- `/rehab_arm/motor_state` payload 中的 motor 3/7 状态字段和 `control_boundary`

这份 JSONL 后续可以作为平台最小样本：平台应该能看到 session、topic 数量、电机条目数、motor 3/7 的状态字段和 `control_boundary`。

如果要验证真实 bridge 发布 topic，建议先用 `vcan0`。一个终端启动 bridge：

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node \
  --ros-args -p interface:=vcan0 -p require_psoc_ok_for_trajectory:=false
```

另一个终端显式发送合成遥测帧：

```bash
python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_motor_status_smoke.py \
  --interface vcan0 \
  --execute
```

第三个终端观察输出：

```bash
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

注意：`--execute` 只发送 `0x330~0x337` 合成遥测帧，用来测试接收/发布链路。它不发送 `0x320`，不控制电机，也不代表 M33 允许运动。上真实 `can0` 前先确认现场没有把这些测试帧误接入控制逻辑；当前设计中它们只能作为遥测。

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

也可以用预设 topic 合同，避免每次手写 topic 名：

```bash
# 仿真/基础采集最小合同：joint_states + safety_state + sensor_state
ros2 run rehab_arm_psoc_bridge check_recording.py /home/pi/rehab_arm_logs/sim_session.jsonl \
  --topic-profile simulation_minimum

# 真机/电机遥测合同：基础合同 + motor_state
ros2 run rehab_arm_psoc_bridge check_recording.py /home/pi/rehab_arm_logs/sim_session.jsonl \
  --topic-profile hardware_telemetry

# 视觉/VLA 数据合同：基础合同 + camera_keyframe
ros2 run rehab_arm_psoc_bridge check_recording.py /home/pi/rehab_arm_logs/sim_session.jsonl \
  --topic-profile perception_vla
```

这些 preset 只检查“录到的数据 topic 是否齐全”。它们不会启动 ROS 节点，不联网，不读取 CAN，不控制 M33 或电机。`hardware_telemetry` 失败并提示缺 `/rehab_arm/motor_state` 时，说明这段数据还不适合做电机曲线、标注或训练前验收。

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
  --topic-profile hardware_telemetry \
  --min-joint-messages 100 \
  --min-moving-joints 5 \
  --require-motor-state \
  --min-motor-entry-count 5 \
  --pretty
```

通过标准：

- 输出 `schema_version=rehab_arm_recording_quality_v1`。
- 输出 `topic_profile=hardware_telemetry` 和对应 `required_topics`。
- `ok=true`。
- `errors=[]`。
- 当前 logging-only/仿真采集阶段不应出现 `motion_allowed=true`。

如果只是短时间 recorder 冒烟测试，可以降低阈值；如果是动态 demo 采集，应要求 `moving_joint_count=5` 和 `motor_entry_count_min>=5`。如果是视觉/VLA 数据，改用 `--topic-profile perception_vla`，并确认 JSONL 里有 `/rehab_arm/camera_keyframe`。

视觉/VLA 关键帧数量检查：

```bash
ros2 run rehab_arm_psoc_bridge validate_recording_quality.py \
  /tmp/rehab_sim_collection/perception_session.jsonl \
  --topic-profile perception_vla \
  --min-camera-keyframes 10 \
  --pretty
```

通过标准：

- `topic_profile=perception_vla`。
- `criteria.min_camera_keyframes=10`。
- `/rehab_arm/camera_keyframe` 数量不少于 10。
- 这个检查只统计 JSONL 中的关键帧消息，不打开摄像头、不读取图片文件、不控制电机。

如果这段 JSONL 和图片文件已经在同一台电脑上，可以进一步检查图片文件存在和 sha256：

```bash
ros2 run rehab_arm_psoc_bridge validate_recording_quality.py \
  /tmp/rehab_sim_collection/perception_session.jsonl \
  --topic-profile perception_vla \
  --min-camera-keyframes 10 \
  --require-camera-files \
  --camera-base-dir /tmp/rehab_sim_collection \
  --pretty
```

通过标准：

- `camera_file_check.checked_count` 等于关键帧数量。
- `camera_file_check.missing_count=0`。
- `camera_file_check.hash_mismatch_count=0`。

注意：如果 JSONL 里的 `image_path` 是 NanoPi 上的绝对路径，而你在另一台电脑离线检查，这个文件检查会失败。这种情况下先只检查 topic 和关键帧数量，等图片同步到本地后再加 `--require-camera-files`。

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

生成离线回放计划：

```bash
ros2 run rehab_arm_psoc_bridge build_replay_plan.py \
  /tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  --topic /joint_states \
  --topic /rehab_arm/motor_state \
  --output /tmp/rehab_sim_collection/replay_plan.json \
  --pretty
```

输出：

- `schema_version=rehab_arm_replay_plan_v1`
- `duration_sec`：本段数据按记录时间计算的总时长。
- `events[]`：按 `ts_unix` 排序的 topic 消息。
- `events[].relative_time_sec`：从本段第一条事件开始的相对时间。
- `topic_counts`：每个 topic 的事件数量。
- `control_boundary=replay_plan_only_not_motion_permission`

如果只是想检查时间轴和 topic 数量，不想输出完整 payload：

```bash
ros2 run rehab_arm_psoc_bridge build_replay_plan.py \
  /tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  --topic /joint_states \
  --no-payload \
  --pretty
```

这个 replay plan 对齐 ROS2 `rosbag2` 的基本思想：按 topic 和时间复现实验数据。区别是它仍然是平台/标注/训练友好的 JSON，不直接发布 ROS topic，不控制 M33，不发 CAN。后续接 MuJoCo 时，应先用它验证时间轴和关节状态，再写 ROS publisher 或 rosbag 转换器。

在 ROS2 中回放 JSONL：

```bash
ros2 run rehab_arm_psoc_bridge jsonl_replay_node.py --ros-args \
  -p recording_path:=/tmp/rehab_sim_collection/sim_demo_motion.jsonl \
  -p topics:=/joint_states,/rehab_arm/motor_state,/rehab_arm/safety_state,/rehab_arm/sensor_state \
  -p speed:=1.0 \
  -p loop:=false
```

会发布：

- `/joint_states`：标准 `sensor_msgs/msg/JointState`，供 RViz、MuJoCo 状态同步和 three.js/URDF 预览使用。
- `/rehab_arm/motor_state`：`std_msgs/msg/String` JSON，供平台、电机表格、颜色映射和标注回放使用。
- `/rehab_arm/safety_state`：`std_msgs/msg/String` JSON，供安全状态回放使用。
- `/rehab_arm/sensor_state`、`/rehab_arm/camera_keyframe`：如果 JSONL 中存在对应记录，也可以一起回放。

注意：这个节点只是把历史数据重新发布到 ROS topic。它不订阅 `/arm_controller/joint_trajectory`，不连接 SocketCAN，不发送 `0x320`，不控制 M33，也不驱动电机。用于真机之前，先在仿真主机/RViz 中确认 topic、时间轴和关节方向。

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

生成标注队列：

```bash
ros2 run rehab_arm_psoc_bridge build_annotation_queue.py \
  /home/pi/rehab_arm_logs/manifest_with_quality.json \
  --output /home/pi/rehab_arm_logs/annotation_queue.json
```

通过标准：

- 输出 `schema_version=rehab_arm_annotation_queue_v1`。
- `ready_count` 是可进入标注的数据段数量。
- `skipped_sessions` 里列出未通过质量门的数据段和原因。
- 默认只接受 `session.ok=true` 且 `quality_report.ok=true` 的 session。

如果要自定义标注字段，可以重复传入 `--label`：

```bash
ros2 run rehab_arm_psoc_bridge build_annotation_queue.py \
  /home/pi/rehab_arm_logs/manifest_with_quality.json \
  --label reach_phase \
  --label object_state \
  --label assistance_quality \
  --output /home/pi/rehab_arm_logs/annotation_queue.json
```

这个队列只用于平台、人工标注、训练前筛选和数据浏览。它不会打开 ROS topic，不联网，不读取 CAN，不控制 M33 或电机。

导出 CSV 标注模板：

```bash
ros2 run rehab_arm_psoc_bridge export_annotation_template.py \
  /home/pi/rehab_arm_logs/annotation_queue.json \
  --output /home/pi/rehab_arm_logs/annotation_template.csv
```

CSV 默认包含：

- `session_id`
- `file_name`
- `path`
- `device_id`
- `robot_id`
- `topic_profile`
- `annotation_status`
- `annotator`
- `notes`
- 队列中的 `recommended_labels`

人工或平台填完后，先保留为标注结果文件；后续再做训练集导出。这个 CSV 仍然只是离线数据，不是 ROS topic、不是 CAN 命令、不是 M33 控制指令。

校验已完成的 CSV 标注结果：

```bash
ros2 run rehab_arm_psoc_bridge validate_annotations.py \
  /home/pi/rehab_arm_logs/annotation_queue.json \
  /home/pi/rehab_arm_logs/annotations_completed.csv
```

通过标准：

- 输出 `schema_version=rehab_arm_annotation_validation_v1`。
- `ok=true`。
- 每个 `session_id` 必须来自 `annotation_queue.json`。
- 每行 `annotation_status` 默认必须是 `approved`。
- 队列推荐的每个 label 字段都必须填写。

如果平台或人工流程使用别的通过状态，可以显式指定：

```bash
ros2 run rehab_arm_psoc_bridge validate_annotations.py \
  /home/pi/rehab_arm_logs/annotation_queue.json \
  /home/pi/rehab_arm_logs/annotations_completed.csv \
  --approved-status reviewed
```

这个校验器是训练前质量门，只判断标注 CSV 是否可进入后续数据集导出。它不会打开 ROS topic，不联网，不读取 CAN，不控制 M33 或电机。

生成数据集索引：

```bash
ros2 run rehab_arm_psoc_bridge build_dataset_index.py \
  /home/pi/rehab_arm_logs/manifest_with_quality.json \
  --dataset-id rehab-arm-bench-001 \
  --purpose replay_review \
  --output /home/pi/rehab_arm_logs/dataset_index.json
```

通过标准：

- 输出 `schema_version=rehab_arm_dataset_index_v1`。
- `ready_count` 是可进入数据集的数据段数量。
- `items[]` 包含 `session_id`、`jsonl_path`、`device_id`、`robot_id`、`topics`、`topic_profile`、`summary` 和 `quality_report_ok`。
- `skipped_sessions[]` 列出缺少质量报告、质量门失败或 session 无效的数据段。
- `control_boundary=dataset_index_only_not_motion_permission`。

这个索引用于平台数据资产、训练前导出、VLA 上下文数据选择和回放审查。它只整理本地 manifest，不上传服务器，不打开 ROS topic，不读取 CAN，不控制 M33 或电机。

校验 Patient Device Profile：

```bash
ros2 run rehab_arm_psoc_bridge validate_patient_profile.py \
  /home/pi/rehab_arm_profiles/patient_device_profile.json \
  --pretty
```

通过标准：

- 输出 `schema_version=patient_device_profile_validation_v1`。
- `ok=true`。
- 患者 ROM 必须在设备绝对限制内，当前第一版默认设备包络为 `-60° ~ +60°`。
- 患者限速必须大于 `0`，且不能超过第一版默认上限 `30 deg/s`，也不能超过设备绝对限速。
- `training_mode` 必须是 `passive_training`、`active_assist`、`resistance_training` 或 `memory_mode`。
- 急停策略必须是 `disable_motor_output`，`fault_latch` 必须为 `true`。
- VLA 权限只能是 `disabled`、`suggest_only` 或 `plan_only`，并且必须明确禁止 `can_frame`、`torque_command`、`current_command`、`velocity_command`、`raw_motor_position`。
- M55 不能声明 `direct_motor_control`。

这个校验器是平台/App/NanoPi/M33/M55 共用 profile 进入系统前的安全质量门。它不写 profile，不上传服务器，不打开 ROS topic，不读取 CAN，不控制 M33 或电机。校验失败时，不应把该 profile 设置为 active，也不应下发给 M33。

导出 M33 安全子集 dry-run：

```bash
ros2 run rehab_arm_psoc_bridge export_m33_safety_subset.py \
  /home/pi/rehab_arm_profiles/patient_device_profile.json \
  --output /home/pi/rehab_arm_profiles/m33_safety_profile.json \
  --pretty
```

通过标准：

- 输出 `schema_version=m33_safety_profile_v1`。
- `ok=true`。
- `joint_limits_deg` 是设备绝对限位和患者 ROM 取更严格后的结果。
- `velocity_limits_dps`、`acceleration_limits_dps2`、`torque_current_limits` 都取设备限制和患者限制中的更保守值。
- `mode_permission.vla_task_execution=false`。
- `control_boundary=m33_safety_subset_dry_run_only_not_sent`。

这个命令只是生成给 M33 合同审查用的 JSON，不会通过 CAN 或其他方式下发给 M33。后续真下发前，还需要加签名/版本/时效检查和 M33 端解析验证。

审查 Patient Device Profile 变更：

```bash
ros2 run rehab_arm_psoc_bridge review_patient_profile_change.py \
  /home/pi/rehab_arm_profiles/active_profile.json \
  /home/pi/rehab_arm_profiles/draft_profile.json \
  --pretty
```

通过标准：

- 输出 `schema_version=patient_device_profile_change_report_v1`。
- `ok=true` 表示旧/新 profile 都合法、版本递增、设备/患者一致。
- `warnings[]` 会列出 ROM 放宽、限速提高、训练模式变化等需要人工审查的项目。
- `changes[]` 会列出具体字段、旧值、新值和风险等级。
- `control_boundary=profile_change_review_only_not_motion_permission`。

这个工具不会自动批准 profile，也不会写入 active profile。平台/App 可以用它在用户确认前显示“本次把 shoulder ROM 从 35° 放宽到 40°”“默认限速从 6 提高到 8”等风险提示。

生成 App BLE -> M33 安全包 dry-run：

```bash
ros2 run rehab_arm_psoc_bridge build_ble_m33_safety_package.py \
  /home/pi/rehab_arm_profiles/patient_device_profile.json \
  --approved-by clinician_001 \
  --approved-at 2026-05-27T10:00:00+08:00 \
  --expires-at 2026-05-28T10:00:00+08:00 \
  --output /home/pi/rehab_arm_profiles/ble_m33_safety_package.json \
  --pretty
```

通过标准：

- 输出 `schema_version=ble_m33_safety_package_v1`。
- `transport=app_ble_to_m33`。
- `ok=true`。
- `profile_status` 必须已经是 `approved` 或 `active`。
- `m33_safety_subset.schema_version=m33_safety_profile_v1`。
- `signature_placeholder` 暂时为空，后续正式 BLE 下发前必须补签名/校验。
- `control_boundary=ble_package_dry_run_only_not_sent`。

这个命令只生成 App 通过 BLE 发给 M33 的最小安全包草案，不进行蓝牙扫描、连接或写入。M33 正式接收前还需要固件侧校验 profile version、device id、有效期、签名和安全限制。

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
  --topic-profile hardware_telemetry \
  --min-joint-messages 50 \
  --min-moving-joints 5 \
  --require-motor-state \
  --min-motor-entry-count 5 \
  --output /home/pi/rehab_arm_logs/manifest_with_quality.json
```

如果是视觉/VLA 数据，把 profile 和关键帧阈值换成：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --include-summary \
  --include-quality-report \
  --topic-profile perception_vla \
  --min-camera-keyframes 10 \
  --output /home/pi/rehab_arm_logs/manifest_with_perception_quality.json
```

如果 manifest 所在机器能访问图片文件，可以加：

```bash
  --require-camera-files \
  --camera-base-dir /home/pi/rehab_arm_logs
```

通过标准：

- 每个有效 session 包含 `quality_report.schema_version=rehab_arm_recording_quality_v1`。
- `quality_report.topic_profile` 记录本次使用的 profile，例如 `hardware_telemetry`。
- `quality_report.required_topics` 记录该 profile 要求的 topic。
- 视觉数据启用文件检查时，`quality_report.camera_file_check.missing_count=0` 且 `hash_mismatch_count=0`。
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
| `node_id=3` | 伺泰威 CANSimple/ODrive 类协议 | heartbeat 标准帧 `0x061`，encoder estimate `0x069` |
| `motor_id=4/5/6/7` | 灵足 RobStride 私有扩展帧协议 | active-report `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`；当前只允许调试使用，型号和机械关节绑定待确认 |
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | M33 状态回复 |
| `0x7C2` | C8T6 -> M33 | 传感数据 |
| `0x7C3` | C8T6 -> M33 | 健康状态 |

更完整的厂家协议、量程来源、未知项和 M33 安全边界见：[MOTOR_PROTOCOLS.md](MOTOR_PROTOCOLS.md)。

伺泰威/肩关节驱动资料当前使用本地离线副本：

```text
D:\电机上位机\肩关节电机资料
```

在线飞书链接如果跳到登录页，不影响继续查本地离线页。

当前已确认的伺泰威 CANSimple 基础规则：

- 使用标准 11-bit CAN ID。
- `CAN ID = (node_id << 5) + cmd_id`。
- 数据区是 classic CAN，最多 8 字节；实际 DLC 跟命令有关。
- 多字节数据使用小端。
- `float32` 按 IEEE754 编码。
- `node_id=3` 时，heartbeat 是 `0x061`，encoder estimate 是 `0x069`。
- `0x061` 的 byte5/byte6/byte7 当前在数据采集中只作为 raw 字段保存，暂时不要当成可靠温度或安全状态。
- 本地 M33/NanoPi 实现中，`Set_Input_Torque` 当前是 4 字节 `float32 torque_nm`，不要为了“凑满 8 字节”随意改协议。

正式机器人控制仍然走 `ROS2 JointTrajectory -> NanoPi -> M33 -> 电机`，不要把这些 CANSimple 直接控制帧放进正式 launch。

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

## 6.5 开发阶段直接调试 7号后的收尾检查

正式机器人路径仍然是 `JointTrajectory -> NanoPi -> M33 -> 电机`。下面命令只用于台架开发时验证 7号电机和 CAN 总线是否工作，不能作为正式控制流程。

```bash
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --enable-report --wait 0.1
python3 /home/pi/nanopi_can_master.py private speed --iface can0 --motor 7 --vel 0.30 --kd 1.0 --wait 0.1
sleep 1.0
python3 /home/pi/nanopi_can_master.py private stop --iface can0 --motor 7 --wait 0.2
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --wait 0.1
```

收尾验证：

```bash
timeout 1 candump -L can0 | head -20
ps -ef | grep -E '[p]soc_can_bridge|[r]os2' || true
ip -details link show can0
```

通过标准：

- `candump` 没有持续 `0x180007FD/0x188007FD`，说明 7号主动上报已经关闭。
- 没有遗留 `psoc_can_bridge` 或 ROS2 运动相关进程。
- `can0` 仍为 `ERROR-ACTIVE`，错误计数为 0。

失败处理：

- 如果还有持续反馈帧，重新发送 `private stop` 和关闭 active-report。
- 如果 ROS bridge 还在运行，先停掉再继续任何人工调试。
- 如果 `can0` 不是 `ERROR-ACTIVE`，不要继续动电机，先排查供电、接线、终端电阻和 MCP2518FD 状态。

7号软件角度停止调试时，必须先读取可信的输出轴角度，再从当前位置累计相对角度。注意运动反馈可能是 `0x188007FD`，解析时应按 `(data2 & 0xFF) == 7` 识别 7号，不要只认静止时常见的 `0x180007FD`。

当前限制：

- 现有脚本中的 `data[0:2] -> -12.57~12.57 rad` 映射已经被现场观察推翻，不能当作 7号输出轴角度。
- 在重新标定前，不要用这个字段做 `55°`、`60°` 等安全停止条件。
- 正式安全限位应放到 M33，并使用经过标定的关节角来源、外部限位或编码器来源。

已确认型号和减速比：

- 3号：伺泰威，减速比 `48:1`；当前还没现场看到真实运动，不能当作已打通。
- 4号、5号：灵足 RS00，官方减速比 `10:1`。
- 6号、7号：灵足 EL05，官方减速比 `9:1`。
- 资料依据：`D:\电机上位机\Product_Information\灵足时代产品规格介绍 RobStride Product Specification Document 20250626.pdf`、RS00/EL05 使用说明书，以及现场型号确认。
- 注意：减速比只说明电机内部电机侧/输出侧关系，不能替代 CAN 协议字段标定。7号当前仍需要标定速度命令和反馈字段到真实输出轴角度的关系。
- NanoPi 遥测解码策略：4/5号 RS00 可以按本地 RS00 示例量程临时输出工程值；6/7号 EL05 目前只输出型号、减速比和 raw 字段，不输出未确认的角度/速度/力矩工程值。

推荐标定动作：

```bash
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --enable-report --wait 0.1
python3 /home/pi/nanopi_can_master.py private speed --iface can0 --motor 7 --vel 0.524 --kd 1.0 --wait 0.1
sleep 3.0
python3 /home/pi/nanopi_can_master.py private stop --iface can0 --motor 7 --wait 0.2
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --wait 0.1
```

现场记录 3 秒内输出端实际转过的角度或圈数，再用它反推 7号真实输出角速度。不要在映射确认前使用未知反馈字段做自动角度停止。

当前一次粗标定结果：

- direct private speed 参数按 `5 rpm` 折算发送 `0.524 rad/s`。
- 持续 `3s` 后，用户确认可见输出面约转 `150°`。
- 粗略输出速度约 `50°/s`，即约 `8.33 rpm`。
- 在完成更精确标定前，所有 7号速度/角度命令都要按实测结果保守处理。

视频标定建议：

- 在输出端面贴一条明显胶带或画一条白线，避免圆孔对称导致看不清角度。
- 手机尽量固定俯拍，不要在动作中移动镜头。
- 拍摄起始静止、运动、停止后三段；停止后保持 1 秒，方便对比起止角度。

## 6.6 开发阶段直接调试 3号伺泰威

3号当前按 CANSimple node `3` 调试，减速比按 `48:1` 记录。正式路径仍应回到 `JointTrajectory -> NanoPi -> M33 -> 电机`，下面只用于台架排查。

温和速度测试：

```bash
python3 /home/pi/nanopi_can_master.py cansimple clear --iface can0 --node 3 --wait 0.2
python3 /home/pi/nanopi_can_master.py cansimple closed-loop --iface can0 --node 3 --wait 0.5
python3 /home/pi/nanopi_can_master.py cansimple vel --iface can0 --node 3 --vel 4.0 --torque 0.0 --wait 0.2
sleep 3.0
python3 /home/pi/nanopi_can_master.py cansimple vel --iface can0 --node 3 --vel 0.0 --torque 0.0 --wait 0.2
python3 /home/pi/nanopi_can_master.py cansimple idle --iface can0 --node 3 --wait 0.3
```

减速比换算：

- 输出端角度 `output_rad` 对应电机侧 `motor_rad = output_rad * 48`。
- 输出端速度 `output_rad_s` 对应电机侧 `motor_rad_s = output_rad_s * 48`。
- 例如输出端约 `5 deg/s`，电机侧约 `4.19 rad/s`。

通过标准：

- 能看到 3号真实 heartbeat/status/encoder feedback，而不是只有 NanoPi 发出的 `0x067/0x06B/0x06D` 命令帧。
- M33 的 3号聚合状态不再长期为零。
- 测试结束后 3号已收到 `vel 0` 和 `idle`。

如果只看到命令帧、没有真实反馈，不要继续加大速度；先确认 node id、闭环状态、错误码、编码器、刹车/使能和驱动供电。

## 6.7 M33 关节标定门

M33 现在把绝对位置控制和标定状态绑定。默认所有关节 `calibrated=0`，即使后续打开 bench motion，ROS `set_target` 和 `motor_pos` 位置控制也会被拒绝，原因是 `joint_uncalibrated`。

查看 M33 当前标定配置：

```text
m33_joint_calib
m33_joint_calib 7
```

预期输出会包含：

```text
JOINT_CALIB: joint=7 motor_id=7 proto=0 calibrated=0 direction_x1000=1000 gear_x1000=9000 zero_mrad=0
JOINT_CALIB_NOTE: absolute position commands are rejected while calibrated=0
```

当 NanoPi/M33 收到某个合法但未标定关节的目标时，M33 应打印类似：

```text
safety_state=limited decision=reject reason=joint_uncalibrated
audit ... joint_calibrated=0 ...
```

NanoPi ROS `/rehab_arm/safety_state` 应解析为：

```text
detail_code=11
detail=joint_uncalibrated
motion_allowed=false
```

上电后的非运动验收顺序：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 63 --wait 0.3
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 5 --rpm 1 --torque-ma 0 --wait 0.15
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 64 --wait 0.8
```

通过标准：

- 第三条命令收到 `0x322`，byte6 为 `0x0B`。
- 解析后为 `detail_code=11`、`detail=joint_uncalibrated`。
- 同时用 `candump` 过滤确认没有对应电机控制帧。例如 7号不应出现 `01800007`、`0300FD07`、`180007FD`、`188007FD`。

注意：如果先发 target、heartbeat 已过期，M33 会优先报 `detail_code=1 heartbeat_timeout`。这也是正确的安全拒绝，但它不能证明标定门已经走到。

### 6.7.1 标定遥测开关

M33 允许 NanoPi 通过正式 `0x320` 链路打开/关闭单个关节的 active-report，用于采集当前位置和原始反馈。这个入口是 telemetry-only，不会发 enable、zero、mode、position、velocity 或 torque。

示例，打开 7号对应的 ROS joint4 遥测：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 70 --wait 0.3
python3 /home/pi/nanopi_can_master.py m33 active-report --iface can0 --joint 4 --enable-report --wait 0.2
timeout 2 candump -L can0 | grep -E '180007FD|188007FD|336|322'
python3 /home/pi/nanopi_can_master.py m33 active-report --iface can0 --joint 4 --wait 0.2
```

通过标准：

- M33 日志应显示 `final action=apply_calibration_telemetry_only`。
- 可以看到 7号 active-report 或 M33 聚合状态 `0x336` 更新。
- 不应看到 `01800007` 或其他 7号位置/速度/扭矩控制帧。
- 结束后必须关闭 active-report，并确认总线没有持续刷 `180007FD/188007FD`。

已验证示例：

```text
0x320#060401                         # NanoPi -> M33: open joint4/motor7 telemetry
0x1800FD07#0102030405060100          # M33 -> motor7: enable active-report
0x180007FD#F8D47FFF7FFF014A          # motor7 -> bus: raw active-report
0x336#B3xx07005A2E0021               # M33 -> NanoPi: cached aggregate status
0x320#060400                         # NanoPi -> M33: close joint4/motor7 telemetry
0x1800FD07#0102030405060000          # M33 -> motor7: disable active-report
```

注意：

- 关闭后 `0x336` 仍可能继续按 M33 状态周期发布，这是聚合/缓存状态，不等于电机还在主动上报。
- 关闭是否成功主要看 `0x180007FD/0x188007FD` 是否停止。

### 6.7.2 标定观测报告

把上面的 `candump -L` 输出保存成文件后，可以用报告工具做一次安全检查：

```bash
calibration_observation /tmp/m33_active_report_gate.candump --motor-id 7 --pretty
```

如果没有安装 ROS 包，也可以在源码目录运行：

```bash
python3 rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/calibration_observation.py /tmp/m33_active_report_gate.candump --motor-id 7 --pretty
```

重点看这些字段：

- `observation_ok=true`：看到了原始电机遥测或 M33 聚合状态。
- `no_motion_control_frames=true`：没有看到对应电机的位置/速度/扭矩控制帧。
- `motor_control_frames=0`：没有误发 7号 `01800007` 这类运动控制帧。
- `safe_to_use_as_motion_proof=false`：这是正确结果，说明报告只证明遥测链路，不证明关节已标定。

如果 `ok=false`，先不要继续标定。检查是否没有打开 active-report，或者是否误发了运动控制帧。

### 6.7.3 未装机台架 7 号快速试错

当前机械臂还没有装机时，可以先用电机官方绝对角度、方向默认、限位 ±60° 打通正式 M33 运动链路。这个阶段不在 M33 里做零点标注；零点、患者 ROM、训练模式和限速参数后续由上位机/平台/App 统一 profile 管理。

更新：7号 EL05 已通过 official CSP 试验确认，RobStride `loc_ref`/反馈位置在当前台架上对应可见输出侧角度，不需要再除以 `9`。当前台架版本使用：

- `CONTROL_MOTOR_JOINT4/5/6/7_GEAR_RATIO=(1.0f)`
- `CONTROL_MOTOR_JOINT7_ZERO_OFFSET_RAD=(0.0f)`
- `CONTROL_MOTOR_JOINT7_CALIBRATED=1U`

M33 正式 `0x320 set_target` 对 4/5/6/7 灵足电机使用官方 CSP 参数流：`run_mode=5`、enable、`limit_spd(0x7017)`、`loc_ref(0x7016)`。因此 ROS joint4 `+5°` 预期就是输出端约 `+5°`。

3号 Sitaiwei CANSimple 当前台架版本使用：

- `CONTROL_MOTOR_JOINT3_GEAR_RATIO=(48.0f)`
- `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(0.0f)`
- `CONTROL_MOTOR_JOINT3_CALIBRATED=1U`

注意：3号这里的 `48.0f` 不是照搬 7号灵足的错误经验。3号当前 formal path 使用 Sitaiwei CANSimple/ODrive-like 协议；该协议的开源/官方参考路线是 ODrive CAN，位置和速度单位是 `rev` / `rev/s`。所以 ROS 关节角要先转换到电机协议侧单位。若后续要让 3号“不乘减速比”地按输出轴角度控制，需要新建 3号 MIT/output-axis RAD 路径，不应直接删掉 CANSimple 的 `gear_ratio`。

当前路线调整：如果电机官方协议提供的角度已经是可用绝对角度，就不让 M33 承担零点标注。M33 的主职责是安全裁决、限位、限速、限流、急停和故障保护；机械零点、患者 ROM、患者限速、训练模式等由上位机/平台/App 统一标注并写入 active Patient Device Profile。

M33 不提供 `m33_session_zero`，NanoPi 的 `m33 zero` 也不作为正式接口使用。上位机标注零点后，应把结果同步到平台/App 的 profile 和数据采集元数据；M33 只接收审核后的安全限制子集。

3号对应 ROS joint0。烧录后可先测：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 92 --wait 0.3
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 0 --deg 5 --rpm 1 --torque-ma 0 --wait 0.3
python3 /home/pi/nanopi_can_master.py m33 stop --iface can0 --joint 0 --wait 0.3
```

如果 formal path 没有看到 3号动，马上再发 heartbeat：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 93 --wait 0.3
```

若 `0x322` 最后几位类似 `... 01 02 0B 00`，其中 detail code `0x0B` 表示 M33 认为该 joint 未标定，正式位置命令已被安全状态机拦截。这时不是 CANSimple 不通，也不是 NanoPi 没发，而是板端 M33 固件没有放开该 joint 的 formal bench calibration gate。

若 formal path 已经能看到 `0x06B/0x06F/0x067/0x06C`，但 3号几乎不动，检查 M33 是否已烧录 `ed1cfc49` 或更新版本。旧版本给 CANSimple `Set_Limits` 第二个 float 写 `0.0`，可能导致位置目标已发送但没有足够执行余量。`ed1cfc49` 改为使用 `CONTROL_CANSIMPLE_POSITION_LIMIT_CURRENT=(5.0f)`。

3号 direct CANSimple +5° 台架验证过的计算方式：

- 先读当前 `0x069` 的 `position_rev`。
- 目标 `target_rev = current_rev + 5 / 360 * 48`。
- 本次实测从约 `7.66448 rev` 到 `8.33206 rev`，折算输出约 `5.0069°`。
- 结束必须发 `Set_Axis_State idle`，并确认 `can0` 仍为 `ERROR-ACTIVE`。

30° 或更大动作前，先确认能看到 3号 `0x061` heartbeat 和 `0x069` encoder estimate。若只看到 M33 `0x332`，不能当成 3号实时反馈在线。

如果 3号驱动重启后 `0x069 position_rev` 回到 `0`，M33 的台架 `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD` 也要跟着重置。当前 M33 commit `abedf348` 使用 `0.0f` 作为未装机台架零点。若继续使用旧的 `55.1f`，formal `+5°` 会被旧零点放大，实测会接近 `42°` 输出。这个重置只是台架调试措施，不是正式机器人上电策略。

3号无反馈时的停止线：

- 被动监听 `can0` 1~3 秒看不到 `0x061/0x069`。
- 发 `clear/closed-loop/idle` 后仍然只看到 M33 `0x332`。
- 这时不要继续发目标角度；先检查 3号供电、CAN 连接、节点 ID、协议模式和电机驱动状态。

### 6.7.4 运动测试后离线复盘

如果现场已经做过一次正式路径运动测试，先不要急着继续加大角度。把 `candump -L` 日志用离线报告工具复盘：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 run rehab_arm_psoc_bridge motion_test_report.py \
  /tmp/motor7_joint4_10deg.candump \
  --motor-id 7 \
  --joint-id 4 \
  --pretty
```

合格标准：

- `ok=true`。
- `target_command_count >= 1`。
- `has_expected_csp_sequence=true`，说明看到 `run_mode/limit_spd/loc_ref`。
- `stop_observed=true`，说明 ROS stop 和电机 stop 帧都出现。
- `no_legacy_mit_control=true`，说明没有退回旧的 `0x01800007` MIT 控制帧。
- `m33_motor_status.delta_position_deg` 有合理变化，用来和现场目测角度对照。

注意：

- 这个工具只读日志，不连接 CAN，不发命令，不代表可以继续运动。
- 如果人不在现场，只允许做这种离线复盘，不要远程继续发动作。

### 6.7.5 台架运动序列工具

需要重复验证电机方向和角度时，先生成计划，不要直接执行。当前统一电机表包含 3/4/5/6/7，但执行白名单只有 3号和 7号：

```bash
ros2 run rehab_arm_psoc_bridge bench_motion_sequence.py --list-motors --pretty
```

当前配置：

| motor_id | joint_id | joint name | 电机 | 测试状态 |
|---:|---:|---|---|---|
| 3 | 0 | `shoulder_lift_joint` | 伺泰威 CANSimple/ODrive-like | 允许台架测试 |
| 4 | 1 | `elbow_lift_joint` | 灵足 RS00 | 只配置，不允许执行 |
| 5 | 2 | `shoulder_abduction_joint` | 灵足 RS00 | 只配置，不允许执行 |
| 6 | 3 | `upper_arm_rotation_joint` | 灵足 EL05 | 只配置，不允许执行 |
| 7 | 4 | `forearm_rotation_joint` | 灵足 EL05 | 允许台架测试 |

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 run rehab_arm_psoc_bridge bench_motion_sequence.py --pretty
```

默认计划是：

- heartbeat precheck。
- joint4 `+5°`，rpm `1`。
- hold `2s`。
- stop joint4。
- joint4 `-5°`，rpm `1`。
- hold `2s`。
- stop joint4。
- heartbeat postcheck。

默认不访问 CAN，不会动电机。

只有人现场盯着台架、设备没有穿戴在人身上、急停/断电手段可用时，才允许执行：

```bash
ros2 run rehab_arm_psoc_bridge bench_motion_sequence.py \
  --execute \
  --confirm-onsite \
  --degrees 5,-5 \
  --rpm 1 \
  --hold-sec 2
```

如果指定 `--motor-id 4/5/6 --execute --confirm-onsite`，工具也会拒绝执行。等 4/5/6 机械安装、限位、方向和风险评估完成后，再显式放开。

执行后必须保存 `candump -L` 日志，再用 `motion_test_report.py` 复盘。人不在现场时不要带 `--execute`。

### 6.7.6 上电只读 ROS 遥测检查

设备刚上电、还没接完整 C8T6/传感器时，先做只读检查。这个流程只验证 NanoPi、CAN、M33、ROS bridge 和基础数据记录，不允许发送运动目标。

先确认 NanoPi 在线：

```bash
ssh pi@192.168.2.66 "hostname; whoami; uptime"
```

在 NanoPi 上启动 CAN：

```bash
echo pi | sudo -S ip link set can0 down 2>/dev/null || true
echo pi | sudo -S ip link set can0 type can bitrate 1000000 restart-ms 100
echo pi | sudo -S ip link set can0 up
ip -details link show can0
```

合格标准：

- `can0` 为 `UP`。
- `can state ERROR-ACTIVE`。
- `berr-counter tx 0 rx 0`，或至少没有持续增长。

被动确认总线：

```bash
timeout 3 candump -L can0
timeout 3 candump -L can0,7C0:7F0
```

当前阶段预期：

- 能看到 M33 aggregate `0x332`。
- 如果 3号在线，能看到 CANSimple `0x061/0x069`。
- 如果 C8T6 未接入，`0x7C2/0x7C3` 可以暂时为 0；接入 C8T6 后必须重新验证。

C8T6/F103 接入后，`0x7C2` 会被 NanoPi bridge 转成 `/rehab_arm/sensor_state` 的 `rehab_arm_sensor_state_v1` JSON：

- `emg_raw`：肌电原始采样。
- `emg_filtered`：肌电滤波值。
- `heart_rate_raw`：心率/PPG 原始值。
- `heart_rate_bpm`：心率 bpm。
- `flags_hex`、`emg_contact`、`imu_valid`、`heart_rate_valid`：传感有效性。

`0x7C3` 会转成 `rehab_arm_sensor_health_v1` JSON：

- `state`：`boot/ok/streaming/limited/fault/unknown`。
- `error_count`：传感节点错误计数。
- `queue_fill_percent`：队列占用百分比。

注意：这些字段只用于数据采集、显示、标注和模型输入，不能作为运动许可。是否允许运动仍只看 M33 `/rehab_arm/safety_state.motion_allowed`。

启动只读 ROS bridge 和 recorder：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

SESSION_ID=poweron-readonly-$(date +%Y%m%d-%H%M%S)
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false \
  -p log_heartbeat:=false
```

另开一个终端记录数据，`SESSION_ID` 要和上面保持一致：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

SESSION_ID=poweron-readonly-YYYYMMDD-HHMMSS

ros2 run rehab_arm_psoc_bridge data_recorder_node.py --ros-args \
  -p output_dir:=/home/pi/rehab_arm_logs \
  -p session_id:=$SESSION_ID \
  -p device_id:=nanopi-m5 \
  -p robot_id:=rehab-arm-alpha \
  -p software_version:=live-poweron \
  -p mode:=poweron_readonly
```

停止后检查记录：

```bash
ros2 run rehab_arm_psoc_bridge check_recording.py \
  /home/pi/rehab_arm_logs/$SESSION_ID.jsonl \
  --topic-profile poweron_readonly
```

合格标准：

- 返回 `ok=true`。
- topics 至少包含 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/motor_state`。
- `/rehab_arm/safety_state.motion_allowed` 在 `bench_armed` 下仍应为 `false`。

注意：

- 每次采集必须换新的 `SESSION_ID`；重复同名会追加写入旧文件。
- `poweron_readonly` 通过只说明基础遥测链路可用，不说明可以上人或可以运动。
- 完整硬件遥测要改用 `hardware_telemetry` profile，并要求 C8T6 `/rehab_arm/sensor_state` 存在。

烧录台架版本 M33 后，直接做极小角度测试。7 号对应 ROS joint4：

```bash
python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 81 --wait 0.3
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 5 --rpm 1 --torque-ma 0 --wait 0.3
```

注意：

- 先 `5°`，确认方向，再 `-5°`，再逐步扩大。
- 台架临时零点只说明开发时能走通链路，不代表可以穿戴在人身上。
- 若出现方向反了、幅度不对、速度不对，立刻 stop/断电，回到零点/方向/比例标定。

只有完成以下动作后，才允许在 M33 配置里把某个关节的 `CONTROL_MOTOR_JOINTx_CALIBRATED` 改成 `1U`：

- 人不穿戴设备，机械臂固定在台架。
- 手动摆到机械零位，并记录该姿态对应的 motor-protocol-side `zero_offset_rad`。
- 用小速度短脉冲确认正方向，设置 `CONTROL_MOTOR_JOINTx_DIRECTION` 为 `1.0f` 或 `-1.0f`。
- 用 `+5°/-5°`、`+10°/-10°` 验证真实输出角度和方向。
- 重新确认软件限位、限速、扭矩/电流限制和急停策略。

当前阶段不要把 RobStride 反馈字段直接当输出关节角度。7号已经出现过“软件解码角度看似到 55°，现场实际转动明显更多”的情况，所以必须先做软件零点和实物比例标定。

## 7. 文档与 Git 维护

### 7.1 查看当前电机配置权威表

当前已知电机身份、关节映射、协议、减速比和测试放行状态统一由 `motor_profiles.py` 输出：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge motor_profiles.py --pretty
```

也可以通过 bench motion 工具查看同一份表：

```bash
ros2 run rehab_arm_psoc_bridge bench_motion_sequence.py --list-motors --pretty
```

当前表的关键事实：

- `3`：伺泰威，CANSimple/ODrive-like，减速比按 `48` 记录，映射 `joint0`。
- `4/5`：灵足 RS00，RobStride CSP，已配置但暂不放行真实执行。
- `6/7`：灵足 EL05，RobStride CSP，`7` 已台架验证过正式 M33 路径。
- 当前真实执行 allowlist 只有 `3` 和 `7`；`4/5/6` 只能 dry-run 和规划，不能真实动。

这张表是给 NanoPi ROS、平台、App、M33 安全配置导出共同对齐的基础资料。修改它不等于放开运动权限；放开真实执行前必须完成机械限位、方向、速度、急停和台架小角度验证。

### 7.2 生成患者/设备安全配置模板

新患者或新设备建档时，先生成保守草稿，再由平台/App/治疗师审核修改：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge build_patient_profile_template.py \
  --profile-id pdp_20260527_0001 \
  --robot-id rehab_arm_alpha \
  --device-id nanopi_m5_001 \
  --patient-id patient_001 \
  --validate \
  --pretty \
  --output patient_device_profile_template.json
```

模板特点：

- 自动包含当前 5 个已知关节。
- 默认 `profile_status=draft`，不是 active，也不会下发 M33。
- 患者 ROM 默认每关节 `[-10°, +10°]`，患者限速默认 `5 deg/s`。
- 急停策略固定为 `disable_motor_output`，`fault_latch=true`。
- VLA 只允许建议/规划，不允许输出 CAN、力矩、电流、速度或裸电机位置。

生成后必须继续运行：

```bash
ros2 run rehab_arm_psoc_bridge validate_patient_profile.py patient_device_profile_template.json --pretty
ros2 run rehab_arm_psoc_bridge export_m33_safety_subset.py patient_device_profile_template.json --pretty
ros2 run rehab_arm_psoc_bridge check_patient_profile_release_gate.py patient_device_profile_template.json --target m33 --pretty
```

注意：模板默认是 `draft`，所以上面的 M33 release gate 应该失败，这是正确现象。只有审核通过、版本号递增、状态变成 `active` 后，`--target m33` 才能通过。

App BLE 包发布前用：

```bash
ros2 run rehab_arm_psoc_bridge check_patient_profile_release_gate.py patient_device_profile_active.json \
  --target app_ble \
  --approved-by clinician_001 \
  --approved-at 2026-05-27T10:00:00+08:00 \
  --expires-at 2026-05-28T10:00:00+08:00 \
  --pretty
```

NanoPi 只缓存 profile、用于仿真/数据采集上下文时用：

```bash
ros2 run rehab_arm_psoc_bridge check_patient_profile_release_gate.py patient_device_profile_active.json \
  --target nanopi_cache \
  --pretty
```

只有 release gate `ok=true` 后，才允许进入对应链路。这个闸门仍然只做 JSON 检查，不连接蓝牙、不发 CAN、不下发 M33。

### 7.3 NanoPi ROS 工作区构建

NanoPi 上优先使用工作区自带脚本构建 ROS 包：

```bash
cd /home/pi/rehab_arm_ros2_ws
./build_ros2.sh --packages-select rehab_arm_psoc_bridge
```

这个脚本会自动 source `/opt/ros/jazzy/setup.bash` 或 `/opt/ros/humble/setup.bash`，并补齐 ROS Python site-packages 路径，避免 `ModuleNotFoundError: No module named 'ament_package'`。

构建后验证：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 pkg executables rehab_arm_psoc_bridge
```

如果要做现场只读验收：

```bash
ACTIVE_REPORT_MOTOR=none SNAPSHOT_SECONDS=2 ECHO_TIMEOUT_SECONDS=8 BUILD_WORKSPACE=0 \
  /home/pi/nanopi_live_telemetry_check.sh
```

合格标准：

- 脚本输出 `PASS: live telemetry path is valid and read-only.`
- 能看到 M33 `0x322`。
- 能收到 `/rehab_arm/motor_state` 和 `/joint_states`。
- `unexpected 0x320 frames` 为空。

如果仿真主机或 NanoPi 只能看到 `/rehab_arm/safety_state`，但 `/rehab_arm/motor_state`、`/joint_states` 没有样本，先做只读 candump，再检查 M33 电机状态帧是否存在：

```bash
timeout 3s candump -L can0 > /tmp/readonly_motor_status_check.candump
ros2 run rehab_arm_psoc_bridge check_m33_motor_status_presence.py \
  /tmp/readonly_motor_status_check.candump \
  --pretty
```

通过标准：

- `valid_m33_motor_status_count > 0`。
- `target_0x320_count = 0`。
- `observed_ids` 至少包含 M33 电机状态 ID `0x330~0x337` 中的一个。

如果只看到 `0x321/0x322`，说明 NanoPi 和 M33 安全心跳链路是通的，但 M33 当前没有发布电机状态帧；这时不要发布轨迹，先让 M33 固件补齐或打开电机状态上报。

正式 bridge 默认还有两道轨迹闸门：

- `require_psoc_ok_for_trajectory=true`：没有 M33/PSoC `motion_allowed=true`，拒绝 `/arm_controller/joint_trajectory`。
- `require_fresh_motor_status_for_trajectory=true`：没有 fresh 的 M33 电机反馈，不把 stale 槽位当成真实姿态，拒绝轨迹。

只有台架调试、且确认现场安全时，才允许临时关闭第二个闸门：

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py \
  --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false \
  -p require_fresh_motor_status_for_trajectory:=false
```

注意：`enable_target_tx=false` 仍然是只读/干跑，不会发 `0x320` 目标。正式发目标前必须恢复 fresh 电机反馈闸门，并由 M33 安全状态机最终放行。

如果要现场快速判断“电机真实反馈源有没有回来”，用只读 readiness 工具：

```bash
timeout 5s candump -L can0 > /tmp/feedback_source_readiness.candump
ros2 run rehab_arm_psoc_bridge feedback_source_readiness.py \
  /tmp/feedback_source_readiness.candump \
  --pretty
```

重点看：

- `raw_motor_feedback_ready=true`：CAN 上已经能看到 3号 CANSimple 或 4~7号灵足主动上报。
- `m33_joint_state_ready=true`：M33 的 `0x330~0x334` 至少有 fresh 样本，仿真主机才可以期待 `/joint_states`。
- `decision=ready_for_ros_joint_states`：可以继续做 ROS 状态链路验证。
- `decision=motor_feedback_source_missing`：不要发轨迹，先查电机侧供电、CAN 分支、共地、终端、电机 ID、驱动状态。
- `target_0x320_count` 必须是 `0`。如果不是 `0`，说明这不是只读采集，不能作为安全 readiness 证据。

也可以直接用 NanoPi 一键脚本，它会保存 can0 状态、candump 和 JSON 报告：

```bash
/home/pi/nanopi_motor_feedback_readiness.sh
```

输出文件默认在：

```bash
/tmp/rehab_arm_feedback_readiness/
```

如果现场确认只允许做非运动查询，可以临时打开查询探测：

```bash
RUN_NON_MOTION_PROBES=1 /home/pi/nanopi_motor_feedback_readiness.sh
```

这个模式只发 CANSimple `Get_Error/Address` 和灵足 `Get_ID` 查询，不发使能、速度、位置、力矩、`0x320` 轨迹目标。若报告里仍然没有 raw feedback，下一步查物理层和电机侧状态，不要继续加 ROS 控制逻辑。

如果纯被动采集 0 帧，但想确认 M33 是否在线，可以只发一次 NanoPi 心跳：

```bash
SEND_M33_HEARTBEAT=1 /home/pi/nanopi_motor_feedback_readiness.sh
```

这个模式只发 `0x321#55` 心跳，用来观察 `0x322` 或 `0x330~0x334` 是否回来；它仍然不发 `0x320` 目标，也不控制电机。

当 readiness 已经通过后，可以做 bridge 干跑轨迹闸门测试：

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash

ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py \
  --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

另一个终端发布最小轨迹：

```bash
ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory \
  "{joint_names: ['shoulder_lift_joint'], points: [{positions: [0.0], time_from_start: {sec: 1, nanosec: 0}}]}"
```

判断：

- 如果 M33 还没有 `motion_allowed=true`，bridge 应拒绝轨迹，并说明原因。
- `enable_target_tx=false` 时，无论接受还是拒绝，都不能出现 `0x320`。
- 只有 dry-run 证明 gate、状态、关节反馈都正确后，才讨论真实 `enable_target_tx=true`。

### 7.4 Linux 仿真主机接入前自检

另一台 Linux 主机接入前，先在该主机上运行仿真环境自检：

```bash
cd ~/rehab_ws_src/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
./build_ros2.sh --packages-select rehab_arm_description rehab_arm_psoc_bridge rehab_arm_sim_mujoco
source install/setup.bash
ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --output sim_readiness_report.json
```

看三个字段：

- `ok=true`：必需项齐全。
- `readiness=ready_with_fallback_sim`：可以先跑简化仿真和数据采集，MuJoCo 还没准备好。
- `readiness=ready_with_mujoco`：可以进入 MuJoCo 仿真。

如果 `ok=false`，先看 `missing_actions`，它会列出缺的模块和建议命令。这个检查只读，不访问 CAN，不发送 `0x320/0x321`，不会命令 M33 或电机。

### 7.5 文档和 Git 维护

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

## 8. 多 AI 联调提示词

明天接入仿真主机、C8T6/传感器、平台和 App 时，统一使用：

- [TOMORROW_INTEGRATION_PROMPTS.md](TOMORROW_INTEGRATION_PROMPTS.md)

里面包含：

- 平台开发 AI 提示词。
- App 开发 AI 提示词。
- ROS/NanoPi/Linux 主线提示词。
- 一天联调 checklist。
- Stop conditions。

联调时优先按文档顺序推进：先 Git 和离线验证，再 NanoPi/CAN/M33/C8T6 数据链路，再平台/App 展示，最后才考虑任何运动测试。
