#!/bin/bash
# 启动 OpenClaw HTTP Bridge 服务器（前台运行，Ctrl+C 停止）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 停用 venv（如果激活了）
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate 2>/dev/null || true
fi

echo "========================================="
echo "启动 OpenClaw HTTP Bridge"
echo "========================================="
echo ""

# 检查并清理端口占用
PORT_PID=$(lsof -ti :8081 2>/dev/null)
if [ -n "$PORT_PID" ]; then
    echo "⚠️  端口 8081 被占用，正在清理..."
    kill -9 $PORT_PID 2>/dev/null
    sleep 1
    echo "✓ 端口已清理"
    echo ""
fi

# 检查 OpenClaw Gateway 是否运行
if ! systemctl --user is-active --quiet openclaw-gateway.service; then
    echo "⚠️  OpenClaw Gateway 未运行，正在启动..."
    systemctl --user start openclaw-gateway.service
    sleep 3
fi

echo "✓ OpenClaw Gateway 运行中"
echo ""

# 获取 IP 地址
IP=$(hostname -I | awk '{print $1}')
echo "NanoPi IP 地址: $IP"
echo "服务器地址: http://$IP:8081"
echo ""
echo "按 Ctrl+C 停止服务"
echo "========================================="
echo ""

# 设置清理函数
cleanup() {
    echo ""
    echo ""
    echo "========================================="
    echo "正在停止服务..."
    echo "========================================="
    exit 0
}

# 捕获 Ctrl+C 信号
trap cleanup SIGINT SIGTERM

# 启动 HTTP Bridge（前台运行）
cd "$SCRIPT_DIR"
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch http_bridge http_bridge.launch.py
