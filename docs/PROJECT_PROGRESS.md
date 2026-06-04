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

- 2026-06-04 地基更新：
  - NanoPi 新增 `m33_model_status.py`，解析 M33 -> NanoPi `0x323` 模型摘要帧，并在 `psoc_can_bridge_node.py` 发布 `/rehab_arm/model_state`。
  - M33 本地工程新增模块化 `applications/m33/m55_model_bridge.*`，消费 `MSG_TYPE_AI_INFERENCE_RESP`/`MSG_TYPE_ASR_TEXT`；control layer 新增 `control_publish_m55_model_result()`，统一发送 `0x323`。
  - M55 Git 证据仓库和实际 `wifi` 工程均新增 `applications/model_result_publisher.*`，当前用 wake-word/voice 小模型做最小验证，不把 AI 逻辑堆进 `main.c`。
  - `0x323`/`/rehab_arm/model_state` 已写入协议和架构文档，固定为 `model_suggestion_only_not_motion_permission`，不改变 `motion_allowed`，不直接映射 `0x320`。
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
| `motor_id=1` | 4015 小电机，协议待补 | 腕部两轴之一，`wanbu_zongxiang_joint` 或 `wanbu_hengxiang_joint` 待确认 |
| `motor_id=2` | 4015 小电机，协议待补 | 腕部两轴之一，`wanbu_zongxiang_joint` 或 `wanbu_hengxiang_joint` 待确认 |
| `node_id=3` | CANSimple/ODrive 类标准帧协议 | `jian_hengxiang_joint` 肩横向，电机轮:输出轴轮 `1:2`，方向/零点待标定 |
| `motor_id=4` | 私有扩展帧 MIT 电机协议 | `jian_zongxiang_joint` 肩纵向，多级齿轮比待补 |
| `motor_id=5` | 私有扩展帧 MIT 电机协议 | `zhou_zongxiang_joint` 肘纵向，方向/零点待标定 |
| `motor_id=6` | 私有扩展帧 MIT 电机协议 | `jian_xuanzhuan_joint` 肩/上臂旋转，方向/零点待标定 |
| `motor_id=7` | 私有扩展帧 MIT 电机协议 | 外部调试电机，当前没有装在机械臂上，不进入正式机械臂映射 |
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段命令 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat |
| `0x322` | M33 -> NanoPi | M33 状态回复 |
| `0x7C2` | C8T6 -> M33 | 传感数据 |
| `0x7C3` | C8T6 -> M33 | 健康状态 |

## 已完成

### 2026-06-03

- 整机架构地基收敛到同一条主线：
  - `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md` 新增“整机架构地基合同”，明确唯一主线是 `传感/电机反馈 -> M33 -> NanoPi -> 仿真主机/服务器/VLA -> NanoPi -> M33 -> 电机`，正式运动入口只认 `JointTrajectory -> NanoPi -> M33 -> 电机`。
  - 明确 M55、M33 BLE 到 App、NanoPi 到服务器、Linux 仿真主机无线 ROS、7号 EL05 都是旁线或研发通道：只能提供状态、意图、建议、shadow、dry-run 或 bench-debug，不能形成新的真机控制闭环。
  - `docs/INTEGRATION_GUIDE.md` 新增“当前主线和旁线对接纪律”，要求新增字段优先落到 `PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`、`PSOC_CAN_PROTOCOL_V1.md`、`medical_arm_6dof_schema.yaml` 或 ROS2 topic 合同，不允许各端各自定义一套。
  - 新增 `test_system_architecture_contract.py`，静态锁住正式运动链路、M33 最终裁决、M55 旁线、App BLE、NanoPi 到服务器、无线 ROS 和共享合同引用，防止后续 AI 把历史 demo 或旁线改成新主线。
- M55/服务器/VLA 数据地基继续补齐：
  - 新增 `docs/M55_MODEL_RESULT_PROTOCOL_V1.md`，定义 `/rehab_arm/model_state`、`rehab_arm_model_state_v1`、第一版 M55 意图/疲劳/语音编号表和 `model_suggestion_only_not_motion_permission` 边界。
  - `data_recorder_node.py`、`jsonl_replay_node.py` 和 `data_recording.py` 接入 `/rehab_arm/model_state`，让 M55/服务器模型摘要可记录、回放、进入 VLA 数据集；`perception_vla` topic profile 现在要求 `/rehab_arm/model_state` 和 `/rehab_arm/camera_keyframe`。
  - `docs/INTEGRATION_GUIDE.md`、`docs/SERVER_SYNC_API_DRAFT.md`、`docs/USER_MANUAL.md` 同步拆分 `/rehab_arm/sensor_state` 和 `/rehab_arm/model_state`：前者是传感摘要，后者是模型建议，二者都不是运动许可。
- M33/M55 IPC、M33 BLE 到 App、M55 小模型部署地基继续补齐：
  - 新增 `docs/M33_M55_IPC_BLE_FOUNDATION.md`，从 GitHub 分支和提交历史确认 M55 主线是 `M55` 分支对应的 WiFi 工程；`wifi` 本地目录当前 `.git` 损坏，历史以 `_m55_ref_repo` 为准。
  - 明确 M33/M55 已有 `m33_m55_comm`：短消息走 Infineon MTB-IPC queue，大块 PCM 走 linker `.ipc_stream_shared`，共享区 `0x261C0000/0x00040000`；后续 EMG/语音/模型结果不能另造跨核通讯。
  - 明确 M33 BLE 已有 NUS 风格 RX/TX、`OpenClaw-NUS`、`stream:on/off`、`heartbeat`、`stop`、`mode:*` 和 bench `move:*`；正式 App 字段应补 safety/profile/joints/motors/sensors/model/session，但 App 仍只能请求/标注，不能发 CAN 或底层电机目标。
  - 新增 `docs/M55_MODEL_DEPLOYMENT_GUIDE.md`，小模型部署按 TFLite Micro 官方/现有路径：量化 `.tflite` -> `xxd -i` C array -> `model_manager_load_tflm_model()` -> `m33_m55_comm_publish()` -> M33 -> NanoPi `/rehab_arm/model_state`。
  - 更新 `M55_MODEL_RESULT_PROTOCOL_V1.md`、`REHAB_ARM_SYSTEM_ARCHITECTURE.md`、`INTEGRATION_GUIDE.md`、`PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` 和 `USER_MANUAL.md`，锁定后续 AI 复用现有 GitHub 工程、IPC、BLE 和模型部署合同。

- 产品自启动与 MuJoCo hardware shadow 基础链路完成实测打通：
  - NanoPi `rehab-arm-nanopi-readonly.service` 已安装、`enabled`、`active`，产品上电后自动运行 `psoc_can_bridge_node.py`，参数固定 `enable_target_tx=false`。
  - NanoPi 服务采用 root `ExecStartPre=+/usr/local/bin/setup_nanopi_can.sh` 配置 MCP2518FD/`can0`，随后以 `User=pi` 运行 ROS2 bridge；避免 root ROS2/DDS 环境问题，也避免 `pi` 用户在 systemd 中无交互 sudo。
  - 现场复测发现 `mcp251xfd spi3.0: Failed to detect MCP2518FD` 时，重载 `mcp251xfd` 可恢复 `can0`；该恢复动作已放入 `setup_nanopi_can.sh`。
  - NanoPi 实测：`can0` 为 `ERROR-ACTIVE`，M33 heartbeat `0x321 -> 0x322` 正常，`0x330~0x334` 周期状态存在，`/rehab_arm/motor_state`、`/rehab_arm/safety_state`、`/joint_states` 均可读。
  - 7 号 EL05 外部电机当前作为临时 shadow 源：`0x334 fresh -> /joint_states forearm_rotation_joint=0.048`。
  - 仿真主机 `rehab-arm-sim-host-shadow.service` 已安装、`enabled`、`active`，自动启动 `medical_arm_6dof_hardware_shadow.launch.py`。
  - 无线 ROS2 端到端验证通过：仿真主机收到 NanoPi `/joint_states forearm_rotation_joint=0.048`；relay 发布 `/sim/medical_arm/joint_trajectory` 六关节位置 `[0.0, 0.0, 0.048, 0.0, 0.0, 0.0]`；MuJoCo `/sim/medical_arm/joint_states` 同步输出 6 个 joint，`name/position/velocity/effort` 长度均为 6。
  - 安全复测：NanoPi 只读服务运行期间单独抓 `timeout 2 candump -L can0,320:7FF` 超时无输出，未发现自动 `0x320` 运动帧。
  - 本地验证：`python -m unittest` 相关 30 项通过；`py_compile` 通过。远程仿真主机构建 `rehab_arm_description rehab_arm_sim_mujoco` 通过。
  - 当前仍不是完整 medical_arm 6DOF 真机控制：M33 正式 6DOF 协议、其他 5 个真实关节 fresh feedback、方向/零点/传动比/患者限位仍待逐个接入和标定。
  - 教程加固：`docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md` 新增“当前地基验收总表”，明确每次上电后从 NanoPi service、CAN、M33、7号 shadow、无线 ROS、MuJoCo 6DOF 到无 `0x320` 的 pass/fail 标准；第 12 节改成逐关节补齐流程，要求每次只补一个真实关节，并把 1/2/3/4/5/6 号当前下一步写清楚。

- 电池上电后完成基础端到端打通：
  - NanoPi `can0` 恢复为 classic CAN 1Mbps `ERROR-ACTIVE`，`timeout 3 candump -L can0` 可见 M33 `0x330~0x334` 周期帧和 `0x321/0x322` 心跳。
  - M33 heartbeat 通过：`0x321#14 -> 0x322#A514070001020100`，发送后 `can0` 当前错误计数保持 `tx 0 rx 0`。
  - 7 号 EL05 active-report 通过：可见 `0x180007FD`，M33 `0x334` 从 stale `flags=0x10` 变成 fresh `flags=0x00`，位置示例 `0x015C` 约 `0.348 rad`。
  - NanoPi ROS bridge 只读通过：`/rehab_arm/motor_state` 有数据，`/joint_states` 发布 `forearm_rotation_joint`，位置示例 `0.348 rad`。
  - 外部 7 号 formal M33 bench 动作通过：发送 `0x320#0304140001000000` 和 `0x320#0304ECFF01000000`，即 ROS joint4 `+2°/-2°`、`1 rpm`、`0 torque_ma`；抓包 `/tmp/motor7_formal_basic_20260602_222057.candump` 记录 `0x320`、`0x334`、`0x180007FD/0x188007FD`，M33 聚合位置从约 `0.348 rad` 变到约 `0.049 rad`。
  - 仿真主机通过无线 ROS2 看到 NanoPi 真实状态：`cal@192.168.2.46` 可 `ros2 topic echo --once /joint_states`，收到 `forearm_rotation_joint=0.049`。
  - 新增并验证 `medical_arm_shadow_relay_node.py`：默认把 NanoPi legacy `forearm_rotation_joint` 映射到 MuJoCo 6DOF `jian_xuanzhuan_joint`。
  - 新增并验证 `medical_arm_6dof_hardware_shadow.launch.py`：远程启动后 `/sim/medical_arm/joint_states` 输出 6 个真实 medical arm joint，其中 `jian_xuanzhuan_joint=0.049`，证明 `7号外部电机 -> NanoPi/M33 -> ROS -> 无线 -> MuJoCo 6DOF shadow` 基础链路已通。
  - 继续完善 6 关节 hardware shadow 主线：`medical_arm_shadow_relay_node.py` 默认 `publish_full_target=true`，向 `/sim/medical_arm/joint_trajectory` 发布完整 6 个 medical arm joint；当前只有 `forearm_rotation_joint -> jian_xuanzhuan_joint` 来自 7 号真实反馈，其他 5 个关节使用显式 `placeholder_positions_json` 保持位。
  - 2026-06-03 远端联调复测通过：NanoPi `/joint_states` 为 `forearm_rotation_joint=0.049`；仿真主机 `/sim/medical_arm/joint_trajectory` 输出 `jian_hengxiang_joint`、`jian_zongxiang_joint`、`jian_xuanzhuan_joint`、`zhou_zongxiang_joint`、`wanbu_zongxiang_joint`、`wanbu_hengxiang_joint`，位置 `[0.0, 0.0, 0.049, 0.0, 0.0, 0.0]`；`/sim/medical_arm/joint_states` 同步为 6 关节状态。
  - 补齐仿真学习基础：`check_sim_env.py` 报告新增 `medical_arm_6dof_contract` 和 `medical_arm_6dof_topic_contract`，明确 6DOF joint 名、MJCF/schema/launch 路径、`/sim/medical_arm/*` topic 合同、当前 7 号 shadow 映射和未接关节占位策略。
  - 新增 `docs/MEDICAL_ARM_MUJOCO_LEARNING_GUIDE.md`：给后续只学习 MuJoCo 仿真的最小路线，覆盖单机 shadow、硬件 shadow、参数修改位置、标定补充顺序和禁止事项。
  - 新增 `docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md`：从上电开始按层验证电机/M33、NanoPi CAN、M33 `0x330~0x334`、7 号 EL05 active-report、NanoPi 只读 bridge、仿真主机 MuJoCo 单机 shadow、NanoPi hardware shadow、小幅 7 号台架测试和停止清理。
  - 新增产品自启动基础：`deploy/scripts/start_nanopi_product_readonly.sh`、`deploy/systemd/rehab-arm-nanopi-readonly.service`、`deploy/scripts/start_sim_host_medical_arm_shadow.sh`、`deploy/systemd/rehab-arm-sim-host-shadow.service` 和 `docs/PRODUCT_AUTOSTART_GUIDE.md`。NanoPi 产品默认自启动只读 bridge，固定 `enable_target_tx=false`；仿真主机 shadow 自启动仅用于研发。
  - 新增 `test_product_autostart_contract.py`，静态防止产品自启动脚本包含 `enable_target_tx:=true`、`m33 target`、`private speed`、`private csp` 等运动入口。
  - 决策澄清：M33 当前已对上的是 legacy 5 槽位和 7 号外部电机 shadow 链路，不是完整 medical_arm 6DOF 正式 M33 协议；其他正式关节仍需要逐个接电机、标定、补 `joint_map_json`。
  - 断电后未做任何远端硬件操作；本地 33 项单测通过，`py_compile` 通过；Windows 本机没有 `bash`，shell 脚本 `bash -n` 需后续在 NanoPi/仿真主机 Linux 上复测。
  - 本轮验证：本地 `python -m unittest ...test_medical_arm_shadow_relay_node.py ...test_mujoco_backend.py ...test_medical_arm_6dof_schema.py` 通过 22 项；本地 `py_compile` 通过；远程仿真主机 `./build_ros2.sh --packages-select rehab_arm_sim_mujoco` 和 `test_medical_arm_shadow_relay_node.py` 通过。
  - 测试后已关闭 7 号 active-report 并发送 stop；`0x334` 回到 stale，`can0` 仍为 `ERROR-ACTIVE`。
  - 未完成：还没有把其他 5 个关节接入真实电机反馈；7 号 shadow 仍只是 MuJoCo shadow/demo，不是正式 6 号真机执行；4 号齿轮比例、1/2 号腕部对应关系、各关节零点/方向/限位仍待标定。

- 搭建 medical_arm 6DOF MuJoCo shadow 基础框架：
  - 新增 `rehab_arm_sim_mujoco/models/medical_arm_6dof.xml`，包含 6 个真实 URDF joint：`jian_hengxiang_joint`、`jian_zongxiang_joint`、`jian_xuanzhuan_joint`、`zhou_zongxiang_joint`、`wanbu_zongxiang_joint`、`wanbu_hengxiang_joint`。
  - `mujoco_backend.py` 新增 `joint_profile=medical_arm_6dof`，保留旧 `legacy_5dof` 默认行为；6DOF profile 有独立 joint 名、限位、速度上限和默认 MJCF。
  - `mujoco_sim_node.py` 新增参数化 topic：`joint_state_topic`、`trajectory_topic`、`safety_state_topic`、`sensor_state_topic`；6DOF shadow 默认走 `/sim/medical_arm/*`，不污染真机 `/joint_states` 或 `/arm_controller/joint_trajectory`。
  - 新增 `medical_arm_6dof_shadow.launch.py`，用于一条命令启动 6DOF shadow 仿真。
  - 更新 `medical_arm_6dof_schema.yaml`：`jian_xuanzhuan_joint` 正式 motor 仍是 6 号；当前允许 7 号 EL05 作为 `temporary_shadow_motor_ref` 临时代替 6 号，只限 `bench_debug_and_mujoco_shadow_only`。
  - 远程仿真主机已同步并验证：`cal@192.168.2.46:/home/cal/桌面/Medical-Rehabilitation-Manipulator` 构建 `rehab_arm_sim_mujoco`/`rehab_arm_description` 通过；`ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_shadow.launch.py` 日志显示 `backend=mujoco-model, joint_profile=medical_arm_6dof`。
  - 远程 ROS topic 验证通过：发布 `/sim/medical_arm/joint_trajectory` 六轴轨迹后，`/sim/medical_arm/joint_states` 输出 6 个真实关节和目标位置。
  - 远程 viewer 入口已准备：`/home/cal/medical_arm_mujoco/open_medical_arm_6dof_shadow.sh`，模型文件为 `/home/cal/medical_arm_mujoco/medical_arm_6dof_shadow.xml`。
  - 验证：本地和远程 `test_mujoco_backend.py`、`test_medical_arm_6dof_schema.py` 通过；`mujoco_backend.py`、`mujoco_sim_node.py` `py_compile` 通过。
  - 未完成：真实质量/惯量、精确 mesh/collision、4 号齿轮比例、1/2 号腕部对应关系、各关节方向/零点/患者限位仍需后续现场逐步标定。

- 完成 NanoPi CAN 无输出现场非运动诊断：
  - NanoPi `pi@192.168.2.66` 在线，`can0` 可拉起为 classic CAN 1Mbps `ERROR-ACTIVE`，当前 `berr-counter tx 0 rx 0`。
  - `timeout 5 candump -L can0` 无任何被动帧。
  - 只发送 M33 heartbeat：`python3 /home/pi/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1`，只见 `TX STD 0x321`，无 `RX 0x322`。
  - 重置 `can0` 后再次发送 heartbeat `seq=2`，仍无 M33 回复，`TX errors/dropped` 和 `bus-off/re-started` 继续增加。
  - 只发送 7 号 EL05 非运动 stop/clear-fault：`private stop --motor 7 --clear-fault`，只见 `TX EXT 0x0400FD07`，无 `0x180007FD/0x188007FD/0x334` 反馈，错误计数继续增加。
  - `dmesg` 显示 MCP2518FD 初始化正常，但测试期间出现多次 `can0: bus-off, scheduling restart in 100 ms`。
  - 结论：当前不是 ROS/MuJoCo/VLA 问题，也不是单个协议解析问题；NanoPi CAN 控制器正常，但总线上当前没有 M33 或电机节点 ACK/反馈。下一步需要现场检查 M33/电机侧供电、共地、CANH/CANL、终端电阻、线束分支、M33 CAN 收发器使能和电机驱动在线状态。
  - 安全：本轮没有发送 `0x320` 目标、位置、速度、力矩或电流命令；仅发送 heartbeat 和 stop/clear-fault。

### 2026-06-02

- 收紧旧 5 关节台架表、新 6 关节 medical_arm 表和 7 号 EL05 临时用途边界：
  - 更新 `motor_profiles.py`：保留 legacy `gear_ratio` 兼容字段，同时新增 `joint_command_ratio`、`drive_internal_reduction_ratio`、`command_position_semantics`、`medical_arm_6dof_joint` 和 `mapping_scope`。
  - 明确 4/5 号是灵足 RS00、6/7 号是灵足 EL05；对 RobStride CSP formal path，4/5/6/7 当前正确关节命令比例是 `1.0`，不得额外乘 `10:1/9:1`；3 号伺泰威 CANSimple/ODrive-like 才需要按减速/协议侧 rev 单位换算。
  - 更新 `medical_arm_6dof_schema.yaml`：保持 `motor_id_7_in_formal_mapping=false`，新增 `allow_motor_id_7_as_temporary_mujoco_shadow_actuator=true`，并把 7 号标为 `temporary_mujoco_shadow_and_external_bench_only`。
  - 更新 `docs/JOINT_MOTOR_MAPPING_DRAFT.md`、`docs/MUJOCO_NANOPI_INTEGRATION_PREP.md`、`docs/USER_MANUAL.md`，把 legacy `shoulder_lift_joint..forearm_rotation_joint` 与新 `jian_* / zhou_* / wanbu_*` 映射分开说明。
  - 决策：后续 AI 和 demo 可以用 7 号 EL05 验证 ROS/NanoPi/M33/MuJoCo 数据流，但 VLA、患者 profile、正式 MJCF 和 M33 medical_arm 执行表不得把 7 号当实物关节。

- 完成 `medical_arm.zip` 可视化后关节/电机映射草案更新：
  - 新增 `docs/JOINT_MOTOR_MAPPING_DRAFT.md`，记录 6 个 URDF 关节、保守 ROM、当前电机对应关系和后续 AI 必须遵守规则。
  - 已确认：`node_id=3 -> jian_hengxiang_joint`，传动为电机轮:输出轴轮 `1:2`；`motor_id=4 -> jian_zongxiang_joint`，齿轮比待补；`motor_id=6 -> jian_xuanzhuan_joint`；`motor_id=5 -> zhou_zongxiang_joint`；4015 小电机 `motor_id=1/2` 属于腕部两轴但具体对应待确认。
  - 明确 `motor_id=7` 当前没有装在机械臂上，只作为外部调试电机，不进入 MuJoCo/VLA/正式机械臂映射。
  - 已修改解压模型 `medical_arm_viewer.urdf` 和 `urdf/medical_arm.urdf`：6 个关节从 `continuous` 改为带保守初始人体/康复 ROM 的 `revolute`。
  - 同步更新 README、系统架构、MuJoCo 差距教程和 CLAUDE 规则，避免后续 AI 继续按旧 7 号或待绑定表理解。
  - 未执行硬件测试、ROS 测试或固件编译；当前限位仍是仿真 smoke-test 起步值，正式穿戴前必须补机械硬限位、患者 profile、方向、零点、传动比、速度/力矩/电流限制。

- 完成远程 MuJoCo 主机第一版可视化 MJCF：
  - 远程主机：`cal@192.168.2.46`，MuJoCo 目录为 `/home/cal/mujoco`，viewer 可执行文件为 `/home/cal/mujoco/build/bin/simulate`。
  - 模型目录：`/home/cal/medical_arm_mujoco/`。
  - 生成文件：`medical_arm_mujoco.xml`、`README_MUJOCO.md`、`joint_motor_mapping.yaml`、`validate_mujoco.py`、`open_mujoco.sh`、两张预览图。
  - 当前 MJCF 包含材质、地面、灯光、两个相机、6 个 hinge joint、6 个 position actuator、末端 site、关节轴 marker 和简化 collision proxy。
  - 验证：`MUJOCO_GL=egl python3 validate_mujoco.py` 通过，输出 `nq=6 nv=6 nu=6 ngeom=15 ncam=2`，并成功渲染 `medical_arm_mujoco_preview.png` 和 `medical_arm_mujoco_preview_close.png`。
  - 未验证：没有接 ROS2/NanoPi；没有真实电机或 M33 控制；collision proxy 仍需按实物进一步调。

- 新增 MuJoCo 接 NanoPi 准备方案：`docs/MUJOCO_NANOPI_INTEGRATION_PREP.md`。
  - 明确当前不能把新 6 关节 MJCF 直接接入旧 5 关节 M33 bridge，必须先做 joint schema/adapter。
  - 规划阶段：单机 MuJoCo、`/sim/medical_arm/*` shadow topics、NanoPi 只读状态、dry-run 轨迹、6 关节 schema 对齐、VLA/服务器接入。
  - 决策：接 NanoPi 初期必须保持 `enable_target_tx=false`；所有轨迹先只产生 DRY-RUN，不允许发 `0x320`。
  - 更新 `docs/SIM_HOST_NANOPI_NETWORK_GUIDE.md`，增加新 6 关节模型与旧 5 关节 bridge 的冲突说明和文档入口。
  - 新增 `rehab_arm_description/config/medical_arm_6dof_schema.yaml`，记录 6 个 URDF joint、shadow topics、安全默认值、电机草案映射和 7 号外部调试边界。
  - 新增 `test_medical_arm_6dof_schema.py`，防止后续误删 6 关节、误开真机目标、或把 7 号放回正式映射。
  - 验证：`python -m unittest rehab_arm_ros2_ws/src/rehab_arm_description/test/test_medical_arm_6dof_schema.py` 通过，`4 tests OK`。

- 完成 NanoPi/仿真主机只读链路复查和 demo/mainline 边界收紧。
  - 远程连接：仿真主机 `cal@192.168.2.46` 可 SSH，NanoPi `pi@192.168.2.66` 可 SSH。
  - 仿真主机验证：`/home/cal/medical_arm_mujoco/medical_arm_mujoco.xml` 存在，`MUJOCO_GL=egl python3 validate_mujoco.py` 仍通过并渲染预览。
  - NanoPi 验证：`can0` 从 STOPPED 拉起到 classic CAN 1Mbps `ERROR-ACTIVE`，tx/rx error counters `0/0`。
  - 被动抓包：5 秒内看到 M33 `0x330~0x334` 周期帧；启动 bridge 后 12 秒抓包统计 `0x330~0x334` 各 114 帧、`0x321` 7 帧、`0x322` 7 帧、`0x320` 0 帧。
  - ROS2/DDS 验证：仿真主机能从 NanoPi bridge 收到 `/rehab_arm/safety_state` 和 `/rehab_arm/motor_state`；短窗口内 `/joint_states` 无样本，后续要确认 M33 motor status fresh 判定和电机未接场景语义。
  - 决策：`demo_trajectory_node.py`、`vla_task_planner_node.py`、`m33_motor_status_smoke.py`、`nanopi_can_master.py`、fallback backend 均明确为 demo/debug/smoke/bench，不得当作 6 关节主线或真机 readiness。
  - 更新：`rehab_arm_ros2_ws/README.md`、`docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`、`docs/MUJOCO_NANOPI_INTEGRATION_PREP.md`、`docs/USER_MANUAL.md`，要求后续 AI 先声明任务属于 mainline、shadow-sim、dry-run、bench-debug 或 offline-demo。

- 完成 NanoPi dry-run 安全门测试，不使用 demo 节点。
  - 工具链：仿真主机直接用 `ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory ...` 发布单关节测试消息；NanoPi 运行现有 `psoc_can_bridge_node.py`，`enable_target_tx=false`。
  - 只读状态检查：`check_m33_motor_status_presence.py /tmp/rehab_bridge_readonly.candump --pretty` 显示 `valid_m33_motor_status_count=570`、`fresh_m33_motor_status_count=0`、`stale_m33_motor_status_count=570`、`target_0x320_count=0`。
  - 反馈源检查：`feedback_source_readiness.py` 输出 `safe_to_expect_joint_states=false`、`decision=motor_feedback_source_missing`，警告 M33 电机状态帧存在但全 stale，且没有真实 Sitaiwei/Lingzu 原始反馈帧。
  - 第一轮 dry-run：默认 `allow_bench_motion_for_trajectory=false`，延迟发布轨迹后 bridge 拒绝：`PSoC motion_allowed is not true, protocol_version=2, state=ok, control_mode=bench_armed, detail=none`；抓包 `0x320=0`。
  - 第二轮 dry-run：仅为验证门控临时设 `allow_bench_motion_for_trajectory=true`，仍保持 `enable_target_tx=false` 和 `require_fresh_motor_status_for_trajectory=true`；bridge 拒绝：`no fresh M33 motor feedback received`；抓包 `0x320=0`。
  - 结论：当前 CAN/M33/NanoPi/ROS2 上行和轨迹订阅链路已通；由于电机未接或反馈未 fresh，`/joint_states` 不应发布，轨迹不应进入 target 队列。这是安全正确的失败。

- 新增机械臂主线 AI 交接文档：`docs/ai-handoffs/rehab-arm-mainline-2026-06-02.md`。
- 交接内容覆盖：安全边界、当前仓库分工、M33/NanoPi/ROS/仿真/平台/App 对接关系、当前电机和 CAN 事实、后续 AI 提示词、近期最小可执行路线。
- 本次只做文档交接整理，未执行硬件测试、ROS 测试或固件编译。

- 完成 `medical_arm.zip` URDF/MuJoCo/VLA 方案评估，并新增交接文档：`docs/ai-handoffs/mujoco-vla-rehab-arm-plan-2026-06-02.md`。
- 评估结论：URDF 当前有 7 个 link、6 个 continuous 关节，但缺少关节限位、速度/力矩限制和临床 ROM；`config` 里只列出 2 个 controller joints，不能直接作为正式 MuJoCo/ROS2 控制模型。
- 决策：MuJoCo 第一阶段应先做 cleaned URDF/Xacro + MJCF，补最终 ROS joint 名称、人体安全 ROM、简化碰撞体、actuator/soft limit/damping，再接 rosbag/replay 和低风险台架验证。
- 决策：VLA 只能输出高层任务、子目标或安全轨迹候选，不能直接输出 CAN、电流、力矩、速度或绕过 M33；第一版推荐 Octo/小型 diffusion policy 打通数据闭环，后续再做 OpenVLA LoRA/OFT。
- 验证：已 fetch GitHub 远端确认 `_nanopi_rosnode_usbcan`、`yiliao_m33`、`_m55_ref_repo` 相关分支本地与远端提交对齐；本轮未执行硬件测试、ROS 测试或固件编译。

- 新增 MuJoCo 仿真差距清单和分阶段教程：`docs/MUJOCO_URDF_GAP_AND_STEP_GUIDE.md`。
- 文档明确当前 URDF 到可用 MuJoCo 模型缺少：最终 ROS joint 名、joint-to-motor mapping、人体 ROM/机械限位、速度/力矩限制、actuator、简化 collision、坐标系/轴向验证和 ROS2 topic 合同。
- 文档固化当前系统边界：VLA 链路为 `VLA/服务器 -> NanoPi -> M33`；仿真主机通过无线 ROS2/DDS 接 NanoPi；MuJoCo 只做仿真、轨迹验证、数据生产和回放，不能作为真机安全权威。
- 本次只新增教程文档和进度记录，未执行硬件测试、ROS 测试或固件编译。

- 补充 4 路肌电参与 VLA 和 MuJoCo 仿真的方案到 `docs/MUJOCO_URDF_GAP_AND_STEP_GUIDE.md`。
- 决策：原始高频 EMG 由 C8T6/M33/M55 本地处理，VLA 只读取 M55 的低频意图、疲劳、共收缩、质量检测和辅助等级建议摘要；M55 输出必须标记为 suggestion-only，不能成为运动许可。
- 决策：MuJoCo 第一版不模拟真实肌肉电生理，只把 M55 摘要作为人类意图输入，用于 rosbag/JSONL 回放、合成意图测试、VLA grounding 和轨迹候选验证。
- 本轮未执行硬件测试、ROS 测试、M55 编译或真实 EMG 采集。

- 按当前目标架构补充 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`：
  - M33 通过 CAN 总线汇总原始传感和电机状态，把传感窗口、训练上下文和必要状态送到 M55。
  - M55 小模型结果以编号/结果码/置信度回到 M33，再由 M33 经 CAN 发给 NanoPi；NanoPi 按版本表解析语义并上传服务器。
  - NanoPi 上传摄像头关键帧、输出端 joint 状态、原始电机诊断、温度/速度/故障、active profile 限位摘要、M55 小模型结果和 M55 语音转文字/音频摘要。
  - 明确因齿轮、同步轮、减速器、连杆或推杆存在，`motor_id` 不等于 `joint`；服务器/VLA/仿真优先使用经过传动比、方向、零点、限位和回差说明换算后的输出端 joint 状态。
  - VLA 融合语音、摄像头、电机/关节状态、M55 小模型结果和限位上下文后，只能输出高层任务、分段目标或轨迹候选；NanoPi/仿真主机生成轨迹后仍由 M33 做最终安全裁决。
  - 本轮只更新架构文档，未执行硬件测试、ROS 测试、M55 编译或真实 VLA 推理。

- 同步更新 README、系统架构、MuJoCo 教程和仿真主机网络指南，使职责分工按当前架构统一：
  - README 新增 M33/M55/NanoPi/Linux 仿真主机/服务器职责分工表。
  - 系统架构文档新增当前职责分工基准，明确 `motor_id`、电机轴角和输出端 joint 必须分层。
  - `SIM_HOST_NANOPI_NETWORK_GUIDE.md` 新增无线 ROS2 延迟定位：无线可用于状态同步、仿真、规划、dry-run 和低频任务目标；急停、力矩/电流内环、fresh 判定和高频助力闭环必须留在 M33 本地安全路径。
  - `MUJOCO_URDF_GAP_AND_STEP_GUIDE.md` 补充无线 ROS2 不承担真机高频安全闭环。
  - 本轮仍只更新文档，未执行硬件测试、ROS 测试、M55 编译或真实 VLA 推理。

- 同步旧架构入口文档 `docs/架构.md`：
  - 原文件是早期 `ROS 2 + CAN + WebSocket` 草案，已替换为当前康复外骨骼主线架构入口。
  - 文档现在指向 `README.md`、`docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`、`docs/MUJOCO_URDF_GAP_AND_STEP_GUIDE.md`、`docs/SIM_HOST_NANOPI_NETWORK_GUIDE.md` 等权威文档。
  - 文档明确旧 WebSocket/CAN 草案不能作为当前实现依据，避免服务器或 VLA 被误解为可直接发 CAN。
  - 新增“后续 AI 必须遵守”规则，要求先读当前权威文档、禁止复活旧直控路径、禁止绕过 M33、禁止混淆 `motor_id` 和输出端 joint。
  - 更新 `CLAUDE.md` 项目概览、当前架构、无线仿真路径、强制 AI 规则和文档索引，使后续 AI 优先读取当前架构基准。

### 2026-05-27

- M33 CANSimple 假 fresh 防护：
  - 给 `scripts/nanopi_can_master.py` 增加 CANSimple 非运动探测动作：`cansimple get-error` 和 `cansimple address`，用于在线探测 3 号而不进入 closed-loop、不发位置/速度/力矩。
  - NanoPi 已同步脚本并验证 CLI 可用；`get-error` 发出 `0x063#00`，`address` 发出 broadcast `0x7E6#`。
  - 实测发现：发送 `0x063#00` 后，M33 `0x330` 短暂从 stale 变为 fresh，但抓包没有 3 号真实 `0x061/0x069` 回复；这是 M33 把主机查询帧当作 CANSimple feedback 刷新了 timestamp。
  - 已修 M33 本地工程：`ctrl_update_motor_feedback_cansimple()` 只有在收到 heartbeat、encoder estimate、MIT feedback、torque feedback 等真实反馈帧时才更新 `s_motor_feedback[idx].timestamp`；主机查询帧/未知 CANSimple 帧不再造成假 fresh。
  - 验证：主仓库 `scripts/nanopi_can_master.py` `py_compile` 通过；M33 `git diff --check` 通过。
  - 未验证：M33 需要用户重新烧录后复测；复测标准是发 `cansimple get-error` 后，如果仍没有 `0x061/0x069`，`0x330` 必须保持 `flags bit4=stale`。

- M33 CANSimple 假 fresh 防护烧录后复测通过：
  - 用户烧录 M33 `1e7ecb7b` 后，NanoPi `can0` 仍为 `ERROR-ACTIVE`，tx/rx error `0/0`。
  - M33 heartbeat/status 在线：`0x321#2C -> 0x322#A52C070000060000`。
  - 发 CANSimple 非运动查询 `0x063#00` 后，5 秒抓包统计：`0x063=1`、`0x330..0x334` 各 48 条。
  - `0x330` 48 条全部 `flags=0x10`，没有再被主机查询帧误刷新成 fresh。
  - 抓包仍没有 3 号真实 `0x061/0x069`，因此 3 号电机原始反馈当前未在线；M33 正确保持 stale。
  - 安全：本轮没有发送 closed-loop、idle、clear、position、velocity、torque 或 M33 target，只发送非运动查询。

- M33 重新烧录后重复确认：
  - 用户再次烧录后，NanoPi `can0` 仍为 `ERROR-ACTIVE`，tx/rx error `0/0`。
  - M33 heartbeat/status 在线：`0x321#2D -> 0x322#A52D070000060000`。
  - 只读抓包 5 秒只有 `0x330..0x334`，各 47 条，全部 `flags=0x10`，无 `0x061/0x069/0x180007FD` 原始电机反馈。
  - 再次发送 CANSimple 非运动查询 `0x063#00` 后，`0x330` 48 条全部保持 `flags=0x10`；确认主机查询帧不会造成假 fresh。
  - 下一步仍是现场恢复至少一个真实电机反馈源，再验证对应 M33 stale 位清零和 `/joint_states` 发布。

- M33 ROS 5 关节遥测检查器收敛：
  - `check_m33_motor_status_presence.py` 从旧的 `0x330~0x337` 全期望，改为正式必需 `0x330~0x334`，并验证 motor_id 映射 `3/4/5/6/7`。
  - `0x335~0x337` 改为 reserved：出现时仅 warning，不再作为缺失项。
  - 报告新增 `stale_m33_motor_status_count`、`fresh_m33_motor_status_count`、`motor_ids_by_status_id`、`required_m33_motor_status_mapping`。
  - 本地验证：`test_check_m33_motor_status_presence.py` 和 `test_psoc_motor_status.py` 共 19 tests passed，`py_compile` 通过。
  - NanoPi 验证：同步并重建 `rehab_arm_psoc_bridge` 后，用真实 `/tmp/post_flash_readonly_probe.candump` 检查通过：`0x330..0x334` 各 47 条，motor_id `3/4/5/6/7`，stale `235`，fresh `0`，`target_0x320_count=0`；NanoPi 单测 `6 passed`。

- M33 电机遥测常驻槽位上报：
  - 本地 M33 工程 `D:\RT-ThreadStudio\workspace\yiliao_m33` 已把 `0x330~0x336` 上报从“只发新鲜反馈”改为“所有已配置槽位周期上报”。
  - 有新鲜反馈时发布真实位置/速度/温度；没有新鲜反馈时发布 `flags bit4=stale_or_no_feedback`、位置/速度 0、温度 `0xFF`。
  - NanoPi/ROS parser 新增 `stale`/`data_fresh` 字段；stale 帧保留在 `/rehab_arm/motor_state`，但不生成 `/joint_states`，避免假 0 位姿污染仿真和规划。
  - 验证：`test_psoc_motor_status.py`、`test_m33_motor_status_smoke.py`、`test_check_m33_motor_status_presence.py` 共 26 tests passed；`py_compile` 通过；主仓库和 M33 工程 `git diff --check` 通过。
  - 未验证：本机没有 `scons` 命令，M33 固件未在当前 shell 编译；需要用户用 RT-Thread Studio 编译烧录后只读抓包验收。
  - 下一步：烧录后不发 `0x320`，只抓 `0x330~0x336`，确认周期帧存在、marker 为 `0xB3`、stale 位能区分缺反馈；再启动 NanoPi bridge 看 `/rehab_arm/motor_state`。

- M33 电机遥测烧录后只读验收与映射修正：
  - 用户烧录后，NanoPi `can0` 为 `UP/LOWER_UP`、`ERROR-ACTIVE`、1Mbps、tx/rx error `0/0`。
  - 只读抓包 5 秒得到 325 条 M33 电机状态帧，`0x330~0x336` 均为 `B3...10...FF` stale 帧，`target_0x320_count=0`。
  - presence checker 通过：`valid_m33_motor_status_count=325`，无 invalid 帧，无 `0x320`。
  - 随后启动只读 bridge 发现 `0x330` payload byte2 为 `1`，说明 M33 仍按内部 motor slot `1..7` 发布，而不是正式 ROS joint `0..4 -> motor 3/4/5/6/7`。
  - 已修正 M33 本地工程：`0x330..0x334` 现在按 ROS 5 关节槽位发布，byte2 应为 `3/4/5/6/7`；`0x335..0x337` 保留给未来扩展。
  - 下一步：用户重新烧录后，再做只读抓包，期望 `0x330..0x334` 出现且 byte2 为 `03 04 05 06 07`，然后再验收 `/rehab_arm/motor_state`。

- M33 ROS joint 遥测映射重新烧录后验收通过：
  - 用户烧录 M33 `746e0ad4` 后，NanoPi `can0` 仍为 `ERROR-ACTIVE`，1Mbps，tx/rx error `0/0`。
  - 只读抓包 3 秒得到 140 条合法 M33 电机遥测帧：`0x330..0x334` 各 28 条，全部 byte0=`B3`，byte3=`0x10` stale/no-feedback，未出现 `0x320`。
  - 原始帧确认正式映射正确：`0x330` byte2=`03`、`0x331` byte2=`04`、`0x332` byte2=`05`、`0x333` byte2=`06`、`0x334` byte2=`07`。
  - NanoPi bridge 只读模式验证 `/rehab_arm/motor_state` 输出 5 个电机：`shoulder_lift_joint=3`、`elbow_lift_joint=4`、`shoulder_abduction_joint=5`、`upper_arm_rotation_joint=6`、`forearm_rotation_joint=7`，全部 `stale=true/data_fresh=false`。
  - `/joint_states` 未收到 stale 样本，符合“缺新鲜反馈不污染仿真姿态”的设计。
  - 下一步：让 M33/电机侧产生新鲜反馈，期望对应 stale 位清零后 `/joint_states` 开始发布真实姿态，再接仿真主机/RViz/平台显示。

- M33 新鲜电机反馈源检查：
  - 被动抓包 3 秒只看到 M33 `0x330..0x334` stale 遥测，各 28 条；没有 3 号 `0x061/0x069`，也没有 7 号 `0x180007FD/0x188007FD`。
  - 通过 M33 telemetry-only active-report 入口发送 `0x320#060401` 打开 ROS joint4/motor7 上报，随后抓包 5 秒仍只看到 `0x330..0x334` stale 帧；关闭命令 `0x320#060400` 已发送。
  - 通过 NanoPi 直接 telemetry-only snapshot 临时打开 motor7 active-report 5 秒，也没有收到 `0x180007FD`；工具结束后已自动关闭。
  - M33 heartbeat/status 在线：`0x321#2A -> 0x322#A52A070001020100`。
  - 结论：当前不是 ROS parser 或 M33 `0x330` 映射问题，而是电机原始反馈源当前未出现在 CAN 总线上；需现场检查电机侧供电、驱动在线状态、CAN 分支/终端、或电机是否接受 active-report。
  - 安全：本轮没有发送位置、速度、力矩目标；只发送 telemetry-only active-report 开/关和 heartbeat。

- 灵足 4~7 非运动在线探测：
  - 通过 NanoPi `nanopi_can_master.py probe` 对 motor `7` 单独发送私有协议 Get_ID，抓包只看到 TX `0000FD07#0000000000000000` 和 M33 `0x330..0x334` stale 帧，没有任何 7 号回复。
  - 对 motor `4..7` 范围发送 Get_ID，现象相同：只有 TX 探测帧和 M33 stale 帧，没有 `0xFE` 类 Get_ID 回复，也没有 `0x18000xFD` active-report。
  - CAN 控制器仍健康：`ERROR-ACTIVE`，tx/rx error `0/0`，bus-errors/error-pass/bus-off 均为 `0`；M33 heartbeat 仍可回复 `0x322#A52B070001020100`。
  - 结论：NanoPi/M33/CAN 控制器链路健康，但灵足 4~7 当前整体没有在总线上响应；下一步应现场检查电机侧供电、驱动使能、CAN 支路/接口、终端和节点 ID。
  - 安全：Get_ID 是非运动探测；本轮没有发送 enable、mode、position、velocity、torque 或 stop 以外的控制命令。

### 2026-05-26

- M33 formal clinical gate scaffold:
  - M33 新增 `CONTROL_CLINICAL_MOTION_ENABLE`，默认 `0U`；bench motion 和 clinical motion 不能同时开启，避免台架状态混成正式穿戴状态。
  - M33 heartbeat `0x322` 现在通过统一状态填充函数处理：bench build 输出 `bench_armed`；clinical build 只有 pre-arm ready 才输出正式 `armed`，否则输出 `prearm_not_ready`。
  - NanoPi parser 增加 detail code `12 -> prearm_not_ready`。
  - 验证：NanoPi 侧 `test_psoc_status.py`、`test_safety_gate.py`、`test_m33_ros_contract.py`、`test_candump_motor_telemetry.py` 共 33 tests passed；M33 `git diff --check` 通过。
  - 未验证：M33 本地 `python -m SCons -j4` 仍失败，原因是工具链路径 `C:\Users\XXYYZZ` 不存在；需要用户在 RT-Thread Studio 里编译烧录。

- NanoPi bench_armed parser and live gate validation:
  - Synced `psoc_status.py` and `test_psoc_status.py` to NanoPi, rebuilt `rehab_arm_psoc_bridge`, and confirmed `0x322#A55B070000060000` parses as `control_mode=bench_armed` with `motion_allowed=false`.
  - Ran ROS bridge with `enable_target_tx=true` and published a legal one-joint trajectory. Bridge rejected it with `PSoC motion_allowed is not true, protocol_version=2, state=ok, control_mode=bench_armed, detail=none`.
  - Verified `candump can0,320:7FF` captured `0` lines and `can0` stayed `ERROR-ACTIVE`, tx/rx error counter `0/0`.
  - Note: this NanoPi workspace currently exposes the executable as `psoc_can_bridge_node.py`; using `psoc_can_bridge_node` prints `No executable found`.

- M33 bench/clinical 安全语义收敛：
  - M33 改为在 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` 且 detail 为 none 时，上报 `control_mode=bench_armed`，不再伪装成正式 `armed`。
  - NanoPi `psoc_status.py` 增加 `bench_armed` 枚举，但默认仍解析为 `motion_allowed=false`；正式运动候选许可只保留 `armed/active + detail=none + error_code=0`。
  - 验证：NanoPi 侧 `test_psoc_status.py`、`test_safety_gate.py`、`test_m33_ros_contract.py`、`test_candump_motor_telemetry.py` 共 33 tests passed；M33 `git diff --check` 通过。
  - 未验证：M33 本地 `python -m SCons -j4` 仍失败，原因是 `rtconfig.py` 中工具链路径 `C:\Users\XXYYZZ` 不存在；需要用户用 RT-Thread Studio 或正确工具链编译烧录。
  - 下一步：烧录后只测 `0x321 -> 0x322`，期望看到 byte5=`0x06`，NanoPi 解析为 `control_mode=bench_armed` 且 `motion_allowed=false`。

- NanoPi 真 CAN 只读验收：
  - NanoPi 在线，`can0` 为 `ERROR-ACTIVE`，1Mbps，tx/rx error counter `0/0`。
  - 被动抓包 5 秒只看到 M33 `0x332`，说明电机遥测在发；随后只发送一次 heartbeat `0x321#01` 触发 `0x322`，全程没有 `0x320`。
  - 抓包统计：`0x321=1`、`0x322=1`、`0x332=39`；转换 JSONL 后 `safety_state_count=1`、`m33_motor_status_count=39`、`motor_state_count=39`、`joint_state_count=39`。
  - 安全发现：`0x322#A501070000030000` 解析为 `state=ok/control_mode=armed/detail=none/motion_allowed=true`，说明当前 M33 固件处在开发台架放行状态，不是 logging-only/limited。
  - 复查：没有 `psoc_can_bridge/ros2/nanopi_can_master` 进程在跑；再次监听 `0x320` 为空；`can0` 仍 `ERROR-ACTIVE`。
  - 下一步：不要直接进入轨迹运动；先把 M33 开发台架 armed 状态和正式安全条件区分清楚，必要时让 M33 默认回到 `limited/logging_only` 或增加更明确的 bench/clinical mode 字段。

- candump 真 CAN 离线验收工具补齐安全状态：
  - `candump_motor_telemetry.py` 现在解析 M33 `0x322` 并输出 `/rehab_arm/safety_state` JSONL 记录。
  - summary 新增 `safety_state_count` 和 `motion_allowed_counts`，方便上电后确认状态链路可见且调试阶段没有误报运动许可。
  - 保持原有 `0x330~0x337 -> /rehab_arm/motor_state + /joint_states` 行为不变。
  - 验证：`python -m unittest test_candump_motor_telemetry.py test_m33_ros_contract.py test_data_recording.py`，61 tests passed；`py_compile candump_motor_telemetry.py` 通过。
  - 下一步：有电时抓一段只读 candump，转换 JSONL 并检查 `safety_state_count > 0`、`motion_allowed_counts.true == 0`、`m33_motor_status_count/joint_state_count > 0`。

- M33 安全状态和 ROS topic 组合合同：
  - 新增 `m33_ros_contract.py`，可离线把 M33 `0x322` 安全状态和 `0x330~0x337` 电机遥测组合成 `/rehab_arm/safety_state`、`/rehab_arm/motor_state`、`/joint_states` 记录。
  - 新增 `test_m33_ros_contract.py`，覆盖 limited/logging-only 有遥测但不允许运动、ok/armed/none 才允许运动候选、坏电机帧不生成假 joint state。
  - 决策：电机遥测只能更新状态和当前姿态，不能提升运动权限；运动候选许可只来自 M33 `0x322 motion_allowed=true`。
  - 验证：`python -m unittest test_m33_ros_contract.py test_psoc_status.py test_psoc_motor_status.py test_safety_gate.py`，29 tests passed。
  - 下一步：把这个合同用于 NanoPi 真 CAN 状态采集验收，再继续接 MuJoCo/数据采集主线。

- 机械臂主线优先，App/平台只预留双监控和双控制边界：
  - 决策：当前阶段先把 `JointTrajectory -> NanoPi -> M33 -> 电机`、安全状态机、限位限速和真实电机反馈打稳；平台患者总览、远程总控台等页面暂缓。
  - App BLE 定位为近端训练交互和安全请求入口，可发开始、暂停、停止、急停请求、模式切换、疼痛/疲劳反馈，但不能直接发 CAN 或绕过 M33。
  - 平台/服务器定位为远端监控、profile draft/review、训练计划、数据采集/标注和高层任务入口，不能做实时闭环底层控制。
  - NanoPi 转发标准 ROS 轨迹和已审核 profile 安全子集；M33 对 App、平台、NanoPi、VLA 的所有请求做最终安全裁决。
  - 文档更新：`docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` 和 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
  - 下一步：继续机械臂主线，优先确认电机绝对角度、M33 ±60° 软件限位、速度/电流限制和状态回报，再接仿真/数据采集。

- M33 零点职责收敛：
  - 决策：若电机官方协议角度已经是可信输出侧绝对角度，M33 不维护零点标注；机械零点、患者 ROM、限速和训练模式由上位机/平台/App 写入统一 Patient Device Profile。
  - M33 只接收安全子集，并负责限位、限速、限流、急停、故障和通信超时的最终裁决。
  - 已撤掉 M33 本轮新增的 RAM session zero 口，诊断日志也不再输出 `zero_source/zero_policy`。
  - 文档更新：`docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` 和 `docs/USER_MANUAL.md`。
  - 验证：M33 代码静态 `git diff --check` 通过；本机无法完整编译 M33，原因是当前 shell 的 SCons/工具链配置不可用。
  - 下一步：继续把电机绝对角度、限位、限速和患者 profile 的数据流打通，平台患者总览等机械臂功能稳定后再加。

- M33 ROS joint 到真实电机映射修正：
  - 现场验证：通过 M33 路径发送 `0x320#03072C0103000000`，CAN 上能看到命令，但 7 号没有动，`0x180007FD` 和 M33 `0x336` 状态没有变化。
  - 对照验证：直接 `nanopi_can_master.py private speed --motor 7 --vel 0.30 --kd 1.0` 后，7 号原始反馈从 `CF93...` 变化到 `D7C1...`，M33 `0x336` 也变化，说明 7 号电机和私有协议路径可用。
  - 根因定位：M33 当前把 ROS joint id 按 `ros_joint + 1` 映射到 motor slot，导致 ROS 5 关节 `0..4` 实际打到 motor slot `1..5`，没有覆盖真实电机 `3..7`。
  - 已改 M33 本地工程：ROS joint `0..4` 映射为 motor slot `3/4/5/6/7`。后续正规链路测试 7 号应发送 ROS joint id `4`，不是 `7`。
- 验证：
  - 本轮真机 CAN：NanoPi `can0` 为 `ERROR-ACTIVE`，M33 `0x322` 在线。
  - 7 号直驱对照脉冲可动，已 stop 并关闭 active-report。
  - M33 代码未能在当前 PowerShell 编译，原因仍是 `arm-none-eabi-gcc` 不在 PATH。
- 下一步：
  - 用户用 RT-Thread Studio 编译并烧录 M33。
  - 烧录后发送 `m33 target --joint 4 --deg 30 --rpm 3 --torque-ma 0` 验证 7 号正规路径。
- 烧录后复测：
  - `m33 target --joint 4 --deg 30 --rpm 3 --torque-ma 0` 已发送 `0x320#03042C0103000000`。
  - 全量 CAN 抓包确认 M33 输出到 motor7：`0x0300FD07#0000000000000000` 和 `0x01800007#855481370F5C3333`。
  - 说明 ROS joint4 -> motor slot 7 的映射已生效。
  - 用户现场反馈发生剧烈转动。已立即发送 M33 stop、private stop 3/4/5/6/7、关闭 active-report，并将 3 号 CANSimple 置零速/idle。
  - 安全修正：M33 默认 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE` 改回 `0`，未标定前禁止 ROS `0x320` 位置目标继续输出到电机。
  - 当前下一步改为离线/低风险标定 motor7 的零点、方向、绝对位置参考和 MIT 位置控制参数，再考虑恢复受控输出。

- M33 电机元数据对齐：
  - 更新本地 M33 工程 `applications/control/control_layer_cfg.h`。
  - joint3 配置为伺泰威 CANSimple/ODrive-like，减速比 `48:1`。
  - joint4/5 配置为灵足 RS00，减速比 `10:1`。
  - joint6/7 配置为灵足 EL05，减速比 `9:1`。
  - 只改配置和注释，没有新增运动行为、没有新增周期打印。
- 验证：
  - `mingw32-make -j4` 能进入 IDE 生成的 Debug 构建入口，但判断目标已是最新。
  - 强制重编 `applications/control/control_layer.o` 时失败，原因是当前 PowerShell PATH 找不到 `arm-none-eabi-gcc`，不是代码语法错误输出。
  - 文本检查确认 M33 配置中的型号和减速比已写入。
  - 尝试并行运行主仓库单元测试和 `git status` 时本机返回 `Out of memory`，本轮不把单元测试记为通过。
- 未验证：
  - 未烧录 M33。
  - 未做真机运动。
  - 未验证 joint3 伺泰威真实运动。
- 下一步：
  - 让 RT-Thread Studio 或正确 PATH 的 ARM 工具链重编 M33。
  - 烧录后只做非运动状态检查，再验证 M33 侧 joint/output 到 motor-side 的角度换算和安全限位拒绝逻辑。

### 2026-05-25

- 对接平台 URDF 模型预览：
  - 明确 `rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf` 可直接导入平台 `模型预览` tab。
  - 当前 URDF 使用内置 `box/cylinder` 几何体，无外部 mesh 依赖，适合浏览器 three.js + urdf-loader 第一版预览。
  - 记录后续带 mesh/xacro 的处理边界：先展开 URDF，处理 `package://` 路径，保持 joint 名称和 `/joint_states` 一致。
  - 仍明确模型预览只读，不代表运动许可。
- 文档更新：
  - `docs/INTEGRATION_GUIDE.md` 新增 URDF 与平台模型预览对接说明。
  - `docs/USER_MANUAL.md` 新增平台导入 URDF 的用户操作步骤和通过标准。

- 对接 AI 合作平台的通用设备数据质量索引：
  - `manifest_with_summary.json` 上传后，平台侧映射为 `device_recording_quality_index_v1`。
  - 该索引只用于标注、导出、图表实验和数据资产审查，不代表运动许可。
  - 康复机械臂保持为平台设备数据工作台的一个适配来源，平台核心不写死为医疗或机械臂专用。
- 文档更新：
  - `docs/INTEGRATION_GUIDE.md` 补充平台质量索引边界。
  - `docs/USER_MANUAL.md` 补充上传 `manifest_with_summary.json` 的推荐流程和安全说明。
- 验证：
  - 平台后端 `python -m pytest tests/test_rehab_arm_sync.py -q` 通过，3 tests passed。
  - 本轮只更新文档和平台后端接口说明，没有运行硬件、CAN、NanoPi 或电机测试。

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
- 用户烧录 M33 logging-only 固件后完成 NanoPi 侧 `0x320` 单帧发送：
  - 用户确认电机驱动电源断开。
  - 先复测 heartbeat，`0x321 seq=3` 收到 `0x322`：
    - `RX STD 0x00000322 [8] A5 03 07 00 62 8A 00 00`
  - `can0` 为 `UP`、`LOWER_UP`、`ERROR-ACTIVE`、1Mbps，错误计数器 `tx 0 rx 0`。
  - 临时运行 bridge：`enable_target_tx:=true`。
  - 发布单关节轨迹 `shoulder_lift_joint=0.1 rad`。
  - NanoPi 日志显示：
    - `TX 320 0300390005000000`
  - `candump can0,320:7FF` 捕获：
    - `can0  320   [8]  03 00 39 00 05 00 00 00`
  - 本轮只完成 NanoPi/CAN 侧单帧发送确认；M33 串口日志待用户反馈。
- 尝试从 NanoPi 查看 M33 串口日志：
  - NanoPi 未发现 `/dev/ttyUSB*`、`/dev/ttyACM*` 或 `/dev/serial/by-id/*`。
  - 未发现 `minicom/picocom/screen` 等串口查看进程。
  - 结论：M33 串口日志当前不在 NanoPi 上，应该在用户烧录/调试用电脑或调试器连接的串口上查看。
  - 复测 CAN heartbeat 正常：
    - `TX STD 0x00000321 [1] 04`
    - `RX STD 0x00000322 [8] A5 04 07 00 F6 E7 04 00`
  - 当前 `can0` 仍为 `UP`、`LOWER_UP`、`ERROR-ACTIVE`、1Mbps，错误计数器 `tx 0 rx 0`。
- 从本机 Windows `KitProg3 USB-UART (COM26)` 读取到 M33 串口日志：
  - 打开 COM26，115200 baud，DTR/RTS 关闭。
  - 再次由 NanoPi 发送单帧 `0x320`：`0300390005000000`。
  - M33 串口输出：
    - `[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22`
  - 结论：M33 已收到 `0x320`，但当前固件日志不是 logging-only 对照格式，而且字样显示可能进入了 `direct apply` 控制应用路径。
  - 已立即停止继续发送 `0x320`；电机驱动继续保持断电。
  - 单帧后复测 heartbeat 正常：
    - `TX STD 0x00000321 [1] 05`
    - `RX STD 0x00000322 [8] A5 05 07 00 FC FA 07 00`
  - 当前 `can0` 仍为 `ERROR-ACTIVE`，错误计数器 `tx 0 rx 0`。
- 无现场硬件条件下补充 `0x320` 协议工具离线测试：
  - 新增 `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/test/test_psoc_payload_tools.py`。
  - 覆盖 `encode_psoc_cmd.py` 和 `decode_psoc_cmd.py` 的合法编码、解码、round-trip、超限拒绝、非有限数拒绝、未知关节拒绝、payload 长度错误和 unknown joint 可见性。
  - 本地验证命令：
    - `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v`
  - 结果：10 tests passed。

### 2026-05-25

- 更新 M33/M55/NanoPi/仿真主机/总服务器/VLA 的数据流架构：
  - 电机反馈和 C8T6 传感数据先进入 M33。
  - M33 将电机状态、传感特征和训练上下文给 M55。
  - M55 只输出意图、疲劳、辅助等级和异常建议，必须回到 M33 审核。
  - NanoPi 作为第一版全量数据主上传网关，汇总电机、传感、安全、模型结果和 session 数据后上传总服务器。
  - M55 WiFi 只作为可选低频摘要/语音/OpenClaw/诊断链路，不作为全量数据主链路。
  - VLA 数据来源明确为服务器历史数据、仿真主机视觉/状态、App 用户目标和 NanoPi 汇总机器人状态；VLA 只输出 `task_goal` 或规划约束。
- 新增数据流图文件：
  - `docs/assets/system_data_flow.mmd`
  - `docs/assets/system_data_flow.png`
- 更新文档：
  - `README.md`
  - `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`
  - `docs/USER_MANUAL.md`
  - `docs/TROUBLESHOOTING_AND_LESSONS.md`
- 已验证：
  - 本地打开 `docs/assets/system_data_flow.png`，确认图片非空、可读。
  - 本次只更新架构文档和图片，没有运行硬件、ROS、CAN 或电机测试。
- 根据用户偏好的白板式数据流图风格，重绘 `docs/assets/system_data_flow.png`：
  - 改为白底、轻边框、细曲线、少色彩的系统关系图。
  - 同步更新 `docs/assets/system_data_flow.mmd`，保持图片源说明与新版布局一致。
  - 已验证本地打开图片，确认没有空白或底部裁切。
- 按最新目标更新 VLA/感知链路：
  - 英飞凌 M55 增加语音采集、语音文本/音频摘要上传服务器。
  - NanoPi 增加摄像头采集，上传关键帧、目标/遮挡物摘要和机器人状态。
  - VLA 固定走服务器链路，用服务器汇聚视觉、语音、机器人状态和历史上下文。
  - VLA 支持复杂任务分解，例如“先移开遮挡物，再拿目标物品”。
  - 服务器下发到 NanoPi 的是分段任务或训练配置，不是底层 CAN/电机命令。
- 设备重新上电后完成 NanoPi/M33 非运动复测：
  - `192.168.2.66` 可 ping 通，NanoPi hostname 为 `wen`。
  - 初始 `can0` 存在但为 `DOWN/STOPPED`。
  - 使用 `sudo` 将 `can0` 配置为 classic CAN `1Mbps` 并拉起。
  - `can0` 进入 `UP/LOWER_UP/ERROR-ACTIVE`，错误计数器 `tx 0 rx 0`。
  - 手动发送 3 次 NanoPi heartbeat `0x321`，均收到 M33 `0x322`：
    - `RX 322 [8] a501070050300200`
    - `RX 322 [8] a502070017330200`
    - `RX 322 [8] a5030700de350200`
  - 运行 `rehab_arm_psoc_bridge` 默认 dry-run：`enable_target_tx:=false`。
  - 发布合法单关节轨迹 `shoulder_lift_joint=0.1 rad`，bridge 输出：
    - `safety ok: accepted 1 trajectory points`
    - `DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000`
  - 监听 `0x320` 的日志只有 `sniff 0x320 start/done`，未捕获真实 `0x320`。
  - 复测后 `can0` 仍为 `ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。
  - 本轮没有发送真实 `0x320`，没有做任何电机运动测试。
- 完成 M33 `0x320` logging-only 安全补丁本地实现和编译：
  - 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`。
  - 修改 `applications/control/control_layer_cfg.h`，新增 `CONTROL_ROS_COMMAND_LOGGING_ONLY`，默认 `1U`。
  - 修改 `applications/control/control_layer.c`，让 M33 收到并解析 `0x320` 后只记录 `s_last_ros_cmd`、打印 payload/字段、安全拒绝结果，然后立即返回。
  - logging-only 模式下不再调用 `ctrl_enqueue_ros_command()`，不再调用 `ctrl_apply_ros_command()`，因此不应再出现 `[control] ros cmd direct apply failed...`。
  - 日志格式目标：
    - `RX 320 dlc=8 data=0300390005000000`
    - `cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0`
    - `decision=reject reason=logging_only_no_motor_output safety_state=limited`
  - 本地编译命令通过：
    - `$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path; mingw32-make -C Debug all -j2`
  - 编译产物已生成在 M33 工程 `Debug/` 下：`rtthread.elf`、`rtthread.bin`、`rtthread.hex`。
  - 编译仍保留工程既有告警：`rtthread.elf has a LOAD segment with RWX permissions`，以及 post-build 中 `arm-none-eabi-objcopy: interleave must be positive` 被 makefile 标记为 ignored；本次新增代码没有导致编译失败。
- 用户烧录 M33 logging-only 固件后完成 ROS bridge 单帧 `0x320` 安全对照：
  - 先验证 `can0`：`UP/LOWER_UP/ERROR-ACTIVE`，1Mbps，`berr-counter tx 0 rx 0`。
  - 先发 3 次 NanoPi heartbeat `0x321`，均收到 M33 `0x322`：
    - `RX 322 [8] a50107005e9d0000`
    - `RX 322 [8] a5020700699d0000`
    - `RX 322 [8] a50307006a9d0000`
  - 开启 Windows 本机 `COM26`，115200 baud，DTR/RTS 关闭，监听 M33 串口。
  - 临时运行 ROS bridge：`enable_target_tx:=true`。
  - 发布一次合法单关节轨迹：`shoulder_lift_joint=0.1 rad`。
  - bridge 日志：
    - `safety ok: accepted 1 trajectory points`
    - `TX 320 0300390005000000`
  - `candump can0,320:7FF` 捕获：
    - `can0  320   [8]  03 00 39 00 05 00 00 00`
  - M33 串口日志符合 logging-only 预期：
    - `RX 320 dlc=8 data=0300390005000000`
    - `cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0`
    - `decision=reject reason=logging_only_no_motor_output safety_state=limited`
  - 没有再出现 `[control] ros cmd direct apply failed...`。
  - 复测 `can0` 仍为 `ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0；再次发送 `0x321 seq=9` 收到 `0x322`。
  - 本轮只验证 ROS/NanoPi/CAN/M33 接收和安全拒绝链路，没有给电机驱动上电，没有做运动测试。
- 完成 NanoPi bridge `0x322` V2 安全状态解析第一版：
  - 新增 `rehab_arm_psoc_bridge/psoc_status.py`，把 M33 status payload 解析拆成纯 Python 函数。
  - 新增 `test/test_psoc_status.py`，覆盖 V1 legacy 兼容、V2 limited/logging-only、emergency_stop、error_code 强制 fault、坏 marker、短帧。
  - 更新 `psoc_can_bridge_node.py`，`handle_psoc_status()` 统一调用 `parse_psoc_status_payload()`。
  - 更新 `docs/PSOC_CAN_PROTOCOL_V1.md`，定义 `0x322` V2 扩展字节：
    - byte4 `safety_state`
    - byte5 `control_mode`
    - byte6 `detail_code`
    - byte7 `heartbeat_age_100ms`
  - 本地验证：
    - `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v`
    - 16 tests passed。
    - `python -m py_compile ...psoc_status.py ...psoc_can_bridge_node.py` 通过。
  - NanoPi 验证：
    - 同步 `psoc_status.py`、`psoc_can_bridge_node.py`、`test_psoc_status.py` 到 `/home/pi/rehab_arm_ros2_ws`。
    - `colcon build --symlink-install --packages-select rehab_arm_psoc_bridge` 通过。
    - `python3 -m unittest discover -s src/rehab_arm_psoc_bridge/test -v` 在 NanoPi 上 6 tests passed。
    - 清理旧 bridge 进程后重新启动 bridge，旧 M33 `0x322` 被解析为 V1 legacy，topic 输出包含 `protocol_version:1`。
    - 本轮没有发布轨迹，没有发送真实 `0x320`，没有做电机运动测试。
  - 复查 `can0` 仍为 `UP/LOWER_UP/ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。
- 完成 M33 `0x322` V2 logging-only 状态上报补丁并本地编译：
  - 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`。
  - 修改 `applications/control/control_layer_cfg.h`，新增与 NanoPi `psoc_status.py` 对齐的 `0x322` V2 enum：
    - `CONTROL_STATUS_SAFETY_LIMITED = 1`
    - `CONTROL_STATUS_MODE_LOGGING_ONLY = 1`
    - `CONTROL_STATUS_DETAIL_LOGGING_ONLY = 10`
  - 修改 `applications/control/control_layer.c` 的 `ctrl_handle_nanopi_heartbeat()`：
    - `0x322` byte0..3 保持 `A5 seq motors error_code`。
    - logging-only 模式下 byte4..7 改为 `01 01 0A 00`。
    - 预期回复形如 `A5 <seq> 07 00 01 01 0A 00`。
  - 本地编译命令通过：
    - `$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path; mingw32-make -C Debug all -j2`
  - 编译产物已更新：
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin`
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex`
  - 本地用 NanoPi bridge 解析器验证示例 payload `A522070001010A00`：
    - `protocol_version=2`
    - `state=limited`
    - `control_mode=logging_only`
    - `detail=logging_only_no_motor_output`
  - 编译仍保留既有工程告警：`rtthread.elf has a LOAD segment with RWX permissions`，以及 post-build 中 `arm-none-eabi-objcopy: interleave must be positive` 被 makefile 标记为 ignored；本次修改没有导致编译失败。
  - 尚未烧录本轮 M33 V2 status 固件，等待用户烧录后只测 `0x321 -> 0x322`，不发 `0x320`。
- 用户烧录 M33 V2 status 固件后完成 NanoPi heartbeat/status 验证：
  - `can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`，1Mbps，`berr-counter tx 0 rx 0`。
  - 原始 SocketCAN 连续发送 `0x321` seq 1/2/3，均收到 V2 `0x322`：
    - `RX 322 [8] a501070001010a00`
    - `RX 322 [8] a502070001010a00`
    - `RX 322 [8] a503070001010a00`
  - 运行 `rehab_arm_psoc_bridge`，未发布任何轨迹，未发送 `0x320`。
  - `candump can0,321:7FF,322:7FF` 旁路确认 bridge heartbeat 触发 V2 status：
    - `can0  321   [1]  01`
    - `can0  322   [8]  A5 01 07 00 01 01 0A 00`
  - `/rehab_arm/safety_state` 完整 JSON：
    - `{"source":"psoc","id_hex":"0x322","data":"A503070001010A00","marker":165,"seq":3,"motors":7,"error_code":0,"protocol_version":2,"state":"limited","safety_code":1,"control_mode":"logging_only","control_mode_code":1,"detail_code":10,"detail":"logging_only_no_motor_output","heartbeat_age_ms":0}`
  - 复查 `can0` 仍为 `ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。
  - 本轮没有发布 `JointTrajectory`，没有发送真实 `0x320`，没有给电机驱动上电，没有做运动测试。
- 完成 M33 `0x320` logging-only 安全审核日志补丁并本地编译：
  - 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`。
  - 修改 `applications/control/control_layer_cfg.h`：
    - 新增 ROS 5 关节 0-based 审核限位，单位 `0.1 deg`，与 NanoPi bridge 当前软件限位对齐。
    - 新增 `CONTROL_ROS_MAX_TARGET_RPM=30`。
    - 新增 `CONTROL_ROS_MAX_TARGET_TORQUE_MA=0`。
    - 新增 `CONTROL_ROS_HEARTBEAT_TIMEOUT_MS=2500`。
  - 修改 `applications/control/control_layer.c`：
    - 记录最近一次 NanoPi heartbeat tick。
    - `0x320` logging-only 日志新增 `heartbeat_ok`、`heartbeat_age_ms`、`joint_known`、`limit_01deg`。
    - 新增 `target_in_limit`、`rpm_in_limit`、`torque_in_limit` 审核结果。
    - `decision` 仍固定为 `reject`，`final_reason=logging_only_no_motor_output`，不会进入电机控制路径。
  - 预期合法单帧 `0300390005000000` 的 M33 串口日志会包含：
    - `audit mode=logging_only heartbeat_ok=1 ... joint_known=1 limit_01deg=[-401,802]`
    - `audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0`
    - `decision=reject reason=logging_only_no_motor_output final_reason=logging_only_no_motor_output safety_state=limited`
  - 本地编译命令通过：
    - `$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path; mingw32-make -C Debug all -j2`
  - 编译产物已更新：
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin`
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex`
  - 编译仍保留既有工程告警：`rtthread.elf has a LOAD segment with RWX permissions`，以及 post-build 中 `arm-none-eabi-objcopy: interleave must be positive` 被 makefile 标记为 ignored；本次修改没有导致编译失败。
  - 尚未烧录本轮 M33 安全审核日志固件，等待用户烧录后只做单帧日志对照。
- 用户烧录 M33 安全审核日志固件后，开始做烧录后验证但被 NanoPi 网络阻塞：
  - Windows 本机能看到 M33 串口 `COM26 KitProg3 USB-UART`。
  - `ssh pi@192.168.2.66` 初始超时，后续不绑定源地址时连接被 `Meta` 虚拟网卡路由到 `198.18.0.1`，不能作为真实 NanoPi 连通性依据。
  - 强制从真实无线源地址 `192.168.2.9` 连接 `192.168.2.66` 仍超时。
  - `ping -S 192.168.2.9 192.168.2.66` 超时，ARP 中没有 `192.168.2.66`。
  - 当前没有登录 NanoPi，没有拉起/检查 `can0`，没有发送 `0x321`、没有发送 `0x320`、没有做任何电机运动测试。
  - 结论：M33 已烧录，但烧录后 CAN/ROS 验证需等 NanoPi 真实局域网 SSH 恢复后继续。
- NanoPi 上电后完成 M33 `0x320` 安全审核日志固件验证：
  - NanoPi 重新可通过真实局域网 SSH 登录，hostname 为 `NanoPi-M5`。
  - 初始 `can0` 为 `DOWN/STOPPED`；使用 `sudo` 配置 classic CAN `1Mbps` 并拉起。
  - `can0` 进入 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
  - 原始 SocketCAN 发送 `0x321` seq 1/2/3，均收到 M33 V2 `0x322`：
    - `a501070001010a00`
    - `a502070001010a00`
    - `a503070001010a00`
  - 临时运行 bridge：
    - `enable_target_tx:=true`
    - `require_psoc_ok_for_trajectory:=false`
    - 说明：M33 当前故意上报 `limited/logging_only`，因此只为单帧审计临时绕过 NanoPi 的 `ok` gate；M33 仍是最终拒绝方。
  - 发布一次合法单关节轨迹 `shoulder_lift_joint=0.1 rad`。
  - bridge 日志：
    - `safety ok: accepted 1 trajectory points`
    - `TX 320 0300390005000000`
  - `candump can0,320:7FF` 捕获：
    - `can0  320   [8]  03 00 39 00 05 00 00 00`
  - M33 `COM26` 串口日志：
    - `RX 320 dlc=8 data=0300390005000000`
    - `cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0`
    - `audit mode=logging_only heartbeat_ok=1 heartbeat_age_ms=141 heartbeat_timeout_ms=2500 joint_known=1 limit_01deg=[-401,802]`
    - `audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0`
    - `decision=reject reason=logging_only_no_motor_output final_reason=logging_only_no_motor_output safety_state=limited`
  - 复查 `can0` 仍为 `ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。
  - 本轮没有给电机驱动上电，没有做运动测试。
- 完成 M33 ROS 命令安全状态机第一版结构化改造并本地编译：
  - 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`。
  - 修改 `applications/control/control_layer.c`。
  - 新增内部状态/裁决/拒绝原因枚举：
    - `CONTROL_ROS_SAFETY_BOOT/LOGGING_ONLY/READY/RUNNING/LIMITED/EMERGENCY_STOP/FAULT`
    - `CONTROL_ROS_DECISION_REJECT/ACCEPT`
    - `CONTROL_ROS_REJECT_LOGGING_ONLY/HEARTBEAT_TIMEOUT/UNKNOWN_JOINT/POSITION_LIMIT/SPEED_LIMIT/TORQUE_LIMIT/UNSUPPORTED_CMD`
  - 新增 `control_ros_safety_assessment_t`，统一保存 heartbeat、joint、position、rpm、torque 检查结果。
  - 新增 `ctrl_assess_ros_command_safety()`，把原来散在日志里的检查收束成结构化安全评估。
  - `ctrl_log_ros_command_only()` 现在只打印评估结果，不再承担安全判断本身。
  - 当前仍保持 `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`，因此即使合法目标也会得到 `decision=reject` 和 `reason=logging_only_no_motor_output`，不会进入电机控制路径。
  - 新预期日志格式包含：
    - `safety_state=logging_only decision=reject reason=logging_only_no_motor_output`
    - `audit heartbeat_ok=... joint_known=... limit_01deg=[...]`
    - `audit target_in_limit=... rpm_in_limit=... torque_in_limit=...`
    - `final action=no_motor_output logging_only=1`
  - 本地编译命令通过：
    - `$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path; mingw32-make -C Debug all -j2`
  - 编译产物已更新：
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin`
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex`
  - 编译仍保留既有工程告警：`rtthread.elf has a LOAD segment with RWX permissions`，以及 post-build 中 `arm-none-eabi-objcopy: interleave must be positive` 被 makefile 标记为 ignored；本次修改没有导致编译失败。
  - 尚未烧录本轮安全状态机结构化固件，等待用户烧录后只做 heartbeat/status 和一帧 `0x320` 日志对照。
- 用户烧录 M33 安全状态机结构化固件后完成非运动复测：
  - NanoPi `can0` 仍为 `UP/LOWER_UP/ERROR-ACTIVE`，classic CAN `1Mbps`，`berr-counter tx 0 rx 0`。
  - 原始 SocketCAN 发送 `0x321` seq 1/2/3，均收到 M33 V2 `0x322`：
    - `a501070001010a00`
    - `a502070001010a00`
    - `a503070001010a00`
  - 临时运行 bridge：
    - `enable_target_tx:=true`
    - `require_psoc_ok_for_trajectory:=false`
    - 说明：只为验证 M33 logging-only 状态机单帧审计，正式运动配置禁止这样绕过 NanoPi `ok` gate。
  - 发布一次合法单关节轨迹 `shoulder_lift_joint=0.1 rad`。
  - bridge 日志：
    - `safety ok: accepted 1 trajectory points`
    - `TX 320 0300390005000000`
  - `candump can0,320:7FF` 捕获：
    - `can0  320   [8]  03 00 39 00 05 00 00 00`
  - M33 `COM26` 串口日志已出现结构化状态机格式：
    - `safety_state=logging_only decision=reject reason=logging_only_no_motor_output`
    - `audit heartbeat_ok=1 heartbeat_age_ms=141 heartbeat_timeout_ms=2500 joint_known=1 limit_01deg=[-401,802]`
    - `audit target_in_limit=1 rpm_in_limit=1 torque_in_limit=1 max_rpm=30 max_torque_ma=0`
    - `final action=no_motor_output logging_only=1`
  - 复查 `can0` 仍为 `ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。
  - 本轮没有给电机驱动上电，没有做运动测试。
- 完成 M33 状态机拒绝用例矩阵第一轮验证：
  - 本轮绕过 ROS bridge 的前置限位，使用 NanoPi raw SocketCAN 直接发送 `0x320` 单帧，以验证 M33 自己的安全状态机。
  - 测试前后 `can0` 均为 `UP/LOWER_UP/ERROR-ACTIVE`，classic CAN `1Mbps`，`berr-counter tx 0 rx 0`。
  - 每个危险用例前先发送 `0x321` heartbeat 并收到 V2 `0x322 limited/logging_only`；heartbeat 超时用例等待 3.2 秒后再发 `0x320`。
  - 超限 position：
    - TX `0300840305000000`，含 `joint_id=0`、`deg_x10=900`，超过 `[-401,802]`。
    - M33：`safety_state=limited decision=reject reason=target_out_of_limit`。
  - 未知 joint：
    - TX `0309390005000000`，含 `joint_id=9`。
    - M33：`safety_state=limited decision=reject reason=unknown_joint`。
  - 非零 torque/current：
    - TX `0300390005000100`，含 `torque_ma=1`，超过当前 `max_torque_ma=0`。
    - M33：`safety_state=limited decision=reject reason=torque_out_of_limit`。
  - heartbeat 超时：
    - 等待后 TX `0300390005000000`。
    - M33：`safety_state=limited decision=reject reason=heartbeat_timeout`，`heartbeat_age_ms=3211`，超过 `2500`。
  - 四个用例最终都打印 `final action=no_motor_output logging_only=1`。
  - 本轮没有给电机驱动上电，没有做运动测试。
- 完成 M33 状态机拒绝用例矩阵第二轮验证：
  - 本轮继续绕过 ROS bridge，使用 NanoPi raw SocketCAN 单帧测试 M33 本体状态机。
  - 测试前后 `can0` 均为 `UP/LOWER_UP/ERROR-ACTIVE`，classic CAN `1Mbps`，`berr-counter tx 0 rx 0`。
  - 速度超限：
    - TX `030039001f000000`，含 `rpm=31`，超过当前 `max_rpm=30`。
    - M33：`safety_state=limited decision=reject reason=velocity_out_of_limit`。
  - unsupported command：
    - TX `0100`，即 `cmd=enable`，当前安全状态机只允许审计 `set_target`。
    - M33：`safety_state=limited decision=reject reason=unsupported_command`。
  - 多错误优先级：
    - 停发 heartbeat 等待 3.2 秒后，TX `030084031f000100`，同时包含 heartbeat 超时、position 超限、velocity 超限、torque 超限。
    - M33：`safety_state=limited decision=reject reason=heartbeat_timeout`。
    - 日志显示 `target_in_limit=0 rpm_in_limit=0 torque_in_limit=0`，但首要拒绝原因仍优先为 heartbeat。
  - 三个用例最终都打印 `final action=no_motor_output logging_only=1`。
  - 本轮没有给电机驱动上电，没有做运动测试。
- 完成 M33 safety reason -> `0x322 detail_code` 第一版实现并本地编译：
  - M33 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`。
  - 修改 `applications/control/control_layer_cfg.h`：
    - 新增 `CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT=1`
    - 新增 `CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND=2`
    - 新增 `CONTROL_STATUS_DETAIL_UNKNOWN_JOINT=3`
    - 新增 `CONTROL_STATUS_DETAIL_TARGET_OUT_OF_LIMIT=4`
    - 新增 `CONTROL_STATUS_DETAIL_VELOCITY_OUT_OF_LIMIT=5`
    - 新增 `CONTROL_STATUS_DETAIL_TORQUE_OUT_OF_LIMIT=6`
    - 保留 `CONTROL_STATUS_DETAIL_LOGGING_ONLY=10`
  - 修改 `applications/control/control_layer.c`：
    - 新增最近一次 ROS safety assessment detail 记录。
    - `ctrl_ros_reject_reason_detail_code()` 将 M33 `reason` 映射成 `0x322` byte6。
    - `ctrl_handle_nanopi_heartbeat()` 在 logging-only 模式下不再固定发送 `detail=10`，而是发送最近一次安全评估 detail。
  - M33 本地编译通过，产物已更新：
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin`
    - `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex`
  - 编译仍保留既有工程告警：`CANFD0_IRQ_cfg defined but not used`、`rtthread.elf has a LOAD segment with RWX permissions`，以及 post-build 中 `arm-none-eabi-objcopy: interleave must be positive` 被 makefile 标记为 ignored；本次修改没有导致编译失败。
- 完成 NanoPi ROS parser 对新 detail_code 的解析：
  - 修改 `rehab_arm_psoc_bridge/psoc_status.py`：
    - code `2` 解析为 `unsupported_command`
    - code `3` 解析为 `unknown_joint`
  - 修改 `test_psoc_status.py`，新增 `test_status_v2_reject_reason_detail_codes`，覆盖 code `1..6`。
  - 更新 `docs/PSOC_CAN_PROTOCOL_V1.md`，说明 M33 会把最近一次 ROS safety assessment 的首要拒绝原因放入 `0x322` byte6。
  - 本地测试通过：
    - `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v`
    - 17 tests passed。
  - NanoPi 同步并验证：
    - 同步 `psoc_status.py` 和 `test_psoc_status.py` 到 `/home/pi/rehab_arm_ros2_ws`。
    - `python3 -m unittest discover -s src/rehab_arm_psoc_bridge/test -v`
    - 7 tests passed。
- 用户烧录 M33 detail_code 固件后尝试非运动验证，但 M33 未在线：
  - NanoPi 在线，`can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`，classic CAN `1Mbps`，`berr-counter tx 0 rx 0`。
  - 发送 `0x321` heartbeat seq 1/2/3，均未收到 `0x322`。
  - 发送超限 `0x320` payload `0300840305000000` 后再发 `0x321`，仍未收到 `0x322`。
  - `candump` 能看到 NanoPi 发出的 `0x321` 和 `0x320`，但没有 M33 `0x322`。
  - Windows `COM26` 无 M33 串口输出，发送换行也无 shell/日志响应。
  - 结论：本轮尚未验证 `0x322` detail 动态变化；当前阻塞是 M33 应用未运行、未复位到应用、烧录镜像/启动配置不对，或板子相关供电/复位状态异常。
  - 本轮没有给电机驱动上电，没有做运动测试。
- M33 恢复在线后完成 `0x322 detail_code` 动态变化非运动验证：
  - 初始 heartbeat：
    - `TX heartbeat_71 321 [1] 71`
    - `RX 322 [8] a571070001010a00`
    - NanoPi parser 解析为 `detail_code=10`、`detail=logging_only_no_motor_output`。
  - 发送超限 `0x320`：
    - `TX target_out_of_limit 320 [8] 0300840305000000`
  - 下一次 heartbeat：
    - `TX heartbeat_72 321 [1] 72`
    - `RX 322 [8] a572070001010400`
    - NanoPi parser 解析为 `detail_code=4`、`detail=target_out_of_limit`。
  - `candump` 与 M33 `COM26` 串口日志一致：
    - `can0  322   [8]  A5 72 07 00 01 01 04 00`
    - M33 日志包含 `safety_state=limited decision=reject reason=target_out_of_limit`。
    - M33 日志最终仍为 `final action=no_motor_output logging_only=1`。
  - `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
  - 本轮没有给电机驱动上电，没有做运动测试。
- 完成第二个 `0x322 detail_code` 抽样验证：`torque_out_of_limit`。
  - 发送前 heartbeat：
    - `TX heartbeat_81 321 [1] 81`
    - `RX 322 [8] a581070001010400`
    - NanoPi parser 解析为 `detail_code=4`、`detail=target_out_of_limit`，说明 M33 仍保留上一条拒绝原因。
  - 发送 torque 超限 `0x320`：
    - `TX torque_out_of_limit 320 [8] 0300390005000100`
  - 下一次 heartbeat：
    - `TX heartbeat_82 321 [1] 82`
    - `RX 322 [8] a582070001010600`
    - NanoPi parser 解析为 `detail_code=6`、`detail=torque_out_of_limit`。
  - `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`，`bus-off/error-pass` 均为 0。
  - 本轮只验证 NanoPi/M33 CAN 状态回报；未查看 COM26 实时串口，未给电机驱动上电，未做运动测试。
- 完成第三个 `0x322 detail_code` 抽样验证：`heartbeat_timeout`。
  - 发送前 heartbeat：
    - `TX heartbeat_91 321 [1] 91`
    - `RX 322 [8] a591070001010600`
    - NanoPi parser 解析为 `detail_code=6`、`detail=torque_out_of_limit`，说明 M33 仍保留上一条拒绝原因。
  - 等待 `3.2s` 超过 M33 heartbeat 超时窗口后，发送普通目标 `0x320`：
    - `TX after_timeout_normal_target 320 [8] 0300390005000000`
  - 下一次 heartbeat：
    - `TX heartbeat_92 321 [1] 92`
    - `RX 322 [8] a592070001010100`
    - NanoPi parser 解析为 `detail_code=1`、`detail=heartbeat_timeout`。
  - 这证明 heartbeat 超时会覆盖普通目标的安全评估结果，并通过 `0x322` 回传到 NanoPi。
  - `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`，`bus-off/error-pass` 均为 0。
  - 本轮只验证 NanoPi/M33 CAN 状态回报；未查看 COM26 实时串口，未给电机驱动上电，未做运动测试。
- 明确 `0x322 detail_code` 的协议语义，并增强 NanoPi parser 输出：
  - 更新 `rehab_arm_psoc_bridge/psoc_status.py`：
    - 保留兼容字段 `detail_code` 和 `detail`。
    - 新增 `detail_semantics="last_safety_assessment"`。
    - 新增 `last_assessment_detail_code`。
    - 新增 `last_assessment_detail`。
  - 更新 `test_psoc_status.py`，覆盖新增字段。
  - 更新 `docs/PSOC_CAN_PROTOCOL_V1.md`，明确 V2 byte6 当前表示“最近一次安全评估详情”，不会随普通 heartbeat 自动清零。
  - 本地测试通过：
    - `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v`
    - 17 tests passed。
  - NanoPi 同步并验证：
    - 同步 `psoc_status.py` 和 `test_psoc_status.py` 到 `/home/pi/rehab_arm_ros2_ws`。
    - `python3 -m unittest discover -s src/rehab_arm_psoc_bridge/test -v`
    - 7 tests passed。
    - 真实 `0x322` 解析包含 `detail_semantics=last_safety_assessment`、`last_assessment_detail=heartbeat_timeout`。
- 统一 `/rehab_arm/safety_state` 上层消费字段：
  - PSoC/M33 status 和 bridge 本地 safety 都输出 `motion_allowed`。
  - 当前 logging-only 和 bridge 本地状态均为 `motion_allowed=false`。
  - 本地测试通过：19 tests passed；NanoPi 测试通过：9 tests passed。
- 新增 NanoPi 最小数据记录节点：
  - 记录 `/rehab_arm/safety_state` 和 `/rehab_arm/sensor_state` 到 JSONL。
  - 本地测试通过：24 tests passed；NanoPi 测试通过：14 tests passed；NanoPi build passed。
  - `ros2 pkg executables rehab_arm_psoc_bridge` 已能看到 `data_recorder_node.py`。
- 数据记录新增 session metadata：
  - JSONL 第一行写入设备、机器人、软件版本、运行模式和数据源 topic。
  - 本地测试通过：25 tests passed；NanoPi build passed。
  - NanoPi 实测 JSONL 第一行为 `record_type=session_metadata`。
- 数据记录新增 `/joint_states`：
  - JSONL 记录 `name/position/velocity/effort/stamp`。
  - 本地测试通过：27 tests passed；NanoPi build passed。
  - NanoPi 实测 JSONL 包含 `/joint_states` topic message。
- 新增 JSONL 检查工具：
  - 校验 `session_metadata` 和必需 topic。
  - 本地测试通过：30 tests passed；NanoPi build passed。
  - NanoPi 实测完整文件 PASS，不完整文件 FAIL。
- 新增数据采集 launch：
  - `data_collection.launch.py` 启动 `data_recorder_node.py`。
  - NanoPi build passed；10 秒短运行可写出 `session_metadata`。
- 规范数据文件命名和同步字段：
  - 默认文件名为 `<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl`。
  - metadata 包含 `schema_version`、`source`、`sync_status=local_only`。
  - 本地测试通过：32 tests passed；NanoPi build passed。
- 新增本地 manifest 工具：
  - 扫描 JSONL 并输出 `rehab_arm_manifest_v1` 清单。
  - 本地测试通过：33 tests passed；NanoPi build passed。
  - NanoPi 实测可标记不完整 session 为 `ok=false`。
- 新增服务器同步 API 草案：
  - 文档：`docs/SERVER_SYNC_API_DRAFT.md`。
  - 只定义非实时 manifest/JSONL 上传边界。
- 新增服务器同步 dry-run 工具：
  - `sync_dry_run.py` 读取 `rehab_arm_manifest_v1`，只打印计划请求，不联网。
  - 本地测试通过：36 tests passed。
  - NanoPi 测试通过：26 tests passed；`colcon build` passed；`ros2 pkg executables` 能看到 `sync_dry_run.py`。
  - NanoPi 实测 dry-run 输出 4 个计划请求：设备注册、manifest、文件上传、sync-status。
- 新增服务器同步 upload 入口：
  - `sync_upload.py` 默认等同 dry-run，不加 `--execute` 不联网。
  - `--execute` 才按 API 草案发送 JSON 和 multipart HTTP 请求。
  - 本地测试通过：40 tests passed。
  - NanoPi 测试通过：30 tests passed；`colcon build` passed；`ros2 pkg executables` 能看到 `sync_upload.py`。
- 新增本地同步测试服务器：
  - `sync_test_server.py` 接收 POST，保存 request log 和原始 body。
  - 本地测试通过：41 tests passed。
  - NanoPi 测试通过：31 tests passed；`colcon build` passed；`ros2 pkg executables` 能看到 `sync_test_server.py`。
  - NanoPi 命令行实测 `sync_upload.py --execute` 对本地假服务器完成 4 个 POST。
- 初步打通 AI 合作平台云端同步：
  - AI 合作平台本地工程：`D:\ai合作产品`。
  - AI 平台提交：`e5eef01e Add rehab arm sync ingestion API`。
  - 云端 API：`http://106.55.62.122:8011/api/rehab-arm/v1`。
  - 云端验证：`sync_upload.py --execute` 完成 4 个 POST，服务器落盘 `apps/api/tmp/rehab_arm_sync/events.jsonl`。
- 新增总控台预备数据 topic：
  - `data_recorder_node.py` 可选记录 `/rehab_arm/motor_state` 和 `/rehab_arm/camera_keyframe`。
  - `data_recording.py` 新增 `rehab_arm_motor_state_v1` 和 `rehab_arm_camera_keyframe_v1` payload helper。
  - 本地测试通过：43 tests passed。
  - NanoPi 测试通过：33 tests passed；`colcon build` passed。
  - NanoPi 实测 JSONL 能写入 motor_state 和 camera_keyframe。
- 新增 NanoPi 摄像头关键帧节点：
  - `camera_keyframe_node.py` 使用 `ffmpeg` 从 V4L2 设备抓取并压缩 JPEG。
  - 发布 `/rehab_arm/camera_keyframe`，供 recorder、总控台和 VLA 数据链路使用。
  - 本地测试通过：45 tests passed。
  - NanoPi 测试通过：35 tests passed；`colcon build` passed；`ros2 pkg executables` 能看到 `camera_keyframe_node.py`。
  - 当前硬件未采到图：`lsusb` 只看到 root hub；`/dev/video0` 报 `No such device`；`/dev/video22` 报 `Not a video capture device`。
- 新增 `/joint_states -> /rehab_arm/motor_state` 仿真遥测桥：
  - 新增 `joint_state_motor_state_node.py`。
  - `data_recording.py` 新增 `make_motor_entries_from_joint_state()`。
  - 作用是让 MuJoCo/假关节状态先生成总控台可消费的 motor table 数据，不控制电机。
  - 支持可选 `joint_motor_map` JSON 参数，把关节名映射到已知 `motor_id`、协议和原始 CAN 信息。
  - 本地测试通过：49 tests passed。
  - NanoPi 测试通过：39 tests passed；`colcon build --symlink-install --packages-select rehab_arm_psoc_bridge` 通过。
  - NanoPi ROS 冒烟测试通过：发布假 `/joint_states` 后，`/rehab_arm/motor_state` 输出 `rehab_arm_motor_state_v1` JSON。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 新增仿真数据采集 bringup 包和 launch：
  - 新增 `rehab_arm_bringup` ROS2 包。
  - 新增 `sim_data_collection.launch.py`，一次启动 MuJoCo/fallback 仿真、`joint_state_motor_state_node.py` 和 `data_recorder_node.py`。
  - 用途是先在仿真环境采集 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state` 和 `/rehab_arm/motor_state`，给后续总控台、标注、回放和 VLA 数据准备统一格式。
  - 修正仿真节点：无轨迹输入时也每 1 秒发布一次 `/rehab_arm/safety_state`，避免 recorder 完整性检查缺 safety topic。
  - 本地 `python -m py_compile` 通过；本地 `rehab_arm_psoc_bridge` 49 tests passed。
  - NanoPi `colcon build --symlink-install --packages-select rehab_arm_bringup` 通过。
  - NanoPi 首轮短跑发现 JSONL 包含 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/sensor_state`，但缺 `/rehab_arm/safety_state`；已在本地修复仿真节点周期发布 safety。
  - 修复后重新同步并构建 NanoPi 时 SSH 再次超时；未继续加压硬件，待 NanoPi 稳定后复测。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 补充 `rehab_arm_bringup` 本地静态测试：
  - 新增 `test_sim_data_collection_launch.py`。
  - 覆盖 `package.xml` 包名和依赖，以及 `sim_data_collection.launch.py` 是否包含仿真节点、motor_state 遥测桥和 recorder。
  - 本地验证通过：bringup 2 tests passed；`rehab_arm_psoc_bridge` 49 tests passed。
  - NanoPi 当前仍 SSH 超时，未做远端复测。
- NanoPi 恢复后完成 `sim_data_collection.launch.py` 数据闭环复测：
  - NanoPi 重新在线，hostname `NanoPi-M5`，无残留 colcon/launch/ROS 节点进程。
  - 同步最新 `mujoco_sim_node.py`、`data_recorder_node.py`、`joint_state_motor_state_node.py` 和 `rehab_arm_bringup` 文件。
  - NanoPi 构建通过：`rehab_arm_sim_mujoco`、`rehab_arm_psoc_bridge`、`rehab_arm_bringup`。
  - NanoPi 单测通过：bringup 2 tests passed；`rehab_arm_psoc_bridge` 39 tests passed。
  - `timeout -s INT 8s ros2 launch rehab_arm_bringup sim_data_collection.launch.py ...` 生成完整 JSONL。
  - `check_recording.py` 输出 `ok=true`，topics 包含 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
  - topic 计数示例：`/joint_states=500`、`/rehab_arm/motor_state=500`、`/rehab_arm/safety_state=5`、`/rehab_arm/sensor_state=500`。
  - `/rehab_arm/motor_state` 示例 payload 为 `rehab_arm_motor_state_v1`，`motor_count=5`。
  - 修复 ROS2 SIGINT 退出时的 shutdown race 日志：最终 `TRACEBACK_COUNT=0`。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 完成仿真 demo 轨迹数据采集：
  - `sim_data_collection.launch.py` 新增 `enable_demo_trajectory` 参数，默认 `false`。
  - 开启后启动 `rehab_arm_control/demo_trajectory_node.py`，发布一条标准 `/arm_controller/joint_trajectory`。
  - `rehab_arm_bringup/package.xml` 增加 `rehab_arm_control` 运行依赖。
  - `demo_trajectory_node.py` 增强 SIGINT 退出保护。
  - 本地验证通过：bringup 2 tests passed；`rehab_arm_psoc_bridge` 49 tests passed。
  - NanoPi 构建通过：`rehab_arm_control`、`rehab_arm_bringup`。
  - NanoPi 动态采集通过：`DEMO_PUBLISHED=1`，`check_recording.py ok=true`，`TRACEBACK_COUNT=0`。
  - JSONL topic 计数示例：`/joint_states=899`、`/rehab_arm/motor_state=898`、`/rehab_arm/safety_state=10`、`/rehab_arm/sensor_state=898`。
  - 5 个关节均记录到运动变化：shoulder lift span `0.55`、elbow lift span `1.05`、shoulder abduction span `0.28`、upper arm rotation span `0.60`、forearm rotation span `0.55`。
  - 本轮仍是纯仿真采集，没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 新增 JSONL session 摘要工具：
  - 新增 `summarize_recording.py`。
  - `data_recording.py` 新增 `summarize_jsonl_records()`，输出 topic 计数、topic 频率、关节 position min/max/span、moving joint count、motor entry count、safety state 和 `motion_allowed` 统计。
  - `setup.py` 和 `CMakeLists.txt` 注册 `summarize_recording` 入口。
  - 本地测试通过：`rehab_arm_psoc_bridge` 50 tests passed。
  - 本地命令行验证通过：临时 JSONL 输出 `rehab_arm_recording_summary_v1`，`moving_joint_count=1`。
  - NanoPi 已同步并构建 `rehab_arm_psoc_bridge` 通过。
  - NanoPi 摘要工具复测通过：重新生成 `sim_demo_motion.jsonl` 后，`summarize_recording.py` 输出 `schema_version=rehab_arm_recording_summary_v1`。
  - NanoPi 摘要结果：`moving_joint_count=5`，`motor_entry_count_min=5`，`motor_entry_count_max=5`。
  - NanoPi 摘要结果包含四个 topic：`/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
  - 5 个关节 span：elbow lift `1.05`、forearm rotation `0.55`、shoulder abduction `0.28`、shoulder lift `0.55`、upper arm rotation `0.60`。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- manifest 可选集成 session summary：
  - `build_recording_manifest()` 新增 `include_summary` 参数，默认 `false`，保持旧 manifest 格式兼容。
  - `build_manifest.py` 新增 `--include-summary` 参数。
  - 本地测试通过：`rehab_arm_psoc_bridge` 51 tests passed。
  - NanoPi 构建通过：`rehab_arm_psoc_bridge`。
  - NanoPi 单测通过：41 tests passed。
  - NanoPi 命令验证通过：`build_manifest.py /tmp/rehab_sim_collection --include-summary --output ...`。
  - 生成 manifest 中 `sim_demo_motion` session 包含 summary：`moving_joint_count=5`，`motor_entry_count_min/max=5`。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 同步 dry-run 验证带 summary 的 manifest 兼容：
  - 新增单测覆盖 `build_sync_dry_run_plan()` 会保留 manifest 中的 `summary` 字段。
  - 本地测试通过：`rehab_arm_psoc_bridge` 52 tests passed。
  - NanoPi 测试通过：42 tests passed。
  - NanoPi 命令验证通过：`sync_dry_run.py /tmp/rehab_sim_collection/manifest_with_summary.json` 输出 `rehab_arm_sync_dry_run_v1`。
  - dry-run 仍为 4 个计划请求，`/sessions/manifest` 请求内保留 `rehab_arm_recording_summary_v1`，`moving_joint_count=5`，`motor_entry_count_min/max=5`。
  - 本轮没有真实联网、没有上传服务器、没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 本地假服务器验证带 summary manifest 的 `sync_upload.py --execute`：
  - NanoPi 启动 `sync_test_server.py`，绑定 `127.0.0.1:8765`，保存请求到 `/tmp/rehab_arm_sync_server_summary`。
  - 对 `manifest_with_summary.json` 执行 `sync_upload.py --execute`，目标为本机假服务器。
  - 上传结果 `ok=true`，`completed_count=4`，`request_count=4`。
  - 假服务器收到 4 个 POST：devices/register、sessions/manifest、sessions/sim_demo_motion/files、sessions/sim_demo_motion/sync-status。
  - 服务端保存的 `/sessions/manifest` body 中保留 summary：`summary_schema=rehab_arm_recording_summary_v1`，`moving_joint_count=5`，`motor_entry_count_min/max=5`。
  - 本轮只连本机假服务器，没有上传真实服务器、没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 新增 JSONL 到 CSV 离线导出工具：
  - 新增 `export_recording_csv.py`。
  - 可从 recorder JSONL 导出 `joint_states.csv` 和 `motor_states.csv`，用于本地画曲线、标注、训练前检查和 Excel/pandas/MATLAB 对接。
  - CSV 为长表格式，每行一个关节或电机遥测样本。
  - 本地测试通过：`rehab_arm_psoc_bridge` 54 tests passed。
  - NanoPi 构建通过：`rehab_arm_psoc_bridge`。
  - NanoPi 测试通过：44 tests passed。
  - NanoPi 动态 session 导出验证通过：`joint_state_row_count=4275`，`motor_state_row_count=4275`。
  - 本轮没有发 CAN、没有发送 `0x320`、没有做电机运动测试。
- 新增对接文档：
  - 新增 `docs/INTEGRATION_GUIDE.md`。
  - 汇总 ROS2 topic、CAN ID、JSONL、manifest、summary、CSV、仿真采集流程、真机安全边界和当前已验证能力。
  - 明确服务器/VLA/App 只对接任务、状态和数据资产，不直接发 CAN 或底层电机命令。
  - 用户准备断电离开，后续切换到离线开发模式。
- 新增 JSONL 数据质量门工具：
  - 新增 `validate_recording_quality.py` 和 `build_recording_quality_report()`。
  - 可检查基础 topic、`/joint_states` 数量、运动关节数、`/rehab_arm/motor_state` 是否存在、每帧 motor 条目数和 `motion_allowed=true` 是否出现。
  - 默认不允许 `motion_allowed=true`，适配当前 logging-only/离线采集阶段。
  - 本地验证通过：`rehab_arm_psoc_bridge` 56 tests passed；`py_compile` 通过。
  - 本轮硬件全断电，未做 NanoPi、CAN、M33/M55 或电机测试。

## 进行中

- 下一步继续按框架补数据链路：
  - 总服务器归入 AI 合作平台工程，不搬到本仓库。
  - 本仓库只保留 NanoPi 数据采集、manifest、dry-run/upload 客户端和本地假服务器验证工具。
  - 离线阶段新增数据质量门和仿真主机使用流程，先服务仿真、标注、回放和后续 CI。
  - 后续先确认 USB/UVC 或深度摄像头枚举，再跑 `camera_keyframe_node.py` 采集真实图像。
  - 用户已准备断电，下一阶段先做离线开发：补文档、测试、数据工具和仿真主机流程，不依赖 NanoPi 在线。
  - 真机方向后续补 M33 电机状态到 `/rehab_arm/motor_state` 的映射。
  - 不进入真实电机控制。
  - 不给电机驱动上电，不做运动测试。

## 待确认

- `node_id=3` 对应哪个真实机械关节。
- `motor_id=4/5/6/7` 分别对应哪个真实机械关节。
- PSoC/M33 固件最终如何定义 `0x320` payload 字段。
- M33 和 M55 的实际通信方式：
  - shared memory
  - IPC
  - RT-Thread message queue
  - 其他方式
- AI 合作平台侧的正式数据资产、标注和权限模型。

## 下一步

严格按“一次只做一个能测试的小目标”推进：

1. 保持电机驱动断开，确认 `can0` 为 `ERROR-ACTIVE`。
2. raw SocketCAN 先测 `0x321 -> 0x322` heartbeat。
3. 离线补齐仿真主机环境搭建、数据质量检查、标注/回放流程，不依赖硬件上电。
4. 保持服务器同步为非实时外部接口，不放进控制闭环。
5. 仍保持 logging-only，不进入真实电机控制路径。

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

### 2026-05-25 - Manifest quality report handoff to platform

- Completed: added optional `quality_report` embedding to `build_recording_manifest()` and `build_manifest.py` via `--include-quality-report` plus quality criteria flags.
- Completed: platform API can read `quality_report` from manifest sessions and use `quality_report.ok=false` as an annotation/export blocking reason.
- Validated: Windows rehab-arm unit test `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_data_recording.py -v` passed 27 tests.
- Validated: platform API test `python -m pytest apps\api\tests\test_rehab_arm_sync.py -q` passed 4 tests.
- Not validated: no NanoPi, CAN, M33/M55, camera, motor, or cloud upload test in this slice.
- Safety: quality reports remain data-quality gates only; they do not grant motion permission or bypass M33.
- Next step: generate a real sim `manifest_with_quality.json`, sync to platform test server/cloud, and confirm the device data workbench shows annotation readiness from the uploaded quality report.

### 2026-05-25 - Cloud quality manifest sync smoke

- Completed: generated an offline sample JSONL session and `manifest_with_quality.json` on the Windows development machine.
- Completed: uploaded the sample through `sync_upload.py --execute` to `http://106.55.62.122:8011/api/rehab-arm/v1`.
- Validated: upload result `ok=true`, `completed_count=4`, and cloud accepted session `quality_demo`.
- Validated: cloud dashboard for `nanopi-quality-demo` reports `data_quality.annotation_ready=true`, `quality_report_ok=true`, and `control_boundary=data_quality_only_not_motion_permission`.
- Not validated: no NanoPi hardware, CAN, M33/M55, camera, motor power, or real patient/device data was used.
- Safety: the cloud sync stayed on the non-realtime data path only.
- Next step: surface the same quality gate clearly in the platform device data workbench UI.

### 2026-05-26 - Server quality gate check tool

- Completed: added `check_server_quality_gate.py` and registered the ROS2 console script.
- Completed: the tool checks `/devices/dashboard` for a device, reports `annotation_ready`, `quality_report_ok`, motor/joint counts, blocking reasons, and data-only safety boundary.
- Validated: new unit tests passed.
- Validated: `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v` passed 60 tests.
- Validated: command-line check against cloud device `nanopi-quality-demo` returned `ok=true`, `annotation_ready=true`, and `control_boundary=data_quality_only_not_motion_permission`.
- Not validated: no NanoPi build, M33/M55 firmware, CAN, motor power, or real camera data in this slice.
- Safety: this tool performs read-only HTTP GET checks only; it does not upload files or control hardware.
- Next step: run the same quality gate check from NanoPi after a real simulation/logging session upload.

### 2026-05-26 - Sync upload can auto-check server quality gate

- Completed: `sync_upload.py --execute` can now add `--check-quality-gate` to query server dashboard after upload.
- Completed: the upload result includes `quality_gate_checks`, checked device count, quality criteria, blocking reasons, and safety note.
- Completed: added `--allow-quality-not-ready` for diagnostics when the user only wants to confirm the server received the device.
- Validated: targeted `test_sync_upload.py` passed 6 tests.
- Validated: full `rehab_arm_psoc_bridge` test suite passed 62 tests.
- Validated: cloud smoke upload with `--check-quality-gate` returned `ok=true` and `annotation_ready=true` for `nanopi-quality-demo`.
- Safety: quality-gate check is a post-upload read-only HTTP GET. It does not send CAN, motor commands, or M33 overrides.
- Next step: when NanoPi is available, build the package there and run the same command after a real sim/log session upload.

### 2026-05-26 - Simulation environment self-check

- Completed: added `rehab_arm_sim_mujoco/check_sim_env.py` and registered the `check_sim_env` ROS2 console script.
- Completed: the tool checks `rclpy`, optional MuJoCo, URDF presence, sim launch files, data collection tools, and the 5-joint contract.
- Completed: updated user manual, simulation framework guide, and troubleshooting notes with the new command.
- Validated: `python -m py_compile rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\rehab_arm_sim_mujoco\check_sim_env.py` passed.
- Validated: `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test -v` passed 3 tests.
- Validated: Windows CLI self-check reports `ok=false/readiness=not_ready` because `rclpy` is not installed, while URDF, launch files, and data tools are found; this is expected on the non-ROS development machine.
- Not validated: no Linux simulation host, NanoPi build, MuJoCo install, CAN, M33/M55, camera, motor power, or real hardware in this slice.
- Safety: this check is read-only and explicitly does not open CAN, send `0x320/0x321`, or command M33/motors.
- Next step: add the platform-side simulation readiness surface or data asset entry that consumes these environment/status reports without turning them into motion permission.

### 2026-05-26 - Simulation readiness report handoff to platform

- Completed: `check_sim_env` now supports `--output` to write `sim_readiness_report.json` for platform upload or handoff.
- Completed: platform API accepts `POST /api/rehab-arm/v1/devices/{device_id}/simulation-readiness` and stores it as latest device telemetry.
- Completed: platform robot data workbench surfaces uploaded simulation readiness reports in the existing read-only readiness strip.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test\test_check_sim_env.py -v` passed 4 tests.
- Validated: `python -m py_compile rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\rehab_arm_sim_mujoco\check_sim_env.py` passed.
- Validated: platform `python -m pytest apps\api\tests\test_rehab_arm_sync.py -q` passed 5 tests.
- Validated: platform `npm --workspace apps/web exec eslint -- "app/projects/[id]/robotics/robotics-workbench-client.tsx"` passed.
- Not validated: no Linux simulation host, NanoPi, CAN, M33/M55, camera, motor power, or real MuJoCo runtime in this slice.
- Safety: simulation readiness is stored with `simulation_readiness_only_not_motion_permission`; it does not grant motion permission or bypass M33.
- Next step: add a tiny upload helper or documented curl command that posts the generated report to the cloud after a real Linux sim-host self-check.

### 2026-05-26 - Test artifact hygiene

- Completed: changed the `check_sim_env --output` unit test to write its report into a temporary directory that is deleted after the test.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test\test_check_sim_env.py -v` passed 4 tests.
- Safety: no demo report, screenshot, sample session, or generated readiness JSON is kept in the project tree.
- Next step: keep future demos and QA screenshots outside committed project files unless they become reusable docs or tests.

### 2026-05-26 - Simulation readiness upload helper

- Completed: added `upload_sim_readiness` to preview or upload `check_sim_env --output` reports to the platform.
- Completed: default mode is dry-run; `--execute` is required before any HTTP POST.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test\test_check_sim_env.py rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test\test_upload_sim_readiness.py -v` passed 8 tests.
- Validated: `python -m py_compile rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\rehab_arm_sim_mujoco\upload_sim_readiness.py` passed.
- Safety: upload result keeps `simulation_readiness_only_not_motion_permission`; it does not send CAN, joint targets, M33 commands, or motor commands.
- Next step: on the Linux simulation host, generate a real report, dry-run the upload, then execute against the cloud only after the report content is reviewed.

### 2026-05-26 - NanoPi CANSimple node 3 tiny motion capture

- Completed: brought `can0` up at classic CAN 1Mbps; bus stayed `ERROR-ACTIVE` with tx/rx error counters at 0.
- Completed: captured motor baseline at `/home/pi/rehab_arm_logs/can_captures/motor_can_baseline_20260525_194531.log`.
- Completed: ran a tiny direct CANSimple node 3 debug motion, avoiding private MIT `motor_id=4`.
- Captured motion log at `/home/pi/rehab_arm_logs/can_captures/cansimple_node3_tiny_motion_20260525_195020.log`.
- Observed: `0x061` heartbeat near 10Hz and `0x069` encoder estimate near 100Hz.
- Safety: sent `vel=0` and `idle` after the test; this remains debug-only direct control, not the formal wearable motion path.

### 2026-05-26 - Candump motor telemetry converter

- Completed: added `candump_motor_telemetry` to convert CANSimple `0x061/0x069` candump logs into unified `/rehab_arm/motor_state` JSONL.
- Completed: registered the ROS2 console script and CMake install entry.
- Validated: unit tests and `py_compile` passed on Windows.
- Validated: the real NanoPi node 3 tiny-motion log was converted in a temporary directory, producing 397 motor_state records from 444 raw CAN frames.
- Safety: converter is offline/log-only; it does not open CAN, send `0x320/0x321`, command M33, or control motors.
- Next step: build on NanoPi and use this JSONL path for real motor telemetry upload/quality checks after the next safe capture.

### 2026-05-26 - Platform Linux board access check panel

- Completed: platform robotics page now has a read-only Linux board access check panel for board presence, runner availability, ROS/simulation report, camera keyframe, CAN/serial data, and last upload time.
- Completed: kept the platform page generic for Linux boards; it does not hardcode the rehab arm and does not modify NPC workbench resources.
- Validated: targeted platform eslint passed for `apps/web/app/projects/[id]/robotics/robotics-workbench-client.tsx`.
- Validated: local authenticated browser QA opened `/projects/proj_rehab_arm/robotics`; desktop and 390px mobile screenshots showed the access check panel, no old control-console label, and no horizontal overflow.
- Validated: cloud platform deploy pulled `ai/game-loop-core`, built successfully, and restarted API `8011` plus web `3001`.
- Not validated: cloud protected-page screenshot is blocked because the local seed account is not valid on the cloud server.
- Safety: the panel is status-only and does not send ROS, CAN, M33, motor, or motion commands.
- Next step: use a real cloud test account to verify the protected robotics page, then continue the next robotics-development thin slice.

### 2026-05-26 - Platform Linux board setup checklist drawer

- Completed: added a collapsed setup checklist to the platform Linux board access panel: register device, scan interfaces, upload read-only data, then enter capture/annotation.
- Validated: targeted platform eslint passed.
- Validated: local authenticated browser QA clicked the drawer on desktop and 390px mobile; no horizontal overflow and no old control-console label.
- Validated: cloud platform deploy pulled latest `ai/game-loop-core`, built successfully, and restarted API `8011` plus web `3001`.
- Safety: the checklist describes data upload and development workflow only; it is not a motion enable path.
- Next step: keep moving toward real simulation host onboarding and data collection assets.

### 2026-05-26 - Linux board manifest generator

- Completed: added `board_manifest` in `rehab_arm_psoc_bridge` to generate `linux_board_manifest_v1` for NanoPi/Jetson/x86 Linux boards.
- Completed: the tool reports device identity, platform info, network/CAN interfaces, serial nodes, camera nodes, USB devices, ROS2 availability, recommended streams, and the safety boundary.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_board_manifest.py -v` passed 3 tests.
- Validated: `python -m py_compile rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\rehab_arm_psoc_bridge\board_manifest.py` passed.
- Validated: full `rehab_arm_psoc_bridge` unit test suite passed 70 tests.
- Validated: CLI smoke generated a manifest in the system temp directory and the temp file was removed after inspection.
- Safety: this is read-only discovery; it does not open CAN, start ROS control, send M33 commands, or move motors.
- Next step: add a dry-run/upload path for `linux_board_manifest_v1` so the platform can show real board capabilities from any configured Linux board.

### 2026-05-26 - Linux board manifest sync dry-run

- Completed: added `board_manifest_sync_dry_run` to convert `linux_board_manifest_v1` into a preview request plan for `/devices/register`.
- Completed: the plan extracts compatible platform fields: `device_id`, `robot_id`, `device_type=linux_board`, software release, and capability labels.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_board_manifest_sync_dry_run.py -v` passed 3 tests.
- Validated: full `rehab_arm_psoc_bridge` unit test suite passed 73 tests.
- Validated: CLI smoke generated a temporary board manifest and printed a dry-run `/devices/register` plan, then removed the temp file.
- Safety: dry-run prints the plan only; it does not open network connections or control hardware.
- Next step: add backend support for storing the full board manifest, then enable explicit `--execute` upload after review.

### 2026-05-26 - Platform full Linux board manifest storage

- Completed: platform API accepts `POST /api/rehab-arm/v1/devices/{device_id}/board-manifest` with `linux_board_manifest_v1`.
- Completed: platform dashboard now returns `board_manifest` latest state per device.
- Completed: platform Linux board page can use `board_manifest` to count camera and CAN/serial/USB readiness before live data streams begin.
- Completed: ROS dry-run now plans two requests: `/devices/register` and `/devices/{device_id}/board-manifest`.
- Validated: platform `python -m pytest apps\api\tests\test_rehab_arm_sync.py -q` passed 6 tests.
- Validated: platform targeted eslint passed for the robotics page.
- Validated: local authenticated browser QA opened the robotics page on desktop and 390px mobile with no horizontal overflow.
- Validated: full `rehab_arm_psoc_bridge` unit test suite passed 73 tests.
- Validated: cloud platform deployed `ai/game-loop-core` commit `3f131e66`; web build succeeded and API/web restarted on `8011/3001`.
- Not validated: no fake board manifest was posted to cloud to avoid demo data pollution.
- Safety: board manifest upload is data-only; it does not control CAN, ROS actions, M33, or motors.
- Next step: add an explicit `--execute` upload command for reviewed board manifests, then test from NanoPi when available.

### 2026-05-26 - Linux board manifest explicit upload command

- Completed: added `board_manifest_sync_upload`, which defaults to dry-run output and only sends HTTP requests when `--execute` is provided.
- Completed: the upload reuses the reviewed two-request plan: `/devices/register` then `/devices/{device_id}/board-manifest`.
- Completed: exposed `board_manifest_sync_upload` as a ROS2 console script and documented the NanoPi/Linux board usage flow.
- Validated: targeted `test_board_manifest_sync_upload.py` passed 2 tests, including fake-opener execution and CLI dry-run behavior.
- Validated: full `rehab_arm_psoc_bridge` unit test suite passed 75 tests.
- Validated: `py_compile` passed for `board_manifest_sync_upload.py`; CLI smoke without `--execute` printed a two-request dry-run plan from a temporary manifest.
- Safety: upload is data-only and preserves `board_manifest_sync_only_not_motion_permission`; it does not open CAN, start ROS motion, command M33, or move motors.
- Next step: test the new command on NanoPi when the board is available, first without `--execute`, then only upload after reviewing the manifest and server URL.

### 2026-05-26 - Simulation environment ROS topic contract

- Completed: extended `check_sim_env` reports with `topic_contract` for `/arm_controller/joint_trajectory`, `/joint_states`, `/rehab_arm/safety_state`, `/rehab_arm/sensor_state`, and `/vla/task_goal`.
- Completed: documented that this contract is shared by MuJoCo/fallback simulation, NanoPi, platform data collection, annotation, and later VLA planning.
- Validated: targeted `test_check_sim_env.py` passed 4 tests after first failing on missing `topic_contract`.
- Validated: full `rehab_arm_sim_mujoco` unit test suite passed 8 tests.
- Validated: `py_compile` passed for `check_sim_env.py`.
- Validated: CLI smoke printed `topic_contract.trajectory_command.topic=/arm_controller/joint_trajectory` and `topic_contract.control_boundary=simulation_topic_contract_not_motion_permission`; local Windows process returned nonzero because this shell is not a sourced ROS2 runtime.
- Safety: `topic_contract` is documentation/report data only and uses `simulation_topic_contract_not_motion_permission`; it does not prove topics are live and does not grant motion permission.
- Next step: have the platform surface the simulation topic contract in the Linux board/simulation readiness panel, then later run it on the real Linux simulation host.

### 2026-05-26 - Recording topic profile presets

- Completed: added named JSONL topic profile presets for `check_recording.py`: `simulation_minimum`, `hardware_telemetry`, and `perception_vla`.
- Completed: `hardware_telemetry` requires `/rehab_arm/motor_state`; `perception_vla` requires `/rehab_arm/camera_keyframe`.
- Completed: documented how to use the profiles before annotation, charting, upload, or training checks.
- Validated: targeted `test_data_recording.py` passed 30 tests, including CLI failure when `hardware_telemetry` is missing `/rehab_arm/motor_state`.
- Validated: full `rehab_arm_psoc_bridge` unit test suite passed 78 tests.
- Validated: `py_compile` passed for `data_recording.py` and `check_recording.py`.
- Validated: CLI smoke on a temporary JSONL returned `topic_profile=hardware_telemetry` and missing `/rehab_arm/motor_state`.
- Safety: topic profile checks only read local JSONL files; they do not open CAN, start ROS nodes, upload data, command M33, or move motors.
- Next step: use these presets in the next real NanoPi/MuJoCo data capture before building a manifest for platform sync.

### 2026-05-26 - Recording quality gate topic profiles

- Completed: `validate_recording_quality.py` and `build_manifest.py --include-quality-report` now accept `--topic-profile`.
- Completed: quality reports include `topic_profile`, `required_topics`, and missing topic details for platform/annotation gating.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 82 tests; `py_compile` passed for touched scripts.
- Safety: read-only JSONL validation only; no ROS launch, CAN access, upload, M33 command, or motor motion.
- Next step: run the same quality gate on the next real NanoPi or MuJoCo capture and surface the result in the platform data page.

### 2026-05-26 - Offline perception quality gate

- Completed: added `--min-camera-keyframes` to JSONL quality reports and manifest quality reports.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 83 tests; `py_compile` passed.
- Safety: offline JSONL counting only; no camera access, CAN access, upload, M33 command, or motor motion.
- Next step: connect platform data page to display camera keyframe count and missing perception topics.

### 2026-05-26 - Offline camera file integrity check

- Completed: added optional `--require-camera-files` and `--camera-base-dir` for perception JSONL quality reports.
- Completed: quality reports now include `camera_file_check` with checked, ok, missing, and sha256 mismatch counts.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 85 tests; `py_compile` passed.
- Safety: optional local file integrity check only; no camera access, CAN access, upload, M33 command, or motor motion.
- Next step: platform data page should show `camera_file_check` when present and avoid enabling it before image files are synced.

### 2026-05-26 - Offline annotation queue

- Completed: added `build_annotation_queue.py` and `rehab_arm_annotation_queue_v1` for quality-gated labeling worklists.
- Completed: queue includes ready sessions, skipped sessions, recommended labels, and a data-only control boundary.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 87 tests; `py_compile` passed.
- Safety: offline manifest transform only; no ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: platform data/annotation page should read the queue and show skipped reasons before training export.

### 2026-05-26 - Offline annotation CSV template

- Completed: added `export_annotation_template.py` to convert `rehab_arm_annotation_queue_v1` into a CSV labeling template.
- Completed: template includes session identity, annotation status, annotator, notes, and recommended label columns.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 89 tests; `py_compile` passed.
- Safety: offline CSV export only; no ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: add validation for completed annotation CSV before training export.

### 2026-05-27 - Offline annotation CSV validation

- Completed: added `validate_annotations.py` and `validate_annotation_rows()` to check completed annotation CSV files against `rehab_arm_annotation_queue_v1`.
- Completed: validator requires queued `session_id`, approved annotation status, and filled recommended label fields before training export.
- Completed: registered the tool in both ROS Python entry points and CMake install scripts.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_data_recording.py` passed 43 tests.
- Safety: offline CSV quality gate only; no ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: build a JSONL replay/inspection path for MuJoCo alignment and platform data review.

### 2026-05-27 - JSONL replay plan baseline

- Completed: added `build_replay_plan.py` and `build_replay_plan()` to convert recorder JSONL into a time-ordered topic replay plan.
- Completed: replay plan supports topic filtering, optional payload omission, relative timestamps, topic counts, and explicit data-only control boundary.
- Completed: documented the open-source-aligned route: ROS2 rosbag-style record/replay, ros2_control JointTrajectory boundary, MoveIt-style limits/time parameterization, and hardware abstraction.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_data_recording.py` passed 46 tests.
- Validated: `python -m py_compile data_recording.py build_replay_plan.py` passed.
- Safety: offline JSON transform only; no ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: use replay plan as the input contract for a MuJoCo/RViz replay adapter or JSONL-to-rosbag/topic publisher.

### 2026-05-27 - ROS2 JSONL replay node

- Completed: added `jsonl_replay_node.py` to publish recorded JSONL events back onto ROS topics by relative timestamp.
- Completed: `/joint_states` replays as standard `sensor_msgs/msg/JointState`; `/rehab_arm/*` telemetry replays as `std_msgs/msg/String` JSON.
- Completed: registered the node in both `setup.py` console scripts and CMake install programs.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_data_recording.py` passed 47 tests.
- Validated: `python -m py_compile jsonl_replay_node.py data_recording.py` passed.
- Safety: ROS replay publishes historical telemetry only; it does not subscribe to `JointTrajectory`, open SocketCAN, send `0x320`, command M33, or move motors.
- Next step: run the replay node on the Linux simulation host with RViz/MuJoCo subscribers and verify joint names/directions against the URDF.

### 2026-05-27 - Offline dataset index

- Completed: added `build_dataset_index.py` and `build_dataset_index()` to turn a quality-gated manifest into a training/replay/platform dataset index.
- Completed: index includes session identity, JSONL path, topics, topic profile, summaries, quality status, skipped reasons, and a data-only control boundary.
- Completed: registered the tool in both `setup.py` console scripts and CMake install programs.
- Validated: `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_data_recording.py` passed 49 tests.
- Validated: `python -m py_compile data_recording.py build_dataset_index.py` passed.
- Safety: offline manifest transform only; no ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: after the simulation host is ready, use `dataset_index.json` to select replay sessions for RViz/MuJoCo and platform annotation review.

### 2026-05-27 - Patient Device Profile validation gate

- Completed: added `patient_profile.py` and `validate_patient_profile.py` for offline safety validation of the shared App/platform/NanoPi/M33/M55 Patient Device Profile.
- Completed: first rule set checks identity/version/status, patient ROM inside device limits and `-60°~+60°` envelope, patient velocity limits, training mode, emergency policy, VLA permission/forbidden outputs, and M55 no-direct-motor-control boundary.
- Completed: registered the tool in both `setup.py` console scripts and CMake install programs.
- Validated: `python -m unittest test_patient_profile.py test_data_recording.py test_m33_ros_contract.py` passed 55 tests.
- Validated: `python -m py_compile patient_profile.py validate_patient_profile.py` passed.
- Safety: offline profile quality gate only; no profile write, ROS launch, network upload, CAN access, M33 command, or motor motion.
- Next step: add a profile-to-M33-safety-subset dry-run exporter after the profile schema is reviewed.

### 2026-05-27 - M33 safety subset dry-run export

- Completed: added `build_m33_safety_subset()` and `export_m33_safety_subset.py` to derive an M33-facing safety subset from a validated Patient Device Profile.
- Completed: exported limits take the stricter value between device absolute limits and patient limits; VLA task execution remains false.
- Completed: registered the tool in both `setup.py` console scripts and CMake install programs.
- Validated: `python -m unittest test_patient_profile.py test_data_recording.py test_m33_ros_contract.py` passed 58 tests.
- Validated: `python -m py_compile patient_profile.py export_m33_safety_subset.py` passed.
- Safety: dry-run JSON generation only; no M33 write, ROS launch, network upload, CAN access, or motor motion.
- Next step: after schema review, define the signed/versioned NanoPi-to-M33 profile update frame or management channel.

### 2026-05-27 - Patient profile change review

- Completed: added `build_patient_profile_change_report()` and `review_patient_profile_change.py` to compare an old active profile with a new draft profile.
- Completed: report rejects non-incremented profile versions and patient/device identity mismatch; warns on ROM widening, velocity increases, and training mode changes.
- Completed: registered the tool in both `setup.py` console scripts and CMake install programs.
- Validated: `python -m unittest test_patient_profile.py test_data_recording.py test_m33_ros_contract.py` passed 61 tests.
- Validated: `python -m py_compile patient_profile.py review_patient_profile_change.py` passed.
- Safety: offline review only; it does not approve, write, sync, launch ROS, access CAN, command M33, or move motors.
- Next step: add a profile approval bundle format that includes validation report, change report, reviewer identity, and signature placeholder.

### 2026-05-27 - App BLE M33 safety package dry-run

- Completed: added `build_ble_m33_safety_package()` and `build_ble_m33_safety_package.py` for the App BLE -> M33 safety package draft.
- Completed: package wraps the validated M33 safety subset, approval metadata, expiry timestamp, device/profile identity, transport marker, and signature placeholder.
- Completed: package is only `ok=true` for `approved` or `active` profiles and required approval/expiry fields.
- Validated: `python -m unittest test_patient_profile.py test_data_recording.py test_m33_ros_contract.py` passed 64 tests.
- Validated: `python -m py_compile patient_profile.py build_ble_m33_safety_package.py` passed.
- Safety: dry-run JSON generation only; no BLE scan/connect/write, no M33 write, no ROS launch, no CAN access, and no motor motion.
- Next step: define the future BLE characteristic/fragmentation/ack contract before implementing real App-to-M33 writes.

### 2026-05-27 - Next-day multi-AI integration prompts

- Completed: added `docs/TOMORROW_INTEGRATION_PROMPTS.md` with copy-ready prompts for platform AI, App AI, and ROS/NanoPi/Linux integration agent.
- Completed: documented the shared safety boundaries, one-day bring-up order, data/profile artifacts, stop conditions, and expected reports.
- Completed: linked the prompt document from `docs/USER_MANUAL.md`.
- Validated: documentation-only change; no code, ROS launch, network, CAN, BLE, M33 command, or motor motion.
- Next step: on integration day, start with Git sync and offline validation before hardware motion tests.

### 2026-05-26 - NanoPi motor data receive check

- Completed: live NanoPi CAN receive test on `192.168.2.66` with `can0` at classic CAN 1Mbps.
- Validated: `can0` stayed `ERROR-ACTIVE` with tx/rx error counters 0.
- Validated: passive capture saw CANSimple node 3 traffic: `0x061` heartbeat and `0x069` encoder/status frames.
- Validated: M33 heartbeat replied on `0x322` with `A5 01 07 00 01 01 0A 00`.
- Validated: private Get_ID probes confirmed motor IDs 4, 5, 6, and 7 reply on extended frames.
- Validated: direct private active-report enabled periodic status for motors 4/5/6/7 as `0x180004FD`, `0x180005FD`, `0x180006FD`, and `0x180007FD` at about 100Hz each.
- Safety: no motion command was sent; only heartbeat, Get_ID, and active-report receive checks were used. Active-report was disabled again after the capture.
- Not validated: M33 `active-report` command path did not produce periodic motor status, so formal NanoPi ROS data collection still needs M33 aggregation/forwarding work instead of direct debug control.
- Next step: update the M33/NanoPi bridge so official motor telemetry comes through the M33 safety boundary and is published to `/rehab_arm/motor_state`.

### 2026-05-26 - Motor protocol baseline and safe telemetry decoding

- Completed: added `docs/MOTOR_PROTOCOLS.md` for current motor IDs, Sitaiwei CANSimple telemetry, Lingzu RobStride private active-report telemetry, M33/M55 data flow, and safety boundaries.
- Completed: updated `candump_motor_telemetry.py` to parse `candump -L` hash lines and Lingzu active-report frames from motors 4/5/6/7.
- Completed: Lingzu active-report now preserves raw fields by default and does not publish engineering units until the exact actuator model for each motor ID is confirmed.
- Completed: documented that the nearest local M33 Git repo is `D:\RT-ThreadStudio\workspace\yiliao_m33`, which already has logging-only `0x320` safety assessment and `0x322` detail-code reporting.
- Completed: located local Feishu offline pages for the shoulder/Sitaiwei drive in `D:\电机上位机\肩关节电机资料` and added the confirmed CANSimple commands, object/parameter headings, hardware interfaces, and SDK/control-mode entries to `docs/MOTOR_PROTOCOLS.md`.
- Completed: extracted Sitaiwei CANSimple frame rules from the local offline protocol page: standard 11-bit ID, `can_id = (node_id << 5) + cmd_id`, little-endian payload, IEEE754 float32, and the official `Set_Input_Pos` byte example.
- Completed: `candump_motor_telemetry.py` now carries CANSimple heartbeat byte5/byte6/byte7 into motor-state JSONL as raw fields instead of pretending they are confirmed engineering values.
- Completed: documented local M33/NanoPi CANSimple control payload layouts for `Set_Axis_State`, `Set_Controller_Mode`, `Set_Input_Pos`, `Set_Input_Vel`, `Set_Input_Torque`, `Set_Limits`, and `Clear_Errors`.
- Completed: corrected the CANSimple data wording from "fixed 8 bytes" to command-dependent classic CAN DLC; M33 currently sends `Set_Input_Torque` as 4-byte `float32`.
- Validated: targeted `test_candump_motor_telemetry.py` passed 10 tests.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 96 tests; `py_compile` passed for `candump_motor_telemetry.py`.
- Not validated: M33/NanoPi control payload table is derived from local implementation and partially from the offline protocol page; it still needs a final vendor-table cross-check before enabling any formal execution path.
- Safety: changes are offline log conversion and documentation only; no CAN device is opened, no `0x320/0x321` is sent, no M33 command is issued, and no motor can move.
- Next step: confirm motor 4/5/6/7 actuator models and joint bindings, then make M33 aggregate official motor telemetry into NanoPi ROS `/rehab_arm/motor_state`.

### 2026-05-26 - M33 aggregate motor telemetry parser draft

- Completed: added NanoPi-side `psoc_motor_status.py` parser for proposed M33 official motor telemetry frames `0x330~0x337`.
- Completed: documented the draft payload in `docs/MOTOR_PROTOCOLS.md`, `docs/PSOC_CAN_PROTOCOL_V1.md`, and `docs/USER_MANUAL.md`.
- Validated: targeted `test_psoc_motor_status.py` passed 7 tests.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 103 tests; `py_compile` passed for `psoc_motor_status.py`.
- Not validated: M33 firmware has not emitted `0x330~0x337` yet; this is a firmware-pending contract.
- Safety: parser is telemetry-only, does not open CAN, send `0x320/0x321`, command M33, or move motors. User has allowed 3/7 small motion later, but this increment intentionally stayed offline.
- Next step: add a read-only ROS bridge path that converts received M33 `0x330~0x337` frames into `/rehab_arm/motor_state`, then test with synthetic frames before hardware.

### 2026-05-26 - M33 motor telemetry read-only ROS bridge path

- Completed: `psoc_can_bridge_node.py` now recognizes `0x330~0x337`, aggregates latest valid M33 motor status frames by slot, and publishes `/rehab_arm/motor_state`.
- Completed: the same M33 motor telemetry now publishes ROS `/joint_states` for RViz, MuJoCo state sync, platform 3D preview, and annotation replay.
- Completed: M33 telemetry now updates the bridge internal `current_positions` for known joints, so future trajectory handling starts from the latest M33-reported pose instead of stale zero defaults.
- Completed: added aggregator tests for latest-per-slot behavior and invalid-frame rejection.
- Validated: targeted `test_psoc_motor_status.py` passed 12 tests.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 117 tests; `py_compile` passed for `psoc_motor_status.py` and `psoc_can_bridge_node.py`.
- Not validated: no live M33 `0x330~0x337` frames yet; hardware execution was not touched.
- Safety: bridge path is receive-only telemetry. It updates internal pose state, but does not change `0x320` sending, does not enable `enable_target_tx`, and does not authorize motor motion.
- Next step: add a synthetic SocketCAN/candump-style smoke command or launch test so NanoPi can verify `/rehab_arm/motor_state` publication before asking M33 firmware to emit real frames.

### 2026-05-26 - Synthetic M33 motor telemetry smoke tool

- Completed: added `m33_motor_status_smoke.py` to dry-run or explicitly send synthetic `0x330~0x337` telemetry frames for motor 3 and motor 7.
- Completed: documented NanoPi dry-run, optional `--execute`, and `/rehab_arm/motor_state` observation workflow.
- Completed: smoke tool can now write a minimal JSONL session with `/joint_states`, `/rehab_arm/safety_state`, `/rehab_arm/sensor_state`, and `/rehab_arm/motor_state` for platform/data pipeline checks.
- Completed: smoke tool stdout now includes `quality_report` when `--output-jsonl` is used, so the platform can consume the same `hardware_telemetry` contract as local validation.
- Validated: targeted `test_m33_motor_status_smoke.py` passed 5 tests.
- Validated: smoke JSONL passes `hardware_telemetry` quality gate with 2 motor entries.
- Validated: targeted `test_m33_motor_status_smoke.py` passed 9 tests.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 114 tests; `py_compile` passed for `m33_motor_status_smoke.py`.
- Not validated: did not run SocketCAN `--execute` on NanoPi or `vcan0` in this Windows shell.
- Safety: default mode is dry-run JSON only. `--execute` sends only telemetry IDs `0x330/0x331`, never `0x320`, and does not command M33 or motors.
- Platform: the generated JSONL is a minimal sample for the platform Linux-board device data page and annotation pipeline; it should remain data-only and not become a command channel.
- Next step: run this on NanoPi with `vcan0` first, then use it to prove recorder captures `/rehab_arm/motor_state` before asking M33 firmware to emit real telemetry.

### 2026-05-26 - Offline candump support for M33 motor telemetry

- Completed: `candump_motor_telemetry.py` now converts M33 `0x330~0x337` motor status frames into `/rehab_arm/motor_state` JSONL with source `candump_m33_motor_status`.
- Completed: conversion summary now includes `m33_motor_status_count`.
- Validated: targeted `test_candump_motor_telemetry.py` passed 11 tests.
- Validated: full `rehab_arm_psoc_bridge` unit tests passed 118 tests; `py_compile` passed for `candump_motor_telemetry.py`.
- Safety: offline conversion only; no CAN device is opened, no frames are sent, and no M33 or motor command is issued.
- Platform: platform/annotation can now consume both live ROS records and offline candump-derived records using the same `/rehab_arm/motor_state` contract.
- Next step: run a `vcan0` smoke capture through `candump_motor_telemetry.py` on NanoPi and compare it with live `/rehab_arm/motor_state`.

### 2026-05-26 - Live true-CAN motor telemetry snapshot for powered 3/7

- Completed: added `live_socketcan_motor_snapshot.py` as a short SocketCAN telemetry snapshot tool for real `can0`.
- Completed: tool decodes current 3号伺泰威 CANSimple `0x061/0x069` and 7号灵足 private active-report `0x180007FD` into motor-state-compatible JSON fields.
- Completed: live snapshot can now write recorder/platform-compatible JSONL containing `session_metadata` and `/rehab_arm/motor_state`.
- Completed: M33 candump conversion also now emits `/joint_states` from M33 `0x330~0x337` logs for RViz/MuJoCo/platform replay.
- Validated on NanoPi true CAN: `can0` was `ERROR-ACTIVE`, 1Mbps, tx/rx error counters 0.
- Validated on NanoPi true CAN: 3s capture saw `0x061=30`, `0x069=300`, `0x180007FD=299`.
- Validated: motor 3 latest heartbeat had `axis_error=0`, `axis_state=1`; motor 3 encoder position/velocity were 0; motor 7 raw active-report was `A4EE7FFF7FFF0140`.
- Validated on NanoPi true CAN: `--output-jsonl` wrote a loadable JSONL with `session_metadata` and `/rehab_arm/motor_state`, `motor_count=2`.
- Validated: local targeted `test_live_socketcan_motor_snapshot.py` passed 7 tests; full bridge unit suite passed 126 tests.
- Hardware note: user confirmed motors 4/5/6 are powered off/closed, so missing Get_ID replies and missing active-report for 4/5/6 are expected in this session.
- Safety: snapshot tool is telemetry-only. It does not send position, velocity, torque, `0x320`, or M33 motion commands. `--enable-active-report` only toggles temporary status reporting and disables it on exit.
- Next step: make the formal M33 firmware emit `0x330~0x337` for motor 3/7 first, then have NanoPi bridge publish the same data through `/rehab_arm/motor_state` and `/joint_states`.

### 2026-05-26 - M33 official motor telemetry firmware prep

- Completed: local M33 branch `M33` now has `0x330~0x337` cached motor telemetry publishing prepared in `applications/control/control_layer.c`.
- Completed: added `CONTROL_CAN_ID_M33_MOTOR_STATUS_BASE=0x330`, marker `0xB3`, publish period 100ms, and fresh-feedback window 1000ms in `control_layer_cfg.h`.
- Completed: M33 publisher reads cached `s_motor_feedback[]` only; it does not enable motors, change active-report, send target, or alter `0x320` execution behavior.
- Completed: added M33 shell command `cmd_m33_motor_status_once` for manual one-shot telemetry validation after flashing.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded with RT-Thread Studio toolchain.
- Not validated: full firmware image was not relinked/flashed in this turn; user will handle flashing.
- Safety: `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U` remains the safety default. `0x330~0x337` is telemetry-only and motion permission still depends on `0x322` plus M33 safety state.
- Next step: after user flashes M33, run NanoPi `candump -L can0,330:7F8` and confirm `B3` telemetry frames appear before using ROS bridge `/rehab_arm/motor_state`.

### 2026-05-26 - M33 telemetry burn-after live validation

- Completed: user flashed M33 firmware; NanoPi `can0` was reachable over SSH and stayed `ERROR-ACTIVE`, 1Mbps, tx/rx error counters 0.
- Validated: NanoPi heartbeat `0x321#01` received M33 status reply `0x322#A501070001010A00`, proving M33 CAN receive/reply is alive after flashing.
- Validated: with 7号灵足 temporary active-report enabled for 5s, CAN saw `0x180007FD=499/500` and M33 aggregate telemetry `0x336=49/50`.
- Validated: M33 `0x336` payload used marker `B3`, for example `336#B32B07002B0E0020`.
- Validated: NanoPi ROS bridge was rebuilt with the latest bridge parser and publishes `/rehab_arm/motor_state`; `/joint_states` was observed once as `m33_status_slot_6` with position about `3.627 rad`.
- Safety: no `/arm_controller/joint_trajectory` was published, no `0x320` target frame was sent, and `enable_target_tx=False` was used for the bridge check.
- Next step: clean up NanoPi executable naming/version sync, then add a repeatable read-only launch/test command for live M33 motor telemetry before any formal trajectory test.

### 2026-05-26 - Repeatable NanoPi live telemetry acceptance script

- Completed: added `scripts/nanopi_live_telemetry_check.sh` as the standard read-only post-power-on acceptance check.
- Completed: the script validates `can0 ERROR-ACTIVE`, sends only NanoPi heartbeat `0x321#01`, expects M33 `0x322`, starts ROS bridge with `enable_target_tx=false`, temporarily enables 7号 telemetry, and checks `/rehab_arm/motor_state` plus `/joint_states`.
- Completed: the script monitors `can0,320:7FF` during the check and fails if any `0x320` target frame appears.
- Validated on NanoPi true CAN: script passed with `0x322#A501070001010A00`, `0x180007FD=499`, `0x336=49`, `/rehab_arm/motor_state` JSON, and `/joint_states` `m33_status_slot_6`.
- Safety: no trajectory was published and no target frame was observed.
- Next step: use this acceptance script before every live hardware session, then move to the next formal robot-development slice: M33/NanoPi safety-state gating before controlled trajectory tests.

### 2026-05-26 - NanoPi trajectory gate requires motion_allowed

- Completed: added `safety_gate.py` so NanoPi trajectory acceptance depends on `0x322 motion_allowed=true`, not just `state=ok`.
- Completed: updated `psoc_can_bridge_node.py` to store the latest parsed `0x322` payload and call the new safety gate before accepting or sending trajectory points.
- Completed: added unit tests proving legacy V1 `state=ok` still rejects because `motion_allowed=false`, logging-only V2 rejects, and V2 `state=ok/control_mode=armed` accepts.
- Validated: targeted safety/status tests passed 12 tests.
- Validated: full `rehab_arm_psoc_bridge` suite passed 130 tests.
- Validated on NanoPi true CAN: workspace rebuilt, live telemetry acceptance script still passed, and a legal trajectory was rejected with `PSoC motion_allowed is not true`; `candump can0,320:7FF` stayed empty.
- Safety: this closes a permission gap where old compatible `0x322 ok` could be mistaken as motion permission.
- Next step: define the next M33 state transition needed for controlled trajectory testing: how M33 moves from `logging_only` to `armed`, and which physical checks must be true before it ever reports `motion_allowed=true`.

### 2026-05-26 - M33 motion_allowed minimum contract

- Completed: tightened NanoPi `0x322` parser so `motion_allowed=true` requires `error_code=0`, `safety_state=ok`, `control_mode=armed/active`, and `detail_code=none`.
- Completed: documented the same minimum M33 contract in `docs/PSOC_CAN_PROTOCOL_V1.md` and `docs/MOTOR_PROTOCOLS.md`.
- Completed: added tests that `ok/armed/detail=motor_fault` still rejects, while `ok/armed/detail=none` and `ok/active/detail=none` allow motion candidate status.
- Validated: targeted `test_psoc_status.py` and `test_safety_gate.py` passed 14 tests.
- Validated: full `rehab_arm_psoc_bridge` suite passed 132 tests.
- Validated on NanoPi true CAN: parser update was synced, ROS workspace rebuilt, and `nanopi_live_telemetry_check.sh` passed with `0x322`, `0x336`, `/rehab_arm/motor_state`, `/joint_states`, and no `0x320`.
- Safety: this does not enable motion; current M33 still reports `limited/logging_only`, so NanoPi continues to reject trajectories.
- Next step: implement an explicit M33 pre-arm checklist/status source, still reporting `motion_allowed=false` until all physical safety inputs and joint limits are confirmed.

### 2026-05-26 - M33 diagnostic pre-arm checklist

- Completed: M33 branch `M33` now has `cmd_m33_prearm_check`.
- Completed: the command reports logging-only state, heartbeat freshness, physical input confirmation placeholders, required/fresh/fault motor feedback masks, and a final `ready` flag.
- Completed: added conservative compile-time defaults: required joint mask `0x7F`, estop/power/limits unconfirmed, and no pre-arm with logging-only.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded.
- Not validated: full firmware image was not relinked/flashed in this turn; user will flash when needed.
- Safety: the command is diagnostic only. It never changes mode, never sends motor output, and current defaults should report `ready=0`.
- Next step: after flashing, run `cmd_m33_prearm_check` and use the failing fields as the checklist for real hardware safety inputs and final joint limit confirmation.

### 2026-05-26 - M33 pre-arm checklist burn-after validation

- Completed: user flashed the M33 pre-arm checklist firmware.
- Validated on NanoPi true CAN: `nanopi_live_telemetry_check.sh` still passed after flashing; `0x322`, `0x336`, `/rehab_arm/motor_state`, and `/joint_states` were observed, and no `0x320` appeared.
- Validated on M33 serial COM26: `cmd_m33_prearm_check` ran successfully.
- Observed: `PREARM: ready=0 motion_allowed_would_be=0`.
- Observed: `PREARM_MODE logging_only_clear=0 logging_only_compile=1`, so firmware still blocks motion output.
- Observed: heartbeat was fresh, `ok=1 age_ms=78 timeout_ms=2500`.
- Observed: `estop_confirmed=0 power_confirmed=0 limits_confirmed=0`, as expected because those physical safety inputs are not confirmed yet.
- Observed: `fresh_mask=0x00000000 fresh_ok=0` at the serial check instant; this is not a failure of the command, it means the required motor feedback freshness condition was not satisfied at that moment.
- Safety: this validation did not send a trajectory or `0x320`; pre-arm correctly stayed false.
- Next step: add a more precise pre-arm motor requirement mask for the currently powered motors, then separately connect/confirm physical estop, power, and limits before any `motion_allowed=true` work.

### 2026-05-26 - M33 pre-arm diagnostic mask override

- Completed: `cmd_m33_prearm_check` now accepts an optional one-shot required joint mask, for example `0x40` for the current slot6/`0x336`/motor7 check and `0x44` for slot2+slot6.
- Completed: the command prints `PREARM_MASK` with the active mask source (`config` or `argv`) and the default compiled mask.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded.
- Not validated: not flashed yet; user will flash when ready.
- Safety: the mask override is diagnostic only. It does not change compile-time defaults, does not persist, and does not enable motion.
- Next step: after flashing, run `cmd_m33_prearm_check 0x40` immediately after enabling motor7 telemetry to confirm whether slot6 freshness becomes observable.

### 2026-05-26 - M33 pre-arm mask burn-after validation

- Completed: user flashed the diagnostic mask override firmware.
- Validated on NanoPi true CAN: `nanopi_live_telemetry_check.sh` passed; `0x322`, `0x336`, `/rehab_arm/motor_state`, `/joint_states` were present and no `0x320` appeared.
- Validated on M33 serial COM26: `cmd_m33_prearm_check 0x40` accepted the one-shot mask and printed `PREARM_MASK required_mask=0x00000040 source=argv default_mask=0x0000007F`.
- Validated: while 7号 telemetry was actively streaming, M33 reported `fresh_mask=0x00000040 fresh_count=1 fresh_ok=1 fault_free=1`.
- Observed: `PREARM ready=0 motion_allowed_would_be=0` remained correct because logging-only and physical safety inputs are still not cleared.
- Safety: no trajectory or `0x320` was sent; the mask only changed the diagnostic motor-freshness requirement for one command invocation.
- Next step: define real physical safety input confirmation sources for estop/power/limits, still without enabling motion.

### 2026-05-26 - M33 physical safety input contract draft

- Completed: M33 branch `M33` now has explicit pre-arm safety input fields for estop, motor power, and joint limits.
- Completed: added default sources as `unwired` and default `safe_now=0`, so the firmware cannot pre-arm until both the input source is confirmed and the live safe state is true.
- Completed: added M33 shell command `cmd_m33_safety_inputs` to print the physical safety input contract without changing mode or enabling output.
- Completed: `cmd_m33_prearm_check` now prints `PREARM_INPUT_DETAIL` with each input source and current safe state.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded.
- Not validated: full firmware image was not relinked or flashed in this turn; user will flash when ready.
- Safety: this is diagnostic-only. It deliberately keeps `ready=0` and does not change `0x322 motion_allowed`.
- Next step: after flashing, run `cmd_m33_safety_inputs` and `cmd_m33_prearm_check 0x40`; confirm safety inputs are still unwired/unconfirmed before assigning real GPIO or ADC sources.

### 2026-05-26 - M33 safety input contract burn-after validation

- Completed: user flashed the M33 safety-input diagnostic firmware.
- Validated on NanoPi true CAN: `/home/pi/nanopi_live_telemetry_check.sh` passed with `can0 ERROR-ACTIVE`, `0x322`, `0x336`, `/rehab_arm/motor_state`, `/joint_states`, and no `0x320`.
- Validated on M33 serial COM26: `cmd_m33_safety_inputs` printed estop, power, and limits as `source=unwired confirmed=0 safe_now=0`.
- Validated on M33 serial COM26: `cmd_m33_prearm_check 0x40` printed `PREARM_INPUT_DETAIL` with all three safety inputs `safe_now=0`.
- Validated with 7号 active-report window open: `cmd_m33_prearm_check 0x40` reported `fresh_mask=0x00000040 fresh_count=1 fresh_ok=1 fault_free=1`.
- Observed: `PREARM ready=0 motion_allowed_would_be=0` remained correct because logging-only and physical safety inputs still block motion.
- Safety: no trajectory was published and no `0x320` target frame appeared.
- Next step: define the real M33 safety-input source mapping plan for estop, motor power/voltage, and joint limits before any armed-mode implementation.

### 2026-05-26 - M33 safety input mapping document

- Completed: added `docs/M33_SAFETY_INPUT_MAPPING.md`.
- Completed: documented the required `estop`, `power`, and `limits` input sources, `confirmed` conditions, `safe_now` conditions, likely M33 detail codes, and future implementation order.
- Completed: linked the mapping document from README, architecture, protocol, and user manual.
- Validated: documentation review only; no firmware, ROS, CAN, NanoPi, or motor command was run.
- Safety: the document keeps current defaults as `unwired/confirmed=0/safe_now=0`; it does not enable `armed`, `active`, `motion_allowed`, or any motor output.
- Next step: once the real wiring/pin choices are known, implement read-only M33 raw input diagnostics for one input at a time, starting with emergency stop.

### 2026-05-26 - M33 safety input pin preselection

- Completed: based on the provided 40Pin RPI-compatible header image, preselected only physical pin 11 / `GPIO0` / `RPI_GPIO_10` for estop.
- Completed: updated power to `not_used_no_power_ok_input` and limits to `software_joint_limits_user_configured`; user clarified only estop should use GPIO, while speed limits and joint limits will be changed in M33 code later.
- Completed: documented fail-safe electrical semantics: estop uses a normally-closed active-low safe loop.
- Validated: documentation-only update; no firmware, CAN, ROS, NanoPi, GPIO, or motor test was run.
- Safety: the estop GPIO must only receive 3.3V logic. Motor bus voltage, battery voltage, or 5V signals must not be connected directly.
- Next step: implement M33 read-only raw GPIO diagnostics for estop only, while leaving power OK unused and keeping speed/limits as user-configured code policies.

### 2026-05-26 - M33 code-configured limit checks

- Completed: M33 pre-arm now has separate placeholders for position limits, speed limits, and torque/current limits.
- Completed: `cmd_m33_prearm_check` prints `PREARM_CODE_LIMITS` with each limit class `confirmed` and `safe_now`.
- Completed: power OK is explicitly unused for this slice and no longer blocks pre-arm; estop and code-configured limits still default to unconfirmed/unsafe.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded.
- Safety: defaults still keep pre-arm failing. This does not enable `armed`, `active`, `motion_allowed`, or motor output.
- Next step: if the user wants, add read-only GPIO raw diagnostic for estop pin 11; user will later edit M33 code values for speed/position/torque-current limits.

### 2026-05-26 - M33 development bench motion gate

- Completed: M33 branch adds `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` for powered bench development only.
- Completed: development gate changes `0x322` to `ok/armed` so NanoPi can pass limited `0x320 set_target` commands during bench tests.
- Completed: M33 now audits `0x320` before output: ROS joint id must be valid, target must be within `-60°~+60°`, speed within `-5~+5 rpm`, and `torque_ma=0`.
- Completed: fixed ROS `0-based` joint id to M33 internal `1-based` motor joint mapping before applying a target.
- Completed: removed the double-execution path when logging-only is disabled; a valid command is assessed once and applied once.
- Validated: forced ARM GCC compile of `Debug/applications/control/control_layer.o` succeeded without warnings.
- Not validated: not flashed yet, no NanoPi live CAN check, no `0x320`, and no motor motion in this slice.
- Safety: this is a development bench mode, not final wearable pre-arm safety. Formal path still requires real estop and final code-configured limits before human-worn motion.
- Next step: user flashes M33, then run NanoPi live status check and one tiny single-joint ROS trajectory while observing M33 serial logs.

### 2026-05-26 - M33 bench firmware flashed, NanoPi SSH blocked

- Completed: user reported the M33 bench-motion firmware was flashed.
- Attempted: Windows host tried SSH to `pi@192.168.2.66` for post-flash NanoPi/CAN validation.
- Observed: initial SSH attempt timed out; later attempts established TCP connection but remote closed/reset during SSH banner exchange.
- Observed: `Test-Connection 192.168.2.66` timed out, while SSH debug showed `Connection established` followed by `kex_exchange_identification: Connection closed/reset by remote host`.
- Not validated: could not run `ip -details link show can0`, `candump`, ROS bridge status, `0x322` parse, or any tiny trajectory.
- Safety: no `0x320` was sent and no motor motion was attempted because M33/NanoPi logs were not observable from this host.
- Next step: on-site check NanoPi SSH service/network, then rerun live status check before any movement command.

### 2026-05-26 - M33 bench motion live validation for motor3 and motor7

- Completed: NanoPi SSH recovered with password login `pi/pi`.
- Validated: `can0` was brought up as classic CAN 1Mbps and reported `UP/LOWER_UP/ERROR-ACTIVE` with `tx=0 rx=0`.
- Validated: after flashing M33 commit `a9310432`, bridge heartbeat `0x321` received M33 status `0x322#A5xx070000030000`, decoded as `ok/armed/detail=none`.
- Completed: started `rehab_arm_psoc_bridge` with `enable_target_tx=true`.
- Validated formal path for motor3: published ROS trajectory `shoulder_abduction_joint=0.02 rad`; bridge sent `0x320#03020B0005000000`; M33 emitted CANSimple frames `0x067/0x068`, confirming ROS joint2 -> M33 motor joint3.
- Completed direct debug pulse for motor7: used `nanopi_can_master.py private speed --motor 7 --vel 0.05 --kd 1.0`, held about 0.3s, then sent private `stop`.
- Observed: motor7 private active-report and M33 status slot `0x336` changed during motion and returned to stopped telemetry; M33 `0x322` stayed `ok/armed/detail=none`.
- Safety: motor3 was through the formal ROS->NanoPi->M33 chain; motor7 was direct NanoPi private CAN debug only and must not be treated as the formal control path.
- Next step: extend the formal M33/ROS mapping so motor7 can be commanded through `0x320` under M33 safety checks instead of direct private CAN.

### 2026-05-26 - Motor3 larger visible ROS/M33 bench motion

- Completed: rejected the user's requested `90°` as it exceeds the current bench safety gate and bridge limits.
- Completed: sent a larger but still bounded formal ROS trajectory for motor3: `shoulder_abduction_joint=0.75 rad` (about `43°`).
- Validated: bridge transmitted `0x320#0302AD0105000000`, which decodes as ROS joint2, `429 * 0.1°`, `5 rpm`, `torque_ma=0`.
- Observed: M33 emitted CANSimple frames `0x067/0x068` after the command, and `0x322` stayed `ok/armed/detail=none`.
- Safety: did not bypass the configured `±60°` M33 bench gate or the NanoPi bridge joint limit; did not send a `90°` target.
- Next step: add a formal ROS/M33 mapping for motor7 so visible 7号 motion can also go through `0x320` instead of direct private CAN.

### 2026-05-26 - Motor3 no-motion diagnosis and motor7 obvious pulse

- Observed: user reported the larger motor3 command did not visibly move.
- Diagnosed: passive and direct checks showed M33 heartbeat/status was healthy, but no real CANSimple heartbeat/feedback from motor3 was observed; M33 `0x332` motor3 telemetry stayed zeroed.
- Inference: prior `0x067/0x068` frames were command traffic/SocketCAN echo, not proof that motor3 entered closed-loop or executed position.
- Completed: ran a more visible direct private-CAN pulse on motor7: `--motor 7 --vel 0.30 --kd 1.0`, held about 1s, then sent stop and disabled active-report.
- Observed: motor7 active report changed from idle `0x180007FD#A545...` to moving `0x188007FD#...` frames, M33 `0x336` slot telemetry changed during motion, then returned to stopped values.
- Completed: stopped the `enable_target_tx=true` ROS bridge after the live test to avoid unintended later trajectory execution.
- Safety: motor7 pulse was still direct debug CAN, not formal path. No 90° command was sent.
- Next step: fix motor3 closed-loop/feedback bring-up separately, and add formal motor7 mapping through M33 before using ROS trajectories for 7号.

### 2026-05-26 - Motor7 repeat live pulse and quiet-state check

- Completed: repeated a direct private-CAN 7号 pulse after user requested another motion test.
- Validated: NanoPi SSH `pi/pi` worked, no ROS bridge process was running, and `can0` stayed classic CAN 1Mbps `ERROR-ACTIVE` with `tx=0 rx=0`.
- Completed: sent `active-report`, `private speed --motor 7 --vel 0.30 --kd 1.0`, held about 1s, then sent `private stop` and disabled active-report.
- Observed: motor7 feedback changed during motion on `0x188007FD`, and M33 aggregate slot `0x336` changed from stopped to moving and back to stopped.
- Validated: after the stop, a 1s `candump` quiet check saw no remaining active-report traffic and no ROS bridge process was left running.
- Safety: this remains a direct debug-only validation of motor7. It does not prove the formal `JointTrajectory -> NanoPi -> M33 -> motor7` path yet.
- Next step: implement formal M33/ROS mapping for motor7 under the same safety audit path instead of using direct private CAN.

### 2026-05-26 - Motor7 feedback mapping invalidated and motor3 direct CANSimple test

- Completed: stopped the prior continuous 7号 direct speed command before starting the bounded test.
- Attempted: ran a direct private-CAN 7号 software-stop test that reads active feedback, commands about `5 rpm`, and stops when the decoded relative value reaches about `55°`.
- Invalidated: user observed the motor rotated far more than `55°`; therefore the current private feedback position mapping is not a trusted joint/output angle.
- Observed: decoded 7号 feedback progressed from `93.77°` to about `148.89°`, but this value must be treated only as a raw protocol-derived field until calibrated.
- Completed: tested 3号伺泰威 through direct CANSimple with gearbox ratio noted as `48:1`: clear errors, closed-loop, velocity command `4.0 rad/s` motor-side for about 3s, then zero velocity and idle.
- Observed: 3号 command frames `0x078`, `0x067`, `0x06B`, and `0x06D` were sent, but M33 aggregate `0x332` stayed zeroed, so real motor3 execution/feedback is still unproven.
- Safety: 7号 and 3号 were both force-stopped after the tests. The attempted 7号 software stop is not acceptable as a safety limit until the angle mapping is calibrated against real motion.
- Next step: calibrate 7号 feedback-to-output-angle using marked physical rotations or official protocol fields, and decode or obtain real 3号 feedback/heartbeat before increasing commands.

### 2026-05-26 - Motor7 timed calibration pulse

- Completed: ran 7号 direct private-CAN at about `5 rpm` (`0.524 rad/s`) for exactly `3s`, then sent `stop` and disabled active-report.
- Validated: `can0` stayed `ERROR-ACTIVE`; after stop, quiet check showed no continuing `0x180007FD/0x188007FD` active-report stream.
- Observed: M33 aggregate `0x336` changed during motion and returned to stopped state after the stop.
- Confirmed by user: the 3s pulse moved roughly `150°` at the visible output face.
- Inferred: current direct private speed command `5 rpm` produced about `50°/s` output motion, or about `8.33 rpm` at the visible output face, so the command unit/path must be calibrated before it is treated as physical output rpm.
- Safety: this was a timed low-speed calibration pulse only. It did not rely on the invalidated feedback angle mapping.
- Next step: repeat with a clear tape/paint mark on the output face and a fixed camera, then derive a first calibration ratio for 7号 output motion.

### 2026-05-26 - RobStride motor model and gear ratio correction

- Completed: user confirmed 4号/5号 are RS00, and 6号/7号 are EL05.
- Verified from local official RobStride materials: RS00 reduction ratio is `10:1`; EL05 reduction ratio is `9:1`.
- Corrected: 3号伺泰威 reduction ratio remains `48:1`; user clarified an intermediate `40:1` note was wrong.
- Completed: updated README, motor protocol documentation, user manual, and troubleshooting notes to stop treating 4/5/6/7 model assignment as unknown.
- Safety: 3号 has received CANSimple commands but has not been visually confirmed to move; it remains execution-unproven. Official gear ratios do not make the current 7号 feedback angle mapping safe.
- Next step: update M33/NanoPi motor model tables so RS00 and EL05 use separate decoding/limit policies.

### 2026-05-26 - NanoPi motor model table for telemetry decoding

- Completed: updated `candump_motor_telemetry.py` with confirmed model metadata: 3号 `48:1`, 4/5号 RS00 `10:1`, 6/7号 EL05 `9:1`.
- Completed: 3号 CANSimple telemetry now carries `gear_ratio=48.0` and `execution_status=command_sent_but_motion_not_visually_confirmed`.
- Completed: 4/5号 RS00 active-report can use the existing local RS00 sample limits for engineering decode.
- Completed: 6/7号 EL05 active-report keeps raw fields plus confirmed `actuator_type=EL05` and `gear_ratio=9.0`; it does not pretend to know EL05 position/velocity/torque limits yet.
- Validated: `python -m unittest rehab_arm_ros2_ws.src.rehab_arm_psoc_bridge.test.test_candump_motor_telemetry` passed, `14` tests.
- Safety: this is telemetry/data decoding only. It does not enable motion and does not make 7号 feedback angle safe for limit-stop.
- Next step: add M33-side motor model/limit tables for RS00 and EL05, keeping EL05 raw/limited until official field ranges are confirmed.

### 2026-05-26 - M33 joint calibration gate

- Completed: checked RobStride official GitHub material (`RobStride/SampleProgram`, `RobStride/EDULITE_A3`, `RobStride/Product_Information`) for private protocol ranges and EDULITE joint mapping.
- Confirmed from official sources: EL05 uses `P=±12.57 rad`, `V=±50 rad/s`, `T=±6 Nm`, reduction `9:1`; RS00 uses `P=±12.57 rad`, `V=±33 rad/s`, `T=±14 Nm`, reduction `10:1`.
- Completed M33 safety update: added per-joint `CALIBRATED`, `DIRECTION`, and `ZERO_OFFSET_RAD` config macros, all defaulting to uncalibrated.
- Completed M33 guard: ROS `set_target` and `motor_pos` absolute position control now reject uncalibrated joints with `joint_uncalibrated`; stop commands remain allowed.
- Completed M33 diagnostic shell command: `m33_joint_calib [joint]` prints calibration gate, direction, gear ratio, and zero offset.
- Completed NanoPi parser update: `0x322 detail_code=11` decodes as `joint_uncalibrated`.
- Validated: `python -m pytest rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/test/test_psoc_status.py` passed, `10` tests.
- Failed or unverified: local M33 compile was not run because `scons` is not installed on this Windows environment.
- Safety: do not send ROS absolute position targets again until the target joint has a measured software zero, direction, scale, and conservative limits.
- Next step: flash this M33 safety build, then perform a non-motion test that a legal `0x320 set_target` for joint4/motor7 is rejected as `joint_uncalibrated`.

### 2026-05-26 - M33 joint calibration gate live validation

- Completed: user flashed M33 commit `daf78140`.
- Validated NanoPi SSH and CAN: `192.168.2.66`, `can0` classic CAN 1Mbps, `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Validated M33 heartbeat before target: `0x322#A53D070001010A00`, decoded as `limited/logging_only/detail=logging_only_no_motor_output`.
- First attempt: sent `0x320#0304320001000000` before refreshing heartbeat; M33 rejected with `0x322#A53E070001010100`, `detail_code=1 heartbeat_timeout`.
- Completed correct-order test: sent heartbeat `0x321#3F`, then legal target `0x320#0304320001000000` for ROS joint4/motor7, then heartbeat `0x321#40`.
- Validated expected result: M33 replied `0x322#A540070001010B00`, `detail_code=11 joint_uncalibrated`.
- Validated no formal 7号 motor output in filtered capture: no `01800007`, `0300FD07`, `180007FD`, or `188007FD` frames appeared around the target.
- Safety: this proved the uncalibrated absolute-position gate is active on the live M33 firmware. Do not enable per-joint `CALIBRATED=1` until zero/direction/scale are measured.
- Next step: add a calibration-only read/jog workflow for 7号 that does not use absolute position targets.

### 2026-05-26 - M33 calibration telemetry active-report gate

- Completed: added `CONTROL_CALIBRATION_ACTIVE_REPORT_ENABLE` to M33, default `1U`.
- Completed: M33 safety assessment now treats NanoPi `0x320 active-report` as calibration telemetry, not absolute motion.
- Completed: even while `CONTROL_ROS_COMMAND_LOGGING_ONLY=1`, accepted `active-report` commands apply through `control_motor_set_active_report()` and log `apply_calibration_telemetry_only`.
- Preserved: `enable`, `zero`, `mode`, and `target` remain blocked by logging-only / calibration gates; `joint_uncalibrated` still blocks absolute position targets.
- Validated locally: static grep confirmed the active-report path and `python -m pytest rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/test/test_psoc_status.py` passed, `10` tests.
- Failed or unverified: local M33 compile was not run because `scons` is not installed on this Windows environment.
- Safety: active-report is telemetry-only, but it still sends a motor protocol frame; after each test, send `m33 active-report --joint <id>` without `--enable-report` to turn it off.
- Next step: after flashing, live-test `m33 active-report --joint 4 --enable-report` and confirm 7号 telemetry appears without any 7号 control frame.

### 2026-05-26 - M33 calibration telemetry active-report live validation

- Completed: user flashed M33 commit `9e1573d7`.
- Validated NanoPi/CAN before and after test: `can0` classic CAN 1Mbps, `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Completed: sent heartbeat, then `0x320#060401` (`m33 active-report --joint 4 --enable-report`), then later `0x320#060400` to disable it.
- Validated M33 formal telemetry path: M33 emitted `0x1800FD07#0102030405060100` to enable 7号 active-report and `0x1800FD07#0102030405060000` to disable it.
- Validated telemetry arrived: capture included `176` frames of `0x180007FD` and `27` frames of M33 aggregate `0x336`.
- Validated no 7号 motion-control frames appeared: `01800007=0`, `0300FD07=0`.
- Validated post-disable: no continued `0x180007FD/0x188007FD` stream; only periodic cached M33 aggregate `0x336` remained.
- Note: the first SSH wrapper timed out because its timeout was shorter than the remote capture/command window; the capture file was complete and was inspected afterward.
- Safety: this proves formal M33 calibration telemetry is available without absolute position/velocity/torque commands.
- Next step: add a bounded calibration-jog command path or use telemetry-only captures to compute software zero/direction before any calibrated position control.

### 2026-05-26 - Calibration observation report tool

- Completed: added `calibration_observation.py` to summarize candump captures from the M33 active-report calibration path.
- Completed: the report counts active-report enable/disable frames, raw 7号 telemetry, M33 `0x336` aggregate samples, and any forbidden motion-control frames.
- Completed: installed command entry as `calibration_observation`.
- Validated: `python -m pytest rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/test/test_calibration_observation.py rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/test/test_candump_motor_telemetry.py` passed, `17` tests.
- Validated: local CLI smoke test produced `schema_version=rehab_arm_calibration_observation_v1`, `observation_ok=true`, `no_motion_control_frames=true`.
- Safety: the tool explicitly marks `safe_to_use_as_motion_proof=false`; this is telemetry observation only, not permission to enable calibrated position control.
- Next step: use this report during the next live zero/direction capture, then derive a candidate software zero offset before enabling any joint calibration flag.

### 2026-05-26 - M33 direct bench trial for motor7

- Completed: simplified the M33 bench path for the not-installed phase: `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` and `CONTROL_MOTOR_JOINT7_CALIBRATED=1U`.
- Behavior: 7号 uses zero offset `0`, direction `+1`, gear ratio `9:1`, ROS joint4 limit `±60°`, and existing `CONTROL_ROS_MAX_TARGET_RPM=5`.
- Safety: this is only for空载台架试错, not wearable approval. Start with `joint4 +5°/-5°`; stop immediately if direction or magnitude is wrong.
- Validated: `git diff --check -- applications/control/control_layer.c applications/control/control_layer_cfg.h` passed in the M33 repo.
- Failed or unverified: local M33 build was not run because `scons` is not installed on this Windows environment.
- Next step: user flashes M33, then send a small NanoPi `m33 target --joint 4 --deg 5 --rpm 1` through the formal path.

### 2026-05-26 - Motor7 formal-path 5 degree live trial

- Completed: after user flashed M33 commit `675db4ff`, ran NanoPi formal M33 path for ROS joint4/motor7 with `+5°`, `rpm=1`, then sent `stop`.
- Validated: `can0` stayed classic CAN 1Mbps, `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Validated: heartbeat before and after returned `0x322` with `detail_code=0`.
- Validated: M33 emitted 7号 frames `0x0300FD07` and `0x01800007`; stop emitted `0x0400FD07`.
- Validated: M33 aggregate `0x336` changed from motor7 enabled (`flags=0x01`) during target to disabled (`flags=0x00`) after stop.
- Failed or unverified: physical motion direction and magnitude require user visual confirmation; Codex can only see CAN telemetry.
- Safety: this proves the formal path can issue motor7 commands in bench mode. It does not prove zero, direction, or physical angle scale are correct.
- Next step: user confirms whether 7号 visibly moved; if yes, test `-5°`; if direction or magnitude is wrong, adjust M33 direction/scale before increasing angle.

### 2026-05-26 - Motor7 direct official CSP flow trial

- Completed: user reported the formal-path `+5°` trial caused a fast multi-turn motion, so additional formal-path targets were stopped.
- Completed: sent direct private-protocol stop frames to motor7; CAN remained `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Completed: tested direct MIT-style motor-side targets; CAN feedback changed but user reported no visible physical motion for the small direct target.
- Completed: tested official RobStride-style CSP sequence on motor7: write `run_mode=5` (`0x7005`), enable, write `limit_spd=0.5` (`0x7017`), write `loc_ref=1.05 rad` (`0x7016`), then stop.
- Validated: CAN frames were emitted as expected: `0x1200FD07` for parameter writes, `0x0300FD07` enable, `0x0400FD07` stop.
- Observed: M33 aggregate `0x336` moved from about `0.554 rad` to about `1.050 rad` after the official CSP flow.
- Failed or unverified: user has not confirmed visible physical motion for the CSP trial; if no visible motion occurred, feedback/parameter position is not yet proven to match the visible output joint.
- Next step: read official load-side/mechanical position parameters such as RobStride `0x7019 mechPos`, compare before/after with video/visual output, then correct the meaning of M33 `pos_rad`.

### 2026-05-26 - Motor7 RobStride position scale confirmed

- Completed: repeated official CSP flow from about `3.0 rad` back to `1.0 rad`; user visually confirmed the physical output moved about `114.4°`.
- Decision: for motor7/EL05, the RobStride `loc_ref` and M33 `0x336 pos_mrad` value match the visible output-side angle in this bench setup. Do not divide this value by the `9:1` gearbox ratio in the M33 ROS joint mapping.
- Completed M33 config update: set `CONTROL_MOTOR_JOINT7_GEAR_RATIO=(1.0f)` for the formal ROS path.
- Completed M33 bench zero update: set `CONTROL_MOTOR_JOINT7_ZERO_OFFSET_RAD=(1.0f)` because the last confirmed physical bench position is about `1.0 rad`; ROS joint4 `0°` now maps to that current bench pose.
- Safety: this is still a temporary bench calibration. Other EL05/RS00 joints are not automatically proven by this single motor7 observation.
- Next step: user flashes M33, then test formal path `joint4 +5° rpm=1`; expected physical output is about `5°`, not `45°` or `114°`.

### 2026-05-26 - Motor7 formal-path fixed-scale retest

- Completed: user flashed M33 commit `5b1f14f6`.
- Completed: ran formal path `m33 target --joint 4 --deg 5 --rpm 1 --torque-ma 0`, waited briefly, then sent `m33 stop --joint 4`.
- Validated: heartbeat before/after returned `0x322` with `detail_code=0`; can0 stayed `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Validated: formal path emitted motor7 enable/control/stop frames: `0x0300FD07`, `0x01800007`, `0x0400FD07`.
- Observed: M33 `0x336` reported motor7 at `0x03F1 = 1009 mrad`, only about `0.5°` from the temporary `1.0 rad` bench zero, not the expected `+5°`.
- Failed or unverified: physical motion requires user confirmation; CAN indicates the formal MIT frame was sent, but the final position did not reach `1.087 rad`.
- Next step: if the user saw no meaningful motion, change M33 formal private control for motor7 from MIT frame control to the official CSP flow (`run_mode=5`, `limit_spd=0x7017`, `loc_ref=0x7016`) that already produced visible 114° movement.

### 2026-05-26 - Lingzu formal path switched to CSP

- Completed: changed M33 `control_joint_motor_set_target()` so private-protocol motor targets call `control_motor_position_control(..., csp_mode=true)` instead of sending a MIT control frame.
- Behavior: formal `0x320 set_target` for Lingzu motors now uses the already-validated RobStride sequence: `run_mode=5`, enable, write `limit_spd(0x7017)`, write `loc_ref(0x7016)`.
- Completed: set M33 ROS mapping `CONTROL_MOTOR_JOINT4/5/6/7_GEAR_RATIO=(1.0f)` so all four Lingzu motors use RobStride output-side angle units in the formal path.
- Preserved: motor3 CANSimple path remains separate and is not affected by this private-protocol CSP change.
- Validated: `git diff --check -- applications/control/control_layer.c applications/control/control_layer_cfg.h` passed in the M33 repo.
- Failed or unverified: local M33 build was not run because `scons` is not installed on this Windows environment.
- Next step: user flashes M33, then test formal joint4 `+5°`; after that test 4/5/6/7 one at a time with small angles.

### 2026-05-26 - Motor7 CSP retest still showed old MIT firmware

- Completed: tested formal path `m33 target --joint 4 --deg 5 --rpm 1` after the CSP code change was pushed.
- Observed: capture still showed `0x01800007` MIT control and no `0x1200FD07` parameter-write frames.
- Conclusion: the board was still running firmware without commit `e9a76441`, or the flashed artifact was not built from the latest M33 branch.
- Safety: no further formal target scaling conclusions should be drawn from this test because it did not exercise the intended CSP path.
- Next step: rebuild/flash M33 commit `e9a76441`, then repeat and confirm `0x1200FD07` appears for `run_mode`, `limit_spd`, and `loc_ref`.

### 2026-05-26 - Motor7 formal CSP path live validation

- Completed: after flashing the CSP M33 firmware, ran formal path `m33 target --joint 4 --deg 5 --rpm 1 --torque-ma 0`, then `m33 stop --joint 4`.
- Validated: formal path emitted the expected RobStride CSP parameter writes: `0x1200FD07` count `3` (`run_mode=5`, `limit_spd`, `loc_ref`).
- Validated: no old MIT control frame appeared: `0x01800007` count `0`.
- Validated: `loc_ref` payload `8C2B8B3F` decodes to about `1.087 rad`, matching temporary zero `1.0 rad + 5°`.
- Validated: heartbeat before/after returned `0x322` with `detail_code=0`; can0 stayed `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Observed: stop emitted `0x0400FD07`; post-stop M33 aggregate reported motor7 around `0x043F = 1.087 rad`.
- Next step: user confirms visible motion was about `5°`; if yes, repeat `-5°`, then test 4/5/6/7 one at a time.

### 2026-05-26 - Motor7 formal CSP 30 degree trial

- Completed: ran formal path `m33 target --joint 4 --deg 30 --rpm 1 --torque-ma 0`, waited about `1.8s`, then sent `m33 stop --joint 4`.
- Validated: formal path stayed on CSP: `0x1200FD07` count `3`, `0x01800007` count `0`.
- Validated: `loc_ref` payload `4905C33F` decodes to about `1.5236 rad`, matching temporary zero `1.0 rad + 30°`.
- Observed: post-stop M33 aggregate reported motor7 around `0x052F = 1.327 rad`, so the motor was moving toward the 30° target but stopped before reaching it due to short wait/low speed.
- Validated: heartbeat before/after returned `0x322` with `detail_code=0`; can0 stayed `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Next step: if the user confirms the observed partial motion is reasonable, repeat with a longer wait or higher rpm to reach the full `30°` target.

### 2026-05-26 - Motor3 CANSimple direct bring-up and bench zero

- Completed: direct-tested 3号 Sitaiwei CANSimple node3 with clear, closed-loop, velocity command, and idle.
- Validated: CANSimple heartbeat/status traffic was present; `0x061` heartbeat showed closed-loop state during the velocity test and idle after stop.
- Completed: ran a more visible direct velocity test: motor-side `8 rad/s` for about `2s`, then idle.
- Observed: M33 aggregate `0x332` moved from about `0.739 rad` to about `1.147 rad`, a change of about `23.4°`, consistent with a 48:1 output mapping.
- Completed M33 bench config update: set `CONTROL_MOTOR_JOINT3_CALIBRATED=1U` and `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(55.1f)` so current bench pose becomes ROS joint0 zero while retaining `48:1`.
- Safety: this is a temporary bench zero only; it does not validate the installed mechanical zero or final limits.
- Next step: user flashes M33, then test formal path `m33 target --joint 0 --deg 5 --rpm 1`; expected physical output is about `5°`.

### 2026-05-26 - Motor3 Sitaiwei open-source driver check

- Completed: re-checked the 3号 Sitaiwei/SteadyWin driver route after the user objected to blindly applying `x48`.
- Found: the local Sitaiwei manual exposes Python/C++/ROS/Arduino SDK routes and points the ROS/CAN path toward the ODrive CAN ecosystem.
- Found: the relevant open-source ROS2 driver is `odriverobotics/ros_odrive`; it provides CAN-bus ROS2 communication for ODrive-style controllers.
- Confirmed from ODrive CAN protocol docs: `Get_Encoder_Estimates` reports `Pos_Estimate` in `rev` and `Vel_Estimate` in `rev/s`; `Set_Input_Pos` also takes `Input_Pos` in `rev`.
- Decision: do not copy the RobStride 7号 `gear_ratio=1.0` conclusion onto 3号. For 3号 CANSimple, keep the motor-side unit conversion path until we deliberately switch to Sitaiwei MIT/output-axis RAD protocol.
- Next step: if 3号 formal CANSimple movement still disagrees with visual output, validate with direct CANSimple `pos`/`vel` captures first; if the user wants no gearbox conversion, implement a separate 3号 MIT-output-axis path instead of deleting the CANSimple ratio.

### 2026-05-26 - Motor3 direct +5 degree CANSimple validation

- Completed: ran a direct CANSimple incremental position test for 3号 from NanoPi, using the ODrive/CANSimple `rev` unit path.
- Commanded: current encoder was about `7.66448 rev`; target was `8.33114 rev`, equal to motor `+0.66667 rev`, which maps to output `+5°` if the 48:1 gearbox conversion is correct.
- Validated: encoder estimate moved from about `7.66448 rev` to `8.33206 rev`; measured delta `0.66758 rev`, which maps to output `5.0069°`.
- Safety: sent CANSimple idle afterward; `can0` remained `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Diagnosed: M33 formal path `m33 target --joint 0 --deg 5` still produced no 3号 position-control frame because the board returned `0x322 = A5 79 07 00 01 02 0B 00`; detail code `0x0B` means `JOINT_UNCALIBRATED`.
- Conclusion: 3号 motor/CANSimple path is working; the current blocker is the M33 formal safety calibration gate on the firmware currently running on the board.
- Next step: flash a M33 build that contains the latest joint3 bench calibration (`CONTROL_MOTOR_JOINT3_CALIBRATED=1U`, zero offset around `55.1 rad`) or deliberately keep the gate closed and continue only direct CANSimple bench tests.

### 2026-05-26 - Motor3 formal gate opened but current limit fix needed

- Completed: after the user flashed the M33 bench firmware, retried formal `m33 target --joint 0 --deg 5 --rpm 1`.
- Validated: M33 formal safety gate no longer rejected joint0; it emitted CANSimple node3 frames `0x06B` controller mode, `0x06F` limits, `0x067` closed-loop, and `0x06C` position target.
- Observed: 3号 encoder changed only about `0.00408 rev`, which maps to about `0.03°`, not the intended `5°`.
- Diagnosed: M33 `control_motor_position_control()` set CANSimple `Set_Limits` second float to `0.0`, so position mode likely had no usable current/torque limit.
- Completed M33 fix in branch `M33`, commit `ed1cfc49`: added `CONTROL_CANSIMPLE_POSITION_LIMIT_CURRENT=(5.0f)` and used it for CANSimple position `Set_Limits`; feed-forward torque remains `0`.
- Next step: user flashes M33 commit `ed1cfc49`, then retest formal joint0 `+5°` and only then try formal `+30°`.

### 2026-05-26 - Motor3 direct 30 degree timed attempt had no node feedback

- Completed: tried a direct CANSimple timed velocity pulse intended to approximate output `+30°`: motor-side `1 rev/s` for `4s`, then idle.
- Safety: command ended with CANSimple idle; `can0` stayed `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Observed: during this attempt no `0x061` heartbeat or `0x069` encoder estimate from node3 was captured; only M33 aggregate `0x332` cached status appeared.
- Failed or unverified: because node3 feedback was absent, this attempt cannot be treated as a successful 30° movement even if a command frame was sent.
- Next step: before any larger 3号 move, first confirm node3 `0x061/0x069` feedback is visible again, or have the user confirm visible motion while keeping the test as unverified in telemetry.

### 2026-05-26 - Motor3 node3 offline during follow-up probe

- User confirmed the attempted 30° move did not visibly move.
- Completed: passive-listened on `can0` for `2s`; captured `0` frames.
- Completed: sent node3 CANSimple probe/control frames `0x063 Get_Error`, `0x078 Clear_Errors`, `0x067 Closed-loop`, then `0x067 Idle`.
- Observed: after the probe, only M33 aggregate cache frames `0x332` appeared; no node3 `0x061` heartbeat or `0x069` encoder estimate appeared.
- Validated: NanoPi CAN stayed `ERROR-ACTIVE` and M33 heartbeat `0x321 -> 0x322` still worked.
- Conclusion: the current blocker is that 3号 Sitaiwei node is not presently responding on the bus; do not continue motion tests until node3 feedback is restored.
- Next step: check 3号 motor power/enable/CAN connection/protocol state, then re-run a passive `0x061/0x069` capture before sending any more 3号 motion commands.

### 2026-05-26 - Motor3 formal path moved but old zero caused overshoot

- Completed: node3 came back online; passive capture showed `0x061` and `0x069` again.
- Completed: retried formal `m33 target --joint 0 --deg 5 --rpm 1` with M33 current-limit fix.
- Validated: M33 emitted CANSimple position path frames with nonzero limit current: `0x06B`, `0x06F` payload ending in `0000A040` (`5.0f`), `0x067`, and `0x06C`.
- Observed: encoder moved from `0 rev` to about `5.594 rev`, which maps to output about `41.96°`, so the old bench zero was wrong after the driver/encoder reset.
- Diagnosed: M33 still had `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(55.1f)`, but node3 encoder estimate had reset to `0 rev`; formal `+5°` therefore targeted about `9.436 rev` rather than about `0.667 rev`.
- Completed M33 fix in branch `M33`, commit `abedf348`: reset `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(0.0f)` for the current uninstalled bench state.
- Safety: command ended with M33 stop and direct CANSimple idle; do not test 30° until the new zero-offset firmware is flashed and formal `+5°` is revalidated.
- Next step: user flashes M33 commit `abedf348`, then retest formal joint0 `+5°`; expected encoder target delta is about `0.6667 rev`, output about `5°`.

### 2026-05-26 - Motor zero source made explicit

- Completed M33 diagnostic hardening: `m33_joint_calib` now prints each joint's `zero_source` and a project-wide `JOINT_ZERO_POLICY`.
- Completed M33 config labels: joint3 zero source is `bench_volatile_encoder_zero_not_for_installed_robot`; joint7 zero source is `bench_temporary_visual_zero_not_for_installed_robot`.
- Decision: the current joint3 `zero_offset=0.0f` is a bench-only value after the Sitaiwei encoder reset, not a formal robot requirement.
- Architecture note: installed/wearable operation must use either persisted mechanical zero offsets or an explicit homing routine after power-up; otherwise absolute position control should stay rejected.
- Next step: flash the new diagnostic build, run `m33_joint_calib 3`, then retest formal joint0 `+5°` only after confirming the zero source is visible in logs.

### 2026-05-26 - Patient device profile protocol baseline

- Completed: added `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` as the shared protocol for platform, App, NanoPi, M33, M55, simulation, data collection and VLA.
- Defined: single active profile rule, role permissions, patient ROM/velocity/acceleration/current limits, training mode, fatigue/pain policy, model runtime settings, VLA permission level, data labeling requirements and synchronization conflict handling.
- Decision: first stage keeps one robot coordinate system and uses patient-specific ROM limits plus derived `rom_percent`; patient-relative coordinates are deferred to a future V2 only if training/generalization requires them.
- M33 boundary: receives only a safety subset and must combine device absolute limits with patient limits by taking the stricter value.
- M55 boundary: publishes `m55_model_result_v1` suggestions only; it cannot directly control motors or loosen M33 limits.
- App/platform boundary: both edit the same versioned Patient Device Profile; neither may maintain a private independent profile.

### 2026-05-27 - NanoPi power-on readonly ROS telemetry

- Completed: powered-on NanoPi check over SSH at `192.168.2.66`; `can0` was brought up as classic CAN 1Mbps and reported `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Validated: passive CAN capture saw M33 aggregate `0x332` plus CANSimple node3 `0x061/0x069`; filtered C8T6 range `0x7C0~0x7C3` still produced `0` frames.
- Validated: M33 heartbeat `0x321 -> 0x322` returned `A5 0C 07 00 00 06 00 00`, parsed as `state=ok`, `control_mode=bench_armed`, `motion_allowed=false`.
- Completed: ran `psoc_can_bridge_node.py` with `enable_target_tx=false`; ROS published `/rehab_arm/safety_state`, `/rehab_arm/motor_state`, and `/joint_states` without sending motor targets.
- Completed: recorded a power-on readonly JSONL session on NanoPi at `/home/pi/rehab_arm_logs/poweron-readonly-20260527-1923.jsonl`.
- Completed: added `poweron_readonly` recording topic profile so C8T6 absence does not fail this specific bring-up check; required topics are `/joint_states`, `/rehab_arm/safety_state`, and `/rehab_arm/motor_state`.
- Validated: local unit tests for the new profile passed; NanoPi `check_recording.py --topic-profile poweron_readonly` returned `ok=true` for the real log.
- Failed or unverified: NanoPi `colcon build --packages-select rehab_arm_psoc_bridge` failed because the board's ROS Jazzy Python environment could not import `ament_package`; pure Python files were copied into install as a temporary field update.
- Next step: repair NanoPi ROS build environment, sync the full latest bridge package, then repeat readonly capture with a fresh session id and C8T6 connected.

### 2026-05-27 - NanoPi ROS build wrapper fixed

- Completed: updated `rehab_arm_ros2_ws/build_ros2.sh` to add the active ROS distro Python site-packages path to `PYTHONPATH` after sourcing ROS.
- Completed: updated `scripts/nanopi_live_telemetry_check.sh` with the same ROS Python path handling and cleaner snapshot-disabled output.
- Validated on NanoPi: `./build_ros2.sh --packages-select rehab_arm_psoc_bridge` now builds successfully without a manual `PYTHONPATH=...` prefix.
- Validated on NanoPi: `check_recording.py --topic-profile poweron_readonly` returns `ok=true` after the normal build/install flow.
- Validated on NanoPi: `ACTIVE_REPORT_MOTOR=none ... /home/pi/nanopi_live_telemetry_check.sh` passed; it saw M33 `0x322`, `/rehab_arm/motor_state`, `/joint_states`, and no unexpected `0x320` target frames.
- Safety: no motion commands or `JointTrajectory` were sent in this task.
- Next step: when C8T6 is connected, run a fresh live check plus `hardware_telemetry` recording profile and require `/rehab_arm/sensor_state`.

### 2026-05-27 - C8T6/F103 sensor JSON contract prepared offline

- Completed: added `f103_sensor_state.py` with parsers for C8T6/F103 `0x7C2` sensor frames and `0x7C3` health frames.
- Completed: `psoc_can_bridge_node.py` now publishes structured `/rehab_arm/sensor_state` JSON for those frames instead of only raw hex fields.
- Defined: `0x7C2` outputs `rehab_arm_sensor_state_v1` with EMG raw/filter, heart-rate raw/bpm, validity flags, and `control_boundary=telemetry_only_not_motion_permission`.
- Defined: `0x7C3` outputs `rehab_arm_sensor_health_v1` with state, error count, queue fill, and the same telemetry-only boundary.
- Validated locally: `test_f103_sensor_state.py` passed 4 tests; `py_compile` passed for the new parser and bridge node.
- Validated on NanoPi: copied the files, ran the new unit test, rebuilt `rehab_arm_psoc_bridge`, and confirmed installed parser import decodes a sample heart rate as `75`.
- Safety: no CAN motion or C8T6 control command was sent; this was an offline contract/readiness change.
- Next step: when C8T6 is physically connected, passively capture `0x7C2/0x7C3`, confirm `/rehab_arm/sensor_state`, then run `hardware_telemetry` recording validation.

### 2026-05-27 - Simulation host readiness report made actionable

- Completed: extended `check_sim_env.py` with `missing_actions` and `next_commands`, so a new Linux simulation host report explains what to install or run next.
- Defined readiness meanings: `not_ready`, `ready_with_fallback_sim`, and `ready_with_mujoco`.
- Preserved safety boundary: the report remains read-only and does not access CAN, `0x320/0x321`, M33, or motors.
- Validated: `test_check_sim_env.py` passed 5 tests.
- Validated: local CLI smoke produced a JSON report with `ok=false` on Windows because `rclpy` is not installed, and correctly listed ROS2/rclpy remediation under `missing_actions`.
- Docs: updated the ROS2 simulation guide and user manual with the readiness report workflow.
- Next step: when the Linux simulation host is available, run `ros2 run rehab_arm_sim_mujoco check_sim_env --pretty --output sim_readiness_report.json`, then follow `missing_actions` until readiness is at least `ready_with_fallback_sim`.

### 2026-05-27 - Motor7 formal joint4 10 degree live motion

- Completed: user allowed moving 7号; interpreted as known motor7, not nonexistent motor77.
- Precheck: NanoPi `can0` was `UP/LOWER_UP`, classic CAN 1Mbps, `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Completed: sent formal M33 path command `m33 target --joint 4 --deg 10 --rpm 1 --torque-ma 0`, waited about 3s, then sent `m33 stop --joint 4`.
- Validated: NanoPi emitted `0x320#0304640001000000` for joint4 target and `0x320#020400` for stop.
- Validated: M33 emitted RobStride CSP frames for motor7: `0x1200FD07` run_mode `5`, `0x1200FD07` limit speed, `0x1200FD07` `loc_ref`, followed by stop `0x0400FD07`.
- Validated: no old MIT control frame `0x01800007` appeared in the filtered control-frame summary.
- Observed: M33 motor7 aggregate `0x336` changed from `position_mrad=-73` to about `174`, about `247 mrad` or `14.1°`; user should visually confirm whether this matches expected bench motion.
- Safety: sent stop after the move; post-test `can0` remained `ERROR-ACTIVE`, tx/rx error counters `0/0`; M33 heartbeat still returned `state=ok/control_mode=bench_armed/motion_allowed=false`.
- Next step: if the visible motion direction is correct, repeat with a smaller closed-loop validation sequence `+5°/-5°` and compare M33 `0x336` delta to commanded joint degrees before moving larger angles.

### 2026-05-27 - Motion test report tool for remote/offline review

- Completed: added `motion_test_report.py`, a read-only candump analyzer for formal M33 motion tests.
- The report checks target `0x320`, stop `0x320`, RobStride CSP parameter writes, private stop frames, absence of legacy MIT control frames, and M33 aggregate position deltas.
- Completed: added `motion_test_report.py` to the ROS package install list.
- Validated locally: `test_motion_test_report.py` passed 3 tests; `py_compile` passed.
- Validated with the real NanoPi log `/tmp/motor7_joint4_10deg.candump`: report returned `ok=true`, `has_expected_csp_sequence=true`, `stop_observed=true`, `no_legacy_mit_control=true`, and `delta_position_deg=14.152`.
- Validated on NanoPi: synced the latest bridge package, rebuilt `rehab_arm_psoc_bridge`, fixed the new script executable bit, and ran `ros2 run rehab_arm_psoc_bridge motion_test_report.py ...`.
- Safety: no additional motion was sent after the user said they were not on site; this task only analyzed existing logs.
- Next step: use this report after every future bench motion before deciding whether to repeat, reverse, or increase commanded angle.

### 2026-05-27 - Guarded bench motion sequence tool

- Completed: added `bench_motion_sequence.py` to generate a formal M33-path bench motion plan for motor7/joint4.
- Default sequence is dry-run only: heartbeat, `+5°`, hold, stop, `-5°`, hold, stop, heartbeat.
- Execution is guarded: `--execute` is rejected unless `--confirm-onsite` is also provided.
- Completed: added the script to ROS install lists and setup entry points.
- Validated locally: `test_bench_motion_sequence.py` passed 3 tests; `py_compile` passed; dry-run CLI printed the expected plan and did not access CAN.
- Validated on NanoPi: synced the script, ran its unit tests, rebuilt `rehab_arm_psoc_bridge`, and confirmed `ros2 run rehab_arm_psoc_bridge bench_motion_sequence.py --pretty` prints the dry-run plan.
- Safety: no new motor motion was sent because the user is not on site.
- Next step: when a human is on site, execute the guarded sequence only with `--execute --confirm-onsite`, capture candump, then validate it with `motion_test_report.py`.

### 2026-05-27 - Unified motor profile table, test only 3 and 7

- Decision: keep one unified motor profile table for all known motors instead of separate ad-hoc tools per motor.
- Completed: `bench_motion_sequence.py` now defines profiles for motor `3/4/5/6/7` with joint mapping, vendor, model and test status.
- Current mapping: motor3 -> joint0 Sitaiwei CANSimple/ODrive-like; motor4 -> joint1 Lingzu RS00; motor5 -> joint2 Lingzu RS00; motor6 -> joint3 Lingzu EL05; motor7 -> joint4 Lingzu EL05.
- Safety: execution allowlist is only motor `3` and motor `7`; motors `4/5/6` can be listed and planned but are rejected if `--execute` is used.
- Validated locally: `test_bench_motion_sequence.py` passed 6 tests; `--list-motors` prints all profiles; `--motor-id 4 --execute --confirm-onsite` returns an allowlist rejection.
- Validated on NanoPi: synced the updated tool, ran the 6 tests, rebuilt `rehab_arm_psoc_bridge`, and confirmed `ros2 run ... --list-motors --pretty` lists all five motors with execution allowlist `[3, 7]`.
- Safety: no motion commands were sent.
- Next step: when on site, test only motor7 and motor3 using the guarded sequence plus candump report; do not test 4/5/6 until their mechanical limits and risk review are ready.

### 2026-05-27 - Shared motor profiles module

- Completed: extracted the known motor table into `motor_profiles.py` so ROS tools, platform sync, App docs, and M33 safety exports can share one source of truth.
- Completed: `bench_motion_sequence.py --list-motors` now uses the shared payload instead of a private duplicated table.
- Current table: motor3 Sitaiwei CANSimple gear ratio `48`; motors4/5 Lingzu RS00; motors6/7 Lingzu EL05; execution allowlist remains `[3, 7]`.
- Validated locally: motor profile tests and bench motion sequence tests passed; `py_compile` and `git diff --check` passed.
- Safety: no NanoPi, CAN, M33, or motor motion was used in this step.
- Next step: sync this shared module to NanoPi and verify dry-run/list only after the board is available; do not execute motion without an on-site human.

### 2026-05-27 - Conservative patient profile template generator

- Completed: added `build_patient_profile_template.py` to generate a draft `patient_device_profile_v1` from the shared motor profile table.
- Defaults: 5 known joints, patient ROM `[-10, 10] deg`, patient speed `5 deg/s`, passive mode, VLA suggest-only, and emergency action `disable_motor_output`.
- Completed: installed the tool in the ROS package and added setup entry point `build_patient_profile_template`.
- Validated locally: `test_patient_profile.py` passed 14 tests; CLI `--validate --pretty` emitted a valid template envelope; `py_compile` and `git diff --check` passed.
- Safety: this is JSON generation/validation only; it does not contact NanoPi, CAN, M33, BLE, App, or platform.
- Next step: use this template as the platform/App shared starting point, then add profile sync quality gates before any active profile can reach M33.

### 2026-05-27 - Patient profile release gate

- Completed: added `check_patient_profile_release_gate.py` and `build_patient_profile_release_gate()` as the single release check before profile data reaches M33, App BLE, or NanoPi cache.
- Rules: M33 target requires `profile_status=active`; App BLE target requires approval metadata and a valid BLE safety package; NanoPi cache requires `approved` or `active`.
- Validated locally: patient profile and motor profile tests passed 23 tests; `py_compile` and `git diff --check` passed.
- Safety: release gate is JSON-only and never connects BLE, CAN, ROS topics, M33, NanoPi, or motors.
- Next step: add the same release gate command to the platform/App integration prompts so their agents call it before any sync button or BLE package export.

### 2026-05-27 - Simulation host and NanoPi ROS2 DDS link

- Completed: logged into simulation host `cal@192.168.2.46`; hostname is `cal-MS-7D90`, ROS distro is Jazzy.
- Completed: confirmed NanoPi `pi@192.168.2.66` and simulation host can ping each other on `192.168.2.0/24`.
- Completed: configured both machines with `ROS_DOMAIN_ID=42`, `ROS_LOCALHOST_ONLY=0`, and `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` via `~/.rehab_arm_ros2_network`.
- Validated: simulation host -> NanoPi ROS2 topic test passed using `/chatter`; NanoPi -> simulation host test passed using `/rehab_net_test`.
- Safety: only ROS2 demo/string topics were used; no bridge launch, CAN, M33 command, trajectory, or motor motion was sent.
- Next step: install/sync the rehab ROS2 workspace on the simulation host, then verify it can see NanoPi `/joint_states`, `/rehab_arm/safety_state`, and `/rehab_arm/motor_state` with target TX disabled.

### 2026-05-27 - Simulation host workspace and NanoPi bridge readonly check

- Completed: transferred the current feature branch to simulation host via Git bundle because the host could not fetch from GitHub over SSH or HTTPS.
- Completed: simulation host is on `feature/rehab-arm-ros2-architecture` at commit `0edee779`.
- Completed: built `rehab_arm_description`, `rehab_arm_sim_mujoco`, and `rehab_arm_psoc_bridge` on the simulation host.
- Fixed: `check_sim_env.py` and `upload_sim_readiness.py` needed executable bits for `ros2 run`.
- Validated: `check_sim_env.py` returned `ok=true`, `readiness=ready_with_fallback_sim`; only optional `mujoco` Python package is missing.
- Validated: NanoPi `can0` was brought up as classic CAN 1 Mbps, `ERROR-ACTIVE`, tx/rx counters `0/0`; bridge started with `enable_target_tx=false`.
- Validated from simulation host: ROS topics `/arm_controller/joint_trajectory`, `/joint_states`, `/rehab_arm/motor_state`, `/rehab_arm/safety_state`, and `/rehab_arm/sensor_state` were discoverable; `/rehab_arm/safety_state` produced a sample.
- Observed: short candump showed only `0x321` heartbeat and `0x322` M33 status; no `0x320` target or motor control frames. `/motor_state` and `/joint_states` had no sample during the short check because no M33 motor status frame appeared.
- Safety: no trajectory was published and no motor motion command was sent; the target-disabled bridge process was stopped after validation.
- Next step: make M33 publish motor status frames or enable the expected status source, then verify `/rehab_arm/motor_state` and `/joint_states` from the simulation host before any trajectory test.

### 2026-05-27 - M33 motor status presence checker

- Completed: added `check_m33_motor_status_presence.py`, a readonly candump checker for expected M33 motor telemetry IDs `0x330~0x337`.
- The report also counts `0x321` NanoPi heartbeat, `0x322` M33/PSoC status, and rejects unexpected `0x320` target frames during readonly checks.
- Validated locally: presence checker, candump telemetry, and synthetic M33 status tests passed 28 tests; `py_compile` and `git diff --check` passed.
- Validated on NanoPi: rebuilt `rehab_arm_psoc_bridge`; the new executable is visible through `ros2 pkg executables`; the new unit test passed.
- Real readonly result for `/tmp/simhost_bridge_readonly.candump`: `0x321=3`, `0x322=3`, `0x320=0`, valid `0x330~0x337=0`, so the current blocker is missing M33 motor telemetry frames rather than ROS2 discovery.
- Safety: no CAN write, trajectory, M33 command, or motor motion was sent by this checker.
- Next step: update or configure M33 firmware to emit `0x330~0x337` motor status frames, then rerun this checker before expecting `/motor_state` and `/joint_states` samples on the simulation host.

### 2026-05-27 - Feedback source readiness checker

- Completed: added `feedback_source_readiness.py`, a readonly candump report for现场快速现查.
- The report separates raw motor feedback sources from ROS-ready M33 telemetry: Sitaiwei CANSimple `0x061/0x069`, Lingzu active reports `0x180004FD~0x180007FD`, M33 `0x330~0x334` stale/fresh status, and unexpected `0x320` target frames.
- Completed: added the tool to the ROS package entry points and documented the NanoPi command in `docs/USER_MANUAL.md`.
- Validated locally: feedback readiness, M33 presence, and candump telemetry tests passed `25 passed`; `py_compile` passed.
- Validated on NanoPi: synced the tool, rebuilt `rehab_arm_psoc_bridge`, confirmed `ros2 run rehab_arm_psoc_bridge feedback_source_readiness.py` is installed, and ran it against `/tmp/feedback_source_readiness.candump`.
- Live readonly result: `0x330~0x334` were present with correct motor IDs `3/4/5/6/7`, all `240` M33 samples were stale, raw motor feedback count was `0`, `target_0x320_count=0`, and decision was `motor_feedback_source_missing`.
- Safety: this tool is read-only and does not send CAN, ROS trajectories, BLE commands, or motor commands.
- Next step: inspect motor-side power/CAN branch/IDs or M33 motor RX path before expecting `/joint_states` or running a trajectory.

### 2026-05-27 - NanoPi one-command feedback readiness script

- Completed: added `scripts/nanopi_motor_feedback_readiness.sh` for现场一键现查.
- Default mode is read-only: capture `can0`, run `feedback_source_readiness.py`, and save reports under `/tmp/rehab_arm_feedback_readiness`.
- Optional mode `SEND_M33_HEARTBEAT=1` sends one safe NanoPi heartbeat `0x321#55` during capture to check whether M33 replies.
- Optional mode `RUN_NON_MOTION_PROBES=1` sends only CANSimple `Get_Error/Address` and Lingzu `Get_ID` query frames, never enable/velocity/position/torque/trajectory commands.
- Completed: documented the command in `docs/USER_MANUAL.md`.
- Validated on NanoPi: `bash -n` passed; default passive run completed and saved reports. Current passive 5s capture had `0` parseable frames, so readiness failed as expected and printed result file paths instead of hiding the failure.
- Validated on NanoPi with `SEND_M33_HEARTBEAT=1 DURATION_SECONDS=3`: `can0` stayed `ERROR-ACTIVE`, but no `0x322`, no `0x330~0x334`, and no raw motor feedback appeared after heartbeat.
- Safety: the default script path sends no CAN writes; heartbeat and query modes are explicitly separated from default passive evidence.
- Next step: check whether M33 is powered/running after the latest reset or flash before debugging ROS trajectory or motor protocols.

### 2026-05-27 - ROS bridge fresh motor feedback trajectory gate

- Completed: `psoc_can_bridge_node.py` now requires recent fresh M33 motor feedback before accepting/sending `JointTrajectory` by default.
- Added parameter `require_fresh_motor_status_for_trajectory=true` and `motor_status_timeout_sec=1.0`.
- The existing M33/PSoC `motion_allowed=true` gate remains required; the new gate prevents stale `0x330~0x334` placeholder slots from being treated as known robot posture.
- Completed: added `fresh_motor_feedback_gate_detail()` in `safety_gate.py` and unit tests.
- Completed: documented the new bridge behavior and the dry-run override in `docs/USER_MANUAL.md`.
- Validated locally: safety, motor status, and joint-state tests passed `24 passed`; `py_compile` passed for the changed modules.
- Validated on NanoPi: synced the changed bridge files, rebuilt `rehab_arm_psoc_bridge`, and `test_safety_gate.py` passed `7 passed`.
- Safety: this is a stricter default gate; it sends no CAN during tests and makes missing feedback fail closed.
- Next step: run a dry-run bridge trajectory rejection test once M33 status is visible again.

### 2026-05-28 - Live NanoPi/M33 readiness and dry-run trajectory gate

- Completed: brought NanoPi `can0` back up as classic CAN 1 Mbps after it was found `DOWN/STOPPED`.
- Validated live readiness: passive capture saw `790` frames, raw 3号 CANSimple feedback (`0x061/0x069`), M33 `0x330~0x334`, and `48` fresh M33 motor samples; no `0x320` target frames.
- Validated with heartbeat: `SEND_M33_HEARTBEAT=1` saw M33 `0x322`, fresh M33 motor status, and no warnings after fixing the readiness parser.
- Fixed: `feedback_source_readiness.py` no longer misclassifies NanoPi heartbeat `0x321` as CANSimple node `25`.
- Fixed: `nanopi_motor_feedback_readiness.sh` now accepts `can <BERR-REPORTING> state ERROR-ACTIVE` as healthy.
- Validated ROS bridge dry-run: `/joint_states`, `/rehab_arm/motor_state`, and `/rehab_arm/safety_state` produced samples with `enable_target_tx=false`; candump saw no `0x320`.
- Validated trajectory gate: publishing a minimal `JointTrajectory` was rejected because M33 `motion_allowed` was not true (`state=ok`, `control_mode=bench_armed`, `detail=none`); no `0x320` was sent.
- Safety: no motor movement commands were sent; all trajectory checks kept `enable_target_tx=false`.
- Next step: update M33/app/platform control path so M33 only sets `motion_allowed=true` after the intended local safety condition is satisfied, then repeat dry-run acceptance before any real `0x320` motion test.

### 2026-05-28 - Explicit bench dry-run trajectory override

- Completed: added NanoPi bridge parameter `allow_bench_motion_for_trajectory=false` by default.
- Behavior: formal `armed/active + motion_allowed=true` remains the normal permission path; `bench_armed` is still rejected unless the new NanoPi parameter is explicitly set.
- Safety: the bench override only affects NanoPi trajectory acceptance; `enable_target_tx=false` still prevents actual `0x320` frames, and M33 still owns downstream safety if target TX is later enabled.
- Fixed tests: `psoc_motion_gate_detail()` now covers default bench rejection, explicit bench acceptance, and bench rejection when detail/error is nonzero.
- Validated locally: `test_safety_gate.py` passed `10 passed`; `py_compile` passed.
- Validated on NanoPi: rebuilt `rehab_arm_psoc_bridge`; `test_safety_gate.py` passed `10 passed`.
- Live dry-run validation: with `enable_target_tx=false` and `allow_bench_motion_for_trajectory=true`, publishing a minimal `JointTrajectory` logged `accepted 1 trajectory points` and `DRY-RUN 320 ...`; candump saw no real `0x320`.
- Next step: do not enable real target TX until the user explicitly requests a motion test and the bench area is confirmed safe.

### 2026-05-28 - Simulation host to NanoPi dry-run ROS trajectory link

- Completed: used simulation host `cal@192.168.2.46` as the upstream ROS publisher and NanoPi `pi@192.168.2.66` as the bridge host.
- Validated DDS discovery: simulation host saw NanoPi topics `/arm_controller/joint_trajectory`, `/joint_states`, `/rehab_arm/motor_state`, `/rehab_arm/safety_state`, and `/rehab_arm/sensor_state`.
- Completed: started one clean NanoPi bridge with `enable_target_tx=false` and `allow_bench_motion_for_trajectory=true`.
- Validated command path: simulation host published a minimal `JointTrajectory`; NanoPi bridge logged `accepted 1 trajectory points` and `DRY-RUN 320 joint=shoulder_lift_joint data=0300000005000000`.
- Validated safety boundary: candump of `can0,320:7FF` remained empty, so no real `0x320` target was sent.
- Validated feedback path: simulation host successfully echoed `/joint_states` from NanoPi.
- Cleanup: stopped the temporary NanoPi bridge and candump processes after the test.
- Safety: no motor movement commands were sent; this was cross-machine ROS dry-run only.
- Next step: when MuJoCo is ready, replace the manual `ros2 topic pub` with a simulator/planner-generated `JointTrajectory` while keeping NanoPi `enable_target_tx=false`.

### 2026-05-28 - Official MuJoCo configured on simulation host

- Completed: installed the official MuJoCo Python package on simulation host `cal@192.168.2.46` with `python3 -m pip install --user --break-system-packages mujoco`.
- Installed version: `mujoco 3.9.0`.
- Completed: configured headless rendering with `export MUJOCO_GL=egl` in `~/.rehab_arm_ros2_network`.
- Validated official MuJoCo smoke test: imported `mujoco`, loaded an MJCF XML string, created `MjModel/MjData`, ran `mj_step`, and rendered a `64x64x3` RGB frame with nonzero pixel sum using EGL.
- Validated project strict check: `ros2 run rehab_arm_sim_mujoco check_sim_env.py --strict-mujoco --pretty` returned `ok=true`, `readiness=ready_with_mujoco`, `checks.mujoco.ok=true`, and `errors=[]`.
- Validated ROS sim node: `ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py` logged `backend=mujoco-python-available` and published 5-joint `/joint_states`.
- Notes: default GLFW render failed under SSH because `DISPLAY` was missing; OSMesa was not configured, but EGL works and is the chosen headless path.
- Safety: this task only changed the simulation host Python/user environment; no NanoPi CAN, M33 command, `0x320`, or motor motion was used.
- Next step: replace the current fallback-first-order sim internals with a real MuJoCo model path while preserving the same `/arm_controller/joint_trajectory` and `/joint_states` ROS contract.

### 2026-05-28 - MuJoCo model backend wired into ROS sim node

- Completed: added `rehab_arm_sim_mujoco.mujoco_backend` with a minimal 5-joint MJCF model, standard joint contract, joint limit clamping, and a MuJoCo-backed kinematic step path.
- Completed: updated `mujoco_sim_node.py` so MuJoCo availability now uses `backend=mujoco-model`; fallback remains available when MuJoCo cannot load.
- Safety decision: first real MuJoCo slice uses velocity-limited kinematic stepping inside MuJoCo instead of unconstrained position-actuator dynamics, because the first actuator attempt produced unstable acceleration warnings and out-of-limit joint values.
- Validated locally: `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test -v` passed 12 tests.
- Validated on simulation host: rebuilt `rehab_arm_sim_mujoco`, started `mujoco_sim_node.py`, published a 5-joint `JointTrajectory`, and echoed `/joint_states`.
- Validation result: node log contained `backend=mujoco-model`; `/joint_states` reached `[0.3, 0.5, 0.1, 0.2, -0.2]` within tolerance; no MuJoCo `Nan, Inf or huge value` warning was emitted after switching to the kinematic backend.
- Safety: no NanoPi CAN, M33 command, `0x320`, or motor motion was used.
- Next step: add a proper MJCF/URDF asset file path and a repeatable sim launch/trajectory demo that records a short dataset for platform annotation.

### 2026-05-28 - MuJoCo model moved to installable asset file

- Completed: added `rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml` as the default MJCF asset instead of relying only on generated XML inside Python code.
- Completed: installed the `models/` directory into the ROS package share path and added `ament_index_python` so the sim node can find the installed model.
- Completed: added `model_path` ROS parameter to `mujoco_sim_node.py`; empty value loads the default installed model, explicit path can be used later for real MJCF/URDF-converted models.
- Validated locally: `python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_sim_mujoco\test -v` passed 15 tests.
- Validated on simulation host: rebuilt `rehab_arm_sim_mujoco`; confirmed installed model exists at `install/rehab_arm_sim_mujoco/share/rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml`.
- Validated trajectory path: node started with `backend=mujoco-model`, published a 5-joint trajectory, and `/joint_states` reached `[0.2, 0.4, 0.05, 0.1, -0.1]` within tolerance.
- Safety: no NanoPi CAN, M33 command, `0x320`, or motor motion was used.
- Next step: add a repeatable sim launch/demo capture that produces a short dataset for platform annotation and later VLA/model training checks.

### 2026-05-28 - Motor4 tiny formal-path motion attempt

- Completed: attempted a small M33 formal-path motor4 test from NanoPi after user requested 4号电机小幅度运动.
- Initial blockers: Windows `COM26` was busy, so M33 serial shell direct command could not be used; NanoPi `can0` was initially `DOWN/STOPPED`.
- Fixed live setup: used NanoPi password `pi` with `sudo -S`, brought `can0` up as classic CAN 1Mbps with `berr-reporting on`; final bus state was `ERROR-ACTIVE`, tx/rx error counters `0/0`.
- Commands sent:
  - heartbeat `0x321#48`, received `0x322#A548070000060000`.
  - pre-stop `0x320#020100` for ROS joint1 -> motor4.
  - tiny target `0x320#0301140001000000` for ROS joint1/motor4, target `+2.0 deg`, `1 rpm`, `0 torque_ma`.
  - post-stop `0x320#020100`.
  - heartbeat `0x321#49`, received `0x322#A549070000060000`.
- Observed CAN: M33 forwarded motor4 stop frame `EXT 0x0400FD04`; motor4 telemetry/status appeared in `0x331`, including fresh data before/after and stale transition during the test window.
- Unverified: no M33 serial log because `COM26` was locked by another process; no visual confirmation from user yet about physical movement.
- Safety: test used small absolute target and immediate stop; no ROS bridge was started.

### 2026-05-28 - Motor4 10 degree formal-path retry

- Reason: user reported no visible motion from the previous `+2 deg` motor4 attempt.
- Completed: retried through the formal NanoPi -> M33 `0x320` path for ROS joint1/motor4 with `+10 deg`, `2 rpm`, `0 torque_ma`, held about 3 seconds, then sent stop.
- Commands observed on CAN: `0x320#060101` active-report enable, `0x320#020100` pre-stop, `0x320#0301640002000000` target, `0x320#020100` post-stop.
- Validation: M33 heartbeat returned `0x322#A534070000060000` and `0x322#A535070000060000`; motor4 aggregate status `0x331` changed from stale/no-feedback to fresh status during capture; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Tooling pitfall found: running `nanopi_can_master.py ... --wait > 0` over SSH can print enough bus traffic to fill the SSH pipe and leave a remote bash process stuck. Use `--wait 0` plus filtered `candump` for live motion tests.
- Unverified: no M33 serial log because `COM26` remains unavailable; user has not yet confirmed whether 4号 visibly moved.
- Safety: only motor4 was commanded, no ROS bridge was started, and a post-stop was sent after the target window.

### 2026-05-28 - Motor4 fixed-speed debug run

- Reason: user asked to rotate at fixed speed for 5 seconds after the formal-path position attempt had no visible confirmation.
- Completed: used NanoPi direct debug path, not the formal ROS/M33 trajectory path: `private active-report --motor 4`, `private speed --motor 4 --vel 0.20 --kd 1.0`, held 5 seconds, then `private stop --motor 4 --clear-fault`.
- Validation: filtered candump recorded active-report frame `0x1800FD04#0102030405060100`, stop frame `0x0400FD04#0100000000000000`, and continuous motor4 aggregate `0x331` changes from about `B3A70400AA070120` through `B3B00401D9080120`; this shows fresh motor4 telemetry changed during the 5-second speed command.
- Final state: active-report was disabled, `0x331` later returned to stale/no-feedback frames, and `can0` remained `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor4 was commanded, speed was low, command duration was bounded to 5 seconds, and stop was sent immediately after the window.
- Next step: wait for user visual confirmation; if motion is confirmed, record direction/sign and then move back to the formal M33 safety path instead of expanding direct debug control.

### 2026-05-28 - Motor4 faster fixed-speed debug run

- Reason: user asked to speed up and lengthen the fixed-speed observation test.
- Completed: used the same NanoPi direct debug path for motor4: active-report enable, `private speed --motor 4 --vel 0.35 --kd 1.0`, held 8 seconds, then `private stop --motor 4 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 108 frames. Motor4 aggregate `0x331` changed continuously during the 8-second window, e.g. from `B3270401A1090320` through `B37B0401030F0220`, then stop frame `0x0400FD04#0100000000000000` was observed.
- Final state: after stop, `0x331` settled near `...040F...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor4 was commanded, duration was bounded, and stop was sent immediately after the window. This remains a direct debug-path test, not the formal robot control path.

### 2026-05-28 - Motor4 reverse fixed-speed debug run

- Reason: user asked to reverse direction, set speed directly to `1`, and run for 10 seconds.
- Completed: used NanoPi direct debug path for motor4 with negative velocity: active-report enable, `private speed --motor 4 --vel -1.0 --kd 1.0`, held 10 seconds, then `private stop --motor 4 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 127 frames. Motor4 aggregate `0x331` changed continuously in the opposite direction, e.g. from `B38D04016C0BF720` through `B3400401C6EDF920`, then stop frame `0x0400FD04#0100000000000000` appeared at the end of the command window.
- Final state: after stop, `0x331` settled near `...70EE...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor4 was commanded, duration was bounded to 10 seconds, and stop was sent immediately after the window. This remains a direct debug-path test, not the formal robot control path.

### 2026-05-28 - Motor4 reverse fixed-speed 5 second repeat

- Reason: user asked to run the same reverse direction again for 5 seconds.
- Completed: used NanoPi direct debug path for motor4 with `private speed --motor 4 --vel -1.0 --kd 1.0`, held 5 seconds, then `private stop --motor 4 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 79 frames. Motor4 aggregate `0x331` changed continuously from about `B33E04000FF00020` through `B33D040133E0F820`; stop frame `0x0400FD04#0100000000000000` appeared after the command window.
- Final state: after stop, `0x331` settled near `...77E1...` and then returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor4 was commanded, duration was bounded to 5 seconds, and stop was sent immediately after the window.

### 2026-05-28 - Motor4 reverse fixed-speed 20 second run

- Reason: user asked to continue motion for 20 seconds.
- Completed: used NanoPi direct debug path for motor4 with `private speed --motor 4 --vel -1.0 --kd 1.0`, held 20 seconds, then `private stop --motor 4 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 223 frames. Motor4 aggregate `0x331` changed continuously from `B38E04000A180021` near motion start through `B35D0401A9DCF821` near stop; stop frame `0x0400FD04#0100000000000000` appeared at `1779959246.062697`.
- Final state: after stop, `0x331` settled near `...9DDC...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor4 was commanded, duration was bounded to 20 seconds, and stop was sent immediately after the window. This remains direct debug control, not the formal robot path.

### 2026-05-28 - Motor6 fixed-speed 10 second run

- Reason: user asked to rotate motor6 for 10 seconds.
- Completed: used NanoPi direct debug path for motor6 with `private active-report --motor 6`, `private speed --motor 6 --vel 0.5 --kd 1.0`, held 10 seconds, then `private stop --motor 6 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 127 frames. Motor6 aggregate `0x333` changed from stale to fresh after active-report enable and then changed continuously from `B31006005511001E` through `B3040601B32C041E`; stop frame `0x0400FD06#0100000000000000` appeared at `1779959518.334354`.
- Final state: after stop, `0x333` settled near `...BC2C...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor6 was commanded, first motor6 run used a moderate `0.5` velocity instead of the faster motor4 value, duration was bounded to 10 seconds, and stop was sent immediately after the window. This remains direct debug control, not the formal robot path.

### 2026-05-28 - Motor6 swing attempt and direct-speed approximate swing

- Reason: user asked to swing between `-45 deg` and `+45 deg`.
- Formal-path attempt: sent NanoPi -> M33 `0x320` commands for ROS joint3/motor6: active-report enable, stop, `-45 deg`, `+45 deg`, `0 deg`, stop, active-report disable.
- Formal-path result: command frames were present (`0x320#03033EFE05000000`, `0x320#0303C20105000000`, `0x320#0303000005000000`), but `0x333` stayed essentially fixed at `...0085D4...`; this means the formal M33 absolute position path did not actually move motor6 in this test.
- Fallback debug test: used direct speed control to approximate a visible swing: `+0.5` for 3 seconds, `-0.5` for 6 seconds, `+0.5` for 3 seconds, then stop and active-report disable.
- Direct-speed validation: filtered candump recorded 155 frames. `0x333` first increased from around `...85D4...` to `...79D9...`, then reversed down through `...D0.../2F...`, then moved back toward `...D5...`; stop frame `0x0400FD06#0100000000000000` appeared at the end.
- Final state: after stop, `0x333` settled near `...59D5...` and later returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: direct-speed swing was bounded and stopped. Do not treat this as completion of formal `JointTrajectory -> M33 -> motor6 position` control; that path still needs debugging.

### 2026-05-28 - Motor5 fixed-speed 10 second run

- Reason: user asked to move motor5 for 10 seconds at speed `0.5`.
- Completed: used NanoPi direct debug path for motor5 with `private active-report --motor 5`, `private speed --motor 5 --vel 0.5 --kd 1.0`, held 10 seconds, then `private stop --motor 5 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 126 frames. Motor5 aggregate `0x332` changed from stale to fresh after active-report enable and then changed continuously from `B3CF0500DEFF001D` through `B3BE05015D05021D`; stop frame `0x0400FD05#0100000000000000` appeared at `1779959861.034258`.
- Final state: after stop, `0x332` settled near `...6405...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor5 was commanded, duration was bounded to 10 seconds, and stop was sent immediately after the window. This remains direct debug control, not the formal robot path.

### 2026-05-28 - Motor5 reverse fixed-speed 10 second run

- Reason: user asked to run motor5 in the opposite direction.
- Completed: used NanoPi direct debug path for motor5 with `private active-report --motor 5`, `private speed --motor 5 --vel -0.5 --kd 1.0`, held 10 seconds, then `private stop --motor 5 --clear-fault` and active-report disable.
- Validation: filtered candump recorded 127 frames. Motor5 aggregate `0x332` changed from stale to fresh after active-report enable and then changed in the opposite direction from `B3A5050080FF001D` through `B394050144FD001D`; stop frame `0x0400FD05#0100000000000000` appeared at `1779959924.613948`.
- Final state: after stop, `0x332` settled near `...64FD...` and later returned to stale/no-feedback frames after active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: only motor5 was commanded, duration was bounded to 10 seconds, and stop was sent immediately after the window. This remains direct debug control, not the formal robot path.

### 2026-05-28 - Motor5 reverse run with 3A current limit

- Reason: user reported insufficient force and asked to increase current limit.
- Completed: used NanoPi direct debug path for motor5, enabled active-report, wrote RobStride/Lingzu `limit_cur(0x7018)=3.0A`, then repeated `private speed --motor 5 --vel -0.5 --kd 1.0` for 10 seconds, followed by stop and active-report disable.
- Validation: filtered candump recorded current-limit write frame `0x1200FD05#1870000000004040`, 137 total frames, continuous `0x332` motor5 aggregate changes, and stop frame `0x0400FD05#0100000000000000` at `1779960008.422313`.
- Final state: after stop, `0x332` settled near `...E9FD...` and later returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: current limit was increased modestly to `3.0A` rather than jumping to a high value; only motor5 was commanded, duration was bounded to 10 seconds, and stop was sent immediately after the window.

### 2026-05-28 - Motor5 3A current observation repeat

- Reason: user asked to repeat the test to observe actual current.
- Completed: repeated the same motor5 direct debug conditions for comparison: active-report enable, `limit_cur(0x7018)=3.0A`, `private speed --motor 5 --vel -0.5 --kd 1.0` for 10 seconds, then stop and active-report disable.
- Validation: filtered candump recorded current-limit write frame `0x1200FD05#1870000000004040`, 138 total frames, continuous `0x332` motor5 aggregate changes, and stop frame `0x0400FD05#0100000000000000` at `1779960197.182458`.
- Note: current exact value is not yet decoded from the aggregate frame; next software task should add raw Lingzu feedback/current decoding and expose it to ROS/platform instead of relying on visual/manual current observation.
- Final state: after stop, `0x332` settled near `...4DFF...` and later returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: parameters matched the previous 3A test, duration was bounded to 10 seconds, and stop was sent immediately after the window.

### 2026-05-28 - Motor5 3A current observation second repeat

- Reason: user asked to restart the same observation run.
- Completed: repeated motor5 direct debug conditions again: active-report enable, `limit_cur(0x7018)=3.0A`, `private speed --motor 5 --vel -0.5 --kd 1.0` for 10 seconds, then stop and active-report disable.
- Validation: filtered candump recorded current-limit write frame `0x1200FD05#1870000000004040`, 137 total frames, continuous `0x332` motor5 aggregate changes, and stop frame `0x0400FD05#0100000000000000` at `1779960268.227946`.
- Final state: after stop, `0x332` settled near `...52FC...` and later returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: parameters matched the previous 3A tests, duration was bounded to 10 seconds, and stop was sent immediately after the window.

### 2026-05-28 - Motor5 torque/current mode diagnosis

- User observation: motor5 only moved a small angle and then stalled; bench supply at 32V still showed about `0.1A`, so increasing `limit_cur` alone did not make the motor draw current.
- Completed: non-motion reads after stop confirmed `limit_cur(0x7018)=3.0f`; `limit_spd(0x7017)` read back as `33.0f`; run mode readback showed `0x7005` value `0`.
- Completed: sent a small MIT torque-feedforward debug test for motor5 with `limit_cur=3.0A`, enable, repeated `torque=-0.2Nm` MIT control frames for about 2 seconds, then stop and active-report disable.
- Validation: tx log recorded 98 repeated `0x017E2B05#8000800000000000` torque frames, stop frame `0x0400FD05#0100000000000000`, and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Finding: MIT torque-feedforward and `limit_cur` are not enough to prove true current control. Official RobStride/Lingzu parameter flow uses `run_mode` plus `iq_ref(0x7006)` for current mode, while `limit_cur(0x7018)` is a limit for velocity/position modes.
- Next step: do not keep increasing `limit_cur` in speed mode. Add a dedicated, bounded current-mode debug command that writes the correct model-specific `run_mode` and ramps `iq_ref(0x7006)` in small steps, with immediate stop/disable and live current feedback decoding.

### 2026-05-28 - Motor5 official current-mode -0.5A pulse

- Reason: user said `0.2A` would not be enough and wanted torque/current mode instead of speed mode.
- Completed: used NanoPi direct parameter path for motor5: active-report enable, write `run_mode(0x7005)=3`, enable, write `iq_ref(0x7006)=-0.5A`, hold 2 seconds, write `iq_ref=0.0A`, stop, active-report disable.
- Validation: filtered candump recorded `0x1200FD05#0570000003000000` (`run_mode=3`), `0x0300FD05#0000000000000000` enable, `0x1200FD05#06700000000000BF` (`iq_ref=-0.5f`), `0x1200FD05#0670000000000000` (`iq_ref=0.0f`), and stop frame `0x0400FD05#0100000000000000`.
- Feedback: `0x332` changed during the current command window, from about `B30D050014FF001F` through `B394050171FB001F`, then recovered after `iq_ref=0` and stop.
- Final state: after stop and active-report disable, `0x332` returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: current-mode pulse was bounded to 2 seconds, setpoint was explicitly returned to zero before stop, and only motor5 was commanded. User needs to report bench supply current response before increasing current further.

### 2026-05-28 - Motor5 official current-mode -0.7A hold

- Reason: user reported that `0.2A` is not enough and asked to try `0.7A` then hold.
- Completed: used NanoPi direct parameter path for motor5: active-report enable, write `run_mode(0x7005)=3`, enable, write `iq_ref(0x7006)=-0.7A`, hold 5 seconds, write `iq_ref=0.0A`, stop, active-report disable.
- Validation: filtered candump recorded `0x1200FD05#0570000003000000` (`run_mode=3`), `0x0300FD05#0000000000000000` enable, `0x1200FD05#06700000333333BF` (`iq_ref=-0.7f`), `0x1200FD05#0670000000000000` (`iq_ref=0.0f`), and stop frame `0x0400FD05#0100000000000000`.
- Feedback: `0x332` changed during the current command window, from about `B34E05015AFFF41F` through `B343050197F80020`, then recovered after `iq_ref=0` and stop.
- Final state: after stop and active-report disable, `0x332` returned to stale/no-feedback frames; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: current-mode hold was bounded to 5 seconds, setpoint was explicitly returned to zero before stop, and only motor5 was commanded. Do not use indefinite current hold over remote SSH.

### 2026-05-28 - Motor5 MIT velocity plus torque feedforward hold

- Reason: user asked whether velocity and torque can be mixed because pure speed/current mode was not ideal.
- Clarification: official `run_mode` speed/current modes are mutually exclusive, but MIT control frames can combine velocity target and torque feedforward in one refreshed command stream.
- Completed: used NanoPi direct MIT debug path for motor5: active-report enable, enable motor, refreshed `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-0.2Nm` for 5 seconds, then stop and active-report disable.
- Validation: tx log recorded 244 repeated MIT frames `0x017E2B05#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the hold, around `...71FF...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: mixed MIT hold was bounded to 5 seconds and explicitly stopped. This can be used as a bench debug strategy, but formal robot control should implement the same idea inside M33 with timeout, current/torque limits, and emergency-stop gates.

### 2026-05-28 - Motor5 stronger MIT velocity plus torque feedforward hold

- Reason: user reported that the previous mixed MIT torque feedforward was still insufficient.
- Completed: used NanoPi direct MIT debug path for motor5 with the same velocity target but stronger feedforward: active-report enable, enable motor, refreshed `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-0.4Nm` for 5 seconds, then stop and active-report disable.
- Validation: tx log recorded 244 repeated MIT frames `0x017C5705#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the hold, around `...F2FE...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: mixed MIT hold was bounded to 5 seconds and explicitly stopped. Further increases should be paired with mechanical inspection or M33-side bounded assist logic rather than open-ended NanoPi MIT frames.

### 2026-05-28 - Motor5 1Nm MIT velocity plus torque feedforward pulse

- Reason: user clarified that `-0.4Nm` was insufficient and at least `1Nm` is needed.
- Completed: used NanoPi direct MIT debug path for motor5 with `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-1.0Nm`, held 3 seconds, then stop and active-report disable.
- Validation: tx log recorded 147 repeated MIT frames `0x0176DB05#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the pulse, around `...F2FE...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: because this jumped from `-0.4Nm` to `-1.0Nm`, duration was bounded to 3 seconds. Wait for user confirmation before extending hold time or increasing torque further.

### 2026-05-28 - Motor5 2Nm MIT velocity plus torque feedforward pulse

- Reason: user reported that `-1.0Nm` was still insufficient and asked for `2Nm`.
- Completed: used NanoPi direct MIT debug path for motor5 with `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-2.0Nm`, held 2 seconds, then stop and active-report disable.
- Validation: tx log recorded 98 repeated MIT frames `0x016DB605#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the pulse, around `...26FF...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: because this is already double the previous `-1.0Nm` test, duration was bounded to 2 seconds. If this is still insufficient, next action should be mechanical/load-path inspection and M33-side bounded assist design, not unbounded remote torque escalation.

### 2026-05-28 - Motor5 5Nm MIT velocity plus torque feedforward pulse

- Reason: user reported that `-2.0Nm` was still insufficient and requested `5Nm`; user also noted official `0.5A` current mode was effective, suggesting MIT torque scale may not map directly to expected output-axis torque.
- Completed: used NanoPi direct MIT debug path for motor5 with `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-5.0Nm`, held 1 second, then stop and active-report disable.
- Validation: tx log recorded 49 repeated MIT frames `0x01524905#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the pulse, around `...D9FF...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: duration was bounded to 1 second because this is a large remote MIT torque-feedforward pulse. Wait for user confirmation before any longer hold; prefer official current mode or M33-side bounded assist for further force testing.

### 2026-05-28 - Motor5 5Nm MIT velocity plus torque feedforward 5 second hold

- Reason: user asked to keep the same `-5.0Nm` MIT feedforward for 5 seconds.
- Completed: used NanoPi direct MIT debug path for motor5 with `vel=-0.3 rad/s`, `kp=0`, `kd=1.0`, `torque_ff=-5.0Nm`, held 5 seconds, then stop and active-report disable.
- Validation: tx log recorded 244 repeated MIT frames `0x01524905#80007ED600003333`; filtered candump recorded stop frame `0x0400FD05#0100000000000000` and active-report disable.
- Feedback: `0x332` stayed fresh during the hold, around `...CEFE...`, then returned to stale/no-feedback frames after stop and active-report disable; `can0` stayed `ERROR-ACTIVE` with tx/rx error counters `0/0`.
- Safety: this was a high MIT torque-feedforward hold, bounded to 5 seconds and explicitly stopped. Do not make this an unbounded NanoPi-side behavior; formal assist must move into M33 with safety limits.

### 2026-05-28 - NanoPi private CSP position command wrapper

- Reason: user observed pure current mode can move motor5 but feels wrong for robot motion: no target position, speed can feel fast, and light resistance can stall if the current setpoint is too low.
- Completed: added `nanopi_can_master.py private csp` as a direct debug wrapper for RobStride/Lingzu official CSP flow: active-report on, `run_mode=5`, enable, `limit_cur(0x7018)`, `limit_spd(0x7017)`, `loc_ref(0x7016)`, bounded observe window, then default stop and active-report off.
- Validation: local Python syntax check passed with `python -m py_compile scripts/nanopi_can_master.py`; CLI help shows `private csp` and the new `--target-rad/--target-deg/--limit-spd/--limit-cur/--hold/--leave-enabled` parameters.
- Deployment: uploaded the updated script to NanoPi `/home/pi/nanopi_can_master.py` and confirmed remote `private --help` shows `csp`.
- Safety: default behavior stops after `--hold`; `--leave-enabled` is explicit bench-only behavior. Formal robot motion still belongs in M33 with joint limits, speed/current limits, timeout, and emergency-stop gates.
- Next step: run a small CSP motor5 trial, for example `--target-deg 10 --limit-spd 0.15 --limit-cur 1.0 --hold 6`.

### 2026-05-28 - NanoPi private CSP slow retract before stop

- Reason: user requested that the CSP debug command should not immediately power off/stop at the end of motion; it should slowly retract first, then stop.
- Completed: extended `nanopi_can_master.py private csp` with optional `--return-rad/--return-deg`, `--return-spd`, and `--return-hold`.
- Behavior: if a return target is provided, the script writes a slower `limit_spd(0x7017)`, writes the return `loc_ref(0x7016)`, waits for `--return-hold`, then sends stop and disables active-report unless `--leave-enabled` is set.
- Validation: local Python syntax check passed and CLI help shows the new return parameters.
- Safety: return motion is explicit; the script will not assume `0°` unless the operator asks for `--return-deg 0`. This avoids unexpected motion toward an unconfirmed zero on a real wearable mechanism.
