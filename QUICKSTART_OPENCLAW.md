# OpenClaw HTTP Bridge 快速使用指南

## 启动服务

```bash
cd /home/pi/nanopi_ros
./start_openclaw_bridge.sh
```

服务会在前台运行，显示实时日志。

**停止服务：按 `Ctrl+C`**

## 服务信息

- **服务器地址**: `http://10.100.191.82:8081`
- **运行模式**: 前台运行，Ctrl+C 停止

## Android APP 配置

```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://10.100.191.82:8081")

// 发送消息给 OpenClaw AI
httpManager.sendMessage("你好，请帮我控制机械臂")
```

## 测试服务

### 在另一个终端测试

```bash
# 健康检查
curl http://localhost:8081/health

# 发送消息给 AI
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 或使用测试脚本
./test_openclaw.sh
```

## 后台运行（可选）

如果需要后台运行：

```bash
# 后台启动
nohup ./start_openclaw_bridge.sh > openclaw.log 2>&1 &

# 查看日志
tail -f openclaw.log

# 停止服务
pkill -f "ros2 launch http_bridge"
```

## 开机自启动（可选）

添加到 crontab：

```bash
crontab -e
```

添加这一行：
```
@reboot sleep 10 && cd /home/pi/nanopi_ros && ./start_openclaw_bridge.sh > /tmp/openclaw_bridge.log 2>&1
```

## 故障排除

### 端口被占用

```bash
# 查看占用端口的进程
sudo lsof -i :8081

# 停止所有 HTTP Bridge 进程
pkill -f "http_bridge"
```

### OpenClaw Gateway 未运行

```bash
systemctl --user status openclaw-gateway.service
systemctl --user start openclaw-gateway.service
```

## 更多文档

- [docs/OPENCLAW_BRIDGE_README.md](docs/OPENCLAW_BRIDGE_README.md) - 完整文档
- [docs/HTTP_BRIDGE_README.md](docs/HTTP_BRIDGE_README.md) - HTTP API 文档
