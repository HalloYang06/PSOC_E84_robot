#!/bin/bash
# OpenClaw HTTP Bridge 测试脚本

SERVER="http://localhost:8081"

echo "========================================="
echo "OpenClaw HTTP Bridge 测试"
echo "========================================="
echo ""

# 1. 健康检查
echo "1. 健康检查 (GET /health)"
curl -s $SERVER/health | python3 -m json.tool
echo ""

# 2. 获取系统状态
echo "2. 获取系统状态 (GET /status)"
curl -s $SERVER/status | python3 -m json.tool
echo ""

# 3. 发送消息
echo "3. 发送消息 (POST /message)"
curl -X POST $SERVER/message \
  -H "Content-Type: application/json" \
  -d '{"message": "测试消息：请帮我抬起手臂"}' | python3 -m json.tool
echo ""

# 4. 切换模式
echo "4. 切换到被动模式 (POST /mode)"
curl -X POST $SERVER/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "passive"}' | python3 -m json.tool
echo ""

# 5. 发送控制指令
echo "5. 发送控制指令 (POST /control)"
curl -X POST $SERVER/control \
  -H "Content-Type: application/json" \
  -d '{"shoulder_angle": 45.0, "elbow_angle": 30.0}' | python3 -m json.tool
echo ""

# 6. API命令
echo "6. OpenClaw工具调用 (POST /api/command)"
curl -X POST $SERVER/api/command \
  -H "Content-Type: application/json" \
  -d '{"tool": "move_arm", "parameters": {"angle": 45}}' | python3 -m json.tool
echo ""

echo "========================================="
echo "测试完成！"
echo "========================================="
