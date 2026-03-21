# PSoC Edge E84 康复机械臂系统 - M33核心

> 基于英飞凌PSoC Edge E84的医疗康复机械臂控制系统 - Cortex-M33主控核心

[**中文**](#) | [**English**](./README_en.md)

## 项目简介

本项目是医疗康复机械臂系统的M33核心固件，负责实时控制、传感器数据采集、蓝牙通信和CAN总线管理。M33核心作为主控制核心，协调整个系统的运行。

## 核心功能

### 1. 蓝牙通信 (Nordic UART Service)
- **设备名称**: OpenClaw-NUS
- **服务UUID**: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- **RX特征值**: `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` (接收命令)
- **TX特征值**: `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` (发送数据)
- **MTU**: 247字节
- **数据格式**: ASCII命令 + JSON数据流

### 2. 命令协议

#### 控制命令
\`\`\`
stop                    # 紧急停止
stream:on              # 启用数据流
stream:off             # 关闭数据流
heartbeat              # 心跳检测
mode:passive           # 被动模式
mode:active            # 主动模式
mode:memory            # 记忆模式
mode:ai                # AI辅助模式
move:0:90.0            # 移动关节 (关节ID:角度)
\`\`\`

#### 数据流格式
\`\`\`json
{"s":1,"m":1,"sh":45.0,"el":30.0,"la":10.0,"hr":75,"sp":98,"e1":0.12,"e2":0.15,"sf":0}
\`\`\`

字段说明：
- \`s\`: streaming状态 (0/1)
- \`m\`: 控制模式 (0=被动, 1=主动, 2=记忆, 3=AI辅助)
- \`sh\`: 肩关节角度 (度)
- \`el\`: 肘关节角度 (度)
- \`la\`: 横向位置 (mm)
- \`hr\`: 心率 (bpm)
- \`sp\`: 血氧饱和度 (%)
- \`e1\`: EMG通道1 (mV)
- \`e2\`: EMG通道2 (mV)
- \`sf\`: 安全状态 (0=正常, 1=警告, 2=紧急)

### 3. CAN总线通信
- **波特率**: 500kbps
- **设备地址分配**:
  - \`0x100\`: 肩关节伺服电机
  - \`0x101\`: 肘关节伺服电机
  - \`0x102\`: 推杆电机
  - \`0x200-0x202\`: 电机反馈数据
  - \`0x300-0x310\`: STM32传感器节点

### 4. 传感器管理
- 肩关节角度传感器
- 肘关节角度传感器
- 横向位置传感器
- 心率传感器 (MAX30102)
- 血氧传感器
- 肌电传感器 (EMG) - 2通道
- 六轴IMU (MPU6050)

### 5. 控制模式
- **被动模式**: 电机无阻力，患者自由运动
- **主动模式**: 电机主动驱动，辅助患者运动
- **记忆模式**: 回放预设的训练动作
- **AI辅助模式**: 根据EMG信号预测意图，智能辅助

### 6. 安全系统
- 实时监控关节角度限位
- 速度限制
- 扭矩限制
- 紧急停止功能
- 异常状态检测

### 7. HTTP服务器
- 提供REST API供OpenClaw调用
- 端点：
  - \`GET /api/sensors\` - 获取传感器数据
  - \`POST /api/command\` - 执行控制命令
  - \`GET /api/status\` - 获取系统状态

## 系统架构

\`\`\`
┌─────────────────────────────────────────┐
│           Android App (手机端)           │
│  - 实时控制UI                            │
│  - 数据可视化                            │
│  - 康复评估                              │
└──────────┬──────────────────────────────┘
           │
           │ 蓝牙BLE (NUS)
           │ - 实时控制指令
           │ - 传感器数据流 (100Hz)
           │
┌──────────▼──────────────────────────────┐
│        PSoC Edge E84 - M33核心          │
│  ┌────────────────────────────────┐     │
│  │  蓝牙GATT服务                   │     │
│  │  - Nordic UART Service         │     │
│  │  - 命令解析                     │     │
│  │  - 数据分包发送                 │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  控制管理器                     │     │
│  │  - 模式切换                     │     │
│  │  - 关节控制                     │     │
│  │  - 轨迹规划                     │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  传感器管理器                   │     │
│  │  - 数据采集                     │     │
│  │  - 滤波处理                     │     │
│  │  - 数据融合                     │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  安全系统                       │     │
│  │  - 限位检测                     │     │
│  │  - 紧急停止                     │     │
│  │  - 故障诊断                     │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  CAN驱动                        │     │
│  │  - 电机控制                     │     │
│  │  - 传感器通信                   │     │
│  └────────────────────────────────┘     │
└──────────┬──────────────────────────────┘
           │
           │ CAN总线 (500kbps)
           │
    ┌──────┴──────┬──────────┬──────────┐
    │             │          │          │
┌───▼────┐  ┌────▼───┐  ┌──▼─────┐  ┌─▼──────────┐
│肩关节  │  │肘关节  │  │推杆    │  │STM32传感器 │
│伺服    │  │伺服    │  │电机    │  │节点        │
│0x100   │  │0x101   │  │0x102   │  │0x300-0x310 │
└────────┘  └────────┘  └────────┘  └────────────┘
\`\`\`

## 与M55核心通信

M33核心通过共享内存与M55核心通信：
- M33 → M55: 传感器数据快照 (用于AI推理)
- M55 → M33: AI推理结果 (运动意图预测)

## 开发环境

- **IDE**: RT-Thread Studio
- **RTOS**: RT-Thread 5.x
- **工具链**: ARM GCC
- **调试器**: J-Link / DAPLink
- **蓝牙协议栈**: Infineon AIROC Bluetooth Stack

## 编译与烧录

### 1. 导入工程
在RT-Thread Studio中导入工程：
\`File -> Import -> RT-Thread Project\`

### 2. 编译
使用scons编译或在RT-Thread Studio中点击Build按钮

### 3. 烧录
使用J-Link烧录或在RT-Thread Studio中点击Download按钮

## 蓝牙连接测试

### 使用nRF Connect (推荐)
1. 扫描并连接 "OpenClaw-NUS"
2. 找到NUS服务 (\`6E400001-...\`)
3. 启用TX特征值的通知
4. 向RX特征值写入命令: \`stream:on\`
5. 观察TX特征值接收到的JSON数据

### 命令示例
\`\`\`
# 启用数据流
stream:on

# 切换到主动模式
mode:active

# 移动肩关节到90度
move:0:90.0

# 移动肘关节到45度
move:1:45.0

# 紧急停止
stop

# 关闭数据流
stream:off
\`\`\`

## 目录结构

\`\`\`
yiliao_m33/
├── applications/
│   ├── main.c                      # 主程序
│   ├── m33/
│   │   ├── app_ble_service.c       # 蓝牙服务层
│   │   ├── bt_app_gatt_handler.c   # GATT处理器
│   │   ├── bt_app_gatt_db.c        # GATT数据库
│   │   ├── can_driver.c            # CAN驱动
│   │   ├── control_manager.c       # 控制管理器
│   │   ├── sensor_manager.c        # 传感器管理器
│   │   ├── safety_system.c         # 安全系统
│   │   ├── http_server.c           # HTTP服务器
│   │   └── openclaw_integration.c  # OpenClaw集成
│   └── common/
│       └── m33_m55_comm.c          # M33-M55通信
├── board/                          # 板级支持包
├── libraries/                      # 库文件
│   ├── HAL_Drivers/               # 硬件抽象层
│   └── components/                # 组件库
└── rtconfig.h                     # RT-Thread配置
\`\`\`

## 配置说明

### 蓝牙配置
- 文件: \`applications/m33/cycfg_gap.h\`
- MTU大小: 247字节
- 设备名称: OpenClaw-NUS

### CAN配置
- 文件: \`applications/m33/can_driver.h\`
- 波特率: 500kbps
- 过滤器: 接收0x200-0x310

### 传感器配置
- 采样频率: 100Hz
- 数据格式: JSON

## 故障排查

### 蓝牙无法连接
1. 检查蓝牙是否已初始化
2. 查看日志: \`[bt] BLE connected conn_id=xxx\`
3. 确认手机蓝牙已开启

### 无法接收数据
1. 确认已发送 \`stream:on\` 命令
2. 检查TX特征值的通知是否已启用
3. 查看日志中的发送记录

### CAN通信异常
1. 检查CAN总线连接
2. 确认波特率配置正确
3. 查看CAN错误计数器

## 相关链接

- [M55核心固件](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M55)
- [RT-Thread文档](https://www.rt-thread.org/document/site/)
- [Infineon PSoC Edge E84](https://www.infineon.com/cms/en/product/microcontroller/32-bit-psoc-arm-cortex-microcontroller/psoc-edge-e8/)

## 许可证

本项目仅供学习和研究使用。

## 作者

- GitHub: [@ChillAmnesiac](https://github.com/ChillAmnesiac)
- Email: 3245056131@qq.com
