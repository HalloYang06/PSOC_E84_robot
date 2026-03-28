#!/bin/bash

# HTTP Bridge Server 编译和运行脚本

set -e

echo "=== HTTP Bridge Server for OpenClaw <-> APP ==="

# 检查ROS 2环境
if [ -z "$ROS_DISTRO" ]; then
    echo "正在加载ROS 2环境..."
    source /opt/ros/jazzy/setup.bash
fi

# 创建构建目录
BUILD_DIR="build_http_bridge"
if [ ! -d "$BUILD_DIR" ]; then
    mkdir -p "$BUILD_DIR"
fi

cd "$BUILD_DIR"

# 编译
echo "正在编译HTTP Bridge Server..."
cmake -DCMAKE_BUILD_TYPE=Release -f ../CMakeLists_http_bridge.txt ..
make -j$(nproc)

echo "编译完成！"
echo ""
echo "使用方法："
echo "  ./build_http_bridge/http_bridge_server"
echo ""
echo "HTTP服务器将监听在: http://0.0.0.0:8081"
echo ""
echo "API端点："
echo "  GET  /health           - 健康检查"
echo "  GET  /status           - 获取系统状态和传感器数据"
echo "  POST /mode             - 切换控制模式"
echo "  POST /control          - 发送控制指令"
echo "  POST /memory/execute   - 执行记忆动作"
echo "  POST /memory/stop      - 停止记忆动作"
echo "  POST /api/command      - OpenClaw工具调用"
echo ""
