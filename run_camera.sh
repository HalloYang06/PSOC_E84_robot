#!/bin/bash

# 快速启动脚本 - 自动检测摄像头并启动客户端

SERVER_IP="10.100.191.235"
SERVER_PORT="8080"
FPS="10"

echo "==================================="
echo "Camera WebSocket Client - Quick Start"
echo "==================================="
echo ""

# 检查程序是否已编译
if [ ! -f "build/camera_websocket_client" ]; then
    echo "Program not found. Building..."
    mkdir -p build
    cd build
    cmake ..
    make
    cd ..
    echo ""
fi

# 显示可用的摄像头
echo "Available cameras:"
v4l2-ctl --list-devices | grep -A 2 "usb\|USB\|WebCamera"
echo ""

# 运行程序（自动检测摄像头）
echo "Starting camera client..."
echo "Server: $SERVER_IP:$SERVER_PORT"
echo "FPS: $FPS"
echo "Camera: Auto-detect"
echo ""
echo "Press Ctrl+C to stop"
echo "==================================="
echo ""

./build/camera_websocket_client $SERVER_IP $SERVER_PORT -1 $FPS
