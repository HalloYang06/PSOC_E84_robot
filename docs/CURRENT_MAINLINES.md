# 当前主线清单

本文档只回答一件事：现在项目到底有哪些主线，分别负责什么，哪些只是历史支线、shadow 或 bench/debug。给后续 AI 接手的 GitHub 路径总览见 [AI_PROJECT_STRUCTURE_GITHUB.md](AI_PROJECT_STRUCTURE_GITHUB.md)。

## 1. 总览

当前必须持续追踪的主线有 7 条：

| 主线 | 位置 | 作用 | 备注 |
|---|---|---|---|
| M33 安全控制主线 | `D:/RT-ThreadStudio/workspace/yiliao_m33` / `origin/M33` | 最终安全责任、CAN 主站、电机控制、状态汇总 | 真机运动最终裁决点 |
| M55 语音/小模型主线 | `D:/RT-ThreadStudio/workspace/wifi` / `origin/M55` | 语音、音频、板端模型结果、M33/M55 IPC | 只输出建议，不直控电机 |
| NanoPi ROS2 主线 | `D:/RT-ThreadStudio/workspace/_nanopi_rosnode_usbcan` | ROS2 bridge、状态汇总、仿真/平台网关 | 当前整合工作区 |
| Linux 仿真主机主线 | `cal@192.168.3.34` / `rehab-arm-sim-host-shadow.service` | MuJoCo hardware shadow、dry-run、6DOF 可视化 | 不承担真机安全闭环 |
| C8T6 传感节点主线 | `origin/C8T6` / 独立 STM32 工程 | EMG/IMU/心率/健康类传感 | 目前未确认总线在线 |
| APP 主线 | `origin/APP` | Android App、BLE 近端交互、高层显示 | 不能成为直控旁路 |
| 平台 / 总控台主线 | 平台仓库 | 任务编排、数据资产、模型、实验追踪 | 只做高层任务和管理 |

主线开发教程见 [MAINLINE_DEVELOPMENT_GUIDE.md](MAINLINE_DEVELOPMENT_GUIDE.md)。临时工程零点表见
`rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_temporary_calibration.yaml`。

## 2. 主线边界

- 正式运动必须走 `JointTrajectory -> NanoPi -> M33 -> 电机`。
- 安全执行层统一收敛到英飞凌 M33；NanoPi、Linux 仿真主机、App、平台和 M55 只做规划、请求、展示、数据、建议和转发。
- M55 只能给语义、语音、模型建议和上下文，不能直接发电机命令。
- Linux 仿真主机只做 `shadow-sim` 和 `dry-run`，不能替代真机安全链路。
- C8T6 是传感节点，不是控制主站。
- APP 和平台只能做高层交互、审核、数据和任务管理，不能绕过 NanoPi/M33。

当前工程阶段允许把“上电当前位置”作为临时工程零点，用于 MuJoCo/dry-run 和小幅相对轨迹开发；这不是临床零点，也不是绕过 M33 的运动许可。

## 3. 支线分类

下面这些入口必须明确标成历史支线、bench 或 shadow，不可混入正式主线：

- `7号 EL05`
- `nanopi_can_master.py`
- `private/cansimple/m33 target`
- `ROS_VLA_WebSocket`
- 旧 wake/demo/fallback 启动脚本

分类原则：

- `mainline`：可能影响真机运动，最终必须回到 M33 安全裁决。
- `shadow-sim`：只做 MuJoCo、可视化、dry-run。
- `dry-run`：只生成候选，不发底层控制。
- `bench-debug`：隔离台架诊断，不进正式流程。
- `offline-demo`：历史演示或合成数据。
- `side-channel`：语音、App、平台、状态汇总等辅助链路。

## 4. 现状记号

- `feature/rehab-arm-ros2-architecture` 是当前综合主线工作区。
- `origin/M33`、`origin/M55`、`origin/C8T6`、`origin/APP`、`nanopi-sdk`、`nanopi-rosnode-usbcan` 都各有职责，不能混成一条线。
- 当前已确认过的历史里程碑包括：M33/M33+NanoPi 主线、MuJoCo 6DOF shadow、以及曾经恢复过的全关节 `/joint_states`。
- 当前代码审计结论：M33 串口 console/FINSH 仍开；4/5/6/7 active-report 不是开机自动打开，必须通过明确遥测命令短时打开并收尾关闭。

## 5. 维护规则

以后新增任何功能或文档，先写清楚它属于哪条线：

```text
mainline / shadow-sim / dry-run / bench-debug / offline-demo / side-channel
```

如果分类不清，默认按 `shadow-sim` 或只读处理，不准直接往真机运动链路里塞。
