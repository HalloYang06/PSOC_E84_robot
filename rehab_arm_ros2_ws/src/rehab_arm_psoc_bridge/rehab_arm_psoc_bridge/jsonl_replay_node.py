#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

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

from rehab_arm_psoc_bridge.data_recording import build_replay_plan, load_jsonl_records


DEFAULT_REPLAY_TOPICS = [
    '/joint_states',
    '/rehab_arm/motor_state',
    '/rehab_arm/safety_state',
    '/rehab_arm/sensor_state',
    '/rehab_arm/camera_keyframe',
]


def is_shutdown_runtime_error(exc: RuntimeError) -> bool:
    return 'Unable to convert call argument' in str(exc)


def parse_topic_list(text: str) -> list[str]:
    if not text.strip():
        return list(DEFAULT_REPLAY_TOPICS)
    return [item.strip() for item in text.split(',') if item.strip()]


def payload_to_json_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def set_joint_state_from_payload(msg, payload: object, stamp) -> bool:
    if not isinstance(payload, dict):
        return False
    names = payload.get('name')
    if not isinstance(names, list):
        return False
    positions = payload.get('position', [])
    velocities = payload.get('velocity', [])
    efforts = payload.get('effort', [])
    if not isinstance(positions, list):
        positions = []
    if not isinstance(velocities, list):
        velocities = []
    if not isinstance(efforts, list):
        efforts = []
    msg.header.stamp = stamp
    msg.name = [str(name) for name in names]
    msg.position = [float(value) for value in positions if isinstance(value, (int, float))]
    msg.velocity = [float(value) for value in velocities if isinstance(value, (int, float))]
    msg.effort = [float(value) for value in efforts if isinstance(value, (int, float))]
    return True


class RehabArmJsonlReplay(Node):
    def __init__(self):
        super().__init__('rehab_arm_jsonl_replay')
        self.declare_parameter('recording_path', '')
        self.declare_parameter('topics', ','.join(DEFAULT_REPLAY_TOPICS))
        self.declare_parameter('speed', 1.0)
        self.declare_parameter('loop', False)
        self.declare_parameter('timer_period_sec', 0.01)

        recording_path = str(self.get_parameter('recording_path').value)
        if not recording_path:
            raise ValueError('recording_path parameter is required')
        topics = parse_topic_list(str(self.get_parameter('topics').value))
        self.speed = max(0.001, float(self.get_parameter('speed').value))
        self.loop = bool(self.get_parameter('loop').value)

        plan = build_replay_plan(load_jsonl_records(Path(recording_path)), topics=topics)
        self.events = list(plan['events'])
        self.event_index = 0
        self.start_wall = time.monotonic()

        self.joint_state_pub = self.create_publisher(JointState, '/joint_states', 20)
        self.string_publishers = {
            topic: self.create_publisher(String, topic, 20)
            for topic in topics
            if topic != '/joint_states'
        }

        timer_period = max(0.001, float(self.get_parameter('timer_period_sec').value))
        self.create_timer(timer_period, self.on_timer)
        self.get_logger().info(
            f'JSONL replay loaded {len(self.events)} events from {recording_path}; '
            f'topics={topics}; speed={self.speed}; loop={self.loop}'
        )

    def on_timer(self) -> None:
        if not self.events:
            return
        elapsed = (time.monotonic() - self.start_wall) * self.speed
        while self.event_index < len(self.events):
            event = self.events[self.event_index]
            if float(event.get('relative_time_sec', 0.0)) > elapsed:
                break
            self.publish_event(event)
            self.event_index += 1

        if self.event_index >= len(self.events) and self.loop:
            self.event_index = 0
            self.start_wall = time.monotonic()

    def publish_event(self, event: dict[str, object]) -> None:
        topic = event.get('topic')
        payload = event.get('payload')
        if topic == '/joint_states':
            msg = JointState()
            if set_joint_state_from_payload(msg, payload, self.get_clock().now().to_msg()):
                self.joint_state_pub.publish(msg)
            return

        publisher = self.string_publishers.get(str(topic))
        if publisher is None:
            return
        msg = String()
        msg.data = payload_to_json_text(payload)
        publisher.publish(msg)


def main(args=None):
    if rclpy is None:
        raise RuntimeError('jsonl_replay_node.py requires ROS2 rclpy')
    rclpy.init(args=args)
    node = RehabArmJsonlReplay()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except RuntimeError as exc:
        if not is_shutdown_runtime_error(exc):
            raise
    finally:
        try:
            node.destroy_node()
        except KeyboardInterrupt:
            pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except KeyboardInterrupt:
                pass


if __name__ == '__main__':
    main()
