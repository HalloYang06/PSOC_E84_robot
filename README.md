# NanoPi ROS 2 Workspace

NanoPi上的ROS 2 Jazzy工作空间，用于医疗康复机械臂控制。实现摄像头流传输、与手机APP的HTTP API桥接和OpenClaw协议支持。

## 项目结构

```
nanopi_ros/
├── src/                        # ROS 2包源码
│   ├── camera_client/          # 摄像头WebSocket客户端
│   │   ├── camera_websocket_client.cpp
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   ├── launch/
│   │   │   └── camera.launch.py
│   │   └── run_camera.sh
│   └── http_bridge/            # HTTP Bridge服务器
│       ├── http_bridge_server.py
│       ├── test_http_bridge.py
│       ├── CMakeLists.txt
│       ├── package.xml
│       ├── setup.py
│       ├── launch/
│       │   └── http_bridge.launch.py
│       ├── start_http_bridge.sh
│       └── run_tests.sh
├── launch/                     # 工作空间级launch文件
│   └── system.launch.py        # 启动所有节点
├── build/                      # colcon构建输出
├── install/                    # 安装目录
├── log/                        # 日志目录
├── scripts/                    # 工具脚本
│   ├── install_deps.sh         # 依赖安装
│   ├── test_http_bridge.sh     # HTTP测试
│   ├── monitor_requests.sh     # 请求监控
│   └── diagnose_app_connection.sh  # APP连接诊断
├── venv/                       # Python虚拟环境
├── build_ros2.sh               # ROS 2构建脚本
├── start_http_bridge.sh        # HTTP Bridge启动脚本
├── CLAUDE.md                   # AI助手指南
├── LEARNING_GUIDE.md           # 完整学习指南
└── README.md                   # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
# 安装系统依赖
cd scripts
./install_deps.sh
```

### 2. 构建ROS 2工作空间

```bash
# 构建所有包
./build_ros2.sh

# 仅构建特定包
./build_ros2.sh --packages camera_client

# 调试模式构建
./build_ros2.sh --debug

# 清理并重新构建
./build_ros2.sh --clean
```

### 3. 加载环境

```bash
source install/setup.bash
```

### 4. 运行节点

#### 方式1：使用ROS 2 launch（推荐）

```bash
# 启动摄像头客户端
ros2 launch camera_client camera.launch.py

# 启动HTTP Bridge
ros2 launch http_bridge http_bridge.launch.py

# 启动所有节点
ros2 launch system.launch.py

# 带参数启动
ros2 launch camera_client camera.launch.py server_ip:=10.100.191.235 fps:=15
```

#### 方式2：使用启动脚本（推荐）

```bash
# HTTP Bridge
./start_http_bridge.sh

# 摄像头客户端
source install/setup.bash
install/camera_client/lib/camera_client/camera_websocket_client
```

## 组件说明

### Camera Client

摄像头WebSocket客户端，将摄像头画面实时传输到服务器。

**特性:**
- ROS 2节点集成
- 支持USB/CSI摄像头
- JPEG压缩
- 可配置帧率
- WebSocket传输
- 自动重连

**Launch参数:**
- `server_ip` - 服务器IP（默认：10.100.191.235）
- `server_port` - 服务器端口（默认：8080）
- `camera_id` - 摄像头ID（默认：-1自动检测）
- `fps` - 帧率（默认：10）

### HTTP Bridge

HTTP API服务器，实现Android APP与ROS 2系统的通信桥接。

**特性:**
- RESTful API
- 与ROS 2完全集成
- 支持OpenClaw协议
- 实时传感器数据
- 控制命令下发

**API端点:**
- `GET /health` - 健康检查
- `GET /status` - 获取系统状态
- `POST /message` - OpenClaw自然语言消息（主要功能）
- `POST /mode` - 切换控制模式
- `POST /control` - 发送控制指令
- `POST /memory/execute` - 执行记忆动作
- `POST /api/command` - OpenClaw工具调用

### Android APP配置

```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://10.100.191.82:8081")  // NanoPi IP
```

或在APP设置中输入：
- 服务器地址: `10.100.191.82`
- 端口: `8081`

## ROS 2开发

### 查看节点

```bash
ros2 node list
ros2 node info /camera_websocket_client
```

### 查看话题

```bash
ros2 topic list
ros2 topic echo /camera/image_raw
```

### 查看服务

```bash
ros2 service list
```

### 查看参数

```bash
ros2 param list
ros2 param get /camera_websocket_client server_ip
```

## 测试

### 摄像头客户端测试

```bash
# 列出可用摄像头
v4l2-ctl --list-devices

# 测试摄像头
ffplay /dev/video45
```

### HTTP Bridge测试

```bash
# 快速测试所有端点
./scripts/test_http_bridge.sh

# 监控实时请求
./scripts/monitor_requests.sh

# 手动测试
curl http://localhost:8081/health
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message":"测试消息"}'
```

## 故障排除

### 构建失败

**问题:** 找不到ROS 2
```bash
source /opt/ros/jazzy/setup.bash
```

**问题:** 找不到colcon
```bash
sudo apt install python3-colcon-common-extensions
```

**问题:** 找不到ament_cmake
```bash
sudo apt install ros-jazzy-ament-cmake ros-jazzy-ament-cmake-python
```

### 运行时错误

**问题:** 摄像头无法打开
```bash
# 检查摄像头权限
sudo usermod -a -G video $USER
# 重新登录生效
```

**问题:** HTTP服务器端口被占用
```bash
# 查看端口占用
sudo lsof -i :8081
```

## 相关文档

- [CLAUDE.md](CLAUDE.md) - 开发指南和项目架构
- [GitHub仓库](https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator/tree/NanoPi_ROSNode)

## 技术栈

- ROS 2 Jazzy
- Python 3.12 + Flask + Flask-CORS
- C++ 17 + OpenCV 4.6 + Boost
- colcon构建系统
- OpenClaw协议

## 许可证

MIT
