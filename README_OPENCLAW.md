# OpenClaw HTTP Bridge - 简单使用

## 首次使用（安装依赖）

```bash
cd /home/pi/nanopi_ros
./install_http_bridge_deps.sh
```

## 启动服务

```bash
./start_openclaw_bridge.sh
```

服务会显示实时日志，按 **Ctrl+C** 停止。

**注意**：启动脚本会自动清理端口占用，无需手动处理。

## 服务地址

```
http://10.100.191.82:8081
```

## Android APP 配置

```kotlin
httpManager.setBaseUrl("http://10.100.191.82:8081")
httpManager.sendMessage("你好，请帮我控制机械臂")
```

## 测试

```bash
# 在另一个终端
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

## 故障排除

如果端口被占用无法启动：

```bash
./cleanup_http_bridge.sh
./start_openclaw_bridge.sh
```

就这么简单！
