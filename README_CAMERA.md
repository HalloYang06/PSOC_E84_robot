# 摄像头 WebSocket 客户端使用说明

## 启动摄像头流

```bash
cd /home/pi/nanopi_ros
./start_camera.sh [服务器IP] [端口] [摄像头ID] [帧率]
```

### 默认参数

```bash
./start_camera.sh
# 等同于:
# 服务器: 10.100.191.235:8080
# 摄像头: -1 (自动检测)
# 帧率: 10 FPS
```

### 自定义参数

```bash
# 指定服务器地址
./start_camera.sh 192.168.1.100

# 指定服务器和端口
./start_camera.sh 192.168.1.100 8080

# 指定摄像头ID（45是你的USB摄像头）
./start_camera.sh 192.168.1.100 8080 45

# 指定帧率
./start_camera.sh 192.168.1.100 8080 45 15
```

## 停止摄像头流

按 `Ctrl+C`

## 摄像头设置

- **分辨率**: 640x480
- **格式**: MJPEG
- **编码**: JPEG (质量 80%)
- **翻转**: 无（已移除水平翻转）

## 查找可用摄像头

```bash
v4l2-ctl --list-devices
# 或
ls /dev/video*
```

## 测试摄像头

```bash
# 测试摄像头45
v4l2-ctl -d /dev/video45 --all
```

## 故障排除

### 摄像头无法打开

```bash
# 检查权限
sudo usermod -a -G video $USER
# 重新登录生效
```

### 找不到摄像头

```bash
# 列出所有视频设备
ls -l /dev/video*

# 查看设备信息
v4l2-ctl --list-devices
```

### 服务器连接失败

- 检查服务器地址和端口
- 确认服务器正在运行
- 检查防火墙设置

## 与 HTTP Bridge 一起使用

可以同时运行摄像头客户端和 HTTP Bridge：

**终端1 - HTTP Bridge:**
```bash
./start_openclaw_bridge.sh
```

**终端2 - 摄像头:**
```bash
./start_camera.sh
```

两个服务独立运行，互不干扰。
