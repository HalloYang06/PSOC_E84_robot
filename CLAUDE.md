# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a ROS 2 Jazzy workspace for real-time CAN communication and WebSocket bridging on embedded Linux (NanoPi/Raspberry Pi). The system enables bidirectional communication between:
- CAN hardware (Infineon controller via SocketCAN)
- ROS 2 nodes (C++ for performance-critical paths)
- Remote servers via WebSocket (100Hz target rate)
- VLA (Vision-Language-Action) control systems
- Camera streaming (USB/CSI cameras via OpenCV)

## Architecture

The system consists of three main components:

1. **CAN Node (C++)**: Interfaces with SocketCAN to read/write CAN frames at 100Hz, publishes to ROS topics
2. **WebSocket Bridge (C++)**: Bidirectional bridge using Boost.Beast, forwards CAN data to remote servers and receives commands
3. **Python Scripts**: Monitoring, visualization, and auxiliary control

Data flow: `CAN Hardware ↔ CAN Node ↔ ROS Topics ↔ WebSocket Bridge ↔ Remote Server/VLA`

## Expected Directory Structure

```
~/ros2_ws/
├── src/
│   ├── can_interface/          # CAN communication package (C++)
│   ├── websocket_bridge/       # WebSocket bridge package (C++)
│   └── control_scripts/        # Python auxiliary scripts
└── install/
```

## Hardware Setup

### CAN Interface Configuration

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

## Dependencies

### System Packages
```bash
# ROS 2 Jazzy
sudo apt install ros-jazzy-rclcpp ros-jazzy-std-msgs ros-jazzy-message-filters

# CAN utilities
sudo apt install can-utils

# C++ libraries
sudo apt install libboost-all-dev

# Camera and vision
sudo apt install libopencv-dev nlohmann-json3-dev v4l-utils

# Python
pip3 install websockets rclpy
```

### Quick Install
```bash
chmod +x install_deps.sh
./install_deps.sh
```

## Build and Run

### Camera WebSocket Client (Standalone)
```bash
# Build
mkdir build && cd build
cmake ..
make

# Run with default settings (server: 10.100.191.235:8080, camera: 0, fps: 10)
./camera_websocket_client

# Run with custom parameters
./camera_websocket_client [server_ip] [port] [camera_id] [fps]
./camera_websocket_client 10.100.191.235 8080 0 15

# Check available cameras
v4l2-ctl --list-devices
```

### Build Workspace
```bash
cd ~/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

### Launch Nodes
```bash
# Launch CAN interface
ros2 launch can_interface can.launch.py

# Launch WebSocket bridge
ros2 launch websocket_bridge bridge.launch.py
```

### Monitoring
```bash
# Check topic frequency
ros2 topic hz /can_rx

# View CAN data
ros2 topic echo /can_rx

# Raw CAN monitoring
candump can0
```

## Message Format

### Custom CAN Message (can_msgs/msg/CanFrame.msg)
```
std_msgs/Header header
uint32 can_id
uint8[] data
bool is_extended
bool is_error
```

### WebSocket Protocol

**ROS → Server (sensor data)**:
```json
{
  "type": "ros_data",
  "dataType": "motors|sensors|image|audio",
  "payload": [...]
}
```

**VLA → ROS (commands)**:
```json
{
  "type": "vla_command",
  "command": {
    "action": "move_forward",
    "params": {"distance": 1.0, "speed": 0.5}
  }
}
```

## Performance Considerations

- **QoS Settings**: CAN data uses RELIABLE + KEEP_LAST(10), WebSocket uses BEST_EFFORT + KEEP_LAST(1)
- **Threading**: CAN I/O runs on dedicated thread with SCHED_FIFO priority, WebSocket uses Boost.Asio thread pool, ROS uses MultiThreadedExecutor (2-4 threads)
- **Zero-copy**: Enable `intra_process_comms` for shared_ptr message passing
- **CPU Affinity**: Pin real-time threads to specific cores to avoid context switching

## Testing

### CAN Loopback Test
```bash
cansend can0 123#DEADBEEF
```

### WebSocket Test
```python
import asyncio
import websockets

async def test():
    async with websockets.connect('ws://localhost:9002') as ws:
        await ws.send('{"id": 0x123, "data": [1,2,3,4]}')
        response = await ws.recv()
        print(response)

asyncio.run(test())
```

## Language Notes

Architecture documentation is in Chinese (架构.md). Code comments and commit messages should follow the existing language conventions in the codebase.
