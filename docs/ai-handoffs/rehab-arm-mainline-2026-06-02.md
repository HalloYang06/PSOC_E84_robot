# 康复外骨骼机械臂主线交接文档

身份：Codex，机械臂主线协作 AI。本文给后续接手的 AI 使用，目标是不用翻聊天记录也能继续推进。

日期：2026-06-02

## 1. 先读哪些文档

优先按这个顺序读：

1. `README.md`：项目当前入口。
2. `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`：总架构和安全边界。
3. `docs/PROJECT_PROGRESS.md`：已完成、已验证和下一步。
4. `docs/TROUBLESHOOTING_AND_LESSONS.md`：踩坑记录，尤其是 CAN、电机、M33、NanoPi。
5. `docs/MOTOR_PROTOCOLS.md`：电机协议和 ID 事实源。
6. `docs/PSOC_CAN_PROTOCOL_V1.md`：NanoPi 和 M33/PSoC 的 CAN 协议。
7. `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`：患者、训练计划、限位、限速、App/平台共用参数语义。
8. `docs/REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md`：仿真主机、ROS2、MuJoCo 路线。
9. `docs/SIM_HOST_NANOPI_NETWORK_GUIDE.md`：仿真主机和 NanoPi 通讯。
10. `docs/SERVER_SYNC_API_DRAFT.md`：平台/服务器预留对接草案。

## 2. 当前仓库和工作区

主线文档仓库：

- `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan`
- 当前主线文档、NanoPi 工具和 ROS2 框架说明都在这里。

M33 固件仓库：

- `D:\RT-ThreadStudio\workspace\yiliao_m33`
- 当前有传感器拆分、控制层注释、安全状态机、电机映射等工作。
- 后续如果接 M33 代码，请先看 `D:\RT-ThreadStudio\workspace\yiliao_m33\docs\ai-handoffs\` 里的专项交接。

ROS2 工作区：

- `D:\RT-ThreadStudio\workspace\rehab_arm_ros2_ws`
- 目标是正规机器人开发框架：URDF/MuJoCo、`/joint_states`、`/arm_controller/joint_trajectory`、仿真和真机统一接口。

旧调试 ROS/CAN 工作区：

- `D:\RT-ThreadStudio\workspace\nanopi_can_ros_ws`
- 只作为 debug tools，不能进入正式真机 bringup 主路径。

平台仓库：

- `D:\ai合作产品`
- 这是另一条主线。本机械臂仓库只维护接口和需求，不要把平台源码搬进机械臂仓库。

## 3. 最高优先级原则

这是穿在人身上的康复外骨骼设备。默认安全态是不动。

必须保持这些边界：

- M33 是最终安全责任方。
- NanoPi、仿真主机、平台、App、VLA、M55 都不能绕过 M33 直接控制电机。
- 正式运动链路是 `JointTrajectory -> NanoPi ROS2 -> M33/PSoC -> 电机`。
- NanoPi 直接发 CANSimple/private 电机帧只允许台架调试，不进入正式 launch。
- VLA 只输出高层任务目标，不输出 CAN、电流、力矩、速度或底层位置帧。
- App 通过 BLE 连接 M33，做近场训练、患者参数、安全状态和急停交互。
- 平台/服务器做远程工程调试、数据采集、标注、模型和多设备管理，不做硬实时控制闭环。

## 4. 当前确认的架构

分层：

```text
平台/服务器/VLA
  -> 仿真主机 ROS2 + MuJoCo + 数据标注
  -> NanoPi ROS2 主控/桥接/摄像头/上传
  -> M33 安全状态机/电机控制/App BLE
  -> M55 小模型/语音/意图和疲劳等推理
  -> C8T6 传感节点
  -> 电机和驱动
```

机器人正规开发路线：

1. 先统一 URDF/MuJoCo 模型和 joint 名称。
2. 先打通 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state`。
3. 采集 JSONL/rosbag，保证数据可复现。
4. 在仿真主机验证轨迹、限位、速度和安全策略。
5. 再走 NanoPi -> M33 -> 电机的正式安全链路。
6. 平台和 App 只写入经过确认的 profile/计划/参数，并且 M33 最终裁决。

## 5. 当前电机和 CAN 事实

不要按旧规划 ID 做开发。当前真实基准如下：

| 对象 | 当前事实 |
| --- | --- |
| 3 号 | 伺泰威，CANSimple/ODrive-like，用户确认减速比为 48 |
| 4 号、5 号 | 灵足 RS00，私有扩展帧 MIT 类协议 |
| 6 号、7 号 | 灵足 EL05，私有扩展帧 MIT 类协议 |
| `0x320` | NanoPi -> M33，关节目标/轨迹片段命令 |
| `0x321` | NanoPi -> M33 heartbeat |
| `0x322` | M33 -> NanoPi 安全/状态回复 |
| `0x330~0x334` | M33 -> NanoPi 5 个 ROS joint 的电机遥测槽位 |
| `0x7C2` | C8T6 -> M33 传感数据 |
| `0x7C3` | C8T6 -> M33 健康状态 |

当前已验证过的关键点：

- `0x330..0x334` 映射到 motor id `3/4/5/6/7`。
- stale/no-feedback 帧不能生成 `/joint_states`，避免假 0 位姿污染仿真。
- `bench_armed` 不能被 NanoPi/平台/App 当成正式人体穿戴运动许可。
- 7 号电机能被直接调试链路驱动，但正式 M33 路径必须继续受安全状态机约束。

## 6. 当前平台对接边界

平台侧文档已补充：

- `D:\ai合作产品\docs\platform-agent-operating-architecture.md`
- 重点看 `4.8.1 机器人开发平台主线`、`4.8.2 平台和机械臂对接协议`、`4.8.3 给其他工作空间 AI 的提示词`。

机械臂侧要遵守：

- NanoPi runner 或轻量数据代理向平台上报只读状态、采集片段和回执。
- 平台优先采集 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`、相机 topic、诊断 topic。
- 平台命令默认只能扫描、只读采集、状态同步、仿真运行、生成审核建议。
- 真实运动必须由人工审核后进入 NanoPi ROS/M33 安全链路。
- 平台不能直接发 CAN 电机帧。

建议的 `robot_state` 字段：

```json
{
  "kind": "robot_state",
  "schema_version": 1,
  "device_id": "rehab-arm-001",
  "source": "nanopi",
  "mode": "idle|sim|real|fault|estop",
  "safety": {
    "state": "ok|limited|emergency_stop|fault|unknown",
    "authority": "m33",
    "message": ""
  },
  "joints": [],
  "sensors": {},
  "camera": {}
}
```

## 7. 当前 App 对接边界

App 是 BLE 接 M33，不是 HTTP 接 NanoPi 的实时控制入口。

App 可做：

- 患者档案。
- 患者 ROM/限位/限速/助力等级/训练计划。
- 主动、被动、记忆等训练模式选择。
- 急停、暂停、继续、停止请求。
- 安全状态、电机状态、传感器摘要、小模型结果显示。

App 不可做：

- 直接发 CAN。
- 绕过 M33 写电机底层控制。
- 自动解除急停。
- 不经确认覆盖平台或 M33 的安全参数。

平台和 App 后续要用同一套 patient/device profile 语义。具体看 `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`。

## 8. 近期最小可执行路线

下一位 AI 不要一上来铺大功能。按这个顺序走：

1. 先把 M33 当前控制层整理任务收尾：
   - `control_layer.c` 已经拆出 `sensor.c/sensor.h`。
   - 用户要求每个函数都要有中文注释。
   - 不改变原功能。
   - 完成后做语法/结构检查，记录到 M33 专项 handoff。

2. 再做 NanoPi/ROS 只读状态闭环：
   - 上电时确认 `can0` 为 `ERROR-ACTIVE`。
   - 不发运动命令，抓 `0x322` 和 `0x330~0x334`。
   - 确认 `/rehab_arm/motor_state` 有 5 个槽位。
   - 确认 stale 状态不发 `/joint_states`。

3. 再做仿真主机接入：
   - 仿真主机和 NanoPi 在同一网络时走 ROS2 DDS 或明确配置的 ROS_DOMAIN_ID。
   - 先同步 `/joint_states`、`/rehab_arm/safety_state`。
   - 再运行 MuJoCo/RViz。

4. 再做平台只读采集：
   - NanoPi 采集 `robot_state`。
   - 平台按钮启动/停止同步，不默认常开。
   - 生成 `manifest.json`、`preview.jsonl`、checksum 和 Artifact。

5. 最后才做小幅真机运动：
   - 先仿真。
   - 再空载台架。
   - 只测 3 号和 7 号或用户明确允许的电机。
   - M33 安全状态必须明确，不能在 `prearm_not_ready`、`limited`、`fault`、`emergency_stop` 时运动。

## 9. 后续 AI 开工提示词

给接手机械臂主线的 AI：

```text
你接手的是康复外骨骼机械臂主线，不是单个电机测试。先阅读 docs/ai-handoffs/rehab-arm-mainline-2026-06-02.md、docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md、docs/PROJECT_PROGRESS.md、docs/TROUBLESHOOTING_AND_LESSONS.md、docs/MOTOR_PROTOCOLS.md。

最高原则：这是穿戴在人身上的设备，默认安全态是不动。M33 是最终安全责任方。正式运动链路是 JointTrajectory -> NanoPi ROS2 -> M33/PSoC -> 电机。NanoPi 直发 CAN 只用于台架调试，不进入正式 bringup。VLA、平台、App 都不能直接发底层电机命令。

当前优先级：
1. 收尾 M33 控制层整理和中文函数注释，不改变行为。
2. 做 NanoPi/ROS 只读状态闭环，确认 safety_state、motor_state、joint_states 的数据门。
3. 接仿真主机，只先做 /joint_states 和 safety_state 同步。
4. 接平台只读数据采集和 robot_state，不做真实运动控制。
5. 真机运动必须先仿真、再空载、再低能量台架，并由用户明确授权。

每完成一个小任务，更新 docs/PROJECT_PROGRESS.md；如果遇到坑，更新 docs/TROUBLESHOOTING_AND_LESSONS.md；如果跨 AI 协作，更新 docs/ai-handoffs。
```

给接手 M33 固件的 AI：

```text
你只负责 D:\RT-ThreadStudio\workspace\yiliao_m33。先看该仓库 docs/ai-handoffs 和 applications/control/control_layer.c、sensor.c、control_layer.h、sensor.h。当前任务是整理控制层，把传感器相关代码拆分清楚，并确保每个函数都有具体中文注释，不改变原功能。安全状态机、限位、限速、限流、急停和 heartbeat timeout 是核心，不要为了测试绕开。

完成后至少做：
- git diff --check
- control_layer.c/sensor.c 括号平衡检查
- 能用本机工具链则编译；不能编译要明确说明原因
- 更新 M33 专项 handoff
```

给接手平台侧 AI：

```text
平台仓库在 D:\ai合作产品。先读 docs/platform-agent-operating-architecture.md 的 4.8.1、4.8.2、4.8.3。平台只做通用机器人开发工作台、只读采集、状态可视化、标注、图表实验、证据链和审核，不直接控制电机。先做 robotics.robot_state.subscribe 和设备窗口里的状态/相机/关节温度显示，必须保留 NPC 工作台结构。
```

给接手 App 的 AI：

```text
App 通过 BLE 接 M33，负责近场患者参数、训练计划、安全状态、急停和训练交互。不要通过 App 直接发 CAN 或绕过 M33。参数语义必须和 docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md 对齐。
```

## 10. 验证和未验证

本交接文档本身只做文档整理，没有执行硬件测试、ROS 测试或固件编译。

当前必须继续验证的事项：

- M33 控制层拆分后的完整编译。
- M33 每个函数中文注释收尾。
- NanoPi 真 CAN 只读状态链路。
- 3 号伺泰威正式路径动作。
- 7 号灵足正式 M33 安全路径动作和角度映射。
- 仿真主机和 NanoPi 的 ROS2 网络通信。
- 平台只读采集和 `robot_state` 实际接入。

## 11. 工作区注意事项

- 不要随便 revert 用户或其他 AI 的未提交改动。
- 主线仓库当前可能有与本交接无关的 dirty 文件，先 `git status --short` 看清楚。
- M33 编译常见问题是本机 PATH 找不到 `arm-none-eabi-gcc` 或 SCons/RT-Thread Studio 工具链不在当前 shell。
- 上电真机测试前必须问清楚用户是否在现场、是否有人穿戴、哪些电机上电、哪些电机允许动。
- 没有用户明确授权时，只做只读抓包、heartbeat、状态采集和离线仿真。
