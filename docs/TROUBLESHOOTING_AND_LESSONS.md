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

### 0x320 的 joint id 是 ROS 关节号，不是电机 ID

现象：

- 发送 `0x320#03072C0103000000` 试图让 7 号电机到 `+30°`，现场没有动。
- CAN 上能看到 M33 在线、`0x320` 已发送、7 号 active-report 存在，但 `0x180007FD` 和 `0x336` 没有随目标变化。
- 直接用 `nanopi_can_master.py private speed --motor 7 --vel 0.30 --kd 1.0`，7 号能动，原始反馈和 M33 `0x336` 都变化。

环境：

- NanoPi `can0` classic CAN 1Mbps，`ERROR-ACTIVE`
- M33 正式控制入口：`0x320`
- 7 号灵足 EL05 私有协议直驱可用

根因：

- `0x320` byte1 表示 ROS trajectory joint id，不是真实电机 ID。
- M33 旧代码把 ROS joint id 用 `ros_joint + 1` 映射到 motor slot，导致 ROS `0..4` 打到 motor `1..5`，没有覆盖真实 `3..7` 电机组合。
- 手动发 `joint=7` 会被 M33 当作未知 ROS joint，而不是电机 7。

解决：

- M33 本地工程已改为显式映射：

```text
ROS joint 0 shoulder_lift_joint      -> motor slot 3
ROS joint 1 elbow_lift_joint         -> motor slot 4
ROS joint 2 shoulder_abduction_joint -> motor slot 5
ROS joint 3 upper_arm_rotation_joint -> motor slot 6
ROS joint 4 forearm_rotation_joint   -> motor slot 7
```

- 后续要通过正规链路动 7 号，应发：

```bash
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 30 --rpm 3 --torque-ma 0
```

技巧：

- 调试时要区分三层 ID：ROS joint id、M33 motor slot、厂家 motor/node id。
- `nanopi_can_master.py private --motor 7` 的 `7` 是厂家电机 ID；`m33 target --joint 4` 的 `4` 是 ROS 关节号。
- 看到 `0x320` 发出但电机不动时，先查 M33 是否拒绝 unknown joint，再查映射表。

状态：

- M33 源码已修并烧录后复测：`0x320#03042C0103000000` 会触发 M33 输出 `0x0300FD07` 和 `0x01800007` 到 motor7。映射问题已基本确认修复。
- 现场反馈发生剧烈转动。已发送软件 stop，并把 M33 默认 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE` 改回 `0`，避免未标定 `0x320` 绝对位置目标继续输出。
- 后续重点转为 motor7 的零点、目标角、MIT 参数和真实输出角标定；未完成前禁止再次发 ROS 位置目标到电机。

### 未标定绝对位置目标会造成剧烈转动

现象：

- `m33 target --joint 4 --deg 30 --rpm 3 --torque-ma 0` 经 M33 映射后触发 motor7 私有 MIT 控制帧。
- 现场反馈发生剧烈转动。

根因：

- 7 号当前没有建立可信零点、方向、当前位置到关节输出角的关系。
- M33 把 ROS joint/output 目标换算成 motor-side 绝对位置目标后发给私有 MIT 控制；如果电机内部当前位置参考和外部关节零点不一致，`+30°` 可能变成很大的绝对位置追踪动作。

解决：

- 立即发送 M33 stop 和 private stop。
- 默认关闭 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE`。
- 后续只允许使用低速、短时、可停止的速度脉冲做方向/比例标定；不要直接使用绝对位置目标。

技巧：

- 绝对位置控制必须排在零点、方向、反馈比例和限位全部确认之后。
- 正规链路打通不等于可以发位置目标。先证明“发到了”，再证明“单位正确”，最后才做位置闭环。

状态：

- 已采取软件停止和默认禁用措施；等待重新编译烧录禁用版 M33。

### 减速比必须在 NanoPi、文档、M33 三处一致

现象：

- 7 号电机用直接调试命令跑 3 秒，现场视频和用户目测约 `150°` 输出转动。
- 这说明现阶段不能把脚本里的速度参数、私有协议 raw 角度字段和真实关节输出角度简单画等号。
- 进一步检查发现 M33 配置里 joint3 仍是 `10:1`，joint4/5/6/7 仍是 `1:1`，与已确认型号不一致。

环境：

- NanoPi SocketCAN 调试工具：`nanopi_can_master.py`
- M33 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`
- 当前确认电机：3 号伺泰威 `48:1`，4/5 灵足 RS00 `10:1`，6/7 灵足 EL05 `9:1`

根因：

- 历史配置默认值没有随着真实电机型号确认同步。
- 厂家协议 raw 值、转子侧单位、减速后输出侧单位混在一起时，容易造成“看起来角度限位是 60 度，实际转了很多”的风险。

解决：

- M33 `applications/control/control_layer_cfg.h` 已同步减速比：joint3 `48.0f`，joint4/5 `10.0f`，joint6/7 `9.0f`。
- 文档和 NanoPi 遥测也记录相同型号/减速比。
- 正式路径必须统一使用 joint/output-side 单位，M33 内部再按减速比转换为 motor-side 单位。

技巧：

- 看到电机“明显转多了”时，先查单位层：输出关节角、转子角、厂家 raw 编码、脚本参数、减速比。
- 未校准前，不能用单一 raw 反馈字段做停止条件。
- 调试直控可以证明“能动”，不能证明“正式安全角度映射正确”。

状态：

- 已修正 M33 配置；等待 M33 重新编译、烧录和现场复测。

### Windows 命令行编译 M33 需要 ARM 工具链进 PATH

现象：

- `scons -j4` 提示 `scons` 不是可识别命令。
- `mingw32-make -j4` 能进入 Debug 构建入口，但目标被判断为最新。
- 强制重编 `applications/control/control_layer.o` 时调用 `arm-none-eabi-gcc`，随后失败：系统找不到指定的文件。

环境：

- Windows PowerShell
- RT-Thread Studio 生成的 `Debug/makefile`
- 本机能找到 `mingw32-make.exe`，但当前 shell PATH 找不到 `arm-none-eabi-gcc`

根因：

- RT-Thread Studio IDE 可能自带/配置了交叉编译器，但当前命令行环境没有继承 ARM GCC 路径。

解决：

- 用 RT-Thread Studio 直接构建，或把 IDE 使用的 `arm-none-eabi-gcc` 所在目录加入 PowerShell PATH 后再运行 `mingw32-make`。

技巧：

- `mingw32-make -j4` 返回 up to date 不等于刚改的头文件已重编。
- 需要确认时可以强制指定目标：`mingw32-make applications/control/control_layer.o -B`。

状态：

- 未修复；等待本机工具链 PATH 配好或使用 IDE 构建。

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

### 拒绝用例要绕过 NanoPi bridge 才能测到 M33 本体

现象：

- ROS bridge 默认会拒绝超限轨迹，不会把危险 `0x320` 发到 CAN。
- 这对正式系统是正确的，但如果要验证 M33 安全状态机是否真的能拒绝危险帧，就不能只用 ROS topic 测。

解决：

- 在 M33 logging-only、驱动断开、不穿戴条件下，用 NanoPi raw SocketCAN 直接发送单帧 `0x320`。
- 每个用例同时记录：
  - `candump can0,320:7FF,321:7FF,322:7FF`
  - M33 `COM26` 串口
  - `ip -details -statistics link show can0`

已验证：

```text
0300840305000000 -> reason=target_out_of_limit
0309390005000000 -> reason=unknown_joint
0300390005000100 -> reason=torque_out_of_limit
heartbeat age 3211ms + 0300390005000000 -> reason=heartbeat_timeout
030039001f000000 -> reason=velocity_out_of_limit
0100 -> reason=unsupported_command
heartbeat age 3211ms + 030084031f000100 -> reason=heartbeat_timeout
```

技巧：

- 正式路径里 NanoPi bridge 和 M33 都要有安全门；测试 M33 本体时需要有意识地绕过 NanoPi 门控，但必须保持 M33 `logging_only`。
- 每个危险用例都要确认最终还有 `final action=no_motor_output logging_only=1`。
- heartbeat 超时用例要先停止 bridge，避免 bridge 持续发 `0x321` 把 M33 heartbeat 刷新掉。
- 多错误优先级要单独测：当 heartbeat 超时和多个限位同时失败时，当前首要 reason 应该是 `heartbeat_timeout`。

状态：

- 第一轮和第二轮拒绝矩阵已通过，未给电机驱动上电，未做运动测试。

### 安全拒绝原因不能只留在串口里

现象：

- M33 串口能看到 `reason=target_out_of_limit` 等具体拒绝原因。
- 但 NanoPi/ROS 只看 `/rehab_arm/safety_state` 时，如果 `0x322` byte6 固定为 `logging_only_no_motor_output`，上层系统无法知道最近一次真正拒绝原因。

解决：

- M33 保存最近一次 ROS safety assessment 的 detail_code。
- `0x322` V2 byte6 使用最近一次 detail，而不是固定 `10`。
- NanoPi `psoc_status.py` 更新 detail 名称，与 M33 reason 对齐：
  - `2 -> unsupported_command`
  - `3 -> unknown_joint`

技巧：

- 串口适合 bring-up，但 ROS/App/服务器要依赖结构化状态。
- 每次新增 M33 reason，都要同步更新 `psoc_status.py`、协议文档和单元测试。
- detail_code 只表示首要拒绝原因；其他失败项可以继续留在 audit 日志或未来扩展状态帧里。

状态：

- M33 已本地实现并编译通过，NanoPi parser 单元测试 17 个通过，等待用户烧录后做非运动验证。
- 用户烧录后第一次非运动验证未通过：NanoPi `can0` 正常，能发 `0x321/0x320`，但无 `0x322`，COM26 也无输出。当前判断为 M33 应用未在线或烧录后未正常启动，尚未验证 detail_code 动态变化。

### 烧录后无 0x322 且串口静默，先怀疑应用没启动

现象：

```text
TX 321 01
NO RX
TX 321 02
NO RX
TX 321 03
NO RX
```

同时：

- `candump` 能看到 NanoPi 发出的 `0x321` 和 `0x320`。
- `can0` 仍为 `ERROR-ACTIVE`，错误计数为 0。
- Windows `COM26` 打开成功，但没有启动日志，发送换行也没有 shell/日志响应。

判断：

- 这不是 NanoPi parser 问题，因为没有任何 `0x322` 到达。
- 这也不是 ROS topic 问题，因为 raw SocketCAN heartbeat 都没有回复。
- 当前优先怀疑 M33 应用未运行、烧录后未复位到应用、烧录了错误镜像，或 M33 控制板供电/复位状态异常。

处理：

1. 现场按一下 M33 reset，或给 M33 控制板断电重上电。
2. 重测 raw heartbeat，只看 `0x321 -> 0x322`，不要发 `0x320`。
3. 如果仍无 `0x322`，重新烧录最新产物，优先使用：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
```

4. 烧录后确认串口有启动日志或 heartbeat 有 `0x322`，再继续 detail_code 验证。

状态：

- 已记录。本轮未给电机驱动上电，未做运动测试。

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

### `0x322 detail_code` 要用“前后两次 heartbeat”验证

现象：

- M33 的 `0x322` byte6 用来上报最近一次 ROS safety assessment 的首要拒绝原因。
- 直接发送危险 `0x320` 后不会自动看到状态变化，必须再发一次 `0x321` heartbeat 触发下一帧 `0x322`。

环境：

- NanoPi `can0`，classic CAN 1Mbps。
- M33 detail_code 固件，`CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`。
- 电机驱动断开，无运动测试。

验证：

- 初始 heartbeat 返回：

```text
RX 322 [8] a571070001010a00
detail_code=10 detail=logging_only_no_motor_output
```

- 发送超限 `0x320` 后，再发 heartbeat，返回：

```text
TX 320 [8] 0300840305000000
RX 322 [8] a572070001010400
detail_code=4 detail=target_out_of_limit
```

- M33 `COM26` 同时打印：

```text
safety_state=limited decision=reject reason=target_out_of_limit
final action=no_motor_output logging_only=1
```

技巧：

- 动态 detail 的验收要同时看三处：`candump`、NanoPi parser、M33 串口。
- `0x322` byte6 从 `0A` 变为 `04`，才说明 M33 已把最近一次拒绝原因带回 NanoPi。
- 只要 M33 仍是 logging-only，看到 `target_out_of_limit` 也不能理解为可运动状态；它只是更清晰的拒绝原因。

状态：

- 已验证通过。
- `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
- 未给电机驱动上电，未做运动测试。

### `0x322 detail_code` 会保留最近一次拒绝原因

现象：

- 完成 `target_out_of_limit` 验证后，再发一次普通 heartbeat，`0x322` 仍返回：

```text
RX 322 [8] a581070001010400
detail_code=4 detail=target_out_of_limit
```

- 这不是新错误，而是 M33 当前设计会保留最近一次 ROS safety assessment 的 detail。

验证：

- 发送 torque 超限帧：

```text
TX 320 [8] 0300390005000100
```

- 下一次 heartbeat 返回：

```text
RX 322 [8] a582070001010600
detail_code=6 detail=torque_out_of_limit
```

技巧：

- 判断 detail 是否“动态更新”，要看新危险帧之后 byte6 是否被覆盖，而不是要求每次 heartbeat 自动清零。
- 如果未来希望安全状态更像实时状态机，可以再设计一条明确的“清除最近拒绝原因/恢复默认 detail”规则；当前阶段先保留最近一次拒绝原因，便于追踪最后一个安全拒绝。

状态：

- `torque_out_of_limit` 抽样验证已通过。
- 本轮未查看 COM26 实时串口，结论基于 NanoPi 收到的 M33 `0x322` 回包和 `can0` 健康状态。
- 电机驱动未上电，未做运动测试。

### heartbeat 超时优先级必须能通过 `0x322` 看见

现象：

- M33 收到普通目标前，如果 NanoPi heartbeat 已超过超时窗口，应该优先拒绝为 `heartbeat_timeout`。
- 这类问题不能只靠串口看，因为后续 App、服务器和 ROS 侧也需要知道为什么被拒绝。

验证：

- 先发一次 heartbeat，确认链路在线：

```text
TX heartbeat_91 321 [1] 91
RX 322 [8] a591070001010600
```

- 等待 `3.2s`，超过当前 M33 `2500ms` heartbeat timeout。
- 发送一个普通目标：

```text
TX 320 [8] 0300390005000000
```

- 再发 heartbeat，下一帧 `0x322` 返回：

```text
RX 322 [8] a592070001010100
detail_code=1 detail=heartbeat_timeout
```

技巧：

- heartbeat timeout 用例要刻意停止 heartbeat，不要让后台 ROS bridge 或其他脚本持续发送 `0x321`。
- 测试前后都要看 `ip -details -statistics link show can0`，确认不是 bus-off、error-passive 或电池/ACK 问题造成的假失败。
- 超时拒绝通过后，仍应恢复正常 heartbeat 再继续下一项测试。

状态：

- 已验证通过。
- `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
- 未给电机驱动上电，未做运动测试。

### App/服务器不要把 `detail_code` 当成实时 fault

现象：

- `0x322 detail_code` 当前会保留最近一次 ROS safety assessment 的结果。
- 如果 App 或服务器只看 `detail=heartbeat_timeout`，可能误以为当前还在持续超时；如果只看 `detail=none`，也可能误以为可以运动。

正确边界：

- `state` 是当前总体安全状态。
- `control_mode` 是当前控制模式。
- `detail/detail_code` 当前语义是 `last_safety_assessment`。
- 可运动判断必须至少同时满足后续定义的 `state=ok`、`control_mode=armed/active`、M33 已解除 logging-only、急停/限位/供电均通过。

解决：

- NanoPi parser 保留旧字段，同时新增：

```json
{
  "detail_semantics": "last_safety_assessment",
  "last_assessment_detail_code": 1,
  "last_assessment_detail": "heartbeat_timeout"
}
```

技巧：

- UI 展示可以写成“最近一次拒绝原因：heartbeat_timeout”，不要写成“当前故障：heartbeat_timeout”。
- 服务器保存数据时同时存 `state/control_mode/detail_semantics/detail`，方便后续标注和追溯。

状态：

- 已在 NanoPi parser 和协议文档中明确。
- 本地 17 个测试通过，NanoPi 7 个 parser 测试通过。
- 真实 `0x322` 已解析出 `detail_semantics=last_safety_assessment`。

### 上层先看 `motion_allowed`

现象：

- App、服务器、VLA、仿真主机如果各自组合 `state/control_mode/detail`，容易判断不一致。

规则：

- `/rehab_arm/safety_state.motion_allowed=false` 时，任何上层都不能请求真实运动。
- 当前 logging-only 阶段必须一直是 `false`。
- 后续即使 `motion_allowed=true`，M33 仍然是最终安全裁决方。

状态：

- NanoPi parser 和 bridge 本地 safety payload 已输出 `motion_allowed`。

### ROS2 Python 节点要确认可执行位

现象：

- `colcon build` 通过，安装目录里也有 `data_recorder_node.py` 链接。
- 但 `ros2 pkg executables rehab_arm_psoc_bridge` 一开始没有显示新节点。

原因：

- 新增 Python 节点文件没有执行位。

解决：

```bash
chmod +x rehab_arm_psoc_bridge/data_recorder_node.py
```

并在 Git 中保留执行位。

状态：

- NanoPi 已验证 `ros2 pkg executables rehab_arm_psoc_bridge` 能看到 `data_recorder_node.py`。

### Windows 远程发布 ROS JSON 时引号容易被 PowerShell 解析坏

现象：

- 从 Windows PowerShell 里通过 `ssh` 执行 `ros2 topic pub`，消息内嵌 JSON 时出现 `ParserError`。

技巧：

- 这类测试优先写成 NanoPi 本地脚本，或先测试 helper/节点注册。
- 不要把复杂 JSON、PowerShell、SSH、ROS YAML 四层引号揉在一个命令里。

### NanoPi 端口通不等于 SSH 命令可执行

现象：

- `Test-NetConnection 192.168.2.66 -Port 22` 显示 `TcpTestSucceeded=True`。
- 但 `ssh pi@192.168.2.66 "echo online"` 超时。

判断：

- 这说明网络端口可达，但 SSH 登录/会话建立卡住。
- 不要在这种状态下继续判定 ROS、CAN 或 colcon 失败。

状态：

- 本次 metadata 数据记录改动已完成本地测试。
- NanoPi 同步验证暂缓，等 SSH 命令能正常返回后再做。

补充：

- 后续 NanoPi SSH 恢复后，metadata recorder 已同步、构建并验证通过。

### ROS2 节点不要用 `self.handle` 做普通成员名

现象：

- `data_recorder_node.py` 启动时报错：

```text
AttributeError: handle cannot be modified after node creation
```

原因：

- `rclpy.node.Node` 已经有只读属性 `handle`。

解决：

- 文件句柄成员改名为 `self.log_handle`。

状态：

- 已修复，NanoPi 上 `data_recorder_node.py` 可写出 `session_metadata`。

### `timeout` 停 ROS2 节点时要处理 `ExternalShutdownException`

现象：

- 用 `timeout 3s ros2 run ... data_recorder_node.py` 做短验证时，数据已写入，但退出留下 traceback。

解决：

- `main()` 同时捕获 `KeyboardInterrupt` 和 `ExternalShutdownException`。

状态：

- 已修复，短运行退出不再打印 traceback。

### recorder 的数据闭环至少要验证一条真实 topic

现象：

- 单元测试和 `colcon build` 通过，不代表 ROS topic 已能落盘。

技巧：

- 启动 `data_recorder_node.py` 后发布一条假 `/joint_states`。
- 检查 JSONL 同时包含 `session_metadata` 和 `/joint_states` 的 `topic_message`。

状态：

- NanoPi 已验证 `/joint_states` 可记录 `name/position/velocity/effort/stamp`。

### 仿真 motor_state 是遥测桥，不是控制器

现象：

- 总控台和数据记录需要 `/rehab_arm/motor_state`。
- 但没有真机电机状态或不能上电时，容易卡在硬件链路上。

解决：

- 使用 `joint_state_motor_state_node.py` 把 `/joint_states` 转成 `/rehab_arm/motor_state`。
- 这适合仿真、离线标注、总控台表格联调和 recorder 测试。

技巧：

- 这个节点的 `control_boundary` 是 `telemetry_only_not_motor_command`。
- 它不发 CAN、不下发 `0x320`、不代表电机真实在线。
- 真机版本仍要以后用 M33 汇总的电机反馈来发布 `/rehab_arm/motor_state`。

状态：

- 本地和 NanoPi 单测通过。
- NanoPi ROS 冒烟测试已确认假 `/joint_states` 能生成 `/rehab_arm/motor_state`。

### JSONL checker 要同时测 PASS 和 FAIL

现象：

- `/tmp/joint_recorder_verify.jsonl` 只有 `session_metadata` 和 `/joint_states`。
- checker 返回 FAIL，缺少 `/rehab_arm/safety_state` 和 `/rehab_arm/sensor_state`。

结论：

- 这是正确行为；单关节测试文件不是完整 session。

技巧：

- checker 验证时至少准备一份完整 JSONL，包含三类 topic。
- 生成测试 JSONL 时用 `json.dumps()`，不要手写多层 SSH/PowerShell JSON 转义。

状态：

- NanoPi 已验证完整 JSONL 返回 `ok=true`。

### launch 短运行验证不要太短

现象：

- `timeout 3s ros2 launch ... data_collection.launch.py` 只看到进程启动，未稳定写出 JSONL。
- 改成 `timeout 10s` 后正常写出 `session_metadata`。

技巧：

- launch 会先启动 launch service，再启动节点；短验证至少给 10 秒。
- 验证 recorder 时优先检查 JSONL 第一行，而不是只看 launch 进程启动。

### `timeout ros2 launch` 可能不会让远程 SSH 干净返回

现象：

- NanoPi 上 `colcon build --packages-select rehab_arm_bringup` 通过。
- 通过 SSH 执行 `timeout 10 ros2 launch rehab_arm_bringup sim_data_collection.launch.py ...` 后，本地 SSH 命令没有按预期返回。
- 随后短时间内新的 SSH 命令也超时。

判断：

- 这不像代码编译错误，更像 launch 子进程、ROS daemon 或远程会话没有被 `timeout` 干净回收。
- 在板子刚恢复上电或发热明显时，不应反复启动高频仿真/记录进程。

技巧：

- 远程验证 launch 时优先用后台启动、显式记录 PID、再显式 shutdown/kill 的脚本。
- 如果 SSH 已经卡住，先等板子恢复或现场重启，不要继续压测。
- 这类卡住不代表可以进入真机 CAN 控制；本轮仍然不发 `0x320`。

状态：

- 已记录。`sim_data_collection.launch.py` 已通过本地语法检查和 NanoPi 构建，但短跑 JSONL 完整性验证待 SSH 恢复后继续。

### 仿真也要周期性发布 safety_state

现象：

- `sim_data_collection.launch.py` 首轮短跑能写出 JSONL。
- JSONL 包含 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/sensor_state`。
- `check_recording.py` 失败，提示缺少 `/rehab_arm/safety_state`。

根因：

- 仿真节点原本只在收到轨迹时发布 safety。
- 离线采集 launch 启动后如果不发布轨迹，recorder 永远收不到 safety topic。

解决：

- `mujoco_sim_node.py` 增加默认 `safety_state=ok`、`safety_detail=simulation ready`。
- 在 timer 中每 1 秒周期发布一次 `/rehab_arm/safety_state`。

技巧：

- 仿真和真机都应持续发布安全状态；上层不应靠“没消息”猜系统是否安全。
- 数据采集完整性检查能及时暴露这类系统接口缺口。

状态：

- 本地已修复并通过语法检查。
- NanoPi 复测被 SSH 超时阻塞，待板子稳定后继续。

### NanoPi 不在线时先补本地静态保护

现象：

- NanoPi SSH 返回 `connect to host 192.168.2.66 port 22: Connection timed out`。
- 不能继续做远端 `colcon build` 或 ROS launch 验证。

技巧：

- 不在线时不要反复压测板子。
- 可以先补不依赖 ROS 安装的本地静态测试，检查 package metadata、launch 文件关键节点和参数是否存在。
- 这不能替代 NanoPi 真 ROS launch，但能防止启动入口被后续提交无意改坏。

状态：

- 已为 `rehab_arm_bringup` 新增本地静态测试。
- 本地 bringup 2 tests passed；NanoPi 复测仍待恢复。

### PowerShell 会提前解析远端 `$(...)`

现象：

- 从 Windows PowerShell 里执行 SSH 远端命令：

```powershell
ssh pi@192.168.2.66 "kill -INT $(cat /tmp/sim_data_collection_launch.pid)"
```

- PowerShell 把 `$(cat ...)` 当成本地表达式执行，报错路径类似：

```text
Cannot find path 'D:\tmp\sim_data_collection_launch.pid'
```

解决：

- 用 PowerShell 单引号包住远端命令，或避免在远端命令里直接写 `$()`。

技巧：

- Windows -> SSH -> bash 有两层 shell；凡是 `$()`、引号和 JSON 混在一起时，优先拆成更简单的远端命令。

状态：

- 已记录。本次 launch 验证改用更简单的 `timeout -s INT`。

### `pkill -f` 可能杀掉当前 SSH 命令

现象：

- 远端命令里先执行：

```bash
pkill -f 'ros2 launch rehab_arm_bringup sim_data_collection.launch.py'
```

- 但同一条 SSH 命令后面也包含这个字符串，`pkill -f` 可能匹配并杀掉当前 shell，导致命令无输出退出。

解决：

- 先用 `pgrep -af` 查看残留 PID，再显式 `kill <pid>`。
- 或把清理命令和启动命令拆成两次 SSH，不要让待匹配字符串出现在当前命令行里。

状态：

- 已记录。本次残留节点按 PID 清理后继续验证。

### ROS2 订阅节点 SIGINT 时可能出现 shutdown race

现象：

- `timeout -s INT ros2 launch ...` 停止仿真采集时，`data_recorder_node.py` 和 `joint_state_motor_state_node.py` 偶发 traceback：

```text
RuntimeError: Unable to convert call argument '0' to Python object
```

判断：

- 这是 ROS2 Jazzy/rclpy 在 SIGINT 时，订阅 executor 正在取消息的退出竞争。
- 数据文件已经写出并且 checker 可通过，但日志污染会误导后续测试。

解决：

- 在两个订阅节点的 `main()` 中只抑制这个已知 shutdown runtime error。
- 不吞普通运行时错误。

状态：

- 已修复并在 NanoPi 复测：`TRACEBACK_COUNT=0`。
- `check_recording.py` 同时返回 `ok=true`。

### 动态采集要验证关节范围，不只看 topic 存在

现象：

- `check_recording.py ok=true` 只能证明基础 topic 齐全。
- 如果 demo 轨迹没有发布，或者仿真没有接到 `/arm_controller/joint_trajectory`，JSONL 仍可能只是静止数据。

技巧：

- 动态采集时同时检查：
  - launch 日志是否出现 `Published multi-joint demo JointTrajectory`。
  - 每个关节的 `position` min/max span 是否大于一个小阈值。
  - `/rehab_arm/motor_state` 数量是否和 `/joint_states` 基本同步。

状态：

- NanoPi 已验证 5 个关节均有运动 span，且 `check_recording.py ok=true`。

### CSV 导出用于离线分析，不是控制链路

规则：

- `export_recording_csv.py` 从 JSONL 导出 `joint_states.csv` 和 `motor_states.csv`。
- CSV 是给标注、画曲线、训练前检查、Excel/pandas/MATLAB 用的离线数据格式。
- CSV 不应被任何节点当成实时控制输入直接下发到 M33 或电机。

状态：

- 本地和 NanoPi 已验证 CSV 导出。

### 数据摘要工具和完整性检查职责不同

规则：

- `check_recording.py` 回答“基础 topic 是否齐全”。
- `summarize_recording.py` 回答“这段数据质量如何”，例如 topic 频率、关节运动范围、motor_state 条目数、安全状态分布。
- `validate_recording_quality.py` 回答“这段数据能不能进入下一步流程”，例如 CI、标注、回放或上传前验收。

技巧：

- 动态 demo 采集后应同时跑两个工具。
- `check_recording.py ok=true` 但 `moving_joint_count=0`，说明采到了数据但没有运动变化。
- `motor_entry_count_min/max` 可帮助总控台快速发现 motor_state 是否缺条目。
- 当前 logging-only/离线采集阶段，质量门默认不允许 `motion_allowed=true`；如果后续真机阶段真的进入可运动状态，必须显式传 `--allow-motion-allowed-true`，并先确认 M33 安全语义已经完成。

状态：

- 本地已新增摘要工具并通过单元测试。
- NanoPi 已构建通过。
- NanoPi 复测时发现 `/tmp/rehab_sim_collection/sim_demo_motion.jsonl` 因重启消失；重新采集后摘要工具验证通过，`moving_joint_count=5`。
- 本地已新增质量门工具并通过单元测试；硬件全断电时只做离线验证，不做 NanoPi/CAN 复测。

### manifest summary 默认不要破坏旧同步格式

规则：

- `build_manifest.py` 默认仍生成旧 manifest 字段，避免影响已有 `sync_dry_run.py` 和 `sync_upload.py`。
- 只有显式加 `--include-summary` 时，才把每个 session 的 `summary` 嵌入 manifest。

技巧：

- 给总控台、标注或人工检查用 `manifest_with_summary.json`。
- 给已经上线的旧同步流程时，可以继续用普通 `manifest.json`。
- 后续如果服务器确认支持 summary，再把上传示例切换到带 summary manifest。

状态：

- 本地和 NanoPi 已验证 `--include-summary`。
- 旧默认 manifest 单测仍确认不含 `summary` 字段。
- `sync_dry_run.py` 已验证会把 manifest 中的 `summary` 原样放进 `/sessions/manifest` 计划请求。

### `/tmp` 里的验证文件可能在重启后消失

现象：

- NanoPi 在线且负载正常。
- 但运行摘要工具时报：

```text
No such file or directory: /tmp/rehab_sim_collection/sim_demo_motion.jsonl
```

根因：

- `/tmp` 是临时目录，设备重启或清理后验证文件可能消失。

技巧：

- 临时验证可以继续用 `/tmp`。
- 需要跨重启保留的数据应写到 `/home/pi/rehab_arm_logs` 或明确的持久目录。
- 复测摘要工具时，如果文件不存在，先重新跑一次 `sim_data_collection.launch.py` 生成 JSONL。

状态：

- 已记录。本次重新生成 `sim_demo_motion.jsonl` 后摘要验证通过。

### 数据文件名要让服务器不用猜

规则：

- 默认 session 文件名使用 `<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl`。
- metadata 里保留同样的 `session_id`，并带 `schema_version`、`source`、`sync_status`。
- 服务器同步前只需要扫描文件名和第一行 metadata，就能建立索引。

### manifest 的 `ok=false` 不一定是程序错

现象：

- 对只含 `session_metadata` 的短验证文件运行 `build_manifest.py`，输出 `ok=false`。

判断：

- 这是正确行为；该文件缺少 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
- manifest 用于同步前筛选，缺数据的 session 不应进入标注/同步流程。

### 服务器同步先做 API 草案，不直接上传

规则：

- 第一版服务器同步只接收 manifest 和 JSONL 文件。
- 不下发 CAN、电流、力矩、速度、裸角度或 M33 override。
- 上传入口默认必须是 dry-run，只有显式 `--execute` 才能联网。
- 真正使用 `--execute` 要等服务器 endpoint 确认后再做。

### `urlopen` 超时参数必须用关键字

现象：

- 本地假服务器收到第 1 个 POST，但 `sync_upload.py --execute` 结果失败。
- 错误为 `message_body should be a bytes-like object or an iterable, got <class 'float'>`。

根因：

- `urllib.request.urlopen(req, timeout_sec)` 的第二个位置参数是 `data`，不是 timeout。

解决：

- 使用 `urllib.request.urlopen(req, timeout=timeout_sec)`。

状态：

- 已修复，Windows 和 NanoPi 均完成 4 个 POST 闭环。

### PowerShell 传远程 bash 脚本要小心 CRLF

现象：

- 通过 PowerShell here-string 传脚本到 NanoPi 后，`tail` 报路径带 `$'\r'`。

技巧：

- 复杂远程验证优先用远程 Python 读文件或确保脚本转换为 LF。
- 生成 JSON/manifest 时优先用远程 Python `json.dumps()`，不要手写多层转义。
- 远程 Python 片段里尽量少写包含嵌套引号的 f-string；`format()` 更不容易被 Windows PowerShell、SSH 和 bash 多层引号干扰。

### USB 摄像头先看 `lsusb`，不要只看 `/dev/video*`

现象：

- NanoPi 有很多 `/dev/video*`，但 `ffmpeg -f v4l2 -i /dev/video0` 报 `No such device`。
- `/dev/video22`、`/dev/video31` 能列格式，但 ffmpeg 报 `Not a video capture device`。
- `lsusb` 只看到 Linux root hub，没有看到 UVC 摄像头设备。

判断：

- 当前没有真正枚举出 USB 摄像头。
- 很多 `/dev/video*` 是 Rockchip ISP/MIPI/编码器管线节点，不等于 USB 摄像头可采集节点。

技巧：

- USB 摄像头优先看 `lsusb` 是否出现摄像头设备，再看 `v4l2-ctl --list-devices`。
- UVC 摄像头通常会显示 `uvcvideo` 相关设备，且 `/dev/videoX` 可被 ffmpeg 打开。
- 深度摄像头后续要同时确认 RGB、Depth、IR 节点和 SDK 支持，不要只验证 RGB。

当前状态：

- 已新增 `camera_keyframe_node.py`，等待摄像头正确枚举后复测。

### 哈希测试不要依赖文本换行

现象：

- `file_sha256()` 单测在 Windows 通过，但同步到 NanoPi 后失败。
- Windows `write_text('...\n')` 可能写成 CRLF，Linux 写成 LF，导致同一测试的 SHA256 不同。

解决：

- 哈希测试使用 `write_bytes(b'...')` 固定文件内容。

技巧：

- 跨 Windows/Linux 验证二进制摘要、协议 payload、CAN frame bytes 时，不要用文本模式生成测试输入。

状态：

- 已修复，Windows 本地和 NanoPi 单测均通过。

### 进度和踩坑要分开

规则：

- `docs/PROJECT_PROGRESS.md` 记录当前进展、验证结果、下一步。
- `docs/TROUBLESHOOTING_AND_LESSONS.md` 记录踩坑、排查方式、技巧。
- 架构改变写 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
- 面向新读者的入口写 `README.md`。

技巧：

- 进度文档回答“现在做到哪里”。
- 踩坑文档回答“以后遇到同类问题怎么少走弯路”。

### 仿真电脑不要直接从复杂 launch 开始排错

现象：

- 新 Linux 仿真主机刚搭好时，直接运行 MuJoCo/采集 launch 可能同时暴露 ROS2、MuJoCo、URDF、Python 包路径和数据工具多个问题。

技巧：

- 先运行 `ros2 run rehab_arm_sim_mujoco check_sim_env --pretty`。
- 如果 `readiness=ready_with_fallback_sim`，说明 ROS2 数据链路可先跑通，但真实 MuJoCo Python 包还没装好。
- 如果 `ok=false`，先看 `errors`，逐项修 ROS2 包、URDF 路径或采集工具导入。
- 在 Windows 开发机上看到 `rclpy is required but not available` 是正常现象，说明这台机器不是 ROS2 仿真运行环境；真正仿真主机应在 Linux + ROS2 环境下通过。
- 只有这个自检通过后，再运行 `sim.launch.py` 或 `sim_data_collection.launch.py`。

状态：

- 已新增自检工具；它只读环境，不访问 CAN，不命令 M33 或电机。

### 仿真自检报告只能作为平台数据资产

现象：

- 平台需要知道仿真主机是否具备 ROS2、URDF、MuJoCo/fallback 和采集工具，但不能把这种“准备度”误解成真机运动许可。

技巧：

- 用 `check_sim_env --output sim_readiness_report.json` 生成只读报告。
- 平台接收端只写入 `simulation_readiness` 最新状态和事件日志。
- UI 文案必须写清楚它是研发准备度，不是 M33 运动许可。
- 如果 `readiness=ready_with_fallback_sim`，可以先跑 ROS topic/数据采集链路；等 MuJoCo 安装好再跑真实 MuJoCo 仿真。

状态：

- 已在工具和平台接口中保留 `simulation_readiness_only_not_motion_permission` 边界。

### 测试 demo 和临时报告不要污染项目

现象：

- 单元测试如果把 `sim_readiness_report.json`、截图、样例 session 或 demo 输出写进源码目录，后面会越积越乱。

技巧：

- 单元测试使用系统临时目录生成输出，测试结束自动删除。
- 只有可复用代码、正式测试、正式文档可以提交；临时 demo 数据、QA 截图、一次性报告不要提交。
- 如果确实需要保留验证证据，优先写进文档摘要，不把生成文件留在仓库里。

状态：

- `check_sim_env --output` 测试已改为 `TemporaryDirectory()`，不会留下测试报告文件。

### 平台上传工具默认必须是 dry-run

现象：

- 仿真主机、NanoPi、服务器之间的工具如果默认联网，容易误把一次测试变成真实上传或真实动作。

技巧：

- `upload_sim_readiness` 默认只打印上传计划。
- 只有加 `--execute` 才会 POST 到平台。
- 这类上传只能走数据资产接口，必须保留 `simulation_readiness_only_not_motion_permission` 边界。
- 上传前先看 dry-run 里的 URL、`device_id`、`robot_id` 和 report 内容。

状态：

- 已新增 `upload_sim_readiness`，单测使用 fake opener，不连真实服务器，不生成持久 demo 文件。

### CANSimple 闭环后 0x069 可能从全 0 变成有效估计值

现象：

- 电机上电后，`0x069` encoder estimate 一开始可能全 0。
- 发送 CANSimple closed-loop 后，`0x069` 变成非零 float 数据。

技巧：

- 不要把第一次从 0 跳到非零的 position estimate 全部当成真实运动量；它可能包含控制器进入闭环后的估计值恢复。
- 做小幅度运动时，必须同时保存 raw CAN log，记录发送的 `0x67/0x6B/0x6D` 和后续 `0x061/0x069`。
- 调试后立刻发 `vel=0` 和 `idle`，再确认 `can0` 仍是 `ERROR-ACTIVE` 且错误计数为 0。

状态：

- 已对 CANSimple `node_id=3` 做极小速度测试并保存日志；未触碰 private MIT `motor_id=4`。

### 原始 CAN 日志要转成统一 motor_state JSONL

现象：

- `candump -tz can0` 原始日志适合保留证据，但不方便直接给总控台、标注工具、质量门和训练前分析使用。
- CANSimple `0x069` 是 turns/turns/s，不能直接当作 ROS 常用 rad/rad/s。

技巧：

- 用 `candump_motor_telemetry` 把 CANSimple `0x061/0x069`、M33 `0x330~0x337` 和已确认的灵足 active-report 离线转换成 `/rehab_arm/motor_state` JSONL。
- 转换后保留 `control_boundary=telemetry_only_not_motor_command`，提醒后续工具这只是遥测数据，不是控制许可。
- 输出文件用临时目录做验证；只有代码、测试和文档进入仓库，不提交真实采集 JSONL 或 demo 数据。
- 闭环刚建立后的 encoder estimate 跳变可能包含估计器恢复，应在分析报告里单独标注。

状态：

- 已新增离线转换器和单元测试，并用真实 NanoPi tiny-motion candump 日志做过临时目录验证。

### 平台接入检查不能被理解成运动许可

现象：

- 平台页面会显示 Linux 开发板、runner、ROS/仿真、摄像头、CAN/串口和最近上传状态。
- 这些状态容易被误读成“系统已经可以动真机”。

技巧：

- 平台接入检查只做研发链路判断：设备是否在线、数据是否上传、仿真报告是否存在、采集/标注是否可继续。
- UI 文案必须持续写明：状态只读，不下发 ROS、CAN、M33 或电机命令。
- 真实运动许可只来自 M33 安全状态机；平台、服务器、VLA、仿真报告和 NPC 建议都不能绕过 M33。

状态：

- 平台 robotics 页面已增加只读 `接入检查` 面板，文档已记录安全边界。

### Linux 开发板 manifest 只能做只读发现

现象：

- 开发板接入平台时需要扫描 `can*`、串口、USB、摄像头、ROS2 环境。
- 如果扫描脚本顺手 bring up CAN、启动 ROS launch 或打开设备流，容易把“接入发现”变成“隐式控制/占用设备”。

技巧：

- `board_manifest` 只读 `/sys/class/net`、`/dev` 和命令可用性。
- 输出必须保留 `control_boundary=board_discovery_only_not_motion_permission`。
- 上传前先人工检查 manifest，确认 `device_id`、`robot_id`、接口列表和安全边界正确。
- 真机运动许可仍只看 M33 安全状态机，不看平台 manifest。

状态：

- 已新增 `board_manifest` 和单元测试；尚未接入平台上传接口。

### 开发板注册先 dry-run 再 execute

现象：

- 平台 `/devices/register` 当前只接收精简字段，不能直接保存完整 `linux_board_manifest_v1`。
- 如果直接把完整 manifest 作为注册 payload 发送，后端可能忽略额外字段，导致用户误以为完整能力清单已经保存。

技巧：

- 先用 `board_manifest_sync_dry_run` 生成请求计划，确认真正会发的是精简注册字段。
- 完整 manifest 的平台持久化要单独做后端接口或扩展 schema，不能假装已完成。
- dry-run 阶段只输出 JSON，不联网；后续加 `--execute` 时必须保留显式开关。

状态：

- 已新增 dry-run 计划工具；真实上传仍未启用。

### 完整 board manifest 要和 session manifest 分开

现象：

- `rehab_arm_manifest_v1` 表示一次数据采集 session 的文件、质量门和同步状态。
- `linux_board_manifest_v1` 表示一台 Linux 开发板的静态/半静态能力，例如 CAN、串口、摄像头、ROS2。
- 如果都塞进 `/sessions/manifest`，平台页面会把“板子能力”和“数据采集质量”混在一起。

技巧：

- 平台后端用独立 `/devices/{device_id}/board-manifest` 保存开发板能力。
- dashboard 同时返回 `manifest` 和 `board_manifest`，前者用于数据质量/标注，后者用于设备接入检查。
- 前端接入检查可以用 `board_manifest` 判断硬件能力，但不能把它当作实时数据或运动许可。

状态：

- 平台已新增 full board manifest 存储；ROS dry-run 已规划对应请求。

### 开发板 manifest 上传必须显式执行

现象：

- 用户需要把真实 NanoPi/Jetson/x86 开发板能力同步到平台。
- 如果上传命令默认联网，容易误传错误 `device_id`、`robot_id` 或把测试环境数据写入云端。

技巧：

- `board_manifest_sync_upload` 默认行为仍是 dry-run；不加 `--execute` 只打印计划请求。
- 真正上传前先人工检查 `linux_board_manifest_v1` 和两条请求 URL。
- 单元测试用 fake opener 验证 HTTP 请求，不对真实服务器写入 demo 数据。

状态：

- 已新增显式 `--execute` 上传命令；尚未在真实 NanoPi 上执行云端上传。

### 仿真 topic 合同不等于 topic 正在运行

现象：

- `check_sim_env` 可以输出 `/arm_controller/joint_trajectory`、`/joint_states`、`/rehab_arm/safety_state` 等标准 topic 合同。
- 用户可能误以为自检报告里有 topic 名，就代表这些 topic 已经实时发布，甚至可以直接控制真机。

技巧：

- `topic_contract` 只说明仿真主机、NanoPi、平台采集标注和 VLA 后续应遵守的接口名称和消息类型。
- 判断 topic 是否真的运行，还要用 `ros2 topic list`、`ros2 topic echo --once`、launch 日志和数据采集 JSONL 验证。
- 真机运动许可仍只来自 M33 安全状态机，不能从仿真报告或平台页面推断。

状态：

- `check_sim_env` 已加入 `topic_contract.control_boundary=simulation_topic_contract_not_motion_permission`。

### JSONL topic profile 是进入标注前的第一道门

现象：

- `check_recording.py ok=true` 的默认检查只要求基础 topic。
- 真机电机遥测、视觉/VLA 数据、纯仿真数据对 topic 的要求不同，手动写 `--required-topic` 容易漏项。

技巧：

- 用 `--topic-profile simulation_minimum` 检查基础仿真/采集数据。
- 用 `--topic-profile hardware_telemetry` 检查电机数据是否包含 `/rehab_arm/motor_state`。
- 用 `--topic-profile perception_vla` 检查视觉/VLA 数据是否包含 `/rehab_arm/camera_keyframe`。
- profile 检查只回答“这段 JSONL 是否包含该流程最小 topic 集”，不回答数据质量、运动幅度或安全许可；后面仍要跑 `validate_recording_quality.py` 和 M33 安全链路检查。

状态：

- `check_recording.py` 已支持 topic profile preset，并有 CLI 单测覆盖缺 `motor_state` 的失败路径。

### 质量门和 manifest 也要使用同一个 topic profile

现象：

- 只在 `check_recording.py` 用 `--topic-profile` 会造成两套口径：topic 齐全性检查知道 `hardware_telemetry`，但质量门或 manifest 里的 `quality_report` 可能仍按默认基础 topic 通过。

技巧：

- `validate_recording_quality.py` 也使用 `--topic-profile hardware_telemetry` 或 `--topic-profile perception_vla`。
- `build_manifest.py --include-quality-report` 同样带上 `--topic-profile`，让平台直接读取 `quality_report.topic_profile`、`required_topics` 和 `schema_check.missing_topics`。
- profile 仍只是数据验收口径，不是运动许可；真机运动必须由 M33 安全状态机允许。

状态：

- 已统一接入 `validate_recording_quality.py`、`build_recording_quality_report()` 和 `build_manifest.py --include-quality-report`。

### 视觉/VLA 数据不能只检查 topic 存在

现象：

- `perception_vla` profile 能确认 JSONL 里至少出现过 `/rehab_arm/camera_keyframe`。
- 但复杂任务规划、遮挡物处理、后续标注和训练需要足够多的关键帧；只有一帧通常不够。

技巧：

- 离线质量门使用 `--topic-profile perception_vla --min-camera-keyframes N`。
- `N` 根据采集任务调整；短冒烟测试可以小，正式标注数据要更严格。
- 该检查只看 JSONL topic 数量，不证明图片文件存在、清晰或深度有效；图片质量和标注质量要另做检查。

状态：

- 已加入 `--min-camera-keyframes`，可用于单文件质量门和 `build_manifest.py --include-quality-report`。

### 摄像头关键帧文件检查只能在图片已同步后开启

现象：

- JSONL 里的 `image_path` 可能是 NanoPi 本机路径，例如 `/home/pi/rehab_arm_frames/f1.jpg`。
- 在开发电脑或平台主机上离线检查时，如果图片文件还没同步过来，直接启用文件检查会把所有关键帧报成 missing。

技巧：

- 先用 `--topic-profile perception_vla --min-camera-keyframes N` 检查消息数量。
- 确认图片文件已同步到本机后，再加 `--require-camera-files --camera-base-dir <frame-root>`。
- `camera_file_check.hash_mismatch_count>0` 表示 JSONL 中记录的 sha256 和本地文件不一致，不能进入正式标注/训练。

状态：

- 已加入可选的本地文件存在和 sha256 检查；默认关闭，避免跨机器路径误报。

### 标注队列必须从质量门之后生成

现象：

- 如果平台或人工直接从普通 `manifest.json` 开始标注，缺 topic、缺 motor_state、缺关键帧或图片 hash 错误的数据也可能混进训练集。

技巧：

- 先生成 `manifest_with_quality.json`。
- 再运行 `build_annotation_queue.py` 生成 `rehab_arm_annotation_queue_v1`。
- 平台默认只展示 `items`；把 `skipped_sessions` 作为质量问题提示，不要静默丢弃。

状态：

- 已新增离线 annotation queue 工具；它只转换 manifest，不联网、不控制硬件。

### 标注 CSV 模板不是训练集

现象：

- `export_annotation_template.py` 会生成可填写的 CSV，但刚导出的行默认 `annotation_status=pending`，label 列为空。
- 如果直接把这个模板当训练集，会把空标签或未审核数据混进模型训练。

技巧：

- CSV 模板只用于人工或平台标注入口。
- 训练前必须再做一次标注结果校验，确认 `annotation_status`、必填 label、备注和质量门都满足要求。
- CSV 里的 session 路径和标签仍是离线数据，不应被任何控制节点消费。

状态：

- 已新增 CSV 模板导出；下一步应做 completed annotation CSV 校验。

### 电机数据接收要区分被动上报、查询回复和周期上报开关

现象：

- NanoPi `can0` 正常且 `ERROR-ACTIVE` 时，被动 `candump` 只看到 `0x061` 和 `0x069`，容易误判只有一个电机在线。
- 实测 `0x061/0x069` 是 CANSimple node 3 的周期状态；私有协议电机 4/5/6/7 不一定默认主动上报。

技巧：

- 先被动抓包确认总线健康，再发非运动 Get_ID probe。4/5/6/7 会用扩展帧 `0x000004FE`、`0x000005FE`、`0x000006FE`、`0x000007FE` 类回复。
- 需要连续状态时，可以用私有 active-report 打开周期上报，实测 4/5/6/7 分别是 `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`，约 100Hz。
- 测试结束要关闭 active-report，避免总线长期高频刷帧影响后续调试。
- 正式机器人路径仍应由 M33 聚合/转发并发布 ROS `/rehab_arm/motor_state`；NanoPi 直接私有 active-report 只是调试手段。

状态：

- 已确认 NanoPi 能接收 4/5/6/7 周期电机状态；M33 `active-report` 转发路径还未打通。

### 灵足主动上报不要在型号未确认前强行换算工程单位

现象：

- 实测 4/5/6/7 会发 `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`。
- 本地 RobStride 示例里同类 payload 可按位置、速度、扭矩、温度解码，但不同型号的速度/扭矩量程不同。

技巧：

- 默认保留 `raw_position_u16`、`raw_velocity_u16`、`raw_torque_u16`、`raw_temperature_u16` 和原始 CAN 数据。
- 只有确认 motor ID 对应 `RS00/RS01/RS02/RS03/RS04/RS05/RS06/EL05` 后，才按对应型号量程输出 rad、rad/s、Nm、摄氏度。
- 数据采集和平台展示可以先显示 raw 值和 `engineering_decode=raw_only_actuator_type_unconfirmed`，不要把未知型号伪装成真实物理量。

状态：

- `candump_motor_telemetry.py` 已按 raw-first 方式处理灵足 active-report。

### 飞书在线链接可能只返回登录页，但本地可能已有离线页

现象：

- 直接访问用户提供的飞书 docx 链接时，HEAD 返回 404。
- 加浏览器 UA 后能下载 HTML，但内容是 passport 登录页，不是文档正文。
- 本项目本地 `D:\电机上位机\肩关节电机资料` 已经保存过三份飞书离线 HTML，里面能读到伺泰威/肩关节产品、用户、协议资料。

技巧：

- 不要从登录页推断协议字段。
- 先搜本地离线资料目录，再判断是否需要在线登录。
- 如果没有离线页，让文档拥有者把飞书权限改成公开可读，或导出 PDF/Word/Markdown 到本地目录后再解析。
- 若只拿到在线登录页但没有离线副本，文档内容应标记为未验证。

状态：

- 已找到本地离线页和学习整理，并已把可确认的 CANSimple 命令、对象/参数项、硬件接口和开发入口补入 `docs/MOTOR_PROTOCOLS.md`。
- 已确认协议页里的核心帧规则：标准 11-bit CAN ID，`can_id = (node_id << 5) + cmd_id`，8 字节小端数据，float32 按 IEEE754 编码。
- 从飞书离线 HTML 抽取内容时，直接 `grep`/`Select-String` 容易输出整页压缩脚本；更稳的做法是解析 HTML 内的 Feishu block JSON，再按 table 的 `rows_id`、`columns_id`、`cell_set` 还原表格。

### CANSimple heartbeat 扩展字节先 raw-first，不要过早命名

现象：

- 伺泰威 node 3 heartbeat `0x061` 实测 payload 类似 `00 00 00 00 08 80 CE 00`。
- byte0..3 和 byte4 可明确用于 axis error / axis state。
- 本地 M33 调试代码曾把 byte5/byte6/byte7 打印为 `flags/temp/life`，但协议表标题写的是 `Motor_Flag/Encoder_Flag/Controller_Flag/Traj_Done/Life`，二者还没完全对齐。

技巧：

- 数据采集可以保留 `heartbeat_byte5/6/7`。
- 在厂家字节级说明和 M33 现场验证前，不要把 byte6 当成可靠温度，也不要把 byte5 当成完整安全位。
- 平台和训练数据中标记 `heartbeat_extension_decode=raw_only_vendor_fields_unconfirmed`。

状态：

- `candump_motor_telemetry.py` 已按 raw-first 方式保留 heartbeat 扩展字节。

### CANSimple 不要把所有命令都假设成 8 字节 DLC

现象：

- 离线协议说明和示例强调 classic CAN 8 字节数据区。
- 但本地 M33 / NanoPi 调试实现中，`Set_Input_Torque` 只发送 4 字节 `float32 torque_nm`。
- 若后续固件或测试工具强制所有 CANSimple 命令都是 DLC=8，可能导致与当前可工作的调试路径不一致。

技巧：

- CANSimple 帧应按 `cmd_id` 建立 payload 合同。
- `Set_Input_Pos` 是 8 字节：`float32 pos_rev + int16 vel_ff_scaled + int16 torque_ff_scaled`。
- `Set_Input_Vel` 和 `Set_Limits` 是 8 字节双 float。
- `Set_Input_Torque` 当前按 4 字节 float 记录，正式执行前再做厂家表和现场实测确认。
- 文档中区分“classic CAN 最多 8 字节”和“某条命令实际 DLC”。

状态：

- `docs/MOTOR_PROTOCOLS.md` 已补充本地 M33/NanoPi 控制 payload 表。

### M33 汇总遥测要和 safety/status 分开

现象：

- `0x322` 已经承担 M33 总体 safety/status、control mode 和最近拒绝原因。
- 多个电机的角度、速度、温度、fault 标志无法可靠塞进单个 `0x322` 8 字节帧。

技巧：

- 保留 `0x322` 只表达安全状态和运动许可相关摘要。
- 为 M33 汇总后的每关节/电机遥测预留独立帧，例如 `0x330~0x337`。
- NanoPi 侧先写 parser 和单元测试，把字段标记为 `proposed_firmware_pending`，等 M33 固件实现后再接入 ROS topic。

状态：

- NanoPi 侧已新增 `psoc_motor_status.py` 和 7 个离线单元测试。
- `psoc_can_bridge_node.py` 已接入只读发布路径，收到合法 `0x330~0x337` 后发布 `/rehab_arm/motor_state`。
- 同一批 `0x330~0x337` 会同步发布 `/joint_states`，用于 RViz、MuJoCo 和平台 3D 预览；仍然只是遥测。
- M33 遥测会刷新 bridge 内部 `current_positions`，用于后续轨迹前置处理，但运动许可仍只看 `0x322` 和 M33 安全状态机。
- `m33_motor_status_smoke.py` 可先 dry-run，再用 `--execute` 向 `vcan0` 或明确选择的 CAN 口发送合成遥测帧验证链路。

### 合成遥测 smoke 工具默认必须干跑

现象：

- 为了验证 bridge 是否发布 `/rehab_arm/motor_state`，需要能在 M33 固件未上报 `0x330~0x337` 前制造测试帧。
- 但直接往真实 `can0` 发测试帧容易和现场调试混淆。

技巧：

- smoke 工具默认只打印 JSON dry-run 计划。
- 只有显式传 `--execute` 才会打开 SocketCAN。
- 先用 `vcan0` 验证 ROS bridge 和 recorder，再考虑真实 `can0`。
- 工具只允许发遥测帧，不发 `0x320` 控制帧。

状态：

- `m33_motor_status_smoke.py` 已按 dry-run-first 方式实现并测试。
- 该工具可写最小 JSONL，并已验证能通过 `hardware_telemetry` 质量门。
- 使用 `--output-jsonl` 时 stdout 会携带同一份 `quality_report`，平台可以直接读取，不需要另造质量判断规则。

### 真 CAN 采集时先确认哪些电机实际在线

现象：

- NanoPi `can0` 健康，`ERROR-ACTIVE`，1Mbps，tx/rx error counters 为 0。
- 被动抓包和 live snapshot 能稳定看到 3号伺泰威 `0x061/0x069`。
- 给 7号灵足临时打开 active-report 后，能稳定看到 `0x180007FD` 约 100Hz。
- 4/5/6 在本次 session 中无 Get_ID 回复，也无 active-report。

根因：

- 用户确认 4/5/6 已关闭/断电，所以它们没有回复是预期现象，不是解析器或 CAN 总线故障。

技巧：

- 先看 `ip -details link show can0`，确认 `ERROR-ACTIVE` 和 error counter。
- 再短时抓真实 CAN，按 ID 计数：`0x061/0x069` 对应 3号伺泰威，`0x180007FD` 对应 7号灵足 active-report。
- 对没有上电的电机，不要继续堆协议修改；先确认电源和驱动在线状态。
- `live_socketcan_motor_snapshot.py --enable-active-report 7` 只开临时状态上报，结束自动关闭，不是运动命令。
- 如果加 `--output-jsonl`，可以直接得到 recorder/platform 可读取的两行 JSONL：`session_metadata` 和 `/rehab_arm/motor_state`。
- 从 Windows PowerShell 远程 SSH 执行时，双引号里的 `$(date -u ...)` 会被 PowerShell 当成本机表达式先解析，可能导致远端文件名丢时间戳。固定文件名或先进入远端 shell 更稳。

状态：

- 已在 NanoPi 真 CAN 验证 3号和 7号遥测可采集；4/5/6 本轮因关闭不参与判断。

### M33 `0x330~0x337` 上报依赖新鲜电机反馈缓存

现象：

- M33 固件补了 `0x330~0x337` 发布线程后，NanoPi 不一定立刻看到这些帧。
- 手动运行 M33 shell `cmd_m33_motor_status_once` 可能输出 `sent=0`。

根因：

- M33 上报线程只读取 `s_motor_feedback[]` 中 1000ms 内更新过的缓存。
- 如果电机未上电、active-report 没打开、CAN 没收到 `0x061/0x069` 或 `0x180007FD`，M33 不会把旧数据伪装成实时状态。

技巧：

- 先用 NanoPi `candump` 看原始电机帧是否存在。
- 再看 M33 串口 `cmd_motor_fb <joint>` 或 `cmd_m33_motor_status_once`。
- `0x330~0x337` byte0 必须是 `B3`；没有 `B3` 不要让 NanoPi parser 当正式 M33 motor status。
- 这条链路是遥测，不是运动许可；`0x322` safety/status 仍然是正式安全裁决入口。

状态：

- M33 侧代码已准备，等待用户烧录后真 CAN 验证。

### 烧录后先看 M33 状态，再看电机缓存

现象：

- 烧录 M33 后，NanoPi `candump -L can0,330:7F8` 一开始可能没有任何 `0x330~0x337`。
- 但发送 NanoPi heartbeat 后可以收到 `0x322#A501070001010A00`。

根因：

- `0x322` 证明 M33 CAN 通信活着。
- `0x330~0x337` 还需要 M33 收到新鲜电机反馈缓存；没有电机主动上报时，M33 不会发布旧状态。

技巧：

- 先发无运动 heartbeat：`cansend can0 321#01`，监听 `0x322`。
- 再短时打开 7号灵足 active-report：`live_socketcan_motor_snapshot.py --iface can0 --duration 5 --enable-active-report 7`。
- 看到 `0x180007FD` 后，M33 应该开始发对应 slot 的 `0x336#B3...`。
- 这一步只验证遥测；不要发 `0x320`，不要发布 `/arm_controller/joint_trajectory`。

状态：

- 已验证 7号灵足 active-report 能触发 M33 发布 `0x336#B3...`，约 10Hz。

### `ros2 topic echo --once` 早于 topic 出现时要指定类型

现象：

- bridge 已发布 `/rehab_arm/motor_state`，但命令可能输出：

```text
WARNING: topic [/rehab_arm/motor_state] does not appear to be published yet
Could not determine the type for the passed topic
```

根因：

- `ros2 topic echo --once /topic` 启动瞬间如果 topic 还没有出现在 graph 里，CLI 无法自动推断类型并直接退出。

技巧：

- 对短时硬件验收命令显式写消息类型：

```bash
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

状态：

- 显式类型后已看到 `/rehab_arm/motor_state` JSON 字符串；`/joint_states` 已看到 `m33_status_slot_6`。

### Bash 严格模式加载 ROS setup 时要临时关闭 nounset

现象：

- `nanopi_live_telemetry_check.sh` 使用 `set -euo pipefail` 后，执行 `source /opt/ros/jazzy/setup.bash` 报错：

```text
AMENT_TRACE_SETUP_FILES: unbound variable
```

根因：

- ROS setup 脚本内部会读取未定义环境变量；这和 bash `set -u` 冲突。

技巧：

- source ROS 和 workspace setup 前后临时切换：

```bash
set +u
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
set -u
```

状态：

- 已在 `scripts/nanopi_live_telemetry_check.sh` 中修复，并在 NanoPi 真 CAN 验收通过。

### 轨迹门控只认 `motion_allowed=true`

现象：

- 旧版 `0x322` V1 可以解析成 `state=ok`。
- 但 V1 没有明确表达 M33 已经完成上电、自检、急停、限位、控制模式等运动许可检查。

根因：

- 对穿戴式机械臂，`state=ok` 只能说明状态包格式兼容或无错误码，不能等价于“允许运动”。
- 真正允许运动必须由 M33 在 `0x322` 中显式给出 `motion_allowed=true`。

技巧：

- NanoPi bridge 轨迹门控应使用 `motion_allowed` 作为唯一正向许可。
- V1 `state=ok`、V2 `logging_only`、`limited`、`fault`、`emergency_stop` 都必须拒绝轨迹。
- 当前 M33 返回 `state=limited/control_mode=logging_only/detail=logging_only_no_motor_output` 时，发布合法轨迹也应看到：

```text
safety limited: rejected trajectory: PSoC motion_allowed is not true, protocol_version=2, state=limited, control_mode=logging_only, detail=logging_only_no_motor_output
```

状态：

- 已加入 `safety_gate.py` 和单元测试；NanoPi 真 CAN 验证拒绝轨迹且 `can0,320:7FF` 无任何目标帧。

### `state=ok/armed` 仍要看 `detail_code`

现象：

- 如果只用 `state=ok` 和 `control_mode=armed/active` 判断可运动，可能忽略 M33 最近一次安全评估里的拒绝原因。

根因：

- 当前 `0x322` V2 byte6 是 `detail_code`，语义是 `last_safety_assessment`。
- 如果这个字段还是 `motor_fault`、`target_out_of_limit`、`logging_only_no_motor_output` 等非 `none`，说明 M33 还没有给出干净的运动许可。

技巧：

- NanoPi parser 的 `motion_allowed=true` 最小条件必须是：
  - `error_code=0`
  - `state=ok`
  - `control_mode=armed/active`
  - `detail_code=none`
- M33 后续进入 `armed` 前，要先清掉或覆盖最近拒绝原因，并把真实安全检查结果反映到 `detail_code`。

状态：

- 已收紧 parser 并加入测试：`ok/armed/detail=motor_fault` 仍解析为 `motion_allowed=false`。

### Pre-arm 检查表默认失败才是安全默认

现象：

- M33 新增 `cmd_m33_prearm_check` 后，当前阶段预期输出 `ready=0`。

根因：

- 当前固件仍然 `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`。
- 急停输入、供电输入、最终限位确认都还没有接入真实硬件合同。
- 并非所有参与运动的电机都有新鲜反馈。

技巧：

- `cmd_m33_prearm_check` 只用于观察，不改变状态。
- 先看 `PREARM_MODE`，再看 `PREARM_INPUTS`，最后看 `PREARM_MOTORS`。
- `fresh_mask` 表示 M33 最近收到反馈的关节/电机槽位，不是运动许可。
- 只有当 M33 未来能稳定给出 `ready=1`，并且 `0x322` 同时满足 `motion_allowed=true` 合同时，NanoPi 才可能进入真实轨迹测试。

状态：

- M33 代码已编译通过；等待用户需要时烧录后现场查看。

### Pre-arm `fresh_mask=0` 说明检查瞬间没有满足新鲜反馈

现象：

- 烧录后运行 `cmd_m33_prearm_check` 输出：

```text
PREARM_MOTORS: required_mask=0x0000007F fresh_mask=0x00000000 ... fresh_ok=0
```

根因：

- pre-arm 使用 M33 缓存里的新鲜电机反馈判断。
- 如果运行串口命令时电机没有持续上报，或 active-report 已经关闭并超过 freshness 窗口，`fresh_mask` 就会是 0。
- 这不表示 CAN 坏；同一次上电已经通过 NanoPi live telemetry check 看到 `0x336`。

技巧：

- 需要验证 motor freshness 时，先让目标电机持续上报，再立刻运行 `cmd_m33_prearm_check`。
- 当前默认 `CONTROL_PREARM_REQUIRED_JOINT_MASK=0x7F` 要求 7 个槽位都有新鲜反馈；如果现场只上电 7 号，后续应先把 required mask 改成当前测试所需的最小集合。
- `ready=0` 是安全默认；不要为了让它变 1 而临时跳过急停、供电、限位确认。
- 新增的 `cmd_m33_prearm_check 0x40` 只用于本次诊断 slot6 freshness；它不修改默认配置，也不代表可运动。

状态：

- 已记录。下一步应先做“测试用 required mask”而不是开放运动。

### Pre-arm 诊断 mask 要和 active-report 同时测

现象：

- 第一次并发测试 `cmd_m33_prearm_check 0x40` 时，远端命令路径写错，7号 active-report 没有真正打开，结果仍是 `fresh_mask=0`。
- 修正远端工作目录后，7号 active-report 打开 8 秒，M33 输出 `fresh_mask=0x00000040 fresh_ok=1`。

根因：

- `cmd_m33_prearm_check 0x40` 只改变 required mask，不会主动打开电机上报。
- 必须在 M33 缓存 freshness 窗口内运行命令。

技巧：

- 正确顺序：
  1. NanoPi 打开 `live_socketcan_motor_snapshot.py --enable-active-report 7 --duration 8`。
  2. 在窗口内发一次 `cansend can0 321#xx` 保持 heartbeat 新鲜。
  3. M33 串口运行 `cmd_m33_prearm_check 0x40`。
- 看到 `fresh_mask=0x40 fresh_ok=1` 只说明 slot6 telemetry 新鲜，不表示 pre-arm ready。

状态：

- 已验证 slot6 freshness 可观测；`ready` 仍保持 0。

### Pre-arm 安全输入要区分“已确认”和“当前安全”

现象：

- 急停、供电、限位这些输入还没有接真实 GPIO/ADC。
- 如果只用 `*_CONFIRMED=1` 表示“这一路做过验证”，后续可能忘记同时检查当前电平/电压/限位状态。

根因：

- 穿戴式设备的安全输入有两个不同问题：这路输入是否已经接线并验证过，以及此刻它是否处于安全状态。
- 二者不能混成一个布尔值。

技巧：

- M33 pre-arm 需要同时满足 `confirmed=1` 和 `safe_now=1`。
- 当前默认 `source=unwired`、`confirmed=0`、`safe_now=0`，所以 `ready=0` 是正确结果。
- `cmd_m33_safety_inputs` 只打印合同，不改变模式，不允许输出。
- `cmd_m33_prearm_check` 的 `PREARM_INPUT_DETAIL` 用来快速确认哪一路还没有接入或当前不安全。

状态：

- 已在 M33 侧加入诊断命令和收紧后的 ready 条件。
- 用户烧录后已验证：`cmd_m33_safety_inputs` 显示三路安全输入均为 `source=unwired confirmed=0 safe_now=0`，`cmd_m33_prearm_check 0x40` 在 7 号 telemetry 新鲜时仍保持 `ready=0`。

### 安全输入先写映射合同，再接真实输入

现象：

- 急停、电源/电压、限位都非常关键，但当前还没有确认具体 pin、ADC channel、硬限位类型或常开/常闭逻辑。

技巧：

- 先维护 `docs/M33_SAFETY_INPUT_MAPPING.md`，把输入源、确认条件、当前安全条件和失败 detail 写清楚。
- 真实固件读取要一项一项加，先只读 raw value，再转 `safe_now`，最后才接入 pre-arm。
- 不要为了推进 `armed` 状态而把 `confirmed` 写死为 1；没有现场验证时必须保持失败。

状态：

- 已新增映射合同文档。下一步等真实接线信息后，先做急停只读诊断。

### 40Pin 安全输入只接 3.3V 逻辑

现象：

- 已从 40Pin RPI 兼容排针中预选 pin 11 作为急停诊断输入。
- 用户确认只有急停需要接 GPIO；电源 OK 不管，限速和限位后续由自己在 M33 代码里设置。

技巧：

- GPIO 只接 3.3V 逻辑，不能直接接电池、电机母线或 5V。
- 急停优先用常闭链路，断线也应读成不安全。
- 电源 OK 当前标记为 `not_used_no_power_ok_input`，不作为接线或实现任务。
- 限速和限位先作为 M33 代码配置，等用户根据真实机械结构写入代码后再确认。
- 选 pin 或写软限位不等于确认安全，固件第一步只能打印 raw value/配置状态，不能让 `confirmed=1` 或 `motion_allowed=true`。

状态：

- 已记录 estop pin 选择和电气语义；尚未实现或验证 GPIO 读取。

### 限速限位先作为 M33 代码配置项

现象：

- 用户明确限速、限位后续由自己直接改 M33 代码设置，不接 GPIO。

技巧：

- pre-arm 要分别暴露位置限位、速度限制、扭矩/电流限制，不要只用一个模糊的 `limits_confirmed`。
- 默认必须是 `confirmed=0 safe_now=0`，这样用户还没填真实参数前不会误进入运动许可。
- 串口看 `PREARM_CODE_LIMITS`，确认三类限制各自状态。

状态：

- M33 已预留 `PREARM_CODE_LIMITS` 输出；等待后续烧录验证。

### 开发台架小幅运动也必须保留 M33 审核

现象：

- 为了尽快打通 `ROS2 JointTrajectory -> NanoPi -> M33 -> motor`，开发阶段需要允许小幅真实运动。
- 原 logging-only 路径只打印不执行；直接关闭 logging-only 会暴露真实执行路径的问题。

根因：

- M33 之前在非 logging-only 分支里存在“入队一次 + 直接执行一次”的结构，可能导致同一条 `0x320` 被执行两次。
- NanoPi/ROS 使用 `0-based` joint id，M33 底层电机关节函数使用 `1-based` joint id，关闭 logging-only 前必须显式转换。

技巧：

- 用 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` 表示台架开发模式，不把它和正式穿戴 pre-arm 混在一起。
- 台架运动也必须先过 M33 审核：关节号、位置、速度、扭矩/电流、heartbeat。
- 当前开发限位是 `-60°~+60°`，速度 `-5~+5 rpm`，`torque_ma=0`。
- 禁止把这种台架模式当作人体穿戴许可；正式模式仍需要急停和最终限速/限位/限流安全确认。

状态：

- M33 已修正为审核通过后单次直接应用；已编译 `control_layer.o`，未烧录验证。

### SSH 端口可连但握手被远端关闭时不要继续动电机

现象：

- 烧录 M33 后，Windows 主机尝试 `ssh pi@192.168.2.66`。
- 一开始连接超时，后续 TCP 能建立，但 SSH 在 banner/key exchange 前被远端关闭或 reset。
- 典型输出：

```text
kex_exchange_identification: Connection closed by remote host
Connection closed by 192.168.2.66 port 22
kex_exchange_identification: read: Connection reset
Connection reset by 192.168.2.66 port 22
```

判断：

- 这不是 ROS 或 CAN 协议问题，首先是 NanoPi 网络/SSH 服务可用性问题。
- 在不能远程看 `can0`、`candump`、ROS bridge 和 M33 状态日志时，不应发送 `0x320` 或运动轨迹。

排查顺序：

- 现场确认 NanoPi IP 是否仍是 `192.168.2.66`。
- 在 NanoPi 本机执行 `hostname -I`、`sudo systemctl status ssh`、`sudo systemctl restart ssh`。
- 如果 SSH 仍被 reset，查看 `sudo journalctl -u ssh -n 80 --no-pager`。
- SSH 恢复后先运行只读检查：`ip -details link show can0`、短时间 `candump -L can0`、ROS `/rehab_arm/safety_state`。

状态：

- 当前远程验收被 SSH 阻塞；没有发送运动命令。

### 先证明 0x322 为 ok/armed，再发 0x320

现象：

- M33 开发台架固件刚烧录后，NanoPi bridge 能发 `0x321`，但如果 `0x322` 仍是 `A5xx070001020A00`，NanoPi 会拒绝轨迹。
- 修正启动 detail 后，`0x322` 变为 `A5xx070000030000`，bridge 才允许 `enable_target_tx=true` 的轨迹下发。

技巧：

- `0x322#A5xx070000030000` 是当前台架开发模式的放行状态：`safety=ok`、`mode=armed`、`detail=none`。
- 发布轨迹前先抓包确认 `0x321/0x322` 连续稳定，CAN 为 `ERROR-ACTIVE`。
- 对 3 号伺泰威，当前正规链路是 `shoulder_abduction_joint` -> ROS joint id `2` -> M33 motor joint `3`。
- 3 号小幅验证帧：`0x320#03020B0005000000`，约等于 joint2 目标 `1.1°`、`5 rpm`、`torque_ma=0`。
- 更明显但仍在边界内的 3 号验证帧：`0x320#0302AD0105000000`，约等于 joint2 目标 `42.9°`、`5 rpm`、`torque_ma=0`。
- 用户要求超过当前限位的角度时，不要绕过 M33/bridge 限位；先给出当前可执行上限内的动作，后续再通过代码审查和烧录调整限位。

状态：

- 已实测 motor3 正规链路能从 ROS trajectory 触发 M33 电机输出。

### motor7 当前只能算直接 CAN 调试，不算正式路径

现象：

- 用户允许开发阶段动 7 号。
- 当前 ROS bridge 只映射 5 个 ROS 关节，M33 对 `0x320` 的 ROS joint id 也只接受 `0..4`，还没有正式映射到 M33 motor joint7。

技巧：

- 如果必须临时验证 7 号，只能明确标为 debug direct CAN：
  - `nanopi_can_master.py private speed --motor 7 --vel 0.05 --kd 1.0`
  - 短时间后必须发送 `nanopi_can_master.py private stop --motor 7`
- 直接 private CAN 绕过 M33 `0x320` 安全审核，不能作为正式机器人开发路径。
- 打开 7 号 active-report 后要关掉，避免总线一直刷 `0x180007FD`。

状态：

- 已短促验证 motor7 private CAN 指令和反馈；下一步应把 7 号接入正式 `0x320` 映射。

### CANSimple 命令帧出现不等于 3号电机真的动了

现象：

- ROS/M33 给 motor3 发出 `0x320#0302AD0105000000` 后，CAN 上能看到 `0x067/0x068`。
- 用户现场反馈 3号没有明显运动。
- 进一步检查时，M33 对 motor3 的 `0x332` 状态帧仍是 `B3 xx 03 00 00 00 00 00`，没有有效位置/速度/温度变化。

判断：

- `0x067/0x068` 很可能只是 M33 发出的 CANSimple 命令或 SocketCAN echo，不是电机已经进入 closed-loop 的证据。
- 如果没有 CANSimple heartbeat、encoder estimate、error/status 回复或 M33 缓存状态变化，就不能认为 motor3 被真正控制。

技巧：

- 3号调试下一步先证明 motor3 自己在线：
  - 查 CANSimple heartbeat 或厂家状态帧。
  - 查 node id 是否仍是 3。
  - 确认驱动电源、使能状态、错误码和 closed-loop 状态。
  - 不要靠 `can0` 仍为 `ERROR-ACTIVE` 判断目标电机 ACK，因为总线上其他节点也可能 ACK。

状态：

- 当前 motor3 正规链路已能把命令发到 M33，但 motor3 执行/反馈未打通。

### motor7 直接 CAN pulse 后要恢复安静

现象：

- 为了让动作更明显，motor7 直接 private CAN 速度从 `0.05 rad/s` 提到 `0.30 rad/s`，保持约 1s。
- active-report 打开后总线会持续出现 `0x180007FD` 或 `0x188007FD`。

技巧：

- 测试后必须发送 `private stop --motor 7`。
- 测试后关闭 active-report：`private active-report --motor 7` 不带 `--enable-report`。
- 如果临时启动了 `enable_target_tx=true` 的 ROS bridge，测试结束后停掉，避免后续误发轨迹。

状态：

- 已执行 stop，关闭 7号 active-report，并停止 ROS bridge。

### 直接电机调试后必须做 quiet check

现象：

- motor7 再次直接 private CAN 测试时，运动阶段能看到 `0x188007FD` 反馈变化，M33 聚合帧 `0x336` 也跟着变化。
- 如果 active-report 没有关掉，后续总线会持续刷反馈帧，容易误判为正式控制链路仍在运行。

技巧：

- 每次直接调试 7号后按固定顺序收尾：`private stop --motor 7`，再运行 `private active-report --motor 7` 关闭主动上报。
- 收尾后运行 `timeout 1 candump -L can0 | head -20`，期望没有持续 `0x180007FD/0x188007FD`。
- 同时查 `ps -ef | grep -E '[p]soc_can_bridge|[r]os2'`，确认没有 `enable_target_tx=true` 的 ROS bridge 遗留。
- `can0` 需要保持 `ERROR-ACTIVE` 且错误计数为 0；否则下一次动作前先排 CAN 物理层或供电。

状态：

- 已完成一次 motor7 复测并确认 stop 后总线安静。

### motor7 反馈 ID 的电机号不总在同一个字段形态，角度映射不能直接信

现象：

- 7号静止主动上报常见为 `0x180007FD`。
- 7号运动反馈会出现 `0x188007FD`。
- 如果只匹配 `data2 == 0x0007`，会漏掉 `0x8007` 这种运动反馈，导致软件以为角度没有变化。
- 修正 ID 匹配后，软件解出的相对变化约为 `55°`，但用户现场观察到实际转了很多圈。

技巧：

- 解 7号 private feedback 时，扩展帧格式为 `type/data2/data1`。
- 对 7号反馈应匹配 `(data2 & 0xFF) == 7` 且 `data1 == 0xFD`，不要只匹配完整 `data2 == 0x0007`。
- 不要把当前脚本里的 `data[0:2] -> -12.57~12.57 rad` 当作输出轴角度或关节角度；它可能是电机内部截断位置、单圈字段、编码器原始映射，或还缺少减速比/多圈累计。
- 在完成实物标定前，7号角度限位不能依赖这个字段，只能使用人工观察、低速短时、外部编码器/限位、或 M33 中经过验证的角度来源。

状态：

- 7号 private feedback 的 ID 识别规则已验证；角度数值映射已被现场观察推翻，后续必须重新标定。

### 7号标定优先用定时低速脉冲，不用未知角度闭环

现象：

- 用户要求观察 7号实际转角。
- 由于反馈角度映射不可信，不能再用“解码到 60°自动停”作为控制条件。

技巧：

- 标定阶段用固定速度和固定时间：例如 `5 rpm` 跑 `3s`，再立即 stop。
- 现场记录实际输出端角度或圈数，再反推真实比例。
- 每次脉冲后关闭 active-report，并用短 `candump` 确认没有 `0x180007FD/0x188007FD` 持续刷屏。

状态：

- 已完成 `5 rpm / 3s` 的 7号定时标定脉冲；用户确认输出面约转 `150°`。
- 这意味着当前 direct private speed 命令 `5 rpm` 对应可见输出端约 `50°/s`，即约 `8.33 rpm`。不要把命令名或脚本参数直接当真实输出 rpm。
- 下一轮建议在输出面贴一条明显胶带或画线，并固定手机视角，再做同样的 `5 rpm / 3s` 标定。

### 先查官方型号和减速比，再解释实测速度

现象：

- 7号 `5 rpm / 3s` 目测约 `150°`，和“命令名就是输出端 5 rpm”的直觉不一致。
- 用户提醒必须查官方资料和减速比。

结论：

- 3号伺泰威减速比为 `48:1`，但目前还没现场看到它真实运动。
- 4号、5号是灵足 RS00，官方减速比 `10:1`。
- 6号、7号是灵足 EL05，官方减速比 `9:1`。
- 资料来自本地官方 RobStride 产品规格书、RS00/EL05 使用说明书，以及现场型号确认。

技巧：

- 减速比只能解释电机侧和输出侧的机械比例；不能自动证明 CAN `speed` 参数、MIT feedback 位置字段或 active-report 位置字段就是输出轴物理角度。
- 对 6/7 号 EL05，后续需要单独补 EL05 的量程、参数表和反馈字段，不能直接套 RS00 的 ROS 示例量程。
- 对 3号伺泰威，在现场未看到动作前，不要把“命令帧发出”写成“控制已打通”。

状态：

- 已把 3/4/5/6/7 型号和减速比写入项目文档；下一步在代码中建立 RS00/EL05 分型号表。

### EL05 不要套用 RS00 的工程量程

现象：

- 本地 `robstride_ros_sample` 有 RS00~RS06 的示例量程，但没有单独 EL05 枚举。
- 6号、7号已经确认是 EL05，且 7号反馈角度映射已被现场观察推翻。

技巧：

- NanoPi 侧可以记录 `actuator_type=EL05` 和 `gear_ratio=9.0`。
- 在确认 EL05 官方量程/字段前，6/7号 active-report 的 position、velocity、torque 继续保持 `None`，只保留 raw 字段。
- 4/5号 RS00 可以使用现有 RS00 示例量程做临时工程解码，但正式 M33 侧仍要再次限幅和标定。

状态：

- 已在 `candump_motor_telemetry.py` 中按该策略实现，并用单测覆盖。

### 3号 CANSimple 命令发出不等于执行已打通

现象：

- 3号伺泰威减速比为 `48:1`，但目前还没现场看到它真实运动。
- 直接 CANSimple 测试已发送 clear errors、closed-loop、velocity mode/input velocity、zero velocity、idle。
- CAN 上能看到命令帧 `0x078`、`0x067`、`0x06B`、`0x06D`，但 M33 聚合状态 `0x332` 仍为零。

判断：

- 当前只能证明 NanoPi 到 CAN 总线的命令发送成功。
- 仍不能证明 3号驱动已经进入 closed-loop、编码器有效、刹车释放、功率级使能或反馈协议已被 M33 正确解析。

技巧：

- 继续加大速度前，先找 3号真实 heartbeat/status/encoder feedback 帧。
- 减速比 `48:1` 需要在规划侧处理：输出端角度/速度乘以 48 后才是电机侧命令量。
- 若以输出端 `5 deg/s` 为目标，电机侧约为 `4.19 rad/s`；这次使用 `4.0 rad/s` 电机侧命令属于温和台架测试。

状态：

- 3号已执行直接 CANSimple温和速度测试并退回 idle；执行/反馈仍未确认。

### 绝对位置控制必须先过软件零点标定门

现象：

- 7号通过 M33 正式路径收到 `30°` 绝对目标后，现场出现剧烈转动。
- 后续查 RobStride 官方示例，帧 `01800007#855481370F5C3333` 按 EL05 映射约为 `30°` 目标、`0.475 rad/s`、`Kp=30`、`Kd=1`，编码本身不像是把 `30°` 写成几百度。

判断：

- 更可能的问题是机械零位、方向、当前位置参考和真实输出角度比例未标定。
- 在这种状态下，任何绝对位置闭环都会让电机去追一个软件认为正确、机械上却不一定安全的位置。

技巧：

- 标定前，M33 必须拒绝 ROS `set_target` 和 `motor_pos` 这类绝对位置控制。
- `m33_joint_calib [joint]` 用来确认 `calibrated/direction/gear/zero_offset`。
- `0x322 detail_code=11` 表示 `joint_uncalibrated`，NanoPi ROS 必须把它解析为 `motion_allowed=false`。
- 标定时优先使用低速短脉冲、人工观察和外部标记，先确认方向和比例，再启用小角度位置闭环。

状态：

- 已在 M33 添加默认未标定门；所有关节默认 `calibrated=0`。
- 后续需要烧录后验证：合法 `0x320 set_target` 应被拒绝为 `joint_uncalibrated`，不应再发出电机位置帧。

### 验证 joint_uncalibrated 前要先刷新 heartbeat

现象：

- 烧录 `daf78140` 后，第一次向 M33 发送合法 `0x320 set_target` 得到 `detail_code=1 heartbeat_timeout`，不是预期的 `joint_uncalibrated`。
- 随后按 `heartbeat -> target -> heartbeat` 顺序重测，得到 `0x322#A540070001010B00`，即 `detail_code=11 joint_uncalibrated`。

原因：

- M33 的安全评估先检查 NanoPi heartbeat 是否新鲜。
- 如果 heartbeat 过期，安全机在更早一层拒绝，不会继续走到“关节是否标定”的检查。

技巧：

- 验证某个具体拒绝原因时，先发一帧 `0x321` heartbeat，让 heartbeat 条件通过。
- 然后立刻发目标帧，再发下一帧 heartbeat 读取 `0x322` byte6。
- 如果目标是验证 `joint_uncalibrated`，过滤 `candump` 时要确认没有对应电机控制帧，例如 7号没有 `01800007`、`0300FD07`、`180007FD/188007FD`。

状态：

- 已现场验证：合法 7号目标在未标定状态下被拒绝为 `joint_uncalibrated`，没有下发 7号电机控制帧。

### 标定遥测和运动命令要分开

现象：

- 下一步需要通过 M33 正式链路读取 7号当前位置/原始反馈。
- 直接使用 ROS 绝对目标不安全，直接 NanoPi private active-report 又绕过 M33 正式链路。

策略：

- 允许 `0x320 active-report` 作为 calibration telemetry 通过 M33。
- 不允许 `enable/zero/mode/target` 因此一起通过。
- M33 日志用 `apply_calibration_telemetry_only` 标记这种非运动遥测动作。

技巧：

- 开遥测前先发 heartbeat，避免被 `heartbeat_timeout` 拦截。
- 采集完必须关闭 active-report，并用短 `candump` 确认没有持续 `180007FD/188007FD`。
- 过滤 CAN 时要同时确认没有 7号控制帧 `01800007`。

状态：

- 已在 M33 代码中加入遥测例外，待烧录后验证。

### M33 active-report 遥测验证通过后仍要区分原始反馈和聚合状态

现象：

- 烧录 `9e1573d7` 后，通过 `0x320#060401` 成功打开 7号 active-report。
- 抓包出现 `0x180007FD` 原始主动上报和 `0x336` M33 聚合状态。
- 关闭 active-report 后，`0x180007FD/0x188007FD` 停止，但 `0x336` 仍周期性出现。

判断：

- `0x180007FD/0x188007FD` 是电机原始 active-report；关闭后应该停止。
- `0x336` 是 M33 聚合/缓存状态发布，关闭 active-report 后仍可能继续发最近缓存值，这是正常状态输出，不代表电机还在持续主动上报。

技巧：

- 验证关闭 active-report 是否成功，应重点看 `180007FD/188007FD` 是否消失。
- 同时确认没有 `01800007` 或 `0300FD07`，避免把遥测入口误变成运动控制入口。
- 如果 SSH wrapper 超时，先补发关闭 active-report，再读 `/tmp/*.candump` 文件做事后分析。

状态：

- 已现场验证：M33 formal `active-report` telemetry path 可用，且没有 7号运动控制帧。

### 标定观测报告不能当成运动标定证明

现象：

- `0x180007FD` 原始主动上报和 `0x336` M33 聚合状态都能显示位置字段。
- 这些字段能证明“遥测链路通了”，但不能证明“物理关节角度已经正确映射”。

原因：

- 7号曾经出现过软件角度看似接近限位、现场实际转动明显更多的情况。
- RobStride private protocol 的 `+/-12.57 rad` 字段映射是电机侧协议范围，不等于本项目已经完成输出关节零点、方向和比例标定。

技巧：

- 用 `calibration_observation <candump.log> --pretty` 先做无运动报告。
- 报告里的 `safe_to_use_as_motion_proof` 必须保持 `false`，它只用于确认有无遥测、有无误发运动帧。
- 只有人工确认机械零点、方向、小角度正反向和 M33 限位后，才允许把对应关节的 `CALIBRATED` 改为 `1U`。

状态：

- 已加入自动化测试，能检测 `01800007` 这类 7号运动控制帧并让报告 `ok=false`。

### 未装机阶段可以先用直接台架配置

现象：

- 当前机械臂还没有装机，用户希望先“随便一个零点”打通正式 M33 运动链路。

策略：

- 在未装机、空载、有人观察的阶段，允许直接把 7号设为 `CALIBRATED=1`、`ZERO_OFFSET=0` 来快速打通链路。
- 仍保留 M33 的 heartbeat、joint limit、rpm limit、torque/current limit 检查。
- 装机或穿戴前必须撤销这种台架配置，重新做机械零点、方向、限位和急停验收。

技巧：

- 临时零点后只测 `+5°/-5°`，用肉眼确认方向和幅度，再考虑更大角度。
- 只要方向/幅度不符合预期，立刻停止，不要用更大目标“试出来”。

状态：

- M33 已改为 7号直接台架标定配置，待烧录后现场验证。

### 正式路径打通不等于物理标定完成

现象：

- M33 台架版本烧录后，NanoPi `m33 target --joint 4 --deg 5 --rpm 1` 成功产生 7号厂家控制帧。
- CAN 上可见 `0x0300FD07`、`0x01800007`，stop 后可见 `0x0400FD07`。

判断：

- 这说明 `NanoPi -> 0x320 -> M33 safety gate -> motor7 private protocol` 这条链路已经能发命令。
- 但它不能证明物理方向、零点和输出角度比例是正确的。

技巧：

- 每次正式路径小角度试动后，马上发 `m33 stop --joint 4`。
- 先让现场观察者确认 `+5°` 的方向和大概幅度，再测 `-5°`。
- 如果方向反了，优先改 `CONTROL_MOTOR_JOINT7_DIRECTION`；如果幅度不对，再回到减速比/协议量程/机械输出映射排查。

状态：

- CAN 链路已现场验证，物理运动效果待用户确认。

### RobStride 参数位置反馈可能不等于可见输出轴运动

现象：

- Direct MIT 和 official CSP flow 都能让 CAN feedback/M33 `0x336` 的位置字段变化。
- 用户现场反馈 small direct target 没有可见运动。
- Official CSP flow 后 `0x336` 从约 `0.554 rad` 变化到约 `1.050 rad`，但仍需用户确认可见输出是否真的动了。

判断：

- 这排除了“完全没有发到电机”的问题，因为 enable、parameter write、feedback 都出现了。
- 当前不能继续把 `0x336 pos_mrad` 当作已经验证的输出关节角。

技巧：

- RobStride 位置模式应优先按官方参数流验证：`run_mode=5`、enable、`limit_spd(0x7017)`、`loc_ref(0x7016)`。
- 下一步读取 `0x7019 mechPos` 等官方机械/负载端参数，与现场视频标记对齐。
- 只有当“读数变化”和“可见输出轴变化”一致后，才能把该字段接入 M33 关节状态和安全限位。

状态：

- Official CSP CAN flow 已跑通；物理输出映射未完成。

### Motor7 RobStride 位置单位已按输出侧角度处理

现象：

- Official CSP 从约 `3.0 rad` 回到 `1.0 rad`，理论变化 `1.997 rad = 114.4°`。
- 用户现场确认看到的也是约 `114.4°`，而不是除以 `9` 后的约 `12.7°`。

根因/判断：

- 对 7号 EL05 当前 CAN 参数接口来说，`loc_ref` 和反馈位置已经对应可见输出侧角度。
- M33 原来把 ROS joint 角度乘以 `gear_ratio=9` 再发给 RobStride，这会把正式路径目标放大。

修正：

- 7号正式 ROS 映射临时改为 `CONTROL_MOTOR_JOINT7_GEAR_RATIO=(1.0f)`。
- 当前台架零点用 `CONTROL_MOTOR_JOINT7_ZERO_OFFSET_RAD=(1.0f)`，让 ROS joint4 `0°` 对齐最后确认的台架姿态。

状态：

- 待烧录后验证 formal path `joint4 +5°` 是否实际输出约 `5°`。

### Lingzu 正式位置控制优先走 CSP 参数流

现象：

- 7号 official CSP flow 能产生可见约 `114.4°` 输出运动。
- M33 formal path 之前使用 MIT 控制帧，虽然 CAN 帧发出，但 fixed-scale retest 只到约 `1.009 rad`，没有到 `1.087 rad` 目标。

判断：

- 对 4/5/6/7 灵足 RobStride 电机，正式 `0x320 set_target` 不应继续依赖 MIT frame 作为位置模式。
- 应使用官方 CSP 参数流：`run_mode=5`、enable、`limit_spd(0x7017)`、`loc_ref(0x7016)`。

修正：

- M33 `control_joint_motor_set_target()` 改为调用 `control_motor_position_control(..., csp_mode=true)`。
- 4/5/6/7 的 formal ROS 映射比例临时统一为 `1.0f`，按输出侧角度处理。

状态：

- 待烧录后验证。

### Motor3 CANSimple 速度参数是电机侧，输出端要按 48:1 看

现象：

- Direct `cansimple vel --node 3 --vel 0.5` 数据通了，但输出端可能不明显。
- Direct `--vel 8.0` 跑约 `2s` 后，M33 `0x332` 输出角从约 `0.739 rad` 到 `1.147 rad`，变化约 `23.4°`。

判断：

- NanoPi direct CANSimple `--vel` 是电机侧 rad/s，不是输出关节侧 rad/s。
- 3号保留 48:1 映射是合理的：输出角约等于电机侧角度除以 48。

修正：

- M33 3号台架配置保持 `CONTROL_MOTOR_JOINT3_GEAR_RATIO=(48.0f)`。
- 当前台架姿态作为临时零点：`CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(55.1f)`。
- 放开台架 formal：`CONTROL_MOTOR_JOINT3_CALIBRATED=1U`。

状态：

- 待烧录后验证 formal joint0 小角度控制。

### 不要把 RobStride 的输出轴单位结论套到伺泰威 CANSimple

现象：

- 7号 RobStride/EL05 经 CSP `loc_ref` 实测后，确认该路径在当前台架上按输出侧角度理解。
- 3号伺泰威也在做 formal path 标定，用户提醒不要盲目 `x48`。

判断：

- 两类电机协议不能混用结论。
- RobStride formal CSP 的 `loc_ref` 已被现场观察验证为输出侧角度。
- 伺泰威 CANSimple/ODrive-like 的 `Set_Input_Pos`、`Get_Encoder_Estimates` 在 ODrive 官方协议里都是 `rev/rev_s` 单位，不是“输出轴度数”接口。

技巧：

- 对 3号，如果继续使用 CANSimple，M33 里保留 `joint -> motor protocol` 的减速比换算。
- 如果希望 3号像 RobStride CSP 那样直接按输出轴角度发命令，应单独做伺泰威 MIT/output-axis RAD 协议路径，先低速台架验证，再进 formal path。
- 现场看到幅度不对时，不要直接把 `gear_ratio` 改成 `1.0`；先确认当前命令到底是 CANSimple、MIT 还是 CANOpen。

状态：

- 已记录源驱动路线：ODrive CAN protocol 与 `odriverobotics/ros_odrive`。

### 3号 direct 能动但 formal 不动时先看 0x322 detail

现象：

- Direct CANSimple 对 3号发送“当前位置 + 输出约 5°”后，`0x069` 从约 `7.66448 rev` 到 `8.33206 rev`，折算输出约 `5.0069°`。
- 但 `m33 target --joint 0 --deg 5 --rpm 1` 没有触发 M33 发 `0x06C Set_Input_Pos`。
- 随后的 heartbeat 回复 `0x322 = A5 79 07 00 01 02 0B 00`。

判断：

- byte6/detail code `0x0B` 是 `JOINT_UNCALIBRATED`。
- 这说明 M33 安全状态机拦截了 formal path，电机没有收到 formal 位置命令。
- 此时不能继续怀疑 CANSimple 公式本身；direct path 已证明 3号能按 `rev` 单位移动。

技巧：

- formal path 不动时，先发一次 heartbeat，看 `0x322` 的 detail code。
- 如果 detail 是 `0x0B`，需要烧录包含对应 `CONTROL_MOTOR_JOINTx_CALIBRATED=1U` 的 M33 bench 固件，或继续让 formal path 保持安全关闭。
- 不要为了绕过这个状态直接把安全门删掉；台架调试可以临时开 gate，但文档里必须标清这是未装机 bench 配置。

状态：

- 3号 direct CANSimple 已验证；formal M33 仍受当前板端固件 calibration gate 阻挡。

### 3号 formal 发了位置帧但几乎不动时检查 Set_Limits 第二字段

现象：

- 烧录 bench firmware 后，formal `m33 target --joint 0 --deg 5` 不再被 `JOINT_UNCALIBRATED` 拦截。
- CAN 上能看到 `0x06B`、`0x06F`、`0x067`、`0x06C`。
- 但 `0x069` 只变化约 `0.00408 rev`，折算输出约 `0.03°`。

判断：

- M33 的 CANSimple position path 原先把 `Set_Limits` 第二个 float 写成 `0.0`。
- 对伺泰威/ODrive-like 位置模式，这个字段不能作为可用限流长期为 0，否则位置目标可能发出但几乎没有执行能力。

修正：

- M33 commit `ed1cfc49` 增加 `CONTROL_CANSIMPLE_POSITION_LIMIT_CURRENT=(5.0f)`。
- 位置目标仍发 `Torque_FF=0`，只是 `Set_Limits` 提供非零限流。

状态：

- 待烧录 `ed1cfc49` 后复测 formal joint0。

### 3号大角度前必须先确认 0x061/0x069 在线

现象：

- direct 30° timed velocity attempt 发送了 `clear`、`closed-loop`、`velocity`、`idle` 命令。
- 该次测试期间没有捕获到 3号 `0x061/0x069`，只看到 M33 `0x332` 缓存状态。

判断：

- 没有 `0x061/0x069` 时不能仅凭 TX 命令帧判断 3号已执行。
- 先前 direct +5° 成功依赖 `0x069` 明确变化；同样标准也必须用于 30°验证。

技巧：

- 大角度前先被动监听 1~3 秒，确认 node3 heartbeat/encoder 在线。
- 如果 node3 反馈缺失，先恢复 closed-loop/反馈，再做位置测试；不要把 M33 缓存状态当成电机实时反馈。

### 3号没有 0x061/0x069 时不要继续盲发动作

现象：

- 用户确认 3号 30°尝试没有动。
- 被动监听 2 秒没有任何 3号帧。
- 主动发 node3 `Get_Error/Clear/Closed-loop/Idle` 后，只看到 M33 `0x332`，没有 3号 `0x061/0x069`。
- M33 heartbeat 仍正常，NanoPi `can0` 仍为 `ERROR-ACTIVE`。

判断：

- NanoPi CAN 和 M33 通信是活的，但 3号 Sitaiwei 当前没有作为 CANSimple node3 响应。
- M33 `0x332` 是聚合/缓存状态，不能替代 3号实时 CANSimple 反馈。

技巧：

- 先查 3号供电、使能、CANH/CANL、节点 ID、协议模式、是否被上位机切换过通信协议。
- 恢复标准是先被动看到 `0x061` heartbeat 和 `0x069` encoder estimate。
- 没有恢复前，不要继续尝试 30°、90°或 formal path 大动作。

### 3号驱动重启后旧 zero_offset 会把小角度放大

现象：

- node3 恢复在线后，formal `+5°` 触发了完整 CANSimple position path。
- `Set_Limits` 已发非零限流 `5.0f`。
- 但 `0x069` 从 `0 rev` 到约 `5.594 rev`，折算输出约 `41.96°`。

判断：

- 3号驱动/编码器重启后 `0x069 position_rev` 回到了 `0`。
- M33 仍保留旧临时零点 `55.1 rad`，导致 formal `+5°` 叠加旧零点后目标约 `9.436 rev`。
- 这不是 48:1 换算错，而是 bench zero offset 已经过期。

修正：

- M33 commit `abedf348` 将当前未装机台架 3号零点改为 `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(0.0f)`。

技巧：

- 伺泰威驱动每次重启/重新归零后，都要重新确认 `0x069 position_rev`，不能沿用上一次的 M33 零点。
- 大角度前必须先用 formal `+5°` 验证零点和方向。
- 这只是台架排故办法；正式机械臂必须做持久化机械零点或上电 homing。
- 旧版 `m33_joint_calib` 曾打印固件侧零点来源；当前路线已取消这类 M33 零点标注，不再把它作为正式依据。

### App、平台、M33、M55 不要各写一套患者参数

现象：

- 医疗康复机械臂需要按不同患者设置 ROM、限速、辅助等级、疼痛/疲劳策略和训练模式。
- 如果 App、平台、NanoPi、M33 和 M55 各自维护参数，现场会出现版本不一致和安全责任不清。

判断：

- 必须使用同一份 versioned Patient Device Profile。
- M33 只接收安全子集，M55 只接收模型子集，平台/App 负责编辑同一份源 profile。
- 第一版不要引入患者相对坐标系；先用机器人坐标系加 patient ROM limit 和 `rom_percent` 训练特征。

技巧：

- 同一设备同一时间只允许一个 active profile。
- 每条训练数据都记录 `profile_id/profile_version/session_id/machine_calibration_id/model_version`。
- VLA 和 M55 都只能输出建议或任务计划，不能直接写底层电机命令。

### M33 不做零点标注源

现象：

- 调试 3号/7号时曾经把临时零点写进 M33，导致驱动重启、台架姿态变化或上位机标注思路变化后，M33 固件里的零点和实际电机绝对角度容易不一致。

判断：

- 如果电机官方协议已经提供可信输出侧绝对角度，M33 不应该再维护一套零点标注。
- 零点、患者 ROM、训练模式、患者限速和标注元数据应该由上位机/平台/App 的统一 Patient Device Profile 管理。
- M33 只接收安全子集，做限位、限速、限流、急停、故障和通信超时裁决。

技巧：

- 不要在正式 M33 协议里新增 `session_zero`、`zero_source` 这类第二套零点语义。
- NanoPi 的 `m33 zero` 不作为正式接口使用；如需台架排故，另建显式 debug 工具，且不得进入正式 bringup。

状态：

- 已撤掉本轮新增的 M33 session zero 入口，并去掉 M33 诊断里的 `zero_source/zero_policy` 输出。

### App 和平台双控制不是双安全裁决

现象：

- 项目需要 App 蓝牙近端控制，也需要平台/服务器远端监控、数据采集、标注和后续总控台。

判断：

- App 和平台都只能提出控制请求或参数草案，不能各自持有一套独立安全权威。
- M33 必须是最终安全裁决方；任何远端延迟、断网、平台状态通过，都不能替代本地急停、限位、限速、限流和故障保护。

技巧：

- App BLE 优先做近端 start/pause/stop/estop request、模式切换和患者反馈。
- 平台优先做 profile draft/review、训练计划、数据/标注/模型管理和远程 stop/pause request。
- 冲突时取更保守状态；只有 M33 回报 `motion_allowed=true`，界面才能显示真实执行中。

### 电机遥测不能提升运动许可

现象：

- `0x330~0x337` 能生成 `/rehab_arm/motor_state` 和 `/joint_states`，平台/仿真/RViz 可以看到机械臂姿态。

判断：

- 遥测新鲜、姿态正常、温度正常，只说明“能看到状态”，不说明“可以动”。
- NanoPi、App、平台、VLA 都必须以 M33 `0x322 motion_allowed=true` 作为运动候选许可；legacy `state=ok` 和 motor telemetry 都不能替代它。

技巧：

- 离线先跑 `test_m33_ros_contract.py`，确认 limited/logging-only + 合法遥测仍然 `motion_candidate_allowed=false`。
- 真机联调时先看 `/rehab_arm/safety_state.motion_allowed`，再看 `/joint_states` 是否新鲜。
- 从 candump 离线验收时，也必须先看 `safety_state_count` 和 `motion_allowed_counts`；只有 `motor_state_count/joint_state_count` 不足以证明系统可以进入运动测试。
- 如果只读 heartbeat 抓包已经出现 `motion_allowed=true`，把它当作“开发台架 armed 状态”处理，不要因为没有发运动命令就忽略这个安全状态；下一步应先区分 bench mode 和正式 clinical mode。
- `bench_armed` 必须和正式 `armed/active` 分开。台架能动不等于可穿戴；NanoPi parser 默认应让 `bench_armed` 的 `motion_allowed=false`。
- NanoPi 上 `ros2 run` 的可执行名要以 `ros2 pkg executables rehab_arm_psoc_bridge` 为准；当前现场工作区使用 `psoc_can_bridge_node.py`，不是无后缀的 `psoc_can_bridge_node`。
- formal clinical 开关默认关闭是安全设计，不是功能缺失。只有 pre-arm ready 才能上报正式 `armed`；如果返回 `prearm_not_ready`，应补安全输入和参数，不要在 NanoPi 侧绕过。

### 离线数据工具测试要在临时目录释放前读取输出

现象：

- `test_build_replay_plan_cli_writes_filtered_plan` 第一次失败，错误为 `FileNotFoundError`，路径位于系统临时目录。

判断：

- CLI 已经写出文件，但测试在 `TemporaryDirectory()` 上下文退出后才读取，临时目录已被清理。

技巧：

- 测试离线导出工具时，要在 `with tempfile.TemporaryDirectory()` 作用域内读取输出文件。
- 这类错误不代表 JSONL/replay 功能失败，先检查测试生命周期。

### 上电只读数据采集不要强制要求 C8T6

现象：

- NanoPi 上电后，`can0`、M33 heartbeat、`0x332` 电机聚合状态、`/joint_states`、`/rehab_arm/motor_state` 都正常。
- 但 `check_recording.py` 默认要求 `/rehab_arm/sensor_state`，在 C8T6 未连接或未发 `0x7C2/0x7C3` 时误判整份记录失败。

判断：

- 上电只读检查的目标是验证 NanoPi、CAN、M33、ROS 状态桥和基础数据记录，不等价于完整硬件遥测验收。
- C8T6/传感器联调应作为下一层检查，不能阻塞基础电机/M33 状态链路确认。

修正：

- 新增 `poweron_readonly` topic profile，只要求 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/motor_state`。
- 完整硬件遥测仍使用 `hardware_telemetry`，继续要求 `/rehab_arm/sensor_state`。

技巧：

- 每次真实采集使用新的 `session_id`； recorder 以追加方式写文件，重复 session 会把多次记录混在一起。
- `bench_armed` 仍按 `motion_allowed=false` 处理；只读采集通过不代表可以运动。

状态：

- NanoPi 真实日志 `/home/pi/rehab_arm_logs/poweron-readonly-20260527-1923.jsonl` 已用 `poweron_readonly` 验证通过。

### NanoPi ROS Jazzy 环境缺 `ament_package`

现象：

- 在 NanoPi 上执行 `colcon build --packages-select rehab_arm_psoc_bridge` 失败。
- 报错包含 `ModuleNotFoundError: No module named 'ament_package'`，CMake 路径来自 `/opt/ros/jazzy`。

判断：

- 这是 NanoPi ROS/Python 构建环境问题，不是 CAN、M33 或 bridge 业务代码失败。
- 当前 `ros2 run` 仍可使用已有 install；纯 Python 文件可临时同步到 install 目录验证逻辑，但这不是长期方案。

技巧：

- 先确认 `/opt/ros/jazzy/setup.bash`、`python3 -V`、`python3 -c "import ament_package"`。
- 如果 `ament_package` 存在于 `/opt/ros/jazzy/lib/python3.12/site-packages`，但构建时仍找不到，先把这个路径补进 `PYTHONPATH`。
- `rehab_arm_ros2_ws/build_ros2.sh` 已加入自动补路径逻辑，优先用该脚本构建，不要长期依赖手动复制 install 文件。

状态：

- NanoPi 已验证 `./build_ros2.sh --packages-select rehab_arm_psoc_bridge` 可正常完成。
- `nanopi_live_telemetry_check.sh` 也已加入同样逻辑，现场只读验收脚本可直接使用。

### Windows here-string 远程执行会给参数带入 `\r`

现象：

- 通过 PowerShell here-string 管道到 `ssh ... bash -s` 时，`ros2 run ... --topic-profile poweron_readonly` 报 `invalid choice: 'poweron_readonly\r'`。

判断：

- 这是 Windows CRLF 进入远端命令参数造成的，不是 ROS 参数解析或 profile 名称错误。

技巧：

- 远端多行脚本适合做构建、复制、较长流程；但带枚举参数的最后验收命令，优先用单行 SSH 或在远端脚本内清理 CRLF。
- 如果看到候选值里明明有同名选项，却提示 `invalid choice`，优先检查参数末尾是否有隐藏 `\r`。

### PowerShell 中 `ssh -o` 可能被误解析

现象：

- 在 PowerShell 里直接运行复杂 `ssh -o BatchMode=yes ...` 命令时，报错类似：
  `A value that is not valid (BatchMode=yes) was specified for the outputFormat parameter.`

判断：

- PowerShell 把 `-o` 当成自己的参数解析了，命令没有真正发到 NanoPi。

技巧：

- 简单远程命令可以用 `ssh.exe --% -o BatchMode=yes ...`。
- 复杂多行远程命令优先用 PowerShell here-string 管道到 `ssh.exe --% ... bash -s`。
- 如果命令里包含枚举参数，注意上一条 CRLF 问题，必要时用单行 SSH 重跑最后的验证命令。
