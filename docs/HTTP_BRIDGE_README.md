# HTTP Bridge Server - OpenClaw <-> APP 通信桥接

## 概述

这个HTTP服务器实现了Android APP期望的所有HTTP API端点，用于桥接ROS 2系统和Android APP。

## 架构

```
Android APP (Kotlin)
    ↕ HTTP/JSON
NanoPi HTTP Bridge Server (C++)
    ↕ ROS 2 Topics
CAN Interface Node
    ↕ SocketCAN
OpenClaw Hardware
```

## 编译和运行

### 编译
```bash
cd /home/pi/ros_node
./build_http_bridge.sh
```

### 运行
```bash
# 确保ROS 2环境已加载
source /opt/ros/jazzy/setup.bash

# 启动HTTP服务器
./build_http_bridge/http_bridge_server
```

服务器将监听在 `http://0.0.0.0:8081`

## API端点

### 1. GET /health
健康检查端点

**响应**:
```json
{
  "status": "ok"
}
```

### 2. GET /status
获取系统状态和传感器数据

**响应**:
```json
{
  "timestamp": 1234567890,
  "mode": "active",
  "main_mode": "ACTIVE",
  "is_emergency_stop": false,
  "is_safety_ok": true,
  "error_code": 0,
  "error_message": "",
  "motor1_angle": 45.5,
  "motor2_angle": 30.2,
  "imu_angle_x": 15.0,
  "emg_ch1": 0.5,
  "heart_rate": 75,
  "motor1_temp": 28.5,
  "motor2_temp": 27.3,
  "shoulder_angle": 45.5,
  "elbow_angle": 30.2,
  "lateral_position": 15.0
}
```

### 3. POST /mode
切换控制模式

**请求**:
```json
{
  "mode": "passive"
}
```

**响应**:
```json
{
  "success": true,
  "mode": "passive"
}
```

**支持的模式**:
- `active` - 主动模式
- `passive` - 被动模式
- `memory` - 记忆模式

### 4. POST /control
发送控制指令（被动模式）

**请求**:
```json
{
  "type": "control",
  "shoulder_angle": 45.0,
  "elbow_angle": 30.0,
  "lateral_pos": 15.0
}
```

**响应**:
```json
{
  "success": true
}
```

### 5. POST /memory/execute
执行记忆动作

**请求**:
```json
{
  "action_id": "action_001"
}
```

**响应**:
```json
{
  "success": true
}
```

### 6. POST /memory/stop
停止记忆动作

**请求**:
```json
{}
```

**响应**:
```json
{
  "success": true
}
```

### 7. POST /api/command
OpenClaw工具调用（扩展功能）

**请求**:
```json
{
  "tool": "move_joint",
  "parameters": {
    "joint_id": 1,
    "angle": 45.0,
    "speed": 30.0
  }
}
```

**响应**:
```json
{
  "success": true,
  "result": "Command sent to OpenClaw"
}
```

## ROS 2 话题

### 订阅的话题
- `/can_rx` (std_msgs/String) - 接收来自CAN节点的传感器数据

### 发布的话题
- `/can_tx` (std_msgs/String) - 发送控制命令到CAN节点

## APP配置

在Android APP中设置NanoPi的IP地址：

```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://192.168.1.100:8081")  // 替换为NanoPi的实际IP
```

## 测试

### 使用curl测试

```bash
# 健康检查
curl http://localhost:8081/health

# 获取状态
curl http://localhost:8081/status

# 切换模式
curl -X POST http://localhost:8081/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"passive"}'

# 发送控制指令
curl -X POST http://localhost:8081/control \
  -H "Content-Type: application/json" \
  -d '{"shoulder_angle":45.0,"elbow_angle":30.0}'

# 执行记忆动作
curl -X POST http://localhost:8081/memory/execute \
  -H "Content-Type: application/json" \
  -d '{"action_id":"action_001"}'
```

### 使用Python测试

```python
import requests

base_url = "http://192.168.1.100:8081"

# 健康检查
response = requests.get(f"{base_url}/health")
print(response.json())

# 获取状态
response = requests.get(f"{base_url}/status")
print(response.json())

# 切换模式
response = requests.post(f"{base_url}/mode", json={"mode": "passive"})
print(response.json())

# 发送控制指令
response = requests.post(f"{base_url}/control", json={
    "shoulder_angle": 45.0,
    "elbow_angle": 30.0,
    "lateral_pos": 15.0
})
print(response.json())
```

## 网络配置

### 查找NanoPi的IP地址
```bash
ip addr show
# 或
hostname -I
```

### 确保防火墙允许8081端口
```bash
sudo ufw allow 8081/tcp
# 或
sudo iptables -A INPUT -p tcp --dport 8081 -j ACCEPT
```

### 在同一WiFi网络中
确保Android设备和NanoPi连接到同一个WiFi网络，或者配置NanoPi作为热点。

## 故障排除

### 端口已被占用
```bash
# 查看8081端口占用情况
sudo lsof -i :8081

# 或更改端口（修改http_bridge_server.cpp中的port变量）
```

### APP无法连接
1. 检查NanoPi的IP地址是否正确
2. 检查防火墙设置
3. 确保HTTP服务器正在运行
4. 使用curl从NanoPi本地测试

### ROS 2通信问题
```bash
# 检查ROS 2话题
ros2 topic list
ros2 topic echo /can_rx
ros2 topic echo /can_tx
```

## 性能优化

- HTTP服务器使用Boost.Beast异步I/O，支持高并发
- ROS 2节点和HTTP服务器运行在不同线程，互不阻塞
- 传感器数据轮询频率：APP默认100ms（10Hz）
- 建议CAN总线频率：100Hz

## 下一步

1. 实现完整的CAN数据解析（根据你的CAN协议）
2. 添加数据缓存和历史记录
3. 实现WebSocket支持（实时双向通信）
4. 添加认证和安全机制
5. 集成OpenClaw AI功能
