# OpenClaw <-> Android APP 集成快速指南

## 概述

已成功为你的NanoPi创建HTTP Bridge Server，实现了与Android APP的完整通信协议。

## 文件说明

### 核心文件
- `http_bridge_server.py` - Python实现的HTTP服务器（推荐使用）
- `http_bridge_server.cpp` - C++实现的HTTP服务器（高性能版本）
- `start_http_bridge.sh` - 快速启动脚本
- `start_system.sh` - 完整系统启动脚本
- `test_http_bridge.py` - API测试工具

### 文档
- `HTTP_BRIDGE_README.md` - 详细的API文档和使用说明
- `CLAUDE.md` - 项目总体文档（已更新）

## 快速开始

### 1. 启动HTTP服务器

```bash
cd /home/pi/ros_node
./start_http_bridge.sh
```

服务器将在 `http://0.0.0.0:8081` 上监听

### 2. 查看NanoPi的IP地址

```bash
hostname -I
```

假设输出是 `192.168.1.100`

### 3. 在Android APP中配置

在你的APP代码中，设置NanoPi的IP地址：

```kotlin
// 在MainActivity或初始化代码中
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://192.168.1.100:8081")  // 使用实际IP

// 测试连接
lifecycleScope.launch {
    val result = httpManager.checkHealth()
    if (result.isSuccess) {
        Log.d("APP", "连接成功！")
    }
}
```

### 4. 测试连接

在NanoPi上运行测试：

```bash
python3 test_http_bridge.py
```

或使用curl：

```bash
curl http://localhost:8081/health
curl http://localhost:8081/status
```

## 已实现的API端点

### 基础端点
✅ `GET /health` - 健康检查
✅ `GET /status` - 获取系统状态和传感器数据
✅ `POST /mode` - 切换控制模式
✅ `POST /control` - 发送控制指令
✅ `POST /memory/execute` - 执行记忆动作
✅ `POST /memory/stop` - 停止记忆动作

### 扩展端点
✅ `POST /api/command` - OpenClaw工具调用
✅ `GET /api/sensor/data` - 获取传感器数据
✅ `POST /api/training/start` - 开始训练会话
✅ `GET /api/stats` - 获取统计数据

## 数据流

```
Android APP (Kotlin)
    ↓ HTTP POST /control
    ↓ {"shoulder_angle": 45.0, "elbow_angle": 30.0}
    ↓
HTTP Bridge Server (Python)
    ↓ ROS 2 Topic: /can_tx
    ↓ {"type": "control", "shoulder_angle": 45.0, ...}
    ↓
CAN Interface Node
    ↓ SocketCAN
    ↓
OpenClaw Hardware
```

```
OpenClaw Hardware
    ↓ SocketCAN
    ↓
CAN Interface Node
    ↓ ROS 2 Topic: /can_rx
    ↓ {"motor1_angle": 45.5, "motor2_angle": 30.2, ...}
    ↓
HTTP Bridge Server (Python)
    ↑ HTTP GET /status
    ↑
Android APP (Kotlin)
```

## APP使用示例

### 1. 健康检查

```kotlin
val result = httpManager.checkHealth()
if (result.isSuccess && result.getOrNull() == true) {
    println("NanoPi连接正常")
}
```

### 2. 获取传感器数据

```kotlin
val statusResult = httpManager.getStatus()
if (statusResult.isSuccess) {
    val status = statusResult.getOrNull()
    val shoulderAngle = status?.get("shoulder_angle") as? Double
    val elbowAngle = status?.get("elbow_angle") as? Double
    println("肩关节: $shoulderAngle°, 肘关节: $elbowAngle°")
}
```

### 3. 切换模式

```kotlin
// 切换到被动模式
httpManager.setMode("passive")

// 切换到主动模式
httpManager.setMode("active")

// 切换到记忆模式
httpManager.setMode("memory")
```

### 4. 发送控制指令

```kotlin
httpManager.sendControl(
    shoulderAngle = 45.0f,
    elbowAngle = 30.0f,
    lateralPos = 15.0f
)
```

### 5. 执行记忆动作

```kotlin
httpManager.executeMemory("action_001")
```

### 6. 调用OpenClaw工具

```kotlin
httpManager.callTool("move_joint", mapOf(
    "joint_id" to 1,
    "angle" to 45.0,
    "speed" to 30.0
))
```

## 网络配置

### 确保设备在同一网络

1. **选项A: 连接到同一WiFi**
   - NanoPi和Android设备连接到同一个WiFi路由器
   - 在APP中使用NanoPi的局域网IP（如192.168.1.100）

2. **选项B: NanoPi作为热点**
   ```bash
   # 在NanoPi上创建WiFi热点
   sudo nmcli dev wifi hotspot ssid OpenClaw password 12345678
   ```
   - Android设备连接到"OpenClaw"热点
   - 在APP中使用NanoPi的热点IP（通常是192.168.4.1）

### 防火墙配置

```bash
# 允许8081端口
sudo ufw allow 8081/tcp

# 或关闭防火墙（仅用于测试）
sudo ufw disable
```

## 故障排除

### 问题1: APP无法连接到NanoPi

**检查清单:**
1. NanoPi和Android设备在同一网络？
2. HTTP服务器正在运行？ (`ps aux | grep http_bridge`)
3. IP地址正确？ (`hostname -I`)
4. 防火墙允许8081端口？
5. 使用curl从NanoPi本地测试？

### 问题2: 连接成功但没有数据

**可能原因:**
- CAN接口未启动
- ROS 2节点未运行
- CAN硬件未连接

**检查:**
```bash
# 检查CAN接口
ip link show can0

# 检查ROS 2话题
ros2 topic list
ros2 topic echo /can_rx
```

### 问题3: 数据延迟

**优化建议:**
- 降低APP轮询频率（默认100ms）
- 使用WebSocket替代HTTP轮询（未来实现）
- 检查网络质量

## 下一步开发

### 短期目标
- [ ] 实现完整的CAN数据解析
- [ ] 添加传感器数据缓存
- [ ] 实现记忆动作存储和回放
- [ ] 添加错误处理和日志

### 中期目标
- [ ] WebSocket支持（实时双向通信）
- [ ] 数据持久化（SQLite）
- [ ] 训练会话管理
- [ ] 康复分析算法

### 长期目标
- [ ] OpenClaw AI集成
- [ ] 多设备支持
- [ ] 云端数据同步
- [ ] 远程监控和控制

## 技术支持

如有问题，请查看：
- `HTTP_BRIDGE_README.md` - 详细API文档
- `CLAUDE.md` - 项目总体文档
- 测试工具: `python3 test_http_bridge.py`

## 总结

✅ HTTP Bridge Server已完成
✅ 所有APP期望的API端点已实现
✅ ROS 2集成已完成
✅ 测试工具已提供
✅ 文档已完善

现在你可以：
1. 启动HTTP服务器: `./start_http_bridge.sh`
2. 在APP中配置NanoPi的IP
3. 开始测试APP和NanoPi的通信！
