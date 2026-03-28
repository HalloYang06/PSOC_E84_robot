#!/bin/bash

# ROS 2工作空间构建脚本

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "  ROS 2 Workspace Build Script"
echo "=========================================="
echo ""

# 加载ROS 2环境
if [ -z "$ROS_DISTRO" ]; then
    echo "加载ROS 2环境..."
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
        echo "使用ROS 2 Jazzy"
    elif [ -f "/opt/ros/humble/setup.bash" ]; then
        source /opt/ros/humble/setup.bash
        echo "使用ROS 2 Humble"
    else
        echo "错误: 未找到ROS 2安装"
        exit 1
    fi
else
    echo "ROS 2环境已加载: $ROS_DISTRO"
fi

echo ""

# 解析参数
BUILD_TYPE="Release"
CLEAN=false
PACKAGES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            BUILD_TYPE="Debug"
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --packages)
            PACKAGES="--packages-select $2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: $0 [--debug] [--clean] [--packages <package_name>]"
            exit 1
            ;;
    esac
done

# 清理构建
if [ "$CLEAN" = true ]; then
    echo "清理构建目录..."
    rm -rf build install log
    echo "清理完成"
    echo ""
fi

# 构建
echo "构建类型: $BUILD_TYPE"
echo "工作空间: $WORKSPACE_ROOT"
echo ""

cd "$WORKSPACE_ROOT"

echo "开始构建..."
colcon build \
    --cmake-args -DCMAKE_BUILD_TYPE=$BUILD_TYPE \
    --symlink-install \
    $PACKAGES

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "  构建成功！"
    echo "=========================================="
    echo ""
    echo "加载环境:"
    echo "  source install/setup.bash"
    echo ""
    echo "运行节点:"
    echo "  ros2 launch camera_client camera.launch.py"
    echo "  ros2 launch http_bridge http_bridge.launch.py"
    echo "  ros2 launch system.launch.py  # 启动所有节点"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "  构建失败"
    echo "=========================================="
    exit 1
fi
