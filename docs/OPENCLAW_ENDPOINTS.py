#!/usr/bin/env python3
"""
添加OpenClaw APP兼容端点
在http_bridge_server.py中添加这些路由
"""

# 常见的OpenClaw APP可能请求的端点：

# 1. /api/openclaw - 主状态端点
@app.route('/api/openclaw', methods=['GET'])
def openclaw_api():
    """OpenClaw主API端点 - 返回系统状态"""
    return get_status()

# 2. /api/openclaw/status - 状态查询
@app.route('/api/openclaw/status', methods=['GET'])
def openclaw_status():
    """OpenClaw状态查询"""
    return get_status()

# 3. /api/openclaw/control - 控制命令
@app.route('/api/openclaw/control', methods=['POST'])
def openclaw_control():
    """OpenClaw控制命令"""
    return send_control()

# 4. /api/openclaw/mode - 模式切换
@app.route('/api/openclaw/mode', methods=['POST'])
def openclaw_mode():
    """OpenClaw模式切换"""
    return set_mode()

# 5. /api/v1/* - 版本化API
@app.route('/api/v1/status', methods=['GET'])
def api_v1_status():
    """API v1 状态"""
    return get_status()

@app.route('/api/v1/control', methods=['POST'])
def api_v1_control():
    """API v1 控制"""
    return send_control()

# 6. /psoc/* - PSoC兼容端点
@app.route('/psoc/status', methods=['GET'])
def psoc_status():
    """PSoC状态端点"""
    return get_status()

@app.route('/psoc/command', methods=['POST'])
def psoc_command():
    """PSoC命令端点"""
    return api_command()
