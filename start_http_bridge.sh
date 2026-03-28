#!/bin/bash

# HTTP Bridge 启动脚本

echo "=========================================="
echo "  启动 HTTP Bridge Server"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ ! -d "venv" ]; then
    echo "错误: 虚拟环境不存在"
    echo "请先创建虚拟环境并安装依赖:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install catkin_pkg empy lark pyyaml flask flask-cors websockets numpy"
    exit 1
fi

source venv/bin/activate

# 加载ROS 2环境
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# 获取IP地址
IP=$(hostname -I | awk '{print $1}')

echo "NanoPi IP地址: $IP"
echo "服务器将监听在: http://0.0.0.0:8081"
echo "从其他设备访问: http://$IP:8081"
echo ""
echo "Android APP配置:"
echo "  服务器地址: $IP"
echo "  端口: 8081"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "=========================================="
echo ""

# 直接运行Python脚本
cd src/http_bridge/http_bridge
python3 http_bridge_server.py
