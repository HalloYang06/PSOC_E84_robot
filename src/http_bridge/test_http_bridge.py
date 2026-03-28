#!/usr/bin/env python3
"""
HTTP Bridge Server 测试工具
用于测试所有API端点
"""

import requests
import json
import time

# 配置
BASE_URL = "http://localhost:8081"  # 修改为NanoPi的实际IP

def test_health():
    """测试健康检查"""
    print("测试 GET /health")
    response = requests.get(f"{BASE_URL}/health")
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {response.json()}")
    print()

def test_status():
    """测试获取状态"""
    print("测试 GET /status")
    response = requests.get(f"{BASE_URL}/status")
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_set_mode():
    """测试切换模式"""
    print("测试 POST /mode")
    for mode in ["passive", "active", "memory"]:
        response = requests.post(f"{BASE_URL}/mode", json={"mode": mode})
        print(f"  切换到 {mode}: {response.json()}")
        time.sleep(0.5)
    print()

def test_control():
    """测试控制指令"""
    print("测试 POST /control")
    response = requests.post(f"{BASE_URL}/control", json={
        "shoulder_angle": 45.0,
        "elbow_angle": 30.0,
        "lateral_pos": 15.0
    })
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {response.json()}")
    print()

def test_memory():
    """测试记忆动作"""
    print("测试 POST /memory/execute")
    response = requests.post(f"{BASE_URL}/memory/execute", json={
        "action_id": "test_action_001"
    })
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {response.json()}")
    print()

    time.sleep(1)

    print("测试 POST /memory/stop")
    response = requests.post(f"{BASE_URL}/memory/stop", json={})
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {response.json()}")
    print()

def test_api_command():
    """测试OpenClaw工具调用"""
    print("测试 POST /api/command")
    response = requests.post(f"{BASE_URL}/api/command", json={
        "tool": "move_joint",
        "parameters": {
            "joint_id": 1,
            "angle": 45.0,
            "speed": 30.0
        }
    })
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {response.json()}")
    print()

def main():
    print("=" * 60)
    print("HTTP Bridge Server 测试工具")
    print("=" * 60)
    print()

    try:
        test_health()
        test_status()
        test_set_mode()
        test_control()
        test_memory()
        test_api_command()

        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print(f"错误: 无法连接到 {BASE_URL}")
        print("请确保HTTP Bridge Server正在运行")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == '__main__':
    main()
