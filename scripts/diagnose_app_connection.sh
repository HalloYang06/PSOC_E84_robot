#!/bin/bash

# APP连接诊断脚本

echo "=========================================="
echo "  OpenClaw APP 连接诊断"
echo "=========================================="
echo ""

# 获取IP
IP=$(hostname -I | awk '{print $1}')
echo "NanoPi IP: $IP"
echo "服务器端口: 8081"
echo ""

# 检查服务器
echo "1. 检查HTTP Bridge服务器状态..."
if ps aux | grep -q "[h]ttp_bridge_server.py"; then
    echo "   ✅ 服务器正在运行"
    PID=$(ps aux | grep "[h]ttp_bridge_server.py" | awk '{print $2}')
    echo "   进程ID: $PID"
else
    echo "   ❌ 服务器未运行"
    echo "   请运行: ./start_http_bridge.sh"
    exit 1
fi
echo ""

# 测试基本端点
echo "2. 测试基本端点..."
echo "   测试 /health:"
response=$(curl -s -w "\n%{http_code}" http://localhost:8081/health)
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | head -1)
if [ "$http_code" = "200" ]; then
    echo "   ✅ 200 OK - $body"
else
    echo "   ❌ $http_code - $body"
fi

echo "   测试 /status:"
response=$(curl -s -w "\n%{http_code}" http://localhost:8081/status)
http_code=$(echo "$response" | tail -1)
if [ "$http_code" = "200" ]; then
    echo "   ✅ 200 OK"
else
    echo "   ❌ $http_code"
fi
echo ""

# 列出所有可用端点
echo "3. 可用的API端点:"
echo "   GET  /health"
echo "   GET  /status"
echo "   POST /mode"
echo "   POST /control"
echo "   POST /memory/execute"
echo "   POST /memory/stop"
echo "   POST /api/command"
echo "   GET  /api/sensor/data"
echo "   POST /api/training/start"
echo "   GET  /api/stats"
echo ""

# 测试常见的404错误
echo "4. 测试APP可能请求的URL..."
test_urls=(
    "/api/openclaw"
    "/openclaw"
    "/api/v1/status"
    "/v1/status"
)

for url in "${test_urls[@]}"; do
    response=$(curl -s -w "\n%{http_code}" http://localhost:8081$url)
    http_code=$(echo "$response" | tail -1)
    if [ "$http_code" = "404" ]; then
        echo "   ❌ $url → 404 (不存在)"
    else
        echo "   ✅ $url → $http_code"
    fi
done
echo ""

# 网络测试
echo "5. 网络连接测试..."
echo "   从手机浏览器访问以下URL测试:"
echo "   http://$IP:8081/health"
echo ""
echo "   如果手机无法访问，检查:"
echo "   - 手机和NanoPi在同一WiFi网络"
echo "   - 防火墙设置: sudo ufw allow 8081/tcp"
echo ""

# 查看最近的请求日志
echo "6. 最近的HTTP请求 (最后10条):"
echo "   提示: 让APP发送请求，然后查看这里的日志"
echo "   按Ctrl+C停止监控"
echo ""
echo "   监控中..."

# 实时监控Flask输出
tail -f /proc/$PID/fd/1 2>/dev/null | grep --line-buffered "GET\|POST\|PUT\|DELETE" | head -10

echo ""
echo "=========================================="
echo "  诊断完成"
echo "=========================================="
