# OpenClaw HTTP Bridge 测试指南

## 测试步骤

### 第一步：启动HTTP Bridge服务器

在NanoPi上打开终端：

```bash
# 1. 加载ROS 2环境
source install/setup.bash

# 2. 启动HTTP Bridge
ros2 launch http_bridge http_bridge.launch.py
```

你应该看到类似输出：
```
[INFO] [http_bridge_node]: HTTP Bridge Node initialized
[INFO] [http_bridge_node]: HTTP Bridge Server started on http://0.0.0.0:8081
```

### 第二步：获取NanoPi的IP地址

在NanoPi上运行：
```bash
hostname -I
# 或
ip addr show | grep "inet "
```

记下IP地址，例如：`192.168.1.100`

### 第三步：本地测试（在NanoPi上）

在NanoPi上打开另一个终端：

```bash
# 运行测试脚本
source install/setup.bash
ros2 run http_bridge test_http_bridge.py
```

或者使用curl手动测试：

```bash
# 1. 健康检查
curl http://localhost:8081/health

# 2. 获取状态
curl http://localhost:8081/status

# 3. 切换模式
curl -X POST http://localhost:8081/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"passive"}'

# 4. 发送控制指令
curl -X POST http://localhost:8081/control \
  -H "Content-Type: application/json" \
  -d '{"shoulder_angle":45.0,"elbow_angle":30.0,"lateral_pos":15.0}'

# 5. 执行记忆动作
curl -X POST http://localhost:8081/memory/execute \
  -H "Content-Type: application/json" \
  -d '{"action_id":"test_action_001"}'

# 6. OpenClaw工具调用
curl -X POST http://localhost:8081/api/command \
  -H "Content-Type: application/json" \
  -d '{"tool":"move_joint","parameters":{"joint_id":1,"angle":45.0}}'
```

### 第四步：从电脑测试（可选）

如果你的电脑和NanoPi在同一网络：

```bash
# 替换为NanoPi的实际IP
export NANOPI_IP=192.168.1.100

# 测试连接
curl http://$NANOPI_IP:8081/health

# 获取状态
curl http://$NANOPI_IP:8081/status
```

### 第五步：Android APP配置

在Android APP中配置NanoPi的IP地址：

```kotlin
// 在APP代码中设置
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://192.168.1.100:8081")  // 替换为你的NanoPi IP
```

或者在APP的设置界面输入：
```
服务器地址: 192.168.1.100
端口: 8081
```

### 第六步：APP测试

1. **连接测试**
   - 打开APP
   - 检查连接状态（应该显示"已连接"或绿色指示灯）

2. **获取状态测试**
   - APP应该能显示传感器数据
   - 检查是否能看到：
     - 肩部角度 (shoulder_angle)
     - 肘部角度 (elbow_angle)
     - 侧向位置 (lateral_position)
     - 温度、心率等

3. **模式切换测试**
   - 在APP中切换模式：主动/被动/记忆
   - 检查NanoPi终端是否有日志输出

4. **控制指令测试**
   - 在被动模式下，通过APP发送控制指令
   - 检查NanoPi终端是否收到命令

## API端点说明

### GET /health
健康检查，返回服务器状态

**响应示例：**
```json
{
  "status": "ok"
}
```

### GET /status
获取系统状态和传感器数据

**响应示例：**
```json
{
  "timestamp": 1234567890,
  "mode": "active",
  "main_mode": "ACTIVE",
  "is_emergency_stop": false,
  "is_safety_ok": true,
  "error_code": 0,
  "error_message": "",
  "motor1_angle": 0.0,
  "motor2_angle": 0.0,
  "imu_angle_x": 0.0,
  "emg_ch1": 0.0,
  "heart_rate": 0,
  "motor1_temp": 25.0,
  "motor2_temp": 25.0,
  "shoulder_angle": 0.0,
  "elbow_angle": 0.0,
  "lateral_position": 0.0
}
```

### POST /mode
切换控制模式

**请求：**
```json
{
  "mode": "passive"  // active, passive, memory
}
```

**响应：**
```json
{
  "success": true,
  "mode": "passive"
}
```

### POST /control
发送控制指令（被动模式）

**请求：**
```json
{
  "shoulder_angle": 45.0,
  "elbow_angle": 30.0,
  "lateral_pos": 15.0
}
```

**响应：**
```json
{
  "success": true
}
```

### POST /memory/execute
执行记忆动作

**请求：**
```json
{
  "action_id": "action_001"
}
```

**响应：**
```json
{
  "success": true
}
```

### POST /memory/stop
停止记忆动作

**请求：**
```json
{}
```

**响应：**
```json
{
  "success": true
}
```

### POST /api/command
OpenClaw工具调用

**请求：**
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

**响应：**
```json
{
  "success": true,
  "result": "Command sent to OpenClaw"
}
```

## 监控ROS 2话题

在另一个终端监控ROS 2通信：

```bash
# 加载环境
source install/setup.bash

# 查看所有话题
ros2 topic list

# 监控发送到CAN的命令
ros2 topic echo /can_tx

# 监控从CAN接收的数据
ros2 topic echo /can_rx
```

## 故障排除

### 无法连接到服务器

1. **检查服务器是否运行**
   ```bash
   ps aux | grep http_bridge
   ```

2. **检查端口是否监听**
   ```bash
   sudo lsof -i :8081
   # 或
   sudo netstat -tlnp | grep 8081
   ```

3. **检查防火墙**
   ```bash
   sudo ufw status
   sudo ufw allow 8081/tcp
   ```

### APP无法连接

1. **确认在同一网络**
   - NanoPi和手机必须在同一WiFi网络

2. **检查IP地址**
   ```bash
   hostname -I
   ```

3. **测试网络连通性**
   - 在手机浏览器访问：`http://192.168.1.100:8081/health`
   - 应该看到 `{"status":"ok"}`

### 服务器启动失败

1. **端口被占用**
   ```bash
   sudo lsof -i :8081
   sudo kill <PID>
   ```

2. **Python依赖缺失**
   ```bash
   source venv/bin/activate
   pip list | grep -E "flask|rclpy"
   ```

## 测试检查清单

- [ ] HTTP Bridge服务器成功启动
- [ ] 本地curl测试所有端点正常
- [ ] 获取到NanoPi的IP地址
- [ ] 从电脑能ping通NanoPi
- [ ] 从电脑能访问 /health 端点
- [ ] APP配置了正确的IP和端口
- [ ] APP能连接到服务器
- [ ] APP能获取状态数据
- [ ] APP能切换模式
- [ ] APP能发送控制指令
- [ ] ROS 2话题能看到命令发布

## 下一步

测试通过后，你可以：

1. 集成真实的CAN硬件
2. 实现实际的传感器数据读取
3. 添加数据记录和分析功能
4. 实现更复杂的控制逻辑
