#!/usr/bin/env python3
"""
HTTP Bridge Server for OpenClaw <-> APP Communication
Python实现版本 - 更容易调试和快速迭代
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from flask import Flask, request, jsonify
from threading import Thread, Lock
import json
import time
import subprocess

# 全局状态
class SystemState:
    def __init__(self):
        self.lock = Lock()
        self.mode = "active"
        self.main_mode = "ACTIVE"
        self.is_emergency_stop = False
        self.is_safety_ok = True
        self.error_code = 0
        self.error_message = ""

        # 传感器数据
        self.motor1_angle = 0.0
        self.motor2_angle = 0.0
        self.imu_angle_x = 0.0
        self.emg_ch1 = 0.0
        self.heart_rate = 0
        self.motor1_temp = 25.0
        self.motor2_temp = 25.0
        self.timestamp = int(time.time() * 1000)

state = SystemState()

# ROS 2节点
class HttpBridgeNode(Node):
    def __init__(self):
        super().__init__('http_bridge_node')

        # 订阅CAN数据
        self.can_rx_sub = self.create_subscription(
            String,
            '/can_rx',
            self.can_rx_callback,
            10
        )

        # 发布控制命令
        self.can_tx_pub = self.create_publisher(String, '/can_tx', 10)

        self.get_logger().info('HTTP Bridge Node initialized')

    def can_rx_callback(self, msg):
        """接收CAN数据并更新系统状态"""
        try:
            data = json.loads(msg.data)
            with state.lock:
                state.motor1_angle = data.get('motor1_angle', state.motor1_angle)
                state.motor2_angle = data.get('motor2_angle', state.motor2_angle)
                state.imu_angle_x = data.get('imu_angle_x', state.imu_angle_x)
                state.emg_ch1 = data.get('emg_ch1', state.emg_ch1)
                state.heart_rate = data.get('heart_rate', state.heart_rate)
                state.motor1_temp = data.get('motor1_temp', state.motor1_temp)
                state.motor2_temp = data.get('motor2_temp', state.motor2_temp)
                state.timestamp = int(time.time() * 1000)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f'Failed to parse CAN data: {e}')

    def publish_command(self, cmd_dict):
        """发布控制命令到CAN"""
        msg = String()
        msg.data = json.dumps(cmd_dict)
        self.can_tx_pub.publish(msg)
        self.get_logger().info(f'Published command: {msg.data}')

# Flask应用
app = Flask(__name__)
ros_node = None

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"status": "ok"})

@app.route('/status', methods=['GET'])
def get_status():
    """获取系统状态和传感器数据"""
    with state.lock:
        status_data = {
            "timestamp": state.timestamp,
            "mode": state.mode,
            "main_mode": state.main_mode,
            "is_emergency_stop": state.is_emergency_stop,
            "is_safety_ok": state.is_safety_ok,
            "error_code": state.error_code,
            "error_message": state.error_message,
            "motor1_angle": state.motor1_angle,
            "motor2_angle": state.motor2_angle,
            "imu_angle_x": state.imu_angle_x,
            "emg_ch1": state.emg_ch1,
            "heart_rate": state.heart_rate,
            "motor1_temp": state.motor1_temp,
            "motor2_temp": state.motor2_temp,
            # 兼容字段
            "shoulder_angle": state.motor1_angle,
            "elbow_angle": state.motor2_angle,
            "lateral_position": state.imu_angle_x
        }
    return jsonify(status_data)

@app.route('/mode', methods=['POST'])
def set_mode():
    """切换控制模式"""
    data = request.get_json()
    mode = data.get('mode')

    if not mode:
        return jsonify({"error": "Missing mode parameter"}), 400

    with state.lock:
        state.mode = mode

    # 发送模式切换命令到CAN
    ros_node.publish_command({"type": "mode", "mode": mode})

    return jsonify({"success": True, "mode": mode})

@app.route('/control', methods=['POST'])
def send_control():
    """发送控制指令（被动模式）"""
    data = request.get_json()

    cmd = {"type": "control"}
    if 'shoulder_angle' in data:
        cmd['shoulder_angle'] = float(data['shoulder_angle'])
    if 'elbow_angle' in data:
        cmd['elbow_angle'] = float(data['elbow_angle'])
    if 'lateral_pos' in data:
        cmd['lateral_pos'] = float(data['lateral_pos'])

    ros_node.publish_command(cmd)

    return jsonify({"success": True})

@app.route('/memory/execute', methods=['POST'])
def execute_memory():
    """执行记忆动作"""
    data = request.get_json()
    action_id = data.get('action_id')

    if not action_id:
        return jsonify({"error": "Missing action_id parameter"}), 400

    ros_node.publish_command({"type": "memory", "action_id": action_id})

    return jsonify({"success": True})

@app.route('/memory/stop', methods=['POST'])
def stop_memory():
    """停止记忆动作"""
    ros_node.publish_command({"type": "stop_memory"})
    return jsonify({"success": True})

@app.route('/api/command', methods=['POST'])
def api_command():
    """OpenClaw工具调用"""
    data = request.get_json()
    tool = data.get('tool')
    parameters = data.get('parameters', {})

    if not tool:
        return jsonify({"error": "Missing tool parameter"}), 400

    ros_node.publish_command({
        "type": "tool",
        "tool": tool,
        "parameters": parameters
    })

    return jsonify({
        "success": True,
        "result": "Command sent to OpenClaw"
    })

@app.route('/api/sensor/data', methods=['GET'])
def get_sensor_data():
    """获取传感器数据（扩展端点）"""
    return get_status()

@app.route('/api/training/start', methods=['POST'])
def start_training():
    """开始训练会话"""
    data = request.get_json()
    patient_id = data.get('patient_id', 'unknown')
    mode = data.get('mode', 'active')

    session_id = f"session_{int(time.time())}"

    ros_node.publish_command({
        "type": "training_start",
        "patient_id": patient_id,
        "mode": mode,
        "session_id": session_id
    })

    return jsonify({
        "success": True,
        "session_id": session_id
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据"""
    # TODO: 实现统计数据收集
    return jsonify({
        "total_sessions": 0,
        "total_duration": 0,
        "average_score": 0
    })

def send_to_openclaw(message):
    """发送消息到OpenClaw并获取响应"""
    try:
        # 使用 openclaw agent 命令发送消息
        # 对于复杂任务（摄像头、图片分析等），需要更长的超时时间
        result = subprocess.run(
            ['openclaw', 'agent', '--agent', 'main', '--message', message, '--json'],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时，适合复杂任务
        )

        if result.returncode == 0:
            # 解析JSON响应
            try:
                response_data = json.loads(result.stdout)
                # 提取AI的回复文本 - 正确的路径是 result.payloads[0].text
                payloads = response_data.get('result', {}).get('payloads', [])
                if payloads and len(payloads) > 0:
                    reply = payloads[0].get('text', '')
                    if reply:
                        ros_node.get_logger().info(f'OpenClaw response: {reply[:100]}...')
                        return reply

                # 如果没有找到文本，记录完整响应用于调试
                ros_node.get_logger().warn(f'No text in OpenClaw response: {response_data}')
                return None

            except json.JSONDecodeError as e:
                ros_node.get_logger().error(f'Failed to parse OpenClaw response: {e}')
                return None
        else:
            ros_node.get_logger().error(f'OpenClaw command failed: {result.stderr}')
            return None

    except subprocess.TimeoutExpired:
        ros_node.get_logger().error('OpenClaw command timeout (5 minutes)')
        return None
    except Exception as e:
        ros_node.get_logger().error(f'Failed to call OpenClaw: {e}')
        return None

@app.route('/message', methods=['POST'])
def handle_message():
    """处理OpenClaw自然语言消息"""
    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({
            "success": False,
            "message": "",
            "error": "Missing message parameter"
        }), 400

    # 记录收到的消息
    ros_node.get_logger().info(f'Received message: {message}')

    # 发布消息到ROS话题（供其他节点处理）
    ros_node.publish_command({
        "type": "natural_language",
        "message": message
    })

    # 调用OpenClaw AI处理
    ai_response = send_to_openclaw(message)

    if ai_response:
        return jsonify({
            "success": True,
            "message": ai_response,
            "error": None
        })
    else:
        # 如果OpenClaw调用失败，返回默认响应
        return jsonify({
            "success": True,
            "message": f"收到消息: {message}（OpenClaw暂时不可用）",
            "error": None
        })

def run_flask_app():
    """在单独线程中运行Flask应用"""
    app.run(host='0.0.0.0', port=8081, debug=False, use_reloader=False)

def main(args=None):
    global ros_node

    # 初始化ROS 2
    rclpy.init(args=args)
    ros_node = HttpBridgeNode()

    # 在单独线程中启动Flask服务器
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()

    ros_node.get_logger().info('HTTP Bridge Server started on http://0.0.0.0:8081')

    try:
        # 运行ROS 2节点
        rclpy.spin(ros_node)
    except KeyboardInterrupt:
        pass
    finally:
        ros_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
