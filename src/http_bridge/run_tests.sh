#!/bin/bash

# HTTP Bridge 测试脚本 - 使用虚拟环境

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/../venv"

echo "=========================================="
echo "  HTTP Bridge 测试工具"
echo "=========================================="
echo ""

# 检查虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 虚拟环境不存在"
    echo "请先运行: ./start_http_bridge.sh"
    exit 1
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 检查requests是否安装
if ! python -c "import requests" 2>/dev/null; then
    echo "安装requests..."
    pip install requests
fi

echo "运行测试..."
echo ""

# 运行测试
python "$SCRIPT_DIR/test_http_bridge.py"

# 停用虚拟环境
deactivate
