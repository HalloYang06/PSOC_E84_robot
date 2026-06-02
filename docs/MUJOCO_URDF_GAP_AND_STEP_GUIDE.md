# MuJoCo 仿真 URDF 差距清单与分阶段补齐教程

本文档回答两个问题：

1. 当前 `medical_arm.zip` 里的 URDF 距离可用 MuJoCo 仿真还差什么。
2. 如何按小步慢慢补齐，不一次性把 ROS2、MuJoCo、VLA、NanoPi、M33 全混在一起。

本项目是医疗康复外骨骼机械臂，默认安全态是不动。仿真、VLA、服务器、NanoPi、App 都不能绕过 M33。正式运动链路保持：

```text
VLA/服务器 -> NanoPi ROS2 -> JointTrajectory/0x320 -> M33 安全裁决 -> 电机
```

仿真主机通过无线 ROS2 接入 NanoPi：

```text
Linux 仿真主机 <-> Wi-Fi/LAN ROS2 DDS <-> NanoPi <-> CAN <-> M33
```

MuJoCo 的职责是仿真、轨迹验证、数据生产、回放和算法训练，不是真机安全权威。无线 ROS2 适合状态同步、可视化、dry-run、规划和数据采集；不适合急停、力矩/电流内环或高频助力闭环，这些必须留在 M33 和本地 CAN/电气安全路径。

## 1. 当前 URDF 已经有什么

当前 zip 解压后是一个 ROS 包结构：

```text
medical_arm/
  config/
  launch/
  meshes/
  textures/
  urdf/
```

主模型：`urdf/medical_arm.urdf`

已有内容：

- 7 个 link。
- 6 个旋转关节；`medical_arm_viewer.urdf` 和 `urdf/medical_arm.urdf` 已先从 `continuous` 改成带保守 ROM 的 `revolute`。
- 每个 link 有质量和惯量。
- 每个 link 有 STL visual/collision mesh。
- STL 尺寸看起来是米制，不像毫米误导出。

当前 6 个关节：

| URDF 关节名 | 当前类型 | 保守初始 ROM | 当前电机关系 | 主要问题 |
|---|---|---|---|---|
| `jian_hengxiang_joint` | `revolute` | `-45° .. +90°` | `node_id=3`，电机轮:输出轴轮 `1:2` | 方向、零点、硬限位待实测 |
| `jian_zongxiang_joint` | `revolute` | `-30° .. +100°` | `motor_id=4`，多级齿轮 | 齿轮比、方向、零点待实测 |
| `jian_xuanzhuan_joint` | `revolute` | `-60° .. +60°` | `motor_id=6` | 输出比例、方向、零点待实测 |
| `zhou_zongxiang_joint` | `revolute` | `0° .. +135°` | `motor_id=5` | 输出比例、方向、零点待实测 |
| `wanbu_zongxiang_joint` | `revolute` | `-45° .. +45°` | 4015 小电机 `motor_id=1/2` 之一 | 具体电机、协议、方向、零点待确认 |
| `wanbu_hengxiang_joint` | `revolute` | `-20° .. +30°` | 4015 小电机 `motor_id=1/2` 之一 | 具体电机、协议、方向、零点待确认 |

`motor_id=7` 当前没有装在机械臂上，只能作为外部调试电机记录，不进入 MuJoCo/VLA/正式机械臂映射。当前映射草案见 [JOINT_MOTOR_MAPPING_DRAFT.md](JOINT_MOTOR_MAPPING_DRAFT.md)。

当前 `config/joint_names_robotic_arm.SLDASM.yaml` 只列出：

```text
jian_xuanzhuan_joint
zhou_zongxiang_joint
```

这说明 CAD 导出的 URDF 和 ROS 控制关节配置还没有收敛。不能直接把这个 URDF 当成正式控制模型。

## 2. 距离 MuJoCo 可用模型还差什么

### 2.0 当前远程 MuJoCo 主机状态

2026-06-02 已在远程仿真主机 `cal@192.168.2.46` 上建立当前可视化目录：

```text
/home/cal/medical_arm_mujoco/
  medical_arm_mujoco.xml
  medical_arm_viewer.urdf
  urdf/medical_arm.urdf
  meshes/*.STL
  README_MUJOCO.md
  joint_motor_mapping.yaml
  validate_mujoco.py
  open_mujoco.sh
  medical_arm_mujoco_preview.png
  medical_arm_mujoco_preview_close.png
```

打开方式：

```bash
cd /home/cal/medical_arm_mujoco
./open_mujoco.sh
```

验证方式：

```bash
cd /home/cal/medical_arm_mujoco
MUJOCO_GL=egl python3 validate_mujoco.py
```

已验证：

- Python `mujoco 3.9.0` 能加载 `medical_arm_mujoco.xml`。
- MuJoCo viewer 3.10 可用路径是 `/home/cal/mujoco/build/bin/simulate`。
- 当前模型有 `nq=6`、`nv=6`、`nu=6`、`ngeom=15`、`ncam=2`。
- 6 个关节和 6 个 position actuator 已按 `medical_arm.urdf` 限位生成。
- 已加入材质、地面、灯光、两个相机、末端 site、关节轴 marker 和简化 collision proxy。

仍需补：

- 真实机械硬限位、患者 profile 和 M33 最终安全限位。
- `motor_id=1/2` 到腕部两轴的具体对应关系。
- `motor_id=4` 到 `jian_zongxiang_joint` 的最终齿轮比。
- 每个电机到输出 joint 的方向、零点、回差和标定版本。
- collision proxy 需要按真实外形进一步调，不应直接把 STL mesh 当动态碰撞体。

### 2.1 关节语义

当前缺少：

- 最终 ROS joint 名。
- 每个 URDF 关节对应人体哪个自由度。
- 每个关节对应哪个电机 ID。
- 关节正方向定义。
- 零位姿定义。
- 角度单位和符号约定。
- `motor_id=1/2` 分别对应腕部哪个轴。
- `motor_id=4` 到 `jian_zongxiang_joint` 的最终齿轮比。
- `node_id=3` 到 `jian_hengxiang_joint` 的方向、零点和 `1:2` 输出侧换算细节。

仓库现有 ROS2 最小仿真仍是早期 5 关节基线，后续需要迁移或兼容到 `medical_arm.zip` 的 6 关节真实 CAD 模型：

| 标准 ROS joint | 含义 | 当前状态 |
|---|---|---|
| `shoulder_lift_joint` | 肩部屈伸/抬举 | 待从 URDF 6 关节中映射 |
| `elbow_lift_joint` | 肘部屈伸 | 待映射 |
| `shoulder_abduction_joint` | 肩部外展/内收 | 待映射 |
| `upper_arm_rotation_joint` | 上臂旋转 | 待映射 |
| `forearm_rotation_joint` | 前臂旋转 | 待映射 |

如果第 6 个自由度要保留，先命名为 `wrist_assist_joint` 或 `wrist_rotation_joint`，但不要急着进正式穿戴控制。

### 2.2 关节限制

当前解压后的 `medical_arm_viewer.urdf` 和 `urdf/medical_arm.urdf` 已加入第一版保守 `revolute` 限位，但这些仍只是工程起步值，对外骨骼正式穿戴还不合格。

必须补：

- 机械硬限位。
- 人体安全 ROM。
- 患者 profile 限位。
- 速度限制。
- 加速度限制。
- 力矩/电流限制。

第一版不要追求极限 ROM。当前先写入 URDF 的保守 smoke-test 范围是：

```text
jian_hengxiang_joint:       -45deg .. +90deg
jian_zongxiang_joint:       -30deg .. +100deg
jian_xuanzhuan_joint:       -60deg .. +60deg
zhou_zongxiang_joint:         0deg .. +135deg
wanbu_zongxiang_joint:      -45deg .. +45deg
wanbu_hengxiang_joint:      -20deg .. +30deg
```

这些只是仿真起步值，不能直接作为临床穿戴限位。正式值要来自机械结构、治疗师协议和患者 profile。

### 2.3 执行器模型

MuJoCo 需要 actuator。当前 URDF 没有：

- motor/actuator。
- control range。
- force range。
- servo kp/kd。
- damping/armature/friction。

第一版 MuJoCo 建议用 position servo，不要一上来做真实电流/力矩：

```xml
<actuator>
  <position joint="shoulder_lift_joint" kp="20" ctrlrange="-0.52 1.05" forcerange="-5 5"/>
  <position joint="elbow_lift_joint" kp="20" ctrlrange="0 1.57" forcerange="-5 5"/>
</actuator>
```

后续再从 position servo 过渡到 torque/impedance/assist-as-needed。

### 2.4 碰撞体

当前 STL mesh 三角面较多，适合视觉，不适合直接作为 MuJoCo collision。

必须补：

- 简化 collision geom。
- 自碰撞排除规则。
- 与人体接触/绑带/支撑点的近似几何。

第一版碰撞建议：

- 大臂、小臂用 capsule 或 box。
- 电机壳用 cylinder。
- 绑带/手撑用 box。
- STL 只做 visual mesh。

### 2.5 惯量和坐标系验证

SolidWorks 导出的质量/惯量可以作为初值，但要验证：

- link 原点是否合理。
- 惯量是否正定。
- 质心是否在 link 附近。
- joint axis 是否和机械实物一致。
- rpy 是否导致模型姿态翻转。

验证方法：

1. MuJoCo 静态加载不爆炸。
2. 每次只动一个关节。
3. 和 CAD/实物拍照对比方向。
4. 和 NanoPi `/joint_states` 回放对比姿态。

### 2.6 ROS2 控制接口

MuJoCo 模型要和真机共用接口：

```text
输入: /arm_controller/joint_trajectory
输出: /joint_states
输出: /rehab_arm/safety_state
输出: /rehab_arm/sensor_state
```

不要让 MuJoCo 仿真专门发另一套私有 topic。后续 VLA、规划器、NanoPi bridge 都围绕这套接口。

## 3. 推荐目录结构

在 ROS2 工作区里逐步补：

```text
rehab_arm_ros2_ws/src/
  rehab_arm_description/
    urdf/
      medical_arm_raw.urdf
      rehab_arm.urdf.xacro
    mujoco/
      rehab_arm_scene.xml
      assets/
    meshes/
      visual/
      collision/
    config/
      joint_limits.yaml
      joint_mapping.yaml
  rehab_arm_sim_mujoco/
    rehab_arm_sim_mujoco/
      mujoco_node.py
      check_sim_env.py
    launch/
      sim.launch.py
```

原则：

- `medical_arm_raw.urdf` 保留原始导出证据。
- `rehab_arm.urdf.xacro` 是清洗后的 ROS2 标准模型。
- `rehab_arm_scene.xml` 是 MuJoCo 运行模型。
- `joint_mapping.yaml` 记录 URDF 关节、ROS joint、电机 ID、人体自由度之间的关系。
- `joint_limits.yaml` 记录机械限位、仿真限位、患者 ROM 默认值。

## 4. 分阶段补齐教程

### 阶段 0：只读归档，不改模型

目标：把原始 zip 和解析结果留档。

要做：

1. 把 `medical_arm.zip` 放到不可变资料目录或记录来源路径。
2. 解压到临时目录。
3. 记录 link/joint 表。
4. 记录 STL 尺寸和质量。
5. 不发布轨迹，不接真机。

验收：

- 能说清楚当前有几个 link、几个 joint。
- 能说清楚哪些 joint 是真实可控、哪些还不确定。

### 阶段 1：建立 cleaned URDF/Xacro

目标：把模型变成 ROS2 能稳定加载的标准描述。

要做：

1. 新建 `rehab_arm_description`。
2. 复制原始 URDF 为 `medical_arm_raw.urdf`。
3. 新建 `rehab_arm.urdf.xacro`。
4. 把关节重命名为标准 ROS joint。
5. 删除或隔离不进入第一版控制的 joint。
6. 添加 conservative joint limits。
7. 添加 `robot_state_publisher` launch。

验收：

```bash
ros2 launch rehab_arm_description display.launch.py
ros2 topic echo /robot_description --once
```

RViz 里能看到模型，手动改 joint angle 时方向符合预期。

### 阶段 2：补关节映射表

目标：让所有人都知道“哪个名字对应哪个东西”。

建议文件：`config/joint_mapping.yaml`

示例：

```yaml
joints:
  - ros_joint: shoulder_lift_joint
    source_urdf_joint: jian_xuanzhuan_joint
    motor_id: 3
    transmission:
      type: pulley
      motor_to_joint_ratio: 0.5
      direction: null
      zero_offset_rad: null
    human_dof: shoulder_flexion_extension
    sign: 1
    calibrated: false
    notes: "待现场确认"
```

验收：

- 每个 ROS joint 都有来源 URDF joint。
- 每个 ROS joint 都明确 motor_id 是否已确认。
- 未确认项写 `null`，不要猜成事实。

### 阶段 3：建立 MuJoCo 最小场景

目标：MuJoCo 能加载模型，不追求真实动力学。

要做：

1. 用 cleaned URDF 转 MJCF，或手写第一版 MJCF。
2. 添加地面、灯光、相机。
3. 使用 visual STL。
4. 碰撞先用简单 capsule/box/cylinder。
5. 添加 position actuator。
6. 添加 joint damping。

验收：

```bash
python3 -m mujoco.viewer --mjcf rehab_arm_scene.xml
```

或者用项目自检：

```bash
ros2 run rehab_arm_sim_mujoco check_sim_env.py --strict-mujoco --pretty
```

通过标准：

- 模型能加载。
- 初始姿态不爆炸、不飞走。
- 单关节控制能缓慢运动。
- 关节不会穿过明显机械限制。

### 阶段 4：ROS2 MuJoCo 节点

目标：MuJoCo 作为 ROS2 节点工作。

输入：

```text
/arm_controller/joint_trajectory
```

输出：

```text
/joint_states
/rehab_arm/safety_state
```

第一版 safety_state 可以是仿真状态：

```json
{
  "source": "mujoco_sim",
  "state": "ok",
  "motion_allowed": false,
  "detail": "simulation_only"
}
```

注意：仿真 `motion_allowed=true` 也不等于真机可动。真机只认 M33。

验收：

```bash
ros2 launch rehab_arm_sim_mujoco sim.launch.py
ros2 topic echo /joint_states --once
ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory ...
```

MuJoCo 收到轨迹并更新 `/joint_states`。

### 阶段 5：无线 ROS2 接 NanoPi，只读

目标：仿真主机通过 Wi-Fi/LAN 看到 NanoPi 状态。

两边统一：

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

仿真主机看 NanoPi：

```bash
ros2 topic list
ros2 topic echo --once /rehab_arm/safety_state
ros2 topic echo --once /rehab_arm/motor_state
```

NanoPi bridge 第一轮必须 target disabled：

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

验收：

- 仿真主机能看到 NanoPi 的 safety/motor/sensor topic。
- NanoPi 不发送 `0x320`。
- CAN 抓包没有轨迹目标。

### 阶段 6：仿真主机发布 dry-run 轨迹到 NanoPi

目标：验证无线 ROS2 轨迹链路，但不动真机。

NanoPi 仍保持：

```text
enable_target_tx=false
```

仿真主机发布：

```bash
ros2 topic pub --once /arm_controller/joint_trajectory trajectory_msgs/msg/JointTrajectory ...
```

验收：

- NanoPi bridge 日志能看到收到轨迹。
- bridge 打印 dry-run 或拒绝原因。
- CAN 上没有 `0x320`。

### 阶段 7：服务器/VLA 接入，但只输出任务目标

你的链路固定为：

```text
VLA -> 服务器 -> NanoPi -> M33
```

VLA 不直接连 M33，不直接连 CAN。

建议 VLA 输出格式：

```json
{
  "schema": "rehab_vla_task_goal_v1",
  "task_id": "session-001-step-003",
  "intent": "assist_elbow_flexion",
  "target_joint": "elbow_lift_joint",
  "target_range_deg": [10, 45],
  "speed_level": "slow",
  "assist_level": "low",
  "requires_human_confirm": true,
  "forbidden_direct_control": true
}
```

服务器/NanoPi 再把它转换成：

```text
任务目标 -> 规划器 -> JointTrajectory 候选 -> NanoPi bridge -> M33 审核
```

验收：

- VLA 只产生 JSON 任务目标。
- 规划器可以在 MuJoCo 中模拟。
- 没有人工确认和 M33 motion_allowed 时，不能发真机目标。

### 阶段 7.1：4 路肌电如何参与 VLA 和仿真

建议采用这个边界：

```text
4 路 EMG 传感器
  -> C8T6/F103 采样和基础滤波
  -> CAN 0x7C2/0x7C3
  -> M33 汇总、时间戳、安全状态绑定
  -> M55 小模型推理
  -> M33/NanoPi 发布模型摘要
  -> 服务器/VLA 作为低频决策上下文
  -> 仿真主机用于回放、标注和策略评估
```

不要让 VLA 直接吃高频原始肌电，也不要让肌电模型直接控制电机。原因有三个：

- 原始 EMG 高频、噪声大、个体差异强，适合 M55 做近端轻量模型，不适合直接塞给大 VLA 做实时闭环。
- VLA 推理延迟和网络链路不可控，不适合作为助力闭环控制器。
- 医疗外骨骼必须让 M33 保持最终安全裁决；M55/VLA 的输出都是建议或上下文。

#### 4 路 EMG 在 M55 上做什么

4 路肌电可以先按肌群放置，例如：

| 通道 | 可能位置 | 主要用途 |
|---|---|---|
| `emg_ch0` | 肱二头肌或目标屈肌 | 肘屈曲意图 |
| `emg_ch1` | 肱三头肌或目标伸肌 | 肘伸展意图 |
| `emg_ch2` | 三角肌前束/中束 | 肩抬举或外展意图 |
| `emg_ch3` | 前臂旋前/旋后相关肌群 | 前臂旋转或代偿检测 |

实际贴片位置必须按康复动作和治疗师建议确认；文档里的位置只是工程起步假设。

M55 不需要输出原始波形给 VLA，第一版输出这些摘要更合适：

```json
{
  "schema": "m55_emg_intent_v1",
  "timestamp_ms": 12345678,
  "window_ms": 200,
  "channels": 4,
  "quality": {
    "ch0_ok": true,
    "ch1_ok": true,
    "ch2_ok": true,
    "ch3_ok": true,
    "electrode_contact_ok": true,
    "noise_level": "low"
  },
  "features": {
    "ch0_rms": 0.31,
    "ch1_rms": 0.08,
    "ch2_rms": 0.12,
    "ch3_rms": 0.05,
    "co_contraction_elbow": 0.18,
    "fatigue_index": 0.22
  },
  "intent": {
    "class": "elbow_flexion",
    "confidence": 0.86,
    "assist_level_suggestion": "low",
    "stop_or_pain_suspected": false
  },
  "control_boundary": "suggestion_only_not_motion_permission"
}
```

第一版模型任务可以很朴素：

- 动作意图分类：肘屈曲、肘伸展、肩抬举、肩外展、前臂旋转、放松、异常。
- 强度估计：低/中/高。
- 共收缩检测：屈肌和伸肌同时紧张时降低助力或暂停。
- 疲劳趋势：同样动作下 RMS/频域特征变化，给出疲劳等级。
- 质量检测：电极脱落、饱和、噪声过高。

M33 可以使用这些结果做保守降级，例如疲劳高就降低速度、共收缩高就暂停，但不能因为 M55 说“想动”就放宽限位或跳过 M33 安全门。

#### VLA 怎么使用 M55 结果

VLA 看到的应该是低频语义摘要，不是 1 kHz 原始 EMG。

推荐服务器给 VLA 的上下文：

```json
{
  "robot_state": {
    "joint_state_fresh": true,
    "safety_state": "ok",
    "motion_allowed": false,
    "active_profile_id": "patient-demo-001"
  },
  "human_intent": {
    "source": "m55_emg_intent_v1",
    "intent_class": "elbow_flexion",
    "confidence": 0.86,
    "assist_level_suggestion": "low",
    "fatigue_index": 0.22,
    "co_contraction_elbow": 0.18,
    "stop_or_pain_suspected": false
  },
  "task_context": {
    "therapy_mode": "active_assist",
    "target": "guided_elbow_flexion",
    "allowed_joint": "elbow_lift_joint"
  }
}
```

VLA 输出仍然只能是高层任务或约束：

```json
{
  "schema": "rehab_vla_task_goal_v1",
  "intent": "assist_elbow_flexion",
  "target_joint": "elbow_lift_joint",
  "target_range_deg": [10, 35],
  "speed_level": "slow",
  "assist_level": "low",
  "reason": "M55 reports confident elbow flexion intent with low fatigue",
  "requires_human_confirm": true,
  "forbidden_direct_control": true
}
```

#### MuJoCo 仿真怎么使用 EMG

MuJoCo 里不要一开始模拟真实肌肉电生理。第一版把 EMG 当成“人类意图输入”更实际。

仿真输入分三层：

1. 真实回放：从 rosbag/JSONL 读取 `m55_emg_intent_v1`，和 `/joint_states`、`/rehab_arm/safety_state` 对齐。
2. 合成意图：手动生成 `elbow_flexion confidence=0.8` 这类低频意图，用来测试 VLA/规划器。
3. 高级人体模型：以后再把 EMG、肌肉疲劳、交互力和人体骨骼模型结合。

仿真中 EMG 摘要可进入：

- `/rehab_arm/sensor_state`：传感和 M55 模型摘要。
- `/rehab_arm/model_state`：M55 或服务器模型输出摘要。
- rosbag/JSONL 数据集：用于后续训练 VLA grounding、意图模型和疲劳模型。

推荐第一版数据频率：

| 数据 | 频率 | 去向 |
|---|---:|---|
| 原始 EMG ADC | 500-1000 Hz | C8T6/M33/M55 本地窗口，不直接给 VLA |
| EMG 特征窗口 | 20-100 Hz | M55 输入或 M33 汇总 |
| M55 意图/疲劳摘要 | 2-10 Hz | NanoPi/服务器/VLA/仿真回放 |
| VLA task goal | 0.1-1 Hz | 服务器到 NanoPi，人工确认或规划器审核 |
| JointTrajectory | 按规划段 | NanoPi 到 M33，M33 最终审核 |

#### 最小可执行流程

先做这个闭环：

```text
离线录制 4 路 EMG + joint_states + safety_state
  -> M55 或离线脚本生成 m55_emg_intent_v1
  -> MuJoCo 回放同一段动作
  -> VLA 读取 M55 摘要和机器人状态
  -> 输出 task_goal
  -> 规划器在 MuJoCo 里验证
  -> NanoPi dry-run 接收，不发 0x320
```

验收标准：

- 原始 EMG 不进 VLA 实时闭环。
- M55 输出里明确 `suggestion_only_not_motion_permission`。
- VLA 输出里明确 `forbidden_direct_control=true`。
- MuJoCo 能用 M55 摘要驱动“意图场景”，但不会直接代表真机运动许可。
- NanoPi 在 dry-run 下收到候选轨迹，CAN 上没有 `0x320`。

### 阶段 8：低能量台架验证

只有前面阶段都通过后，才考虑打开真机目标发送。

必须满足：

- M33 heartbeat 正常。
- `/rehab_arm/safety_state.motion_allowed=true`，且不是 `bench_armed` 冒充正式穿戴许可。
- `/rehab_arm/motor_state` 有 fresh 反馈。
- `/joint_states` 不是 stale 0。
- joint mapping 已确认。
- 患者/台架 profile 已审核。
- 急停可用。
- 目标角度小、速度慢、力矩/电流限制保守。

第一轮只允许极小动作，例如 1 到 3 度，不做连续康复训练。

## 5. 当前最小任务清单

按这个顺序做，每一步都可以单独验收：

1. 固化原始 URDF：保存 zip、记录关节表。
2. 建 `rehab_arm_description` cleaned Xacro。
3. 写 `joint_mapping.yaml`，先允许 `motor_id: null`。
4. 写 `joint_limits.yaml`，先用保守仿真限位。
5. 建 MuJoCo `rehab_arm_scene.xml`，只加载静态模型。
6. 给每个 joint 加 position actuator。
7. 用简化 collision 替代 raw STL collision。
8. 写 MuJoCo ROS2 node，发布 `/joint_states`。
9. 仿真主机无线 ROS2 发现 NanoPi topic。
10. NanoPi target disabled 下接收 dry-run `JointTrajectory`。
11. 服务器/VLA 只下发 task goal JSON。
12. task goal 在仿真主机变成仿真轨迹。
13. 仿真轨迹通过质量门后，再讨论台架小角度真机验证。

## 6. 不要做的事

- 不要把当前 raw URDF 直接当正式 MuJoCo 控制模型。
- 不要保留 `continuous` 关节进入外骨骼临床控制。
- 不要用 raw STL mesh 做全部 collision。
- 不要让 VLA 输出 CAN、电流、力矩、速度或裸电机位置。
- 不要让仿真主机无线 ROS2 直接控制电机。
- 不要让服务器绕过 NanoPi/M33。
- 不要把 `bench_armed` 当作正式穿戴许可。
- 不要把 stale 的 `/joint_states=0` 当真实姿态。

## 7. 推荐验收表

| 阶段 | 验收物 | 通过条件 |
|---|---|---|
| 0 | 原始 URDF 记录 | link/joint/mesh/质量表完整 |
| 1 | cleaned URDF/Xacro | RViz 可加载，joint 名统一 |
| 2 | joint mapping | 每个 joint 来源、方向、motor_id 状态明确 |
| 3 | MuJoCo scene | 可加载、不爆炸、单关节可动 |
| 4 | ROS2 sim node | `/joint_states` 稳定发布 |
| 5 | 无线 ROS2 | 仿真主机能看到 NanoPi topic |
| 6 | dry-run 轨迹 | NanoPi 收到 ROS 轨迹但不发 `0x320` |
| 7 | VLA task goal | VLA 只出高层 JSON，不出底层控制 |
| 8 | 台架小动作 | M33 放行、fresh 反馈、急停有效、角度极小 |

## 8. 给后续 AI/工程师的提示词

可以直接把下面这段给后续 AI：

```text
当前项目是医疗康复外骨骼机械臂。请继续 MuJoCo 仿真模型补齐，不要绕过 M33。VLA 链路固定为 VLA/服务器 -> NanoPi -> M33，仿真主机通过无线 ROS2 接 NanoPi。当前 raw URDF 有 7 links、6 continuous joints，但缺少最终 ROS joint 名、人体 ROM、速度/力矩限制、actuator、简化 collision、joint-to-motor mapping。请优先创建 rehab_arm_description cleaned Xacro、joint_mapping.yaml、joint_limits.yaml 和 MuJoCo 最小 scene；所有真机轨迹必须先 dry-run，NanoPi enable_target_tx=false，不能发 0x320。
```
