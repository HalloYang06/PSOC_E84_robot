# ROS 2工作空间设置完成

## ✅ 改造完成

项目已成功改造为标准ROS 2 Jazzy工作空间，使用colcon构建系统。

## 当前状态

### 包结构
- `camera_client` - C++ ament_cmake包（摄像头WebSocket客户端）
- `http_bridge` - Python ament_python包（HTTP API服务器）

### 虚拟环境
项目使用venv来管理Python依赖，已安装：
- catkin_pkg, empy, lark, pyyaml (ROS 2构建工具)
- flask, flask-cors, websockets (应用依赖)

## 快速开始

### 1. 构建工作空间
```bash
./build_ros2.sh
```

### 2. 加载环境
```bash
source install/setup.bash
```

### 3. 启动节点

**启动摄像头客户端：**
```bash
ros2 launch camera_client camera.launch.py
```

**启动HTTP Bridge：**
```bash
ros2 launch http_bridge http_bridge.launch.py
```

**启动所有节点：**
```bash
ros2 launch launch/system.launch.py
```

**带参数启动：**
```bash
ros2 launch camera_client camera.launch.py \
    server_ip:=192.168.1.100 \
    server_port:=8080 \
    camera_id:=0 \
    fps:=15
```

## 常用命令

### 包管理
```bash
# 列出所有包
ros2 pkg list

# 查看包信息
ros2 pkg prefix camera_client
ros2 pkg prefix http_bridge
```

### 节点管理
```bash
# 列出运行中的节点
ros2 node list

# 查看节点信息
ros2 node info /camera_websocket_client
ros2 node info /http_bridge_server
```

### 话题管理
```bash
# 列出所有话题
ros2 topic list

# 查看话题数据
ros2 topic echo /camera/image_raw

# 查看话题频率
ros2 topic hz /camera/image_raw
```

### 参数管理
```bash
# 列出节点参数
ros2 param list

# 获取参数值
ros2 param get /camera_websocket_client server_ip

# 设置参数值
ros2 param set /camera_websocket_client fps 15
```

## 构建选项

### 构建特定包
```bash
./build_ros2.sh --packages camera_client
./build_ros2.sh --packages http_bridge
```

### 调试构建
```bash
./build_ros2.sh --debug
```

### 清理并重新构建
```bash
./build_ros2.sh --clean
```

### 使用colcon直接构建
```bash
colcon build --symlink-install
colcon build --packages-select camera_client
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug
```

## 依赖管理

### 系统依赖（已安装）
- ROS 2 Jazzy
- colcon构建工具
- cv_bridge, image_transport
- OpenCV, Boost

### Python依赖（在venv中）
```bash
source venv/bin/activate
pip list
```

### 添加新依赖
如果需要添加新的Python包：
```bash
source venv/bin/activate
pip install <package_name>
```

## 故障排除

### 构建失败
```bash
# 确保ROS 2环境已加载
source /opt/ros/jazzy/setup.bash

# 清理并重新构建
./build_ros2.sh --clean
```

### 找不到包
```bash
# 确保已source工作空间
source install/setup.bash

# 检查包是否已安装
ros2 pkg list | grep camera_client
```

### Python模块找不到
```bash
# 确保venv已激活（构建时会自动使用）
source venv/bin/activate
pip list
```

### 摄像头无法打开
```bash
# 检查摄像头设备
v4l2-ctl --list-devices
ls /dev/video*

# 检查权限
sudo usermod -a -G video $USER
# 重新登录生效
```

## 开发工作流

### 修改C++代码
```bash
# 1. 编辑代码
vim src/camera_client/camera_websocket_client.cpp

# 2. 重新构建
./build_ros2.sh --packages camera_client

# 3. 加载环境
source install/setup.bash

# 4. 运行
ros2 launch camera_client camera.launch.py
```

### 修改Python代码
```bash
# 1. 编辑代码
vim src/http_bridge/http_bridge/http_bridge_server.py

# 2. 重新构建（Python使用--symlink-install，通常不需要重新构建）
./build_ros2.sh --packages http_bridge

# 3. 加载环境
source install/setup.bash

# 4. 运行
ros2 launch http_bridge http_bridge.launch.py
```

### 添加新包
```bash
# C++包
cd src
ros2 pkg create --build-type ament_cmake my_package \
    --dependencies rclcpp std_msgs

# Python包
ros2 pkg create --build-type ament_python my_package \
    --dependencies rclpy std_msgs

# 构建
cd ..
colcon build --packages-select my_package
```

## 文档

- [CLAUDE.md](CLAUDE.md) - AI助手开发指南
- [README.md](README.md) - 项目概述
- [docs/HTTP_BRIDGE_README.md](docs/HTTP_BRIDGE_README.md) - HTTP API文档
- [docs/QUICKSTART.md](docs/QUICKSTART.md) - 快速入门

## 下一步

1. ✅ ROS 2工作空间改造完成
2. ✅ 使用colcon构建系统
3. ✅ 两个包成功构建
4. ✅ Launch文件正常工作
5. 🔄 测试摄像头和HTTP Bridge功能
6. 📋 添加CAN接口包（计划中）
7. 📋 添加WebSocket桥接包（计划中）
