# OpenClaw Skills 使用指南

## 什么是 Skills？

Skills 是预定义的系统命令脚本，OpenClaw 可以直接调用它们，无需 AI 推理。

## 性能对比

| 方式 | 响应时间 | 说明 |
|------|---------|------|
| **使用 Skills** | 1-3 秒 ⚡ | 直接执行脚本 |
| **AI 推理** | 10-30 秒 | 需要模型生成代码 |

**速度提升: 5-10 倍！**

## 已配置的 Skills

### 摄像头相关

1. **find_camera** - 查找摄像头
2. **start_camera_stream** - 启动摄像头流
3. **stop_camera_stream** - 停止摄像头流
4. **take_photo** - 拍照

### 系统管理

5. **system_status** - 系统状态
6. **check_http_bridge** - HTTP Bridge 状态

## 使用方法

### 通过 OpenClaw AI（推荐）

直接发送自然语言指令，OpenClaw 会自动调用相应的 skill：

```
用户: "帮我找一下摄像头"
→ OpenClaw 调用 find_camera.sh

用户: "启动摄像头流"
→ OpenClaw 调用 start_camera_stream.sh

用户: "拍个照存到 /home/pi/photo.jpg"
→ OpenClaw 调用 take_photo.sh

用户: "系统状态怎么样"
→ OpenClaw 调用 system_status.sh
```

### 手动测试 Skills

```bash
cd /home/pi/nanopi_ros

# 列出所有 skills
./manage_skills.sh list

# 测试 skill
./manage_skills.sh test system_status.sh

# 运行 skill
./manage_skills.sh run find_camera.sh
./manage_skills.sh run take_photo.sh /dev/video45 /home/pi/test.jpg
```

## Skills 位置

```
/home/pi/.openclaw/agents/main/skills/
├── check_http_bridge.sh
├── find_camera.sh
├── start_camera_stream.sh
├── stop_camera_stream.sh
├── system_status.sh
├── take_photo.sh
└── README.md
```

## 添加新 Skill

1. 创建脚本文件：
```bash
nano /home/pi/.openclaw/agents/main/skills/my_skill.sh
```

2. 添加脚本内容：
```bash
#!/bin/bash
# Skill: 我的技能
# 描述: 做某件事情

echo "执行我的技能..."
# 你的代码
```

3. 添加执行权限：
```bash
chmod +x /home/pi/.openclaw/agents/main/skills/my_skill.sh
```

4. 重启 OpenClaw Gateway：
```bash
systemctl --user restart openclaw-gateway.service
```

## 示例对话

### 场景1: 查找并启动摄像头

```
用户: "帮我找一下摄像头在哪"
AI: [调用 find_camera.sh]
    "找到以下摄像头设备：
     - /dev/video45 (USB Camera)
     推荐使用 /dev/video45"

用户: "好的，启动摄像头流，发送到 10.100.191.235"
AI: [调用 start_camera_stream.sh 10.100.191.235 8080 45 10]
    "✓ 摄像头流已启动
     服务器: 10.100.191.235:8080
     帧率: 10 FPS"
```

### 场景2: 拍照并分析

```
用户: "拍个照存到 /home/pi/photo.jpg"
AI: [调用 take_photo.sh /dev/video45 /home/pi/photo.jpg]
    "✓ 拍照成功: /home/pi/photo.jpg"

用户: "分析这张照片里有什么"
AI: [读取图片并分析]
    "照片中有..."
```

### 场景3: 系统监控

```
用户: "系统状态怎么样"
AI: [调用 system_status.sh]
    "CPU: 7.5%
     内存: 已用 2.1G / 总计 4G
     温度: 38°C
     运行时间: 36 分钟"
```

## 优势

1. **快速响应** - 1-3 秒完成操作
2. **可靠性高** - 预定义脚本，不会出错
3. **易于维护** - 直接修改脚本即可
4. **可扩展** - 随时添加新 skills

## 故障排除

### Skill 未被识别

```bash
# 检查文件权限
ls -l /home/pi/.openclaw/agents/main/skills/

# 确保有执行权限
chmod +x /home/pi/.openclaw/agents/main/skills/*.sh

# 重启 OpenClaw Gateway
systemctl --user restart openclaw-gateway.service
```

### Skill 执行失败

```bash
# 手动测试 skill
/home/pi/.openclaw/agents/main/skills/skill_name.sh

# 查看错误信息
bash -x /home/pi/.openclaw/agents/main/skills/skill_name.sh
```

## 更多信息

- Skills 目录: `/home/pi/.openclaw/agents/main/skills/`
- 管理工具: `./manage_skills.sh`
- OpenClaw 文档: https://docs.openclaw.ai
