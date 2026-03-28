#!/bin/bash
# 清理 HTTP Bridge 进程和端口

echo "========================================="
echo "清理 HTTP Bridge 进程"
echo "========================================="
echo ""

# 查找占用 8081 端口的进程
PORT_PID=$(lsof -ti :8081 2>/dev/null)

if [ -n "$PORT_PID" ]; then
    echo "发现占用端口 8081 的进程: $PORT_PID"
    kill -9 $PORT_PID 2>/dev/null
    echo "✓ 已清理端口 8081"
else
    echo "端口 8081 未被占用"
fi

# 清理所有 http_bridge 相关进程
HTTP_PIDS=$(pgrep -f "http_bridge")
if [ -n "$HTTP_PIDS" ]; then
    echo "发现 HTTP Bridge 进程: $HTTP_PIDS"
    pkill -9 -f "http_bridge"
    echo "✓ 已清理所有 HTTP Bridge 进程"
else
    echo "没有运行中的 HTTP Bridge 进程"
fi

sleep 1

# 验证
if lsof -i :8081 > /dev/null 2>&1; then
    echo "✗ 端口 8081 仍被占用"
    lsof -i :8081
    exit 1
else
    echo ""
    echo "✓ 清理完成，可以启动服务了"
fi

echo ""
echo "========================================="
