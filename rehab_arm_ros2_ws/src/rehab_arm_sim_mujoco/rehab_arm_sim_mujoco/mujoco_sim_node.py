#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory


JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]

LIMITS = {
    'shoulder_lift_joint': (-0.70, 1.40, 0.60),
    'elbow_lift_joint': (0.00, 1.80, 0.70),
    'shoulder_abduction_joint': (-0.45, 0.80, 0.40),
    'upper_arm_rotation_joint': (-1.20, 1.20, 0.70),
    'forearm_rotation_joint': (-1.20, 1.20, 0.70),
}


@dataclass
class TrajectorySegment:
    start_time: float
    end_time: float
    start_positions: list[float]
    end_positions: list[float]


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


class MujocoSimNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_mujoco_sim')
        self.declare_parameter('rate_hz', 100.0)
        self.rate_hz = float(self.get_parameter('rate_hz').value)
        self.positions = [0.0] * len(JOINT_NAMES)
        self.velocities = [0.0] * len(JOINT_NAMES)
        self.segments: list[TrajectorySegment] = []
        self.last_time = self.get_clock().now().nanoseconds / 1e9

        self.joint_pub = self.create_publisher(JointState, '/joint_states', 20)
        self.safety_pub = self.create_publisher(String, '/rehab_arm/safety_state', 10)
        self.sensor_pub = self.create_publisher(String, '/rehab_arm/sensor_state', 10)
        self.traj_sub = self.create_subscription(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            self.on_trajectory,
            10,
        )
        self.timer = self.create_timer(1.0 / self.rate_hz, self.on_timer)

        try:
            import mujoco  # noqa: F401
            self.backend = 'mujoco-python-available'
        except Exception:
            self.backend = 'fallback-first-order'
        self.get_logger().info(f'Rehab arm simulation ready, backend={self.backend}')

    def on_trajectory(self, msg: JointTrajectory) -> None:
        name_to_index = {name: i for i, name in enumerate(JOINT_NAMES)}
        incoming_indices = [name_to_index[name] for name in msg.joint_names if name in name_to_index]
        if not incoming_indices:
            self.get_logger().warn('Received trajectory with no known joints')
            return

        now = self.get_clock().now().nanoseconds / 1e9
        current = list(self.positions)
        previous_time = now
        previous_positions = current
        segments: list[TrajectorySegment] = []

        for point in msg.points:
            end_positions = list(previous_positions)
            for src_i, dst_i in enumerate(incoming_indices):
                if src_i < len(point.positions):
                    low, high, _ = LIMITS[JOINT_NAMES[dst_i]]
                    end_positions[dst_i] = clamp(float(point.positions[src_i]), low, high)
            point_time = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
            end_time = now + max(point_time, 0.02)
            if end_time <= previous_time:
                end_time = previous_time + 0.02
            segments.append(TrajectorySegment(previous_time, end_time, previous_positions, end_positions))
            previous_time = end_time
            previous_positions = end_positions

        self.segments = segments
        self.publish_safety('ok', 'trajectory accepted')

    def on_timer(self) -> None:
        now = self.get_clock().now().nanoseconds / 1e9
        dt = max(1.0 / self.rate_hz, now - self.last_time)
        previous = list(self.positions)
        self.last_time = now

        if self.segments:
            segment = self.segments[0]
            if now >= segment.end_time:
                self.positions = list(segment.end_positions)
                self.segments.pop(0)
            else:
                alpha = (now - segment.start_time) / max(segment.end_time - segment.start_time, 1e-6)
                alpha = clamp(alpha, 0.0, 1.0)
                self.positions = [
                    start + (end - start) * alpha
                    for start, end in zip(segment.start_positions, segment.end_positions)
                ]

        self.velocities = [(pos - old) / dt for pos, old in zip(self.positions, previous)]
        self.publish_joint_state()
        self.publish_sensor_state()

    def publish_joint_state(self) -> None:
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = JOINT_NAMES
        msg.position = list(self.positions)
        msg.velocity = list(self.velocities)
        msg.effort = [0.0] * len(JOINT_NAMES)
        self.joint_pub.publish(msg)

    def publish_safety(self, state: str, detail: str) -> None:
        payload = {'state': state, 'detail': detail, 'source': 'sim'}
        self.safety_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def publish_sensor_state(self) -> None:
        effort_hint = sum(abs(v) for v in self.velocities)
        payload = {
            'source': 'sim',
            'emg_ch1': round(0.10 + 0.02 * math.sin(effort_hint), 4),
            'emg_ch2': round(0.11 + 0.02 * math.cos(effort_hint), 4),
            'fatigue_score': 0.0,
            'heart_rate': 72,
            'imu_roll': 0.0,
            'imu_pitch': round(self.positions[0], 4),
        }
        self.sensor_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))


def main(args=None):
    rclpy.init(args=args)
    node = MujocoSimNode()
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
