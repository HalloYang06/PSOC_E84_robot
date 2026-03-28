#!/bin/bash
# 安装 HTTP Bridge 依赖

echo "========================================="
echo "安装 HTTP Bridge 依赖"
echo "========================================="
echo ""

# 停用 venv
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate 2>/dev/null || true
fi

echo "正在安装 Python 包..."
/usr/bin/python3 -m pip install flask flask-cors --break-system-packages

echo ""
echo "验证安装..."
/usr/bin/python3 -c "import flask; print('✓ Flask 安装成功')"
/usr/bin/python3 -c "import flask_cors; print('✓ Flask-CORS 安装成功')"

echo ""
echo "========================================="
echo "依赖安装完成！"
echo "========================================="
