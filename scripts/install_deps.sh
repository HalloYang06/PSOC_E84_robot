#!/bin/bash

# ROS 2依赖安装脚本

echo "=========================================="
echo "  安装ROS 2工作空间依赖"
echo "=========================================="
echo ""

# 检查ROS 2是否安装
if [ -z "$ROS_DISTRO" ]; then
    echo "正在加载ROS 2环境..."
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
        echo "使用ROS 2 Jazzy"
    elif [ -f "/opt/ros/humble/setup.bash" ]; then
        source /opt/ros/humble/setup.bash
        echo "使用ROS 2 Humble"
    else
        echo "错误: 未找到ROS 2安装"
        echo "请先安装ROS 2: https://docs.ros.org/en/jazzy/Installation.html"
        exit 1
    fi
else
    echo "ROS 2环境已加载: $ROS_DISTRO"
fi

echo ""
echo "安装系统依赖..."

# ROS 2开发工具
sudo apt update
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    ros-$ROS_DISTRO-ament-cmake \
    ros-$ROS_DISTRO-ament-cmake-python

# ROS 2核心包
sudo apt install -y \
    ros-$ROS_DISTRO-rclcpp \
    ros-$ROS_DISTRO-rclpy \
    ros-$ROS_DISTRO-std-msgs \
    ros-$ROS_DISTRO-sensor-msgs

# 摄像头相关
sudo apt install -y \
    ros-$ROS_DISTRO-cv-bridge \
    ros-$ROS_DISTRO-image-transport \
    libopencv-dev \
    v4l-utils

# C++库
sudo apt install -y \
    libboost-all-dev

# Python包 - 使用apt安装系统包
sudo apt install -y \
    python3-catkin-pkg \
    python3-empy \
    python3-lark \
    python3-yaml \
    python3-flask \
    python3-flask-cors \
    python3-numpy

# 创建并配置venv
echo ""
echo "配置Python虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 创建venv"
fi

source venv/bin/activate
pip install --upgrade pip
pip install catkin_pkg empy lark pyyaml flask flask-cors websockets numpy opencv-python
echo "✅ venv依赖安装完成"
deactivate

echo ""
echo "注意: 项目使用venv管理Python依赖"
echo "已安装: catkin_pkg empy lark pyyaml flask flask-cors websockets numpy opencv-python"
echo ""

echo ""
echo "=========================================="
echo "  依赖安装完成！"
echo "=========================================="
echo ""
echo "下一步:"
echo "  1. 构建工作空间: ./build_ros2.sh"
echo "  2. 加载环境: source install/setup.bash"
echo "  3. 启动节点: ros2 launch launch/system.launch.py"
echo ""
