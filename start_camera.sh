#!/bin/bash
# 启动摄像头 WebSocket 客户端

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "启动摄像头 WebSocket 客户端"
echo "========================================="
echo ""

# 默认参数
SERVER_IP="${1:-10.100.191.235}"
SERVER_PORT="${2:-8080}"
CAMERA_ID="${3:--1}"
FPS="${4:-10}"

echo "服务器地址: $SERVER_IP:$SERVER_PORT"
echo "摄像头ID: $CAMERA_ID (-1 = 自动检测)"
echo "帧率: $FPS FPS"
echo ""
echo "按 Ctrl+C 停止"
echo "========================================="
echo ""

# 设置清理函数
cleanup() {
    echo ""
    echo ""
    echo "========================================="
    echo "正在停止摄像头客户端..."
    echo "========================================="
    exit 0
}

# 捕获 Ctrl+C 信号
trap cleanup SIGINT SIGTERM

# 启动摄像头客户端
cd "$SCRIPT_DIR"
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run camera_client camera_websocket_client --ros-args \
    -p server_ip:=$SERVER_IP \
    -p server_port:=$SERVER_PORT \
    -p camera_id:=$CAMERA_ID \
    -p fps:=$FPS
