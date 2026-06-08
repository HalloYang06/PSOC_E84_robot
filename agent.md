# 康复机械臂 Agent 长期接管备忘

更新日期：2026-06-08

本文件是后续 AI、开发者和调试人员接手项目时优先阅读的长期备忘。它不是聊天记录替代品，而是把当前项目边界、工程位置、安全规则和 Git 管理习惯固化到仓库里，避免依赖旧电脑本地路径或口头交接。

## 1. 项目一句话

本项目是一套医疗康复外骨骼机械臂系统：M33 负责实时安全裁决和电机控制，M55 负责端侧 AI/信号推理，NanoPi 负责 ROS2、SocketCAN、状态聚合和网关，Linux 主机负责 MuJoCo shadow-sim、规划 dry-run 和研发验证，服务器/VLA/App 只能提供建议、状态、标注或候选任务。

正式运动唯一主线：

```text
JointTrajectory -> NanoPi -> M33 -> motor
```

M33 是最终安全裁决。任何 M55、App、服务器、VLA、MuJoCo 或调试脚本都不能绕过 M33 直接形成真实运动许可。

## 2. 当前工程位置

| 子系统 | 本机路径 | Git 分支/状态 | 用途 |
|---|---|---|---|
| ROS2 / NanoPi / MuJoCo / 文档主线 | `F:\rehab_arm_main` | `feature/rehab-arm-ros2-architecture`, 当前交接点 `d61703dc` | 系统架构、ROS2 工作区、MuJoCo、NanoPi 部署、总文档 |
| M33 固件 | `F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED` | `M33`, 当前交接点 `192ad049` | CAN 主站、BLE、M33/M55 IPC、模型结果桥、最终安全裁决 |
| M55 端侧 AI Git 工程 | `F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED` | `main` | `applications/edge_ai`、IMU/端侧 AI、共享内存 consumer、训练数据和文档 |
| M55 WiFi 本地工作副本 | `F:\RT-ThreadStudio\workspace\wifi` | 当前不是 Git 仓库 | 交接文档提到的 M55 WiFi/小模型工作副本；改动前必须先确认是否纳入 Git 或迁移 |

不要把旧电脑路径当作事实来源。跨机器接手时，优先从 GitHub 拉指定仓库和分支，再读交接文档。

GitHub 仓库：

```text
https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git
```

关键分支：

```text
feature/rehab-arm-ros2-architecture
M33
```

## 3. 首读文档

每次做真机、ROS2、M33、M55 或 MuJoCo 相关动作前，先读：

```text
docs/ai-handoffs/current-system-handoff-2026-06-08.md
doc/项目概述.md
```

主线仓库已有的关键文档：

```text
docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md
docs/M33_M55_MODEL_INPUT_PROTOCOL_V1.md
docs/M55_MODEL_RESULT_PROTOCOL_V1.md
docs/JOINT_MOTOR_MAPPING_DRAFT.md
docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md
```

M55 Git 工程关键文档：

```text
AGENTS.md
docs/edge-ai-architecture.md
docs/m33-producer-integration-guide.md
docs/m33-m55-bringup-log.md
docs/CHANGELOG.md
```

## 4. 真机安全规则

默认只读，不发 `0x320`。

任何真机相关动作前：

1. 读当前交接文档。
2. 先看 `git status`，不要提交无关本地文件。
3. NanoPi 产品服务默认只读：`enable_target_tx=false`。
4. MuJoCo 是 shadow-sim，不直接控制真机。
5. M55/App/服务器/VLA 只能给建议、状态、标注或 dry-run 候选，不能给真实运动许可。
6. 4/5/6 active-report 只能临时打开验证，验证后必须关闭。
7. 7 号 EL05 是外部台架调试电机，不是正式机械臂关节，不能作为 hardware shadow 默认映射。
8. 密码、token、密钥和个人凭据不要写进仓库。

最终安全检查常用只读命令：

```bash
ssh pi@192.168.2.66 "ip -details -statistics link show can0; systemctl is-active rehab-arm-nanopi-readonly.service"
ssh pi@192.168.2.66 "timeout 6 candump -L can0,321:7FF,322:7FF,323:7FF,330:7F8,320:7FF"
ssh pi@192.168.2.66 "source /opt/ros/jazzy/setup.bash; source ~/.rehab_arm_ros2_network; source ~/rehab_arm_ros2_ws/install/setup.bash; timeout 6 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState"
```

## 5. 设备

| 设备 | 地址 | 角色 |
|---|---|---|
| NanoPi | `pi@192.168.2.66` | SocketCAN、ROS2 bridge、M33 状态解析、相机/服务器网关 |
| Linux MuJoCo 仿真主机 | `cal@192.168.2.46` | MuJoCo 6DOF hardware shadow、无线 ROS2、dry-run |
| M33 | PSoC Edge E84 M33 | 最终安全裁决、CAN 主站、BLE、M55 数据桥 |
| M55 | PSoC Edge E84 M55 | 端侧 AI、EMG/语音/IMU 小模型推理、结果回传 M33 |

## 6. 当前电机映射

| 电机 | 当前关节 | MuJoCo medical joint | 注意 |
|---|---|---|---|
| 3 号 Sitaiwei CANSimple | `shoulder_lift_joint` | `jian_hengxiang_joint` | 用户确认同步轮电机端:输出轴端为 `1:2`，输出角约为电机角 `0.5` |
| 4 号 RS00 | `elbow_lift_joint` | `jian_zongxiang_joint` | 齿轮比未知 |
| 5 号 RS00 | `shoulder_abduction_joint` | `zhou_zongxiang_joint` | 方向、零点、输出比例待标定 |
| 6 号 EL05 | `upper_arm_rotation_joint` | `jian_xuanzhuan_joint` | 方向、零点待标定 |
| 1/2 号 4015 小电机 | 待确认 | `wanbu_zongxiang_joint` / `wanbu_hengxiang_joint` | 腕部两轴还没接线 |
| 7 号 EL05 | 无正式关节 | 无默认映射 | 外部台架调试电机，不在机械臂上 |

## 7. Git 管理规则

每次修改都要做 Git 管理：

1. 修改前先看对应仓库 `git status --short --branch`。
2. 只改当前任务相关文件，不回滚用户已有改动。
3. 修改后看 `git diff` 和 `git status`。
4. 文档/代码变更要提交到对应仓库；提交信息使用中文。
5. M55 工程的重要改动还要同步更新 `docs/CHANGELOG.md`。
6. 如果目标目录不是 Git 仓库，例如当前 `wifi`，不要直接承诺“已纳入版本管理”；先迁移到 Git 工程或初始化仓库。

## 8. 文档板块

主线仓库新增 `doc/` 作为随时查看的轻量项目台账：

```text
doc/项目概述.md
doc/调试问题分析总结/
doc/change_log/
doc/学习/
```

`docs/` 继续保留为既有详细工程文档目录；`doc/` 用于快速接手、日常记录和学习沉淀。
