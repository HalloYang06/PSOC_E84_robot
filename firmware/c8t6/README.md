# PSoC Edge E84 康复机械臂系统

> 基于英飞凌PSoC Edge E84的医疗康复机械臂控制系统 - 完整开发计划

## 项目概述

开发一套基于PSoC Edge E84的医疗康复机械臂控制系统，实现患者上肢康复训练的智能辅助。

### 硬件组成

- **主控板**: 英飞凌PSoC Edge E84 (Edgi-Talk开发板)
  - **Cortex-M33核心** (主控制核) - [查看代码](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M33)
  - **Cortex-M55核心** (AI推理核) - [查看代码](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M55)

- **执行机构**:
  - 伺服电机1: 肩关节纵向抬升
  - 伺服电机2: 肘关节纵向抬升
  - 推杆电机: 肩关节横向张开

- **传感器节点** (STM32C8T6):
  - MSG肌电传感器 (EMG) - 2通道
  - 心率传感器 (MAX30102)
  - 六轴IMU传感器 (MPU6050)
  - 作为独立CAN节点，采集并发送传感器数据

- **通讯**: CAN总线连接所有电机和传感器节点 (500kbps)

## 系统架构

\`\`\`
┌─────────────────────────────────────────────────────────────────┐
│                      Android App (手机端)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 患者管理     │  │ 实时控制     │  │ 康复评估     │          │
│  │ 训练记录     │  │ 数据可视化   │  │ PDF导出      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────┬──────────────────────┬──────────────────────────────────┘
         │                      │
         │ ①蓝牙BLE (实时控制)  │ ②HTTP (OpenClaw)
         │   - 快速响应         │   - 自然语言控制
         │   - 传感器数据流     │   - 复杂指令
         │                      │
         ↓                      ↓
┌────────────────────┐   ┌─────────────────────────────────────┐
│   PSoC Edge E84    │   │         OpenClaw Gateway            │
│                    │   │  (PC端运行)                         │
│  ┌──────────────┐  │   │                                     │
│  │ M33核心      │  │   │  ③HTTP桥接 (PSoC ↔ OpenClaw)       │
│  │ - CAN驱动    │◄─┼───┤  - 转发App的自然语言指令           │
│  │ - 蓝牙BLE    │  │   │  - 返回执行结果                     │
│  │ - 实时控制   │  │   │  - AI康复建议推送                   │
│  │ - 传感器管理 │  │   └─────────────────────────────────────┘
│  └──────┬───────┘  │
│         │          │
│  ┌──────▼───────┐  │
│  │ M55核心      │  │
│  │ - WiFi连接   │◄─┼─── HTTP通信
│  │ - AI推理引擎 │  │
│  │ - EMG预测    │  │
│  │ - 康复评估   │  │
│  └──────────────┘  │
└────────┬────────────┘
         │ CAN总线 (500kbps)
         │
    ┌────┴────┬────────┬────────┬────────────┐
    │         │        │        │            │
┌───▼────┐ ┌─▼──────┐ ┌▼──────┐ ┌▼──────┐ ┌─▼────────────────┐
│ 肩关节 │ │ 肘关节 │ │ 推杆  │ │ 电机  │ │ STM32C8T6        │
│ 伺服   │ │ 伺服   │ │ 电机  │ │ 反馈  │ │ 传感器节点       │
│ 0x100  │ │ 0x101  │ │ 0x102 │ │0x200-2│ │ 0x300-0x310      │
└────────┘ └────────┘ └───────┘ └───────┘ └──────────────────┘
\`\`\`

## 核心功能

### M33核心 (主控制核)

**职责**: 实时控制、蓝牙通信、CAN总线管理

- **蓝牙通信** (Nordic UART Service)
  - 设备名称: OpenClaw-NUS
  - 实时控制指令接收
  - 传感器数据流发送 (100Hz)
  - MTU: 247字节

- **CAN总线控制**
  - 电机控制 (肩关节、肘关节、推杆)
  - 传感器数据采集
  - 波特率: 500kbps

- **控制模式**
  - 被动模式: 电机无阻力
  - 主动模式: 电机主动驱动
  - 记忆模式: 回放训练动作
  - AI辅助模式: 智能辅助

- **安全系统**
  - 关节角度限位
  - 速度/扭矩限制
  - 紧急停止功能

[查看M33核心详细文档 →](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M33)

### M55核心 (AI推理核)

**职责**: WiFi连接、AI推理、康复评估

- **WiFi连接**
  - 连接局域网
  - HTTP服务器
  - OpenClaw通信

- **AI推理引擎**
  - EMG信号分析
  - 运动意图预测
  - 康复评估
  - 异常检测

- **OpenClaw集成**
  - 自然语言指令解析
  - 训练计划生成
  - 康复报告生成

[查看M55核心详细文档 →](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M55)

## 通讯协议

### 蓝牙协议 (App ↔ M33)

#### 控制命令
\`\`\`
stop                    # 紧急停止
stream:on              # 启用数据流
stream:off             # 关闭数据流
mode:passive           # 被动模式
mode:active            # 主动模式
mode:memory            # 记忆模式
mode:ai                # AI辅助模式
move:0:90.0            # 移动关节 (关节ID:角度)
\`\`\`

#### 数据流格式
\`\`\`json
{
  "s": 1,              // streaming状态
  "m": 1,              // 控制模式
  "sh": 45.0,          // 肩关节角度
  "el": 30.0,          // 肘关节角度
  "la": 10.0,          // 横向位置
  "hr": 75,            // 心率
  "sp": 98,            // 血氧
  "e1": 0.12,          // EMG通道1
  "e2": 0.15,          // EMG通道2
  "sf": 0              // 安全状态
}
\`\`\`

### HTTP API (OpenClaw ↔ M55)

#### 获取传感器数据
\`\`\`
GET /api/sensors
\`\`\`

#### 执行控制命令
\`\`\`
POST /api/command
Body: {
  "command": "move_joint",
  "joint_id": 0,
  "target_angle": 90.0
}
\`\`\`

#### AI推理请求
\`\`\`
POST /api/inference
Body: {
  "type": "emg_prediction",
  "data": [0.12, 0.15, 0.18, ...]
}
\`\`\`

## 使用场景

### 场景1: 简单实时控制 (蓝牙直连)
\`\`\`
用户点击"抬起肩关节" 
  → App通过蓝牙发送指令 
  → M33执行 
  → 实时反馈
\`\`\`

### 场景2: 自然语言控制 (OpenClaw桥接)
\`\`\`
用户说"帮我做一组康复训练"
  → App发送到OpenClaw (HTTP)
  → OpenClaw理解意图，生成训练计划
  → OpenClaw通过WiFi调用M55的HTTP API
  → M55通知M33执行训练
  → 传感器数据通过蓝牙实时返回App
  → 训练结束，OpenClaw生成康复评估
  → 评估结果返回App
\`\`\`

### 场景3: AI辅助训练 (三者协同)
\`\`\`
1. 用户在App启动"AI助力模式"
2. App通过蓝牙设置M33为AI模式
3. 患者开始运动，M33采集EMG信号
4. M33将数据发送到M55进行AI推理
5. M55预测运动意图，返回结果给M33
6. M33根据预测调整电机阻尼
7. 传感器数据通过蓝牙流式传输到App显示
8. 训练结束，App请求OpenClaw生成康复评估
9. OpenClaw调用M55获取历史数据
10. OpenClaw生成评估报告返回App
\`\`\`

## 快速开始

### 1. 克隆代码

\`\`\`bash
# M33核心 (主控制核)
git clone -b M33 git@github.com:ChillAmnesiac/Medical-Rehabilitation-Manipulator.git yiliao_m33

# M55核心 (AI推理核)
git clone -b M55 git@github.com:ChillAmnesiac/Medical-Rehabilitation-Manipulator.git wifi
\`\`\`

### 2. 开发环境

- **IDE**: RT-Thread Studio
- **RTOS**: RT-Thread 5.x
- **工具链**: ARM GCC
- **调试器**: J-Link / DAPLink

### 3. 烧录顺序

⚠️ **必须按照以下顺序烧录**：

\`\`\`
1. Secure M33 (安全核心)
2. M33 (非安全核心)
3. M55 (应用核心)
\`\`\`

### 4. 测试蓝牙连接

使用nRF Connect或其他蓝牙调试工具：
1. 扫描并连接 "OpenClaw-NUS"
2. 找到NUS服务
3. 启用TX特征值的通知
4. 向RX特征值写入: \`stream:on\`
5. 观察接收到的JSON数据

### 5. 配置WiFi (M55)

编辑 \`wifi/applications/main.c\`：
\`\`\`c
#define WIFI_SSID "your_wifi_ssid"
#define WIFI_PASSWORD "your_wifi_password"
\`\`\`

## 项目文档

- [完整开发计划文档](./开发计划文档.md) - 详细的系统设计和实现方案
- [M33核心文档](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M33) - 蓝牙通信、CAN控制
- [M55核心文档](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M55) - WiFi连接、AI推理

## 技术栈

- **硬件平台**: Infineon PSoC Edge E84
- **操作系统**: RT-Thread RTOS
- **蓝牙协议栈**: Infineon AIROC Bluetooth Stack
- **通信协议**: 
  - 蓝牙BLE (Nordic UART Service)
  - HTTP/REST API
  - CAN总线
- **AI框架**: TensorFlow Lite (计划)

## 开发进度

- [x] M33核心基础框架
- [x] 蓝牙GATT服务实现
- [x] CAN总线驱动
- [x] 传感器管理模块
- [x] 控制管理器
- [x] 安全系统
- [x] M55核心基础框架
- [x] WiFi连接模块
- [x] HTTP服务器
- [x] OpenClaw集成框架
- [ ] AI推理引擎实现
- [ ] 真实传感器数据接入
- [ ] 电机控制优化
- [ ] Android App开发
- [ ] 系统集成测试

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

本项目仅供学习和研究使用。

## 联系方式

- GitHub: [@ChillAmnesiac](https://github.com/ChillAmnesiac)
- Email: 3245056131@qq.com

## 致谢

感谢RT-Thread社区和Infineon提供的技术支持。
