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
