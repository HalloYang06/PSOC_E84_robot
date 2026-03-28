# OpenClaw HTTP Bridge 使用说明

## 概述

HTTP Bridge 服务器已集成 OpenClaw AI 智能体，可以处理自然语言指令并返回智能响应。

## 服务器信息

- **服务器地址**: `http://10.100.191.82:8081`
- **OpenClaw Gateway**: 运行在端口 18789
- **AI 模型**: Claude Opus 4.6

## 启动服务器

```bash
cd /home/pi/nanopi_ros
./start_openclaw_bridge.sh
```

或者手动启动：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch http_bridge http_bridge.launch.py
```

## API 端点

### 1. 发送消息给 OpenClaw AI（主要功能）

```bash
POST /message
Content-Type: application/json

{
  "message": "你好，请介绍一下你自己"
}
```

响应：
```json
{
  "success": true,
  "message": "我是一个刚启动的 AI 助手...",
  "error": null
}
```

### 2. 健康检查

```bash
GET /health
```

### 3. 获取系统状态

```bash
GET /status
```

### 4. 其他端点

- `POST /mode` - 切换控制模式
- `POST /control` - 发送控制指令
- `POST /api/command` - OpenClaw 工具调用

## Android APP 配置

在你的 Android APP 中设置：

```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://10.100.191.82:8081")

// 发送消息
httpManager.sendMessage("你好，请帮我控制机械臂")
```

## 测试

使用提供的测试脚本：

```bash
./test_openclaw.sh
```

或者手动测试：

```bash
# 测试 AI 响应
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，请介绍一下你自己"}'

# 测试机械臂控制
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message": "请帮我抬起机械臂"}'
```

## 工作原理

1. Android APP 发送 HTTP POST 请求到 `/message` 端点
2. HTTP Bridge 接收消息并调用 `openclaw agent` 命令
3. OpenClaw Gateway 处理消息并调用 Claude Opus 4.6 AI 模型
4. AI 生成智能响应
5. HTTP Bridge 将响应返回给 APP

## 响应时间

- 典型响应时间：10-30 秒（取决于消息复杂度）
- 超时设置：35 秒

## 日志查看

### HTTP Bridge 日志
```bash
ros2 topic echo /rosout
```

### OpenClaw 日志
```bash
tail -f /tmp/openclaw/openclaw-2026-03-28.log
```

## 故障排除

### OpenClaw Gateway 未运行

```bash
systemctl --user status openclaw-gateway.service
systemctl --user start openclaw-gateway.service
```

### HTTP Bridge 端口被占用

```bash
sudo lsof -i :8081
# 停止占用端口的进程
```

### AI 响应超时

- 检查网络连接
- 查看 OpenClaw 日志
- 确认 API 密钥有效

## 性能优化

当前配置：
- 使用 `openclaw agent` 命令行接口（简单可靠）
- 每次请求创建新的子进程
- 适合低频率请求（< 1 req/s）

如需高性能：
- 考虑使用 WebSocket 直接连接到 Gateway
- 实现连接池和会话管理
- 使用异步处理

## 下一步

1. 配置 OpenClaw 的工具和技能来控制机械臂
2. 添加更多 ROS 2 话题集成
3. 实现传感器数据反馈
4. 添加语音识别支持
