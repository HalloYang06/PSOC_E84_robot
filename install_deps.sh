#!/bin/bash

# 安装脚本 - 安装所有必需的依赖

echo "Installing dependencies for Camera WebSocket Client..."

# 更新包列表
sudo apt update

# 安装OpenCV
echo "Installing OpenCV..."
sudo apt install -y libopencv-dev

# 安装Boost
echo "Installing Boost..."
sudo apt install -y libboost-all-dev

# 安装nlohmann-json
echo "Installing nlohmann-json..."
sudo apt install -y nlohmann-json3-dev

# 安装CMake (如果需要)
echo "Installing CMake..."
sudo apt install -y cmake build-essential

# 安装摄像头相关工具
echo "Installing camera utilities..."
sudo apt install -y v4l-utils

echo ""
echo "Installation complete!"
echo ""
echo "To verify camera is detected, run:"
echo "  v4l2-ctl --list-devices"
echo ""
echo "To build the project:"
echo "  mkdir build && cd build"
echo "  cmake .."
echo "  make"
echo ""
echo "To run:"
echo "  ./camera_websocket_client [server_ip] [port] [camera_id] [fps]"
echo "  Example: ./camera_websocket_client 10.100.191.235 8080 0 10"
