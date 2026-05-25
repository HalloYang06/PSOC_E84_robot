# 康复外骨骼机械臂踩坑与技巧记录

本文档记录项目中踩过的坑、排查路径、根因、解决方法和以后要记住的技巧。每次遇到新的坑都要补充这里，不要只留在聊天记录里。

## 记录格式

每个坑尽量按这个格式写：

```text
标题:
现象:
环境:
排查:
根因:
解决:
技巧:
相关文件/命令:
状态:
```

## CAN 与硬件

### MCP2518FD 驱动加载了，但没有 can0

现象：

```bash
ip -details link show can0
# Device "can0" does not exist.

lsmod | grep -E "mcp|can"
# mcp251xfd 已加载

dmesg | grep -Ei "mcp251|mcp251xfd|spi3"
# Failed to read Oscillator Configuration Register (osc=0x00000000)
# error -ENODEV: Failed to detect MCP2518FD
```

环境：

- NanoPi M5
- MCP2518FD SPI CAN 模块
- SPI 设备节点能看到，例如 `spi3.0`

排查：

- 内核模块存在不等于 CAN 设备存在。
- `/sys/bus/spi/devices` 能看到 SPI 设备，也不等于 MCP2518FD 芯片通信正常。
- `dmesg` 里 `Failed to read Oscillator Configuration Register` 是关键。

根因：

- 驱动探测 MCP2518FD 失败，可能原因包括供电不稳、晶振/时钟不工作、SPI 接线/片选/中断/设备树配置不对、模块未正确上电。

解决：

- 先查供电和共地。
- 再查 SPI 的 CS/SCK/MISO/MOSI 和 INT。
- 再查设备树里的 oscillator frequency、interrupt GPIO、spi bus、cs。
- 不要只看 `lsmod`，必须看 `ip link` 和 `dmesg`。

技巧：

- `lsmod` 只能说明驱动加载，不说明设备探测成功。
- `can0` 不存在时，优先看 `dmesg`，不要直接改 ROS 代码。

相关命令：

```bash
ip -details link show can0
lsmod | grep -E "mcp|can"
ls /sys/bus/spi/devices
dmesg | grep -Ei "mcp251|mcp251xfd|spi"
```

状态：

- 已记录。后续如果再次出现，按硬件/设备树优先排查。

### CAN 总线调试要先证明有心跳

现象：

- ROS 节点或控制脚本发命令，但电机不动。
- 不确定是协议错、CAN 线错、波特率错还是目标节点不在线。

排查：

- 先把 `can0` 拉起来。
- 先 `candump` 或 `nanopi_can_master.py monitor`。
- 对 CANSimple 节点，先找 heartbeat。

当前已知：

- `node_id=3` 的 CANSimple heartbeat 是标准帧 `0x061`。

技巧：

- 没看到 heartbeat 前，不要调控制参数。
- 没看到 RX 前，不要急着改协议 payload。
- 有一个独立观察者很重要，例如 `candump can0`。

相关命令：

```bash
ip -details link show can0
candump can0
~/nanopi_can_master.py monitor --iface can0 --seconds 5
```

状态：

- 已记录。正式控制前继续坚持这个顺序。

## CAN 协议与电机 ID

### 不要把旧文档 CAN ID 当成当前真实链路

现象：

- 旧文档里出现过旧规划 ID。
- 当前现场真实链路已经变成 `node_id=3`、`motor_id=4/5/6/7`、`0x320/0x321/0x322`、`0x7C2/0x7C3`。

根因：

- 项目经历过多轮方案变化，旧规划文档和当前现场硬件链路不一致。

解决：

- 主 README 和主架构文档只记录当前真实链路。
- 旧文档只能作为历史资料，不能作为当前实现依据。

技巧：

- 当前 CAN ID 只认主 README 和 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
- 机械关节绑定还没确认前，不要把 `motor_id=4/5/6/7` 写死为正式关节。

状态：

- 已从主 README 和主架构文档移除旧规划 ID。

### 调试直控协议不能进入正式 ROS bringup

现象：

- `nanopi_can_master.py` 能直接让电机动。
- 容易误以为正式 ROS 节点也应该直接发同样的电机 CAN 帧。

根因：

- 调试工具用于 bring-up 和诊断，正式系统需要 M33 做安全责任方。

解决：

- 调试路径：

```text
NanoPi debug tool -> direct CANSimple/private motor frame -> motor
```

- 正式路径：

```text
JointTrajectory -> NanoPi -> CAN 0x320/0x321 -> M33 -> motor
```

技巧：

- 能直控电机只说明 CAN 和协议可用，不说明正式安全链路完成。
- ROS bringup 不启动 `private` 或 `cansimple` 直控运动逻辑。

状态：

- 已写入 README 和架构文档边界。

## ROS2 与 Python 节点

### `ros2 run` 找不到 Python 节点

现象：

```bash
ros2 run rehab_arm_sim_mujoco mujoco_sim_node
# 找不到可执行

ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py
# 也可能找不到

ls install/rehab_arm_sim_mujoco/lib/rehab_arm_sim_mujoco
# 能看到 mujoco_sim_node.py
```

排查：

- `ros2 pkg executables rehab_arm_sim_mujoco` 是否能列出节点。
- 源文件是否有 shebang。
- 源文件是否有 executable bit。

根因：

- `install(PROGRAMS ...)` 安装 Python 脚本时，脚本本身需要可执行权限。
- Windows 工作区创建文件时容易没有 Linux executable bit。

解决：

```bash
git add --chmod=+x rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py
chmod +x /home/pi/rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py
colcon build --symlink-install --packages-select rehab_arm_sim_mujoco
source install/setup.bash
ros2 pkg executables rehab_arm_sim_mujoco
```

技巧：

- 看到 install 目录有文件，不代表 `ros2 run` 能发现它。
- 先用 `ros2 pkg executables 包名` 判断 ROS 认不认识这个可执行。

状态：

- `rehab_arm_sim_mujoco` 已修复 executable bit，`ros2 pkg executables` 能看到 `mujoco_sim_node.py`。
- `rehab_arm_control` 也遇到同类风险，已给 `demo_trajectory_node.py` 和 `vla_task_planner_node.py` 设置 executable，`ros2 pkg executables rehab_arm_control` 能看到两个节点。

### `timeout` 结束 ROS2 Python 节点时出现 shutdown 异常

现象：

```text
rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called
rclpy.executors.ExternalShutdownException
```

环境：

- ROS2 Jazzy
- Python `rclpy`
- 用 `timeout 4 ros2 run ...` 做短时间运行测试

根因：

- `timeout` 结束进程时，ROS context 可能已经 shutdown。
- 节点 finally 里再次 `rclpy.shutdown()` 会触发二次 shutdown。
- Jazzy 可能抛 `ExternalShutdownException`。

解决：

- shutdown 前检查：

```python
if rclpy.ok():
    rclpy.shutdown()
```

- spin 捕获：

```python
from rclpy.executors import ExternalShutdownException

try:
    rclpy.spin(node)
except (KeyboardInterrupt, ExternalShutdownException):
    pass
```

技巧：

- `timeout` 是很好的节点冒烟测试工具，但要让节点优雅处理外部终止。
- 运行测试通过不应留下 Python traceback。

状态：

- 已修复并在 NanoPi 上验证：
  - `timeout 4 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py` 能干净结束。
  - 节点启动日志正常，无 Python traceback。
- `rehab_arm_psoc_bridge` 还额外遇到 `rclpy._rclpy_pybind11.RCLError: failed to initialize wait set`，已通过捕获 `RCLError` 修复，`timeout 4 ros2 run rehab_arm_psoc_bridge ...` 能干净结束。

### Bridge 打印 TX heartbeat 不代表总线 ACK 成功

现象：

`rehab_arm_psoc_bridge` 启动后能打印：

```text
PSoC CAN bridge ready on can0
TX 321 01
```

但 CAN 统计显示：

```text
TX packets: 0
TX errors/dropped 增加
```

并且没有看到 M33 的 `0x322` 回复。

环境：

- NanoPi `can0`
- 1Mbps
- `ERROR-ACTIVE`
- `rehab_arm_psoc_bridge` 只发 heartbeat，不发轨迹

根因：

- ROS 节点成功调用 `sock.send()` 只能说明帧写入 SocketCAN。
- `TX packets` 不增加且 dropped 增加，说明帧没有成功发到总线或没有被 ACK。
- 可能原因包括 M33/PSoC 没上电、没接入总线、固件未运行、波特率不一致、总线缺少 ACK 节点、接线/终端异常。

解决：

- 不要继续发轨迹。
- 先用原始工具对照：

```bash
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
candump can0
ip -details -statistics link show can0
```

- 只有看到 `0x322` 回复或 TX packets 正常增长，才算 heartbeat 链路通过。

技巧：

- 应区分“应用层尝试发送”和“CAN 总线发送成功”。
- 对 CAN heartbeat 验证，至少要看一种总线层证据：`0x322` 回复、TX packets 增长、独立设备 candump 观察到帧。

状态：

- bridge 应用层启动和 heartbeat 尝试已通过。
- M33 回复/总线 ACK 未通过，下一步排查 PSoC/M33 在线状态和 CAN ACK。

### M33 heartbeat 未回复时要让 ROS 明确暴露 limited 状态

现象：

- `rehab_arm_psoc_bridge` 能打印 heartbeat：

```text
TX 321 01
TX 321 02
TX 321 03
TX 321 04
```

- 但没有 `0x322` 回复。
- `nanopi_can_master.py heartbeat --iface can0 --seq 7 --wait 1` 也只看到 TX，没有 RX。
- `can0` TX packets 不增加，TX errors/dropped 增加。

根因：

- 当前 M33/PSoC heartbeat/status 链路未通，可能是硬件未在线、固件未运行 heartbeat 任务、波特率/接线/ACK 问题。
- 软件如果只打印 TX，操作者容易误以为 bridge 正常。

解决：

- 在 `rehab_arm_psoc_bridge` 增加：
  - `status_timeout_sec` 参数，默认 `2.5`
  - `heartbeat_tx_count`
  - `status_rx_count`
  - `last_status_time`
  - 诊断定时器
- 当发出 heartbeat 但没有收到 `0x322` 时，发布：

```json
{"state":"limited","detail":"no PSoC status after 4 heartbeats","source":"psoc_bridge"}
```

技巧：

- bridge 的健康状态不能只看进程是否启动。
- PSoC/M33 未回复时，ROS safety topic 必须显式表达 limited/fault，方便 App、工作站和数据记录系统发现问题。

状态：

- 已实现并在 NanoPi 上验证 `/rehab_arm/safety_state` 能输出 limited。

### PSoC/M33 没有 ACK/0x322 时先确认电池电量

现象：

- NanoPi bridge 或调试脚本能尝试发送 heartbeat：

```text
TX 321 01
```

- `nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1` 没有收到 `0x322`。
- `can0` 仍是 `ERROR-ACTIVE`，但 TX packets 不增长，TX dropped/errors 增加。

环境：

- NanoPi `can0`
- 1Mbps classic CAN
- PSoC/M33 作为正式控制主站和 heartbeat/status 回复方

排查：

- ROS2 bridge 已能启动并调用 SocketCAN 发送。
- `can0` 已经 UP，说明 NanoPi 侧 CAN 接口存在。
- 没有 `0x322`，且 TX packets 不增长，说明总线层没有成功 ACK。

根因：

- 用户现场确认：电池没电，导致 PSoC/M33 或相关 CAN 节点未正常在线/供电不足，因此无法 ACK NanoPi heartbeat，也无法回复 `0x322`。

解决：

- 先给电池充电或更换电池。
- 确认 PSoC/M33、CAN 收发器和电机侧节点都正常上电。
- 再复测：

```bash
ip -details -statistics link show can0
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
```

技巧：

- CAN “发不出去/没有 ACK” 不一定是协议错，电源是第一检查项。
- 看到 `TX 321` 只能说明应用层尝试发送；看到 `0x322`、TX packets 增长或独立 CAN 工具观察到帧，才算总线层验证通过。

状态：

- 已确认并复测通过。
- 电池恢复后，`nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1` 能收到：

```text
RX STD 0x00000322 [8] A5 01 07 00 48 EA 6D 00
```
- 2026-05-25 设备重新上电后再次复测：
  - `can0` 拉起到 `UP/LOWER_UP/ERROR-ACTIVE/1Mbps`。
  - 手动发送 `0x321` seq 1/2/3，均收到 `0x322`。
  - `can0` 错误计数器 `tx 0 rx 0`，`bus-off/error-pass` 均为 0。

### 上电后 can0 可能存在但仍是 DOWN/STOPPED

现象：

- NanoPi 上能看到 `can0`，但它还不能收发：

```text
can0: <NOARP,ECHO>
state DOWN
can state STOPPED
```

环境：

- NanoPi M5
- MCP2518FD / `mcp251xfd`
- classic CAN 1Mbps

处理：

```bash
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details link show can0
```

通过标准：

```text
can0: <NOARP,UP,LOWER_UP,ECHO>
can state ERROR-ACTIVE
bitrate 1000000
berr-counter tx 0 rx 0
```

技巧：

- “设备存在”不等于“总线已工作”；每次上电后先确认 `UP/LOWER_UP/ERROR-ACTIVE`。
- `ERROR-ACTIVE` 且错误计数为 0 后，再做 heartbeat，不要直接发轨迹。

状态：

- 2026-05-25 已验证。

- ROS `rehab_arm_psoc_bridge` 也能发布 PSoC 来源的 `ok` safety state，说明这次无回复确实是供电问题，不是 ROS bridge 协议问题。
- 后续 bridge 安全门控测试中再次出现没电：正常 `status_timeout_sec` 下 bridge 持续 `no PSoC status after N heartbeats`，用户确认又没电了。低电量时停止测试，先恢复供电。
- 2026-05-25 用户烧录 M33 后，NanoPi `192.168.2.66` 真实局域网不可达；后续用户确认原因是忘记给设备上电。上电后 NanoPi SSH 恢复，`can0` 可拉起并收到 M33 V2 `0x322`。

技巧补充：

- 烧录完成不等于系统已上电运行；烧录后测试前先确认 NanoPi、M33、CAN 收发器三者都已上电。
- 如果 M33 串口在 Windows 上可见，但 NanoPi 不在线，说明“调试器/烧录器在线”和“整机控制链路在线”不是一回事。

### Bridge 门控拒绝轨迹时要同时看日志和 candump

现象：

- 测试 `rehab_arm_psoc_bridge` 轨迹安全门控时，发布了 `/arm_controller/joint_trajectory`。
- PSoC/M33 无新鲜 `0x322 ok` 状态。

验证：

- bridge 日志出现：

```text
safety limited: rejected trajectory: no PSoC status received
```

- 同时 `candump can0,320:7FF` 没有任何输出。

结论：

- 这表示 bridge 在不安全状态下拒绝轨迹，并且没有发送 `0x320`，符合穿戴设备“默认不动”的要求。

技巧：

- 只看 ROS topic 可能受发现时序影响；关键安全测试要同时看节点日志和 CAN 原始帧。
- 拒绝轨迹时的验收标准不是“有 limited 日志”一个条件，还要确认总线上没有 `0x320`。

状态：

- 已在 NanoPi 非运动条件下验证通过。
- 电池恢复后又验证了一种 PSoC 在线但轨迹超限的情况：

```text
safety limited: trajectory point 0 joint shoulder_lift_joint 99.000 outside [-0.700, 1.400]
```

- 同时 `candump can0,320:7FF` 为空，说明超限拒绝发生在发送 `0x320` 之前。

### 合法轨迹默认也要 dry-run，不要默认发送 0x320

现象：

- PSoC/M33 已经回复 `0x322 ok`。
- 轨迹也在软件限位内。
- 但 M33 侧 `0x320` 解析、日志、限幅和拒绝原因还没有完成对照。

解决：

- `rehab_arm_psoc_bridge` 增加 `enable_target_tx`，默认 `false`。
- 默认情况下合法轨迹只打印：

```text
DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000
```

- `candump can0,320:7FF` 应为空。

技巧：

- 对穿戴设备，合法轨迹也不等于可以发到控制主站；必须先有 M33 侧日志和安全裁决可观察。
- 只有在 M33 日志固件准备好、用户确认烧录并允许后，才临时打开 `enable_target_tx:=true`。

状态：

- 已在 NanoPi 上验证 dry-run：合法单关节轨迹只生成一个 shoulder dry-run 目标，没有发送 `0x320`。
- 同时修正了单关节轨迹会给未命令关节生成目标的问题。

### 对照 M33 日志前先用解码工具统一 payload 理解

现象：

- NanoPi dry-run 会打印 `DRY-RUN 320 ... data=0300390005000000`。
- M33 侧后续也需要解析同一组 bytes。
- 如果双方对端序、单位、缩放或关节编号理解不一致，可能出现日志看似正常但目标值错误。

解决：

- 新增协议文档 `docs/PSOC_CAN_PROTOCOL_V1.md`。
- 新增解码工具：

```bash
ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000
```

已验证输出：

```text
joint_id: 0
joint_name: shoulder_lift_joint
deg_x10: 57
target_deg: 5.70000
target_rad: 0.09948
rpm: 5
torque_ma: 0
```

技巧：

- M33 串口日志应按同样字段打印，逐项对照。
- 对照通过前不要打开 `enable_target_tx:=true`。

状态：

- 本地和 NanoPi 均已验证解码工具。
- 也已新增并验证编码工具：

```bash
ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1
```

- 输出 payload `0300390005000000`，再用解码工具能反查为同一目标。
- 超限输入会被编码工具拒绝，不输出 payload。

### M33 日志固件第一版必须 logging-only

现象：

- 下一步需要 M33 侧接收真实 `0x320`，但系统是穿戴设备，不能因为“只是对照协议”就让电机动。

解决：

- 新增 `docs/M33_0X320_LOGGER_GUIDE.md`。
- M33 当前阶段收到 `0x320` 后只做：
  - 解析 payload。
  - 打印字段。
  - 打印 `decision/reason/safety_state`。
- 默认 `decision=reject`，`reason=logging_only_no_motor_output`。

技巧：

- 在 M33 日志、限幅、安全状态机全部可观察前，不要让 M33 把 `0x320` 连接到电机执行层。
- 需要烧录时由用户烧录；烧录前 NanoPi 保持 `enable_target_tx=false`。

状态：

- 已完成 M33 logging-only 参考指南，尚未烧录 M33。

### M33 安全判断不能长期藏在打印函数里

现象：

- M33 第一版 logging-only 固件能打印 heartbeat、joint、limit、rpm、torque 检查结果。
- 但这些判断最初集中在 `ctrl_log_ros_command_only()` 中，容易让人误解成“靠打印做安全”。

根因：

- 第一阶段为了确认 M33 是否正确解析 `0x320`，先把所有字段和判断都打印出来。
- 这适合做 bring-up 对照，但不适合成为正式安全状态机。

解决：

- 在 M33 `applications/control/control_layer.c` 中新增结构化安全评估：
  - `control_ros_safety_assessment_t`
  - `ctrl_assess_ros_command_safety()`
  - `CONTROL_ROS_SAFETY_*`
  - `CONTROL_ROS_DECISION_*`
  - `CONTROL_ROS_REJECT_*`
- 让安全判断先生成 `state/decision/reason`，日志函数只输出这个结果。
- 当前仍保持 `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`，所以合法帧也会 `decision=reject`，最终 `no_motor_output`。

技巧：

- bring-up 阶段可以多打印，但安全判断必须能脱离打印函数独立存在。
- 后续真实控制路径只能消费结构化 `assessment`，不能重新写一套散乱判断。
- 每次新增安全条件，要先进 `ctrl_assess_ros_command_safety()`，再考虑日志和状态上报。

状态：

- 本地 M33 已完成第一版结构化改造并编译通过，等待烧录后复测。
- 用户烧录后已完成非运动复测：合法 `0x320` 单帧得到 `safety_state=logging_only decision=reject reason=logging_only_no_motor_output` 和 `final action=no_motor_output logging_only=1`，说明安全评估已经脱离纯打印并形成结构化结果。

### 发送真实 0x320 单帧时必须同时看 NanoPi TX 和 M33 串口

现象：

- 用户已烧录 M33 logging-only 固件，并确认电机驱动电源断开。
- NanoPi 临时打开 `enable_target_tx:=true` 发单帧 `0x320`。

NanoPi 侧已验证：

```text
TX 320 0300390005000000
can0  320   [8]  03 00 39 00 05 00 00 00
```

技巧：

- 这只能证明 NanoPi 和 CAN 总线发出了 `0x320`，不能证明 M33 正确解析。
- 下一步必须看 M33 串口日志是否包含 `RX 320 dlc=8 data=0300390005000000`。
- 如果 M33 没有日志，优先查 M33 CAN filter、标准帧/扩展帧配置、DLC、CAN RX 回调是否被调用。
- 如果 M33 字段不一致，优先查 little-endian、字段偏移和单位缩放。

状态：

- NanoPi/CAN 侧单帧发送已通过。
- 已从本机 Windows `KitProg3 USB-UART (COM26)` 读取到 M33 日志：

```text
[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22
```

- 说明 M33 收到了 `cmd=3 joint=0`，但当前固件不是 logging-only 对照格式，而且可能进入了 direct apply 路径。
- 已停止继续发送 `0x320`，等待 M33 固件改为 logging-only。

### M33 出现 direct apply 日志时必须停止 0x320 测试

现象：

```text
[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22
```

环境：

- 电机驱动电源已断开。
- NanoPi 单帧发送 `0x320 data=0300390005000000`。
- M33 串口通过本机 Windows `COM26` 读取，115200 baud。

判断：

- `cmd=3 joint=0` 说明 M33 已经收到并识别了部分字段。
- `direct apply failed` 说明 M33 当前代码路径可能尝试把 ROS/CAN 命令交给控制应用层。
- 这不符合当前 logging-only 阶段要求。

处理：

- 不再继续发 `0x320`。
- 电机驱动继续断电。
- M33 固件应改为收到 `0x320` 后只打印字段和安全拒绝：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 joint_id=0 joint=shoulder_lift_joint deg_x10=57 target_deg=5.7 target_rad=0.09948 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output
safety_state=limited
```

状态：

- 已修复并复测通过。
- 用户烧录 M33 logging-only 固件后，再次通过 ROS bridge 发送同一个单帧 `0x320`。
- M33 串口输出：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output safety_state=limited
```

- 未再出现 `ros cmd direct apply failed`。
- 本轮未给电机驱动上电，未做运动测试。

### M33 logging-only 改完后必须本地编译通过再让用户烧录

现象：

- 需要把 M33 `0x320` 从 direct apply 路径切到 logging-only。
- 直接在命令行运行 `mingw32-make -C Debug all -j2` 时最初找不到 `arm-none-eabi-gcc`。

环境：

- Windows 本机工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`
- RT-Thread Studio 自带 ARM GCC。

排查：

- 本机找到了可用编译器：

```text
D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin\arm-none-eabi-gcc.exe
```

解决：

- 只在当前 PowerShell 会话临时加 PATH，不改系统环境：

```powershell
$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path
mingw32-make -C Debug all -j2
```

- 编译通过后才允许进入“请用户烧录”阶段。

技巧：

- 不要让用户烧录未经本地编译验证的固件。
- logging-only 模式下 `0x320` 必须在解析后立即返回，不能进入 `ctrl_apply_ros_command()` 或任何电机控制路径。
- 短帧日志打印应先把 payload 补零到 8 字节，避免串口日志读到旧数据。

状态：

- M33 本地编译已通过。
- 用户已烧录并完成单帧对照验证。
- 本次新增的安全补丁目标日志为：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output safety_state=limited
```

### Windows 到 NanoPi 远程脚本要注意 CRLF

现象：

- 从 Windows PowerShell 用 here-string 通过 SSH 发送多行 bash 脚本到 NanoPi。
- 脚本末尾执行 `ip -details -statistics link show can0` 时，远端报：

```text
Device "can0\r" does not exist.
```

根因：

- Windows CRLF 换行里的 `\r` 被带到了 bash 参数中，`can0` 变成了 `can0\r`。

解决：

- 硬件/CAN 关键命令复查时，用单独 SSH 命令或先去掉 CRLF。
- 本次单独复查：

```bash
ip -details -statistics link show can0
```

确认 `can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。

技巧：

- Windows 远程发多行 shell 脚本时，失败信息里如果出现奇怪的路径或设备名，要怀疑隐藏的 `\r`。
- 对安全验收相关的最后状态，尽量单独再查一次，避免被脚本换行问题污染结论。

状态：

- 已记录。本次 `0x320` 对照本身不受影响，CAN 和 M33 串口日志均已验证。

### Windows 的 Meta 虚拟网卡会误导 NanoPi 连通性判断

现象：

- 用户烧录 M33 后准备复测 NanoPi/M33 链路。
- `ssh pi@192.168.2.66` 一开始超时，后续出现 `kex_exchange_identification: Connection closed by remote host`。
- `Test-NetConnection 192.168.2.66 -Port 22` 显示 `TcpTestSucceeded=True`，但详情里源地址是：

```text
InterfaceAlias : Meta
SourceAddress  : 198.18.0.1
NextHop        : 198.18.0.2
```

排查：

- 本机真实局域网地址是 `192.168.2.9` 和 `192.168.2.10`。
- 强制从无线源地址测试：

```powershell
ssh -b 192.168.2.9 -o ConnectTimeout=8 pi@192.168.2.66 "hostname"
ping -S 192.168.2.9 -n 1 192.168.2.66
```

- 结果真实无线源地址到 `192.168.2.66` 超时，ARP 中也没有 `192.168.2.66`。

根因：

- Windows 路由把未绑定源地址的连接送进了 `Meta/198.18.0.x` 虚拟网卡或代理路径。
- 这个路径上的端口连通性不能证明 NanoPi 在真实 `192.168.2.0/24` 局域网在线。

解决：

- 验证 NanoPi 时优先强制源地址或明确真实网卡：

```powershell
ssh -b 192.168.2.9 pi@192.168.2.66 "hostname"
ping -S 192.168.2.9 -n 3 192.168.2.66
arp -a 192.168.2.66
```

- 只有真实 `192.168.2.x` 源地址能 SSH 到 NanoPi，才继续 `can0`、heartbeat 和 `0x320` 测试。

技巧：

- `Test-NetConnection` 通过时一定看 `InterfaceAlias` 和 `SourceAddress`。
- 不要把 `198.18.0.x` 代理/虚拟网卡结果当作 NanoPi 局域网已恢复。
- 网络路径不确定时，不发 CAN，不做硬件测试。

状态：

- 已记录。当前 M33 已烧录，但 NanoPi 真实局域网 SSH 未恢复，因此未发送 `0x321/0x320`。

### ROS bridge 验证前要清理旧进程

现象：

- 已同步并重建新版 `rehab_arm_psoc_bridge`。
- `ros2 topic echo /rehab_arm/safety_state` 仍看到旧格式 JSON，没有 `protocol_version` 字段。

排查：

- NanoPi 上还有旧 bridge 进程：

```bash
pgrep -af 'psoc_can_bridge_node|rehab_arm_psoc_bridge'
```

根因：

- CAN raw socket 和 ROS topic 都可能同时存在多个 bridge 进程。
- 旧进程继续发布 `/rehab_arm/safety_state`，会让测试看起来像新版没有生效。

解决：

```bash
kill <旧 bridge pid>
colcon build --symlink-install --packages-select rehab_arm_psoc_bridge
```

技巧：

- 每次验证 bridge 行为前先 `pgrep`。
- 如果怀疑是旧进程，清理后再看 `candump`、bridge 日志和 ROS topic。

状态：

- 已记录。本次清理旧进程后，NanoPi 能看到新版 `0x322` parser 输出 `protocol_version:1`。

### `ros2 topic echo` 太早启动时显式指定消息类型

现象：

```text
WARNING: topic [/rehab_arm/safety_state] does not appear to be published yet
Could not determine the type for the passed topic
```

环境：

- 远程脚本里先启动 `ros2 topic echo --once`，再启动短时 bridge。
- topic 发布器还没完成发现，echo 无法推断消息类型。

解决：

```bash
ros2 topic echo --once /rehab_arm/safety_state std_msgs/msg/String
```

技巧：

- 短时自动化测试里显式指定 ROS message type，比等待 topic discovery 更稳定。
- 如果 topic 本身是 JSON 字符串，抓到一条后再看里面的 `state/protocol_version/detail`。

状态：

- 已记录。后续 bridge topic 验证优先显式指定 `std_msgs/msg/String`。

### V2 status limited 是安全通过，不是可运动

现象：

- M33 V2 status 固件烧录后，NanoPi 能收到：

```text
RX 322 [8] a501070001010a00
```

- ROS `/rehab_arm/safety_state` 输出：

```json
{"protocol_version":2,"state":"limited","control_mode":"logging_only","detail":"logging_only_no_motor_output"}
```

判断：

- 这说明 M33 在线、heartbeat/status 链路正常、V2 parser 正常。
- 但 `state=limited` 和 `control_mode=logging_only` 明确表示当前不是可运动状态。

处理：

- 当前阶段只允许继续做日志、安全状态机和单帧对照。
- 不要因为 heartbeat/status 通过就给电机驱动上电或发布运动轨迹。

状态：

- 已验证并记录。下一步继续设计 M33 `0x320` 安全审核日志，默认仍不输出电机控制。

补充：

- M33 上报 `limited/logging_only` 时，NanoPi bridge 默认会拒绝轨迹，这是正确安全行为。
- 如需做 M33 logging-only 审计单帧测试，才可以临时使用：

```bash
-p enable_target_tx:=true -p require_psoc_ok_for_trajectory:=false
```

- 这个参数组合只能用于电机驱动断开、外骨骼不穿戴、M33 固定拒绝输出的单帧审计；不能作为正式运动 bringup 配置。

### ROS 关节编号和 M33/电机编号不要混用

现象：

- NanoPi bridge 的 `0x320` payload 使用 ROS 关节编号，例如 `shoulder_lift_joint -> joint_id=0`。
- M33 控制层和底层电机驱动里可能还有电机 ID、CANSimple node_id 或私有 MIT motor_id。
- 如果把 ROS joint_id 当成真实电机 ID，后续一旦打开真实控制路径，可能驱动错误关节。

正确边界：

- `0x320` 的 `joint_id` 当前是 ROS 5 关节 0-based 逻辑编号。
- 当前已知真实电机链路仍只记录为 `node_id=3` 和 `motor_id=4/5/6/7`，机械关节绑定待确认。
- M33 必须保存一张独立的“ROS joint_id -> 安全审核 -> 真实电机通道”映射表。
- 在映射表、方向、限位、急停和单关节空载验证完成前，不允许把 `0x320` 直接接到底层电机输出。

技巧：

- 串口日志要同时打印 `joint_id` 和最终映射到的 motor/channel；没有映射时打印 `joint_known=0` 或拒绝原因。
- 当前 logging-only 审核日志里的 `limit_01deg` 是 ROS 关节限位，不等于电机原始编码器限位。
- 真实运动前必须逐个关节确认方向：正角度命令、机械运动方向、编码器反馈方向三者一致。

状态：

- 已记录。当前 M33 安全审核日志仍固定 `decision=reject`，不会进入真实电机控制路径。

### 没硬件时也要守住协议回归测试

场景：

- 用户不在现场，不能给硬件上电。
- 仍然可以推进不会触碰 CAN/电机的协议工具质量。

做法：

- 新增离线单元测试：

```bash
python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v
```

- 覆盖 `encode_psoc_cmd.py` 和 `decode_psoc_cmd.py`。

状态：

- 已验证 10 个测试全部通过。

### NanoPi 看不到 M33 串口时不要误判为 M33 没日志

现象：

- 用户让 NanoPi 侧查看 M33 日志。
- NanoPi 上没有 `/dev/ttyUSB*`、`/dev/ttyACM*`、`/dev/serial/by-id/*`。
- 也没有正在运行的 `minicom/picocom/screen` 串口查看进程。

结论：

- M33 串口没有接到 NanoPi，不能从 NanoPi 直接查看。
- 串口日志大概率在用户烧录/调试用电脑或调试器连接的串口上。

同时确认：

```text
TX STD 0x00000321 [1] 04
RX STD 0x00000322 [8] A5 04 07 00 F6 E7 04 00
```

- `can0` 为 `ERROR-ACTIVE`，错误计数器 `tx 0 rx 0`，说明 CAN 链路仍然正常。

技巧：

- “看不到串口日志”要先分清是 M33 没打印，还是串口根本没接到当前主机。
- 如果要让 NanoPi 查看 M33 日志，需要把 M33 UART/USB-CDC 接到 NanoPi，或者提供调试电脑远程访问。

### SSH 远端 bash 里后台任务会影响 source 环境

现象：

一条 SSH 命令里先 source ROS 环境，再后台启动节点，再执行 `ros2 topic`，结果后面的命令找不到 `ros2`：

```text
bash: line 1: ros2: command not found
timeout: failed to run command 'ros2': No such file or directory
```

排查：

- 原命令大致是：

```bash
cd ws && . /opt/ros/jazzy/setup.bash && . install/setup.bash && timeout 10 ros2 run ... & pid=$!; ros2 topic list
```

- `&` 的优先级导致前面的链路被放进后台，后面的 `ros2 topic list` 没有继承 source 后的环境。

解决：

- 只把需要后台运行的节点命令放进括号：

```bash
cd /home/pi/rehab_arm_ros2_ws
. /opt/ros/jazzy/setup.bash
. install/setup.bash
(timeout 10 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py >/tmp/rehab_sim_node.log 2>&1) &
pid=$!
sleep 2
ros2 topic list
ros2 topic echo --once /joint_states
kill $pid 2>/dev/null || true
```

技巧：

- SSH 远端一行命令里混用 `&&`、`;`、`&` 时要特别小心。
- 后台运行 ROS 节点时，用 `( ... ) &` 包住节点命令，避免把环境 setup 链路也放进后台。
- 从 Windows PowerShell 通过 SSH 管道发送多行 bash 脚本时，注意去掉 CRLF 里的 `\r`；否则远端可能出现路径后带 `$'\r'` 或临时脚本找不到的问题。
- 不要在 source ROS setup 前开启 `set -u`；`/opt/ros/jazzy/setup.bash` 可能访问未定义环境变量。

状态：

- 已记录。后续远程测试 ROS 节点时使用括号后台法。

## 架构边界

### App BLE 和 HTTP 容易混

现象：

- 文档容易写成 App 通过 HTTP 控制 NanoPi，再控制电机。
- 但实际 App 的近端实时控制是 BLE 连接英飞凌。

正确边界：

```text
实时近端链路: App <-> BLE <-> 英飞凌 M33/M55
高层 AI 链路: App <-> HTTP <-> NanoPi/OpenClaw
```

技巧：

- BLE 可以承载训练操作、状态显示、标注、急停请求。
- HTTP/OpenClaw 只做高层 AI、报告、训练建议和远程服务。
- HTTP 不做实时电机闭环控制。

状态：

- 已写入 README 和主架构文档。

### 总服务器不是实时控制链路

现象：

- 项目里还有一个总服务器，当前是开发工具服务器，未来会扩展为总控台。
- 容易误放到控制闭环里。

正确边界：

- 总服务器管理设备、数据、模型、实验、远程协作。
- 总服务器不直接发 CAN。
- 总服务器不绕过 M33。
- 总服务器掉线时，本地真机控制和安全仍要能工作。

技巧：

- 总服务器接口先按非实时设计。
- 它可以下发配置、任务、报告请求，但不能直接下发底层电机控制量。

状态：

- 已写入 README、主架构文档和进度文档。

### 全量数据上传主链路不要分散到多个实时节点

现象：

- M33、M55、NanoPi、App、仿真主机和总服务器都可能看到一部分数据，容易设计成每个节点各自上传。
- 这样会带来 session 对齐困难、时间戳不一致、断网补传复杂、职责边界混乱。

正确边界：

- 第一版全量上传主链路选 NanoPi。
- NanoPi 汇总 M33 的电机、传感、安全和 M55 模型摘要，再同步给仿真主机和总服务器。
- M55 WiFi 可上传语音、OpenClaw、模型摘要或诊断信息，但不承担第一版全量数据主链路。
- App 可做账号、报告和非实时标注同步，但实时近端状态仍由 M33 BLE 提供。

技巧：

- 先用 NanoPi 做 session_id、时间戳对齐、本地落盘和断网补传。
- 高频数据先本地记录，服务器保存索引和文件，不把服务器放进实时闭环。

状态：

- 已写入 README、主架构文档、使用手册和数据流图。

### VLA 数据来源要在高层汇聚，不能直接吃 CAN

现象：

- 容易把 VLA 想成直接读取 CAN 数据并输出控制命令。
- 这会让高层 AI 越过仿真、规划和 M33 安全边界。

正确边界：

- VLA 输入来自服务器历史数据、仿真主机视觉/仿真状态、App 用户目标和 NanoPi 汇总的机器人状态。
- VLA 输出只能是 `task_goal`、任务约束或规划建议。
- VLA 不直接发 CAN，不输出电机力矩、速度、电流或裸位置命令。

技巧：

- VLA 输出后必须经过运动规划器生成 `JointTrajectory`。
- `JointTrajectory` 再经 NanoPi 到 M33，由 M33 做最终安全审核。

状态：

- 已写入 README、主架构文档、使用手册和数据流图。

### 远程 VLA 适合复杂任务分解，不适合底层实时控制

现象：

- 当 VLA、仿真主机和 NanoPi 不在同一局域网时，VLA 只能通过服务器接入。
- 这条链路有网络延迟和抖动，但复杂任务又需要视觉、语音、历史上下文和状态汇聚。

正确边界：

- NanoPi 采集摄像头关键帧、目标/遮挡物摘要和机器人状态，上传服务器。
- M55/英飞凌采集语音，上传语音文本、音频摘要和模型结果。
- 服务器把视觉、语音、机器人状态、历史数据和标注上下文提供给 VLA。
- VLA 输出复杂任务计划，例如“先移开遮挡物，再拿目标物品”。
- 服务器下发到 NanoPi 的是分段任务、阶段目标或训练配置，不是 CAN 帧或底层电机命令。

技巧：

- 远程 VLA 做“任务理解和任务分解”，本地 NanoPi/仿真主机做轨迹生成，M33 做安全裁决。
- 被遮挡目标任务应拆成可验证阶段：识别遮挡物、规划移开遮挡物、确认目标可见、再规划接近/拿取目标。
- 每个阶段都要可取消、可超时、可人工确认。

状态：

- 已写入 README、主架构文档、使用手册和新版数据流图。

## 文档维护技巧

### 进度和踩坑要分开

规则：

- `docs/PROJECT_PROGRESS.md` 记录当前进展、验证结果、下一步。
- `docs/TROUBLESHOOTING_AND_LESSONS.md` 记录踩坑、排查方式、技巧。
- 架构改变写 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
- 面向新读者的入口写 `README.md`。

技巧：

- 进度文档回答“现在做到哪里”。
- 踩坑文档回答“以后遇到同类问题怎么少走弯路”。
