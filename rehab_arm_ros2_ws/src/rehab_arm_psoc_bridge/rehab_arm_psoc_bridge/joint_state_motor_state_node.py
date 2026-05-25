#!/usr/bin/env python3
from __future__ import annotations

import json

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from std_msgs.msg import String
except ModuleNotFoundError:
    rclpy = None
    ExternalShutdownException = Exception
    Node = object
    JointState = None
    String = None

from rehab_arm_psoc_bridge.data_recording import (
    make_motor_entries_from_joint_state,
    make_motor_state_payload,
)


def parse_joint_motor_map(text: str) -> dict[str, dict[str, object]]:
    if not text.strip():
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError('joint_motor_map must be a JSON object')
    result: dict[str, dict[str, object]] = {}
    for joint_name, value in payload.items():
        if not isinstance(value, dict):
            raise ValueError(f'joint_motor_map[{joint_name!r}] must be an object')
        result[str(joint_name)] = dict(value)
    return result


class JointStateMotorStateNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_joint_state_motor_state')
        self.declare_parameter('robot_id', 'rehab-arm-alpha')
        self.declare_parameter('device_id', 'nanopi-m5')
        self.declare_parameter('source', 'joint_state_bridge')
        self.declare_parameter('joint_motor_map', '')

        self.robot_id = str(self.get_parameter('robot_id').value)
        self.device_id = str(self.get_parameter('device_id').value)
        self.source = str(self.get_parameter('source').value)
        self.joint_motor_map = parse_joint_motor_map(str(self.get_parameter('joint_motor_map').value))

        self.publisher = self.create_publisher(String, '/rehab_arm/motor_state', 20)
        self.create_subscription(JointState, '/joint_states', self.on_joint_states, 20)
        self.get_logger().info('bridging /joint_states to /rehab_arm/motor_state telemetry')

    def on_joint_states(self, msg) -> None:
        motors = make_motor_entries_from_joint_state(
            names=list(msg.name),
            positions=list(msg.position),
            velocities=list(msg.velocity),
            efforts=list(msg.effort),
            joint_motor_map=self.joint_motor_map,
        )
        payload = make_motor_state_payload(
            motors=motors,
            robot_id=self.robot_id,
            device_id=self.device_id,
            source=self.source,
        )
        out = String()
        out.data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        self.publisher.publish(out)


def main(args=None):
    if rclpy is None:
        raise RuntimeError('joint_state_motor_state_node.py requires ROS2 rclpy')
    rclpy.init(args=args)
    node = JointStateMotorStateNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
