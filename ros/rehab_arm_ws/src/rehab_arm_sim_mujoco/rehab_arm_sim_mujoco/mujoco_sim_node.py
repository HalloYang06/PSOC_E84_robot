#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import rclpy
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

from rehab_arm_sim_mujoco.mujoco_backend import (
    JOINT_NAMES,
    LEGACY_5DOF_PROFILE,
    LIMITS,
    RehabArmMujocoBackend,
    clamp,
    joint_names_for_profile,
    limits_for_profile,
)


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
        self.declare_parameter('model_path', '')
        self.declare_parameter('joint_profile', LEGACY_5DOF_PROFILE)
        self.declare_parameter('joint_state_topic', '/joint_states')
        self.declare_parameter('trajectory_topic', '/arm_controller/joint_trajectory')
        self.declare_parameter('safety_state_topic', '/rehab_arm/safety_state')
        self.declare_parameter('sensor_state_topic', '/rehab_arm/sensor_state')
        self.rate_hz = float(self.get_parameter('rate_hz').value)
        self.model_path = str(self.get_parameter('model_path').value or '')
        self.joint_profile = str(self.get_parameter('joint_profile').value or LEGACY_5DOF_PROFILE)
        self.joint_names = joint_names_for_profile(self.joint_profile)
        self.limits = limits_for_profile(self.joint_profile)
        self.joint_state_topic = str(self.get_parameter('joint_state_topic').value)
        self.trajectory_topic = str(self.get_parameter('trajectory_topic').value)
        self.safety_state_topic = str(self.get_parameter('safety_state_topic').value)
        self.sensor_state_topic = str(self.get_parameter('sensor_state_topic').value)
        self.positions = [0.0] * len(self.joint_names)
        self.velocities = [0.0] * len(self.joint_names)
        self.desired_positions = [0.0] * len(self.joint_names)
        self.segments: list[TrajectorySegment] = []
        self.last_time = self.get_clock().now().nanoseconds / 1e9
        self.safety_state = 'ok'
        self.safety_detail = 'simulation ready'
        self.next_safety_publish_time = self.last_time

        self.joint_pub = self.create_publisher(JointState, self.joint_state_topic, 20)
        self.safety_pub = self.create_publisher(String, self.safety_state_topic, 10)
        self.sensor_pub = self.create_publisher(String, self.sensor_state_topic, 10)
        self.traj_sub = self.create_subscription(
            JointTrajectory,
            self.trajectory_topic,
            self.on_trajectory,
            10,
        )
        self.timer = self.create_timer(1.0 / self.rate_hz, self.on_timer)

        self.mujoco_backend = None
        try:
            self.mujoco_backend = RehabArmMujocoBackend(
                model_path=self.model_path,
                joint_profile=self.joint_profile,
            )
            self.backend = 'mujoco-model'
        except Exception as exc:
            self.backend = 'fallback-first-order'
            self.get_logger().warn(f'MuJoCo model backend unavailable, using fallback: {exc}')
        self.get_logger().info(
            f'Rehab arm simulation ready, backend={self.backend}, '
            f'joint_profile={self.joint_profile}, joint_state_topic={self.joint_state_topic}, '
            f'trajectory_topic={self.trajectory_topic}'
        )

    def on_trajectory(self, msg: JointTrajectory) -> None:
        name_to_index = {name: i for i, name in enumerate(self.joint_names)}
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
                    low, high, _ = self.limits[self.joint_names[dst_i]]
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
                self.desired_positions = list(segment.end_positions)
                self.segments.pop(0)
            else:
                alpha = (now - segment.start_time) / max(segment.end_time - segment.start_time, 1e-6)
                alpha = clamp(alpha, 0.0, 1.0)
                self.desired_positions = [
                    start + (end - start) * alpha
                    for start, end in zip(segment.start_positions, segment.end_positions)
                ]

        if self.mujoco_backend is not None:
            self.positions = self.mujoco_backend.step(self.desired_positions, dt)
        else:
            self.positions = list(self.desired_positions)
        self.velocities = [(pos - old) / dt for pos, old in zip(self.positions, previous)]
        self.publish_joint_state()
        self.publish_sensor_state()
        if now >= self.next_safety_publish_time:
            self.publish_safety(self.safety_state, self.safety_detail)
            self.next_safety_publish_time = now + 1.0

    def publish_joint_state(self) -> None:
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = list(self.positions)
        msg.velocity = list(self.velocities)
        msg.effort = [0.0] * len(self.joint_names)
        self.joint_pub.publish(msg)

    def publish_safety(self, state: str, detail: str) -> None:
        self.safety_state = state
        self.safety_detail = detail
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
    except (KeyboardInterrupt, ExternalShutdownException, RCLError):
        pass
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
