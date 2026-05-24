# 康复外骨骼机械臂项目进度

本文档记录当前架构、实现进度、验证结果和下一步计划。每次完成一个任务后都要补充本文件，避免进度只留在聊天记录里。

## 当前基准

- 当前分支：`feature/rehab-arm-ros2-architecture`
- 主 README：[README.md](../README.md)
- 架构审查稿：[REHAB_ARM_SYSTEM_ARCHITECTURE.md](REHAB_ARM_SYSTEM_ARCHITECTURE.md)
- 使用手册：[USER_MANUAL.md](USER_MANUAL.md)
- 新手搭建教程草稿：[REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md](REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md)
- 踩坑与技巧记录：[TROUBLESHOOTING_AND_LESSONS.md](TROUBLESHOOTING_AND_LESSONS.md)
- 当前 ROS2 工作区：`rehab_arm_ros2_ws/`
- PSoC CAN 协议 V1：[PSOC_CAN_PROTOCOL_V1.md](PSOC_CAN_PROTOCOL_V1.md)
- M33 `0x320` 日志固件指南：[M33_0X320_LOGGER_GUIDE.md](M33_0X320_LOGGER_GUIDE.md)

## 架构状态

- 已明确 App 两条链路：
  - `App <-> BLE <-> 英飞凌 M33/M55`：近端训练控制、状态显示、标注、急停请求。
  - `App <-> HTTP <-> NanoPi/OpenClaw`：高层 AI、报告、训练建议和远程服务。
- 已明确总服务器/未来总控台：
  - 当前作为开发工具服务器。
  - 后续管理多设备、数据资产、模型版本、实验记录和远程协作。
  - 规划仓库：`https://github.com/wenjunyong666/ai-`，分支 `ai`。
- 已明确正式真机运动链路：
  - `JointTrajectory -> NanoPi -> M33 -> 电机`
  - M33 是正式电机控制主站和最终安全责任方。
- 已明确调试链路：
  - `nanopi_can_master.py` 可直接发 CANSimple 或私有扩展帧。
  - 调试直控协议不进入正式 ROS bringup。

## 当前 CAN/电机记录

只记录当前真实链路，不使用旧文档里的旧规划 ID。

| ID | 协议 | 当前状态 |
|---|---|---|
| `node_id=3` | CANSimple/ODrive 类标准帧协议 | heartbeat 为 `0x061`，机械关节绑定待确认 |
| `motor_id=4` | 私有扩展帧 MIT 电机协议 | 可作为调试 ID，机械关节绑定待确认 |
| `motor_id=5` | 私有扩展帧 MIT 电机协议 | 机械关节绑定待确认 |
| `motor_id=6` | 私有扩展帧 MIT 电机协议 | 机械关节绑定待确认 |
| `motor_id=7` | 私有扩展帧 MIT 电机协议 | 机械关节绑定待确认 |
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段命令 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | M33 状态回复 |
| `0x7C2` | C8T6 -> M33 | 传感数据 |
| `0x7C3` | C8T6 -> M33 | 健康状态 |

## 已完成

### 2026-05-24

- 新建分支 `feature/rehab-arm-ros2-architecture`。
- 新建 ROS2 工作区 `rehab_arm_ros2_ws/`。
- 初步创建以下包：
  - `rehab_arm_description`
  - `rehab_arm_sim_mujoco`
  - `rehab_arm_control`
  - `rehab_arm_psoc_bridge`
- 在 NanoPi 上验证：
  - `rehab_arm_description` 能构建。
  - `rehab_arm_sim_mujoco` 能构建。
- 修复 `rehab_arm_sim_mujoco` 脚本执行权限问题：
  - `ros2 pkg executables rehab_arm_sim_mujoco` 已能看到 `mujoco_sim_node.py`。
- 新增主架构文档：
  - `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`
- 替换仓库主 README：
  - `README.md` 已改为当前系统架构 README。
- 明确抛弃旧文档中的旧规划 CAN ID：
  - 当前主架构不再使用旧规划 ID。
- 新增本进度文档：
  - `docs/PROJECT_PROGRESS.md`
- 新增 Codex skill：
  - `rehab-arm-progress-keeper`
- 新增踩坑与技巧文档：
  - `docs/TROUBLESHOOTING_AND_LESSONS.md`
- 更新 `rehab-arm-progress-keeper` skill：
  - 后续任务结束前需要同时检查进度文档和踩坑文档。
- 新增使用手册：
  - `docs/USER_MANUAL.md`
- 新增 Codex closeout skill：
  - `rehab-arm-task-closeout`
  - 后续每个小任务完成后要更新进度、踩坑、使用手册，并提交推送到 GitHub 当前 feature 分支。
- GitHub 分支上传：
  - 已提交 `78cb2547 Add rehab arm ROS2 architecture baseline`。
  - 已推送到 `origin/feature/rehab-arm-ros2-architecture`。
  - GitHub PR 地址提示：`https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/pull/new/feature/rehab-arm-ros2-architecture`
- 完成 `rehab_arm_sim_mujoco` 第一轮 NanoPi 冒烟测试：
  - 同步 `mujoco_sim_node.py` 到 NanoPi。
  - 只重建 `rehab_arm_sim_mujoco`。
  - `ros2 pkg executables rehab_arm_sim_mujoco` 能看到 `mujoco_sim_node.py`。
  - `timeout 4 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py` 能干净结束，无 traceback。
  - 启动节点后能看到 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
  - `ros2 topic echo --once /joint_states` 能收到 5 个关节状态。
- 完成 `rehab_arm_control` 第一轮 NanoPi 集成测试：
  - 给 `demo_trajectory_node.py` 和 `vla_task_planner_node.py` 增加 ROS2 退出保护。
  - 设置两个 Python 节点为 executable。
  - 同步 `rehab_arm_control` 到 NanoPi。
  - 只重建 `rehab_arm_control`。
  - `ros2 pkg executables rehab_arm_control` 能看到 `demo_trajectory_node.py` 和 `vla_task_planner_node.py`。
  - 后台启动 `rehab_arm_sim_mujoco`，运行 `demo_trajectory_node.py` 发布 demo `JointTrajectory`。
  - `/joint_states` 位置从 0 变成非零，验证 demo 轨迹能驱动仿真状态变化。
- 完成 `rehab_arm_psoc_bridge` 第一轮 NanoPi 非运动测试：
  - 给 `psoc_can_bridge_node.py` 增加 ROS2 退出保护。
  - 设置 Python 节点为 executable。
  - 新增 `log_heartbeat` 参数，默认关闭，测试时可打印 heartbeat TX。
  - 同步 `rehab_arm_psoc_bridge` 到 NanoPi。
  - 只重建 `rehab_arm_psoc_bridge`。
  - `ros2 pkg executables rehab_arm_psoc_bridge` 能看到 `psoc_can_bridge_node.py`。
  - `can0` 为 `UP`、`ERROR-ACTIVE`、1Mbps。
  - 节点启动后能打印 `TX 321 01`，说明已尝试发 NanoPi heartbeat。
  - `timeout 4 ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p log_heartbeat:=true` 能干净结束。
  - 未验证通过 M33 回复：未看到 `0x322`，且 `can0` TX packets 未增加、TX dropped 增加，疑似当前 `0x321` 未被总线 ACK 或 M33 不在线/未应答。
- 完成 M33 heartbeat 回复链路排查与 bridge 诊断增强：
  - `can0` 当前为 `UP`、`ERROR-ACTIVE`、1Mbps。
  - 监听 `node_id=3` heartbeat 标准帧 `0x061`，4 秒内未看到帧。
  - 用 `/home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 7 --wait 1` 发送 `0x321`，未收到 `0x322`。
  - 发送后 `can0` TX packets 仍为 0，TX dropped/errors 增加，确认当前总线层 ACK/回复未通。
  - 给 `rehab_arm_psoc_bridge` 增加 `status_timeout_sec` 参数和 PSoC status timeout 诊断。
  - 验证 bridge 无轨迹运行时会发布 `/rehab_arm/safety_state`：
    - `{"state":"limited","detail":"no PSoC status after 4 heartbeats","source":"psoc_bridge"}`
- 现场确认 M33/PSoC heartbeat 无回复的硬件根因：
  - 现象是 NanoPi 能打印 `TX 321`，但未收到 `0x322`，并且 `can0` TX packets 不增长、TX dropped/errors 增加。
  - 用户现场确认原因是电池没电，导致目标控制板/总线节点未正常在线或无法 ACK。
  - 结论：这次不是 ROS2 bridge 代码问题，也不是 `0x321/0x322` 协议定义问题；先恢复供电再复测。
- 强化人身安全架构边界：
  - 在 `README.md`、`docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`、`docs/USER_MANUAL.md`、`docs/REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md` 中前置安全原则。
  - 明确康复外骨骼是穿戴在人身上的设备，安全优先级高于演示效果、控制精度、AI 能力和开发速度。
  - 明确默认不动、异常即停、M33 最终裁决、急停本地有效、仿真先行、人在设备内禁止调试直控。
- 电池恢复后完成 M33 heartbeat/status 链路复测：
  - `can0` 为 `UP`、`LOWER_UP`、`ERROR-ACTIVE`、1Mbps，错误计数器当前 `tx 0 rx 0`。
  - `/home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1` 成功发出 `STD 0x321 [1] 01`。
  - 收到 M33 回复 `STD 0x322 [8] A5 01 07 00 48 EA 6D 00`。
  - TX packets 从 0 增长到 1，确认总线层 ACK/发送成功。
  - `rehab_arm_psoc_bridge` 非运动测试成功发布 `/rehab_arm/safety_state`：
    - `{"state":"ok","source":"psoc","id_hex":"0x322","data":"A504070079F86E00","marker":165,"seq":4,"motors":7,"error_code":0}`
  - 本轮没有发布真实 `JointTrajectory`，没有做电机运动测试。
- 完成 `rehab_arm_psoc_bridge` 轨迹下发安全门控第一版：
  - 新增 `require_psoc_ok_for_trajectory`，默认 `true`，没有新鲜 M33 `0x322 ok` 时拒绝轨迹。
  - 新增 `reject_out_of_limit_trajectory`，默认 `true`，轨迹点超出软件关节限位时拒绝而不是静默夹紧。
  - 新增 `max_trajectory_points`，默认 `100`，避免一次塞入过长轨迹。
  - 启动时 safety state 从 `ok` 改为 `limited: bridge started, waiting for PSoC status`。
  - 发送轨迹点前会再次检查 M33 状态；若中途掉线或状态过期，会清空剩余轨迹并停止发送。
  - `0x322` 状态解析增加 marker `0xA5` 校验和过短帧 fault 处理。
  - `publish_safety()` 增加日志输出，便于远程测试时不用完全依赖 topic echo。
- 已验证：
  - 本地 `python -m py_compile rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py` 通过。
  - NanoPi `colcon build --symlink-install --packages-select rehab_arm_psoc_bridge` 通过。
  - 非运动门控测试通过：发布一条 `JointTrajectory`，在无新鲜 PSoC status 条件下日志输出 `rejected trajectory: no PSoC status received`。
  - 同时 `candump can0,320:7FF` 为空，确认门控拒绝时没有发送 `0x320` 轨迹帧。
- 未完成：
  - 准备做正常 PSoC `ok` 条件下的 bridge 非运动复测时，用户确认又没电了；因此未继续发 `0x320`，也未做任何电机运动测试。
- 电池再次恢复后完成 `rehab_arm_psoc_bridge` 门控复测：
  - `can0` 为 `UP`、`LOWER_UP`、`ERROR-ACTIVE`、1Mbps，错误计数器 `tx 0 rx 0`。
  - `/home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 2 --wait 1` 成功收到：
    - `RX STD 0x00000322 [8] A5 02 07 00 17 98 79 00`
  - 新 bridge 在正常 `status_timeout_sec=2.5` 下能收到 PSoC `ok`：
    - `{"state":"ok","source":"psoc","id_hex":"0x322","data":"A504070009F07900","marker":165,"seq":4,"motors":7,"error_code":0}`
  - PSoC 在线时发布超限轨迹 `shoulder_lift_joint=99.0 rad`，bridge 拒绝：
    - `trajectory point 0 joint shoulder_lift_joint 99.000 outside [-0.700, 1.400]`
  - 同时 `candump can0,320:7FF` 为空，确认超限拒绝时没有发送 `0x320`。
  - 本轮仍没有发布合法真实运动轨迹，没有做电机运动测试。
- 完成 `rehab_arm_psoc_bridge` 默认 dry-run 保护：
  - 新增 `enable_target_tx` 参数，默认 `false`。
  - 默认情况下，即使 M33 为 `ok` 且轨迹合法，bridge 也只打印 `DRY-RUN 320 ...`，不向 SocketCAN 发送 `0x320`。
  - 后续只有在 M33 日志固件已准备好、且需要对照 payload 时，才可显式设置 `enable_target_tx:=true`。
- 修正单关节轨迹会生成所有关节目标的问题：
  - `TrajectoryPointRuntime` 增加 `joint_names`。
  - bridge 现在只为当前 `JointTrajectory.joint_names` 中明确出现的关节生成目标帧。
- 已验证：
  - 本地 `python -m py_compile rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py` 通过。
  - NanoPi `colcon build --symlink-install --packages-select rehab_arm_psoc_bridge` 通过。
  - PSoC `ok` 条件下发布合法 `shoulder_lift_joint=0.1 rad` 轨迹，bridge 输出：
    - `DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000`
  - `candump can0,320:7FF` 为空，确认默认 dry-run 没有发送 `0x320`。
  - 日志只出现一个 shoulder 目标，没有再为其他未命令关节生成 dry-run 目标。
- 固化 PSoC CAN 协议 V1 和对照工具：
  - 新增 `docs/PSOC_CAN_PROTOCOL_V1.md`，记录 `0x320/0x321/0x322` 字段、单位、端序、关节编号和 M33 日志要求。
  - 新增 `rehab_arm_psoc_bridge/decode_psoc_cmd.py`，用于解码 `0x320` payload，不访问 CAN。
  - 新增 `rehab_arm_psoc_bridge/encode_psoc_cmd.py`，用于从关节名和目标角度生成 `0x320` payload，不访问 CAN。
  - `CMakeLists.txt` 安装 `encode_psoc_cmd.py` 和 `decode_psoc_cmd.py`，可通过 `ros2 run rehab_arm_psoc_bridge ...` 调用。
- 已验证：
  - 本地 `python -m py_compile rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/decode_psoc_cmd.py` 通过。
  - 本地 `python -m py_compile rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/encode_psoc_cmd.py` 通过。
  - 本地 `python .../encode_psoc_cmd.py shoulder_lift_joint 0.1` 输出 payload `0300390005000000`。
  - 本地超限输入 `shoulder_lift_joint 99.0` 会被拒绝，不输出 payload。
  - 本地 `python .../decode_psoc_cmd.py 0300390005000000` 输出 `joint_id=0`、`target_deg=5.7`、`target_rad=0.09948`、`rpm=5`、`torque_ma=0`。
  - NanoPi `colcon build --symlink-install --packages-select rehab_arm_psoc_bridge` 通过。
  - NanoPi `ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1` 输出 payload `0300390005000000`。
  - NanoPi `ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000` 输出同样字段。
- 准备 M33 `0x320` 日志固件参考：
  - 新增 `docs/M33_0X320_LOGGER_GUIDE.md`。
  - 文档定义 M33 收到 `0x320` 后当前阶段只解析、打印、记录安全裁决，不驱动电机。
  - 提供 C 参考解析函数：`read_i16_le()`、`decode_0x320()`、`validate_0x320()`、`handle_can_0x320()`。
  - 明确 M33 串口日志最少要打印 `RX 320`、`cmd/joint_id/deg_x10/target_deg/target_rad/rpm/torque_ma`、`decision/reason/safety_state`。
  - 明确进入真实 `0x320` 单帧对照前需要用户烧录 M33 日志固件；烧录前 NanoPi 保持 `enable_target_tx=false`。

## 进行中

- 下一步准备明确 `0x320` payload 与 M33 固件日志对照方法：
  - 协议 V1 已写入 `docs/PSOC_CAN_PROTOCOL_V1.md`。
  - M33 日志固件参考已写入 `docs/M33_0X320_LOGGER_GUIDE.md`。
  - 需要你确认或烧录 M33 侧日志/解析固件。
  - NanoPi 侧默认 dry-run，不发合法 `0x320` 运动目标，直到 M33 侧能明确打印收到的关节号、目标值、限幅结果和拒绝原因。

## 待确认

- `node_id=3` 对应哪个真实机械关节。
- `motor_id=4/5/6/7` 分别对应哪个真实机械关节。
- PSoC/M33 固件最终如何定义 `0x320` payload 字段。
- M33 和 M55 的实际通信方式：
  - shared memory
  - IPC
  - RT-Thread message queue
  - 其他方式
- 总服务器 `wenjunyong666/ai-` 的 `ai` 分支访问方式和 API 形态。

## 下一步

严格按“一次只做一个能测试的小目标”推进：

1. 明确 M33 固件当前是否已经解析 `0x320`，以及是否能打印关节号、角度、速度、扭矩/电流和安全裁决。
2. 如果需要烧录 M33 日志固件，由用户执行烧录。
3. NanoPi 只发送一条不接人、不带运动执行的受限 `0x320` 目标帧给 M33 日志观察。
4. 对照 ROS 输入、CAN payload 和 M33 日志一致后，再考虑下一步低能量台架测试。

## 更新规则

每次任务结束时至少补充：

- 完成了什么。
- 改了哪些关键文件。
- 验证了什么。
- 没验证或失败的地方。
- 下一步最小任务。
- 新踩的坑和可复用技巧要补到 `docs/TROUBLESHOOTING_AND_LESSONS.md`。
- 新增或变化的使用命令、测试流程、验收标准要补到 `docs/USER_MANUAL.md`。
- 每个小任务完成后提交并推送到 `origin/feature/rehab-arm-ros2-architecture`。
