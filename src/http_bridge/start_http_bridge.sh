#!/bin/bash

# HTTP Bridge Server 快速启动脚本 - 使用虚拟环境

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/../venv"

echo "=== HTTP Bridge Server for OpenClaw <-> APP ==="
echo ""

# 检查虚拟环境是否存在
if [ ! -d "$VENV_DIR" ]; then
    echo "虚拟环境不存在，正在创建..."
    python3 -m venv "$VENV_DIR"

    if [ $? -ne 0 ]; then
        echo "错误: 无法创建虚拟环境"
        echo "请先安装: sudo apt install python3-venv"
        exit 1
    fi

    echo "虚拟环境创建成功"
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 检查并安装依赖
echo "检查Python依赖..."
if ! python -c "import flask" 2>/dev/null; then
    echo "安装Flask..."
    pip install flask
fi

if ! python -c "import requests" 2>/dev/null; then
    echo "安装requests..."
    pip install requests
fi

# 检查ROS 2环境
if [ -z "$ROS_DISTRO" ]; then
    echo "正在加载ROS 2环境..."
    source /opt/ros/jazzy/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash 2>/dev/null
fi

# 显示网络信息
echo ""
echo "NanoPi IP地址："
hostname -I | awk '{print $1}'
echo ""

# 启动服务器
echo "正在启动HTTP Bridge Server..."
echo "服务器地址: http://0.0.0.0:8081"
echo "虚拟环境: $VENV_DIR"
echo "按 Ctrl+C 停止服务器"
echo ""

python "$SCRIPT_DIR/http_bridge_server.py"

# 退出时停用虚拟环境
deactivate
