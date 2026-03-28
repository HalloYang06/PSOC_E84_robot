以下是ros_client.py
#!/usr/bin/env python3
"""
ROS WebSocket客户端示例
在NanoPi上运行，发送图像、语音、电机和传感器数据到WebSocket服务器
"""

import asyncio
import websockets
import json
import base64A
from datetime import datetime

# WebSocket服务器地址（替换为你的公网IP或域名）
WS_SERVER = "ws://YOUR_SERVER_IP:8080"

class ROSWebSocketClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.ws = None

    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            self.ws = await websockets.connect(self.server_url)
            print(f"Connected to {self.server_url}")

            # 注册为ROS客户端
            await self.ws.send(json.dumps({
                "type": "register",
                "role": "ros"
            }))

            response = await self.ws.recv()
            print(f"Registration response: {response}")

        except Exception as e:
            print(f"Connection error: {e}")
            raise

    async def send_image(self, image_data):
        """
        发送图像数据
        image_data: base64编码的图像字符串，或者图像文件路径
        """
        if self.ws is None:
            print("Not connected")
            return

        try:
            # 如果是文件路径，读取并编码
            if isinstance(image_data, str) and image_data.endswith(('.jpg', '.png', '.jpeg')):
                with open(image_data, 'rb') as f:
                    image_bytes = f.read()
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    image_data = f"data:image/jpeg;base64,{image_base64}"

            message = {
                "type": "ros_data",
                "dataType": "image",
                "payload": image_data
            }

            await self.ws.send(json.dumps(message))
            print("Image sent")

        except Exception as e:
            print(f"Error sending image: {e}")

    async def send_audio(self, audio_data):
        """
        发送语音数据
        audio_data: base64编码的音频字符串，或者音频文件路径
        """
        if self.ws is None:
            print("Not connected")
            return

        try:
            # 如果是文件路径，读取并编码
            if isinstance(audio_data, str) and audio_data.endswith(('.wav', '.mp3', '.ogg')):
                with open(audio_data, 'rb') as f:
                    audio_bytes = f.read()
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                    audio_data = f"data:audio/wav;base64,{audio_base64}"

            message = {
                "type": "ros_data",
                "dataType": "audio",
                "payload": audio_data
            }

            await self.ws.send(json.dumps(message))
            print("Audio sent")

        except Exception as e:
            print(f"Error sending audio: {e}")

    async def send_motor_data(self, motors):
        """
        发送电机数据
        motors: 电机数据列表，每个电机包含 position, velocity, current
        示例: [
            {"position": 45.5, "velocity": 1.2, "current": 0.5},
            {"position": 90.0, "velocity": 0.8, "current": 0.3},
            ...
        ]
        """
        if self.ws is None:
            print("Not connected")
            return

        try:
            message = {
                "type": "ros_data",
                "dataType": "motors",
                "payload": motors
            }

            await self.ws.send(json.dumps(message))
            print(f"Motor data sent: {len(motors)} motors")

        except Exception as e:
            print(f"Error sending motor data: {e}")

    async def send_sensor_data(self, sensors):
        """
        发送传感器数据
        sensors: 传感器数据列表
        示例: [
            {"name": "温度", "value": 25.5, "unit": "°C"},
            {"name": "湿度", "value": 60, "unit": "%"},
            {"name": "距离", "value": 150, "unit": "cm"}
        ]
        """
        if self.ws is None:
            print("Not connected")
            return

        try:
            message = {
                "type": "ros_data",
                "dataType": "sensors",
                "payload": sensors
            }

            await self.ws.send(json.dumps(message))
            print(f"Sensor data sent: {len(sensors)} sensors")

        except Exception as e:
            print(f"Error sending sensor data: {e}")

    async def receive_commands(self):
        """接收来自VLA的指令"""
        try:
            async for message in self.ws:
                data = json.loads(message)

                if data.get("type") == "vla_command":
                    command = data.get("command")
                    print(f"Received VLA command: {command}")
                    # 在这里处理VLA发来的指令
                    # 例如：控制机器人移动、执行动作等

        except Exception as e:
            print(f"Error receiving commands: {e}")

    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
            print("Connection closed")


# 使用示例
async def main():
    client = ROSWebSocketClient(WS_SERVER)

    try:
        await client.connect()

        # 创建接收指令的任务
        receive_task = asyncio.create_task(client.receive_commands())

        # 模拟发送数据
        while True:
            # 发送电机数据（5个电机）
            motor_data = [
                {"position": 45.5, "velocity": 1.2, "current": 0.5},
                {"position": 90.0, "velocity": 0.8, "current": 0.3},
                {"position": 30.2, "velocity": 1.5, "current": 0.6},
                {"position": 60.8, "velocity": 0.9, "current": 0.4},
                {"position": 120.5, "velocity": 1.1, "current": 0.55}
            ]
            await client.send_motor_data(motor_data)

            # 发送传感器数据
            sensor_data = [
                {"name": "温度", "value": 25.5, "unit": "°C"},
                {"name": "湿度", "value": 60, "unit": "%"},
                {"name": "距离", "value": 150, "unit": "cm"},
                {"name": "电压", "value": 12.5, "unit": "V"}
            ]
            await client.send_sensor_data(sensor_data)

            # 如果有图像，发送图像
            # await client.send_image("/path/to/image.jpg")

            # 如果有语音，发送语音
            # await client.send_audio("/path/to/audio.wav")

            await asyncio.sleep(1)  # 每秒发送一次

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
以下是vla_client.py
#!/usr/bin/env python3
"""
VLA WebSocket客户端示例
用于VLA发送控制指令到ROS
"""

import asyncio
import websockets
import json

# WebSocket服务器地址（替换为你的公网IP或域名）
WS_SERVER = "ws://YOUR_SERVER_IP:8080"

class VLAWebSocketClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.ws = None

    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            self.ws = await websockets.connect(self.server_url)
            print(f"Connected to {self.server_url}")

            # 注册为VLA客户端
            await self.ws.send(json.dumps({
                "type": "register",
                "role": "vla"
            }))

            response = await self.ws.recv()
            print(f"Registration response: {response}")

        except Exception as e:
            print(f"Connection error: {e}")
            raise

    async def send_command(self, command):
        """
        发送控制指令到ROS
        command: 指令字典
        示例: {
            "action": "move",
            "params": {"x": 1.0, "y": 0.5, "theta": 0.0}
        }
        """
        if self.ws is None:
            print("Not connected")
            return

        try:
            message = {
                "type": "vla_command",
                "command": command
            }

            await self.ws.send(json.dumps(message))
            print(f"Command sent: {command}")

        except Exception as e:
            print(f"Error sending command: {e}")

    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
            print("Connection closed")


# 使用示例
async def main():
    client = VLAWebSocketClient(WS_SERVER)

    try:
        await client.connect()

        # 示例：发送不同类型的指令
        commands = [
            {
                "action": "move_forward",
                "params": {"distance": 1.0, "speed": 0.5}
            },
            {
                "action": "rotate",
                "params": {"angle": 90, "direction": "left"}
            },
            {
                "action": "grasp",
                "params": {"force": 0.8}
            },
            {
                "action": "set_motor",
                "params": {"motor_id": 1, "position": 45.0}
            }
        ]

        for cmd in commands:
            await client.send_command(cmd)
            await asyncio.sleep(2)  # 每2秒发送一个指令

        # 保持连接
        await asyncio.sleep(10)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
这个是我的服务器的readme.md的内容
# ROS-VLA WebSocket 通信服务器

实时WebSocket服务器，用于ROS和VLA之间的双向通信，支持图像、语音、电机、传感器数据传输和指令控制。

## 功能特性

- ✅ ROS数据实时上传（图像、语音、电机、传感器）
- ✅ VLA指令下发到ROS
- ✅ Web实时监控界面
- ✅ 自动重连机制
- ✅ 多客户端支持

## 快速开始

### 1. 安装依赖

```bash
cd ros-vla-websocket
npm install
```

### 2. 启动服务器

```bash
npm start
```

服务器将在 `http://0.0.0.0:8080` 启动

### 3. 访问监控界面

浏览器打开: `http://YOUR_SERVER_IP:8080`

## 客户端使用

### ROS客户端（NanoPi）

1. 安装Python依赖:
```bash
pip3 install websockets
```

2. 修改 `ros_client.py` 中的服务器地址:
```python
WS_SERVER = "ws://YOUR_SERVER_IP:8080"
```

3. 运行客户端:
```bash
python3 ros_client.py
```

### VLA客户端

1. 安装Python依赖:
```bash
pip3 install websockets
```

2. 修改 `vla_client.py` 中的服务器地址:
```python
WS_SERVER = "ws://YOUR_SERVER_IP:8080"
```

3. 运行客户端:
```bash
python3 vla_client.py
```

## 数据格式

### ROS发送数据

**图像数据:**
```json
{
  "type": "ros_data",
  "dataType": "image",
  "payload": "data:image/jpeg;base64,..."
}
```

**电机数据:**
```json
{
  "type": "ros_data",
  "dataType": "motors",
  "payload": [
    {"position": 45.5, "velocity": 1.2, "current": 0.5},
    {"position": 90.0, "velocity": 0.8, "current": 0.3}
  ]
}
```

**传感器数据:**
```json
{
  "type": "ros_data",
  "dataType": "sensors",
  "payload": [
    {"name": "温度", "value": 25.5, "unit": "°C"},
    {"name": "湿度", "value": 60, "unit": "%"}
  ]
}
```

### VLA发送指令

```json
{
  "type": "vla_command",
  "command": {
    "action": "move_forward",
    "params": {"distance": 1.0, "speed": 0.5}
  }
}
```

## 公网部署

### 方法1: 使用云服务器

1. 购买云服务器（阿里云、腾讯云等）
2. 开放8080端口
3. 上传代码并运行

### 方法2: 使用内网穿透

使用frp、ngrok等工具将本地服务映射到公网

**frp示例配置:**
```ini
[websocket]
type = tcp
local_ip = 127.0.0.1
local_port = 8080
remote_port = 8080
```

### 方法3: 使用Cloudflare Tunnel

免费且稳定的内网穿透方案

## 端口配置

修改端口可以通过环境变量:
```bash
PORT=3000 npm start
```

## 安全建议

1. 生产环境建议添加认证机制
2. 使用HTTPS/WSS加密传输
3. 限制客户端连接数
4. 添加数据大小限制

## 故障排查

**连接失败:**
- 检查防火墙设置
- 确认服务器IP和端口正确
- 查看服务器日志

**数据不显示:**
- 检查客户端是否正确注册
- 查看浏览器控制台错误
- 确认数据格式正确

## 许可证

MIT
