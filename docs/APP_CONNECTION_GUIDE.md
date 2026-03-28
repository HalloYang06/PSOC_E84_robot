# APP连接配置指南

## 问题解决

### 404错误原因
APP默认配置的服务器地址是 `192.168.1.100:8080`，但NanoPi的实际地址不同。

### 解决方案

#### 在APP中配置正确的服务器地址

1. **打开APP**
2. **进入"远程控制"界面**
3. **输入服务器信息**：
   ```
   IP地址: 10.100.191.82
   端口: 8081
   ```
4. **点击"连接"按钮**

#### 验证连接

连接成功后，APP会显示：
- ✅ 绿色WiFi图标
- ✅ "已连接到 10.100.191.82:8081"

## APP使用的所有API端点

所有端点都已在服务器上实现：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/status` | GET | 获取系统状态和传感器数据 |
| `/mode` | POST | 切换控制模式 |
| `/control` | POST | 发送控制指令 |
| `/memory/execute` | POST | 执行记忆动作 |
| `/memory/stop` | POST | 停止记忆动作 |
| `/api/sensor/data` | GET | 获取传感器数据 |
| `/api/training/start` | POST | 开始训练会话 |
| `/api/stats` | GET | 获取统计数据 |
| `/api/command` | POST | OpenClaw工具调用 |

## APP代码分析

### HTTP管理器

APP使用两个HTTP管理器：

1. **HttpManager.kt** - 基础HTTP通信
   - 默认URL: `http://localhost:8081`
   - 用于轮询传感器数据

2. **PsocHttpManager.kt** - PSoC API调用
   - 默认URL: `http://192.168.1.100`
   - 实现完整的REST API

### 设置URL的方法

```kotlin
// 方法1: 通过UI设置（推荐）
// 在RemoteControlScreen中输入IP和端口

// 方法2: 代码中设置
val psocManager = PsocHttpManager()
psocManager.setBaseUrl("http://10.100.191.82:8081")

// 方法3: 通过ViewModel
viewModel.setPSoCUrl("http://10.100.191.82:8081")
```

## 测试步骤

### 1. 确保服务器运行

```bash
# 在NanoPi上
./start_http_bridge.sh
```

### 2. 测试网络连接

```bash
# 在手机浏览器访问
http://10.100.191.82:8081/health
```

应该看到：
```json
{"status":"ok"}
```

### 3. 在APP中连接

- 打开APP
- 进入远程控制界面
- 输入IP: `10.100.191.82`
- 输入端口: `8081`
- 点击连接

### 4. 验证功能

连接成功后测试：
- ✅ 查看传感器数据
- ✅ 切换控制模式
- ✅ 发送控制指令
- ✅ 执行记忆动作

## 监控请求日志

如果仍有问题，运行监控脚本查看实际请求：

```bash
./scripts/monitor_requests.sh
```

然后在APP上操作，查看日志输出。

## 常见问题

### Q: APP显示"连接失败"
**A**: 检查：
1. NanoPi和手机在同一WiFi网络
2. HTTP Bridge服务器正在运行
3. IP地址输入正确
4. 端口号是8081（不是8080）

### Q: 连接成功但功能不工作
**A**: 查看监控日志，确认：
1. APP发送的请求格式正确
2. 服务器返回200状态码
3. 没有JSON解析错误

### Q: 如何获取NanoPi的IP地址
**A**: 在NanoPi上运行：
```bash
hostname -I
```

## 网络配置

### 确保在同一网络

**NanoPi**:
```bash
ip addr show
# 查看wlan0或eth0的IP
```

**手机**:
- 设置 → WiFi → 查看当前连接的网络
- 确保和NanoPi在同一个WiFi

### 防火墙设置

如果连接失败，检查防火墙：
```bash
sudo ufw allow 8081/tcp
```

## 开发者信息

### APP源码位置
```
GitHub: ChillAmnesiac/Medical-Rehabilitation-Manipulator
分支: APP
```

### 关键文件
- `HttpManager.kt` - HTTP通信管理
- `PsocHttpManager.kt` - PSoC API调用
- `RemoteControlScreen.kt` - 远程控制UI
- `RobotViewModel.kt` - 业务逻辑

### API兼容性
✅ 完全兼容 - 所有APP需要的端点都已实现
