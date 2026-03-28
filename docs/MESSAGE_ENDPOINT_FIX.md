# 问题解决完整记录

## 问题描述

APP连接服务器后，发送消息时返回404错误。

## 问题分析

### 监控日志显示
```
10.100.191.42 - - [28/Mar/2026 10:49:59] "GET /health HTTP/1.1" 200 -  ✅ 连接成功
10.100.191.42 - - [28/Mar/2026 10:51:30] "POST /message HTTP/1.1" 404 - ❌ 发送消息失败
```

### 根本原因

APP使用 `OpenClawService.kt` 发送自然语言消息到 `/message` 端点，但服务器上没有实现这个端点。

## 解决方案

### 添加 `/message` 端点

在 `http_bridge_server.py` 中添加：

```python
@app.route('/message', methods=['POST'])
def handle_message():
    """处理OpenClaw自然语言消息"""
    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({
            "success": False,
            "message": "",
            "error": "Missing message parameter"
        }), 400

    # 记录收到的消息
    ros_node.get_logger().info(f'Received message: {message}')

    # 发布消息到ROS话题
    ros_node.publish_command({
        "type": "natural_language",
        "message": message
    })

    # 返回响应
    return jsonify({
        "success": True,
        "message": f"收到消息: {message}",
        "error": None
    })
```

### 测试结果

```bash
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message":"测试消息"}'

# 响应:
{
    "success": true,
    "message": "收到消息: 测试消息",
    "error": null
}
```

## 完整的API端点列表

现在服务器支持所有APP需要的端点：

| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| `/health` | GET | 健康检查 | ✅ |
| `/status` | GET | 获取系统状态 | ✅ |
| `/mode` | POST | 切换模式 | ✅ |
| `/control` | POST | 发送控制指令 | ✅ |
| `/memory/execute` | POST | 执行记忆动作 | ✅ |
| `/memory/stop` | POST | 停止记忆动作 | ✅ |
| `/api/sensor/data` | GET | 获取传感器数据 | ✅ |
| `/api/training/start` | POST | 开始训练 | ✅ |
| `/api/stats` | GET | 获取统计数据 | ✅ |
| `/api/command` | POST | OpenClaw工具调用 | ✅ |
| `/message` | POST | 自然语言消息 | ✅ 新增 |

## APP使用场景

### `/message` 端点的用途

APP通过 `OpenClawService` 发送自然语言指令：

```kotlin
// APP代码
val openClawService = OpenClawService()
openClawService.setBaseUrl("http://10.100.191.82:8081")

// 发送自然语言消息
val response = openClawService.sendMessage("抬起手臂")
```

### 请求格式

```json
POST /message
Content-Type: application/json

{
    "message": "抬起手臂"
}
```

### 响应格式

```json
{
    "success": true,
    "message": "收到消息: 抬起手臂",
    "error": null
}
```

## 数据流

```
Android APP
    ↓ POST /message {"message": "抬起手臂"}
HTTP Bridge Server
    ↓ 发布到ROS话题 /can_tx
    ↓ {"type": "natural_language", "message": "抬起手臂"}
CAN Node (未来实现)
    ↓ 解析并执行
OpenClaw Hardware
```

## 重启服务器

修改代码后需要重启：

```bash
# 停止旧服务器
pkill -f http_bridge_server.py

# 启动新服务器
./start_http_bridge.sh
```

## 验证步骤

### 1. 测试端点
```bash
curl -X POST http://10.100.191.82:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message":"测试"}'
```

### 2. 在APP中测试
- 打开APP
- 连接到服务器 (10.100.191.82:8081)
- 发送自然语言指令
- 应该收到成功响应

### 3. 监控日志
```bash
./scripts/monitor_requests.sh
```

应该看到：
```
POST /message HTTP/1.1" 200 -
```

## 问题解决时间线

1. **10:49** - APP连接成功 (`GET /health` 返回200)
2. **10:51** - 发送消息失败 (`POST /message` 返回404)
3. **分析** - 查看APP源码，发现使用 `/message` 端点
4. **修复** - 在服务器添加 `/message` 端点
5. **测试** - 端点工作正常，返回200

## 学习要点

### 1. 如何排查404错误

**步骤**：
1. 监控HTTP请求日志
2. 找出404的URL路径
3. 查看APP源码确认端点用途
4. 在服务器添加缺失的端点

### 2. Flask路由添加

```python
@app.route('/path', methods=['POST'])
def handler():
    data = request.get_json()
    # 处理逻辑
    return jsonify(response)
```

### 3. ROS 2消息发布

```python
ros_node.publish_command({
    "type": "message_type",
    "data": "content"
})
```

### 4. HTTP请求-响应格式

**请求**：
- Method: POST
- Headers: Content-Type: application/json
- Body: JSON数据

**响应**：
- Status: 200 OK
- Body: JSON数据

## 下一步

现在所有端点都已实现，APP应该可以完全正常工作：

- ✅ 连接服务器
- ✅ 获取状态
- ✅ 切换模式
- ✅ 发送控制指令
- ✅ 发送自然语言消息
- ✅ 执行记忆动作

## 相关文件

- `http_bridge_server.py` - HTTP服务器实现
- `OpenClawService.kt` - APP的OpenClaw服务
- `monitor_requests.sh` - 请求监控脚本
- `start_http_bridge.sh` - 服务器启动脚本
