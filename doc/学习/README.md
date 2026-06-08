# 学习

本目录用于沉淀康复机械臂项目相关学习笔记，面向后续接手者、实习生和调试人员。重点是把“为什么这样做”讲清楚，而不是只堆命令。

## 建议主题

- ROS2 `JointTrajectory`、`/joint_states` 和 rosbag2。
- NanoPi SocketCAN、systemd 只读服务和 ROS2 网络配置。
- M33 安全状态机、CAN 主站、`0x320/0x321/0x322/0x323/0x330~0x334`。
- M33/M55 IPC、共享内存、`MSG_TYPE_SENSOR_SNAPSHOT`、`MSG_TYPE_AI_INFERENCE_RESP`。
- M55 端侧 AI：`edge_ai_signal_window_t`、classifier adapter、TFLM/int8 模型部署。
- MuJoCo MJCF、URDF、hardware shadow 和 dry-run 的区别。
- 电机映射、传动比、零点、方向、软/硬限位和患者 ROM。
- 医疗康复外骨骼的安全边界和验证分级。

## 推荐文件格式

```text
YYYY-MM-DD-主题.md
```

建议结构：

```text
# 主题

## 一句话结论

## 背景

## 关键概念

## 项目中的具体位置

## 常见误区

## 下一步实践
```

## 当前必读

```text
agent.md
doc/项目概述.md
docs/ai-handoffs/current-system-handoff-2026-06-08.md
docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md
docs/M33_M55_MODEL_INPUT_PROTOCOL_V1.md
docs/M55_MODEL_RESULT_PROTOCOL_V1.md
```
