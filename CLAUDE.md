# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ROS 2 Jazzy workspace for embedded robotics on NanoPi/Raspberry Pi. Implements camera streaming and HTTP API bridge for Android APP integration.

**Current Components:**
- Camera WebSocket client (C++ ROS 2 node) - streams camera frames to remote server
- HTTP Bridge server (Python ROS 2 node) - REST API for Android APP using OpenClaw protocol

**Planned Components:**
- CAN interface node for SocketCAN communication (100Hz)
- WebSocket bridge for VLA (Vision-Language-Action) control systems

## Architecture

```
Android APP ↔ HTTP Bridge (Python) ↔ ROS 2 Topics
Camera → Camera Client (C++) → WebSocket → Remote Server
(Future: CAN Hardware ↔ CAN Node ↔ ROS Topics)
```

## Directory Structure

```
nanopi_ros/                     # ROS 2 workspace root
├── src/
│   ├── camera_client/          # Camera streaming package (C++)
│   │   ├── camera_websocket_client.cpp
│   │   ├── launch/camera.launch.py
│   │   └── package.xml
│   └── http_bridge/            # HTTP API bridge package (Python)
│       ├── http_bridge/        # Python package
│       │   ├── __init__.py
│       │   └── http_bridge_server.py
│       ├── launch/http_bridge.launch.py
│       ├── setup.py
│       └── package.xml
├── launch/
│   └── system.launch.py        # Launch all nodes
├── build/, install/, log/      # ROS 2 build outputs (auto-generated)
├── scripts/                    # Utility scripts
├── docs/                       # Documentation
└── build_ros2.sh               # Main build script
```

## Build and Development

### ROS 2 Build System

**IMPORTANT**: This is a ROS 2 workspace. Use `colcon build`, NOT `catkin_make` (ROS 1) or standalone `cmake`.

### Build Commands

```bash
# Build entire workspace
./build_ros2.sh

# Build specific package
./build_ros2.sh --packages camera_client

# Debug build
./build_ros2.sh --debug

# Clean and rebuild
./build_ros2.sh --clean

# Or use colcon directly
colcon build --symlink-install
colcon build --packages-select camera_client
```

### Setup Environment

```bash
# Load ROS 2 environment (if not already loaded)
source /opt/ros/jazzy/setup.bash

# Load workspace overlay
source install/setup.bash
```

### Launch Nodes

```bash
# Launch individual nodes
ros2 launch camera_client camera.launch.py
ros2 launch http_bridge http_bridge.launch.py

# Launch all nodes
ros2 launch launch/system.launch.py

# Launch with parameters
ros2 launch camera_client camera.launch.py server_ip:=192.168.1.100 fps:=15
```

### Run Nodes Directly

```bash
# Camera client
ros2 run camera_client camera_websocket_client

# HTTP bridge
ros2 run http_bridge http_bridge_server
```

## Dependencies

### System Packages
```bash
# ROS 2 Jazzy base
sudo apt install ros-jazzy-desktop

# ROS 2 development tools
sudo apt install python3-colcon-common-extensions
sudo apt install ros-jazzy-ament-cmake ros-jazzy-ament-cmake-python

# ROS 2 packages
sudo apt install ros-jazzy-rclcpp ros-jazzy-rclpy
sudo apt install ros-jazzy-std-msgs ros-jazzy-sensor-msgs
sudo apt install ros-jazzy-cv-bridge ros-jazzy-image-transport

# Camera and vision
sudo apt install libopencv-dev v4l-utils

# C++ libraries
sudo apt install libboost-all-dev

# Python packages (system-wide via apt)
sudo apt install python3-catkin-pkg python3-empy python3-lark
sudo apt install python3-yaml python3-flask python3-flask-cors
```

### Virtual Environment Setup (for websockets)
```bash
# Create and activate venv
python3 -m venv venv
source venv/bin/activate

# Install Python packages in venv
pip install catkin_pkg empy lark pyyaml flask flask-cors websockets
```

### Quick Install
```bash
cd scripts
./install_deps.sh
```

**Note**: Due to PEP 668, system Python is externally managed. The install script uses `apt` for most packages. For packages not available via apt (like websockets), use the project's venv.

## ROS 2 Development

### Check Node Status
```bash
# List running nodes
ros2 node list

# Node information
ros2 node info /camera_websocket_client
ros2 node info /http_bridge_server
```

### Monitor Topics
```bash
# List topics
ros2 topic list

# Check topic frequency
ros2 topic hz /camera/image_raw

# View topic data
ros2 topic echo /camera/image_raw
```

### Parameters
```bash
# List parameters
ros2 param list

# Get parameter value
ros2 param get /camera_websocket_client server_ip

# Set parameter value
ros2 param set /camera_websocket_client fps 15
```

### Debugging
```bash
# View logs
ros2 run rqt_console rqt_console

# Check node graph
ros2 run rqt_graph rqt_graph
```

## Camera Client

### Features
- ROS 2 node for camera streaming
- Supports USB/CSI cameras via OpenCV
- JPEG compression for efficient transmission
- WebSocket client for remote streaming
- Configurable frame rate and camera selection

### Configuration
```bash
# Launch parameters
ros2 launch camera_client camera.launch.py \
    server_ip:=10.100.191.235 \
    server_port:=8080 \
    camera_id:=-1 \
    fps:=10
```

### Check Available Cameras
```bash
v4l2-ctl --list-devices
ls /dev/video*
```

## HTTP Bridge

### Features
- REST API server for Android APP
- Implements OpenClaw protocol
- ROS 2 topic integration
- Real-time sensor data streaming
- Control command interface

### API Endpoints
- `GET /health` - Health check
- `GET /status` - System status and sensor data
- `POST /mode` - Switch control mode (active/passive/memory)
- `POST /control` - Send control commands
- `POST /memory/execute` - Execute memory action
- `POST /memory/stop` - Stop memory action
- `POST /api/command` - OpenClaw tool calls

### Testing
```bash
# Test all endpoints
ros2 run http_bridge test_http_bridge.py

# Or use curl
curl http://localhost:8081/health
curl http://localhost:8081/status
```

### Android APP Configuration
```kotlin
val httpManager = PsocHttpManager()
httpManager.setBaseUrl("http://192.168.1.100:8081")  // Replace with NanoPi IP
```

## Hardware Setup (Future)

### CAN Interface Configuration
When CAN node is implemented:

```bash
# Load kernel modules
sudo modprobe can can_raw mcp251x

# Configure CAN0 (500kbps bitrate)
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Verify
ip link show can0
candump can0
```

## Troubleshooting

### Build Issues

**ROS 2 not found:**
```bash
source /opt/ros/jazzy/setup.bash
```

**colcon not found:**
```bash
sudo apt install python3-colcon-common-extensions
```

**Package dependencies missing:**
```bash
rosdep install --from-paths src --ignore-src -r -y
```

### Runtime Issues

**Camera cannot open:**
```bash
# Check camera permissions
sudo usermod -a -G video $USER
# Re-login for changes to take effect

# List available cameras
v4l2-ctl --list-devices
```

**HTTP server port occupied:**
```bash
sudo lsof -i :8081
```

**Node not found after build:**
```bash
# Make sure to source the workspace
source install/setup.bash
```

## Package Development

### Adding a New ROS 2 Package

```bash
# Create C++ package
cd src
ros2 pkg create --build-type ament_cmake my_package \
    --dependencies rclcpp std_msgs

# Create Python package
ros2 pkg create --build-type ament_python my_package \
    --dependencies rclpy std_msgs

# Build and test
cd ..
colcon build --packages-select my_package
source install/setup.bash
```

### Package Structure

**C++ Package (ament_cmake):**
- `CMakeLists.txt` - Build configuration
- `package.xml` - Package metadata and dependencies
- `include/` - Header files
- `src/` - Source files
- `launch/` - Launch files

**Python Package (ament_python):**
- `setup.py` - Python package setup
- `package.xml` - Package metadata
- `<package_name>/` - Python module directory
- `launch/` - Launch files
- `resource/` - Package marker

## Documentation

- [README.md](README.md) - Project overview and quick start
- [docs/HTTP_BRIDGE_README.md](docs/HTTP_BRIDGE_README.md) - HTTP API detailed documentation
- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Quick start guide
- [docs/架构.md](docs/架构.md) - Architecture documentation (Chinese)

## Language Notes

Architecture documentation and some code comments are in Chinese. Code and commit messages follow existing language conventions in the codebase.
