# 医疗康复外骨骼机械臂平台化开发方案

更新时间：2026-05-15

本文把 YueSpeak 暂停，把医疗康复外骨骼机械臂作为平台上的第一个重型真实项目来推进。目标不是把平台改成机械臂专用系统，而是用这个项目倒逼平台具备通用的设备调试、总线采集、只读桥、数据工厂、Runner 派工和强审能力。

## 1. 输入材料结论

### 1.1 两张图的有效信息

图 1 的核心不是具体连线，而是“多智能层 + 多硬件节点 + 数据闭环”：

- 电脑/服务器是高层智能与训练平台。
- APP 是患者/治疗师交互入口。
- 英飞凌板负责本地实时控制、语音/小模型、CAN 总线、安全保护。
- NanoPi 负责 ROS、摄像头、局部桥接、Linux 侧执行。
- 小模型、VLA、OpenClaw 不直接越过安全层驱动电机。
- 输入包含图像、语音、电机和传感器数据；输出是实时 action 或训练/报告。

图 2 的核心是平台开发流程：

- 先让线程读仓库和文档，明确每个分支职责。
- 再通过 Boss/NPC 创建知识库、技能和分工。
- 再把平台补成 CAN 调试台、串口调试台、数据采集工厂、模型训练调度、ROS 只读桥。
- 最后通过机械臂项目完善平台本身。

### 1.2 文档结论

旧《开发计划文档》偏 PSoC Edge E84 + APP/OpenClaw + CAN 传感器。v2.0 已经更合理地转成：

- PSoC Edge E84：快、稳、安全、本地轻量模型。
- NanoPi M5：ROS2、MoveIt、状态机、相机、桥接、日志。
- 外部训练/VLA 电脑：大模型、训练、视觉/语言任务理解。
- APP/OpenClaw：交互、报告、任务编排。

你的新方向进一步收敛为：第一阶段先别做泛机器人说明页，平台要先能真实调 CAN、调串口、读 ROS、采数据、把数据进训练工厂。

## 2. 仓库分支地图

仓库：`https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator`

已扫到分支：

| 分支 | 当前定位 | 可复用内容 | 主要风险 |
| --- | --- | --- | --- |
| `main` | 总文档与旧架构入口 | 项目背景、早期 CAN ID、M33/M55/APP 关系 | 架构已被新双主控方案部分替代 |
| `APP` | Android 康复机械臂 APP | Kotlin/Compose 页面、蓝牙/HTTP/OpenClaw、`ProtocolParser.kt`、`PROTOCOL.md` | 含大量 `build/` 生成物，需清理后再作为源码基线 |
| `C8T6` | STM32F103 传感器 CAN 节点 | CubeMX/CMake、`CAN1` 初始化、MAX30100/IMU/ADC 方向 | 目前更像基础工程，传感器帧协议和平台数据 schema 需重定 |
| `M33` | 英飞凌 M33 实时控制核心 | CAN 驱动、安全系统、传感器管理、控制层、蓝牙/HTTP/OpenClaw 接口 | 当前 CAN ID 还是 3 轴旧方案，需升级到多电机 + 传感器 + 支架 |
| `M55` | 英飞凌 M55 AI/语音/模型核心 | TensorFlow Lite Micro 管理器、语音服务、M33/M55 通信、唤醒词/ASR/TTS 接口 | 语音和模型线已混杂，需明确哪些模型真放 M55，哪些放训练电脑 |
| `NanoPi_ROSNode` | NanoPi ROS2 工作空间 | ROS2 Jazzy、摄像头 WebSocket、HTTP bridge、OpenClaw bridge、launch | HTTP bridge 现在有写命令入口，平台第一阶段应只读接入，写操作强审 |
| `ROS_VLA_WebSocket` | ROS/VLA/Infineon WebSocket 中继 | Node.js WebSocket、ROS/VLA/Infineon 角色注册、监控 UI | 适合改成平台只读桥原型，但 VLA 指令下发必须进强审 |
| `ai` | VLA 任务解析原型 | `ResolvedTask` schema、task parser、grounding、phase、confirmation、ROS msg/srv | 适合作为高层任务理解，不可直接输出电机命令 |
| `nanopi-sdk` | NanoPi CAN HAT / MCP2518FD 配置 | SPI overlay、`setup-can.sh`、can0 配置 | 需要在真实 NanoPi Linux 上验证，平台只能先做检查/采集/回放 |
| `wake-word-model` | 唤醒词训练与 PSoC 部署 | 训练、TFLite、C array、验收报告、microfrontend 参数 | 唤醒词不是机械臂第一阶段主线，可作为小模型部署流水线样板 |
| `PCB` | 电源板与 STM32 主控板资料 | 嘉立创 EDA zip，说明电源和 STM32 采集板 | 需要硬件 BOM/接口定义后再进入平台证据库 |

## 3. 推荐总架构

### 3.1 设备网络

第一阶段建议把物理链路收敛成：

```text
平台服务器 / 训练电脑
  |  HTTPS / WebSocket / Runner
  v
Runner 电脑
  |  平台派工、训练、数据整理、仿真、VLA
  |
NanoPi M5 / Linux Runner
  |  ROS2 只读桥、SocketCAN can0 只读采集、串口只读采集、rosbag
  |
CAN 总线
  |-- PSoC Edge E84 M33/M55
  |-- 电机 0x100~0x10F
  |-- C8T6 传感器节点 0x300~0x31F
  |-- 支架/底盘/电源/安全节点 0x400~0x4FF
```

重要调整：

- NanoPi、英飞凌、电机、C8T6 都是 CAN 网络里的设备，但平台不应该默认谁是永久主站。
- 平台第一阶段只做监听、采集、解析、回放、建议和强审，不默认写入 CAN。
- ROS 只读桥读取 ROS topic/service/action 状态，识别有价值信息后发给对应 Runner 线程做分析或草案，不直接 publish。

### 3.2 智能分层

| 层 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| PSoC M33 | CAN、实时控制、安全限位、局部状态、低延迟保护 | 大模型、复杂规划、训练发布 |
| PSoC M55 | 小模型推理、语音唤醒/轻量语音、EMG/异常/阶段识别 | VLA 主体、直接绕过 M33 控制电机 |
| C8T6 | 传感器采集与 CAN 打包 | 决策、医疗结论 |
| NanoPi | ROS2、SocketCAN、串口、相机、rosbag、状态机、只读桥 | 高频闭环、绕过安全门写硬件 |
| Runner 电脑 | 数据训练、VLA、仿真、报告、仓库构建 | 直接真实运动 |
| 平台 | 派工、数据工厂、调试台、证据链、强审、回执 | 替人确认医疗/硬件/发布 |

## 4. 平台应新增的通用能力

### 4.1 机器人工作台第一阶段改造

当前机器人工作台应先去掉泛机器人说明项，第一屏改成 HMI/IDE：

```text
左栏：设备树 / 通道
  - CAN 总线 can0/can1
  - 串口 ttyUSB0/COMx
  - ROS 只读桥
  - 电机节点
  - 传感器节点
  - Runner 电脑

中间：当前调试台
  - CAN 总线帧表 / 波形 / 解码
  - 串口收发日志 / 协议解析
  - ROS topic/state 只读面板
  - 当前设备状态和异常

右栏：属性 / 证据 / 动作门
  - 采样频率
  - DBC/协议映射
  - 解码字段
  - 风险门
  - 写入动作申请

底部：事件 / 回执 / 数据包
  - 最新帧
  - 采集批次
  - Runner 回执
  - 错误和人工决定
```

### 4.2 CAN 总线调试台

平台通用对象：

- 总线：`bus_id`, `interface`, `bitrate`, `mode`, `owner_runner`
- 节点：`node_id`, `device_type`, `vendor`, `capability`, `safety_class`
- 帧：`can_id`, `dlc`, `payload_hex`, `timestamp`, `direction`, `decoded_fields`
- 解码协议：DBC 或平台自定义 JSON decoder
- 采样任务：`signals`, `frequency_hz`, `duration`, `trigger`, `storage_policy`

第一阶段只支持：

- 只读 candump 风格帧流。
- CAN ID 分组和颜色。
- 原始帧 + 解码字段并列。
- 按 CAN ID / 信号名 / 节点过滤。
- 采样频率设定和批次保存。
- 写帧按钮存在但默认锁住，必须走人工强审。

机械臂初始 CAN ID 建议：

| 范围 | 用途 |
| --- | --- |
| `0x100-0x10F` | 电机控制与状态 |
| `0x200-0x20F` | 电机反馈聚合或驱动器状态 |
| `0x300-0x31F` | C8T6 传感器：EMG、IMU、心率、血氧 |
| `0x400-0x4FF` | 支架、底盘、电源、急停、安全 |
| `0x500-0x5FF` | 调试、版本、心跳、诊断 |

### 4.3 串口调试台

平台通用对象：

- 端口：`port`, `baudrate`, `data_bits`, `parity`, `stop_bits`
- 帧协议：行协议、二进制帧、JSON 行、CRC 帧
- 数据方向：只读、草案写入、强审写入

第一阶段支持：

- 串口只读日志。
- JSON/ASCII 自动识别。
- 行协议解析器。
- “发送命令”先做草案，不直接写串口。
- 人工审核后由 Runner 执行写入，并必须回执。

适用场景：

- 英飞凌调试串口。
- C8T6 串口输出。
- 电机驱动板串口日志。
- NanoPi 上 USB 转串口设备。

### 4.4 ROS 只读桥

第一版只读桥只做：

- `ros2 topic list`
- `ros2 topic echo --once` 或固定频率采样
- `ros2 node list`
- `ros2 param dump` 的只读版本
- `rosbag record` 草案生成
- topic/schema 映射到平台数据工厂

明确禁止自动做：

- `ros2 topic pub`
- `ros2 service call`
- `ros2 action send_goal`
- launch/restart 节点
- 改参数

当只读桥读到有价值信息后，平台动作是：

1. 生成“观察卡片”：topic、时间、关键字段、异常。
2. 发给负责 ROS 电脑的 Runner 线程。
3. Runner 线程做分析、给出建议或生成仿真/只读检查命令。
4. 涉及写 ROS 的动作进入强审。

### 4.5 数据训练工厂

数据工厂必须成为机械臂项目的中心，而不是附属页面。

#### 数据来源

- CAN 电机数据：角度、速度、电流、温度、故障码、位置误差。
- C8T6 传感器：EMG、IMU、心率、血氧。
- PSoC 小模型输出：意图、异常、阶段。
- ROS：joint_states、tf、任务状态、safety_state、rosbag。
- 摄像头：顶部相机、末端相机。
- APP/OpenClaw：患者任务、训练模式、语音文本、报告。

#### 采样任务

每个采样任务必须明确：

- 采样对象：信号列表。
- 采样频率：例如 EMG 500-2000Hz，电机 100-500Hz，ROS 状态 10-50Hz，视频 5-30fps。
- 时间同步：Runner 本地时间 + 设备时间戳 + 批次时间。
- 触发方式：手动、任务开始、异常、阈值、训练模板。
- 隐私等级：普通工程数据、患者数据、医疗敏感数据。

#### 数据集 schema

建议第一版统一成：

```json
{
  "dataset_id": "rehab-arm-session-001",
  "session": {
    "project_id": "medical_rehab_arm",
    "patient_ref": "匿名患者或模拟对象",
    "mode": "passive|active|assist|debug|simulation",
    "operator": "human",
    "started_at": "ISO8601"
  },
  "streams": [
    {
      "stream_id": "can_motor",
      "source": "can0",
      "frequency_hz": 200,
      "signals": ["m1.angle", "m1.current", "m1.temp"]
    }
  ],
  "events": [
    {
      "t": 1.23,
      "type": "manual_marker|model_prediction|safety_warning",
      "label": "elbow_flex_start",
      "confidence": 0.82
    }
  ],
  "artifacts": {
    "raw": "平台托管数据对象",
    "preview": "下采样预览",
    "labels": "人工确认标签"
  }
}
```

#### 训练回流

数据工厂要支持四类训练：

1. EMG 意图识别：PSoC/M55 小模型。
2. 异常检测：PSoC/M55 小模型。
3. 动作阶段识别：PSoC/M55 或 NanoPi。
4. VLA 任务解析/grounding/阶段建议：训练电脑。

平台边界：

- AI 可以预标注低置信片段。
- 人确认标签和训练发布。
- 模型可生成部署候选，但烧录和真实启用必须强审。

## 5. 推荐 NPC / Runner 工位

### 5.1 平台 NPC 分工

| NPC | 职责 | 第一阶段任务 |
| --- | --- | --- |
| Boss | 目标拆解、派工、验收链 | 维护机械臂项目任务树和安全边界 |
| 仓库/架构 NPC | 分支地图、代码归档、接口契约 | 清理 APP 生成物，建立 mono-repo 或分支迁移计划 |
| CAN/串口 NPC | 总线协议、调试台需求 | 建 CAN ID 表、帧 decoder、串口协议 |
| ROS/NanoPi NPC | ROS 只读桥、Linux Runner | 把 NanoPi_ROSNode 收成只读桥与 rosbag 入口 |
| 数据工厂 NPC | 采样、数据集、标注、训练 | 定义 sampling job、dataset schema、训练回流 |
| PSoC/M55 NPC | 小模型与固件接口 | 定义 M33/M55 数据接口与模型部署候选 |
| 安全/QA NPC | 医疗/硬件/强审 | 确认任何写入、运动、烧录都不自动执行 |

### 5.2 Runner 电脑划分

| Runner | 物理位置 | 能做什么 | 不能自动做什么 |
| --- | --- | --- | --- |
| 平台服务器 | 云/VPS/局域网服务器 | Web/API、任务、数据索引、报告 | 直接硬件动作 |
| 训练电脑 | GPU/高性能 PC | 模型训练、VLA、仿真、数据处理 | 发布模型到硬件 |
| NanoPi Runner | 机械臂本机 Linux | CAN 只读、串口只读、ROS 只读、rosbag | 写 CAN、写 ROS、上电运动 |
| APP Runner | Android 开发电脑 | APP 构建、模拟器、UI 测试 | 医疗结论 |
| PSoC Runner | 英飞凌开发电脑 | 编译、静态检查、生成烧录包 | 自动烧录/启用真实控制 |

## 6. 第一阶段开发顺序

### 第 0 阶段：项目入库与知识库

目标：

- 在平台里创建“医疗康复机械臂”项目，不再挂 YueSpeak。
- 仓库各分支进入项目证据库。
- 两份文档、两张图进入项目资料。
- Boss 创建工位和 NPC 知识库。

验收：

- 工作台能从项目主页进入机械臂任务树。
- 分支地图可见。
- 人工边界卡可见。

### 第 1 阶段：CAN 只读调试台

目标：

- NanoPi Runner 能声明 `can0` 能力。
- 平台能显示 CAN 总线、节点、帧流、解码字段。
- 能设采样频率并保存批次。

最小闭环：

```text
NanoPi candump/can monitor
-> Runner 上报帧
-> 平台 CAN 调试台显示
-> 数据工厂保存采样批次
-> NPC 生成解码建议
-> 人确认协议表
```

验收：

- 不插真实电机时可用回放文件验证。
- 接真实 CAN 时默认只读。
- 写帧入口必须显示“需要人工强审”。

### 第 2 阶段：串口只读调试台

目标：

- 平台接收串口日志。
- 支持 JSON 行/ASCII/二进制 hex 预览。
- 串口写入只生成草案。

验收：

- 英飞凌/C8T6 串口日志能进入平台。
- 命令草案不会自动发送。

### 第 3 阶段：数据训练工厂

目标：

- 建立采样任务。
- CAN/串口/ROS 数据进入统一 dataset。
- AI 做预标注，人做确认。

第一批数据集：

- 电机静态数据：节点在线、温度、电流、角度。
- EMG 空载数据：放松/发力/噪声。
- IMU 姿态数据：静止/缓慢移动。
- ROS 只读状态：joint_states/tf/safety_state。

验收：

- 用户能在数据工厂看到当前样本、波形、低置信片段、标签、导出。

### 第 4 阶段：ROS 只读桥

目标：

- NanoPi Runner 上报 topic 列表、节点列表、关键 topic 采样。
- 平台识别有用信息并派给 ROS Runner 线程分析。

验收：

- `/joint_states`、`/tf`、`/rehab/safety_state` 等只读展示。
- 平台能从异常 topic 生成派工卡。
- 不发生自动 publish/service/action。

### 第 5 阶段：训练与模型部署候选

目标：

- 数据工厂触发训练电脑 Runner。
- 训练 EMG/异常/阶段识别候选模型。
- 生成部署包候选和评估报告。

验收：

- 模型只到“候选发布”。
- 人工确认后才进入烧录或启用流程。

## 7. 平台通用化要求

这次不能把页面命名成“医疗机械臂专用”。平台能力应抽象为：

- 设备工作台：适配机器人、汽车、无人机、工控、IoT。
- 总线调试：CAN、串口、后续 EtherCAT/Modbus。
- 数据工厂：任意传感器/日志/图像/音频/事件流。
- 只读桥：ROS、系统日志、数据库、生产线设备。
- Runner 派工：按电脑能力派任务。
- 强审动作门：所有真实世界写入动作统一受控。

机械臂项目只是一个配置包：

- 设备模板：康复机械臂。
- 协议模板：CAN ID / 串口 / ROS topic。
- 数据模板：EMG/IMU/电机/相机/训练 session。
- 安全模板：医疗、硬件、运动、写入、烧录、发布。

## 8. 安全边界

绝不自动执行：

- 真实上电。
- 电机运动。
- CAN 写帧。
- 串口写命令。
- firmware 烧录。
- ROS publish/service/action/write 参数。
- 模型发布到硬件。
- 训练数据医疗结论。
- 医疗/康复最终验收。

可以自动执行：

- 仓库读取。
- 静态分析。
- 数据 schema 校验。
- 回放数据解析。
- 仿真/只读测试。
- 训练草案。
- 文档生成。
- 派工和证据整理。

## 9. 下一轮建议派工

### Boss 派工 1：仓库重组方案

输出：

- 分支到模块映射。
- 哪些文件迁移到 `apps/android`、`firmware/psoc-m33`、`firmware/psoc-m55`、`firmware/c8t6`、`robot/nanopi_ros`、`ai/vla`。
- 哪些 build 产物删掉。

### Boss 派工 2：CAN 调试台薄片

输出：

- 平台 UI 第一屏。
- 采样任务 API 草案。
- CAN 帧 mock 数据。
- 数据工厂接收最小闭环。

### Boss 派工 3：ROS 只读桥薄片

输出：

- Runner 能力声明。
- topic 只读采样格式。
- 从 ROS 异常到 NPC 派工的卡片流程。

### Boss 派工 4：数据工厂 schema

输出：

- dataset/session/stream/event/label schema。
- EMG/IMU/电机/ROS/图像数据的第一版映射。
- AI 预标注与人工确认流程。

## 10. 最小可交付里程碑

两周内平台与机械臂项目的共同 MVP：

1. 平台项目主页能进入机械臂项目，不再是 YueSpeak 主线。
2. 仓库分支地图进入观测台/证据库。
3. 机器人工作台显示 CAN 调试台、串口调试台、ROS 只读桥，而不是泛机器人说明。
4. CAN 回放数据能进入数据工厂。
5. 数据工厂能按采样频率保存一批电机/传感器数据。
6. ROS 只读桥能读取 topic 列表和一条模拟 `/joint_states`。
7. 任意写入动作都显示强审门。
8. Boss/NPC 能围绕上述真实工位派单和回执。

## 11. 无 NPC 依赖的完整执行分工

后续如果切换到新的项目工作区，先不要依赖现有 NPC 派工结果。所有分工可以由 Codex 主线程按下面工作包顺序直接推进。

### 11.1 工作包 A：新项目工作区初始化

目标：把机械臂项目从平台样例项目中独立出来。

要做：

1. 创建新平台项目，例如 `proj_medical_rehab_arm`。
2. 绑定外部仓库 `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator`。
3. 把两份需求文档、两张架构图、本文档导入项目资料。
4. 在项目首页显示：
   - 当前阶段：硬件接入前的平台工具面建设。
   - 当前禁止动作：真实上电、真实运动、CAN 写入、串口写入、firmware 烧录、ROS 写操作。
   - 当前允许动作：仓库只读、mock 数据、回放数据、仿真、schema、UI、Runner 只读采集。

验收：

- 新项目不再出现 YueSpeak 作为主目标。
- 项目目标写清楚是“具身智能医疗康复外骨骼机械臂”。
- 平台仍保持通用，不出现“平台只服务机械臂”的文案。

### 11.2 工作包 B：仓库整理与模块边界

目标：把多分支产物整理成能被平台理解的模块地图。

建议模块：

```text
medical-rehab-arm/
  app/android/                 # 来自 APP 分支，清理 build 产物后迁入
  firmware/psoc-m33/           # 来自 M33
  firmware/psoc-m55/           # 来自 M55
  firmware/stm32-c8t6/         # 来自 C8T6
  robot/nanopi-ros/            # 来自 NanoPi_ROSNode
  robot/ros-vla-bridge/        # 来自 ROS_VLA_WebSocket
  ai/vla-task-resolver/        # 来自 ai
  ai/wake-word-model/          # 来自 wake-word-model
  linux/nanopi-can/            # 来自 nanopi-sdk
  hardware/pcb/                # 来自 PCB
  docs/
```

第一轮不要真正大迁移仓库，先生成平台模块索引：

| 模块 | 来源分支 | 当前用途 | 第一阶段动作 |
| --- | --- | --- | --- |
| Android App | `APP` | 患者/治疗师交互、蓝牙/HTTP、传感器显示 | 清理 build 产物，保留通信协议和 UI |
| PSoC M33 | `M33` | CAN、传感器、安全、控制 | 升级 CAN ID 表和只读状态输出 |
| PSoC M55 | `M55` | 小模型、语音、M33/M55 通信 | 明确小模型槽位与部署候选 |
| STM32 C8T6 | `C8T6` | 传感器 CAN 节点 | 定义 EMG/IMU/心率 CAN 帧 |
| NanoPi ROS | `NanoPi_ROSNode` | ROS2、HTTP bridge、相机 | 先改造成只读桥与数据采集入口 |
| ROS/VLA WS | `ROS_VLA_WebSocket` | WebSocket 中继 | 只保留监控和只读转发，写操作进强审 |
| VLA Resolver | `ai` | 任务解析、grounding、阶段判断 | 作为高层建议，不直接控电机 |
| NanoPi CAN | `nanopi-sdk` | SocketCAN/overlay | 真实 NanoPi 上验证前只做脚本审查 |
| Wake Word | `wake-word-model` | 小模型训练部署样例 | 作为模型流水线样板，不做第一优先 |
| PCB | `PCB` | 电源与 STM32 板资料 | 入证据库，等待 BOM/接口表 |

验收：

- 平台能显示每个模块、来源分支、负责人、风险等级、下一步。
- `APP` 分支生成物风险被明确标记。

### 11.3 工作包 C：机器人工作台收敛为设备调试台

目标：把当前机器人工作台从“机器人说明页”改成通用设备调试台。

第一屏布局：

```text
左栏：对象树
  - 总线：can0 / can1
  - 串口：ttyUSB0 / COMx
  - ROS：topic / node / bag
  - 设备：PSoC / C8T6 / motor / NanoPi / runner

中间：当前工具面
  - CAN 帧流、解码表、波形
  - 串口日志、协议解析
  - ROS 只读 topic 状态
  - 当前异常与建议

右栏：属性与强审
  - 采样频率
  - 解码协议
  - 设备能力
  - 写入动作申请
  - 人工审核状态

底部：事件线
  - 采集批次
  - Runner 回执
  - 异常记录
  - 人工决定
```

第一轮页面只需要 mock/回放数据：

- `can0` 节点列表。
- `0x100` 电机状态。
- `0x300` C8T6 传感器状态。
- `/joint_states` 只读状态。
- “写 CAN 帧”“写串口”“ROS publish”按钮全部锁住并显示强审。

验收：

- 用户一眼看到这是调试台，不是长页面。
- 不出现自动真实运动入口。
- 所有写入动作都不可直接执行。

### 11.4 工作包 D：CAN 只读采集与回放

目标：先用回放数据打通平台链路，再接 NanoPi 真实 can0。

数据格式建议：

```json
{
  "source": "can0",
  "timestamp_ns": 0,
  "can_id": "0x100",
  "dlc": 8,
  "payload_hex": "0102030405060708",
  "direction": "rx",
  "decoded": {
    "device": "motor_1",
    "angle_deg": 12.3,
    "current_a": 0.8,
    "temperature_c": 31.2,
    "fault": 0
  }
}
```

平台接口需要支持：

- 上传一批 CAN 帧。
- 查询最近帧。
- 按 CAN ID 过滤。
- 按设备过滤。
- 保存为采样批次。
- 导出到数据工厂。

真实 NanoPi Runner 第一版命令只允许：

```bash
ip -details link show can0
candump can0
```

禁止：

```bash
cansend
```

验收：

- mock CAN 帧能显示在机器人工作台。
- CAN 批次能进入数据工厂。
- 写入命令只生成待审卡。

### 11.5 工作包 E：串口只读采集

目标：把英飞凌/C8T6/电机驱动板串口日志纳入平台。

数据格式建议：

```json
{
  "source": "ttyUSB0",
  "timestamp_ns": 0,
  "baudrate": 115200,
  "raw": "{\"emg\":123,\"hr\":76}",
  "parsed": {
    "emg": 123,
    "heart_rate": 76
  },
  "parse_status": "ok"
}
```

第一版支持：

- 串口行日志。
- JSON 行解析。
- hex 预览。
- 错误行标记。
- 发送命令草案。

验收：

- `ProtocolParser.kt` 里兼容的传感器 JSON 能在平台里解析。
- 串口写入入口必须强审。

### 11.6 工作包 F：ROS 只读桥

目标：把 NanoPi ROS 信息变成平台可见证据，并能触发 Runner 分析任务。

只读采集对象：

- `ros2 topic list`
- `/joint_states`
- `/tf`
- `/rehab/safety_state`
- `/rehab/session_state`
- `/camera/*/image_raw` 的元信息和抽帧
- rosbag 文件索引

平台数据格式：

```json
{
  "runner_id": "nanopi-ros-runner",
  "topic": "/joint_states",
  "schema": "sensor_msgs/msg/JointState",
  "timestamp_ns": 0,
  "sample": {
    "name": ["m1", "m2"],
    "position": [0.1, 0.2],
    "velocity": [0.0, 0.0],
    "effort": [0.3, 0.4]
  }
}
```

触发派工：

```text
ROS 只读桥发现异常/有价值状态
-> 平台生成观察卡片
-> 派给 ROS Runner 线程
-> Runner 只做分析/仿真/报告
-> 如果建议写 ROS，进入人工强审
```

验收：

- 只读 topic 能进平台。
- 平台能根据状态生成“分析任务”。
- 不自动 publish/service/action。

### 11.7 工作包 G：数据训练工厂

目标：机械臂所有数据都能进入平台形成训练集，而不是散落在 APP、ROS、固件日志里。

第一版数据流：

```text
CAN / 串口 / ROS / APP / 图像
-> Runner 采集
-> 平台采样批次
-> 数据工厂样本
-> AI 预标注
-> 人工确认
-> 训练任务
-> 模型候选
-> 人工发布
```

关键 UI：

- 左栏：数据源、采样任务、数据集、标签集。
- 中间：当前样本、波形、图像帧、事件。
- 右栏：采样频率、schema、标签、AI 建议、QA。
- 底部：采集日志、训练回执、导出记录。

第一批标签：

- `relax`
- `elbow_flex_intent`
- `shoulder_lift_intent`
- `resist`
- `fatigue_warning`
- `normal`
- `unexpected_resistance`
- `stuck`
- `need_stop`
- `prepare`
- `assist`
- `hold`
- `return`
- `done`

验收：

- 能用 mock/回放数据创建一个训练集。
- AI 可以给低置信片段建议。
- 人才能确认标签和发布训练结果。

### 11.8 工作包 H：小模型与训练发布链

目标：先定义模型流水线，不急着烧录硬件。

模型优先级：

1. EMG 意图识别。
2. 异常检测。
3. 动作阶段识别。
4. 支架助力意图。
5. 唤醒词。
6. VLA 高层任务解析。

平台模型对象：

```json
{
  "model_id": "emg-intent-v0",
  "target": "psoc-m55",
  "input_streams": ["emg_ch1", "emg_ch2", "imu"],
  "window_ms": 200,
  "labels": ["relax", "elbow_flex_intent"],
  "metrics": {
    "accuracy": 0.0,
    "latency_ms": 0.0
  },
  "release_state": "candidate"
}
```

发布边界：

- `candidate`：平台可自动生成。
- `approved_for_lab`：人确认。
- `flashed_to_device`：必须人工执行或人工批准 Runner 执行。
- `enabled_in_real_session`：必须二次强审。

验收：

- wake-word-model 可作为模型验收报告样板。
- EMG/异常/阶段模型先走假数据或录制数据。

### 11.9 工作包 I：强审与医疗安全

目标：所有真实世界动作统一进入强审，不让页面散落危险按钮。

强审类型：

- `hardware_power`
- `can_write`
- `serial_write`
- `firmware_flash`
- `ros_publish`
- `ros_service`
- `ros_action`
- `motion`
- `model_release`
- `medical_acceptance`
- `deployment`

每个强审卡必须包含：

- 谁发起。
- 目标设备。
- 动作内容。
- 风险等级。
- 只读证据。
- 回滚/停止方案。
- 预计影响。
- 人工批准按钮。
- 人工拒绝按钮。

验收：

- 没有任何真实写入绕过强审。
- AI/NPC/Runner 只能提交建议或草案。

## 12. 换工作区后的第一天执行清单

如果马上切新项目工作区，第一天建议按这个顺序做：

1. 建项目：`医疗康复外骨骼机械臂`。
2. 录入仓库 URL 和分支列表。
3. 导入本文档、两份原始文档、两张图。
4. 建模块地图，不搬代码。
5. 建安全边界卡。
6. 改机器人工作台第一屏 mock：CAN / 串口 / ROS 只读 / 强审。
7. 建 CAN mock 数据和 decoder。
8. 让 CAN mock 数据进入数据工厂。
9. 建 ROS 只读 mock：`/joint_states`。
10. 建“ROS 只读发现 -> Runner 分析任务”的卡片流。

第一天不要做：

- 烧录。
- 上电。
- 真实电机运动。
- 真实 CAN 写入。
- ROS 写操作。
- 大仓库重构。

## 13. Codex 单线程推进方式

在没有 NPC 的情况下，Codex 主线程按下面节奏推进：

1. 每轮开始先看当前项目工作区状态。
2. 优先改平台通用能力，不做机械臂硬编码。
3. 每次只做一个薄片：
   - 页面 UI
   - mock 数据
   - API/schema
   - 验收脚本
4. 每个薄片都必须有：
   - 用户第一眼验收方式。
   - 强审边界。
   - 数据进入平台的位置。
   - 对其他项目的泛化解释。
5. 有真实硬件相关动作时，只生成待审卡和操作说明，不执行。

推荐前 6 个实现薄片：

1. 机器人工作台改成设备调试台 shell。
2. CAN mock 帧流和节点表。
3. CAN 采样批次进入数据工厂。
4. 串口日志 mock 和协议解析。
5. ROS 只读 topic mock 和观察卡片。
6. 数据工厂训练集样本/标签/AI 预标注 UI。
