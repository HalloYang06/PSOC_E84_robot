# 康复外骨骼机械臂对接文档

本文档给后续仿真主机、NanoPi、英飞凌 M33/M55、App、数据标注工具和预留总控台开发者使用。它只定义当前已确认的数据接口和安全边界，不要求现在接入服务器实现。

## 1. 总原则

- 这是穿戴在人身上的康复外骨骼，安全优先级高于演示效果、AI 能力和开发速度。
- 正式运动链路只能是：`JointTrajectory -> NanoPi -> M33 -> 电机`。
- M33 是最终安全裁决方，负责限位、限速、急停、掉线保护和电机输出许可。
- NanoPi 直发电机 CAN 只允许作为调试工具，不进入正式 bringup。
- App 近端实时链路走 BLE 到英飞凌；HTTP/OpenClaw 只做高层服务，不做底层电机闭环。
- 服务器/VLA 后续只接任务、状态和数据资产，不直接发 CAN，不直接发电机力矩、电流、速度或裸位置命令。

## 2. ROS2 对接接口

| Topic | Type | 发布方 | 订阅方 | 说明 |
|---|---|---|---|---|
| `/arm_controller/joint_trajectory` | `trajectory_msgs/msg/JointTrajectory` | 仿真主机/规划器/VLA 任务规划后端 | 仿真节点、NanoPi PSoC bridge | 标准关节轨迹入口。真机路径必须再经过 M33 安全裁决。 |
| `/joint_states` | `sensor_msgs/msg/JointState` | 仿真节点或真机状态桥 | RViz、recorder、motor_state bridge、算法 | 标准关节状态。 |
| `/rehab_arm/safety_state` | `std_msgs/msg/String` JSON | M33 bridge 或仿真节点 | App、recorder、总控台、算法 | 安全状态。上层优先看 `motion_allowed`。 |
| `/rehab_arm/sensor_state` | `std_msgs/msg/String` JSON | 仿真节点、M33/M55 汇总桥 | recorder、算法、总控台 | EMG、IMU、心率、疲劳、模型摘要等。 |
| `/rehab_arm/motor_state` | `std_msgs/msg/String` JSON | 仿真遥测桥或后续 M33 状态桥 | recorder、总控台、标注工具 | 电机/关节遥测，只是数据，不是命令。 |
| `/rehab_arm/camera_keyframe` | `std_msgs/msg/String` JSON | NanoPi camera keyframe 节点 | recorder、总控台、VLA 数据链路 | 摄像头关键帧元数据，不是控制命令。 |
| `/vla/task_goal` | `std_msgs/msg/String` JSON | App/服务器/VLA | 任务规划器 | 高层任务目标，不直接控制电机。 |

## 2.1 URDF 与平台模型预览

当前模型文件：

```text
rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf
```

该文件当前只使用 URDF 内置几何体 `box/cylinder`，没有依赖外部 mesh，因此可以先直接导入 AI 合作平台的设备数据工作台 `模型预览` tab 做浏览器只读预览。

平台侧第一版用途：

- 解析 link、joint、parent/child 和 joint limit。
- 用 three.js + urdf-loader 尝试直接渲染 URDF。
- 后续把采集片段中的 `/joint_states` 按同名 joint 做回放。
- 只作为模型检查、数据标注和证据查看入口，不作为仿真控制器。

导入规则：

- 推荐先导入展开后的 `.urdf`，不要直接导入 `.xacro`。
- 如果后续 URDF 引用 `package://.../meshes/...`，需要把 mesh 资产打包并提供路径映射。
- joint 名称必须和 `/joint_states.name` 一致，否则平台只能显示结构，不能自动回放采集数据。
- 平台显示模型不代表允许真机运动，真实运动仍走 `JointTrajectory -> NanoPi -> M33 -> 电机` 和 M33 安全裁决。

## 3. CAN 对接接口

| CAN ID | 方向 | 当前用途 |
|---|---|---|
| `0x320` | NanoPi -> M33 | 关节目标/轨迹片段命令。当前仍按 M33 logging-only 安全审核推进。 |
| `0x321` | NanoPi -> M33 | NanoPi heartbeat。 |
| `0x322` | M33 -> NanoPi | M33 安全状态、模式、最近一次安全评估详情。 |
| `0x7C2` | C8T6 -> M33 | 传感数据。 |
| `0x7C3` | C8T6 -> M33 | 传感节点健康状态。 |

当前已知电机调试 ID：

| ID | 协议 | 边界 |
|---|---|---|
| `node_id=3` | CANSimple/ODrive 类标准帧协议 | 调试工具可观察/诊断，正式链路不直控。 |
| `motor_id=4/5/6/7` | 私有扩展帧 MIT 电机协议 | 机械关节绑定待确认，正式链路不由 NanoPi 直控。 |

## 4. 记录文件对接

### JSONL Session

默认记录文件：

```text
<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl
```

每行是一个 JSON object：

- 第一行通常是 `record_type=session_metadata`。
- 后续为 `record_type=topic_message`。
- 必需 topic：`/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
- 可选 topic：`/rehab_arm/motor_state`、`/rehab_arm/camera_keyframe`。

检查完整性：

```bash
ros2 run rehab_arm_psoc_bridge check_recording.py /path/to/session.jsonl
```

生成摘要：

```bash
ros2 run rehab_arm_psoc_bridge summarize_recording.py /path/to/session.jsonl --pretty
```

摘要核心字段：

| 字段 | 说明 |
|---|---|
| `topic_counts` | 每个 topic 的消息数。 |
| `topic_rates_hz` | 根据 `ts_unix` 估算的 topic 频率。 |
| `joint_position_ranges` | 每个关节 position 的 `min/max/span`。 |
| `moving_joint_count` | span 大于 `0.01 rad` 的关节数量。 |
| `motor_entry_count_min/max` | 每帧 motor_state 里电机条目数量范围。 |
| `safety_states` | 安全状态分布。 |
| `motion_allowed_counts` | `motion_allowed` 统计。 |

质量门检查：

```bash
ros2 run rehab_arm_psoc_bridge validate_recording_quality.py /path/to/session.jsonl \
  --min-joint-messages 100 \
  --min-moving-joints 5 \
  --require-motor-state \
  --min-motor-entry-count 5
```

输出 `rehab_arm_recording_quality_v1`，包含 `ok/errors/warnings/criteria/schema_check/summary`。总控台、标注工具或 CI 可以先看 `ok`，再读取 `errors` 给操作者。当前 logging-only/离线采集阶段默认不允许 `motion_allowed=true`。

### Manifest

普通 manifest：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --output /home/pi/rehab_arm_logs/manifest.json
```

带 summary 的 manifest：

```bash
ros2 run rehab_arm_psoc_bridge build_manifest.py /home/pi/rehab_arm_logs \
  --include-summary \
  --output /home/pi/rehab_arm_logs/manifest_with_summary.json
```

对接建议：

- 标注工具、总控台、数据浏览页面优先读取 `manifest_with_summary.json`。
- 旧同步流程或只需要上传文件索引时，可以继续读取普通 `manifest.json`。
- `summary` 字段是数据质量索引，不是控制指令。
- 上传到 AI 合作平台后，平台侧会把该 summary 转成通用 `device_recording_quality_index_v1`。
- 平台质量索引只判断数据是否适合标注、导出和图表分析，不代表允许真机运动。
- 康复机械臂只是平台设备数据工作台的第一个适配来源；平台 UI 不应写死为医疗或机械臂专用。

### CSV 导出

导出 JSONL 为 CSV：

```bash
ros2 run rehab_arm_psoc_bridge export_recording_csv.py /path/to/session.jsonl \
  --output-dir /path/to/session_csv
```

输出文件：

| 文件 | 说明 |
|---|---|
| `joint_states.csv` | 长表格式，每行一个关节样本。 |
| `motor_states.csv` | 长表格式，每行一个电机/关节遥测样本。 |

`joint_states.csv` 字段：

```text
ts_unix,stamp_sec,stamp_nanosec,joint_name,position,velocity,effort
```

`motor_states.csv` 字段：

```text
ts_unix,robot_id,device_id,source,joint_name,motor_id,protocol,position,velocity,effort,current,torque,temperature,voltage,enabled,fault,error_code,raw_can_id
```

CSV 用途：

- 本地画曲线。
- 康复动作标注。
- 小模型训练前的数据检查。
- 和 Excel、pandas、MATLAB 等工具对接。

## 5. 仿真采集对接流程

静态采集：

```bash
ros2 launch rehab_arm_bringup sim_data_collection.launch.py \
  output_dir:=/home/pi/rehab_arm_logs \
  session_id:=sim_static \
  flush_every:=1
```

动态 demo 轨迹采集：

```bash
timeout -s INT 12s ros2 launch rehab_arm_bringup sim_data_collection.launch.py \
  output_dir:=/home/pi/rehab_arm_logs \
  session_id:=sim_demo_motion \
  flush_every:=1 \
  enable_demo_trajectory:=true
```

验收顺序：

1. `check_recording.py` 返回 `ok=true`。
2. `validate_recording_quality.py --min-moving-joints 5 --require-motor-state --min-motor-entry-count 5` 返回 `ok=true`。
3. `summarize_recording.py` 中 `moving_joint_count=5`。
4. `motor_entry_count_min=5` 且 `motor_entry_count_max=5`。
5. 导出 CSV 后，`joint_states.csv` 和 `motor_states.csv` 均有数据行。

## 6. 真机对接边界

真机正式运动前必须满足：

- M33 已解除 logging-only，并完成安全状态机验证。
- `/rehab_arm/safety_state.motion_allowed=true` 的语义已由 M33 明确上报。
- 急停、限位、限速、掉线保护、电池/供电异常处理都已验证。
- 关节名和真实电机 ID 映射已经确认。
- 现场有人能断电或按急停。

禁止：

- 服务器直接发 CAN。
- App HTTP 直接下发电机底层控制量。
- VLA 直接输出电流、力矩、速度或裸电机位置。
- 人穿戴设备时使用 NanoPi 调试工具直控电机。

## 7. 当前已验证能力

- 仿真节点发布 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
- `/joint_states` 可转换成 `/rehab_arm/motor_state`。
- recorder 可写出 JSONL。
- `check_recording.py` 可检查基础 topic。
- `summarize_recording.py` 可总结数据质量。
- `validate_recording_quality.py` 可做离线 PASS/FAIL 质量门。
- `build_manifest.py --include-summary` 可生成带 summary 的 manifest。
- `sync_dry_run.py` 和本地 `sync_test_server.py` 已验证能保留 summary 字段。
- `export_recording_csv.py` 可导出 `joint_states.csv` 和 `motor_states.csv`。

所有上述能力均不要求电机上电，不发送 `0x320`，不做真实电机运动。
