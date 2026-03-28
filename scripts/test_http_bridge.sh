#!/bin/bash

# OpenClaw HTTP Bridge 快速测试脚本

echo "=========================================="
echo "  OpenClaw HTTP Bridge 快速测试"
echo "=========================================="
echo ""

# 获取NanoPi IP
NANOPI_IP=$(hostname -I | awk '{print $1}')
BASE_URL="http://localhost:8081"

echo "NanoPi IP地址: $NANOPI_IP"
echo "测试URL: $BASE_URL"
echo ""

# 检查服务器是否运行
echo "检查HTTP Bridge服务器..."
if ! curl -s --connect-timeout 2 $BASE_URL/health > /dev/null 2>&1; then
    echo "❌ 错误: HTTP Bridge服务器未运行"
    echo ""
    echo "请先启动服务器:"
    echo "  source install/setup.bash"
    echo "  ros2 launch http_bridge http_bridge.launch.py"
    exit 1
fi
echo "✅ 服务器正在运行"
echo ""

# 测试1: 健康检查
echo "测试 1/6: GET /health"
response=$(curl -s $BASE_URL/health)
echo "  响应: $response"
if echo "$response" | grep -q "ok"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

# 测试2: 获取状态
echo "测试 2/6: GET /status"
response=$(curl -s $BASE_URL/status)
echo "  响应: $(echo $response | jq -C '.' 2>/dev/null || echo $response)"
if echo "$response" | grep -q "timestamp"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

# 测试3: 切换模式
echo "测试 3/6: POST /mode"
response=$(curl -s -X POST $BASE_URL/mode \
    -H "Content-Type: application/json" \
    -d '{"mode":"passive"}')
echo "  响应: $response"
if echo "$response" | grep -q "success"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

# 测试4: 发送控制指令
echo "测试 4/6: POST /control"
response=$(curl -s -X POST $BASE_URL/control \
    -H "Content-Type: application/json" \
    -d '{"shoulder_angle":45.0,"elbow_angle":30.0,"lateral_pos":15.0}')
echo "  响应: $response"
if echo "$response" | grep -q "success"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

# 测试5: 执行记忆动作
echo "测试 5/6: POST /memory/execute"
response=$(curl -s -X POST $BASE_URL/memory/execute \
    -H "Content-Type: application/json" \
    -d '{"action_id":"test_action_001"}')
echo "  响应: $response"
if echo "$response" | grep -q "success"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

# 测试6: OpenClaw工具调用
echo "测试 6/6: POST /api/command"
response=$(curl -s -X POST $BASE_URL/api/command \
    -H "Content-Type: application/json" \
    -d '{"tool":"move_joint","parameters":{"joint_id":1,"angle":45.0}}')
echo "  响应: $response"
if echo "$response" | grep -q "success"; then
    echo "  ✅ 通过"
else
    echo "  ❌ 失败"
fi
echo ""

echo "=========================================="
echo "  测试完成！"
echo "=========================================="
echo ""
echo "Android APP配置:"
echo "  服务器地址: $NANOPI_IP"
echo "  端口: 8081"
echo "  完整URL: http://$NANOPI_IP:8081"
echo ""
echo "从其他设备测试:"
echo "  curl http://$NANOPI_IP:8081/health"
echo ""
