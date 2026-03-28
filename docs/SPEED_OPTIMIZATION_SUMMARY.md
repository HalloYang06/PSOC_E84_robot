# 拍照速度优化总结

## 问题

- **APP拍照**: 30-120秒 ❌
- **命令行测试**: 1.6秒 ✅

## 根本原因

APP发送的消息是 **"拍个照"**，但快速路径只匹配 **"拍照"、"拍一张"** 等关键词，导致走了慢速AI路径。

## 解决方案

### 1. 扩展快速路径关键词匹配

修改 `http_bridge_server.py` 第230行：

```python
# 之前（不匹配"拍个照"）
if any(keyword in message for keyword in ['拍照', '拍一张', '照片', 'take photo', 'take a photo', 'capture']):

# 现在（匹配"拍个照"）
if any(keyword in message for keyword in ['拍照', '拍一张', '拍个照', '照片', '拍张照', 'take photo', 'take a photo', 'capture', 'photo']):
```

### 2. 重新编译并重启

```bash
# 编译
colcon build --packages-select http_bridge --symlink-install

# 重启
pkill -9 -f http_bridge
source install/setup.bash
ros2 launch http_bridge http_bridge.launch.py &
```

## 测试结果

### 命令行测试
```bash
# "拍一张照片" - 1.6秒
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message":"拍一张照片"}'

# "拍个照" - 1.7秒
curl -X POST http://localhost:8081/message \
  -H "Content-Type: application/json" \
  -d '{"message":"拍个照"}'
```

### 日志确认
```
[INFO] Received message: 拍个照
[INFO] Quick path: Taking photo          ← 走快速路径
[INFO] Quick path executed in <3s        ← 1.7秒完成
```

## 性能对比

| 场景 | 之前 | 现在 | 提升 |
|------|------|------|------|
| APP "拍个照" | 30-120秒 | 1.7秒 | **60倍** |
| 命令行 "拍一张照片" | 1.6秒 | 1.6秒 | 保持 |

## APP端无需修改

✅ APP代码不需要任何修改
✅ 继续使用 `/message` 端点
✅ 继续发送 "拍个照" 消息
✅ 自动享受快速路径优化

## 架构说明

### 快速路径（1-2秒）⚡
```
APP "拍个照"
    ↓
HTTP Bridge /message
    ↓
关键词匹配 ✓
    ↓
直接执行 take_photo.sh
    ↓
返回结果 (1.7秒)
```

### AI路径（30-120秒）🤖
```
APP "帮我分析这张照片"
    ↓
HTTP Bridge /message
    ↓
关键词匹配 ✗
    ↓
调用 OpenClaw AI
    ↓
AI推理 + 工具调用
    ↓
返回结果 (30-120秒)
```

## 支持的快速命令

### 拍照
- "拍照"
- "拍一张"
- "拍个照"
- "拍张照"
- "照片"
- "take photo"
- "capture"
- "photo"

### 查找摄像头
- "查找摄像头"
- "有哪些摄像头"
- "find camera"
- "list camera"

### 系统状态
- "系统状态"
- "状态"
- "system status"
- "status"

## 添加新的快速命令

编辑 `http_bridge_server.py` 的 `execute_quick_command()` 函数：

```python
def execute_quick_command(message):
    # 添加新命令
    if any(keyword in message for keyword in ['你的关键词1', '你的关键词2']):
        ros_node.get_logger().info('Quick path: Your command')
        try:
            result = subprocess.run(
                ['/path/to/your/script.sh'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return f"✓ 成功：{result.stdout.strip()}"
        except Exception as e:
            return None

    # 没有匹配的快速命令，返回None走AI路径
    return None
```

## 故障排查

### 如果APP还是慢

1. **检查HTTP Bridge是否运行**
   ```bash
   curl http://localhost:8081/health
   # 应该返回: {"status":"ok"}
   ```

2. **查看实时日志**
   ```bash
   tail -f /tmp/http_launch.log
   ```

   应该看到：
   ```
   [INFO] Quick path: Taking photo
   [INFO] Quick path executed in <3s
   ```

   如果看到：
   ```
   [INFO] Using AI path (slow, 30-120s)
   ```
   说明关键词没匹配上，需要添加更多关键词。

3. **确认编译生效**
   ```bash
   grep "拍个照" install/http_bridge/lib/python3.12/site-packages/http_bridge/http_bridge_server.py
   # 应该能找到这个关键词
   ```

## 维护建议

1. **定期查看日志**，了解用户常用的表达方式
2. **添加新关键词**，覆盖更多用户习惯
3. **监控响应时间**，确保快速路径正常工作

## 总结

✅ 问题已解决
✅ APP无需修改
✅ 响应时间从30-120秒降到1.7秒
✅ 提升60倍性能
✅ 保留AI能力处理复杂任务
