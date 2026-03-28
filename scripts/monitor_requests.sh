#!/bin/bash

# 实时监控HTTP请求日志

echo "=========================================="
echo "  实时监控 HTTP 请求"
echo "=========================================="
echo ""
echo "现在请在手机APP上操作，这里会显示所有请求"
echo "按 Ctrl+C 停止监控"
echo ""
echo "时间              方法   URL路径                    状态码"
echo "----------------------------------------------------------------"

# 获取服务器进程ID
PID=$(ps aux | grep "[h]ttp_bridge_server.py" | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "错误: HTTP Bridge服务器未运行"
    exit 1
fi

# 实时监控标准输出
tail -f /proc/$PID/fd/1 2>/dev/null | while read line; do
    # 只显示HTTP请求行
    if echo "$line" | grep -qE "GET|POST|PUT|DELETE|PATCH"; then
        echo "$line"
    fi
done
