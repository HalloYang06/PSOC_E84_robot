# PSoC Edge E84 康复机械臂系统 - M55核心

> 基于英飞凌PSoC Edge E84的医疗康复机械臂控制系统 - Cortex-M55 AI推理核心

[**中文**](#) | [**English**](./README_en.md)

## 项目简介

本项目是医疗康复机械臂系统的M55核心固件，负责WiFi连接、AI推理、康复评估和OpenClaw集成。M55核心作为AI推理核心，提供智能辅助功能。

**注意**: 原计划在M33核心开启WiFi，现已调整为M55核心负责WiFi功能，以充分利用M55的计算能力。

## 核心功能

### 1. WiFi连接
- 连接到局域网WiFi
- 提供HTTP服务器
- 与OpenClaw Gateway通信
- 接收自然语言指令

### 2. HTTP服务器
- 提供REST API供OpenClaw调用
- 端点：
  - \`GET /api/sensors\` - 获取传感器数据
  - \`POST /api/command\` - 执行控制命令
  - \`GET /api/status\` - 获取系统状态
  - \`POST /api/inference\` - AI推理请求

### 3. AI推理引擎
- **EMG信号处理**: 分析肌电信号，预测运动意图
- **康复评估**: 评估患者康复进度
- **运动预测**: 预测患者下一步动作
- **异常检测**: 检测异常运动模式

### 4. OpenClaw集成
- 接收自然语言指令
- 解析并转换为控制命令
- 生成康复评估报告
- 提供AI康复建议

### 5. 与M33通信
- 通过共享内存接收传感器数据
- 发送AI推理结果到M33
- 实时数据同步

## 系统架构

\`\`\`
┌─────────────────────────────────────────┐
│         OpenClaw Gateway (PC端)         │
│  - 自然语言理解                          │
│  - 训练计划生成                          │
│  - 康复评估                              │
└──────────┬──────────────────────────────┘
           │
           │ HTTP/WiFi
           │ - 自然语言指令
           │ - AI推理请求
           │
┌──────────▼──────────────────────────────┐
│        PSoC Edge E84 - M55核心          │
│  ┌────────────────────────────────┐     │
│  │  WiFi模块                       │     │
│  │  - 网络连接                     │     │
│  │  - HTTP服务器                   │     │
│  │  - OpenClaw通信                 │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  AI推理引擎                     │     │
│  │  - EMG信号分析                  │     │
│  │  - 运动意图预测                 │     │
│  │  - 康复评估                     │     │
│  └────────────────────────────────┘     │
│  ┌────────────────────────────────┐     │
│  │  数据处理                       │     │
│  │  - 传感器数据融合               │     │
│  │  - 特征提取                     │     │
│  │  - 数据预处理                   │     │
│  └────────────────────────────────┘     │
└──────────┬──────────────────────────────┘
           │
           │ 共享内存
           │ - 传感器数据
           │ - AI推理结果
           │
┌──────────▼──────────────────────────────┐
│        PSoC Edge E84 - M33核心          │
│  - CAN总线控制                           │
│  - 蓝牙通信                              │
│  - 实时控制                              │
└─────────────────────────────────────────┘
\`\`\`

## 工作流程

### 场景1: 自然语言控制
\`\`\`
1. 用户在App输入: "帮我做一组肩关节训练"
2. App发送到OpenClaw Gateway (HTTP)
3. OpenClaw理解意图，生成训练计划
4. OpenClaw通过WiFi调用M55的HTTP API
5. M55解析指令，通过共享内存通知M33执行
6. M33控制电机执行训练动作
7. 训练数据实时回传到M55
8. M55进行AI分析，生成康复评估
9. 评估结果返回OpenClaw，再返回App
\`\`\`

### 场景2: AI辅助训练
\`\`\`
1. 用户启动"AI助力模式"
2. M33采集EMG信号，发送到M55
3. M55 AI引擎实时分析EMG信号
4. 预测患者运动意图
5. 将预测结果发送回M33
6. M33根据预测调整电机阻尼
7. 实现智能辅助效果
\`\`\`

### 场景3: 康复评估
\`\`\`
1. 训练结束后，App请求康复评估
2. OpenClaw通过WiFi请求M55
3. M55从M33获取训练数据
4. AI引擎分析训练数据
5. 生成康复评估报告
6. 返回OpenClaw，再返回App
7. App保存到数据库并生成PDF
\`\`\`

## 开发环境

- **IDE**: RT-Thread Studio
- **RTOS**: RT-Thread 5.x
- **工具链**: ARM GCC
- **调试器**: J-Link / DAPLink
- **WiFi模块**: 板载WiFi芯片

## 编译与烧录

### 1. 导入工程
在RT-Thread Studio中导入工程：
\`File -> Import -> RT-Thread Project\`

### 2. 配置WiFi
编辑 \`applications/main.c\` 中的WiFi配置：
\`\`\`c
#define WIFI_SSID "your_wifi_ssid"
#define WIFI_PASSWORD "your_wifi_password"
\`\`\`

### 3. 编译
使用scons编译或在RT-Thread Studio中点击Build按钮

### 4. 烧录
使用J-Link烧录或在RT-Thread Studio中点击Download按钮

**注意**: 必须先烧录M33核心，再烧录M55核心

## 启动顺序

\`\`\`
+------------------+
|   Secure M33     |
|  (Secure Core)   |
+------------------+
          |
          v
+------------------+
|       M33        |
| (Non-Secure Core)|
+------------------+
          |
          v
+-------------------+
|       M55         |
| (Application Core)|
+-------------------+
\`\`\`

⚠️ 严格按照此顺序烧录，否则系统可能无法正常运行。

## API端点

### 获取传感器数据
\`\`\`
GET /api/sensors
Response: {
  "shoulder_angle": 45.0,
  "elbow_angle": 30.0,
  "lateral_position": 10.0,
  "heart_rate": 75,
  "spo2": 98,
  "emg_ch1": 0.12,
  "emg_ch2": 0.15,
  "timestamp": 1234567890
}
\`\`\`

### 执行控制命令
\`\`\`
POST /api/command
Body: {
  "command": "move_joint",
  "joint_id": 0,
  "target_angle": 90.0
}
Response: {
  "status": "success",
  "message": "Command executed"
}
\`\`\`

### AI推理请求
\`\`\`
POST /api/inference
Body: {
  "type": "emg_prediction",
  "data": [0.12, 0.15, 0.18, ...]
}
Response: {
  "prediction": "flexion",
  "confidence": 0.95
}
\`\`\`

### 获取系统状态
\`\`\`
GET /api/status
Response: {
  "mode": "active",
  "safety_state": "normal",
  "wifi_connected": true,
  "m33_connected": true
}
\`\`\`

## 目录结构

\`\`\`
wifi/
├── applications/
│   ├── main.c                      # 主程序
│   ├── http_server.c               # HTTP服务器
│   └── openclaw_integration.c      # OpenClaw集成
├── board/                          # 板级支持包
├── libraries/                      # 库文件
│   ├── HAL_Drivers/               # 硬件抽象层
│   └── components/                # 组件库
└── rtconfig.h                     # RT-Thread配置
\`\`\`

## 配置说明

### WiFi配置
- SSID和密码在 \`applications/main.c\` 中配置
- 支持WPA/WPA2加密

### HTTP服务器配置
- 默认端口: 80
- 最大连接数: 5
- 超时时间: 30秒

### AI模型配置
- 模型文件位置: \`models/\`
- 支持的模型格式: TensorFlow Lite

## 故障排查

### WiFi无法连接
1. 检查SSID和密码是否正确
2. 确认WiFi信号强度
3. 查看日志中的连接错误信息

### HTTP服务器无响应
1. 检查WiFi是否已连接
2. 确认防火墙设置
3. 使用ping测试网络连通性

### M33通信异常
1. 确认M33核心已正常运行
2. 检查共享内存配置
3. 查看通信日志

## 相关链接

- [M33核心固件](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/M33)
- [RT-Thread文档](https://www.rt-thread.org/document/site/)
- [Infineon PSoC Edge E84](https://www.infineon.com/cms/en/product/microcontroller/32-bit-psoc-arm-cortex-microcontroller/psoc-edge-e8/)

## 许可证

本项目仅供学习和研究使用。

## 作者

- GitHub: [@ChillAmnesiac](https://github.com/ChillAmnesiac)
- Email: 3245056131@qq.com
