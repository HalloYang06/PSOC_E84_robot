# AI 接手项目结构总览

本文给后续 AI 或协作者快速接手机械臂项目使用。所有路径都使用 GitHub 分支和仓库内路径，不使用本地电脑路径。

## 1. 仓库

GitHub 仓库：

```text
https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator
```

当前综合主线分支：

```text
feature/rehab-arm-ros2-architecture
```

代码不是单一目录承载全部功能，而是同一个 GitHub 仓库按分支拆分子系统。

## 2. 分支结构

| 分支 | 职责 | 接手时先看 |
|---|---|---|
| `feature/rehab-arm-ros2-architecture` | ROS2、NanoPi bridge、MuJoCo、主线文档、协议、dry-run、profile | `README.md`、`docs/AI_PROJECT_STRUCTURE_GITHUB.md`、`docs/CURRENT_MAINLINES.md` |
| `M33` | Infineon M33 固件、CAN 主站、安全状态机、电机控制、M33/M55 IPC、BLE 近端入口 | M33 control/safety/CAN/M55 bridge 相关源码和 README |
| `M55` | Infineon M55 WiFi、语音、音频、小模型、M33/M55 结果桥 | M55 model/voice/audio/WiFi 相关源码和 README |
| `C8T6` | STM32F103C8T6 传感节点、CAN transport、传感采集 | CAN 协议、传感 app service、HAL/Keil 工程 |
| `APP` | Android App、BLE 交互、3D 手臂界面、用户端状态显示 | Android app、BLE protocol、UI |
| `nanopi-sdk` | NanoPi 底层 CAN bring-up 和系统脚本参考 | SocketCAN、MCP2518FD、系统服务脚本 |
| `nanopi-rosnode-usbcan` / `NanoPi_ROSNode` | 早期 NanoPi/ROS 旁线 | 只作历史参考 |
| `ROS_VLA_WebSocket` | 早期 ROS/VLA/WebSocket 方向 | 只作历史参考 |
| `PCB` | PCB/硬件资料 | 硬件参考 |
| `ai` | 平台/AI 早期资料 | 只作平台方向参考 |
| `wake-word-model` | 唤醒词模型资料 | 只作 M55 语音参考 |
| `main` | 入口/早期资料 | 不作为当前开发主线 |

## 3. 当前唯一真机运动主线

真实运动只能走：

```text
JointTrajectory -> NanoPi ROS2 bridge -> M33 safety/control -> motor
```

禁止新增这些旁路：

- 服务器或 VLA 直接发 CAN。
- App HTTP 直接控制电机。
- M55 小模型直接控制电机。
- Linux 仿真主机绕过 NanoPi/M33 控制电机。
- NanoPi 调试脚本进入穿戴正式流程。

安全执行层统一在 M33。其他层只做规划、请求、dry-run、展示、数据、建议或转发。

## 4. `feature/rehab-arm-ros2-architecture` 结构

### 4.1 文档入口

| 路径 | 作用 |
|---|---|
| `README.md` | 当前仓库入口和安全边界 |
| `docs/AI_PROJECT_STRUCTURE_GITHUB.md` | 本文，给 AI 接手用 |
| `docs/CURRENT_PROJECT_BRIEFING.md` | 项目讲解稿，适合先读 |
| `docs/CURRENT_MAINLINES.md` | 当前主线/旁线分类 |
| `docs/MAINLINE_DEVELOPMENT_GUIDE.md` | 后续怎么开发、怎么补主线 |
| `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md` | 总体架构基准 |
| `docs/USER_MANUAL.md` | 使用、验证和命令手册 |
| `docs/PROJECT_PROGRESS.md` | 进度记录 |
| `docs/TROUBLESHOOTING_AND_LESSONS.md` | 排障和踩坑记录 |

### 4.2 ROS2 工作区

主工作区：

```text
rehab_arm_ros2_ws/
```

关键包：

| 路径 | 作用 |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_description/` | URDF、关节 schema、临时标定表 |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/` | MuJoCo 仿真、6DOF 模型、hardware shadow relay |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/` | NanoPi ROS2 bridge、PSoC/M33 CAN 解析、profile、dry-run gate |
| `rehab_arm_ros2_ws/src/rehab_arm_control/` | demo trajectory、VLA task planner placeholder、轨迹工具 |
| `rehab_arm_ros2_ws/src/rehab_arm_bringup/` | launch 和集成启动 |

### 4.3 机器人模型和标定

| 路径 | 作用 |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf` | 基础 URDF |
| `rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_schema.yaml` | 6DOF 关节、电机映射、限位草案 |
| `rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_temporary_calibration.yaml` | 当前姿态作为工程临时零点的可修改表 |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml` | MuJoCo 6DOF 模型 |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml` | 最小仿真模型 |

当前临时策略：

```text
上电当前位置 = engineering zero
```

这只用于 planner、MuJoCo dry-run 和小幅相对轨迹。它不是临床零点，不是真实机械零位，不是运动许可。

### 4.4 NanoPi / M33 bridge

| 路径 | 作用 |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py` | ROS JointTrajectory 到 M33 CAN bridge |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_status.py` | M33 `0x322` 状态解析 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_motor_status.py` | M33 `0x330~0x334` 电机状态解析 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_ros_contract.py` | M33/ROS 合同 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_model_status.py` | M55/M33 `0x323` 模型结果解析 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/motor_profiles.py` | 电机 profile 表 |

主要 ROS topic：

| Topic | 方向 | 说明 |
|---|---|---|
| `/joint_states` | NanoPi -> ROS | 当前 fresh 关节状态 |
| `/rehab_arm/motor_state` | NanoPi -> ROS | 电机状态 JSON |
| `/rehab_arm/safety_state` | NanoPi -> ROS | M33 safety/status JSON |
| `/rehab_arm/model_state` | NanoPi -> ROS | M55/M33 模型建议 JSON |
| `/arm_controller/joint_trajectory` | Planner -> NanoPi | 正式轨迹入口，必须再经 M33 |

### 4.5 MuJoCo / shadow / dry-run

| 路径 | 作用 |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py` | MuJoCo sim node |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_backend.py` | MuJoCo backend |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/medical_arm_shadow_relay_node.py` | `/joint_states` 到 `/sim/...` shadow relay |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_shadow.launch.py` | 纯 MuJoCo 6DOF launch |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py` | 硬件 shadow launch |

MuJoCo 话题：

| Topic | 说明 |
|---|---|
| `/sim/medical_arm/joint_trajectory` | MuJoCo shadow 输入 |
| `/sim/medical_arm/joint_states` | MuJoCo shadow 输出 |
| `/sim/medical_arm/safety_state` | 仿真 safety |
| `/sim/medical_arm/sensor_state` | 仿真 sensor |

调试时推荐用隔离 topic，例如：

```text
/codex_path_test/joint_trajectory
/codex_path_test/joint_states
```

避免误接真实 `/arm_controller/joint_trajectory`。

### 4.6 Planner / VLA / dry-run gate

| 路径 | 作用 |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_control/rehab_arm_control/trajectory_utils.py` | 轨迹工具和 demo 轨迹 |
| `rehab_arm_ros2_ws/src/rehab_arm_control/rehab_arm_control/vla_task_planner_node.py` | VLA task planner placeholder |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/vla_candidate_gate.py` | VLA candidate gate |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/mujoco_dry_run_review.py` | MuJoCo dry-run review plan |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/operator_review.py` | 人工/治疗师审核 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_gate_preparation.py` | M33 gate 准备包 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/server_action_ingress.py` | 服务器动作入口质量门 |

候选轨迹流程：

```text
server/VLA high-level request
-> vla_plan_candidate_v1
-> vla_candidate_gate
-> mujoco_dry_run_review
-> operator_review
-> m33_gate_preparation
-> /arm_controller/joint_trajectory
-> M33 final gate
```

前面的 gate 只是质量门和审核，不是运动许可。

### 4.7 Profile / 患者约束 / App/平台协议

| 路径 | 作用 |
|---|---|
| `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` | 患者/设备 profile 协议 |
| `docs/COMMAND_CENTER_APP_PROTOCOL_V1.md` | 总控台/App 协议 |
| `docs/M33_SAFETY_INPUT_MAPPING.md` | M33 安全输入映射 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/patient_profile.py` | profile 校验和 M33 safety subset |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/build_patient_profile_template.py` | profile 模板生成 |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/validate_patient_profile.py` | profile 校验 |

Profile 可以收集患者 ROM、速度限制、训练模式和安全子集。M33 仍是最终执行裁决点。

## 5. M33 分支结构说明

分支：

```text
M33
```

职责：

- CAN 主站。
- 电机控制。
- `0x320` 轨迹/目标接收。
- `0x321/0x322` heartbeat/status。
- `0x330~0x334` 电机状态聚合。
- `0x323` M55 模型结果转发。
- M33/M55 IPC。
- BLE 近端状态和请求。
- 限位、限速、限流、急停、fault、timeout。

后续 AI 切到 `M33` 分支后，应优先找：

```text
applications/
```

以及 control、CAN、M55 bridge、BLE、安全状态机相关文件。不要在 M33 里新增 VLA 或平台逻辑；M33 只接受审核后的安全子集和轨迹请求。

## 6. M55 分支结构说明

分支：

```text
M55
```

职责：

- 语音/音频采集。
- 小模型/TFLite Micro。
- EMG/疲劳/意图建议。
- M33/M55 IPC。
- WiFi/服务器 relay。
- 结果回 M33，再由 M33/NanoPi 发布。

M55 输出永远是建议，不是运动许可。不要让 M55 直接发电机控制。

## 7. C8T6 分支结构说明

分支：

```text
C8T6
```

职责：

- STM32F103C8T6 传感板。
- CAN control/ACK/sensor/health。
- EMG/IMU/心率等轻量传感。

当前协议边界：

| CAN ID | 方向 | 说明 |
|---|---|---|
| `0x7C0` | M33/NanoPi -> C8T6 | 控制 |
| `0x7C1` | C8T6 -> M33/NanoPi | ACK |
| `0x7C2` | C8T6 -> M33/NanoPi | sensor |
| `0x7C3` | C8T6 -> M33/NanoPi | health |

C8T6 是传感节点，不是控制主站。

## 8. APP 分支结构说明

分支：

```text
APP
```

职责：

- Android App。
- BLE 近端交互。
- 状态显示。
- 训练 start/pause/stop 请求。
- 3D 手臂界面。
- 标注、profile 确认、高层交互。

App 不能直接发 CAN，也不能绕过 M33。

## 9. 当前硬件/电机口径

当前机械臂主线：

| 电机/节点 | 当前角色 |
|---|---|
| `node_id=3` | CANSimple，当前主线电机 |
| `motor_id=4` | RS00，当前主线电机 |
| `motor_id=5` | RS00，当前主线电机 |
| `motor_id=6` | EL05，当前主线电机 |
| `motor_id=1/2` | 腕部 4015 候选，当前未上电/待补 |
| `motor_id=7` | 外部调试电机，不属于当前机械臂主线 |

当前 6DOF MuJoCo joints：

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

## 10. AI 接手顺序

后续 AI 接手时按这个顺序读：

1. `README.md`
2. `docs/AI_PROJECT_STRUCTURE_GITHUB.md`
3. `docs/CURRENT_MAINLINES.md`
4. `docs/MAINLINE_DEVELOPMENT_GUIDE.md`
5. `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`
6. `docs/PROJECT_PROGRESS.md`
7. `docs/TROUBLESHOOTING_AND_LESSONS.md`
8. 当前任务相关分支源码

做任何改动前先分类：

```text
mainline / shadow-sim / dry-run / bench-debug / offline-demo / side-channel
```

如果分类不清，默认只读或 shadow-sim。

## 11. 后续最重要的 TODO

1. 填完整 `medical_arm_6dof_temporary_calibration.yaml` 的 4/5/6 当前零点、方向和限位。
2. 接入 1/2 腕部电机，确认协议、ID、方向和限位。
3. 写 current-state-relative joint-space planner，先只输出 MuJoCo/dry-run candidate。
4. 修复/监督 Linux shadow service 中 `mujoco_sim_node.py` 退出后的重启问题。
5. 把正式 `/arm_controller/joint_trajectory` 小幅动作接回 NanoPi -> M33 -> 电机主线。
6. C8T6 稳定 ACK/传感链路，进入 M33/M55 sensor path。
7. App/平台只接 profile、状态、审核和高层任务，不接底层控制。

