# HTTP Bridge 测试完成指南

## ✅ 问题已解决

**问题**: 缺少Python依赖（numpy, flask等）
**解决**: 项目使用venv管理Python依赖，所有包已安装

## 快速测试（2步）

### 第1步：启动HTTP Bridge

```bash
./start_http_bridge.sh
```

你会看到：
```
==========================================
  启动 HTTP Bridge Server
==========================================

NanoPi IP地址: 10.100.191.82
服务器将监听在: http://0.0.0.0:8081
从其他设备访问: http://10.100.191.82:8081

Android APP配置:
  服务器地址: 10.100.191.82
  端口: 8081

按 Ctrl+C 停止服务器
==========================================

[INFO] [http_bridge_node]: HTTP Bridge Node initialized
[INFO] [http_bridge_node]: HTTP Bridge Server started on http://0.0.0.0:8081
```

### 第2步：测试连接（新终端）

```bash
./scripts/test_http_bridge.sh
```

你会看到所有测试通过：
```
✅ 服务器正在运行
✅ 测试 1/6: GET /health - 通过
✅ 测试 2/6: GET /status - 通过
✅ 测试 3/6: POST /mode - 通过
✅ 测试 4/6: POST /control - 通过
✅ 测试 5/6: POST /memory/execute - 通过
✅ 测试 6/6: POST /api/command - 通过
```

## Android APP 配置

根据启动脚本显示的IP地址，在APP中配置：

```
服务器地址: 10.100.191.82  (你的实际IP)
端口: 8081
```

或在APP代码中：
```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://10.100.191.82:8081")
```

## 手动测试命令

### 基础测试
```bash
# 健康检查
curl http://localhost:8081/health
# 响应: {"status":"ok"}

# 获取状态
curl http://localhost:8081/status
# 响应: JSON格式的系统状态和传感器数据
```

### 模式切换
```bash
# 切换到被动模式
curl -X POST http://localhost:8081/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"passive"}'

# 切换到主动模式
curl -X POST http://localhost:8081/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"active"}'

# 切换到记忆模式
curl -X POST http://localhost:8081/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"memory"}'
```

### 控制指令
```bash
# 发送控制指令（被动模式）
curl -X POST http://localhost:8081/control \
  -H "Content-Type: application/json" \
  -d '{"shoulder_angle":45.0,"elbow_angle":30.0,"lateral_pos":15.0}'
```

### 记忆动作
```bash
# 执行记忆动作
curl -X POST http://localhost:8081/memory/execute \
  -H "Content-Type: application/json" \
  -d '{"action_id":"test_action_001"}'

# 停止记忆动作
curl -X POST http://localhost:8081/memory/stop \
  -H "Content-Type: application/json" \
  -d '{}'
```

### OpenClaw工具调用
```bash
curl -X POST http://localhost:8081/api/command \
  -H "Content-Type: application/json" \
  -d '{"tool":"move_joint","parameters":{"joint_id":1,"angle":45.0,"speed":30.0}}'
```

## 监控ROS 2通信

在另一个终端：

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

## 从其他设备测试

### 从电脑测试
```bash
# 替换为NanoPi的实际IP
export NANOPI_IP=10.100.191.82

# 测试连接
curl http://$NANOPI_IP:8081/health

# 获取状态
curl http://$NANOPI_IP:8081/status
```

### 从手机浏览器测试
在手机浏览器中访问：
```
http://10.100.191.82:8081/health
```

应该看到：
```json
{"status":"ok"}
```

## APP测试步骤

1. **配置连接**
   - 打开APP设置
   - 输入服务器地址: `10.100.191.82`
   - 输入端口: `8081`
   - 保存设置

2. **测试连接**
   - APP应显示"已连接"或绿色指示灯
   - 如果连接失败，检查：
     - NanoPi和手机在同一WiFi网络
     - HTTP Bridge服务器正在运行
     - 防火墙没有阻止8081端口

3. **测试功能**
   - 查看传感器数据（应该显示默认值）
   - 切换模式（主动/被动/记忆）
   - 在被动模式下发送控制指令
   - 执行记忆动作

## 故障排除

### 服务器无法启动

**问题**: `ModuleNotFoundError: No module named 'flask'`
**解决**: 确保使用启动脚本 `./start_http_bridge.sh`，它会自动激活venv

**问题**: `Address already in use`
**解决**:
```bash
# 查找占用端口的进程
sudo lsof -i :8081

# 停止旧进程
pkill -f http_bridge_server.py
```

### APP无法连接

**问题**: 连接超时
**检查**:
1. NanoPi和手机在同一网络
   ```bash
   # 在NanoPi上
   hostname -I
   ```
2. 服务器正在运行
   ```bash
   curl http://localhost:8081/health
   ```
3. 防火墙设置
   ```bash
   sudo ufw allow 8081/tcp
   ```

### 测试脚本失败

**问题**: `curl: command not found`
**解决**:
```bash
sudo apt install curl
```

## API端点完整列表

| 端点 | 方法 | 功能 | 请求体 |
|------|------|------|--------|
| `/health` | GET | 健康检查 | - |
| `/status` | GET | 获取系统状态 | - |
| `/mode` | POST | 切换模式 | `{"mode":"active\|passive\|memory"}` |
| `/control` | POST | 发送控制指令 | `{"shoulder_angle":45.0,"elbow_angle":30.0}` |
| `/memory/execute` | POST | 执行记忆动作 | `{"action_id":"action_001"}` |
| `/memory/stop` | POST | 停止记忆动作 | `{}` |
| `/api/command` | POST | OpenClaw工具调用 | `{"tool":"move_joint","parameters":{...}}` |

## 下一步

测试通过后：

1. ✅ HTTP Bridge正常工作
2. ✅ APP能连接到NanoPi
3. 🔄 集成真实的CAN硬件
4. 🔄 实现实际的传感器数据读取
5. 🔄 添加数据记录功能
6. 🔄 实现更复杂的控制逻辑

## 相关文档

- [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) - 详细测试指南
- [docs/HTTP_BRIDGE_README.md](docs/HTTP_BRIDGE_README.md) - HTTP API文档
- [CLAUDE.md](CLAUDE.md) - 开发指南
