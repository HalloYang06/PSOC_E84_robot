#!/bin/bash

# OpenClaw 项目统一构建脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  OpenClaw Project Build Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  all              构建所有项目（默认）"
    echo "  camera           仅构建摄像头客户端"
    echo "  http             仅构建HTTP Bridge"
    echo "  clean            清理构建文件"
    echo "  help             显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0               # 构建所有项目"
    echo "  $0 camera        # 仅构建摄像头客户端"
    echo "  $0 clean         # 清理构建文件"
    exit 0
}

# 清理构建文件
clean_build() {
    echo -e "${YELLOW}清理构建文件...${NC}"
    rm -rf build
    rm -rf camera_client/build
    rm -rf http_bridge/build
    echo -e "${GREEN}✓ 清理完成${NC}"
    exit 0
}

# 构建项目
build_project() {
    local target=$1

    # 创建构建目录
    if [ ! -d "build" ]; then
        mkdir build
    fi

    cd build

    echo -e "${BLUE}配置CMake...${NC}"

    case $target in
        camera)
            cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_CAMERA_CLIENT=ON -DBUILD_HTTP_BRIDGE=OFF ..
            ;;
        http)
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
            cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_CAMERA_CLIENT=OFF -DBUILD_HTTP_BRIDGE=ON ..
            ;;
        all)
            # 检查ROS 2环境
            if [ -z "$ROS_DISTRO" ]; then
                echo -e "${YELLOW}正在加载ROS 2环境...${NC}"
                if [ -f "/opt/ros/jazzy/setup.bash" ]; then
                    source /opt/ros/jazzy/setup.bash
                elif [ -f "/opt/ros/humble/setup.bash" ]; then
                    source /opt/ros/humble/setup.bash
                fi
            fi
            cmake -DCMAKE_BUILD_TYPE=Release ..
            ;;
    esac

    echo ""
    echo -e "${BLUE}开始编译...${NC}"
    make -j$(nproc)

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  构建成功！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "可执行文件位置:"

    if [ -f "bin/camera_websocket_client" ]; then
        echo -e "  ${GREEN}✓${NC} 摄像头客户端: build/bin/camera_websocket_client"
    fi

    if [ -f "bin/http_bridge_server" ]; then
        echo -e "  ${GREEN}✓${NC} HTTP Bridge: build/bin/http_bridge_server"
    fi

    echo ""
    echo "运行方式:"

    if [ -f "bin/camera_websocket_client" ]; then
        echo "  ./build/bin/camera_websocket_client [server_ip] [port] [camera_id] [fps]"
    fi

    if [ -f "bin/http_bridge_server" ]; then
        echo "  ./build/bin/http_bridge_server"
        echo "  或使用Python版本: ./http_bridge/start_http_bridge.sh"
    fi

    echo ""
}

# 主逻辑
case "${1:-all}" in
    help|-h|--help)
        show_help
        ;;
    clean)
        clean_build
        ;;
    camera)
        build_project camera
        ;;
    http)
        build_project http
        ;;
    all)
        build_project all
        ;;
    *)
        echo -e "${RED}错误: 未知选项 '$1'${NC}"
        echo "使用 '$0 help' 查看帮助"
        exit 1
        ;;
esac
