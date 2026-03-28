#!/bin/bash

# OpenClaw 完整系统启动脚本
# 启动所有必要的服务：CAN接口、HTTP Bridge、WebSocket Bridge

set -e

echo "=========================================="
echo "  OpenClaw System Startup"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查ROS 2环境
if [ -z "$ROS_DISTRO" ]; then
    echo -e "${YELLOW}正在加载ROS 2环境...${NC}"
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
    elif [ -f "/opt/ros/humble/setup.bash" ]; then
        source /opt/ros/humble/setup.bash
    else
        echo -e "${RED}错误: 未找到ROS 2安装${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ ROS 2环境: $ROS_DISTRO${NC}"

# 检查CAN接口
echo ""
echo "检查CAN接口..."
if ip link show can0 &> /dev/null; then
    CAN_STATE=$(ip -details link show can0 | grep -o "state [A-Z]*" | awk '{print $2}')
    if [ "$CAN_STATE" == "UP" ]; then
        echo -e "${GREEN}✓ CAN0接口已启动${NC}"
    else
        echo -e "${YELLOW}! CAN0接口存在但未启动，正在启动...${NC}"
        sudo ip link set can0 type can bitrate 500000
        sudo ip link set can0 up
        echo -e "${GREEN}✓ CAN0接口已启动${NC}"
    fi
else
    echo -e "${YELLOW}! CAN0接口不存在，跳过CAN配置${NC}"
fi

# 显示网络信息
echo ""
echo "网络信息:"
IP_ADDR=$(hostname -I | awk '{print $1}')
echo -e "  IP地址: ${GREEN}$IP_ADDR${NC}"
echo -e "  HTTP服务: ${GREEN}http://$IP_ADDR:8081${NC}"
echo ""

# 检查Flask
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}正在安装Flask...${NC}"
    pip3 install flask
fi

# 启动选项
echo "请选择启动模式:"
echo "  1) 仅HTTP Bridge (推荐用于APP开发)"
echo "  2) 完整系统 (HTTP + CAN + WebSocket)"
echo "  3) 测试模式 (HTTP + 模拟数据)"
echo ""
read -p "请输入选项 [1-3]: " choice

case $choice in
    1)
        echo ""
        echo -e "${GREEN}启动HTTP Bridge Server...${NC}"
        python3 /home/pi/ros_node/http_bridge_server.py
        ;;
    2)
        echo ""
        echo -e "${GREEN}启动完整系统...${NC}"
        echo "TODO: 实现完整系统启动"
        python3 /home/pi/ros_node/http_bridge_server.py
        ;;
    3)
        echo ""
        echo -e "${GREEN}启动测试模式...${NC}"
        echo "TODO: 实现测试模式"
        python3 /home/pi/ros_node/http_bridge_server.py
        ;;
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac
