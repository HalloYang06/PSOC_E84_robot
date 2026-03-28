# 快速参考

## 项目结构

```
camera_client/    - 摄像头WebSocket客户端
http_bridge/      - HTTP API服务器（APP通信）
scripts/          - 工具脚本
docs/             - 文档
build/            - 构建输出
```

## 常用命令

### 构建
```bash
./build.sh              # 构建所有
./build.sh camera       # 仅摄像头
./build.sh http         # 仅HTTP Bridge
./build.sh clean        # 清理
```

### 运行
```bash
# 摄像头客户端
cd camera_client && ./run_camera.sh

# HTTP Bridge (Python)
cd http_bridge && ./start_http_bridge.sh

# HTTP Bridge (C++)
./build/bin/http_bridge_server
```

### 测试
```bash
# HTTP API测试
cd http_bridge && python3 test_http_bridge.py

# 摄像头测试
v4l2-ctl --list-devices
```

## 文件位置

| 文件 | 位置 |
|------|------|
| 摄像头源码 | `camera_client/camera_websocket_client.cpp` |
| HTTP服务器(Python) | `http_bridge/http_bridge_server.py` |
| HTTP服务器(C++) | `http_bridge/http_bridge_server.cpp` |
| 主CMake | `CMakeLists.txt` |
| 构建脚本 | `build.sh` |
| 可执行文件 | `build/bin/` |

## HTTP API端点

```
GET  /health              - 健康检查
GET  /status              - 获取状态
POST /mode                - 切换模式
POST /control             - 控制指令
POST /memory/execute      - 执行记忆动作
POST /api/command         - OpenClaw工具调用
```

## 配置

### 摄像头服务器地址
编辑: `camera_client/run_camera.sh`
```bash
SERVER_IP="10.100.191.235"
SERVER_PORT="8080"
```

### HTTP服务器端口
编辑: `http_bridge/http_bridge_server.py`
```python
port = 8081
```

## 查看文档

```bash
cat README.md                      # 项目说明
cat docs/QUICKSTART.md             # 快速入门
cat docs/HTTP_BRIDGE_README.md     # HTTP API详细文档
cat PROJECT_REORGANIZATION.md      # 重组说明
```

## 验证项目结构

```bash
./verify_structure.sh
```
