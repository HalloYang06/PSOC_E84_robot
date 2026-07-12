# System overview

本页描述当前仓库中的产品主线，而不是对历史分支的汇总。协议细节分别见 `docs/protocols/can-protocol.md`、`docs/protocols/m33-m55-ipc.md`、`docs/protocols/app-api.md` 与 `docs/protocols/safety-boundary.md`。

## Product layers

1. **设备与实时控制层**：C8T6 采集 EMG/心率等传感数据；PSoC E84 的 M33 负责 CAN、关节映射、电机反馈、限位、心跳，并在架构上承担最终安全裁决；M55 负责本地推理、语音和模型结果发布。实现入口是 `firmware/c8t6/app`、`firmware/m33/applications/control/control_layer.c` 与 `firmware/m55/applications`。
2. **边缘协调层**：NanoPi 运行 ROS 2 与 SocketCAN bridge，把 `JointTrajectory` 候选转换为 `0x320`，并把 M33/C8T6 遥测转换为 ROS topics。入口是 `ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py`。
3. **数字影子层**：MuJoCo 接收硬件状态或独立仿真状态，用于 shadow/simulation，不替代 M33 的安全判定。入口是 `ros/rehab_arm_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/medical_arm_shadow_relay_node.py`。
4. **产品与数据层**：Android/移动 Web、平台 Web 和 FastAPI 提供账户、设备绑定、计划、训练记录、遥测上传、模型 relay 与可视化。入口是 `apps/mobile/www/rehab-mobile-runtime.js`、`platform/web/app/projects/[id]/rehab-arm-control/rehab-arm-control-client.tsx` 与 `platform/api/app/modules/rehab_arm`。
5. **高层智能层**：VLA 解析高层任务并生成建议或 dry-run trajectory candidate；它不是运动许可源。边界由 `ai/vla/services/vla_bridge_service.py` 与 `ai/vla/tests/test_control_boundary.py` 固定。

## Hardware and runtime ownership

| 部件 | 当前所有权 | 不拥有的权限 |
| --- | --- | --- |
| C8T6 | ADC/EMG/心率采集、滤波、`0x7C2` sensor 与 `0x7C3` health 上报 | 电机运动许可 |
| M33 | CAN 总线、电机协议适配、关节限位/校准、pre-arm 状态汇总、`0x322` 安全状态与最终执行边界 | M55/云端模型训练 |
| M55 | M33-M55 IPC 消费、本地模型/语音处理、模型结果建议 | 绕过 M33 直接驱动电机 |
| NanoPi/ROS bridge | `JointTrajectory` 校验、SocketCAN 编解码、heartbeat、ROS telemetry topics | 最终安全裁决；默认也不发送 target |
| MuJoCo | simulation/shadow 可视化与数据验证 | 真实硬件控制权 |
| App/Web/API | 用户、计划、训练记录、设备数据与高层请求 | 直接 CAN 或电机输出 |

设计原则 `M33_ARCHITECTURAL_FINAL_SAFETY_AUTHORITY`：M33 是架构上的最终安全裁决者；M55、VLA、平台、App 和 ROS 只能提供建议、候选轨迹或上层门控。当前 `ctrl_assess_ros_command_safety()` 对 `SET_TARGET` 已检查 NanoPi heartbeat、joint mapping、position/rpm/`torque_ma` bounds 与 calibration。反馈 freshness/fault 会进入 pre-arm/status readiness，但 accepted `SET_TARGET` 的 apply path 尚无证据表明会重新执行完整 pre-arm 或 current-mode gate；这是必须补齐的实现缺口，不能把设计原则写成已完全执行的事实。

## Formal motion path

正式的数据形态是：App/Web/VLA/planner 的高层请求或候选 → ROS 2 `JointTrajectory` → NanoPi bridge → classic CAN `0x320` → M33 本地安全审核 → 电机私有协议。ROS bridge 订阅 `/arm_controller/joint_trajectory`，检查已知关节、有限数值、点数、限位、M33 `0x322` 新鲜许可和电机反馈，再生成 `SET_TARGET`。

这条路径当前具有两道独立默认闸门：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py` 的 `enable_target_tx=false` 使 target 仅 dry-run；`firmware/m33/applications/control/control_layer_cfg.h` 当前选择 development bench motion、关闭 clinical motion。因而“代码路径存在”不等于“临床主线已使能”。

## Telemetry and model-result path

- C8T6 → M33/NanoPi：`0x7C2` 传 sensor，`0x7C3` 传 health；ROS bridge 发布 `/rehab_arm/sensor_state`。
- 电机 → M33 → NanoPi：M33 聚合异构电机反馈，以 `0x330`–`0x334` 对应五个正式 ROS slot；bridge 发布 `/rehab_arm/motor_state` 与新鲜数据驱动的 `/joint_states`。
- M33 → M55：`MSG_TYPE_SENSOR_SNAPSHOT` / `MSG_TYPE_SENSOR_STREAM` 经双队列 IPC 提供模型输入。
- M55 → M33 → NanoPi：`MSG_TYPE_AI_INFERENCE_RESP` 回到 M33，再由 M33 以 `0x323` 发布；该帧强制带 `suggestion_only`，bridge 发布 `/rehab_arm/model_state`。
- NanoPi → platform API：motor/sensor/safety、session 和文件属于非实时上传与产品数据，不组成电机闭环。实现见 `platform/api/app/modules/rehab_arm/router.py`。

## Mainline vs simulation/bench

- **mainline contract**：ROS bridge、M33 safety gate、正式 telemetry topics 与平台上传契约；真实 target 仍需显式启用且通过 M33。
- **shadow-sim**：`ros/rehab_arm_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py` 观察硬件状态，不向 M33 授权。
- **simulation**：`ros/rehab_arm_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_shadow.launch.py` 和 `ros/rehab_arm_ws/src/rehab_arm_bringup/launch/sim_data_collection.launch.py` 用于仿真/采集。
- **bench/offline demo**：历史五关节 demo/VLA publisher 被保留用于离线验证，隔离规则见 `tools/bench-debug/legacy-5dof/README.md`；正式 launch 边界由 `ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py` 检查。

## Current verified capability

这里的“已验证”限定为仓库实现和自动化契约，不冒充最新实机验收：

- M33 与 ROS 对 `0x320`、`0x321`、`0x322`、`0x323`、`0x330`–`0x334` 的编码、解析和安全门控有对应实现与测试，见 `ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_m33_ros_contract.py`。
- M33/M55 共享 message ABI、双向 IPC queue、sensor input 和 AI response bridge 已落入两侧源码，静态契约见 `firmware/m55/tools/test_emg_intent_bridge_contract.py`。
- BLE NUS profile 已实现连接、通知、heartbeat/stream 控制及只读拒绝策略，启动策略测试见 `firmware/m33/tools/test_m33_ble_startup_policy_static.py`。
- 平台具备 App API、设备遥测上传、训练与 AI 草稿边界测试，见 `platform/api/tests/test_rehab_arm_app_backend.py` 与 `platform/api/tests/test_rehab_arm_sync.py`。
- MuJoCo shadow relay 有离线测试，见 `ros/rehab_arm_ws/src/rehab_arm_sim_mujoco/test/test_medical_arm_shadow_relay_node.py`。

## Known incomplete capability

- ROS target 发送默认关闭；当前 M33 是 bench build，clinical motion 关闭，不能据此宣称临床可穿戴运动链闭环完成。
- 当前正式 motor telemetry 仅定义五个 slot (`0x330`–`0x334`)；`0x335`–`0x337` 只是 NanoPi 接受的未来保留范围。代码/文档证据未建立完整六自由度实机反馈映射。
- `0x330` parser 内仍保留 `proposed_firmware_pending` 元数据，而 M33 已存在 publisher；这说明软件来源状态标记尚未统一，不能替代实机证据。
- IPC message ABI 没有显式 wire version、packing 或跨编译器字节序声明；只能按当前同平台 C struct 使用。
- `SET_TARGET_PREARM_RECHECK_GAP`：当前 accepted `SET_TARGET` 路径没有重新执行完整 pre-arm/current-mode gate；反馈 freshness/fault 虽参与 pre-arm 与状态生成，但尚未证明在每条 target 应用前都会 fail closed。临床路径必须先补齐并验证此规则。
- Platform API、App、Web、VLA 和 MuJoCo 均未实现直接 motor control；云端计划接受、模型结果或 UI 状态都不是运动许可。
