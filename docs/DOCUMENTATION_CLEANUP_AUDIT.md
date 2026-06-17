# 文档清理审计

本文用于整理 GitHub 仓库文档，避免后续 AI 被旧 demo、重复教程和历史旁线带偏。路径均为仓库内 GitHub 路径。

## 1. 必须保留的入口文档

这些是后续 AI 接手和当前主线开发必须先看的文档：

| 路径 | 原因 |
|---|---|
| `README.md` | 仓库入口 |
| `docs/AI_PROJECT_STRUCTURE_GITHUB.md` | GitHub 分支/路径总览，给 AI 接手用 |
| `docs/CURRENT_MAINLINES.md` | 当前主线和旁线分类 |
| `docs/MAINLINE_DEVELOPMENT_GUIDE.md` | 当前怎么继续开发 |
| `docs/CURRENT_PROJECT_BRIEFING.md` | 项目讲解稿 |
| `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md` | 架构基准 |
| `docs/USER_MANUAL.md` | 使用和验证手册 |
| `docs/PROJECT_PROGRESS.md` | 进度记录 |
| `docs/TROUBLESHOOTING_AND_LESSONS.md` | 排障和经验 |

## 2. 必须保留的协议/安全文档

| 路径 | 原因 |
|---|---|
| `docs/PSOC_CAN_PROTOCOL_V1.md` | PSoC/M33 CAN 协议 |
| `docs/MOTOR_PROTOCOLS.md` | 电机协议汇总 |
| `docs/M33_0X320_LOGGER_GUIDE.md` | `0x320`/M33 日志和调试 |
| `docs/M33_SAFETY_INPUT_MAPPING.md` | M33 安全输入 |
| `docs/M33_M55_IPC_BLE_FOUNDATION.md` | M33/M55 和 BLE 地基 |
| `docs/M33_M55_MODEL_INPUT_PROTOCOL_V1.md` | M33 -> M55 输入合同 |
| `docs/M55_MODEL_RESULT_PROTOCOL_V1.md` | M55 结果合同 |
| `docs/M55_MODEL_DEPLOYMENT_GUIDE.md` | M55 模型部署 |
| `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` | 患者/设备 profile |
| `docs/COMMAND_CENTER_APP_PROTOCOL_V1.md` | 总控台/App 协议 |
| `docs/SERVER_SYNC_API_DRAFT.md` | 服务器同步草案 |

## 3. 当前可用教程

| 路径 | 保留理由 |
|---|---|
| `docs/MUJOCO_MOVE_MOTOR_GUIDE.md` | 当前 MuJoCo-only 动作和路径规划教程 |
| `docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md` | 上电全链路验证 |
| `docs/PRODUCT_AUTOSTART_GUIDE.md` | 产品/研发自启动 |
| `docs/SIM_HOST_NANOPI_NETWORK_GUIDE.md` | NanoPi 和仿真主机网络 |
| `docs/NANOPI_CAN_MASTER_USAGE.md` | NanoPi 调试工具说明，保留但必须标为 bench-debug |
| `docs/TESTING_GUIDE.md` | 测试入口 |

## 4. 建议合并或归档的文档

这些文档不是立刻删除对象，但容易和当前主线重复。建议下一轮整理时移动到 `docs/archive/`，或把仍有价值的片段合并进当前入口文档。

| 路径 | 建议 | 原因 |
|---|---|---|
| `docs/架构.md` | 归档或删除 | 已被 `REHAB_ARM_SYSTEM_ARCHITECTURE.md` 和 `CURRENT_PROJECT_BRIEFING.md` 覆盖 |
| `docs/MEDICAL_ARM_MUJOCO_LEARNING_GUIDE.md` | 合并后归档 | 与 `MUJOCO_MOVE_MOTOR_GUIDE.md`、`MUJOCO_URDF_GAP_AND_STEP_GUIDE.md` 重叠 |
| `docs/MUJOCO_NANOPI_INTEGRATION_PREP.md` | 合并后归档 | 早期准备文档，当前已有 power-on 和 mainline 文档 |
| `docs/REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md` | 合并后归档 | 偏新手/早期框架，当前架构文档已覆盖大部分 |
| `docs/HTTP_BRIDGE_README.md` | 归档 | 早期 HTTP bridge，当前正式运动不走 HTTP 直控 |
| `docs/MESSAGE_ENDPOINT_FIX.md` | 归档 | 历史修复说明，保留到 troubleshooting 后可归档 |
| `docs/OPENCLAW_BRIDGE_README.md` | 归档 | OpenClaw 高层服务旁线，不是当前真机控制主线 |
| `docs/OPENCLAW_PERFORMANCE.md` | 归档 | OpenClaw 性能历史资料 |
| `docs/OPENCLAW_ENDPOINTS.py` | 移出 docs 或归档 | 代码文件放在 docs 下容易混乱 |
| `docs/SPEED_OPTIMIZATION_SUMMARY.md` | 归档 | 历史优化总结 |
| `docs/TOMORROW_INTEGRATION_PROMPTS.md` | 归档 | 临时提示词/计划，不应作为当前主线入口 |
| `docs/PLATFORM_AI_PROMPT_VLA_LVA_HTTP.md` | 归档或合并到平台协议 | 提示词类文档，容易过期 |
| `docs/APP_CONNECTION_GUIDE.md` | 保留或合并 | 若 APP 分支文档完善，可合并到 App 协议区 |
| `docs/VOICE_WAKE_TTS_PORTABILITY_GUIDE.md` | 保留或合并 | M55 语音仍有价值，但可压缩进 M55 文档索引 |

## 5. 已处理的重复草稿

| 路径 | 处理 |
|---|---|
| `docs/MUJOCO_QUICKSTART_JOINT_TRAJECTORY.md` | 删除本地未跟踪草稿，内容已并入 `docs/MUJOCO_MOVE_MOTOR_GUIDE.md` |

## 6. 建议的清理方式

不要直接一次性删除大量历史文档。建议分两步：

1. 新建 `docs/archive/`，先移动第 4 节文档。
2. 跑一次全仓搜索，确认没有 README 或教程入口引用这些旧文档。
3. 一周后如果无人需要，再删除 archive 中确定过期的内容。

这样 GitHub 历史还能追溯，后续 AI 也不会在 docs 根目录被旧资料干扰。

